import os
import shutil
import time

import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.gui.watcher import RunScanner  # noqa: E402
from spotlab.record.run import RunRecorder  # noqa: E402


def _arten(ereignisse):
    return [art for art, _ in ereignisse]


def test_neuer_lauf_wird_gemeldet(tmp_path):
    scanner = RunScanner(tmp_path)
    assert scanner.tick() == []

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    assert "lauf_begonnen" in _arten(scanner.tick())


def test_zustand_und_ereignisse_kommen_durch(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
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
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    rec.finish("ok")
    alt = time.time() - 60
    os.utime(rec.dir / "zustand.jsonl", (alt, alt))

    assert RunScanner(tmp_path).tick() == []


def test_ende_wird_gemeldet(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()

    alt = time.time() - 60
    os.utime(rec.dir / "zustand.jsonl", (alt, alt))
    assert "lauf_beendet" in _arten(scanner.tick())


def test_bilder_werden_gemeldet(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()

    rec.image("frontleft", b"\x89PNG", {"source": "frontleft_fisheye_image"})
    bilder = [p for art, p in scanner.tick() if art == "bild"]
    assert bilder and bilder[0].endswith(".png")


def test_fehlender_ordner_wirft_nicht(tmp_path):
    assert RunScanner(tmp_path / "gibtsnicht").tick() == []


def test_verschwundener_lauf_wirft_nicht(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
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

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    watcher._takt()  # Takt von Hand auslösen, ohne Ereignisschleife

    assert [a for a, _ in empfangen] == ["begonnen", "zustand"]
