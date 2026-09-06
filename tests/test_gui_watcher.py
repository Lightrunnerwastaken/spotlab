import os
import shutil
import time

import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.gui.watcher import RunScanner, lauf_verzeichnisse  # noqa: E402
from spotlab.record.run import RunRecorder  # noqa: E402
from spotlab.workshop.project import create_project  # noqa: E402


def _runs(tmp_path):
    """Arbeitsordner mit einem Projekt — so sieht es in der GUI wirklich aus."""
    return create_project("demo", tmp_path) / "runs"


def _arten(ereignisse):
    return [art for art, _ in ereignisse]


def test_neuer_lauf_wird_gemeldet(tmp_path):
    scanner = RunScanner(tmp_path)
    assert scanner.tick() == []

    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    assert "lauf_begonnen" in _arten(scanner.tick())


def test_zustand_und_ereignisse_kommen_durch(tmp_path):
    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()

    rec.event("kommando", name="stand")
    rec.sample({"battery": 89.0})
    ereignisse = scanner.tick()

    zustaende = [d for art, d in ereignisse if art == "zustand"]
    kommandos = [d for art, d in ereignisse if art == "ereignis"]
    assert zustaende[-1]["daten"]["battery"] == 89.0
    assert kommandos[-1]["art"] == "kommando"


def test_alter_lauf_wird_beim_start_nicht_gemeldet(tmp_path):
    """Beim Öffnen der GUI sollen alte Läufe nicht als 'jetzt gestartet' erscheinen."""
    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    rec.finish("ok")
    alt = time.time() - 60
    os.utime(rec.dir / "zustand.jsonl", (alt, alt))

    assert RunScanner(tmp_path).tick() == []


def test_ende_wird_gemeldet(tmp_path):
    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()

    alt = time.time() - 60
    os.utime(rec.dir / "zustand.jsonl", (alt, alt))
    assert "lauf_beendet" in _arten(scanner.tick())


def test_bilder_werden_gemeldet(tmp_path):
    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()

    rec.image("frontleft", b"\x89PNG", {"source": "frontleft_fisheye_image"})
    bilder = [p for art, p in scanner.tick() if art == "bild"]
    assert bilder and bilder[0].endswith(".png")


def test_fehlender_ordner_wirft_nicht(tmp_path):
    assert RunScanner(tmp_path / "gibtsnicht").tick() == []


def test_verschwundener_lauf_wirft_nicht(tmp_path):
    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()
    shutil.rmtree(rec.dir)
    scanner.tick()  # darf nicht werfen


def test_watcher_sendet_qt_signale(tmp_path, qapp):
    from spotlab.gui.watcher import RunWatcher

    empfangen = []
    watcher = RunWatcher(tmp_path)
    watcher.lauf_begonnen.connect(lambda p: empfangen.append(("begonnen", p)))
    watcher.zustand.connect(lambda d: empfangen.append(("zustand", d)))

    rec = RunRecorder(_runs(tmp_path), None, backend="dryrun")
    rec.sample({"battery": 90.0})
    watcher._takt()  # Takt von Hand auslösen, ohne Ereignisschleife

    assert [a for a, _ in empfangen] == ["begonnen", "zustand"]


def test_beobachter_findet_laeufe_ueber_die_projekte_hinweg(tmp_path):
    """Der Beobachter bekommt den ARBEITSORDNER, nicht einen runs-Ordner.

    Regressionstest zu einem Fehler, den erst der End-zu-End-Lauf zeigte: der
    Scanner suchte direkt im Arbeitsordner nach Laufverzeichnissen und fand
    darum nie einen — die Live-Ansicht wäre im Unterricht immer leer geblieben.
    """
    a = create_project("projekt-a", tmp_path)
    b = create_project("projekt-b", tmp_path)
    rec_a = RunRecorder(a / "runs", None, backend="dryrun")
    rec_a.sample({"battery": 90.0})
    rec_b = RunRecorder(b / "runs", None, backend="dryrun")
    rec_b.sample({"battery": 80.0})

    gefunden = [p for art, p in RunScanner(tmp_path).tick() if art == "lauf_begonnen"]
    assert sorted(gefunden) == sorted([str(rec_a.dir), str(rec_b.dir)])


def test_laufverzeichnisse_ignoriert_projektlose_ordner(tmp_path):
    create_project("echt", tmp_path)
    (tmp_path / "kein-projekt").mkdir()
    assert lauf_verzeichnisse(tmp_path) == []


def test_gleiche_lauf_id_in_zwei_projekten_kollidiert_nicht(tmp_path):
    """Der Scanner schlüsselt nach vollem Pfad, nicht nach Verzeichnisnamen."""
    a = create_project("a", tmp_path)
    b = create_project("b", tmp_path)
    for projekt in (a, b):
        ziel = projekt / "runs" / "20260807T120000Z_gleich"
        (ziel / "bilder").mkdir(parents=True)
        (ziel / "zustand.jsonl").write_text('{"t": 0.0, "daten": {}}\n', encoding="utf-8")
        (ziel / "lauf.json").write_text('{"id": "x"}', encoding="utf-8")

    gefunden = [p for art, p in RunScanner(tmp_path).tick() if art == "lauf_begonnen"]
    assert len(gefunden) == 2


def test_die_ansicht_wird_gemeldet_wenn_sie_sich_aendert(tmp_path):
    """Das MuJoCo-Backend ersetzt <lauf>/ansicht.jpg atomar, hoechstens zehnmal
    je Sekunde. Der Watcher meldet die Datei nur, wenn sie sich geaendert hat --
    sonst zeichnete die GUI viermal je Sekunde dasselbe Bild neu."""
    rec = RunRecorder(_runs(tmp_path), None, backend="mujoco")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()

    bild = rec.dir / "ansicht.jpg"
    bild.write_bytes(b"\xff\xd8erstes")
    gemeldet = [d for art, d in scanner.tick() if art == "ansicht"]
    assert gemeldet == [str(bild)]

    assert [d for art, d in scanner.tick() if art == "ansicht"] == [], "unveraendert, nicht melden"

    bild.write_bytes(b"\xff\xd8zweites, laenger")
    assert [d for art, d in scanner.tick() if art == "ansicht"] == [str(bild)]
