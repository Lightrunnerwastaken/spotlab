# spotlab GraphNav — Implementierungsplan, Teil 2 (Verben, GUI, CLI)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Fortsetzung von `2026-08-07-spotlab-graphnav.md`. **Global Constraints** von dort gelten unverändert weiter.

**Umfang:** Tasks 7–12 — Schülerverben, Draufsicht, Ansicht „Karten", Fensterverdrahtung, Kommandozeile, Doku und Abnahme.

---

## Task 7: Die Schülerverben

**Files:**
- Create: `src/spotlab/api/navigation.py`, `tests/test_api_navigation.py`
- Modify: `src/spotlab/backends/real/session.py`, `src/spotlab/api/spot.py`

**Interfaces:**
- Consumes: `Capability.GRAPH_NAV`, `require`, `NavStatus`, `store.finde`, `store.lade_graph`, `NavigationError`
- Produces:
  - `Map(name: str, dir: Path, graph)` mit `.waypoints -> list[str]` und `.id_fuer(name) -> str`
  - `load_map(backend, recorder, workspace, name=None, active=None) -> Map`
  - `localize(backend, recorder) -> str`
  - `navigate_to(backend, recorder, karte, ziel, limits, timeout=120.0, schlaf=time.sleep, jetzt=time.monotonic) -> None`
  - `NACHSENDE_INTERVALL_S = 0.5`, `KOMMANDO_GUELTIGKEIT_S = 1.5`
- `RealSpot` bekommt **durchreichende Methoden** — hier, weil erst `api/navigation.py` sie braucht und `api/` nicht direkt in `backends/real/` greifen soll:
  `upload_map(kartenordner)`, `localize()`, `travel_params(limits)`, `navigate_step(waypoint_id, dauer_s, params, command_id=None)`, `navigation_status(command_id)`
- `Spot` bekommt `load_map(name=None)`, `localize()`, `navigate_to(ziel, timeout=120.0)`, `waypoints()`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_api_navigation.py`

```python
import pytest
from bosdyn.api.graph_nav import map_pb2

from spotlab.api.navigation import Map, load_map, localize, navigate_to
from spotlab.backends.base import Capability, NavStatus
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits
from spotlab.errors import NavigationError, SpotlabError, UnsupportedCapability
from spotlab.maps.store import karten_wurzel, speichere_metadaten


def _graph():
    graph = map_pb2.Graph()
    for kennung, name in (("wp0", "start"), ("wp1", "kueche")):
        wp = graph.waypoints.add()
        wp.id = kennung
        wp.annotations.name = name
    kante = graph.edges.add()
    kante.id.from_waypoint = "wp0"
    kante.id.to_waypoint = "wp1"
    return graph


def _karte_auf_platte(tmp_path, name="turnhalle"):
    ordner = karten_wurzel(tmp_path) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph().SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph())
    return ordner


class FakeBackend(DryRunBackend):
    """Trockenlauf plus GraphNav — das Attrappen-Gegenstück zu RealSpot."""

    def __init__(self, folge=None):
        super().__init__()
        self.power_on()
        self.protokoll = []
        self.letzte_params = None
        self._folge = list(folge or [])
        self._abrufe = 0

    def capabilities(self):
        return super().capabilities() | Capability.GRAPH_NAV

    def upload_map(self, kartenordner):
        self.protokoll.append(f"upload:{kartenordner.name}")
        return _graph()

    def localize(self):
        self.protokoll.append("localize")
        return "wp0"

    def travel_params(self, limits):
        self.letzte_params = limits
        return f"params({limits.max_speed})"

    def navigate_step(self, waypoint_id, dauer_s, params, command_id=None):
        self.protokoll.append(f"nav:{waypoint_id}")
        return 7

    def navigation_status(self, command_id):
        self._abrufe += 1
        if self._folge:
            return self._folge.pop(0)
        return NavStatus(fertig=True, status="Angekommen.", gescheitert=False)


