# spotlab GUI — Implementierungsplan, Teil 2 (Qt-Oberfläche)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Fortsetzung von `2026-08-07-spotlab-gui.md`. **Global Constraints** von dort gelten unverändert weiter.

**Umfang:** Tasks 6–17 — Paletten, Beobachter, Arbeiter, Kopfleiste, die vier Ansichten, Fenster, CLI, Kettentest, Doku.

## Testumgebung für alle Qt-Tasks

Alle Qt-Tests laufen ohne Bildschirm. In `tests/conftest.py` **einmalig** ergänzen (Task 6, Step 3):

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

Diese Zeile muss **vor** dem ersten `PySide6`-Import stehen, also im `conftest.py` ganz oben — deshalb wird sie in Task 6 gesetzt und nicht später.

Eine gemeinsame `QApplication` pro Testlauf, ebenfalls in `conftest.py`:

```python
import pytest


@pytest.fixture(scope="session")
def qapp():
    """Eine QApplication pro Testlauf — mehrere gleichzeitig sind nicht erlaubt."""
    pyside = pytest.importorskip("PySide6.QtWidgets")
    app = pyside.QApplication.instance() or pyside.QApplication([])
    yield app
```

`importorskip` sorgt dafür, dass die Suite **ohne das Extra `[gui]` sauber durchläuft** und die Qt-Tests übersprungen werden — genau wie `matura-spot` sauber ohne Menagerie-Asset skippt.

---

## Task 6: Paletten

**Files:**
- Create: `src/spotlab/gui/__init__.py`, `src/spotlab/gui/theme.py`, `tests/test_gui_theme.py`
- Modify: `tests/conftest.py`, `pyproject.toml`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `Palette` frozen dataclass: `hintergrund, flaeche, rand, text, gedaempft, akzent, ok, warnung, gefahr` (alle `str`, Hex)
  - `DUNKEL: Palette`, `HELL: Palette`
  - `palette_fuer(dunkel: bool) -> Palette`
  - `stylesheet(p: Palette) -> str`

**`theme.py` ist vollständig Qt-frei** — das Auslesen der Windows-Einstellung braucht Qt und liegt in `app.py` (Task 12). Nur so bleibt die Palettenwahl ohne Fenster prüfbar.

- [ ] **Step 1: Fehlschlagenden Test schreiben** — `tests/test_gui_theme.py`

```python
import re

from spotlab.gui.theme import DUNKEL, HELL, Palette, palette_fuer, stylesheet

FELDER = ("hintergrund", "flaeche", "rand", "text", "gedaempft",
          "akzent", "ok", "warnung", "gefahr")


def test_beide_paletten_sind_vollstaendig():
    for palette in (DUNKEL, HELL):
        for feld in FELDER:
            wert = getattr(palette, feld)
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", wert), f"{feld}={wert!r}"


def test_auswahl_folgt_dem_schalter():
    assert palette_fuer(True) is DUNKEL
    assert palette_fuer(False) is HELL


def test_paletten_unterscheiden_sich():
    assert DUNKEL.hintergrund != HELL.hintergrund
    assert DUNKEL.text != HELL.text


def test_stylesheet_enthaelt_nur_farben_der_palette():
    """Keine Farbliterale im Widget-Code — sonst bricht der zweite Modus."""
    text = stylesheet(DUNKEL)
    erlaubt = {getattr(DUNKEL, f).lower() for f in FELDER}
    gefunden = {t.lower() for t in re.findall(r"#[0-9a-fA-F]{6}", text)}
    assert gefunden <= erlaubt, f"fremde Farben: {gefunden - erlaubt}"


def test_stylesheet_ist_fuer_beide_paletten_baubar():
    assert len(stylesheet(HELL)) > 100
    assert stylesheet(HELL) != stylesheet(DUNKEL)


def test_theme_ist_qt_frei():
    """Die Palettenwahl muss ohne Fenster prüfbar bleiben."""
    import pathlib

    import spotlab.gui.theme as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in quelle
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_theme.py -q`, erwartet `ModuleNotFoundError`

- [ ] **Step 3: `tests/conftest.py` ergänzen** — die Datei komplett ersetzen durch:

```python
import os
import sys
from pathlib import Path

# Muss vor dem ersten PySide6-Import stehen: Qt-Tests laufen ohne Bildschirm.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def qapp():
    """Eine QApplication pro Testlauf — mehrere gleichzeitig sind nicht erlaubt."""
    pyside = pytest.importorskip("PySide6.QtWidgets")
    app = pyside.QApplication.instance() or pyside.QApplication([])
    yield app
```

- [ ] **Step 4: `src/spotlab/gui/__init__.py` anlegen**

```python
"""Die Oberfläche — Beobachter und Starter, hält nie ein Lease."""
```

- [ ] **Step 5: `src/spotlab/gui/theme.py` implementieren**

```python
"""Zwei Paletten, hell und dunkel.

Bewusst Qt-frei: das Auslesen der Windows-Einstellung braucht Qt und liegt in
app.py. Nur so bleibt die Palettenwahl ohne Fenster prüfbar — und nur so
lassen sich Farbliterale im Widget-Code verhindern, denn die einzige Quelle
für Farben ist dieses Modul.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    hintergrund: str
    flaeche: str
    rand: str
    text: str
    gedaempft: str
    akzent: str
    ok: str
    warnung: str
    gefahr: str


DUNKEL = Palette(
    hintergrund="#1e1f22",
    flaeche="#26282c",
    rand="#34373d",
    text="#d7dae0",
    gedaempft="#868d97",
    akzent="#579dff",
    ok="#3fb950",
    warnung="#d29922",
    gefahr="#e5484d",
)

HELL = Palette(
    hintergrund="#f4f5f7",
    flaeche="#ffffff",
    rand="#dfe1e6",
    text="#1f2328",
    gedaempft="#6b7280",
    akzent="#0b5cd5",
    ok="#1a7f37",
    warnung="#9a6700",
    gefahr="#d1372f",
)


def palette_fuer(dunkel):
    return DUNKEL if dunkel else HELL


def stylesheet(p):
    """Qt-Stylesheet aus der Palette. Einzige Stelle mit Farbwerten im Programm."""
    return f"""
QWidget {{
    background: {p.hintergrund};
    color: {p.text};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}
QFrame#Flaeche, QListWidget, QTableWidget, QPlainTextEdit, QLineEdit, QDoubleSpinBox {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 8px;
}}
QLineEdit, QDoubleSpinBox {{ padding: 6px 8px; }}
QLabel#Gedaempft {{ color: {p.gedaempft}; }}
QLabel#Titel {{ font-size: 16px; font-weight: 600; }}
QLabel#Kachelwert {{ font-family: Consolas, monospace; font-size: 17px; font-weight: 600; }}
QLabel#Kachelname {{ color: {p.gedaempft}; font-size: 10px; }}
QLabel#Ok {{ color: {p.ok}; }}
QLabel#Warnung {{ color: {p.warnung}; }}
QLabel#Gefahr {{ color: {p.gefahr}; }}
QPushButton {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 7px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {p.akzent}; }}
QPushButton:disabled {{ color: {p.gedaempft}; }}
QPushButton#Notaus {{
    background: {p.gefahr};
    color: {p.flaeche};
    border: none;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 10px 20px;
}}
QPushButton#Navi {{
    background: transparent;
    border: none;
    text-align: left;
    padding: 8px 10px;
}}
QPushButton#Navi:checked {{ background: {p.rand}; font-weight: 600; }}
QHeaderView::section {{
    background: {p.flaeche};
    color: {p.gedaempft};
    border: none;
    border-bottom: 1px solid {p.rand};
    padding: 6px;
}}
QTableWidget {{ gridline-color: {p.rand}; }}
QPlainTextEdit {{ font-family: Consolas, monospace; font-size: 12px; }}
"""
```

- [ ] **Step 6: `pyproject.toml` um das Extra ergänzen** — den Block `[project.optional-dependencies]` ersetzen durch:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
gui = ["PySide6>=6.6"]
```

- [ ] **Step 7: Tests laufen lassen** — `pytest tests/test_gui_theme.py -q`, erwartet 6 PASS

- [ ] **Step 8: Commit**

```bash
git add src/spotlab/gui pyproject.toml tests/
git commit -m "feat(gui): helle und dunkle Palette, Qt-frei und geprueft"
```

---

## Task 7: Lauf-Beobachter

**Files:**
- Create: `src/spotlab/gui/watcher.py`, `tests/test_gui_watcher.py`

**Interfaces:**
- Consumes: `JsonlTail`, `spotlab.record.read.read_run`, `spotlab.workshop.control.ist_aktiv`
- Produces:
  - `RunScanner(runs_dir)` — **Qt-frei**, mit `.tick() -> list[tuple[str, object]]`
  - `RunWatcher(runs_dir, parent=None)` — `QObject` mit Signalen `lauf_begonnen(str)`, `zustand(dict)`, `ereignis(dict)`, `bild(str)`, `lauf_beendet(str)`, `fehler(str)`; `.start()`, `.stop()`

**Aufteilung mit Absicht:** die gesamte Logik steckt in `RunScanner`, der nur Listen zurückgibt und ohne Qt getestet wird. `RunWatcher` ist eine Hülle, die `tick()` per `QTimer` aufruft und die Ergebnisse als Signale aussendet. Damit ist das Schwierige prüfbar und das Qt-Teil trivial.

Ereignisarten aus `tick()`: `("lauf_begonnen", str(pfad))`, `("zustand", dict)`, `("ereignis", dict)`, `("bild", str(pfad))`, `("lauf_beendet", str(pfad))`.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_watcher.py`

```python
import os
import time

from spotlab.gui.watcher import RunScanner
from spotlab.record.run import RunRecorder


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
    import shutil

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    scanner = RunScanner(tmp_path)
    scanner.tick()
    shutil.rmtree(rec.dir)
    scanner.tick()          # darf nicht werfen


def test_watcher_sendet_qt_signale(tmp_path, qapp):
    from spotlab.gui.watcher import RunWatcher

    empfangen = []
    watcher = RunWatcher(tmp_path)
    watcher.lauf_begonnen.connect(lambda p: empfangen.append(("begonnen", p)))
    watcher.zustand.connect(lambda d: empfangen.append(("zustand", d)))

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    watcher._takt()          # Takt von Hand auslösen, ohne Ereignisschleife

    assert [a for a, _ in empfangen] == ["begonnen", "zustand"]
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_watcher.py -q`

