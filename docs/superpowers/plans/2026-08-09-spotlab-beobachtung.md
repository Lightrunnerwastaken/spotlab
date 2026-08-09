# Beobachter-Modus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leaseloses Mitschreiben von `RobotState`, während ein Mensch den Spot
mit dem Tablet steuert — damit Kalibrierdaten entstehen können, bevor
Abnahmepunkt A1 (Not-Aus-Koexistenz) durch ist.

**Architecture:** Ein `Beobachtung`-Objekt nach dem Vorbild von
`maps/session.py::RecordingSession`: `verbinde()` liefert einen angemeldeten
Roboter ohne Lease und ohne E-Stop, eine Nur-Lese-`Zustandsquelle` mit genau
einer Methode speist den bestehenden `StateSampler`, und die Aufzeichnung läuft
über den unveränderten `RunRecorder`. Das Messfenster-Protokoll wird aus
`api/spot.py` in ein eigenes Modul gehoben, damit beide Seiten dieselbe
Definition benutzen. Das Drehbuch (welche Abschnitte, welche Tempobänder) lebt
in matura-spot, weil es RESEARCH DECISIONs enthält.

**Tech Stack:** Python 3.11+, bosdyn-client 5.0.1.2, pytest. Keine neuen
Abhängigkeiten.

## Global Constraints

- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von
  `src/spotlab/beobachtung/`.** Dieselbe harte Regel wie bei `maps/`. Ein Test
  prüft das über Importzeilen (`^\s*(from|import)\s+`), nicht über Docstrings —
  Docstring-Treffer waren in diesem Projekt schon zweimal ein Fehlalarm.
- **Python-Bezeichner englisch, Meldungen und Doku deutsch.** Ausnahme wie
  gehabt: Datei- und Feldnamen der Aufzeichnung sind deutsch.
- **Fehlende Messwerte sind `None`, nie 0.**
- **Bestehende Schlüssel in `zustand.jsonl` ändern sich nicht.**
- **`t_robot` wird nicht in Klientenzeit umgerechnet.**
- **Der Abtaster holt nichts nach.**
- Zeitabhängige Funktionen nehmen `schlaf`/`jetzt` als Parameter.
- Tests laufen ohne Roboter und ohne Netz; Qt-Tests mit
  `QT_QPA_PLATFORM=offscreen`.
- Arbeitsverzeichnis für spotlab-Tests: `D:\Users\janis\Documents\Matura\spotlab`.
  Für matura-spot: `D:\Users\janis\Documents\Matura\matura-spot`.

---

## File Structure

**spotlab**

| Datei | Verantwortung |
|---|---|
| `src/spotlab/record/messfenster.py` (neu) | Das Messfenster-Protokoll: Ereignisse schreiben, Abtastrate umschalten, Verschachtelung verbieten. Kennt Recorder und Abtaster, sonst nichts. |
| `src/spotlab/record/sampler.py` (ändern) | Zusätzlich ein begrenzter Ring der letzten Abtastungen plus `verlauf()`. |
| `src/spotlab/api/spot.py` (ändern) | `messfenster` delegiert; Signatur unverändert. |
| `src/spotlab/beobachtung/quelle.py` (neu) | `Zustandsquelle`: eine Methode, `robot_state()`. Der Kern der Sicherheitsaussage. |
| `src/spotlab/beobachtung/session.py` (neu) | `Beobachtung`: verbinden, aufzeichnen, Tempo und Drehrate melden, garantiert abbauen. |
| `tests/test_record_messfenster.py` (neu) | Das herausgelöste Protokoll für sich. |
| `tests/test_beobachtung_quelle.py` (neu) | Sicherheitsaussage und Schichtregel. |
| `tests/test_beobachtung_session.py` (neu) | Lebenszyklus, Tempo, Drehrate. |
| `docs/ABNAHME.md` (ändern) | Neuer Punkt A19. |
| `CLAUDE.md` (ändern) | Zwei neue nicht verhandelbare Regeln. |

**matura-spot**

| Datei | Verantwortung |
|---|---|
| `scripts/beobachten_real.py` (neu) | Das Drehbuch: Abschnitte, Tempobänder, Terminal-Führung, Protokoll. |
| `tests/test_beobachten_real.py` (neu) | Trockenprobe als echter Unterprozess. |

---

## Task 1: Messfenster-Protokoll herauslösen

**Files:**
- Create: `src/spotlab/record/messfenster.py`
- Modify: `src/spotlab/api/spot.py` (Import, `Spot.__init__`, `Spot.messfenster`)
- Test: `tests/test_record_messfenster.py`

**Interfaces:**
- Consumes: `RunRecorder.event(art, **daten)`, `StateSampler.takt()`,
  `StateSampler.setze_takt(hz, reich)`.
