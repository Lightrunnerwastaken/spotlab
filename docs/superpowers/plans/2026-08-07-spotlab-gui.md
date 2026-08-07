# spotlab GUI — Implementierungsplan, Teil 1 (Fundament-Nachträge und Qt-freie Module)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine PySide6-Oberfläche, mit der Schüler Projekte anlegen, Skripte starten, beim Laufen zusehen und im Notfall anhalten können — ohne Kommandozeile.

**Architecture:** Die GUI ist Klient von `workshop/`, `record/` und `config.py` und importiert **nie** `bosdyn` oder `backends/`. Alles, was nicht Widget ist, liegt in Qt-freien Modulen und wird normal mit pytest geprüft; Qt-Klassen bleiben dünne Hüllen, die Signale verdrahten. Live-Daten kommen aus dem Lauf-Verzeichnis, nicht aus einer eigenen Roboterverbindung.

**Tech Stack:** Python 3.13, PySide6 6.11.1 (optionales Extra `[gui]`), pytest. Bestehendes Fundament: `bosdyn-client`/`bosdyn-api` 5.0.1.2.

## Global Constraints

- Python ≥ 3.11, entwickelt und geprüft auf 3.13.9.
- **`PySide6>=6.6` ist die einzige neue Abhängigkeit**, und nur im Extra `[gui]`. Keine Diagrammbibliothek — die eine Kurve wird auf einem `QPainter`-Widget gezeichnet.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.** Das ist eine Entwurfsregel, kein Stil: die GUI hält nie ein Lease.
- Python-Bezeichner englisch, alle Meldungen an Nutzer deutsch. Datei- und Feldnamen der Aufzeichnung deutsch.
- Alle Tests laufen ohne Roboter, ohne Netz und ohne Bildschirm (`QT_QPA_PLATFORM=offscreen`).
- Keine Farbliterale in Widget-Code — Farben kommen ausschliesslich aus `gui/theme.py`.
- Testgetrieben: erst der fehlschlagende Test, dann die Implementierung. Commit pro Task.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `src/spotlab/record/run.py` | `pid` in `lauf.json`, `STOPP_DATEI` | ändern |
| `src/spotlab/record/sampler.py` | prüft auf Stopp-Markierung | ändern |
| `src/spotlab/config.py` | Feld `workspace` | ändern |
| `src/spotlab/workshop/launcher.py` | `start_script` nicht blockierend | ändern |
| `src/spotlab/record/tail.py` | inkrementelles jsonl-Nachlesen | **neu** |
| `src/spotlab/workshop/control.py` | Läufe finden, freundlich stoppen, hart beenden | **neu** |
| `src/spotlab/gui/theme.py` | zwei Paletten, Stylesheet | **neu** |
| `src/spotlab/gui/watcher.py` | `RunWatcher` mit Qt-Signalen | **neu** |
| `src/spotlab/gui/workers.py` | `DoctorWorker`, `OutputReader` | **neu** |
| `src/spotlab/gui/header.py` | Kopfleiste mit NOT-AUS | **neu** |
| `src/spotlab/gui/sidebar.py` | Navigation | **neu** |
| `src/spotlab/gui/views/projects.py` | Projekte anlegen, öffnen, starten | **neu** |
| `src/spotlab/gui/views/live.py` | laufender Lauf | **neu** |
| `src/spotlab/gui/views/runs.py` | Laufliste, Detail, Tempo-Kurve | **neu** |
| `src/spotlab/gui/views/checkup.py` | Zugangsdaten und Prüfung | **neu** |
| `src/spotlab/gui/app.py` | Hauptfenster, Verdrahtung, `main()` | **neu** |
| `src/spotlab/cli.py` | Unterkommando `gui` | ändern |
| `pyproject.toml` | Extra `[gui]` | ändern |

---

## Task 1: Prozess-ID und Arbeitsordner

**Files:**
- Modify: `src/spotlab/record/run.py`, `src/spotlab/config.py`
- Test: `tests/test_record_run.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `spotlab.record.run.STOPP_DATEI = "stopp"`
  - `lauf.json` enthält `"pid": <int>`
  - `Config.workspace: str = ""`, geschrieben als `[gui] workspace`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — an `tests/test_record_run.py` anhängen

```python
def test_lauf_json_traegt_die_prozess_id(tmp_path):
    """Ohne die PID kann der Not-Aus keinen Lauf beenden, den er nicht selbst gestartet hat."""
    import json
    import os

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.finish("ok")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["pid"] == os.getpid()