- [ ] **Step 3: `gui/watcher.py` implementieren**

```python
"""Den runs/-Ordner mitlesen und als Qt-Signale weitergeben.

Abgefragt statt QFileSystemWatcher: Anfügungen an eine offene Datei lösen
unter Windows keine verlässliche Verzeichnisbenachrichtigung aus, und 10 Hz
Anfügungen würden einen Ereignis-Beobachter überschwemmen. Ein 250-ms-Takt,
der nur die neuen Bytes liest, kostet praktisch nichts.

Die Logik steckt vollständig in RunScanner (Qt-frei, geprüft); RunWatcher ist
nur die Hülle, die den Takt gibt und Signale aussendet.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from spotlab.record.tail import JsonlTail
from spotlab.workshop.control import ist_aktiv

TAKT_MS = 250


class _Lauf:
    def __init__(self, verzeichnis):
        self.dir = Path(verzeichnis)
        self.zustand = JsonlTail(self.dir / "zustand.jsonl")
        self.ereignisse = JsonlTail(self.dir / "ereignisse.jsonl")
        self.gesehene_bilder = set()


class RunScanner:
    """Qt-freier Kern: findet Läufe und liefert die Neuigkeiten seit dem letzten Aufruf."""

    def __init__(self, runs_dir):
        self._wurzel = Path(runs_dir)
        self._offen = {}

    def tick(self):
        ereignisse = []
        ereignisse.extend(self._neue_laeufe())
        for name in list(self._offen):
            ereignisse.extend(self._neuigkeiten(name))
        return ereignisse

    # ------------------------------------------------------------------ intern

    def _neue_laeufe(self):
        gefunden = []
        try:
            kandidaten = [p for p in self._wurzel.iterdir() if p.is_dir()]
        except OSError:
            return gefunden
        for verzeichnis in sorted(kandidaten, key=lambda p: p.name):
            if verzeichnis.name in self._offen or not ist_aktiv(verzeichnis):
                continue
            self._offen[verzeichnis.name] = _Lauf(verzeichnis)
            gefunden.append(("lauf_begonnen", str(verzeichnis)))
        return gefunden

    def _neuigkeiten(self, name):
        lauf = self._offen[name]
        ereignisse = []
        for satz in lauf.zustand.neue_saetze():
            ereignisse.append(("zustand", satz))
        for satz in lauf.ereignisse.neue_saetze():
            ereignisse.append(("ereignis", satz))
        ereignisse.extend(self._neue_bilder(lauf))
        if not ist_aktiv(lauf.dir):
            del self._offen[name]
            ereignisse.append(("lauf_beendet", str(lauf.dir)))
        return ereignisse

    @staticmethod
    def _neue_bilder(lauf):
        gefunden = []
        try:
            dateien = sorted((lauf.dir / "bilder").glob("*.png"))
        except OSError:
            return gefunden
        for datei in dateien:
            if datei.name not in lauf.gesehene_bilder:
                lauf.gesehene_bilder.add(datei.name)
                gefunden.append(("bild", str(datei)))
        return gefunden


class RunWatcher(QObject):
    lauf_begonnen = Signal(str)
    zustand = Signal(dict)
    ereignis = Signal(dict)
    bild = Signal(str)
    lauf_beendet = Signal(str)
    fehler = Signal(str)

    def __init__(self, runs_dir, parent=None):
        super().__init__(parent)
        self._scanner = RunScanner(runs_dir)
        self._timer = QTimer(self)
        self._timer.setInterval(TAKT_MS)
        self._timer.timeout.connect(self._takt)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _takt(self):
        try:
            ereignisse = self._scanner.tick()
        except Exception as fehler:      # eine GUI, die still nichts mehr tut, ist schlimmer
            self.fehler.emit(f"Beobachter: {type(fehler).__name__}: {fehler}")
            return
        signale = {
            "lauf_begonnen": self.lauf_begonnen,
            "zustand": self.zustand,
            "ereignis": self.ereignis,
            "bild": self.bild,
            "lauf_beendet": self.lauf_beendet,
        }
        for art, nutzlast in ereignisse:
            signale[art].emit(nutzlast)
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_watcher.py -q`, erwartet 8 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/watcher.py tests/test_gui_watcher.py
git commit -m "feat(gui): Lauf-Beobachter mit Qt-freiem Kern"
```

---

## Task 8: Arbeiter für Prüfung und Skriptausgabe

**Files:**
- Create: `src/spotlab/gui/workers.py`, `tests/test_gui_workers.py`

**Interfaces:**
- Consumes: `spotlab.workshop.doctor.diagnose`
- Produces:
  - `DoctorWorker(parent=None)` — `QThread`, Signale `fertig(list)`, `fehler(str)`; `.run()` ruft `diagnose()`
  - `OutputReader(prozess, parent=None)` — `QThread`, Signale `zeile(str)`, `ende(int)`

**Warum Threads:** `diagnose()` braucht mehrere Sekunden übers Netz. Im Qt-Hauptthread würde das Fenster genau dann einfrieren, wenn man es am dringendsten braucht.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_workers.py`

```python
import io

from spotlab.gui.workers import DoctorWorker, OutputReader
from spotlab.workshop.doctor import Check


class FakeProzess:
    def __init__(self, zeilen, returncode=0):
        self.stdout = io.StringIO("".join(z + "\n" for z in zeilen))
        self.returncode = returncode

    def wait(self):
        return self.returncode


def test_doctor_worker_meldet_ergebnisse(qapp, monkeypatch):
    pruefungen = [Check("Netz", True, "antwortet")]
    monkeypatch.setattr("spotlab.gui.workers.diagnose", lambda: pruefungen)

    empfangen = []
    worker = DoctorWorker()
    worker.fertig.connect(empfangen.append)
    worker.run()          # direkt aufrufen, ohne Thread zu starten

    assert empfangen == [pruefungen]


def test_doctor_worker_faengt_ausnahmen(qapp, monkeypatch):
    def kaputt():
        raise RuntimeError("Netz weg")

    monkeypatch.setattr("spotlab.gui.workers.diagnose", kaputt)

    fehler = []
    worker = DoctorWorker()
    worker.fehler.connect(fehler.append)
    worker.run()

    assert fehler and "Netz weg" in fehler[0]


def test_ausgabe_leser_gibt_zeilen_weiter(qapp):
    empfangen = []
    enden = []
    leser = OutputReader(FakeProzess(["Akku: 87 %", "Fertig."], returncode=0))
    leser.zeile.connect(empfangen.append)
    leser.ende.connect(enden.append)
    leser.run()

    assert empfangen == ["Akku: 87 %", "Fertig."]
    assert enden == [0]


def test_ausgabe_leser_ohne_pipe(qapp):
    class OhnePipe:
        stdout = None

        def wait(self):
            return 1

    enden = []
    leser = OutputReader(OhnePipe())
    leser.ende.connect(enden.append)
    leser.run()          # darf nicht werfen

    assert enden == [1]
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_workers.py -q`

- [ ] **Step 3: `gui/workers.py` implementieren**

```python
"""Hintergrund-Arbeiter.

Im Qt-Hauptthread passiert nur Anzeige. diagnose() braucht mehrere Sekunden
übers Netz, und die Pipe eines Kindprozesses muss laufend geleert werden —
sonst füllt sich der Puffer und der Kindprozess bleibt stehen.

Beide Arbeiter fangen Ausnahmen ab und melden sie als Signal: eine GUI, die
still nichts mehr tut, ist schlimmer als eine, die abstürzt.
"""

from PySide6.QtCore import QThread, Signal

from spotlab.workshop.doctor import diagnose


class DoctorWorker(QThread):
    fertig = Signal(list)
    fehler = Signal(str)

    def run(self):
        try:
            self.fertig.emit(list(diagnose()))
        except Exception as fehler:
            self.fehler.emit(f"Prüfung fehlgeschlagen: {type(fehler).__name__}: {fehler}")


class OutputReader(QThread):
    zeile = Signal(str)
    ende = Signal(int)

    def __init__(self, prozess, parent=None):
        super().__init__(parent)
        self._prozess = prozess

    def run(self):
        strom = getattr(self._prozess, "stdout", None)
        if strom is not None:
            try:
                for zeile in strom:
                    self.zeile.emit(zeile.rstrip("\n"))
            except Exception as fehler:
                self.zeile.emit(f"[Ausgabe abgebrochen: {fehler}]")
        try:
            code = int(self._prozess.wait())
        except Exception:
            code = -1
        self.ende.emit(code)
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_workers.py -q`, erwartet 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/workers.py tests/test_gui_workers.py
git commit -m "feat(gui): Arbeiter fuer Pruefung und Skriptausgabe"
```

---

## Task 9: Kopfleiste mit NOT-AUS

**Files:**
- Create: `src/spotlab/gui/header.py`, `tests/test_gui_header.py`

**Interfaces:**
- Consumes: `spotlab.gui.theme`
- Produces: `Header(QWidget)` mit Signal `notaus()`, Methoden `zeige_config(cfg)`, `zeige_pruefung(list[Check])`, `zeige_zustand(dict)`, `zeige_getrennt()`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_header.py`