- Produces: `spotlab.record.messfenster.Messfenster(recorder, sampler)` mit
  `oeffne(name, hz=50.0, reich=True, **felder)` als Kontextmanager, und
  `spotlab.record.messfenster.RESERVIERT = ("phase", "hz_soll")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_record_messfenster.py
import pytest

from spotlab.record.messfenster import Messfenster


class FakeRecorder:
    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))


class FakeSampler:
    def __init__(self):
        self.hz, self.reich = 10.0, False
        self.verlauf_der_takte = []

    def takt(self):
        return self.hz, self.reich

    def setze_takt(self, hz, reich):
        self.hz, self.reich = hz, reich
        self.verlauf_der_takte.append((hz, reich))


def test_fenster_hebt_die_rate_und_setzt_sie_zurueck():
    rec, abt = FakeRecorder(), FakeSampler()
    with Messfenster(rec, abt).oeffne("G3", hz=50.0):
        assert abt.takt() == (50.0, True)
    assert abt.takt() == (10.0, False)


def test_fenster_schreibt_start_und_ende():
    rec, abt = FakeRecorder(), FakeSampler()
    with Messfenster(rec, abt).oeffne("G3", hz=50.0, stuetzstelle="0.30"):
        pass
    arten = [a for a, _ in rec.ereignisse]
    assert arten == ["messfenster", "messfenster"]
    assert rec.ereignisse[0][1]["phase"] == "start"
    assert rec.ereignisse[0][1]["hz_soll"] == 50.0
    assert rec.ereignisse[0][1]["stuetzstelle"] == "0.30"
    assert rec.ereignisse[1][1]["phase"] == "ende"


def test_ausnahme_setzt_die_rate_trotzdem_zurueck():
    """Ohne finally bliebe der Lauf fuer immer auf 50 Hz."""
    rec, abt = FakeRecorder(), FakeSampler()
    with pytest.raises(ValueError):
        with Messfenster(rec, abt).oeffne("G3"):
            raise ValueError("mittendrin")
    assert abt.takt() == (10.0, False)
    assert rec.ereignisse[-1][1]["phase"] == "ende"


def test_verschachtelung_ist_verboten():
    from spotlab.errors import SpotlabError

    fenster = Messfenster(FakeRecorder(), FakeSampler())
    with fenster.oeffne("aussen"):
        with pytest.raises(SpotlabError, match="aussen"):
            with fenster.oeffne("innen"):
                pass


def test_reservierte_feldnamen_werden_abgewiesen():
    from spotlab.errors import SpotlabError

    fenster = Messfenster(FakeRecorder(), FakeSampler())
    with pytest.raises(SpotlabError, match="phase"):
        with fenster.oeffne("G3", phase="start"):
            pass


def test_ohne_recorder_und_abtaster_laeuft_es_durch():
    """Tests bauen Spot ohne beides; das darf nicht werfen."""
    with Messfenster(None, None).oeffne("G3"):
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_record_messfenster.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.record.messfenster'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/spotlab/record/messfenster.py
"""Das Messfenster-Protokoll — an genau einer Stelle.

Herausgeloest aus api/spot.py, weil die Logik nur an Recorder und Abtaster
haengt und nicht am Roboter: der Beobachter-Modus (beobachtung/session.py)
kommandiert nichts und braucht dasselbe Protokoll. Zwei Formulierungen davon
haetten bedeutet, dass messung/fenster.py bald zwei leicht verschiedene
Fensterprotokolle lesen muss.
"""

import contextlib

from spotlab.errors import SpotlabError

# `name` fehlt hier absichtlich: es ist ein Positionsparameter von oeffne(),
# und Python weist ein doppeltes `name=` schon mit einer klaren Meldung ab.
RESERVIERT = ("phase", "hz_soll")


class Messfenster:
    """Schreibt Fenstermarken und schaltet die Abtastung dichter.

    `recorder` und `sampler` duerfen None sein — Tests bauen Spot so.
    """

    def __init__(self, recorder, sampler):
        self._recorder = recorder
        self._sampler = sampler
        self._offen = None

    @property
    def offen(self):
        return self._offen

    @contextlib.contextmanager
    def oeffne(self, name, hz=50.0, reich=True, **felder):
        doppelt = [k for k in RESERVIERT if k in felder]
        if doppelt:
            raise SpotlabError(
                f"Die Feldnamen {', '.join(doppelt)} sind im Messfenster belegt. "
                "Nimm einen anderen Namen."
            )
        if self._offen is not None:
            raise SpotlabError(
                f"Es ist schon ein Messfenster offen: „{self._offen}“. "
                "Verschachtelte Fenster waeren in der Auswertung nicht "
                "auseinanderzuhalten."
            )

        self._offen = name
        vorher = self._sampler.takt() if self._sampler is not None else None
        if self._recorder is not None:
            self._recorder.event(
                "messfenster", phase="start", name=name, hz_soll=hz, **felder
            )
        if self._sampler is not None:
            self._sampler.setze_takt(hz, reich)
        try:
            yield
        finally:
            # Ohne finally bliebe der Lauf nach einer Ausnahme fuer immer auf
            # 50 Hz und das Fenster ohne Ende.
            if self._sampler is not None and vorher is not None:
                self._sampler.setze_takt(*vorher)
            if self._recorder is not None:
                self._recorder.event("messfenster", phase="ende", name=name, **felder)
            self._offen = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_record_messfenster.py -q`
Expected: PASS (6 Tests)

- [ ] **Step 5: `Spot` auf die neue Stelle umstellen**

In `src/spotlab/api/spot.py`:
- Import ergänzen: `from spotlab.record.messfenster import RESERVIERT, Messfenster`
  und die lokale `RESERVIERT`-Definition samt ihrem Kommentar entfernen (der
  Kommentar wandert mit ins neue Modul; er steht dort schon).
- In `__init__` statt `self._fenster_offen = None`:
  `self._fenster = Messfenster(recorder, sampler)`
- `messfenster` ersetzen durch:

```python
    def messfenster(self, name, hz=50.0, **felder):
        """Markiert ein Messfenster und tastet darin dicht und vollstaendig ab.

        Innerhalb des Blocks laeuft die Abtastung mit `hz` und schreibt den
        vollen Umfang; danach wieder wie zuvor. Die Marken landen als Ereignisse
        in der Aufzeichnung, damit spaeter feststeht, welche Abtastungen zu
        welcher Bedingung gehoeren.

            with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
                spot.walk(vx=0.30, duration=8.0)

        Das Protokoll selbst liegt in record/messfenster.py — der
        Beobachter-Modus benutzt dasselbe.
        """
        return self._fenster.oeffne(name, hz=hz, **felder)
```

Der `@contextlib.contextmanager`-Dekorator an `Spot.messfenster` **entfällt**:
die Methode gibt den fertigen Kontextmanager zurück. `import contextlib` in
`spot.py` bleibt nur, wenn es noch andere Nutzer hat — sonst entfernen.