def test_stopp_datei_ist_benannt():
    from spotlab.record.run import STOPP_DATEI

    assert STOPP_DATEI == "stopp"
```

und an `tests/test_config.py`:

```python
def test_arbeitsordner_ueberlebt_schreiben_und_lesen(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(),
                 workspace=r"D:\Schule\Spot")
    save_config(cfg, pfad)
    assert load_config(pfad).workspace == r"D:\Schule\Spot"


def test_arbeitsordner_hat_leere_vorgabe(tmp_path):
    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot]\nip = "1.2.3.4"\nusername = "u"\n', encoding="utf-8")
    assert load_config(pfad).workspace == ""
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_record_run.py tests/test_config.py -q`, erwartet 4 Fehlschläge

- [ ] **Step 3: `record/run.py` ergänzen**

Nach `ZEITFORMAT` einfügen:

```python
STOPP_DATEI = "stopp"          # von der GUI angelegt; der Abtaster bricht daraufhin ab
```

In `RunRecorder.__init__` im `self._meta`-Wörterbuch nach `"python"` einfügen:

```python
            "pid": os.getpid(),
```

(`os` ist in `run.py` bereits importiert.)

- [ ] **Step 4: `config.py` ergänzen**

In `Config` nach `default_backend`:

```python
    workspace: str = ""          # Arbeitsordner der GUI; leer = noch nicht gewählt
```

In `save_config` den `[defaults]`-Block ergänzen um:

```python
        "\n[gui]\n"
        f"workspace = {_toml_string(cfg.workspace)}\n"
```

In `load_config` im `Config(...)`-Aufruf ergänzen:

```python
        workspace=roh.get("gui", {}).get("workspace", ""),
```

- [ ] **Step 5: Tests laufen lassen** — `pytest -q`, erwartet alle PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/record/run.py src/spotlab/config.py tests/
git commit -m "feat(record,config): Prozess-ID im Lauf und Arbeitsordner in der Konfiguration"
```

---

## Task 2: Stopp-Markierung im Abtaster

**Files:**
- Modify: `src/spotlab/record/sampler.py`
- Test: `tests/test_sampler.py`

**Interfaces:**
- Consumes: `spotlab.record.run.STOPP_DATEI`
- Produces: `StateSampler` bricht den Lauf ab, sobald `<lauf>/stopp` existiert — über `_thread.interrupt_main()`, also über den vorhandenen `KeyboardInterrupt`-Pfad von `connect()`

**Warum über eine Datei und nicht über ein Signal:** funktioniert für jeden Lauf, egal wer ihn gestartet hat, und umgeht die Windows-Eigenheiten beim Zustellen von `SIGINT` an einen fremden Prozess.

- [ ] **Step 1: Fehlschlagenden Test schreiben** — an `tests/test_sampler.py` anhängen

```python
def test_stopp_markierung_bricht_den_lauf_ab(tmp_path, monkeypatch):
    """Die GUI legt <lauf>/stopp an; der Abtaster löst KeyboardInterrupt im Hauptthread aus."""
    from spotlab.record.run import STOPP_DATEI

    gerufen = []
    monkeypatch.setattr("spotlab.record.sampler._thread.interrupt_main",
                        lambda: gerufen.append(True))

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.05)
    (rec.dir / STOPP_DATEI).touch()
    threading.Event().wait(0.15)
    abtaster.stop()
    rec.finish("abgebrochen")

    assert gerufen, "interrupt_main wurde nicht aufgerufen"


def test_stopp_wird_nur_einmal_ausgeloest(tmp_path, monkeypatch):
    """Sonst hagelt es KeyboardInterrupts, während der Abbau läuft."""
    from spotlab.record.run import STOPP_DATEI

    gerufen = []
    monkeypatch.setattr("spotlab.record.sampler._thread.interrupt_main",
                        lambda: gerufen.append(True))

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    (rec.dir / STOPP_DATEI).touch()
    abtaster = StateSampler(DryRunBackend(), rec, hz=500.0)
    abtaster.start()
    threading.Event().wait(0.2)
    abtaster.stop()
    rec.finish("abgebrochen")

    assert len(gerufen) == 1
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_sampler.py -q`, erwartet 2 Fehlschläge