```python
from spotlab.config import Config, Limits
from spotlab.gui.header import Header
from spotlab.workshop.doctor import Check


def test_notaus_knopf_sendet_signal(qapp):
    kopf = Header()
    gedrueckt = []
    kopf.notaus.connect(lambda: gedrueckt.append(True))
    kopf.notaus_knopf.click()
    assert gedrueckt == [True]


def test_notaus_ohne_rueckfrage(qapp):
    """Wer den Not-Aus drückt, hat keine Zeit für einen Dialog."""
    import inspect

    import spotlab.gui.header as modul

    quelle = inspect.getsource(modul)
    assert "QMessageBox" not in quelle


def test_erklaerung_steht_dauerhaft_da(qapp):
    text = Header().hinweis.text().lower()
    assert "motoren" in text
    assert "physische" in text or "tablet" in text


def test_konfiguration_wird_angezeigt(qapp):
    kopf = Header()
    kopf.zeige_config(Config(ip="192.168.80.3", username="u",
                             nickname="Spot der Kanti", limits=Limits()))
    assert "Spot der Kanti" in kopf.status.text()
    assert "192.168.80.3" in kopf.status.text()


def test_lauf_zustand_zeigt_akku_live(qapp):
    kopf = Header()
    kopf.zeige_zustand({"daten": {"battery": 61.5, "velocity": [0.3, 0.0, 0.0]}})
    assert "61" in kopf.akku.text()


def test_pruefung_faerbt_die_ampel(qapp):
    kopf = Header()
    kopf.zeige_pruefung([Check("Netz", True, "antwortet"),
                         Check("Lease", False, "gehalten von anna", "absprechen")])
    assert kopf.ampel.objectName() in ("Warnung", "Gefahr")

    kopf.zeige_pruefung([Check("Netz", True, "antwortet")])
    assert kopf.ampel.objectName() == "Ok"


def test_getrennt_zustand(qapp):
    kopf = Header()
    kopf.zeige_getrennt()
    assert kopf.ampel.objectName() == "Gedaempft"
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_header.py -q`

- [ ] **Step 3: `gui/header.py` implementieren**

```python
"""Kopfleiste: Zustand links, NOT-AUS rechts.

Der Knopf ist in jeder Ansicht sichtbar und fragt NICHT nach. Wer ihn drückt,
hat keine Zeit für einen Dialog. Was er tut, steht dauerhaft daneben — samt
dem Hinweis, dass der physische Not-Aus das primäre Sicherheitsmittel bleibt.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

ERKLAERUNG = (
    "Beendet das laufende Programm sofort — der Spot schaltet die Motoren ab und "
    "sackt zusammen. Wirkt nur auf spotlab. Das primäre Sicherheitsmittel bleibt "
    "der physische Not-Aus am Tablet."
)


class Header(QWidget):
    notaus = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ampel = QLabel("●")
        self.ampel.setObjectName("Gedaempft")
        self.status = QLabel("Nicht eingerichtet")
        self.akku = QLabel("Akku —")
        self.lease = QLabel("Lease —")

        self.notaus_knopf = QPushButton("NOT-AUS")
        self.notaus_knopf.setObjectName("Notaus")
        self.notaus_knopf.setCursor(Qt.PointingHandCursor)
        self.notaus_knopf.clicked.connect(self.notaus.emit)

        self.hinweis = QLabel(ERKLAERUNG)
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        zeile = QHBoxLayout()
        for widget in (self.ampel, self.status, self.akku, self.lease):
            zeile.addWidget(widget)
        zeile.addStretch(1)
        zeile.addWidget(self.notaus_knopf)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(14, 10, 14, 8)
        aussen.addLayout(zeile)
        aussen.addWidget(self.hinweis)

    # ------------------------------------------------------------- Anzeige

    def _setze_ampel(self, name):
        self.ampel.setObjectName(name)
        self.ampel.style().unpolish(self.ampel)
        self.ampel.style().polish(self.ampel)

    def zeige_config(self, cfg):
        if cfg is None:
            self.status.setText("Nicht eingerichtet — Ansicht „Spot"")
            return
        self.status.setText(f"{cfg.nickname} · {cfg.ip}")

    def zeige_getrennt(self):
        self._setze_ampel("Gedaempft")
        self.akku.setText("Akku —")
        self.lease.setText("Lease —")

    def zeige_pruefung(self, pruefungen):
        if not pruefungen:
            self.zeige_getrennt()
            return
        schlimm = [p for p in pruefungen if not p.ok]
        if not schlimm:
            self._setze_ampel("Ok")
        elif any(p.name in ("Netz", "Anmeldung", "Not-Aus") for p in schlimm):
            self._setze_ampel("Gefahr")
        else:
            self._setze_ampel("Warnung")

        for pruefung in pruefungen:
            if pruefung.name == "Akku":
                self.akku.setText(f"Akku {pruefung.detail}")
            if pruefung.name == "Lease":
                self.lease.setText(f"Lease {pruefung.detail}")

    def zeige_zustand(self, satz):
        """Live-Werte aus zustand.jsonl — ohne eigene Roboterverbindung."""
        daten = satz.get("daten", {})
        akku = daten.get("battery")
        if akku is not None:
            self.akku.setText(f"Akku {akku:.0f} %")
        self._setze_ampel("Ok")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_header.py -q`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/header.py tests/test_gui_header.py
git commit -m "feat(gui): Kopfleiste mit NOT-AUS ohne Rueckfrage"
```

---

## Task 10: Seitenleiste und Ansicht „Projekte"

**Files:**
- Create: `src/spotlab/gui/sidebar.py`, `src/spotlab/gui/views/__init__.py`, `src/spotlab/gui/views/projects.py`, `tests/test_gui_projects.py`

**Interfaces:**
- Consumes: `create_project`, `open_in_editor`, `start_script`
- Produces:
  - `Sidebar(QWidget)` mit Signal `gewaehlt(str)` und Knöpfen für `"projekte" | "live" | "laeufe" | "spot"`
  - `ProjectsView(QWidget)` mit Signal `lauf_gestartet(object, str)` (Prozess, Skriptpfad), Methoden `setze_arbeitsordner(pfad)`, `aktualisiere()`
  - `projekte_in(ordner) -> list[Path]` — Qt-frei: Unterordner mit `runs/`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_projects.py`

```python
from spotlab.gui.views.projects import ProjectsView, projekte_in
from spotlab.workshop.project import create_project


def test_projekte_werden_erkannt(tmp_path):
    create_project("a", tmp_path)
    create_project("b", tmp_path)
    (tmp_path / "kein-projekt").mkdir()
    assert [p.name for p in projekte_in(tmp_path)] == ["a", "b"]


def test_leerer_ordner(tmp_path):
    assert projekte_in(tmp_path) == []


def test_fehlender_ordner(tmp_path):
    assert projekte_in(tmp_path / "gibtsnicht") == []


def test_ansicht_listet_projekte_und_skripte(qapp, tmp_path):
    create_project("demo", tmp_path)
    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)

    assert ansicht.projektliste.count() == 1
    ansicht.projektliste.setCurrentRow(0)
    namen = [ansicht.skriptliste.item(i).text() for i in range(ansicht.skriptliste.count())]
    assert "hallo_spot.py" in namen


def test_starten_reicht_trockenlauf_durch(qapp, tmp_path, monkeypatch):
    create_project("demo", tmp_path)
    gerufen = {}

    def fake_start(pfad, dryrun=False, **kw):
        gerufen["pfad"], gerufen["dryrun"] = pfad, dryrun
        return object()

    monkeypatch.setattr("spotlab.gui.views.projects.start_script", fake_start)

    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.projektliste.setCurrentRow(0)
    ansicht.skriptliste.setCurrentRow(0)
    ansicht.trockenlauf.setChecked(True)
    ansicht.starten_knopf.click()

    assert gerufen["dryrun"] is True
    assert str(gerufen["pfad"]).endswith("hallo_spot.py")


def test_starten_ohne_auswahl_tut_nichts(qapp, tmp_path, monkeypatch):
    gerufen = []
    monkeypatch.setattr("spotlab.gui.views.projects.start_script",
                        lambda *a, **k: gerufen.append(a))
    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.starten_knopf.click()
    assert gerufen == []


def test_sidebar_meldet_die_wahl(qapp):
    from spotlab.gui.sidebar import Sidebar

    gewaehlt = []
    leiste = Sidebar()
    leiste.gewaehlt.connect(gewaehlt.append)
    leiste.knoepfe["laeufe"].click()
    assert gewaehlt == ["laeufe"]
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_projects.py -q`

- [ ] **Step 3: `gui/sidebar.py` implementieren**

```python
"""Navigation links — dieselbe Anordnung wie VS Code, das die Schüler daneben offen haben."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QPushButton, QVBoxLayout, QWidget

EINTRAEGE = (
    ("projekte", "Projekte"),
    ("live", "Live-Lauf"),
    ("laeufe", "Läufe"),
    ("spot", "Spot"),
)


class Sidebar(QWidget):
    gewaehlt = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(150)
        self.knoepfe = {}
        gruppe = QButtonGroup(self)
        gruppe.setExclusive(True)

        anordnung = QVBoxLayout(self)
        anordnung.setContentsMargins(8, 12, 8, 12)
        anordnung.setSpacing(2)
        for schluessel, beschriftung in EINTRAEGE:
            knopf = QPushButton(beschriftung)
            knopf.setObjectName("Navi")
            knopf.setCheckable(True)
            knopf.clicked.connect(lambda _=False, s=schluessel: self.gewaehlt.emit(s))
            gruppe.addButton(knopf)
            anordnung.addWidget(knopf)
            self.knoepfe[schluessel] = knopf
        anordnung.addStretch(1)
        self.knoepfe["projekte"].setChecked(True)

    def waehle(self, schluessel):
        self.knoepfe[schluessel].setChecked(True)
```

- [ ] **Step 4: `gui/views/__init__.py` anlegen**

```python
"""Die vier Ansichten."""
```

- [ ] **Step 5: `gui/views/projects.py` implementieren**