- [ ] **Step 6: Regression prüfen**

Run: `python -m pytest tests/test_messfenster.py tests/test_api_spot.py tests/test_messung_fenster.py -q`
Expected: PASS, unverändert. Die bestehenden Messfenster-Tests dürfen von der
Verschiebung nichts merken.

- [ ] **Step 7: Delegationstest ergänzen**

```python
# ans Ende von tests/test_record_messfenster.py
def test_spot_delegiert_an_dieselbe_stelle():
    """Sonst gaebe es doch wieder zwei Fensterprotokolle."""
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend

    rec, abt = FakeRecorder(), FakeSampler()
    spot = Spot(DryRunBackend(), recorder=rec, sampler=abt)
    with spot.messfenster("G3", hz=25.0):
        assert abt.takt() == (25.0, True)
    assert [a for a, _ in rec.ereignisse] == ["messfenster", "messfenster"]
```

- [ ] **Step 8: Volle Suite und Commit**

Run: `python -m pytest -q`
Expected: 735 passed + die neuen Tests

```bash
git add src/spotlab/record/messfenster.py src/spotlab/api/spot.py tests/test_record_messfenster.py
git commit -m "refactor(record): Messfenster-Protokoll an genau eine Stelle"
```

---

## Task 2: Ringpuffer im Abtaster

**Files:**
- Modify: `src/spotlab/record/sampler.py`
- Test: `tests/test_sampler.py` (anhängen)

**Interfaces:**
- Consumes: nichts Neues.
- Produces: `StateSampler.verlauf()` → `tuple` der zuletzt geschriebenen
  Abtastungen (älteste zuerst), höchstens `RING` Einträge.
  `spotlab.record.sampler.RING = 512`.

- [ ] **Step 1: Write the failing test**

```python
# ans Ende von tests/test_sampler.py
def test_verlauf_ist_anfangs_leer():
    from spotlab.record.sampler import StateSampler

    abtaster = StateSampler(_backend(), _recorder(), hz=50.0)
    assert abtaster.verlauf() == ()


def test_verlauf_haelt_die_geschriebenen_abtastungen():
    """Die Live-Anzeige liest von hier — ein zweiter Abfragestrom nebenher
    waere eine zweite Wahrheit ueber denselben Roboter."""
    from spotlab.record.sampler import StateSampler

    abtaster = StateSampler(_backend(), _recorder(), hz=50.0)
    for _ in range(3):
        abtaster._einmal()
    verlauf = abtaster.verlauf()
    assert len(verlauf) == 3
    assert all("pose" in s for s in verlauf)


def test_verlauf_ist_begrenzt():
    """Eine lange Sitzung darf nicht den Speicher fuellen."""
    from spotlab.record.sampler import RING, StateSampler

    abtaster = StateSampler(_backend(), _recorder(), hz=50.0)
    for _ in range(RING + 25):
        abtaster._einmal()
    assert len(abtaster.verlauf()) == RING


def test_verlauf_ist_eine_kopie():
    from spotlab.record.sampler import StateSampler

    abtaster = StateSampler(_backend(), _recorder(), hz=50.0)
    abtaster._einmal()
    erste = abtaster.verlauf()
    abtaster._einmal()
    assert len(erste) == 1, "der zurueckgegebene Verlauf hat sich mitveraendert"
```

Die Hilfsfunktionen `_backend()` und `_recorder()` existieren in
`tests/test_sampler.py` bereits oder sind dort nach dem vorhandenen Muster
anzulegen (DryRunBackend mit `power_on()`, RunRecorder auf `tmp_path`). Wenn
sie fehlen, `tmp_path` als Fixture in die Tests aufnehmen.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sampler.py -q -k verlauf`
Expected: FAIL — `AttributeError: 'StateSampler' object has no attribute 'verlauf'`

- [ ] **Step 3: Write minimal implementation**

In `src/spotlab/record/sampler.py`:

```python
import collections   # zu den Importen

# Ring der zuletzt geschriebenen Abtastungen, aus dem die Live-Anzeige des
# Beobachter-Modus liest. Begrenzt nach ANZAHL, ausgewertet wird nach ZEIT —
# sonst haenge die Fensterlaenge an der gerade eingestellten Rate.
RING = 512
```

In `__init__` ergänzen:

```python
        self._ring = collections.deque(maxlen=RING)
        self._ring_sperre = threading.Lock()
```

Die Schleife bekommt einen herausgezogenen Einzelschritt, damit Tests ihn ohne
Thread aufrufen können:

```python
    def _einmal(self, reich=False):
        """Eine Abtastung holen, schreiben und in den Ring legen.

        Gibt True zurueck, wenn es geklappt hat. Die Abtastung darf den Lauf
        nie kippen — deshalb faengt der Aufrufer nichts, sondern liest das Wort.
        """
        try:
            satz = as_sample(self._backend.robot_state(), reich=reich)
        except Exception:
            return False
        self._recorder.sample(satz)
        with self._ring_sperre:
            self._ring.append(satz)
        return True

    def verlauf(self):
        """Kopie der zuletzt geschriebenen Abtastungen, aelteste zuerst."""
        with self._ring_sperre:
            return tuple(self._ring)
```

Und `_schleife` benutzt ihn:

```python
    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            with self._takt_sperre:
                periode, reich = self._periode, self._reich
            self._pruefe_stopp()
            if not self._einmal(reich):
                self._stopp.wait(periode)
                continue
            # Nichts nachholen: dauert die RPC laenger als die Periode, laeuft
            # die Schleife eben langsamer. Nachholen erzeugte Bursts, die in der
            # Auswertung wie echte Dynamik aussehen.
            rest = periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sampler.py -q`
Expected: PASS, inklusive der bestehenden Abtaster-Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/record/sampler.py tests/test_sampler.py
git commit -m "feat(record): Ringpuffer der letzten Abtastungen fuer die Live-Anzeige"
```