- [ ] **Step 3: `record/sampler.py` umschreiben**

```python
"""10-Hz-Abtastung des Roboterzustands in einem Hintergrund-Thread.

Läuft unabhängig davon, was das Schülerskript tut — auch ein Skript, das nur
wartet, produziert damit verwertbare Messdaten für die Sim-Kalibrierung.

Zweite Aufgabe: der Thread ist der Zustellweg für den freundlichen Stopp der
GUI. Er prüft bei jedem Takt, ob <lauf>/stopp angelegt wurde, und löst dann
KeyboardInterrupt im Hauptthread aus — also genau den Abbruchpfad, den
connect() bereits behandelt.
"""

import _thread
import threading
import time

from spotlab.api.state import as_sample
from spotlab.record.run import STOPP_DATEI


class StateSampler:
    def __init__(self, backend, recorder, hz=10.0):
        self._backend = backend
        self._recorder = recorder
        self._periode = 1.0 / float(hz)
        self._stopp = threading.Event()
        self._thread = None
        self._stopp_datei = recorder.dir / STOPP_DATEI
        self._abbruch_gemeldet = False

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._schleife, name="spotlab-sampler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=2.0):
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _pruefe_stopp(self):
        """Genau einmal auslösen — sonst regnet es KeyboardInterrupts in den Abbau."""
        if self._abbruch_gemeldet:
            return
        try:
            vorhanden = self._stopp_datei.exists()
        except OSError:
            return
        if vorhanden:
            self._abbruch_gemeldet = True
            _thread.interrupt_main()

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            self._pruefe_stopp()
            try:
                self._recorder.sample(as_sample(self._backend.robot_state()))
            except Exception:  # Abtastung darf den Lauf nie kippen
                self._stopp.wait(self._periode)
                continue
            rest = self._periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_sampler.py -q`, erwartet 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/record/sampler.py tests/test_sampler.py
git commit -m "feat(record): Stopp-Markierung loest den vorhandenen Abbruchpfad aus"
```

---

## Task 3: `start_script` nicht blockierend

**Files:**
- Modify: `src/spotlab/workshop/launcher.py`
- Test: `tests/test_workshop_launcher.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `start_script(pfad, dryrun=False, starter=subprocess.Popen) -> Popen` — kehrt sofort zurück, `stdout`/`stderr` zusammengeführt als Text-Pipe
  - `run_script(pfad, dryrun=False, starter=subprocess.Popen) -> int` — blockierende CLI-Variante, **auf `start_script` aufgesetzt**

**Achtung, Bruch an bestehenden Tests:** `run_script` nahm bisher ein `starter` entgegen, das sich wie `subprocess.run` verhält (Rückgabe mit `.returncode`). Jetzt verhält es sich wie `subprocess.Popen` (Rückgabe mit `.wait()`). Die drei bestehenden Attrappen in `tests/test_workshop_launcher.py` sind entsprechend anzupassen — das ist eine bewusste Änderung, kein Versehen.

- [ ] **Step 1: Bestehende Attrappe anpassen und neue Tests schreiben** — in `tests/test_workshop_launcher.py` die Klasse `Ergebnis` ersetzen durch:

```python
class FakeProzess:
    """Verhält sich wie ein Popen: hat wait() und returncode."""

    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = None

    def wait(self):
        return self.returncode
```

und im Modul die drei Vorkommen `return Ergebnis()` durch `return FakeProzess()` ersetzen sowie die Importzeile ergänzen:

```python
from spotlab.workshop.launcher import run_script, start_script
```

Neue Tests anhängen:

```python
def test_start_script_kehrt_sofort_zurueck(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    gebaut = []

    def starter(argumente, **kw):
        gebaut.append((argumente, kw))
        return FakeProzess()

    prozess = start_script(skript, starter=starter)
    assert prozess.returncode == 0
    argumente, kw = gebaut[0]
    assert argumente[1] == str(skript)
    assert kw["cwd"] == str(tmp_path)


def test_start_script_fuehrt_ausgabe_zusammen(tmp_path):
    """Ein Leser statt zwei: sonst muss die GUI zwei Pipes gleichzeitig bedienen."""
    import subprocess

    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    gebaut = []

    def starter(argumente, **kw):
        gebaut.append(kw)
        return FakeProzess()

    start_script(skript, starter=starter)
    kw = gebaut[0]
    assert kw["stdout"] is subprocess.PIPE
    assert kw["stderr"] is subprocess.STDOUT
    assert kw["text"] is True


def test_run_script_wartet_und_gibt_code_zurueck(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    assert run_script(skript, starter=lambda *a, **k: FakeProzess(returncode=3)) == 3
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_workshop_launcher.py -q`, erwartet Fehlschläge wegen fehlendem `start_script`

- [ ] **Step 3: `workshop/launcher.py` umschreiben**

```python
"""Ein Schülerskript starten.

Die Aufzeichnung hängt an connect(), nicht an diesem Starter — wer in VS Code
F5 drückt, bekommt sie genauso. Hier kommen nur die Backend-Wahl per
Umgebungsvariable, der Importpfad und die Ausgabe-Pipe dazu.

start_script() kehrt sofort zurück und ist der Weg der GUI; run_script()
wartet und ist der Weg der Kommandozeile. Beide bauen denselben Prozess auf,
damit es keinen zweiten Code-Pfad gibt.
"""

import os
import subprocess
import sys
from pathlib import Path

from spotlab.errors import SpotlabError

ENV_BACKEND = "SPOTLAB_BACKEND"


def _umgebung(dryrun):
    umgebung = dict(os.environ)
    if dryrun:
        umgebung[ENV_BACKEND] = "dryrun"

    # UTF-8 im Kindprozess erzwingen: die Meldungen der Bibliothek sind deutsch,
    # und eine Windows-Konsole mit cp1252 macht daraus sonst Buchstabensalat.
    umgebung["PYTHONUTF8"] = "1"

    # Den Importpfad des Elternprozesses weiterreichen: wer spotlab hier
    # importieren kann, muss es auch im Kindprozess können. Ohne das scheitert
    # `spotlab run` in jedem Quellcode-Checkout ohne Installation.
    umgebung["PYTHONPATH"] = os.pathsep.join(
        [p for p in sys.path if p] + [umgebung.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    return umgebung


def start_script(pfad, dryrun=False, starter=subprocess.Popen):
    """Startet das Skript und kehrt SOFORT zurück. Gibt den Prozess-Handle zurück.

    stdout und stderr laufen zusammen in eine Text-Pipe: die GUI muss dann nur
    einen Leser betreiben, und die Reihenfolge von print und Traceback bleibt
    so erhalten, wie sie im Terminal erschiene.
    """
    skript = Path(pfad).resolve()
    if not skript.exists():
        raise SpotlabError(f"Die Datei {skript} gibt es nicht.")

    return starter(
        [sys.executable, "-u", str(skript)],
        cwd=str(skript.parent),
        env=_umgebung(dryrun),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def run_script(pfad, dryrun=False, starter=subprocess.Popen):
    """Blockierende Variante für die Kommandozeile."""
    prozess = start_script(pfad, dryrun=dryrun, starter=starter)
    if getattr(prozess, "stdout", None) is not None:
        for zeile in prozess.stdout:
            print(zeile, end="")
    return int(prozess.wait())
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_workshop_launcher.py -q`, erwartet alle PASS

- [ ] **Step 5: Gesamtsuite** — `pytest -q`; `tests/test_cli.py::test_run_mit_dryrun_setzt_die_variable` muss weiterhin PASS sein (echter Unterprozess)

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/workshop/launcher.py tests/test_workshop_launcher.py
git commit -m "feat(workshop): start_script kehrt sofort zurueck, run_script setzt darauf auf"
```

---

## Task 4: Inkrementelles jsonl-Nachlesen

**Files:**
- Create: `src/spotlab/record/tail.py`, `tests/test_record_tail.py`

**Interfaces:**
- Consumes: nichts
- Produces: `JsonlTail(path)` mit `.neue_saetze() -> list[dict]` und `.stand -> int`

**Der Kern der Sache:** eine halb geschriebene letzte Zeile darf **nicht** verschluckt werden. Der Stand wird nur bis zum letzten vollständigen Zeilenumbruch fortgeschrieben. Ein naiver Ansatz verliert hier still Messwerte — und zwar genau die, die beim Abbruch eines Laufs am interessantesten sind.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_record_tail.py`