```python
"""Projekte anlegen, in VS Code öffnen, Skripte starten.

Der Trockenlauf ist ein sichtbares Häkchen statt einer Kommandozeilenoption,
die niemand findet — Üben ohne Roboter soll man sehen können.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.errors import SpotlabError
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import start_script
from spotlab.workshop.project import create_project


def projekte_in(ordner):
    """Unterordner, die ein runs/-Verzeichnis haben — daran erkennt man ein Projekt."""
    wurzel = Path(ordner)
    try:
        kandidaten = [p for p in wurzel.iterdir() if p.is_dir()]
    except OSError:
        return []
    return sorted((p for p in kandidaten if (p / "runs").is_dir()), key=lambda p: p.name)


class ProjectsView(QWidget):
    lauf_gestartet = Signal(object, str)
    arbeitsordner_geaendert = Signal(str)

    def __init__(self, editor_command="code", parent=None):
        super().__init__(parent)
        self._ordner = None
        self._editor = editor_command

        self.pfadanzeige = QLabel("Kein Arbeitsordner gewählt")
        self.pfadanzeige.setObjectName("Gedaempft")
        self.waehlen_knopf = QPushButton("Arbeitsordner wählen…")
        self.waehlen_knopf.clicked.connect(self._waehle_ordner)

        self.projektliste = QListWidget()
        self.projektliste.currentRowChanged.connect(lambda _: self._fuelle_skripte())
        self.neu_knopf = QPushButton("Neues Projekt")
        self.neu_knopf.clicked.connect(self._neues_projekt)
        self.oeffnen_knopf = QPushButton("In VS Code öffnen")
        self.oeffnen_knopf.clicked.connect(self._oeffne_projekt)

        self.skriptliste = QListWidget()
        self.trockenlauf = QCheckBox("Trockenlauf (ohne Roboter)")
        self.starten_knopf = QPushButton("Starten")
        self.starten_knopf.clicked.connect(self._starte)

        kopf = QHBoxLayout()
        kopf.addWidget(self.pfadanzeige, 1)
        kopf.addWidget(self.waehlen_knopf)

        projektknoepfe = QHBoxLayout()
        projektknoepfe.addWidget(self.neu_knopf)
        projektknoepfe.addWidget(self.oeffnen_knopf)
        projektknoepfe.addStretch(1)

        startzeile = QHBoxLayout()
        startzeile.addWidget(self.trockenlauf)
        startzeile.addStretch(1)
        startzeile.addWidget(self.starten_knopf)

        anordnung = QVBoxLayout(self)
        anordnung.addLayout(kopf)
        anordnung.addWidget(QLabel("Projekte"))
        anordnung.addWidget(self.projektliste, 2)
        anordnung.addLayout(projektknoepfe)
        anordnung.addWidget(QLabel("Programme"))
        anordnung.addWidget(self.skriptliste, 2)
        anordnung.addLayout(startzeile)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.pfadanzeige.setText(str(self._ordner) if self._ordner else "Kein Arbeitsordner gewählt")
        self.aktualisiere()

    def aktualisiere(self):
        self.projektliste.clear()
        if self._ordner is None:
            self.skriptliste.clear()
            return
        for projekt in projekte_in(self._ordner):
            self.projektliste.addItem(projekt.name)
        self._fuelle_skripte()

    def _gewaehltes_projekt(self):
        eintrag = self.projektliste.currentItem()
        if eintrag is None or self._ordner is None:
            return None
        return self._ordner / eintrag.text()

    def _fuelle_skripte(self):
        self.skriptliste.clear()
        projekt = self._gewaehltes_projekt()
        if projekt is None:
            return
        for datei in sorted(projekt.glob("*.py")):
            self.skriptliste.addItem(datei.name)

    # ------------------------------------------------------------- Aktionen

    def _waehle_ordner(self):
        gewaehlt = QFileDialog.getExistingDirectory(self, "Arbeitsordner wählen")
        if gewaehlt:
            self.setze_arbeitsordner(gewaehlt)
            self.arbeitsordner_geaendert.emit(gewaehlt)

    def _neues_projekt(self):
        if self._ordner is None:
            QMessageBox.information(self, "spotlab", "Wähle zuerst einen Arbeitsordner.")
            return
        name, ok = QInputDialog.getText(self, "Neues Projekt", "Name:")
        if not ok or not name.strip():
            return
        try:
            create_project(name, self._ordner)
        except (SpotlabError, FileExistsError) as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))
            return
        self.aktualisiere()

    def _oeffne_projekt(self):
        projekt = self._gewaehltes_projekt()
        if projekt is None:
            return
        try:
            open_in_editor(projekt, command=self._editor)
        except SpotlabError as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))

    def _starte(self):
        projekt = self._gewaehltes_projekt()
        eintrag = self.skriptliste.currentItem()
        if projekt is None or eintrag is None:
            return
        skript = projekt / eintrag.text()
        try:
            prozess = start_script(skript, dryrun=self.trockenlauf.isChecked())
        except SpotlabError as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))
            return
        self.lauf_gestartet.emit(prozess, str(skript))
```

- [ ] **Step 6: Tests laufen lassen** — `pytest tests/test_gui_projects.py -q`, erwartet 7 PASS

- [ ] **Step 7: Commit**

```bash
git add src/spotlab/gui/sidebar.py src/spotlab/gui/views tests/test_gui_projects.py
git commit -m "feat(gui): Seitenleiste und Projektansicht"
```

---

## Task 11: Ansicht „Live-Lauf"

**Files:**
- Create: `src/spotlab/gui/views/live.py`, `tests/test_gui_live.py`

**Interfaces:**
- Consumes: `stoppe_freundlich`, `beende_hart`, `ist_aktiv`
- Produces: `LiveView(QWidget)` mit `setze_lauf(pfad, skript)`, `zeige_zustand(satz)`, `zeige_ereignis(satz)`, `zeige_bild(pfad)`, `zeige_ausgabe(zeile)`, `lauf_beendet()`, `notaus()`; Signal `meldung(str)`

**Die Eskalation:** `Stopp` schreibt die Markierung. Ist der Lauf nach **3 Sekunden** noch aktiv, erscheint „reagiert nicht" samt Knopf zum harten Beenden. Im Test wird der Zeitgeber von Hand ausgelöst statt gewartet.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_live.py`

```python
from spotlab.gui.views.live import LiveView
from spotlab.record.run import STOPP_DATEI, RunRecorder


def _lauf(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    return rec


def test_leerer_zustand_sagt_was_zu_tun_ist(qapp):
    text = LiveView().leer.text().lower()
    assert "starten" in text or "programm" in text


def test_zustand_fuellt_die_kacheln(qapp, tmp_path):
    ansicht = LiveView()
    ansicht.setze_lauf(_lauf(tmp_path).dir, "hallo_spot.py")
    ansicht.zeige_zustand({"daten": {"battery": 61.0, "pose": [1.02, 0.0, 0.0],
                                     "velocity": [0.30, 0.0, 0.0],
                                     "feet": [True, True, False, True]}})
    assert "1.02" in ansicht.kachel_pose.text()
    assert "0.30" in ansicht.kachel_tempo.text()
    assert "61" in ansicht.kachel_akku.text()


def test_ereignisse_landen_in_der_liste(qapp, tmp_path):
    ansicht = LiveView()
    ansicht.setze_lauf(_lauf(tmp_path).dir, "x.py")
    ansicht.zeige_ereignis({"t": 0.28, "art": "kommando", "daten": {"name": "stand"}})
    assert ansicht.ereignisliste.count() == 1
    assert "stand" in ansicht.ereignisliste.item(0).text()


def test_ausgabe_wird_angehaengt(qapp, tmp_path):
    ansicht = LiveView()
    ansicht.setze_lauf(_lauf(tmp_path).dir, "x.py")
    ansicht.zeige_ausgabe("Akku: 87 %")
    assert "Akku: 87 %" in ansicht.ausgabe.toPlainText()


def test_stopp_legt_die_markierung_an(qapp, tmp_path):
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.stopp_knopf.click()
    assert (rec.dir / STOPP_DATEI).exists()


def test_eskalation_erscheint_erst_wenn_es_haengt(qapp, tmp_path):
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.stopp_knopf.click()
    assert not ansicht.hart_knopf.isVisible()

    ansicht._pruefe_eskalation()          # Zeitgeber von Hand auslösen
    assert ansicht.hart_knopf.isVisible()


def test_keine_eskalation_wenn_der_lauf_endete(qapp, tmp_path):
    import os
    import time

    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.stopp_knopf.click()

    alt = time.time() - 60
    os.utime(rec.dir / "zustand.jsonl", (alt, alt))
    ansicht._pruefe_eskalation()
    assert not ansicht.hart_knopf.isVisible()


def test_notaus_ruft_hartes_beenden(qapp, tmp_path, monkeypatch):
    gerufen = []
    monkeypatch.setattr("spotlab.gui.views.live.beende_hart",
                        lambda p, **kw: gerufen.append(p) or True)
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.notaus()
    assert gerufen == [rec.dir]


def test_notaus_ohne_lauf_meldet_das(qapp):
    meldungen = []
    ansicht = LiveView()
    ansicht.meldung.connect(meldungen.append)
    ansicht.notaus()
    assert meldungen and "läuft" in meldungen[0].lower()
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_live.py -q`

- [ ] **Step 3: `gui/views/live.py` implementieren**