---

## Task 3: Nur-Lese-Zustandsquelle

**Files:**
- Create: `src/spotlab/beobachtung/__init__.py` (leer)
- Create: `src/spotlab/beobachtung/quelle.py`
- Test: `tests/test_beobachtung_quelle.py`

**Interfaces:**
- Produces: `spotlab.beobachtung.quelle.Zustandsquelle(state_client)` mit
  `robot_state()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_beobachtung_quelle.py
"""Die Sicherheitsaussage des Beobachter-Modus, als Test.

Der Modus darf den Roboter nicht bewegen koennen. Nicht "soll nicht" —
"kann nicht": die Quelle hat gar keine Kommando-Methode.
"""

import re
from pathlib import Path

from spotlab.beobachtung.quelle import Zustandsquelle

WURZEL = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "beobachtung"

VERBOTEN = (
    "send_command", "power_on", "power_off", "walk", "move", "stand", "sit",
    "stop", "navigate", "upload_map", "localize",
)


class FakeStateClient:
    def __init__(self):
        self.abrufe = 0

    def get_robot_state(self):
        self.abrufe += 1
        return "zustand"


def test_die_quelle_liefert_den_zustand():
    client = FakeStateClient()
    assert Zustandsquelle(client).robot_state() == "zustand"
    assert client.abrufe == 1


def test_die_quelle_hat_keine_kommando_methode():
    oeffentlich = {n for n in dir(Zustandsquelle) if not n.startswith("_")}
    assert oeffentlich == {"robot_state"}, f"unerwartete Oberflaeche: {oeffentlich}"
    for name in VERBOTEN:
        assert not hasattr(Zustandsquelle, name)


def test_kein_lease_und_kein_estop_unter_beobachtung():
    """Dieselbe harte Regel wie bei maps/. Geprueft ueber IMPORTZEILEN --
    ein Treffer im Docstring war hier schon zweimal ein Fehlalarm."""
    muster = re.compile(r"^\s*(from|import)\s+.*(lease|estop)", re.IGNORECASE | re.M)
    for datei in WURZEL.rglob("*.py"):
        text = datei.read_text(encoding="utf-8")
        treffer = muster.findall(text)
        assert not treffer, f"{datei.name} importiert Lease oder E-Stop: {treffer}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_beobachtung_quelle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.beobachtung'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/spotlab/beobachtung/__init__.py
"""Beobachter-Modus: mitschreiben, ohne zu steuern."""
```

```python
# src/spotlab/beobachtung/quelle.py
"""Die Nur-Lese-Zustandsquelle — der Kern der Sicherheitsaussage.

`StateSampler` braucht vom Backend genau eine Methode: `robot_state()`. Diese
Klasse hat genau diese eine. Es gibt hier keine Kommando-Methode, die man
versehentlich aufrufen koennte — das ist staerker als eine Capability-Pruefung,
die erst zur Laufzeit wirft.

Deshalb darf der Beobachter-Modus vor Abnahmepunkt A1 benutzt werden: er nimmt
dem Tablet nichts weg und kann den Roboter nicht bewegen.
"""


class Zustandsquelle:
    def __init__(self, state_client):
        self._state = state_client

    def robot_state(self):
        return self._state.get_robot_state()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_beobachtung_quelle.py -q`
Expected: PASS (3 Tests)

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/beobachtung/ tests/test_beobachtung_quelle.py
git commit -m "feat(beobachtung): Nur-Lese-Zustandsquelle"
```

---

## Task 4: Beobachtungs-Sitzung und Lebenszyklus

**Files:**
- Create: `src/spotlab/beobachtung/session.py`
- Test: `tests/test_beobachtung_session.py`

**Interfaces:**
- Consumes: `Zustandsquelle`, `Messfenster`, `RunRecorder`, `StateSampler`,
  `spotlab.backends.real.verbindung.verbinde(cfg, robot_bauen=None, passwort_lesen=None)`.
- Produces:
  - `Beobachtung(quelle, recorder, sampler)`
  - `Beobachtung.connect(cfg, runs_dir=None, verbinder=None)` → `Beobachtung`
  - `Beobachtung.trocken(runs_dir=None)` → `Beobachtung`
  - `__enter__`/`__exit__`, `messfenster(name, hz=50.0, **felder)`,
    `zustand()`, `beende(ergebnis="ok", fehler=None)`
  - `Beobachtung.lauf_verzeichnis` → `Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_beobachtung_session.py
import json

import pytest

from spotlab.beobachtung.session import Beobachtung


def test_trockene_sitzung_zeichnet_auf(tmp_path):
    with Beobachtung.trocken(runs_dir=tmp_path) as b:
        with b.messfenster("B1-Stand", hz=50.0, regler="MEDIUM"):
            pass
    lauf = json.loads(next(tmp_path.glob("*/lauf.json")).read_text(encoding="utf-8"))
    assert lauf["backend"] == "beobachter"
    assert lauf["ergebnis"] == "ok"


def test_der_abtaster_wird_garantiert_gestoppt(tmp_path):
    b = Beobachtung.trocken(runs_dir=tmp_path)
    with b:
        pass
    assert b.sampler._thread is None


def test_eine_ausnahme_schliesst_den_lauf_trotzdem_ab(tmp_path):
    with pytest.raises(ValueError):
        with Beobachtung.trocken(runs_dir=tmp_path):
            raise ValueError("mittendrin")
    lauf = json.loads(next(tmp_path.glob("*/lauf.json")).read_text(encoding="utf-8"))
    assert lauf["ergebnis"] == "fehler"
    assert "mittendrin" in (lauf["fehler"] or "")