```python
import json

from spotlab.record.tail import JsonlTail


def _schreibe(pfad, *saetze, unvollstaendig=None):
    with pfad.open("a", encoding="utf-8") as datei:
        for satz in saetze:
            datei.write(json.dumps(satz, ensure_ascii=False) + "\n")
        if unvollstaendig is not None:
            datei.write(unvollstaendig)


def test_fehlende_datei_ergibt_leere_liste(tmp_path):
    assert JsonlTail(tmp_path / "gibtsnicht.jsonl").neue_saetze() == []


def test_liest_nur_neues(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, {"t": 2})
    tail = JsonlTail(pfad)
    assert [s["t"] for s in tail.neue_saetze()] == [1, 2]
    assert tail.neue_saetze() == []

    _schreibe(pfad, {"t": 3})
    assert [s["t"] for s in tail.neue_saetze()] == [3]


def test_halbe_letzte_zeile_wird_nicht_verschluckt(tmp_path):
    """Der wichtigste Fall: der Abtaster schreibt gerade, wir lesen mitten hinein."""
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, unvollstaendig='{"t": 2, "dat')
    tail = JsonlTail(pfad)
    assert [s["t"] for s in tail.neue_saetze()] == [1]

    with pfad.open("a", encoding="utf-8") as datei:      # Zeile fertigschreiben
        datei.write('en": {}}\n')
    assert [s["t"] for s in tail.neue_saetze()] == [2]


def test_verkuerzte_datei_setzt_den_stand_zurueck(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, {"t": 2})
    tail = JsonlTail(pfad)
    tail.neue_saetze()

    pfad.write_text("", encoding="utf-8")
    _schreibe(pfad, {"t": 9})
    assert [s["t"] for s in tail.neue_saetze()] == [9]


def test_unlesbare_zeile_wird_uebersprungen(tmp_path):
    pfad = tmp_path / "z.jsonl"
    pfad.write_text('{"t": 1}\nkein json\n{"t": 2}\n', encoding="utf-8")
    assert [s["t"] for s in JsonlTail(pfad).neue_saetze()] == [1, 2]


def test_umlaute_ueberleben(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"art": "rückmeldung", "daten": {"status": "steht"}})
    assert JsonlTail(pfad).neue_saetze()[0]["art"] == "rückmeldung"


def test_stand_waechst_nur_bis_zum_zeilenumbruch(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, unvollstaendig="halb")
    tail = JsonlTail(pfad)
    tail.neue_saetze()
    assert tail.stand == len('{"t": 1}\n'.encode("utf-8"))
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_record_tail.py -q`, erwartet `ModuleNotFoundError`

- [ ] **Step 3: `record/tail.py` implementieren**