```python
"""Der laufende Lauf: Ereignisse, Telemetrie, Bild, Ausgabe, Stopp.

Der freundliche Stopp schreibt nur eine Markierung — der Abtaster des Laufs
holt sie ab. Reagiert der Lauf nach ESKALATION_MS nicht, bietet die Ansicht
das harte Beenden an, statt kommentarlos zu erschlagen oder ewig zu warten.
"""

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.workshop.control import beende_hart, ist_aktiv, stoppe_freundlich

ESKALATION_MS = 3000


def _kachel(name):
    rahmen = QFrame()
    rahmen.setObjectName("Flaeche")
    wert = QLabel("—")
    wert.setObjectName("Kachelwert")
    beschriftung = QLabel(name)
    beschriftung.setObjectName("Kachelname")
    anordnung = QVBoxLayout(rahmen)
    anordnung.setContentsMargins(10, 7, 10, 7)
    anordnung.addWidget(beschriftung)
    anordnung.addWidget(wert)
    return rahmen, wert


class LiveView(QWidget):
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lauf = None

        self.leer = QLabel(
            "Gerade läuft kein Programm.\n\n"
            "Starte eines unter „Projekte" — oder drücke in VS Code F5. "
            "Beides wird hier angezeigt."
        )
        self.leer.setObjectName("Gedaempft")

        self.titel = QLabel("—")
        self.titel.setObjectName("Titel")
        self.stopp_knopf = QPushButton("Stopp")
        self.stopp_knopf.clicked.connect(self.stoppe)
        self.hart_knopf = QPushButton("Reagiert nicht — hart beenden")
        self.hart_knopf.clicked.connect(self.notaus)
        self.hart_knopf.hide()

        self.ereignisliste = QListWidget()
        self.ausgabe = QPlainTextEdit()
        self.ausgabe.setReadOnly(True)
        self.bild = QLabel("Kein Bild")
        self.bild.setObjectName("Flaeche")
        self.bild.setFixedWidth(240)
        self.bild.setMinimumHeight(160)

        pose, self.kachel_pose = _kachel("Pose x / y")
        tempo, self.kachel_tempo = _kachel("Tempo")
        fuesse, self.kachel_fuesse = _kachel("Füsse")
        akku, self.kachel_akku = _kachel("Akku")

        kopf = QHBoxLayout()
        kopf.addWidget(self.titel, 1)
        kopf.addWidget(self.hart_knopf)
        kopf.addWidget(self.stopp_knopf)

        mitte = QHBoxLayout()
        mitte.addWidget(self.ereignisliste, 1)
        mitte.addWidget(self.bild)

        kacheln = QHBoxLayout()
        for widget in (pose, tempo, fuesse, akku):
            kacheln.addWidget(widget)

        self.inhalt = QWidget()
        innen = QVBoxLayout(self.inhalt)
        innen.setContentsMargins(0, 0, 0, 0)
        innen.addLayout(kopf)
        innen.addLayout(mitte, 3)
        innen.addLayout(kacheln)
        innen.addWidget(QLabel("Ausgabe"))
        innen.addWidget(self.ausgabe, 2)
        self.inhalt.hide()

        aussen = QVBoxLayout(self)
        aussen.addWidget(self.leer)
        aussen.addWidget(self.inhalt)

        self._eskalation = QTimer(self)
        self._eskalation.setSingleShot(True)
        self._eskalation.setInterval(ESKALATION_MS)
        self._eskalation.timeout.connect(self._pruefe_eskalation)

    # ------------------------------------------------------------- Zustand

    def setze_lauf(self, verzeichnis, skript):
        self._lauf = Path(verzeichnis)
        self.titel.setText(f"{skript} — läuft")
        self.ereignisliste.clear()
        self.ausgabe.clear()
        self.bild.setText("Kein Bild")
        self.hart_knopf.hide()
        self.leer.hide()
        self.inhalt.show()

    def lauf_beendet(self):
        self._eskalation.stop()
        self.hart_knopf.hide()
        if self._lauf is not None:
            self.titel.setText(self.titel.text().replace("läuft", "beendet"))
        self._lauf = None

    # ------------------------------------------------------------- Anzeige

    def zeige_zustand(self, satz):
        daten = satz.get("daten", {})
        pose = daten.get("pose") or [0.0, 0.0, 0.0]
        tempo = daten.get("velocity") or [0.0, 0.0, 0.0]
        fuesse = daten.get("feet") or []
        akku = daten.get("battery")
        self.kachel_pose.setText(f"{pose[0]:.2f} / {pose[1]:.2f}")
        self.kachel_tempo.setText(f"{tempo[0]:.2f} m/s")
        self.kachel_fuesse.setText(" ".join("●" if f else "○" for f in fuesse) or "—")
        if akku is not None:
            self.kachel_akku.setText(f"{akku:.0f} %")

    def zeige_ereignis(self, satz):
        daten = satz.get("daten", {})
        beschreibung = daten.get("name") or daten.get("status") or ""
        self.ereignisliste.addItem(
            f"{satz.get('t', 0.0):7.2f} s  {satz.get('art', ''):<14} {beschreibung}"
        )
        self.ereignisliste.scrollToBottom()

    def zeige_bild(self, pfad):
        pixmap = QPixmap(str(pfad))
        if not pixmap.isNull():
            self.bild.setPixmap(pixmap.scaledToWidth(240))

    def zeige_ausgabe(self, zeile):
        self.ausgabe.appendPlainText(zeile)

    # ------------------------------------------------------------- Stoppen

    def stoppe(self):
        if self._lauf is None:
            self.meldung.emit("Es läuft gerade kein Programm.")
            return
        stoppe_freundlich(self._lauf)
        self.titel.setText(self.titel.text().replace("läuft", "wird gestoppt"))
        self._eskalation.start()

    def _pruefe_eskalation(self):
        if self._lauf is not None and ist_aktiv(self._lauf):
            self.hart_knopf.show()

    def notaus(self):
        if self._lauf is None:
            self.meldung.emit("Es läuft gerade kein Programm.")
            return
        if not beende_hart(self._lauf):
            self.meldung.emit("Der Lauf läuft nicht mehr.")
        self.hart_knopf.hide()
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_live.py -q`, erwartet 9 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/views/live.py tests/test_gui_live.py
git commit -m "feat(gui): Live-Ansicht mit Stopp und Eskalation"
```

---

## Task 12: Ansicht „Läufe" mit Tempo-Kurve

**Files:**
- Create: `src/spotlab/gui/views/runs.py`, `tests/test_gui_runs.py`

**Interfaces:**
- Consumes: `list_runs`, `read_jsonl`
- Produces:
  - `tempo_reihen(run_dir) -> tuple[list[tuple[float,float]], list[tuple[float,float]]]` — **Qt-frei**: (gemessen, kommandiert)
  - `SpeedPlot(QWidget)` — zeichnet beide Reihen mit `QPainter`
  - `RunsView(QWidget)` mit `setze_arbeitsordner(pfad)`, `aktualisiere()`

**Warum keine Diagrammbibliothek:** eine Kurve rechtfertigt keine weitere Abhängigkeit auf zwanzig Schullaptops. Die Datenaufbereitung ist Qt-frei und geprüft; das Zeichnen ist ein Dutzend Zeilen `QPainter`.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_runs.py`

```python
from spotlab.gui.views.runs import RunsView, tempo_reihen
from spotlab.record.run import RunRecorder
from spotlab.workshop.project import create_project


def _lauf_mit_fahrt(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("kommando", name="walk", vx=0.3, vy=0.0, wz=0.0, duration=2.0)
    for tempo in (0.0, 0.15, 0.29):
        rec.sample({"battery": 90.0, "velocity": [tempo, 0.0, 0.0]})
    rec.finish("ok")
    return rec.dir


def test_gemessene_reihe_kommt_aus_dem_zustand(tmp_path):
    gemessen, _ = tempo_reihen(_lauf_mit_fahrt(tmp_path))
    assert [round(v, 2) for _, v in gemessen] == [0.0, 0.15, 0.29]


def test_kommandierte_reihe_kommt_aus_den_ereignissen(tmp_path):
    _, kommandiert = tempo_reihen(_lauf_mit_fahrt(tmp_path))
    assert kommandiert
    assert all(abs(v - 0.3) < 1e-9 for _, v in kommandiert)


def test_lauf_ohne_fahrt_hat_leere_kommandoreihe(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0, "velocity": [0.0, 0.0, 0.0]})
    rec.finish("ok")
    _, kommandiert = tempo_reihen(rec.dir)
    assert kommandiert == []


def test_fehlender_lauf_ergibt_leere_reihen(tmp_path):
    assert tempo_reihen(tmp_path / "gibtsnicht") == ([], [])


def test_ansicht_listet_laeufe(qapp, tmp_path):
    projekt = create_project("demo", tmp_path)
    _lauf_mit_fahrt(projekt / "runs")

    ansicht = RunsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.tabelle.rowCount() == 1
    assert ansicht.tabelle.item(0, 1).text() == "ok"


def test_ansicht_ohne_laeufe(qapp, tmp_path):
    ansicht = RunsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.tabelle.rowCount() == 0


def test_auswahl_fuellt_die_kurve(qapp, tmp_path):
    projekt = create_project("demo", tmp_path)
    _lauf_mit_fahrt(projekt / "runs")

    ansicht = RunsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.tabelle.selectRow(0)
    assert ansicht.kurve.gemessen


def test_kurve_zeichnet_ohne_daten(qapp):
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QWidget

    from spotlab.gui.views.runs import SpeedPlot

    kurve = SpeedPlot()
    kurve.resize(200, 100)
    kurve.render(QPixmap(200, 100))          # darf nicht werfen
    assert isinstance(kurve, QWidget)
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_runs.py -q`

- [ ] **Step 3: `gui/views/runs.py` implementieren**