def test_karte_wird_geladen_und_beschrieben(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = FakeBackend()
    karte = load_map(backend, None, tmp_path, "turnhalle")
    assert isinstance(karte, Map)
    assert karte.name == "turnhalle"
    assert sorted(karte.waypoints) == ["kueche", "start"]
    assert "upload:turnhalle" in backend.protokoll


def test_ohne_argument_wird_die_aktive_karte_genommen(tmp_path):
    _karte_auf_platte(tmp_path, "aula")
    karte = load_map(FakeBackend(), None, tmp_path, None, active="aula")
    assert karte.name == "aula"


def test_ohne_argument_und_ohne_aktive_karte_klarer_fehler(tmp_path):
    _karte_auf_platte(tmp_path, "aula")
    with pytest.raises(SpotlabError) as info:
        load_map(FakeBackend(), None, tmp_path, None, active="")
    assert "aula" in str(info.value)


def test_ohne_arbeitsordner_klarer_fehler():
    with pytest.raises(SpotlabError) as info:
        load_map(FakeBackend(), None, None, "turnhalle")
    assert "Arbeitsordner" in str(info.value)


def test_namen_werden_zu_wegpunkt_ids(tmp_path):
    _karte_auf_platte(tmp_path)
    karte = load_map(FakeBackend(), None, tmp_path, "turnhalle")
    assert karte.id_fuer("kueche") == "wp1"


def test_unbekannter_wegpunkt_zaehlt_die_vorhandenen_auf(tmp_path):
    _karte_auf_platte(tmp_path)
    karte = load_map(FakeBackend(), None, tmp_path, "turnhalle")
    with pytest.raises(SpotlabError) as info:
        karte.id_fuer("keller")
    assert "start" in str(info.value) and "kueche" in str(info.value)


def test_lokalisieren_reicht_durch():
    backend = FakeBackend()
    assert localize(backend, None) == "wp0"
    assert "localize" in backend.protokoll


def test_fahrt_erreicht_das_ziel(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = FakeBackend()
    karte = load_map(backend, None, tmp_path, "turnhalle")
    navigate_to(backend, None, karte, "kueche", Limits(),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert "nav:wp1" in backend.protokoll


def test_der_geschwindigkeitsdeckel_landet_in_den_params(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = FakeBackend()
    karte = load_map(backend, None, tmp_path, "turnhalle")
    navigate_to(backend, None, karte, "kueche", Limits(max_speed=0.25),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert backend.letzte_params.max_speed == 0.25


def test_kommando_wird_nachgesendet(tmp_path):
    """Navigationskommandos verfallen — wie Geschwindigkeitskommandos."""
    _karte_auf_platte(tmp_path)
    unterwegs = NavStatus(fertig=False, status="Unterwegs.", gescheitert=False)
    backend = FakeBackend(folge=[unterwegs, unterwegs])
    karte = load_map(backend, None, tmp_path, "turnhalle")
    navigate_to(backend, None, karte, "kueche", Limits(),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert backend.protokoll.count("nav:wp1") >= 3


def test_verloren_bricht_mit_klartext_ab(tmp_path):
    _karte_auf_platte(tmp_path)
    verloren = NavStatus(fertig=False, status="Der Spot hat sich verloren.",
                         gescheitert=True)
    backend = FakeBackend(folge=[verloren])
    karte = load_map(backend, None, tmp_path, "turnhalle")
    with pytest.raises(NavigationError) as info:
        navigate_to(backend, None, karte, "kueche", Limits(),
                    schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert "verloren" in str(info.value)


def test_zeitueberschreitung_meldet_klartext(tmp_path):
    _karte_auf_platte(tmp_path)
    unterwegs = NavStatus(fertig=False, status="Unterwegs.", gescheitert=False)
    backend = FakeBackend(folge=[unterwegs] * 50)
    karte = load_map(backend, None, tmp_path, "turnhalle")
    uhr = iter([0.0, 0.0, 5.0, 500.0, 900.0])
    with pytest.raises(NavigationError) as info:
        navigate_to(backend, None, karte, "kueche", Limits(), timeout=10.0,
                    schlaf=lambda _: None, jetzt=lambda: next(uhr))
    assert "10" in str(info.value)


def test_ohne_graph_nav_klare_verweigerung(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = DryRunBackend()
    backend.power_on()
    with pytest.raises(UnsupportedCapability):
        load_map(backend, None, tmp_path, "turnhalle")


def test_ereignisse_werden_aufgezeichnet(tmp_path):
    from spotlab.record.run import RunRecorder

    _karte_auf_platte(tmp_path)
    rec = RunRecorder(tmp_path / "runs", None, backend="test")
    backend = FakeBackend()
    karte = load_map(backend, rec, tmp_path, "turnhalle")
    navigate_to(backend, rec, karte, "kueche", Limits(),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    rec.finish("ok")
    text = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert "load_map" in text and "navigate_to" in text
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_api_navigation.py -q`

- [ ] **Step 3: `api/navigation.py` implementieren**

```python
"""Auf einer Karte fahren.

Die Verben laufen im Schülerskript, nicht in der GUI: der Roboter bewegt sich
autonom, also braucht es Lease und Not-Aus — dieselbe Regel wie für move().

Zwei Dinge nimmt die Bibliothek dem Schüler ab, die im SDK-Beispiel jedes Mal
von Hand stehen: das Nachsenden (Navigationskommandos verfallen) und der
Geschwindigkeitsdeckel aus config.toml.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from spotlab.backends.base import Capability, require
from spotlab.errors import NavigationError, SpotlabError
from spotlab.maps.store import finde, karten, lade_graph

NACHSENDE_INTERVALL_S = 0.5
KOMMANDO_GUELTIGKEIT_S = 1.5


@dataclass(frozen=True)
class Map:
    name: str
    dir: Path
    graph: object

    @property
    def waypoints(self):
        """Die bei der Aufnahme gesetzten Namen."""
        return [wp.annotations.name for wp in self.graph.waypoints if wp.annotations.name]

    def id_fuer(self, name):
        for wp in self.graph.waypoints:
            if wp.annotations.name == name or wp.id == name:
                return wp.id
        vorhanden = ", ".join(self.waypoints) or "keine benannten Wegpunkte"
        raise SpotlabError(
            f"Den Wegpunkt '{name}' gibt es auf der Karte '{self.name}' nicht. "
            f"Vorhanden: {vorhanden}."
        )

    def __repr__(self):
        return f"<Map {self.name} mit {len(self.graph.waypoints)} Wegpunkten>"


def _protokolliere(recorder, name, **daten):
    if recorder is not None:
        recorder.event("kommando", name=name, **daten)


def load_map(backend, recorder, workspace, name=None, active=None):
    """Karte auf den Roboter laden. Ohne `name` die in der GUI gewählte."""
    require(backend, Capability.GRAPH_NAV, "auf einer Karte navigieren")
    if not workspace:
        raise SpotlabError(
            "Es ist kein Arbeitsordner gesetzt. Wähle einen in der Ansicht 'Projekte'."
        )
    gewaehlt = name or active
    if not gewaehlt:
        vorhanden = ", ".join(k.name for k in karten(workspace)) or "keine"
        raise SpotlabError(
            "Es ist keine Karte ausgewählt. Gib eine an — spot.load_map('name') — "
            f"oder wähle eine in der Ansicht 'Karten'. Vorhanden: {vorhanden}."
        )

    ordner = finde(workspace, gewaehlt)
    _protokolliere(recorder, "load_map", karte=str(gewaehlt))
    backend.upload_map(ordner)
    return Map(name=ordner.name, dir=ordner, graph=lade_graph(ordner))


def localize(backend, recorder):
    require(backend, Capability.GRAPH_NAV, "sich auf einer Karte verorten")
    _protokolliere(recorder, "localize")
    kennung = backend.localize()
    if recorder is not None:
        recorder.event("rückmeldung", name="localize", status=f"verortet bei {kennung}")
    return kennung


def navigate_to(backend, recorder, karte, ziel, limits, timeout=120.0,
                schlaf=time.sleep, jetzt=time.monotonic):
    """Autonom zu einem Wegpunkt fahren.

    Navigationskommandos verfallen wie Geschwindigkeitskommandos, deshalb die
    Schleife: nachsenden, Rückmeldung prüfen, wiederholen.
    """
    require(backend, Capability.GRAPH_NAV, "auf einer Karte navigieren")
    waypoint_id = karte.id_fuer(ziel)
    params = backend.travel_params(limits)
    _protokolliere(recorder, "navigate_to", ziel=str(ziel), waypoint=waypoint_id,
                   max_speed=limits.max_speed)

    ende = jetzt() + float(timeout)
    command_id = None
    letzter_text = ""
    while True:
        command_id = backend.navigate_step(
            waypoint_id, KOMMANDO_GUELTIGKEIT_S, params, command_id=command_id)
        zustand = backend.navigation_status(command_id)

        if zustand.status != letzter_text:
            letzter_text = zustand.status
            if recorder is not None:
                recorder.event("rückmeldung", name="navigate_to", status=zustand.status)

        if zustand.gescheitert:
            raise NavigationError(zustand.status)
        if zustand.fertig:
            return
        if jetzt() >= ende:
            raise NavigationError(
                f"Der Spot hat '{ziel}' nicht innerhalb von {timeout:.0f} s erreicht "
                f"(zuletzt: {zustand.status})."
            )
        schlaf(NACHSENDE_INTERVALL_S)
```

- [ ] **Step 4: `RealSpot` um die durchreichenden Methoden erweitern** — in `backends/real/session.py` vor `# ---- Abbau` einfügen:

```python
    # ------------------------------------------------------------- GraphNav

    def upload_map(self, kartenordner):
        from spotlab.backends.real import graphnav

        self._lease.raise_if_lost()
        return graphnav.upload_map(self._robot, kartenordner)

    def localize(self):
        from spotlab.backends.real import graphnav

        self._lease.raise_if_lost()
        return graphnav.localize(self._robot)

    def travel_params(self, limits):
        from spotlab.backends.real import graphnav

        return graphnav.travel_params(limits)

    def navigate_step(self, waypoint_id, dauer_s, params, command_id=None):
        from spotlab.backends.real import graphnav

        self._lease.raise_if_lost()
        return graphnav.navigate_step(self._robot, waypoint_id, dauer_s, params,
                                      command_id=command_id)

    def navigation_status(self, command_id):
        from spotlab.backends.real import graphnav

        return graphnav.navigation_status(self._robot, command_id)
```

- [ ] **Step 5: `Spot`-Fassade erweitern** — in `api/spot.py` den Import ergänzen:

```python
from spotlab.api import motion, navigation, perception, posture
```

im `__init__` nach `self._robot = robot` einfügen:

```python
        self._karte = None
        self._workspace = workspace
        self._active_map = active_map
```

und die Signatur zu
`def __init__(self, backend, recorder=None, limits=None, robot=None, workspace=None, active_map=None):`
erweitern. Danach die Verben ergänzen:

```python
    # ------------------------------------------------------------ Karten

    def load_map(self, name=None):
        self._karte = navigation.load_map(
            self.backend, self.recorder, self._workspace, name, self._active_map)
        return self._karte

    def localize(self):
        return navigation.localize(self.backend, self.recorder)

    def navigate_to(self, ziel, timeout=120.0):
        if self._karte is None:
            from spotlab.errors import SpotlabError

            raise SpotlabError(
                "Es ist keine Karte geladen — rufe zuerst spot.load_map() auf.")
        navigation.navigate_to(self.backend, self.recorder, self._karte, ziel,
                               self.limits, timeout=timeout)

    def waypoints(self):
        return self._karte.waypoints if self._karte else []
```

- [ ] **Step 6: `connect()` reicht Arbeitsordner und aktive Karte durch** — in `src/spotlab/__init__.py` den `Spot(...)`-Aufruf ersetzen durch:

```python
    spot = Spot(unten, recorder=recorder, limits=grenzen, robot=roher_roboter,
                workspace=(cfg.workspace if cfg else None),
                active_map=(cfg.active_map if cfg else None))
```

- [ ] **Step 7: Test dafür ergänzen** — an `tests/test_api_spot.py` anhängen:

```python
def test_navigate_ohne_karte_sagt_was_zu_tun_ist():
    from spotlab.errors import SpotlabError

    spot = _spot()
    with pytest.raises(SpotlabError) as info:
        spot.navigate_to("kueche")
    assert "load_map" in str(info.value)


def test_waypoints_ohne_karte_ist_leer():
    assert _spot().waypoints() == []
```

- [ ] **Step 8: Tests laufen lassen** — `pytest -q`, erwartet alle PASS

- [ ] **Step 9: Commit**

```bash
git add src/spotlab tests/
git commit -m "feat(api): load_map, localize, navigate_to mit Nachsenden und Deckel"
```

---

## Task 8: Die Draufsicht

**Files:**
- Create: `src/spotlab/gui/mapplot.py`, `tests/test_gui_mapplot.py`

**Interfaces:**
- Consumes: `Grundriss`, `Punkt`, `gui.theme.DUNKEL`
- Produces: `MapPlot(QWidget)` mit `.setze_grundriss(grundriss, palette=None)`, Attribut `.grundriss`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_mapplot.py`

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QColor, QPixmap  # noqa: E402

from spotlab.gui.mapplot import MapPlot  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.maps.geometry import Grundriss, Punkt  # noqa: E402


def _grundriss():
    return Grundriss(
        punkte=[Punkt("a", "start", 0.0, 0.0), Punkt("b", "kueche", 4.0, 3.0)],
        kanten=[("a", "b")],
        quelle="anker",
        hinweis="",
    )


def _gezeichnet(widget, breite=320, hoehe=240):
    widget.resize(breite, hoehe)
    bild = QPixmap(breite, hoehe)
    widget.render(bild)
    return bild.toImage()


def _zaehle(bild, hexfarbe, toleranz=40):
    ziel = QColor(hexfarbe)
    treffer = 0
    for y in range(bild.height()):
        for x in range(bild.width()):
            farbe = bild.pixelColor(x, y)
            if (abs(farbe.red() - ziel.red()) < toleranz
                    and abs(farbe.green() - ziel.green()) < toleranz
                    and abs(farbe.blue() - ziel.blue()) < toleranz):
                treffer += 1
    return treffer


def test_leerer_grundriss_zeichnet_ohne_absturz(qapp):
    plot = MapPlot()
    plot.setze_grundriss(Grundriss([], [], "leer", "Diese Karte ist leer."))
    _gezeichnet(plot)          # darf nicht werfen


def test_punkte_werden_gezeichnet(qapp):
    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    bild = _gezeichnet(plot)
    assert _zaehle(bild, DUNKEL.akzent) > 20


def test_hinweis_wird_uebernommen(qapp):
    plot = MapPlot()
    grundriss = Grundriss([Punkt("a", "", 0.0, 0.0)], [], "kette", "Rundungsfehler möglich.")
    plot.setze_grundriss(grundriss, DUNKEL)
    assert plot.grundriss.hinweis == "Rundungsfehler möglich."


def test_ein_einzelner_punkt_stuerzt_nicht_ab(qapp):
    """Ohne Ausdehnung wäre der Massstab eine Division durch null."""
    plot = MapPlot()
    plot.setze_grundriss(Grundriss([Punkt("a", "", 2.0, 2.0)], [], "kette", ""), DUNKEL)
    _gezeichnet(plot)


def test_widget_ohne_flaeche_stuerzt_nicht_ab(qapp):
    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    _gezeichnet(plot, breite=1, hoehe=1)
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_mapplot.py -q`

- [ ] **Step 3: `gui/mapplot.py` implementieren**

```python
"""Draufsicht auf eine Karte.

Gezeichnet mit QPainter — dieselbe Überlegung wie bei der Tempo-Kurve: das
SDK-Beispiel graph_nav_view_map braucht VTK, eine 3D-Rendering-Bibliothek von
rund hundert Megabyte, um Punkte und Linien zu zeichnen. Auf zwanzig
Schullaptops steht das in keinem Verhältnis.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from spotlab.gui.theme import DUNKEL
from spotlab.maps.geometry import Grundriss

RAND = 30
PUNKT_R = 4


class MapPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.grundriss = Grundriss([], [], "leer", "Keine Karte gewählt.")
        self.palette_ = DUNKEL

    def setze_grundriss(self, grundriss, palette=None):
        self.grundriss = grundriss
        if palette is not None:
            self.palette_ = palette
        self.update()

    def paintEvent(self, ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        breite = max(self.width() - 2 * RAND, 1)
        hoehe = max(self.height() - 2 * RAND, 1)

        maler.setPen(QPen(QColor(self.palette_.rand), 1))
        maler.drawRect(RAND, RAND, breite, hoehe)

        punkte = self.grundriss.punkte
        if not punkte:
            maler.setPen(QColor(self.palette_.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter,
                           self.grundriss.hinweis or "Keine Wegpunkte.")
            return

        x_werte = [p.x for p in punkte]
        y_werte = [p.y for p in punkte]
        spanne_x = max(max(x_werte) - min(x_werte), 1e-6)
        spanne_y = max(max(y_werte) - min(y_werte), 1e-6)
        # Massstab gemeinsam, damit die Karte nicht verzerrt
        massstab = min(breite / spanne_x, hoehe / spanne_y) * 0.9
        mitte_x, mitte_y = (max(x_werte) + min(x_werte)) / 2, (max(y_werte) + min(y_werte)) / 2

        def auf_schirm(punkt):
            return (
                int(RAND + breite / 2 + (punkt.x - mitte_x) * massstab),
                # y nach oben: Bildschirmkoordinaten laufen andersherum
                int(RAND + hoehe / 2 - (punkt.y - mitte_y) * massstab),
            )

        lage = {p.id: auf_schirm(p) for p in punkte}

        maler.setPen(QPen(QColor(self.palette_.gedaempft), 1))
        for von, nach in self.grundriss.kanten:
            if von in lage and nach in lage:
                maler.drawLine(*lage[von], *lage[nach])

        for punkt in punkte:
            x, y = lage[punkt.id]
            benannt = bool(punkt.name)
            maler.setPen(QPen(QColor(
                self.palette_.ok if benannt else self.palette_.akzent), 2))
            maler.drawEllipse(x - PUNKT_R, y - PUNKT_R, 2 * PUNKT_R, 2 * PUNKT_R)
            if benannt:
                maler.setPen(QColor(self.palette_.text))
                maler.drawText(x + PUNKT_R + 3, y - PUNKT_R, punkt.name)

        maler.setPen(QColor(self.palette_.gedaempft))
        maler.drawText(RAND, RAND - 10,
                       f"{len(punkte)} Wegpunkte · Quelle: {self.grundriss.quelle}")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_mapplot.py -q`, erwartet 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/mapplot.py tests/test_gui_mapplot.py
git commit -m "feat(gui): Kartendraufsicht auf QPainter"
```

---

## Task 9: Der Aufnahme-Arbeiter

**Files:**
- Create: `src/spotlab/gui/recorder.py`, `tests/test_gui_recorder.py`

**Interfaces:**
- Consumes: `RecordingSession`, `RecordingStatus`
- Produces:
  - `Auftrag(art: str, daten: dict)` — frozen dataclass; Arten `"start"`, `"waypoint"`, `"stop"`, `"speichern"`, `"ende"`
  - `RecordingWorker(QThread)` mit Signalen `status(object)`, `fehler(str)`, `gespeichert(str)`, `bereit()`; Methoden `.starte(graph_leeren)`, `.setze_wegpunkt(name)`, `.beende()`, `.speichere(wurzel, name)`, `.schliesse()`
  - `verarbeite(sitzung, auftrag) -> tuple[str, object]` — **Qt-frei**, das prüfbare Herzstück

**Warum ein Thread:** `RecordingSession.connect` braucht Sekunden, und der Status wird im Sekundentakt abgefragt. Beides im Qt-Hauptthread würde das Fenster einfrieren.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_recorder.py`

```python
import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.errors import MapError  # noqa: E402
from spotlab.gui.recorder import Auftrag, verarbeite  # noqa: E402
from spotlab.maps.session import RecordingStatus  # noqa: E402


class FakeSession:
    def __init__(self, fehler=None):
        self.protokoll = []
        self._fehler = fehler

    def start(self, graph_leeren=False):
        if self._fehler:
            raise self._fehler
        self.protokoll.append(f"start:{graph_leeren}")

    def waypoint(self, name):
        if self._fehler:
            raise self._fehler
        self.protokoll.append(f"waypoint:{name}")
        return "wp-neu"

    def stop(self):
        self.protokoll.append("stop")

    def download(self, wurzel, name, roboter=None):
        self.protokoll.append(f"download:{name}")
        return wurzel / name

    def status(self):
        return RecordingStatus(True, 3, 2, "Aufnahme läuft")


def test_start_wird_durchgereicht():
    sitzung = FakeSession()
    art, _ = verarbeite(sitzung, Auftrag("start", {"graph_leeren": True}))
    assert art == "status"
    assert sitzung.protokoll == ["start:True"]


def test_wegpunkt_wird_durchgereicht():
    sitzung = FakeSession()
    verarbeite(sitzung, Auftrag("waypoint", {"name": "kueche"}))
    assert sitzung.protokoll == ["waypoint:kueche"]


def test_stoppen_und_speichern(tmp_path):
    sitzung = FakeSession()
    art, nutzlast = verarbeite(
        sitzung, Auftrag("speichern", {"wurzel": tmp_path, "name": "turnhalle"}))
    assert art == "gespeichert"
    assert "download:turnhalle" in sitzung.protokoll
    assert str(nutzlast).endswith("turnhalle")


def test_fehler_wird_als_fehler_gemeldet_nicht_geworfen():
    sitzung = FakeSession(fehler=MapError("Kein Fiducial."))
    art, nutzlast = verarbeite(sitzung, Auftrag("start", {"graph_leeren": False}))
    assert art == "fehler"
    assert "Fiducial" in nutzlast


def test_unerwarteter_fehler_wird_ebenfalls_gemeldet():
    sitzung = FakeSession(fehler=RuntimeError("Netz weg"))
    art, nutzlast = verarbeite(sitzung, Auftrag("start", {"graph_leeren": False}))
    assert art == "fehler"
    assert "Netz weg" in nutzlast


def test_unbekannter_auftrag_meldet_das():
    art, nutzlast = verarbeite(FakeSession(), Auftrag("quatsch", {}))
    assert art == "fehler"
    assert "quatsch" in nutzlast


def test_worker_ist_ein_qthread(qapp):
    from PySide6.QtCore import QThread

    from spotlab.gui.recorder import RecordingWorker

    assert issubclass(RecordingWorker, QThread)
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_recorder.py -q`

- [ ] **Step 3: `gui/recorder.py` implementieren**

```python
"""Die Aufzeichnung im Hintergrund.

RecordingSession.connect braucht Sekunden, und der Status wird im Sekundentakt
abgefragt. Beides im Qt-Hauptthread würde das Fenster einfrieren.

Das prüfbare Herzstück ist verarbeite() — Qt-frei, ohne Thread, ohne
Warteschlange. Der QThread darum herum ist nur Transport.
"""

import queue
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal

from spotlab.errors import SpotlabError

TAKT_S = 1.0


@dataclass(frozen=True)
class Auftrag:
    art: str
    daten: dict = field(default_factory=dict)


def verarbeite(sitzung, auftrag):
    """Einen Auftrag ausführen. Gibt ('status'|'gespeichert'|'fehler', Nutzlast).

    Wirft NICHT — ein Fehler in der Aufnahme darf den Arbeiter nicht beenden,
    sonst steht die Anzeige still und niemand weiss warum.
    """
    try:
        if auftrag.art == "start":
            sitzung.start(graph_leeren=bool(auftrag.daten.get("graph_leeren")))
        elif auftrag.art == "waypoint":
            sitzung.waypoint(auftrag.daten["name"])
        elif auftrag.art == "stop":
            sitzung.stop()
        elif auftrag.art == "speichern":
            sitzung.stop()
            ziel = sitzung.download(auftrag.daten["wurzel"], auftrag.daten["name"],
                                    roboter=auftrag.daten.get("roboter"))
            return "gespeichert", str(ziel)
        else:
            return "fehler", f"Unbekannter Auftrag: {auftrag.art}"
    except SpotlabError as fehler:
        return "fehler", str(fehler)
    except Exception as fehler:
        return "fehler", f"{type(fehler).__name__}: {fehler}"
    return "status", sitzung.status()


class RecordingWorker(QThread):
    status = Signal(object)
    fehler = Signal(str)
    gespeichert = Signal(str)
    bereit = Signal()

    def __init__(self, cfg, parent=None, verbinder=None):
        super().__init__(parent)
        self._cfg = cfg
        self._verbinder = verbinder
        self._auftraege = queue.Queue()
        self._laeuft = True

    # ------------------------------------------------------------- Aufträge

    def starte(self, graph_leeren=False):
        self._auftraege.put(Auftrag("start", {"graph_leeren": graph_leeren}))

    def setze_wegpunkt(self, name):
        self._auftraege.put(Auftrag("waypoint", {"name": name}))

    def beende(self):
        self._auftraege.put(Auftrag("stop"))

    def speichere(self, wurzel, name, roboter=None):
        self._auftraege.put(
            Auftrag("speichern", {"wurzel": wurzel, "name": name, "roboter": roboter}))

    def schliesse(self):
        self._laeuft = False
        self._auftraege.put(Auftrag("ende"))

    # ------------------------------------------------------------- Schleife

    def run(self):
        from spotlab.maps.session import RecordingSession

        try:
            sitzung = RecordingSession.connect(self._cfg, verbinder=self._verbinder)
        except SpotlabError as fehler:
            self.fehler.emit(str(fehler))
            return
        except Exception as fehler:
            self.fehler.emit(f"{type(fehler).__name__}: {fehler}")
            return

        self.bereit.emit()
        try:
            while self._laeuft:
                try:
                    auftrag = self._auftraege.get(timeout=TAKT_S)
                except queue.Empty:
                    self._melde_status(sitzung)
                    continue
                if auftrag.art == "ende":
                    break
                art, nutzlast = verarbeite(sitzung, auftrag)
                if art == "fehler":
                    self.fehler.emit(nutzlast)
                elif art == "gespeichert":
                    self.gespeichert.emit(nutzlast)
                else:
                    self.status.emit(nutzlast)
        finally:
            sitzung.close()

    def _melde_status(self, sitzung):
        try:
            self.status.emit(sitzung.status())
        except Exception as fehler:
            self.fehler.emit(f"Status nicht abrufbar: {fehler}")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_gui_recorder.py -q`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/recorder.py tests/test_gui_recorder.py
git commit -m "feat(gui): Aufnahme-Arbeiter mit Qt-freiem Kern"
```

---

## Task 10: Die Ansicht „Karten"

**Files:**
- Create: `src/spotlab/gui/views/maps.py`, `tests/test_gui_maps_view.py`
- Modify: `src/spotlab/gui/sidebar.py`, `src/spotlab/gui/app.py`

**Interfaces:**
- Consumes: `store.karten`, `store.lade_graph`, `store.loesche`, `geometry.grundriss`, `MapPlot`, `RecordingWorker`
- Produces: `MapsView(QWidget)` mit Signalen `aktive_karte_gewaehlt(str)`, `meldung(str)`; Methoden `setze_arbeitsordner(pfad)`, `setze_config(cfg)`, `aktualisiere()`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_gui_maps_view.py`

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from bosdyn.api.graph_nav import map_pb2  # noqa: E402

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.views.maps import MapsView  # noqa: E402
from spotlab.maps.store import karten_wurzel, speichere_metadaten  # noqa: E402


def _graph():
    graph = map_pb2.Graph()
    for kennung, name in (("wp0", "start"), ("wp1", "kueche")):
        wp = graph.waypoints.add()
        wp.id = kennung
        wp.annotations.name = name
    kante = graph.edges.add()
    kante.id.from_waypoint = "wp0"
    kante.id.to_waypoint = "wp1"
    anker = graph.anchoring.anchors.add()
    anker.id = "wp0"
    anker.seed_tform_waypoint.rotation.w = 1.0
    anker = graph.anchoring.anchors.add()
    anker.id = "wp1"
    anker.seed_tform_waypoint.rotation.w = 1.0
    anker.seed_tform_waypoint.position.x = 2.0
    return graph


def _karte(tmp_path, name="turnhalle"):
    ordner = karten_wurzel(tmp_path) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph().SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph())
    return ordner


def _cfg(tmp_path):
    return Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path))


def test_liste_zeigt_die_karten(qapp, tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 1
    assert "turnhalle" in ansicht.liste.item(0).text()


def test_ohne_karten_bleibt_die_liste_leer(qapp, tmp_path):
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 0


def test_auswahl_zeichnet_die_draufsicht(qapp, tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.liste.setCurrentRow(0)
    assert len(ansicht.plot.grundriss.punkte) == 2
    assert ansicht.plot.grundriss.quelle == "anker"


def test_als_aktiv_setzen_meldet_den_namen(qapp, tmp_path):
    _karte(tmp_path)
    gewaehlt = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.aktive_karte_gewaehlt.connect(gewaehlt.append)
    ansicht.liste.setCurrentRow(0)
    ansicht.aktiv_knopf.click()
    assert gewaehlt == ["turnhalle"]


def test_als_aktiv_ohne_auswahl_tut_nichts(qapp, tmp_path):
    gewaehlt = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.aktive_karte_gewaehlt.connect(gewaehlt.append)
    ansicht.aktiv_knopf.click()
    assert gewaehlt == []


def test_aufnahme_ohne_konfiguration_meldet_klartext(qapp, tmp_path):
    meldungen = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.meldung.connect(meldungen.append)
    ansicht.start_knopf.click()
    assert meldungen and "eingerichtet" in meldungen[0].lower()


def test_hinweis_auf_tablet_und_fiducial_steht_da(qapp):
    ansicht = MapsView()
    text = ansicht.hinweis.text().lower()
    assert "fiducial" in text
    assert "tablet" in text


def test_status_fuellt_die_anzeige(qapp, tmp_path):
    from spotlab.maps.session import RecordingStatus

    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht._zeige_status(RecordingStatus(True, 12, 11, "Aufnahme läuft"))
    assert "12" in ansicht.aufnahme_status.text()
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_gui_maps_view.py -q`

- [ ] **Step 3: `gui/views/maps.py` implementieren**

```python
"""Ansicht „Karten": aufzeichnen, ansehen, auswählen.

Aufzeichnen braucht kein Lease — deshalb darf die GUI es. Hochladen und
Fahren gehören ins Skript, deshalb setzt der Auswählen-Knopf nur die aktive
Karte in der Konfiguration.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.mapplot import MapPlot
from spotlab.maps.geometry import grundriss
from spotlab.maps.store import karten, lade_graph, loesche

HINWEIS = (
    "Zum Aufzeichnen muss der Spot ein Fiducial sehen. Fahre ihn während der "
    "Aufnahme mit dem TABLET durch den Raum — spotlab zeichnet nur mit und "
    "übernimmt die Steuerung nicht."
)


class MapsView(QWidget):
    aktive_karte_gewaehlt = Signal(str)
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ordner = None
        self._config = None
        self._worker = None
        self._karten = []

        self.hinweis = QLabel(HINWEIS)
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        self.graph_leeren = QCheckBox("Karte auf dem Roboter zuerst leeren")
        self.start_knopf = QPushButton("Aufnahme starten")
        self.start_knopf.clicked.connect(self._starte_aufnahme)
        self.wegpunkt_knopf = QPushButton("Wegpunkt setzen")
        self.wegpunkt_knopf.clicked.connect(self._setze_wegpunkt)
        self.speichern_knopf = QPushButton("Beenden und speichern")
        self.speichern_knopf.clicked.connect(self._beende_und_speichere)
        self.aufnahme_status = QLabel("Keine Aufnahme")
        self.aufnahme_status.setObjectName("Gedaempft")
        for knopf in (self.wegpunkt_knopf, self.speichern_knopf):
            knopf.setEnabled(False)

        self.liste = QListWidget()
        self.liste.currentRowChanged.connect(self._zeige_karte)
        self.aktiv_knopf = QPushButton("Als aktive Karte setzen")
        self.aktiv_knopf.clicked.connect(self._setze_aktiv)
        self.loeschen_knopf = QPushButton("Löschen")
        self.loeschen_knopf.clicked.connect(self._loesche)

        self.plot = MapPlot()
        self.plot_hinweis = QLabel("")
        self.plot_hinweis.setObjectName("Gedaempft")
        self.plot_hinweis.setWordWrap(True)

        aufnahme = QHBoxLayout()
        aufnahme.addWidget(self.start_knopf)
        aufnahme.addWidget(self.wegpunkt_knopf)
        aufnahme.addWidget(self.speichern_knopf)
        aufnahme.addStretch(1)
        aufnahme.addWidget(self.aufnahme_status)

        kartenknoepfe = QHBoxLayout()
        kartenknoepfe.addWidget(self.aktiv_knopf)
        kartenknoepfe.addWidget(self.loeschen_knopf)
        kartenknoepfe.addStretch(1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Aufnahme"))
        anordnung.addWidget(self.hinweis)
        anordnung.addWidget(self.graph_leeren)
        anordnung.addLayout(aufnahme)
        anordnung.addWidget(QLabel("Karten"))
        anordnung.addWidget(self.liste, 1)
        anordnung.addLayout(kartenknoepfe)
        anordnung.addWidget(self.plot, 3)
        anordnung.addWidget(self.plot_hinweis)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def setze_config(self, cfg):
        self._config = cfg

    def aktualisiere(self):
        self.liste.clear()
        self._karten = karten(self._ordner) if self._ordner else []
        for eintrag in self._karten:
            self.liste.addItem(
                f"{eintrag.name}  ·  {eintrag.wegpunkte} Wegpunkte, "
                f"{eintrag.kanten} Kanten")

    def _gewaehlte(self):
        zeile = self.liste.currentRow()
        if zeile < 0 or zeile >= len(self._karten):
            return None
        return self._karten[zeile]

    def _zeige_karte(self, _zeile):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        try:
            riss = grundriss(lade_graph(eintrag.dir))
        except OSError as fehler:
            self.meldung.emit(f"Die Karte lässt sich nicht lesen: {fehler}")
            return
        self.plot.setze_grundriss(riss)
        self.plot_hinweis.setText(riss.hinweis)

    # ------------------------------------------------------------- Karten

    def _setze_aktiv(self):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        self.aktive_karte_gewaehlt.emit(eintrag.name)
        self.meldung.emit(
            f"'{eintrag.name}' ist jetzt die aktive Karte — im Skript reicht "
            f"spot.load_map().")

    def _loesche(self):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        antwort = QMessageBox.question(
            self, "spotlab", f"Die Karte '{eintrag.name}' wirklich löschen?")
        if antwort != QMessageBox.Yes:
            return
        loesche(eintrag.dir)
        self.aktualisiere()

    # ------------------------------------------------------------- Aufnahme

    def _starte_aufnahme(self):
        if self._config is None:
            self.meldung.emit(
                "Der Spot ist noch nicht eingerichtet — Ansicht 'Spot'.")
            return
        if self._ordner is None:
            self.meldung.emit("Wähle zuerst einen Arbeitsordner — Ansicht 'Projekte'.")
            return
        if self._worker is not None:
            self.meldung.emit("Es läuft bereits eine Aufnahme.")
            return

        from spotlab.gui.recorder import RecordingWorker

        self._worker = RecordingWorker(self._config, self)
        self._worker.status.connect(self._zeige_status)
        self._worker.fehler.connect(self._aufnahme_fehler)
        self._worker.gespeichert.connect(self._aufnahme_gespeichert)
        self._worker.bereit.connect(
            lambda: self._worker.starte(self.graph_leeren.isChecked()))
        self._worker.start()
        self.start_knopf.setEnabled(False)
        self.wegpunkt_knopf.setEnabled(True)
        self.speichern_knopf.setEnabled(True)
        self.aufnahme_status.setText("Verbinde…")

    def _setze_wegpunkt(self):
        if self._worker is None:
            return
        name, ok = QInputDialog.getText(self, "Wegpunkt", "Name:")
        if ok and name.strip():
            self._worker.setze_wegpunkt(name.strip())

    def _beende_und_speichere(self):
        if self._worker is None or self._ordner is None:
            return
        name, ok = QInputDialog.getText(self, "Karte speichern", "Name der Karte:")
        if not ok or not name.strip():
            return
        from spotlab.maps.store import karten_wurzel

        self._worker.speichere(
            karten_wurzel(self._ordner), name.strip(),
            roboter=self._config.nickname if self._config else None)

    def _zeige_status(self, status):
        self.aufnahme_status.setText(
            f"{status.meldung} · {status.wegpunkte} Wegpunkte, {status.kanten} Kanten")

    def _aufnahme_fehler(self, text):
        self.meldung.emit(text)

    def _aufnahme_gespeichert(self, pfad):
        self.meldung.emit(f"Karte gespeichert: {pfad}")
        self._beende_worker()
        self.aktualisiere()

    def _beende_worker(self):
        if self._worker is not None:
            self._worker.schliesse()
            self._worker.wait(3000)
            self._worker = None
        self.start_knopf.setEnabled(True)
        self.wegpunkt_knopf.setEnabled(False)
        self.speichern_knopf.setEnabled(False)
        self.aufnahme_status.setText("Keine Aufnahme")
```

- [ ] **Step 4: Seitenleiste um den fünften Eintrag erweitern** — in `gui/sidebar.py` `EINTRAEGE` ersetzen durch:

```python
EINTRAEGE = (
    ("projekte", "Projekte"),
    ("live", "Live-Lauf"),
    ("laeufe", "Läufe"),
    ("karten", "Karten"),
    ("spot", "Spot"),
)
```

- [ ] **Step 5: `gui/app.py` verdrahten** — Import ergänzen:

```python
from spotlab.gui.views.maps import MapsView
```

im `self.ansichten`-Wörterbuch ergänzen `"karten": MapsView(),` und die Reihenfolge-Schleife
zu `for schluessel in ("projekte", "live", "laeufe", "karten", "spot"):` erweitern.

In `_verdrahte` ergänzen:

```python
        self.ansichten["karten"].meldung.connect(self._melde)
        self.ansichten["karten"].aktive_karte_gewaehlt.connect(self._merke_aktive_karte)
```

In `_setze_arbeitsordner` nach der `laeufe`-Zeile ergänzen:

```python
        self.ansichten["karten"].setze_arbeitsordner(pfad or None)
```

Nach `_merke_arbeitsordner` einfügen:

```python
    def _merke_aktive_karte(self, name):
        if self._config is None:
            self._melde("Der Spot ist noch nicht eingerichtet — Ansicht 'Spot'.")
            return
        self._config = replace(self._config, active_map=name)
        save_config(self._config)
        self.ansichten["karten"].setze_config(self._config)
```

In `__init__` nach `self.kopf.zeige_config(self._config)` ergänzen:

```python
        self.ansichten["karten"].setze_config(self._config)
```

und in `_config_gespeichert` ebenfalls `self.ansichten["karten"].setze_config(cfg)`.

- [ ] **Step 6: Test für die Verdrahtung ergänzen** — an `tests/test_gui_app.py` anhängen:

```python
def test_fenster_hat_jetzt_fuenf_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {"projekte", "live", "laeufe", "karten", "spot"}
    assert fenster.stapel.count() == 5


def test_aktive_karte_wird_gemerkt(qapp, tmp_path, monkeypatch):
    from spotlab.config import Config, Limits, save_config

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits()), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    fenster = MainWindow()
    fenster._merke_aktive_karte("turnhalle")

    from spotlab.config import load_config

    assert load_config(pfad).active_map == "turnhalle"
```

- [ ] **Step 7: Tests laufen lassen** — `pytest -q`, erwartet alle PASS

- [ ] **Step 8: Commit**

```bash
git add src/spotlab/gui tests/
git commit -m "feat(gui): Ansicht Karten mit Aufnahme, Liste und Draufsicht"
```

---

## Task 11: Kommandozeile

**Files:**
- Modify: `src/spotlab/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `spotlab maps` (auflisten), `spotlab record-map <name>` (interaktiv aufzeichnen)

- [ ] **Step 1: Fehlschlagende Tests schreiben** — an `tests/test_cli.py` anhängen

```python
def test_maps_kommando_existiert():
    assert build_parser().parse_args(["maps"])


def test_record_map_braucht_einen_namen():
    assert build_parser().parse_args(["record-map", "turnhalle"])


def test_maps_ohne_arbeitsordner_sagt_das(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    assert main(["maps"]) == 1
    assert "Arbeitsordner" in capsys.readouterr().err


def test_maps_listet_die_karten(monkeypatch, capsys, tmp_path):
    from bosdyn.api.graph_nav import map_pb2

    from spotlab.config import Config, Limits, save_config
    from spotlab.maps.store import karten_wurzel, speichere_metadaten

    graph = map_pb2.Graph()
    graph.waypoints.add().id = "wp0"
    ordner = karten_wurzel(tmp_path) / "turnhalle"
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    speichere_metadaten(ordner, "turnhalle", "SN-1", graph)

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits(),
                       workspace=str(tmp_path)), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    assert main(["maps"]) == 0
    assert "turnhalle" in capsys.readouterr().out
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_cli.py -q`

- [ ] **Step 3: `cli.py` ergänzen** — in `build_parser` vor `unter.add_parser("gui", …)`:

```python
    unter.add_parser("maps", help="aufgezeichnete Karten auflisten")

    aufnahme = unter.add_parser("record-map", help="eine Karte aufzeichnen")
    aufnahme.add_argument("name")
    aufnahme.add_argument("--leeren", action="store_true",
                          help="Karte auf dem Roboter zuerst leeren")
```

in `_fuehre_aus` vor `if args.kommando == "gui":`:

```python
    if args.kommando == "maps":
        return _maps()
    if args.kommando == "record-map":
        return _record_map(args.name, args.leeren)
```

und am Dateiende:

```python
def _arbeitsordner():
    from spotlab.config import load_config

    cfg = load_config()
    if not cfg.workspace:
        raise SpotlabError(
            "Es ist kein Arbeitsordner gesetzt. Wähle einen in der Oberfläche "
            "(`spotlab gui`, Ansicht 'Projekte')."
        )
    return cfg, Path(cfg.workspace)


def _maps():
    from spotlab.maps.store import karten

    cfg, ordner = _arbeitsordner()
    liste = karten(ordner)
    if not liste:
        print(f"In {ordner} gibt es noch keine Karten. "
              f"Aufzeichnen mit:  spotlab record-map <name>")
        return 0
    aktiv = cfg.active_map
    for eintrag in liste:
        marke = "*" if eintrag.name == aktiv else " "
        print(f"{marke} {eintrag.name:<24} {eintrag.wegpunkte:>4} Wegpunkte, "
              f"{eintrag.kanten:>4} Kanten   {eintrag.aufgezeichnet or ''}")
    if aktiv:
        print(f"\n* = aktive Karte; im Skript reicht spot.load_map()")
    return 0


def _record_map(name, leeren):
    """Interaktiv wie das SDK-Beispiel: fahren tut man mit dem Tablet."""
    from spotlab.maps.session import RecordingSession
    from spotlab.maps.store import karten_wurzel

    cfg, ordner = _arbeitsordner()
    print(f"{GRAU}Der Spot muss ein Fiducial sehen. Gefahren wird mit dem TABLET — "
          f"spotlab zeichnet nur mit.{AUS}")
    sitzung = RecordingSession.connect(cfg)
    try:
        sitzung.start(graph_leeren=leeren)
        print(f"{GRUEN}Aufnahme läuft.{AUS} Befehle: <Name> = Wegpunkt setzen · "
              f"s = Status · f = fertig")
        while True:
            eingabe = input("> ").strip()
            if eingabe == "f":
                break
            if eingabe == "s":
                zustand = sitzung.status()
                print(f"  {zustand.meldung} · {zustand.wegpunkte} Wegpunkte, "
                      f"{zustand.kanten} Kanten")
                continue
            if eingabe:
                print(f"  Wegpunkt gesetzt: {sitzung.waypoint(eingabe)}")
        sitzung.stop()
        ziel = sitzung.download(karten_wurzel(ordner), name, roboter=cfg.nickname)
        print(f"{GRUEN}Karte gespeichert:{AUS} {ziel}")
    finally:
        sitzung.close()
    return 0
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_cli.py -q`, erwartet alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/cli.py tests/test_cli.py
git commit -m "feat(cli): maps und record-map"
```

---

## Task 12: Doku und Abnahme

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/ABNAHME.md`

- [ ] **Step 1: `README.md`** — Abschnitt „Karten" nach „Oberfläche" einfügen:

Aufzeichnen (`spotlab record-map turnhalle` oder Ansicht „Karten"), dass **der Spot ein
Fiducial sehen muss** und **mit dem Tablet gefahren wird**, Auflisten mit `spotlab maps`,
die aktive Karte, und das Skriptbeispiel:

```python
with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    karte = spot.load_map()          # die in der GUI gewählte Karte
    print(karte.waypoints)
    spot.localize()
    spot.navigate_to("kueche")
```

Dazu der Satz, dass Karten im SDK-Format liegen und sich mit `graph_nav_command_line.py`
und `view_map.py` aus dem SDK austauschen lassen. Und die Warnung, dass `navigate_to` den
Roboter **autonom** bewegt.

- [ ] **Step 2: `CLAUDE.md`** — unter „Nicht verhandelbar" ergänzen:

```markdown
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von `src/spotlab/maps/`.**
  Aufzeichnen ist leaselos; nur deshalb darf die GUI es. Ein Lease dort bräche H1.
- **Autonome Fahrt bekommt immer `travel_params` mit `velocity_limit` aus der
  Konfiguration.** Ohne das führe ein Schüler autonom schneller als von Hand.
- **Das Kartenformat auf der Platte ist das des SDK.** Kein eigenes Format — sonst geht
  die Austauschbarkeit mit `graph_nav_command_line.py` und `view_map.py` verloren.
```

- [ ] **Step 3: `docs/ABNAHME.md`** — vor „Nach der Abnahme" die Punkte A12–A16 einfügen,
jeweils mit Prozedur, Erwartung und leerem Ergebnisfeld:

**A12 — Fiducials.** Sind die Markierungen vorhanden und aufgehängt? `spotlab record-map test`
starten. Erwartung: kein `STATUS_MISSING_FIDUCIALS`. *Voraussetzung für A13–A16 — ohne
Fiducial ist die ganze Stufe nicht benutzbar.*

**A13 — Aufzeichnen.** Aufnahme starten, mit dem Tablet durch den Raum fahren, unterwegs
zwei benannte Wegpunkte setzen, beenden und speichern. Erwartung: der Zähler steigt sichtbar;
`karten/<name>/graph` existiert; für jeden Wegpunkt liegt ein Schnappschuss in
`waypoint_snapshots/`; `spotlab maps` zeigt die Karte mit plausiblen Zahlen.

**A14 — Gegenprobe zur Interoperabilität.** Dieselbe Karte in der Ansicht „Karten" **und**
mit `python view_map.py <pfad>` aus dem SDK öffnen. Erwartung: gleiche Anordnung der
Wegpunkte. *Bestätigt Kartenformat (N5) und Geometrie (4.3) auf einen Schlag.* Notieren,
ob unsere Ansicht `anker` oder `kette` als Quelle meldet.

**A15 — Lokalisieren.** Roboter neu starten, `spot.load_map("<name>")` und `spot.localize()`.
Erwartung: die Verortung gelingt und nennt einen Wegpunkt der Karte.

**A16 — Autonome Fahrt.** *Freifläche und Aufsicht sicherstellen.* `spot.navigate_to("<name>")`
zu einem entfernten Wegpunkt. Erwartung: der Spot erreicht den Wegpunkt; **die aus
`runs/<id>/zustand.jsonl` gemessene Höchstgeschwindigkeit bleibt unter `max_speed` aus
`config.toml`**; der NOT-AUS in der GUI wirkt während der Fahrt. Den gemessenen Wert
notieren — er ist die Bestätigung, dass der Deckel greift und nicht nur im Code steht.

- [ ] **Step 4: Gesamtsuite** — `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/ABNAHME.md
git commit -m "docs: Karten im README, Arbeitsregeln, Abnahme A12-A16"
```

---

## Selbstprüfung des Plans

**Spec-Abdeckung:** N1 (kein Beispiel-Starter) → nichts zu bauen, in den Nicht-Zielen · N2 (Aufzeichnen in der GUI, leaselos) → Tasks 5, 9, 10; als Test in Task 5 festgehalten · N3 (Fahrt mit Deckel) → Tasks 6, 7 · N4 (Karten im Arbeitsordner) → Task 3 · N5 (SDK-Format) → Task 3, Gegenprobe A14 · N6 (QPainter statt VTK) → Task 8 · 4.1 Sitzung → Task 5 · 4.2 store → Task 3 · 4.3 geometry → Task 2 · 4.4 graphnav → Task 6 · 4.5 Verben → Task 7 · 4.6 Ansicht → Task 10 · Abschnitt 6 Fehlerbehandlung → Task 4 · Abschnitt 7 Prüfung → in jeden Task eingebaut · Abschnitt 8 Abnahme → Task 12.

**Abweichung von der Spec, bewusst:** Die Spec nennt in 4.4 die Signatur
`upload_map(robot, graph, waypoint_snapshots, edge_snapshots)`. Der Plan legt sie auf
`upload_map(robot, kartenordner)` fest — die Schnappschüsse werden erst gelesen, wenn der
Roboter in `unknown_*_snapshot_ids` meldet, dass sie ihm fehlen. Das spart es, bei jedem
Laden alle Schnappschüsse von der Platte zu ziehen; eine Karte mit fünfzig Wegpunkten hat
fünfzig davon, jeder mit Punktwolke.

**Ein in der Spec nicht behandelter Fall, hier entschieden:** `upload_map` ruft
`generate_new_anchoring=True`. Damit hat jede geladene Karte Anker, auch wenn die
aufgezeichnete keine hatte — die Draufsicht zeigt danach also `quelle="anker"`. Das ist
gewollt: die Anker sind der genauere Weg, und der Roboter rechnet sie ohnehin.