```python
"""Eine jsonl-Datei mitlesen, während sie geschrieben wird.

Der Abtaster schreibt mit 10 Hz; die GUI liest mit 4 Hz nach. Beim Lesen kann
die letzte Zeile halb geschrieben sein. Sie darf dann NICHT als kaputt
verworfen werden — sonst verliert die Anzeige still Messwerte, und zwar
bevorzugt die letzten vor einem Abbruch, also die interessantesten.

Deshalb wandert der Lesestand nur bis zum letzten vollständigen
Zeilenumbruch; der Rest wird beim nächsten Aufruf gelesen.
"""

import json
from pathlib import Path


class JsonlTail:
    def __init__(self, path):
        self._pfad = Path(path)
        self.stand = 0

    def neue_saetze(self):
        """Alle vollständigen Zeilen seit dem letzten Aufruf."""
        try:
            groesse = self._pfad.stat().st_size
        except OSError:
            return []                       # Datei (noch) nicht da

        if groesse < self.stand:            # neu begonnen oder geleert
            self.stand = 0
        if groesse == self.stand:
            return []

        try:
            with self._pfad.open("rb") as datei:
                datei.seek(self.stand)
                roh = datei.read(groesse - self.stand)
        except OSError:
            return []

        letzter_umbruch = roh.rfind(b"\n")
        if letzter_umbruch < 0:
            return []                       # noch keine vollständige Zeile
        vollstaendig = roh[: letzter_umbruch + 1]
        self.stand += len(vollstaendig)

        saetze = []
        for zeile in vollstaendig.decode("utf-8", errors="replace").splitlines():
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                saetze.append(json.loads(zeile))
            except json.JSONDecodeError:
                continue
        return saetze
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_record_tail.py -q`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/record/tail.py tests/test_record_tail.py
git commit -m "feat(record): inkrementelles jsonl-Nachlesen ohne Verlust halber Zeilen"
```

---

## Task 5: Läufe finden und anhalten

**Files:**
- Create: `src/spotlab/workshop/control.py`, `tests/test_control.py`

**Interfaces:**
- Consumes: `spotlab.record.run.STOPP_DATEI`, `spotlab.record.read.read_run`
- Produces:
  - `LEBENSZEICHEN_S = 2.0`
  - `ist_aktiv(run_dir, grenze_s=LEBENSZEICHEN_S, jetzt=None) -> bool`
  - `aktive_laeufe(runs_dir, grenze_s=LEBENSZEICHEN_S) -> list[Path]`
  - `stoppe_freundlich(run_dir) -> None`
  - `beende_hart(run_dir, killer=None) -> bool`
  - `pid_von(run_dir) -> int | None`

**Zwei Entwurfspunkte, die Tests brauchen:**

1. **Lebendigkeit über den Änderungszeitpunkt von `zustand.jsonl`**, nicht über die Prozess-ID. Unter Windows ist `os.kill(pid, 0)` kein Test, sondern beendet den Prozess.
2. **`beende_hart` tötet nur einen Lauf, der noch lebt.** Prozess-IDs werden vom Betriebssystem wiederverwendet; eine gespeicherte ID blind zu töten könnte einen fremden Prozess treffen.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_control.py`

```python
import json
import os
import time

from spotlab.record.run import STOPP_DATEI, RunRecorder
from spotlab.workshop.control import (
    aktive_laeufe,
    beende_hart,
    ist_aktiv,
    pid_von,
    stoppe_freundlich,
)


def _lauf(tmp_path, pid=4711, alter_s=0.0):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.set_robot_info(pid=pid)
    rec.sample({"battery": 90.0})
    if alter_s:
        alt = time.time() - alter_s
        os.utime(rec.dir / "zustand.jsonl", (alt, alt))
    return rec.dir


def test_frischer_lauf_ist_aktiv(tmp_path):
    assert ist_aktiv(_lauf(tmp_path)) is True


def test_alter_lauf_ist_nicht_aktiv(tmp_path):
    assert ist_aktiv(_lauf(tmp_path, alter_s=30.0)) is False


def test_lauf_ohne_zustandsdatei_ist_nicht_aktiv(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    assert ist_aktiv(rec.dir) is False


def test_aktive_laeufe_filtert(tmp_path):
    frisch = _lauf(tmp_path)
    _lauf(tmp_path, alter_s=30.0)
    assert [p.name for p in aktive_laeufe(tmp_path)] == [frisch.name]


def test_aktive_laeufe_bei_fehlendem_ordner(tmp_path):
    assert aktive_laeufe(tmp_path / "gibtsnicht") == []


def test_pid_wird_gelesen(tmp_path):
    assert pid_von(_lauf(tmp_path, pid=1234)) == 1234


def test_pid_fehlt_ergibt_none(tmp_path):
    verzeichnis = tmp_path / "leer"
    verzeichnis.mkdir()
    (verzeichnis / "lauf.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    assert pid_von(verzeichnis) is None


def test_stopp_legt_die_markierung_an(tmp_path):
    verzeichnis = _lauf(tmp_path)
    stoppe_freundlich(verzeichnis)
    assert (verzeichnis / STOPP_DATEI).exists()


def test_stopp_ist_idempotent(tmp_path):
    verzeichnis = _lauf(tmp_path)
    stoppe_freundlich(verzeichnis)
    stoppe_freundlich(verzeichnis)          # darf nicht werfen


def test_hartes_beenden_ruft_den_killer(tmp_path):
    verzeichnis = _lauf(tmp_path, pid=1234)
    getroffen = []
    assert beende_hart(verzeichnis, killer=getroffen.append) is True
    assert getroffen == [1234]


def test_toter_lauf_wird_nicht_getoetet(tmp_path):
    """Prozess-IDs werden wiederverwendet — ein toter Lauf darf niemanden treffen."""
    verzeichnis = _lauf(tmp_path, pid=1234, alter_s=30.0)
    getroffen = []
    assert beende_hart(verzeichnis, killer=getroffen.append) is False
    assert getroffen == []


def test_lauf_ohne_pid_wird_nicht_getoetet(tmp_path):
    verzeichnis = _lauf(tmp_path)
    (verzeichnis / "lauf.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    getroffen = []
    assert beende_hart(verzeichnis, killer=getroffen.append) is False
    assert getroffen == []
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_control.py -q`, erwartet `ModuleNotFoundError`