```python
"""Vergangene Läufe ansehen — mit der einen Auswertung, die zählt.

Kommandiertes gegen gemessenes Tempo ist genau die Grösse, auf die die spätere
Real→Sim-Kalibrierung hinausläuft. Sie macht aus zustand.jsonl etwas
Ansehbares statt nur Archiviertes.

Gezeichnet wird mit QPainter: eine Kurve rechtfertigt keine weitere
Abhängigkeit auf zwanzig Schullaptops.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.theme import DUNKEL
from spotlab.record.read import list_runs, read_jsonl
from spotlab.gui.views.projects import projekte_in

SPALTEN = ("Lauf", "Ergebnis", "Dauer", "Backend", "Skript")


def tempo_reihen(run_dir):
    """(gemessen, kommandiert) als Listen von (Sekunde, m/s)."""
    verzeichnis = Path(run_dir)
    gemessen = []
    for satz in read_jsonl(verzeichnis / "zustand.jsonl"):
        tempo = (satz.get("daten") or {}).get("velocity")
        if tempo:
            gemessen.append((float(satz.get("t", 0.0)), float(tempo[0])))

    kommandiert = []
    for satz in read_jsonl(verzeichnis / "ereignisse.jsonl"):
        daten = satz.get("daten") or {}
        if satz.get("art") == "kommando" and daten.get("name") == "walk":
            t0 = float(satz.get("t", 0.0))
            vx = float(daten.get("vx", 0.0))
            dauer = float(daten.get("duration", 0.0))
            kommandiert.append((t0, vx))
            kommandiert.append((t0 + dauer, vx))
    return gemessen, kommandiert


class SpeedPlot(QWidget):
    """Zwei Linien: gemessen und kommandiert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.gemessen = []
        self.kommandiert = []
        self.palette_ = DUNKEL

    def setze_daten(self, gemessen, kommandiert, palette=None):
        self.gemessen = list(gemessen)
        self.kommandiert = list(kommandiert)
        if palette is not None:
            self.palette_ = palette
        self.update()

    def paintEvent(self, ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        rand = 26
        breite = max(self.width() - 2 * rand, 1)
        hoehe = max(self.height() - 2 * rand, 1)

        maler.setPen(QPen(QColor(self.palette_.rand), 1))
        maler.drawRect(rand, rand, breite, hoehe)

        alle = self.gemessen + self.kommandiert
        if not alle:
            maler.setPen(QColor(self.palette_.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Keine Fahrdaten in diesem Lauf")
            return

        t_max = max(t for t, _ in alle) or 1.0
        v_max = max(0.1, max(abs(v) for _, v in alle)) * 1.15

        def punkt(t, v):
            return (rand + breite * (t / t_max), rand + hoehe * (1.0 - v / v_max))

        for reihe, farbe, dicke in (
            (self.kommandiert, self.palette_.gedaempft, 1),
            (self.gemessen, self.palette_.akzent, 2),
        ):
            if len(reihe) < 2:
                continue
            maler.setPen(QPen(QColor(farbe), dicke))
            vorher = punkt(*reihe[0])
            for t, v in reihe[1:]:
                jetzt = punkt(t, v)
                maler.drawLine(*(int(x) for x in vorher), *(int(x) for x in jetzt))
                vorher = jetzt

        maler.setPen(QColor(self.palette_.gedaempft))
        maler.drawText(rand, rand - 8, f"m/s (max {v_max:.2f})")
        maler.drawText(rand, self.height() - 6, f"0 – {t_max:.1f} s")


class RunsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ordner = None
        self._laeufe = []

        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._zeige_detail)

        self.ereignisliste = QListWidget()
        self.kurve = SpeedPlot()

        detail = QHBoxLayout()
        detail.addWidget(self.ereignisliste, 1)
        detail.addWidget(self.kurve, 1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Läufe"))
        anordnung.addWidget(self.tabelle, 2)
        anordnung.addWidget(QLabel("Kommandiertes (grau) gegen gemessenes (farbig) Tempo"))
        anordnung.addLayout(detail, 3)

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def aktualisiere(self):
        self._laeufe = []
        if self._ordner is not None:
            for projekt in projekte_in(self._ordner):
                self._laeufe.extend(list_runs(projekt / "runs"))
        self._laeufe.sort(key=lambda lauf: lauf.id, reverse=True)

        self.tabelle.setRowCount(len(self._laeufe))
        for zeile, lauf in enumerate(self._laeufe):
            skript = Path(lauf.skript).name if lauf.skript else ""
            werte = (lauf.id, lauf.ergebnis, f"{lauf.dauer_s:.1f} s", lauf.backend, skript)
            for spalte, wert in enumerate(werte):
                self.tabelle.setItem(zeile, spalte, QTableWidgetItem(str(wert)))

    def _zeige_detail(self):
        zeilen = {i.row() for i in self.tabelle.selectedIndexes()}
        if not zeilen:
            return
        lauf = self._laeufe[min(zeilen)]
        self.ereignisliste.clear()
        for satz in read_jsonl(lauf.dir / "ereignisse.jsonl"):
            daten = satz.get("daten") or {}
            beschreibung = daten.get("name") or daten.get("status") or ""
            self.ereignisliste.addItem(
                f"{satz.get('t', 0.0):7.2f} s  {satz.get('art', ''):<14} {beschreibung}"
            )
        self.kurve.setze_daten(*tempo_reihen(lauf.dir))
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_runs.py -q`, erwartet 8 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/views/runs.py tests/test_gui_runs.py
git commit -m "feat(gui): Laufliste mit Tempo-Kurve auf QPainter"
```

---

## Task 13: Ansicht „Spot"

**Files:**
- Create: `src/spotlab/gui/views/checkup.py`, `tests/test_gui_checkup.py`

**Interfaces:**
- Consumes: `Config`, `Limits`, `load_config`, `save_config`, `save_password`, `DoctorWorker`
- Produces: `CheckupView(QWidget)` mit Signalen `config_gespeichert(object)`, `pruefung_fertig(list)`; Methoden `lade()`, `zeige_pruefung(list)`

**Schliesst eine echte Lücke:** `spotlab login` fragt über `input()` und `getpass()` im Terminal. Ein Schüler, der nur die GUI benutzt, könnte sich damit nie einrichten.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_checkup.py`

```python
from spotlab.config import Config, Limits
from spotlab.gui.views.checkup import CheckupView
from spotlab.workshop.doctor import Check


def test_felder_werden_aus_der_konfiguration_gefuellt(qapp, tmp_path, monkeypatch):
    from spotlab.config import save_config

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="10.0.0.9", username="schueler", nickname="Bello",
                       limits=Limits(max_speed=0.4, max_turn_rate=0.5)), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    ansicht = CheckupView()
    ansicht.lade()
    assert ansicht.ip.text() == "10.0.0.9"
    assert ansicht.benutzer.text() == "schueler"
    assert ansicht.spitzname.text() == "Bello"
    assert abs(ansicht.max_tempo.value() - 0.4) < 1e-9


def test_ohne_konfiguration_bleiben_die_felder_leer(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    ansicht = CheckupView()
    ansicht.lade()
    assert ansicht.ip.text() == ""


def test_speichern_schreibt_konfiguration_und_passwort(qapp, tmp_path, monkeypatch):
    pfad = tmp_path / "config.toml"
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    passwoerter = {}
    monkeypatch.setattr("spotlab.gui.views.checkup.save_password",
                        lambda benutzer, wort: passwoerter.update({benutzer: wort}))

    ansicht = CheckupView()
    ansicht.ip.setText("192.168.80.3")
    ansicht.benutzer.setText("schueler")
    ansicht.spitzname.setText("Spot der Kanti")
    ansicht.passwort.setText("geheim")
    ansicht.speichern_knopf.click()

    from spotlab.config import load_config

    assert load_config(pfad).ip == "192.168.80.3"
    assert passwoerter == {"schueler": "geheim"}


def test_leeres_passwort_ueberschreibt_nicht(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "config.toml")
    gerufen = []
    monkeypatch.setattr("spotlab.gui.views.checkup.save_password",
                        lambda *a: gerufen.append(a))

    ansicht = CheckupView()
    ansicht.ip.setText("1.2.3.4")
    ansicht.benutzer.setText("u")
    ansicht.speichern_knopf.click()
    assert gerufen == []


def test_passwortfeld_ist_verdeckt(qapp):
    from PySide6.QtWidgets import QLineEdit

    assert CheckupView().passwort.echoMode() == QLineEdit.Password


def test_pruefergebnisse_werden_angezeigt(qapp):
    ansicht = CheckupView()
    ansicht.zeige_pruefung([
        Check("Netz", True, "antwortet"),
        Check("Anmeldung", False, "falsch", "spotlab login"),
    ])
    text = ansicht.ergebnisse.toPlainText()
    assert "Netz" in text and "spotlab login" in text
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_checkup.py -q`

- [ ] **Step 3: `gui/views/checkup.py` implementieren**

```python
"""Zugangsdaten und Prüfung.

Der Einrichtungsteil schliesst eine Lücke: `spotlab login` fragt über input()
und getpass() im Terminal. Wer nur die GUI benutzt, könnte sich damit nie
einrichten. Gespeichert wird über dieselben Funktionen wie im CLI — kein
zweiter Speicherweg, nur eine zweite Eingabemaske.

Die Geschwindigkeitsgrenzen stehen hier, damit eine Lehrperson sie für
Anfängerstunden herunterdrehen kann, ohne eine TOML-Datei zu suchen.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.config import Config, Limits, load_config, save_config, save_password
from spotlab.errors import SpotlabError


class CheckupView(QWidget):
    config_gespeichert = Signal(object)
    pruefung_angefordert = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = None

        self.ip = QLineEdit()
        self.benutzer = QLineEdit()
        self.spitzname = QLineEdit()
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        self.passwort.setPlaceholderText("leer lassen, um es nicht zu ändern")

        self.max_tempo = QDoubleSpinBox()
        self.max_tempo.setRange(0.05, 1.6)
        self.max_tempo.setSingleStep(0.05)
        self.max_tempo.setSuffix(" m/s")
        self.max_drehung = QDoubleSpinBox()
        self.max_drehung.setRange(0.05, 2.0)
        self.max_drehung.setSingleStep(0.05)
        self.max_drehung.setSuffix(" rad/s")

        self.speichern_knopf = QPushButton("Speichern")
        self.speichern_knopf.clicked.connect(self.speichere)
        self.pruefen_knopf = QPushButton("Spot prüfen")
        self.pruefen_knopf.clicked.connect(self.pruefung_angefordert.emit)

        self.ergebnisse = QPlainTextEdit()
        self.ergebnisse.setReadOnly(True)

        formular = QFormLayout()
        formular.addRow("IP-Adresse", self.ip)
        formular.addRow("Benutzername", self.benutzer)
        formular.addRow("Spitzname", self.spitzname)
        formular.addRow("Passwort", self.passwort)
        formular.addRow("Höchstgeschwindigkeit", self.max_tempo)
        formular.addRow("Höchste Drehrate", self.max_drehung)

        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.speichern_knopf)
        knoepfe.addWidget(self.pruefen_knopf)
        knoepfe.addStretch(1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Zugangsdaten"))
        anordnung.addLayout(formular)
        anordnung.addLayout(knoepfe)
        anordnung.addWidget(QLabel("Prüfung"))
        anordnung.addWidget(self.ergebnisse, 1)

        self.lade()

    # ------------------------------------------------------------- Daten

    def lade(self):
        try:
            self._config = load_config()
        except SpotlabError:
            self._config = None
        grenzen = self._config.limits if self._config else Limits()
        self.ip.setText(self._config.ip if self._config else "")
        self.benutzer.setText(self._config.username if self._config else "")
        self.spitzname.setText(self._config.nickname if self._config else "")
        self.max_tempo.setValue(grenzen.max_speed)
        self.max_drehung.setValue(grenzen.max_turn_rate)

    def speichere(self):
        alt = self._config
        cfg = Config(
            ip=self.ip.text().strip(),
            username=self.benutzer.text().strip(),
            nickname=self.spitzname.text().strip() or "Spot",
            limits=Limits(max_speed=self.max_tempo.value(),
                          max_turn_rate=self.max_drehung.value()),
            editor_command=alt.editor_command if alt else "code",
            default_backend=alt.default_backend if alt else "real",
            workspace=alt.workspace if alt else "",
        )
        save_config(cfg)
        wort = self.passwort.text()
        if wort:
            save_password(cfg.username, wort)
            self.passwort.clear()
        self._config = cfg
        self.config_gespeichert.emit(cfg)

    def zeige_pruefung(self, pruefungen):
        zeilen = []
        for pruefung in pruefungen:
            zeichen = "OK  " if pruefung.ok else "FEHL"
            zeilen.append(f"{zeichen} {pruefung.name:<14} {pruefung.detail}")
            if pruefung.rat:
                zeilen.append(f"       → {pruefung.rat}")
        self.ergebnisse.setPlainText("\n".join(zeilen))
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_checkup.py -q`, erwartet 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/views/checkup.py tests/test_gui_checkup.py
git commit -m "feat(gui): Ansicht Spot mit Einrichtung und Pruefung"
```

---

## Task 14: Hauptfenster

**Files:**
- Create: `src/spotlab/gui/app.py`, `tests/test_gui_app.py`

**Interfaces:**
- Consumes: alles aus Tasks 6–13
- Produces:
  - `MainWindow(QWidget)` mit `.kopf`, `.leiste`, `.ansichten` (dict), `.stapel`
  - `system_ist_dunkel(app) -> bool` — die **einzige** Stelle, die Qt nach dem Farbschema fragt
  - `main(argv=None) -> int`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_app.py`