def test_strg_c_wird_als_abgebrochen_verbucht(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        with Beobachtung.trocken(runs_dir=tmp_path):
            raise KeyboardInterrupt()
    lauf = json.loads(next(tmp_path.glob("*/lauf.json")).read_text(encoding="utf-8"))
    assert lauf["ergebnis"] == "abgebrochen"


def test_connect_holt_weder_lease_noch_estop(tmp_path):
    """Der ganze Grund, warum das Werkzeug vor A1 benutzbar ist."""
    from spotlab.config import Config

    gerufen = []

    class FakeRobot:
        def ensure_client(self, name):
            gerufen.append(name)
            return object()

    b = Beobachtung.connect(
        Config(ip="1.2.3.4", username="u"),
        runs_dir=tmp_path,
        verbinder=lambda cfg: FakeRobot(),
    )
    b.beende()
    assert all("lease" not in n.lower() and "estop" not in n.lower() for n in gerufen), gerufen


def test_messfenster_landet_in_den_ereignissen(tmp_path):
    with Beobachtung.trocken(runs_dir=tmp_path) as b:
        with b.messfenster("B2-Fahrt", hz=50.0, ziel_m_s="0.12"):
            pass
        verzeichnis = b.lauf_verzeichnis
    zeilen = (verzeichnis / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    fenster = [json.loads(z) for z in zeilen if json.loads(z)["art"] == "messfenster"]
    assert [f["daten"]["phase"] for f in fenster] == ["start", "ende"]
    assert fenster[0]["daten"]["ziel_m_s"] == "0.12"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_beobachtung_session.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.beobachtung.session'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/spotlab/beobachtung/session.py
"""Eine Beobachtungssitzung: mitschreiben, waehrend ein Mensch steuert.

Aufgebaut wie maps/session.py::RecordingSession — `verbinde()` liefert einen
angemeldeten, zeitsynchronen Roboter OHNE Lease und OHNE E-Stop-Endpunkt.
Deshalb steht dieses Werkzeug nicht hinter Abnahmepunkt A1: es nimmt dem Tablet
nichts weg und kann den Roboter nicht bewegen.

Darum herum die unveraenderte Aufzeichnungsmaschinerie: RunRecorder,
StateSampler, Messfenster. Nichts davon wird hier nachgebaut — zwei Stellen mit
den kalibrierkritischen Zeitregeln waeren eine zu viel.
"""

import math

from spotlab.beobachtung.quelle import Zustandsquelle
from spotlab.record.messfenster import Messfenster
from spotlab.record.run import RunRecorder
from spotlab.record.sampler import StateSampler

BACKEND_NAME = "beobachter"
ABTASTRATE_HZ = 10.0        # ausserhalb der Messfenster, wie bei spotlab.connect()

# Zeitfenster der Live-Zahlen. Nach ZEIT ausgewaehlt, nicht nach Anzahl —
# damit die Zahl unabhaengig von der eingestellten Abtastrate ist.
LIVE_FENSTER_S = 2.0
LIVE_MINDESTPUNKTE = 4


class Beobachtung:
    def __init__(self, quelle, recorder, sampler):
        self.quelle = quelle
        self.recorder = recorder
        self.sampler = sampler
        self._fenster = Messfenster(recorder, sampler)
        self._beendet = False

    # ----------------------------------------------------------- Aufbau

    @classmethod
    def connect(cls, cfg, runs_dir=None, verbinder=None, skript=None):
        """Leaselos verbinden und aufzeichnen.

        `verbinde()` prueft SPOTLAB_NUR_TROCKEN mit — ein Agent kann also auch
        keinen Beobachter auf den echten Roboter loslassen.
        """
        from bosdyn.client.robot_state import RobotStateClient

        from spotlab.backends.real.verbindung import verbinde

        robot = (verbinder or verbinde)(cfg)
        quelle = Zustandsquelle(
            robot.ensure_client(RobotStateClient.default_service_name)
        )
        return cls._bauen(quelle, runs_dir, skript)

    @classmethod
    def trocken(cls, runs_dir=None, skript=None):
        """Ohne Roboter. DryRunBackend hat robot_state() und plausible Werte."""
        from spotlab.backends.dryrun import DryRunBackend

        return cls._bauen(DryRunBackend(), runs_dir, skript)

    @classmethod
    def _bauen(cls, quelle, runs_dir, skript):
        from pathlib import Path

        ziel = Path(runs_dir) if runs_dir else Path.cwd() / "runs"
        recorder = RunRecorder(ziel, skript, backend=BACKEND_NAME)
        sampler = StateSampler(quelle, recorder, hz=ABTASTRATE_HZ)
        sitzung = cls(quelle, recorder, sampler)
        recorder.event("verbunden", backend=BACKEND_NAME)
        sampler.start()
        return sitzung

    @property
    def lauf_verzeichnis(self):
        return self.recorder.dir

    # ----------------------------------------------------------- Betrieb

    def messfenster(self, name, hz=50.0, **felder):
        """Wie `Spot.messfenster` — dieselbe Definition, dasselbe Modul."""
        return self._fenster.oeffne(name, hz=hz, **felder)

    def zustand(self):
        """Die zuletzt geschriebene Abtastung, oder None."""
        verlauf = self.sampler.verlauf()
        return verlauf[-1] if verlauf else None

    # ----------------------------------------------------------- Abbau

    def beende(self, ergebnis="ok", fehler=None):
        """Abtaster stoppen und Lauf abschliessen. Laeuft immer durch."""
        if self._beendet:
            return
        self._beendet = True
        self.recorder.abbau_beginnt()
        try:
            self.sampler.stop()
        finally:
            self.recorder.finish(ergebnis, fehler)

    def __enter__(self):
        return self

    def __exit__(self, art, wert, spur):
        if art is None:
            self.beende("ok")
        elif issubclass(art, KeyboardInterrupt):
            self.beende("abgebrochen", "Vom Benutzer abgebrochen (Ctrl-C)")
        else:
            self.beende("fehler", f"{art.__name__}: {wert}")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_beobachtung_session.py -q`
Expected: PASS (6 Tests)

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/beobachtung/session.py tests/test_beobachtung_session.py
git commit -m "feat(beobachtung): leaselose Sitzung mit garantiertem Abbau"
```

---

## Task 5: Live-Tempo und Drehrate

**Files:**
- Modify: `src/spotlab/beobachtung/session.py`
- Test: `tests/test_beobachtung_session.py` (anhängen)

**Interfaces:**
- Produces: `Beobachtung.tempo()` → `float` (m/s) oder `None`,
  `Beobachtung.drehrate()` → `float` (rad/s) oder `None`.

- [ ] **Step 1: Write the failing test**

```python
# ans Ende von tests/test_beobachtung_session.py
import math


class _Verlauf:
    """Ein Abtaster, der nur einen vorgegebenen Verlauf liefert."""

    def __init__(self, saetze):
        self._saetze = tuple(saetze)
        self._thread = None

    def verlauf(self):
        return self._saetze

    def takt(self):
        return 50.0, True

    def setze_takt(self, hz, reich):
        pass

    def stop(self, timeout=2.0):
        pass


def _satz(t, x=0.0, y=0.0, yaw=0.0):
    return {"t_robot": t, "pose": [x, y, yaw]}


def _sitzung(saetze):
    return Beobachtung(quelle=None, recorder=None, sampler=_Verlauf(saetze))


def test_tempo_ist_weg_durch_zeit():
    saetze = [_satz(t / 50.0, x=0.2 * (t / 50.0)) for t in range(100)]
    assert _sitzung(saetze).tempo() == pytest.approx(0.2, abs=0.005)


def test_tempo_nimmt_den_betrag_nicht_die_x_komponente():
    """Beim Tablet-Fahren liegt die Fahrtrichtung nicht auf der odom-x-Achse."""
    saetze = [
        _satz(t / 50.0, x=0.12 * (t / 50.0), y=0.16 * (t / 50.0)) for t in range(100)
    ]
    assert _sitzung(saetze).tempo() == pytest.approx(0.2, abs=0.005)


def test_tempo_waehlt_nach_zeit_nicht_nach_anzahl():
    """Bei 10 Hz umfassen 125 Eintraege 12 s — ein Tempo darueber waere falsch."""
    langsam = [_satz(t / 10.0, x=0.0) for t in range(30)]          # 3 s Stillstand
    schnell = [_satz(3.0 + t / 10.0, x=0.3 * (t / 10.0)) for t in range(1, 21)]
    tempo = _sitzung(langsam + schnell).tempo()
    assert tempo == pytest.approx(0.3, abs=0.02)


def test_tempo_ohne_genug_punkte_ist_none():
    assert _sitzung([_satz(0.0), _satz(0.02)]).tempo() is None
    assert _sitzung([]).tempo() is None


def test_drehrate_summiert_ueber_den_umschlag_hinweg():
    """2.5 Umdrehungen sind 2.5 Umdrehungen, nicht der Rest modulo 2 pi."""
    dauer, umdrehungen = 2.0, 2.5
    n = 200
    saetze = [
        _satz(
            dauer * i / n,
            yaw=(umdrehungen * 2 * math.pi * i / n + math.pi) % (2 * math.pi) - math.pi,
        )
        for i in range(n + 1)
    ]
    erwartet = umdrehungen * 2 * math.pi / dauer
    assert _sitzung(saetze).drehrate() == pytest.approx(erwartet, rel=0.02)


def test_ohne_zeitstempel_gibt_es_keine_zahl():
    """Fehlende Messwerte sind None, nie 0."""
    saetze = [{"pose": [0.0, 0.0, 0.0]} for _ in range(10)]
    sitzung = _sitzung(saetze)
    assert sitzung.tempo() is None
    assert sitzung.drehrate() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_beobachtung_session.py -q -k "tempo or drehrate or zeitstempel"`
Expected: FAIL — `AttributeError: 'Beobachtung' object has no attribute 'tempo'`

- [ ] **Step 3: Write minimal implementation**

In `src/spotlab/beobachtung/session.py`, im Abschnitt „Betrieb":

```python
    def _live_punkte(self):
        """(t_robot, x, y, yaw) der letzten LIVE_FENSTER_S, oder leere Liste.

        Zeitbasis ist die ROBOTERUHR: fuer Abstaende innerhalb eines Laufs zaehlt
        sie, und die Latenz der Klientenuhr gehoert nicht in eine Geschwindigkeit.
        """
        punkte = []
        for satz in self.sampler.verlauf():
            t, pose = satz.get("t_robot"), satz.get("pose")
            if t is None or not pose or len(pose) < 3:
                continue
            punkte.append((float(t), float(pose[0]), float(pose[1]), float(pose[2])))
        if len(punkte) < LIVE_MINDESTPUNKTE:
            return []
        ende = punkte[-1][0]
        drin = [p for p in punkte if ende - p[0] <= LIVE_FENSTER_S]
        return drin if len(drin) >= LIVE_MINDESTPUNKTE else []

    def tempo(self):
        """Bodengeschwindigkeit in m/s ueber die letzten Sekunden, oder None.

        BETRAG, nicht x-Komponente: beim Tablet-Fahren liegt die Fahrtrichtung
        nicht auf der odom-x-Achse. Der Sim misst dp[0]/dt entlang seiner
        Fahrtrichtung — beide Zahlen sind nur bei GERADEAUSFAHRT dasselbe.
        Deshalb steht „geradeaus, nicht lenken" in jedem Fahrt-Abschnitt des
        Drehbuchs.
        """
        drin = self._live_punkte()
        if not drin:
            return None
        dt = drin[-1][0] - drin[0][0]
        if dt <= 0:
            return None
        return math.hypot(drin[-1][1] - drin[0][1], drin[-1][2] - drin[0][2]) / dt

    def drehrate(self):
        """Gierrate in rad/s, aus dem AUFSUMMIERTEN Winkel — oder None.

        Eine Endwert-Differenz mit Umschlag bei ±pi zeigte eine Drehung von
        2 pi + x als x an; ein viel zu schnell drehender Roboter saehe perfekt aus.
        """
        drin = self._live_punkte()
        if not drin:
            return None
        dt = drin[-1][0] - drin[0][0]
        if dt <= 0:
            return None
        summe = 0.0
        for erst, zweit in zip(drin, drin[1:]):
            summe += (zweit[3] - erst[3] + math.pi) % (2 * math.pi) - math.pi
        return summe / dt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_beobachtung_session.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/beobachtung/session.py tests/test_beobachtung_session.py
git commit -m "feat(beobachtung): Live-Tempo und Drehrate aus dem Abtaster-Ring"
```

---

## Task 6: Das Drehbuch in matura-spot

**Files:**
- Create: `matura-spot/scripts/beobachten_real.py`
- Test: `matura-spot/tests/test_beobachten_real.py`

**Interfaces:**
- Consumes: `spotlab.beobachtung.session.Beobachtung` mit `connect`, `trocken`,
  `messfenster`, `tempo`, `drehrate`, `lauf_verzeichnis`, `beende`.
- Produces: `out/beobachtung/<lauf-id>/protokoll_beobachtung.json`.

**Wichtig:** Die Tempobänder sind RESEARCH DECISIONs und gehören als solche
markiert. Werte aus der Sim-Messung vom 09.08.2026: erreichte Geschwindigkeiten
0.051 / 0.115 / 0.165 / 0.213 m/s; erreichte Gierraten rund 0.22 und 0.31 rad/s.

- [ ] **Step 1: Write the failing test**

```python
# matura-spot/tests/test_beobachten_real.py
"""Die Trockenprobe des Beobachter-Drehbuchs — echter Unterprozess.

Attrappen-Tests pruefen nur, dass die richtigen Argumente gebaut werden. Ob das
Skript wirklich durchlaeuft, zeigt erst ein echter Start — und das muss es,
bevor jemand mit dem Spot in der Halle steht.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
SPOTLAB_SRC = WURZEL.parent / "spotlab" / "src"
HAT_SPOTLAB = importlib.util.find_spec("spotlab") is not None or SPOTLAB_SRC.is_dir()

pytestmark = pytest.mark.skipif(not HAT_SPOTLAB, reason="spotlab nicht verfügbar")


def test_trockenprobe_faehrt_das_drehbuch_durch(tmp_path):
    umgebung = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(WURZEL / "src"), str(SPOTLAB_SRC)]),
        "PYTHONUTF8": "1",
    }
    ergebnis = subprocess.run(
        [sys.executable, str(WURZEL / "scripts" / "beobachten_real.py"),
         "--trocken", "--out", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=umgebung, timeout=120,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr

    protokoll = json.loads(
        next(tmp_path.glob("*/protokoll_beobachtung.json")).read_text(encoding="utf-8")
    )
    assert protokoll["umgebung"]["kommandiert"] is False
    assert protokoll["umgebung"]["quelle"] == "trocken"
    ids = [a["id"] for a in protokoll["abschnitte"]]
    assert ids[:3] == ["B1", "B2", "B3"]
    # Jeder Fahrt-Abschnitt traegt sein Zielband als ABSICHT, nicht als Sollwert.
    fahrt = next(a for a in protokoll["abschnitte"] if a["id"] == "B2")
    assert fahrt["spiegelt"] == "G3"
    assert all("ziel_m_s" in f["stuetzstelle"] for f in fahrt["fenster"])


def test_das_drehbuch_nennt_die_gespiegelten_gates():
    from spotsim.gates import GATES_BY_ID

    modul = _modul()
    for abschnitt in modul.ABSCHNITTE:
        if abschnitt.spiegelt is not None:
            assert abschnitt.spiegelt in GATES_BY_ID, abschnitt.spiegelt


def test_kein_fahrt_abschnitt_ohne_geradeaus_hinweis():
    """tempo() misst den Betrag, der Sim die x-Komponente. Gleich sind sie nur
    bei Geradeausfahrt -- das MUSS in der Anweisung stehen."""
    modul = _modul()
    for abschnitt in modul.ABSCHNITTE:
        if abschnitt.spiegelt in ("G2", "G3"):
            assert "geradeaus" in abschnitt.anweisung.lower(), abschnitt.id


def _modul():
    spec = importlib.util.spec_from_file_location(
        "beobachten_real", WURZEL / "scripts" / "beobachten_real.py"
    )
    modul = importlib.util.module_from_spec(spec)
    for pfad in (str(WURZEL / "src"), str(SPOTLAB_SRC)):
        if pfad not in sys.path:
            sys.path.insert(0, pfad)
    spec.loader.exec_module(modul)
    return modul
```

- [ ] **Step 2: Run test to verify it fails**

Run (aus `matura-spot`): `python -m pytest tests/test_beobachten_real.py -q`
Expected: FAIL — Skript existiert nicht

- [ ] **Step 3: Write the script**

`matura-spot/scripts/beobachten_real.py` mit:

- Modul-Docstring: Zweck, Sicherheitshinweis (leaselos, aber der Spot fährt
  trotzdem — Aufsicht nötig), Bedienung durch zwei Personen.
- `@dataclass(frozen=True) class Abschnitt:` mit `id`, `titel`, `spiegelt`,
  `anweisung`, `freiraum`, `art` (`"stand"`, `"fahrt"`, `"drehen"`, `"stoss"`,
  `"sensorik"`, `"frei"`), `ziel` (float oder None).
- `ABSCHNITTE`-Tupel mit B1…B6 gemäss Spec-Tabelle, Tempobänder
  `0.05 / 0.12 / 0.17 / 0.21` und Drehbänder `0.22 / 0.31`, jeweils als
  eigener `Abschnitt` mit `ziel`.
- `_frage(text)` wie in `gates_real.py` (Enter / n / x).
- `_regler(vorgabe)` — fragt Gangart und `swing_height`, vorbelegt.
- `_LiveAnzeige` — Thread, schreibt zweimal pro Sekunde
  `f"  {tempo:.3f} m/s (Ziel {ziel:.2f} ± {TOLERANZ})"` bzw. `"  —"` wenn
  `tempo()` None liefert; `stop()` setzt ein Event.
- `fahre_abschnitt(b, abschnitt, regler)` — Fenster öffnen, Anzeige starten,
  `input()` abwarten, Anzeige stoppen, Fenster schliessen.
- `_protokoll(...)` — schreibt nach **jedem** Abschnitt neu (Befund S3.1: ein
  Abbruch darf die von Hand eingetippten Impulse nicht vernichten).
- `main()` mit `--trocken`, `--out`, `--zeitraffer`, `--nur B2,B4`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_beobachten_real.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/beobachten_real.py tests/test_beobachten_real.py
git commit -m "feat: Beobachter-Drehbuch fuer die Messfahrt mit dem Tablet"
```

---

## Task 7: Abnahme und Regeln

**Files:**
- Modify: `spotlab/docs/ABNAHME.md` (neuer Punkt A19)
- Modify: `spotlab/CLAUDE.md` (zwei Regeln)
- Modify: `spotlab/docs/HAERTUNG.md` (Stand)

- [ ] **Step 1: A19 schreiben**

Neuer Abschnitt am Ende von `docs/ABNAHME.md`, vor „Nach der Abnahme":

```markdown
## A19 — Beobachtungssitzung

**Warum dieser Punkt vor A1 kommen darf** Der Beobachter holt kein Lease und
registriert keinen E-Stop-Endpunkt. Er kann den Roboter nicht bewegen. Genau
das ist hier zu BEWEISEN, nicht anzunehmen.

**Prozedur**
1. `python scripts/beobachten_real.py` starten (matura-spot), Abschnitt B1.
2. Von einem zweiten Rechner: `spotlab lease` — muss `frei` melden.
3. Von einem zweiten Rechner: `spotlab doctor` — Stufe „Not-Aus-Endpunkt" muss
   `kein 'spotlab'-Endpunkt in der Konfiguration` melden.
4. Mit dem Tablet fahren, Abschnitt B2, Zielband 0.17 m/s halten.
5. Strg-C mitten in einem Abschnitt.

**Erwartung** (2) und (3) beweisen die Leaselosigkeit. (4): die Live-Anzeige ist
aus zwei Metern lesbar und folgt der Zahl, die hinterher unter `messwerte`
steht. (5): der Lauf ist sauber abgeschlossen, `protokoll_beobachtung.json`
enthält die bis dahin gefahrenen Abschnitte samt eingetippter Impulse.

**Notieren** Ob sich ein Zielband überhaupt halten lässt — davon hängt ab, ob
die Bänder taugen oder ob die Auswertung breiter binnen muss.

**Ergebnis** _(offen)_
```

- [ ] **Step 2: CLAUDE.md ergänzen**

Bei „Nicht verhandelbar":

```markdown
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von
  `src/spotlab/beobachtung/`.** Dieselbe Regel wie bei `maps/`, und sie ist der
  ganze Grund, warum der Beobachter-Modus vor Abnahmepunkt A1 benutzbar ist:
  er nimmt dem Tablet nichts weg und kann den Roboter nicht bewegen.
  `Zustandsquelle` hat genau eine Methode — es gibt gar nichts zu missbrauchen.
- **Das Messfenster-Protokoll steht in `record/messfenster.py`, an genau einer
  Stelle.** `api/spot.py` und `beobachtung/session.py` delegieren beide dorthin.
  Zwei Formulierungen hiessen, dass `messung/fenster.py` bald zwei leicht
  verschiedene Fensterprotokolle lesen muss.
```

- [ ] **Step 3: Volle Suiten**

Run (spotlab): `python -m pytest -q`
Run (matura-spot): `python -m pytest -q`
Expected: beide grün

- [ ] **Step 4: Commit**

```bash
git add docs/ABNAHME.md CLAUDE.md docs/HAERTUNG.md
git commit -m "docs: A19 Beobachtungssitzung, Regeln fuer beobachtung/"
```

---

## Self-Review

**Spec coverage**

| Spec-Abschnitt | Task |
|---|---|
| `record/messfenster.py` herauslösen | 1 |
| Ringpuffer im Abtaster | 2 |
| `Zustandsquelle` + Sicherheitsaussage + Schichtregel | 3 |
| `Beobachtung` Lebenszyklus, `trocken()`, `backend: "beobachter"` | 4 |
| `SPOTLAB_NUR_TROCKEN` gilt automatisch | 4 (Test `test_connect_holt_weder_lease_noch_estop` deckt den Pfad; die Schranke selbst ist in `tests/test_schranke.py` bereits abgedeckt) |
| Live-Zahlen, Zeitbasis, Betrag, Umschlag | 5 |
| Drehbuch, Bänder, Regler, Protokoll, Zwischenspeichern | 6 |
| A19, CLAUDE.md | 7 |

**Offen gelassen, bewusst:** der Vergleich gegen den Sim über die neue x-Achse.
Die Spec grenzt ihn ausdrücklich als eigenen Schritt ab.

**Type consistency geprüft:** `Messfenster.oeffne` heisst in Task 1, 4 und 5
gleich; `verlauf()` in Task 2 und 5; `tempo()`/`drehrate()` in Task 5 und 6;
`lauf_verzeichnis` in Task 4 und 6.