- [ ] **Step 3: `workshop/control.py` implementieren**

```python
"""Läufe finden und anhalten — ohne Qt, ohne Roboterverbindung.

Zwei Wege, wie im Entwurf festgelegt:

freundlich  Markierung ins Lauf-Verzeichnis; der Abtaster löst daraufhin
            KeyboardInterrupt aus, der Abbau läuft, der Spot setzt sich hin.
hart        Prozess töten; die Keepalives sterben, der Roboter schneidet die
            Motorleistung ab. Ein stehender Spot sackt dabei zusammen — das
            ist die Bedeutung eines Not-Aus, kein Fehler.
"""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from spotlab.record.run import STOPP_DATEI

LEBENSZEICHEN_S = 2.0


def ist_aktiv(run_dir, grenze_s=LEBENSZEICHEN_S, jetzt=None):
    """Lebt der Lauf noch?

    Gemessen am Änderungszeitpunkt von zustand.jsonl, nicht an der Prozess-ID:
    der Abtaster schreibt mit 10 Hz, und unter Windows ist os.kill(pid, 0) kein
    Test, sondern beendet den Prozess.
    """
    zustand = Path(run_dir) / "zustand.jsonl"
    try:
        letzte_aenderung = zustand.stat().st_mtime
    except OSError:
        return False
    return (jetzt or time.time()) - letzte_aenderung <= grenze_s


def aktive_laeufe(runs_dir, grenze_s=LEBENSZEICHEN_S):
    wurzel = Path(runs_dir)
    if not wurzel.is_dir():
        return []
    return sorted(
        (p for p in wurzel.iterdir() if p.is_dir() and ist_aktiv(p, grenze_s)),
        key=lambda p: p.name,
    )


def pid_von(run_dir):
    lauf = Path(run_dir) / "lauf.json"
    try:
        daten = json.loads(lauf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pid = daten.get("pid")
    return int(pid) if isinstance(pid, int) else None


def stoppe_freundlich(run_dir):
    """Markierung anlegen. Der Abtaster des Laufs sieht sie beim nächsten Takt."""
    (Path(run_dir) / STOPP_DATEI).touch()


def _standard_killer(pid):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        os.kill(pid, signal.SIGKILL)


def beende_hart(run_dir, killer=None):
    """Prozess des Laufs töten. Gibt False zurück, wenn nichts zu töten war.

    Getötet wird NUR ein Lauf, der nach ist_aktiv() noch lebt. Prozess-IDs
    werden vom Betriebssystem wiederverwendet; eine gespeicherte ID blind zu
    töten könnte einen fremden Prozess treffen. Die Lebendigkeitsprüfung bindet
    das Zeitfenster auf zwei Sekunden.
    """
    if not ist_aktiv(run_dir):
        return False
    pid = pid_von(run_dir)
    if pid is None:
        return False
    (killer or _standard_killer)(pid)
    return True
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_control.py -q`, erwartet 12 PASS

- [ ] **Step 5: Gesamtsuite** — `pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/workshop/control.py tests/test_control.py
git commit -m "feat(workshop): Laeufe finden, freundlich stoppen, hart beenden"
```

---

*Fortsetzung: `2026-08-07-spotlab-gui-teil2.md` (Tasks 6–17: Qt-Oberfläche, CLI, Kettentest, Doku).*