```python
from spotlab.gui.app import MainWindow


def test_fenster_baut_sich_mit_vier_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {"projekte", "live", "laeufe", "spot"}
    assert fenster.stapel.count() == 4


def test_navigation_wechselt_die_ansicht(qapp):
    fenster = MainWindow()
    fenster.leiste.knoepfe["laeufe"].click()
    assert fenster.stapel.currentWidget() is fenster.ansichten["laeufe"]


def test_notaus_der_kopfleiste_erreicht_die_live_ansicht(qapp, monkeypatch):
    gerufen = []
    fenster = MainWindow()
    monkeypatch.setattr(fenster.ansichten["live"], "notaus",
                        lambda: gerufen.append(True))
    fenster.kopf.notaus_knopf.click()
    assert gerufen == [True]


def test_zustandssignal_erreicht_kopf_und_live(qapp, tmp_path):
    from spotlab.record.run import RunRecorder

    fenster = MainWindow()
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    fenster._lauf_begonnen(str(rec.dir))
    fenster._zustand({"daten": {"battery": 55.0, "pose": [1.0, 0.0, 0.0],
                                "velocity": [0.2, 0.0, 0.0], "feet": [True] * 4}})

    assert "55" in fenster.kopf.akku.text()
    assert "1.00" in fenster.ansichten["live"].kachel_pose.text()


def test_ohne_konfiguration_startet_die_spot_ansicht(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    fenster = MainWindow()
    assert fenster.stapel.currentWidget() is fenster.ansichten["spot"]


def test_lauf_start_wechselt_zur_live_ansicht(qapp, tmp_path):
    class FakeProzess:
        stdout = None

        def wait(self):
            return 0

    fenster = MainWindow()
    fenster._lauf_gestartet(FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_fehlermeldungen_landen_in_der_statuszeile(qapp):
    fenster = MainWindow()
    fenster._melde("Beobachter kaputt")
    assert "Beobachter kaputt" in fenster.statuszeile.text()
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_app.py -q`

- [ ] **Step 3: `gui/app.py` implementieren**

```python
"""Das Hauptfenster: Kopfleiste, Seitenleiste, vier Ansichten.

Hier wird verdrahtet und sonst nichts. Die einzige Stelle im Programm, die Qt
nach dem Farbschema fragt, ist system_ist_dunkel() — theme.py bleibt dadurch
Qt-frei und prüfbar.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spotlab.config import load_config, save_config
from spotlab.errors import SpotlabError
from spotlab.gui.header import Header
from spotlab.gui.sidebar import Sidebar
from spotlab.gui.theme import palette_fuer, stylesheet
from spotlab.gui.views.checkup import CheckupView
from spotlab.gui.views.live import LiveView
from spotlab.gui.views.projects import ProjectsView
from spotlab.gui.views.runs import RunsView
from spotlab.gui.watcher import RunWatcher
from spotlab.gui.workers import DoctorWorker, OutputReader


def system_ist_dunkel(app=None):
    """Die einzige Stelle, die Qt nach dem Farbschema fragt."""
    app = app or QApplication.instance()
    if app is None:
        return True
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return True


class MainWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("spotlab")
        self.resize(1080, 720)

        try:
            self._config = load_config()
        except SpotlabError:
            self._config = None

        self.kopf = Header()
        self.leiste = Sidebar()
        self.statuszeile = QLabel("")
        self.statuszeile.setObjectName("Gedaempft")

        self.ansichten = {
            "projekte": ProjectsView(
                editor_command=self._config.editor_command if self._config else "code"),
            "live": LiveView(),
            "laeufe": RunsView(),
            "spot": CheckupView(),
        }
        self.stapel = QStackedWidget()
        for schluessel in ("projekte", "live", "laeufe", "spot"):
            self.stapel.addWidget(self.ansichten[schluessel])

        unten = QHBoxLayout()
        unten.setContentsMargins(0, 0, 0, 0)
        unten.addWidget(self.leiste)
        unten.addWidget(self.stapel, 1)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(self.kopf)
        aussen.addLayout(unten, 1)
        aussen.addWidget(self.statuszeile)

        self._watcher = None
        self._leser = None
        self._doctor = None
        self._verdrahte()
        self._setze_arbeitsordner(self._config.workspace if self._config else "")
        self.kopf.zeige_config(self._config)

        if self._config is None:
            self._wechsle("spot")
            self.leiste.waehle("spot")

    # ------------------------------------------------------------- Aufbau

    def _verdrahte(self):
        self.leiste.gewaehlt.connect(self._wechsle)
        self.kopf.notaus.connect(lambda: self.ansichten["live"].notaus())
        self.ansichten["live"].meldung.connect(self._melde)
        self.ansichten["projekte"].lauf_gestartet.connect(self._lauf_gestartet)
        self.ansichten["projekte"].arbeitsordner_geaendert.connect(self._merke_arbeitsordner)
        self.ansichten["spot"].config_gespeichert.connect(self._config_gespeichert)
        self.ansichten["spot"].pruefung_angefordert.connect(self._pruefe)

    def _setze_arbeitsordner(self, pfad):
        self.ansichten["projekte"].setze_arbeitsordner(pfad or None)
        self.ansichten["laeufe"].setze_arbeitsordner(pfad or None)
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if not pfad:
            return
        self._watcher = RunWatcher(Path(pfad))
        self._watcher.lauf_begonnen.connect(self._lauf_begonnen)
        self._watcher.zustand.connect(self._zustand)
        self._watcher.ereignis.connect(self.ansichten["live"].zeige_ereignis)
        self._watcher.bild.connect(self.ansichten["live"].zeige_bild)
        self._watcher.lauf_beendet.connect(self._lauf_beendet)
        self._watcher.fehler.connect(self._melde)
        self._watcher.start()

    # ------------------------------------------------------------- Reaktionen

    def _wechsle(self, schluessel):
        self.stapel.setCurrentWidget(self.ansichten[schluessel])

    def _melde(self, text):
        self.statuszeile.setText(text)

    def _merke_arbeitsordner(self, pfad):
        self._setze_arbeitsordner(pfad)
        if self._config is None:
            return
        from dataclasses import replace

        self._config = replace(self._config, workspace=pfad)
        save_config(self._config)

    def _config_gespeichert(self, cfg):
        self._config = cfg
        self.kopf.zeige_config(cfg)

    def _pruefe(self):
        self.ansichten["spot"].pruefen_knopf.setEnabled(False)
        self.ansichten["spot"].pruefen_knopf.setText("Prüfe…")
        self._doctor = DoctorWorker(self)
        self._doctor.fertig.connect(self._pruefung_fertig)
        self._doctor.fehler.connect(self._melde)
        self._doctor.finished.connect(self._pruefung_aufraeumen)
        self._doctor.start()

    def _pruefung_fertig(self, pruefungen):
        self.ansichten["spot"].zeige_pruefung(pruefungen)
        self.kopf.zeige_pruefung(pruefungen)

    def _pruefung_aufraeumen(self):
        self.ansichten["spot"].pruefen_knopf.setEnabled(True)
        self.ansichten["spot"].pruefen_knopf.setText("Spot prüfen")

    def _lauf_gestartet(self, prozess, skript):
        self._wechsle("live")
        self.leiste.waehle("live")
        self._leser = OutputReader(prozess, self)
        self._leser.zeile.connect(self.ansichten["live"].zeige_ausgabe)
        self._leser.start()

    def _lauf_begonnen(self, verzeichnis):
        self.ansichten["live"].setze_lauf(verzeichnis, Path(verzeichnis).name)

    def _zustand(self, satz):
        self.kopf.zeige_zustand(satz)
        self.ansichten["live"].zeige_zustand(satz)

    def _lauf_beendet(self, verzeichnis):
        self.ansichten["live"].lauf_beendet()
        self.ansichten["laeufe"].aktualisiere()
        self.kopf.zeige_getrennt()

    def closeEvent(self, ereignis):
        if self._watcher is not None:
            self._watcher.stop()
        super().closeEvent(ereignis)


def main(argv=None):
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("spotlab")
    app.setStyleSheet(stylesheet(palette_fuer(system_ist_dunkel(app))))
    fenster = MainWindow()
    fenster.show()
    return app.exec()
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_app.py -q`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/app.py tests/test_gui_app.py
git commit -m "feat(gui): Hauptfenster mit Verdrahtung"
```

---

## Task 15: `spotlab gui`

**Files:**
- Modify: `src/spotlab/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: Unterkommando `gui`; ohne PySide6 eine verständliche Meldung statt `ModuleNotFoundError`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — an `tests/test_cli.py` anhängen

```python
def test_gui_kommando_existiert():
    assert build_parser().parse_args(["gui"])


def test_gui_ohne_pyside_nennt_den_befehl(monkeypatch, capsys):
    import builtins

    echt = builtins.__import__

    def ohne_pyside(name, *args, **kw):
        if name.startswith("spotlab.gui") or name.startswith("PySide6"):
            raise ImportError("No module named 'PySide6'")
        return echt(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", ohne_pyside)
    assert main(["gui"]) == 1
    assert "pip install" in capsys.readouterr().err
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_cli.py -q`

- [ ] **Step 3: `cli.py` ergänzen** — in `build_parser` nach dem `lease`-Block:

```python
    unter.add_parser("gui", help="Fenster öffnen")
```

und in `_fuehre_aus` vor `return 1`:

```python
    if args.kommando == "gui":
        return _gui()
```

sowie am Dateiende:

```python
def _gui():
    try:
        from spotlab.gui.app import main as gui_main
    except ImportError:
        print(
            f"{ROT}Die Oberfläche braucht PySide6.{AUS}\n"
            "Einmalig installieren mit:\n"
            "    pip install -e .[gui]",
            file=sys.stderr,
        )
        return 1
    return int(gui_main([]) or 0)
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_cli.py -q`, erwartet alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/cli.py tests/test_cli.py
git commit -m "feat(cli): Unterkommando gui mit verstaendlichem Hinweis ohne PySide6"
```

---

## Task 16: Kettentest

**Files:**
- Create: `tests/test_kette.py`

**Interfaces:**
- Consumes: alles

**Der wichtigste Test des Plans.** Er deckt die Naht ab, an der GUI und Fundament zusammenstossen, und läuft vollständig ohne Roboter: echtes Skript, echter Unterprozess, echter Beobachter, echter Stopp.

- [ ] **Step 1: Test schreiben** — `tests/test_kette.py`

```python
"""Die ganze Kette ohne Roboter: starten → beobachten → stoppen."""

import time

import pytest

from spotlab.gui.watcher import RunScanner
from spotlab.workshop.control import ist_aktiv, stoppe_freundlich
from spotlab.workshop.launcher import start_script
from spotlab.workshop.project import create_project

SKRIPT = """
import spotlab

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    for _ in range(200):
        spot.walk(vx=0.1, duration=0.2)
"""


def _warte_bis(bedingung, grenze_s=15.0, takt_s=0.1):
    ende = time.monotonic() + grenze_s
    while time.monotonic() < ende:
        wert = bedingung()
        if wert:
            return wert
        time.sleep(takt_s)
    return None


@pytest.mark.timeout(60) if hasattr(pytest.mark, "timeout") else (lambda f: f)
def test_starten_beobachten_stoppen(tmp_path):
    projekt = create_project("kette", tmp_path)
    (projekt / "lang.py").write_text(SKRIPT, encoding="utf-8")

    prozess = start_script(projekt / "lang.py", dryrun=True)
    try:
        scanner = RunScanner(projekt / "runs")

        gefunden = _warte_bis(
            lambda: [p for art, p in scanner.tick() if art == "lauf_begonnen"])
        assert gefunden, "Der Beobachter hat den Lauf nicht aufgegriffen"
        lauf = gefunden[0]

        zustaende = _warte_bis(
            lambda: [d for art, d in scanner.tick() if art == "zustand"])
        assert zustaende, "Keine Telemetrie angekommen"
        assert "battery" in zustaende[0]["daten"]

        stoppe_freundlich(lauf)
        assert _warte_bis(lambda: prozess.poll() is not None), \
            "Der freundliche Stopp hat den Lauf nicht beendet"

        _warte_bis(lambda: not ist_aktiv(lauf))
        import json

        daten = json.loads((__import__("pathlib").Path(lauf) / "lauf.json")
                           .read_text(encoding="utf-8"))
        assert daten["ergebnis"] == "abgebrochen"
    finally:
        if prozess.poll() is None:
            prozess.kill()
            prozess.wait()
```

**Hinweis zum Dekorator:** `pytest-timeout` ist keine Abhängigkeit dieses Projekts. Die
Zeile `@pytest.mark.timeout(60) if ... else (lambda f: f)` ist deshalb zu **ersetzen** durch
schlichtes Weglassen des Dekorators — die Schleifen in `_warte_bis` haben eigene Schranken.
Der Test hat damit eine harte Obergrenze von rund 30 s.

- [ ] **Step 2: Dekoratorzeile entfernen** — die Zeile mit `pytest.mark.timeout` löschen, sodass die Funktion direkt auf den Docstring folgt

- [ ] **Step 3: Test laufen lassen** — `pytest tests/test_kette.py -q -s`, erwartet PASS

- [ ] **Step 4: Gesamtsuite** — `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add tests/test_kette.py
git commit -m "test: Kettentest starten-beobachten-stoppen ohne Roboter"
```

---

## Task 17: Doku und Abnahme

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/ABNAHME.md`

- [ ] **Step 1: `README.md`** — Abschnitt „Oberfläche" nach dem Schnellstart einfügen: Installation `pip install -e .[gui]`, Start `spotlab gui`, die vier Ansichten in je einem Satz, und der Hinweis, dass die GUI **nie ein Lease hält** und deshalb kein Live-Kamerabild ohne laufendes Skript zeigt. Die Stopp-Semantik in zwei Sätzen: Stopp = Spot setzt sich hin, NOT-AUS = Motoren aus und Spot sackt zusammen.

- [ ] **Step 2: `CLAUDE.md`** — unter „Nicht verhandelbar" ergänzen:

```markdown
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.**
  Die GUI hält nie ein Lease; sie liest Live-Daten aus dem Lauf-Verzeichnis.
- **Farben nur aus `gui/theme.py`.** Ein Farbliteral im Widget-Code bricht den zweiten
  Hell/Dunkel-Modus, ohne dass es auffällt.
- **`beende_hart` tötet nur einen Lauf, der nach `ist_aktiv()` noch lebt.** Prozess-IDs
  werden wiederverwendet.
```

und unter „Tests" ergänzen:

```markdown
- Qt-Tests laufen mit `QT_QPA_PLATFORM=offscreen` (in `conftest.py` gesetzt) und werden
  ohne das Extra `[gui]` sauber übersprungen.
- Was nicht Widget ist, gehört in ein Qt-freies Modul — `record/tail.py`,
  `workshop/control.py`, `gui/theme.py`, `gui/watcher.py::RunScanner`.
```

- [ ] **Step 3: `docs/ABNAHME.md`** — die Punkte A9–A11 anhängen, jeweils mit Prozedur, Erwartung und leerem Ergebnisfeld:

**A9 — Freundlicher Stopp aus der GUI.** Skript mit langer `walk()`-Phase starten, in der GUI *Stopp* drücken. Erwartung: Spot bremst, setzt sich kontrolliert hin, Motoren aus, Lease frei; `lauf.json` trägt `abgebrochen`. Der Knopf „Reagiert nicht" darf **nicht** erscheinen.

**A10 — NOT-AUS aus der GUI.** Spot steht, NOT-AUS drücken. Erwartung: Motoren gehen sofort aus, Spot sackt zusammen; `lauf.json` bleibt auf `läuft` stehen (der Prozess wurde getötet, `finish()` lief nie); der Roboter ist danach ohne Neustart wieder verbindbar. **Vor diesem Punkt Freifläche und Aufsicht sicherstellen.**

**A11 — F5-Lauf aus VS Code.** GUI geöffnet lassen, in VS Code F5 drücken. Erwartung: die GUI greift den Lauf innerhalb einer Sekunde auf, zeigt Telemetrie, und **beide Stopp-Knöpfe wirken**. Fällt A11 durch, ist Grundsatzentscheidung H3 falsch und die GUI für den Unterrichtsalltag wertlos.

- [ ] **Step 4: Gesamtsuite** — `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/ABNAHME.md
git commit -m "docs: Oberflaeche im README, Arbeitsregeln, Abnahme A9-A11"
```

---

## Selbstprüfung des Plans

**Spec-Abdeckung:** H1 (kein Lease) → Regel in Global Constraints, geprüft in Task 6 (`test_theme_ist_qt_frei` als Muster) und in CLAUDE.md verankert · H2 (PySide6 als Extra) → Task 6 Step 6, Task 15 · H3 (alle Läufe) → Task 7, Task 16 · H4 (zwei Stopp-Wege) → Task 2, Task 5, Task 11 · H5 (zwei Paletten) → Task 6, Task 14 `system_ist_dunkel` · Nachtrag a (pid) → Task 1 · b (Stopp-Markierung) → Task 2 · c (`start_script`) → Task 3 · d (workspace) → Task 1, verwendet in Task 14 · 5.1 tail → Task 4 · 5.2 control → Task 5 · 5.3 theme → Task 6 · 5.4 watcher/workers → Tasks 7, 8 · 5.5 Kopfleiste → Task 9 · 5.6 Projekte → Task 10 · 5.7 Live → Task 11 · 5.8 Läufe → Task 12 · 5.9 Spot → Task 13 · Abschnitt 7 Fehlerbehandlung → in den jeweiligen Tasks als Tests · Abschnitt 8 Prüfung → durchgehend · Abschnitt 9 Abnahme → Task 17.

**Bewusste Abweichung von der Spec:** Die Spec nennt für `RunWatcher` die Signalnamen ohne Typen. Der Plan legt sie auf `Signal(str)` für Pfade und `Signal(dict)` für Sätze fest, weil Qt-Signale typisiert deklariert werden müssen. Pfade werden als `str` übertragen, nicht als `Path` — Qt-Signale mit `object` sind möglich, aber `str` hält die Verdrahtung überprüfbar.

**Ein in der Spec nicht behandelter Fall, hier entschieden:** Die Spec sagt nicht, was passiert, wenn beim Start der GUI bereits ein Lauf aktiv ist. Task 7 entscheidet: **ja, er wird aufgegriffen** (`RunScanner._neue_laeufe` prüft nur `ist_aktiv`, nicht den Startzeitpunkt) — nur alte, beendete Läufe werden ignoriert. Das ist das Verhalten, das man erwartet, wenn man die GUI öffnet, während ein Skript schon läuft.
