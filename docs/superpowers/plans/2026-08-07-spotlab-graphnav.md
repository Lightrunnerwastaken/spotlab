# spotlab GraphNav — Implementierungsplan, Teil 1 (Qt-freie Schichten)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Karten aufzeichnen, ablegen, ansehen, auswählen — und den Spot darauf autonom von Wegpunkt zu Wegpunkt fahren lassen.

**Architecture:** Aufzeichnen ist **leaselos** und lebt in `maps/` (Qt-frei), die GUI ist nur Oberfläche darüber. Navigieren bewegt den Roboter, braucht Lease und Not-Aus und lebt deshalb als Bibliotheksverb im Schülerskript. Das Kartenformat auf der Platte ist unverändert das des SDK, damit Karten mit den SDK-Beispielen austauschbar bleiben.

**Tech Stack:** Python 3.13, `bosdyn-client` 5.0.1.2 (GraphNav ist enthalten), PySide6 6.11.1 (nur Extra `[gui]`), pytest. **Keine neuen Abhängigkeiten.**

## Global Constraints

- **Keine neuen Abhängigkeiten.** GraphNav ist Teil von `bosdyn-client`; gezeichnet wird mit `QPainter`.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.** Unverändert aus Stufe 3.
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von `src/spotlab/maps/`.** Neu — hält Grundsatzentscheidung N2 fest: die GUI darf reden, aber keine Kontrolle an sich reissen.
- **Kartenformat auf der Platte ist das des SDK** (`graph`, `waypoint_snapshots/`, `edge_snapshots/`). Nur `karte.json` kommt dazu.
- Python-Bezeichner englisch, alle Meldungen an Nutzer deutsch. Datei- und Feldnamen der Ablage deutsch.
- Alle Tests laufen ohne Roboter, ohne Netz und ohne Bildschirm (`QT_QPA_PLATFORM=offscreen`).
- Keine Farbliterale in Widget-Code — Farben nur aus `gui/theme.py`.
- Testgetrieben: erst der fehlschlagende Test, dann die Implementierung. Commit pro Task.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `src/spotlab/backends/base.py` | `Capability.GRAPH_NAV`, `NavStatus` | ändern |
| `src/spotlab/config.py` | Feld `active_map` | ändern |
| `src/spotlab/backends/real/verbindung.py` | gemeinsamer Aufbau Auth + Zeitsync | **neu** |
| `src/spotlab/backends/real/session.py` | nutzt `verbinde()` | ändern |
| `src/spotlab/errors/graphnav.py` | GraphNav-Statuscodes → Klartext | **neu** |
| `src/spotlab/maps/geometry.py` | Wegpunkt-Positionen aus dem Graphen | **neu** |
| `src/spotlab/maps/store.py` | Karten ablegen, auflisten, lesen, löschen | **neu** |
| `src/spotlab/maps/session.py` | Aufzeichnungssitzung, leaselos | **neu** |
| `src/spotlab/backends/real/graphnav.py` | Hochladen, Lokalisieren, Navigieren | **neu** |
| `src/spotlab/api/navigation.py` | `load_map`, `localize`, `navigate_to`, `waypoints` | **neu** |
| `src/spotlab/gui/mapplot.py` | Draufsicht auf `QPainter` | **neu** |
| `src/spotlab/gui/views/maps.py` | Ansicht „Karten" | **neu** |
| `src/spotlab/gui/sidebar.py` · `gui/app.py` | fünfter Eintrag, Verdrahtung | ändern |
| `src/spotlab/cli.py` | `record-map`, `maps` | ändern |

---

## Task 1: Fähigkeit, aktive Karte, gemeinsamer Verbindungsaufbau

**Files:**
- Modify: `src/spotlab/backends/base.py`, `src/spotlab/config.py`, `src/spotlab/backends/real/session.py`
- Create: `src/spotlab/backends/real/verbindung.py`
- Test: `tests/test_backend_base.py`, `tests/test_config.py`, `tests/test_real_verbindung.py`

**Interfaces:**
- Consumes: `spotlab.errors.translate`, `TimeSyncFailed`
- Produces:
  - `Capability.GRAPH_NAV`
  - `NavStatus(fertig: bool, status: str, gescheitert: bool)` — frozen dataclass in `backends/base.py`
  - `Config.active_map: str = ""`, geschrieben als `[maps] active`
  - `verbinde(cfg, robot_bauen=None, passwort_lesen=None) -> robot` — Auth + Zeitsync, sonst nichts

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_real_verbindung.py`

```python
import pytest

from spotlab.backends.real.verbindung import verbinde
from spotlab.config import Config, Limits
from spotlab.errors import BadCredentials, TimeSyncFailed


class FakeRobot:
    def __init__(self, protokoll, auth_fehler=None, sync_fehler=None):
        self.protokoll = protokoll
        self.time_sync = self
        self._auth_fehler = auth_fehler
        self._sync_fehler = sync_fehler

    def authenticate(self, user, password):
        if self._auth_fehler:
            raise self._auth_fehler
        self.protokoll.append("auth")

    def wait_for_sync(self):
        if self._sync_fehler:
            raise self._sync_fehler
        self.protokoll.append("time_sync")


def _cfg():
    return Config(ip="1.2.3.4", username="u", nickname="Spot", limits=Limits())


def test_reihenfolge_auth_dann_zeitsync():
    protokoll = []
    verbinde(_cfg(), robot_bauen=lambda c: FakeRobot(protokoll),
             passwort_lesen=lambda u: "x")
    assert protokoll == ["auth", "time_sync"]


def test_kein_lease_und_kein_estop():
    """verbinde() macht NUR Auth und Zeitsync — sonst wäre es nicht leaselos."""
    protokoll = []
    verbinde(_cfg(), robot_bauen=lambda c: FakeRobot(protokoll),
             passwort_lesen=lambda u: "x")
    assert "estop" not in protokoll and "lease" not in protokoll


def test_falsches_passwort_wird_uebersetzt():
    from bosdyn.client.auth import InvalidLoginError

    with pytest.raises(BadCredentials):
        verbinde(_cfg(),
                 robot_bauen=lambda c: FakeRobot([], auth_fehler=InvalidLoginError(response=None)),
                 passwort_lesen=lambda u: "x")


def test_zeitsync_fehler_wird_uebersetzt():
    with pytest.raises(TimeSyncFailed) as info:
        verbinde(_cfg(),
                 robot_bauen=lambda c: FakeRobot([], sync_fehler=RuntimeError("weg")),
                 passwort_lesen=lambda u: "x")
    assert "Uhr" in str(info.value)
```

und anhängen an `tests/test_backend_base.py`:

```python
def test_graph_nav_ist_eine_eigene_faehigkeit():
    assert Capability.GRAPH_NAV not in Capability.CAMERAS
    assert Capability.GRAPH_NAV not in Capability.LOCOMOTION


def test_navstatus_ist_unveraenderlich():
    from spotlab.backends.base import NavStatus

    zustand = NavStatus(fertig=True, status="angekommen", gescheitert=False)
    with pytest.raises(AttributeError):
        zustand.fertig = False
```

und an `tests/test_config.py`:

```python
def test_aktive_karte_ueberlebt_schreiben_und_lesen(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), active_map="turnhalle")
    save_config(cfg, pfad)
    assert load_config(pfad).active_map == "turnhalle"


def test_aktive_karte_hat_leere_vorgabe(tmp_path):
    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot]\nip = "1.2.3.4"\nusername = "u"\n', encoding="utf-8")
    assert load_config(pfad).active_map == ""
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_real_verbindung.py tests/test_backend_base.py tests/test_config.py -q`

- [ ] **Step 3: `backends/base.py` ergänzen** — in `Capability` nach `ESTOP` einfügen:

```python
    GRAPH_NAV = enum.auto()
```

nach der `Feedback`-Klasse einfügen:

```python
@dataclass(frozen=True)
class NavStatus:
    """Rückmeldung einer laufenden Navigation, backend-unabhängig.

    Dieselbe Naht wie Feedback: api/ bleibt dadurch protobuf-frei.
    """

    fertig: bool
    status: str          # deutscher Klartext
    gescheitert: bool = False
```

und `_EINZELN` um `Capability.GRAPH_NAV` erweitern.

- [ ] **Step 4: `config.py` ergänzen** — in `Config` nach `workspace`:

```python
    active_map: str = ""  # in der GUI gewählte Karte; leer = keine
```

in `save_config` den `[gui]`-Block ergänzen um:

```python
        "\n[maps]\n"
        f"active = {_toml_string(cfg.active_map)}\n"
```

in `load_config` im `Config(...)`-Aufruf ergänzen:

```python
        active_map=roh.get("maps", {}).get("active", ""),
```

- [ ] **Step 5: `backends/real/verbindung.py` schreiben**

```python
"""Der gemeinsame Anfang jeder Roboterverbindung: Auth und Zeitsync.

Von RealSpot.connect (das danach E-Stop und Lease holt) UND von der
Aufzeichnungssitzung benutzt (die beides NICHT holt). Ohne diese Trennung
stünde die Fehlerübersetzung zweimal im Code.
"""

from bosdyn.client import create_standard_sdk

from spotlab.config import load_password
from spotlab.errors import TimeSyncFailed, translate

SDK_NAME = "spotlab"


def standard_robot(cfg):
    sdk = create_standard_sdk(SDK_NAME)
    return sdk.create_robot(cfg.ip)


def verbinde(cfg, robot_bauen=None, passwort_lesen=None):
    """Angemeldeter, zeitsynchroner Roboter — ohne Lease, ohne E-Stop."""
    robot = (robot_bauen or standard_robot)(cfg)

    try:
        robot.authenticate(cfg.username, (passwort_lesen or load_password)(cfg.username))
    except Exception as fehler:
        uebersetzt = translate(fehler, ip=cfg.ip)
        if uebersetzt is not None:
            raise uebersetzt from fehler
        raise

    try:
        robot.time_sync.wait_for_sync()
    except Exception as fehler:
        raise TimeSyncFailed(
            "Die Uhr deines Laptops weicht zu stark von der des Roboters ab; "
            "die Zeitsynchronisierung ist fehlgeschlagen. Windows-Uhrzeit "
            "automatisch stellen lassen und erneut versuchen."
        ) from fehler

    return robot
```

- [ ] **Step 6: `backends/real/session.py` auf `verbinde()` umstellen**

Die Importe `from bosdyn.client import create_standard_sdk` und `from spotlab.config import load_password` entfernen, dafür:

```python
from spotlab.backends.real.verbindung import standard_robot as _standard_robot
from spotlab.backends.real.verbindung import verbinde
```

Die Funktion `_standard_robot` und die beiden Blöcke für `authenticate` und `wait_for_sync` in `RealSpot.connect` ersetzen durch:

```python
        robot = verbinde(cfg, robot_bauen=robot_bauen, passwort_lesen=passwort_lesen)
```

`TimeSyncFailed` aus den Importen von `session.py` entfernen, falls dort sonst nicht mehr benutzt.

- [ ] **Step 7: Tests laufen lassen** — `pytest -q`, erwartet alle PASS (auch `tests/test_real_session.py` unverändert)

- [ ] **Step 8: Commit**

```bash
git add src/spotlab tests/
git commit -m "feat: Faehigkeit GRAPH_NAV, aktive Karte, gemeinsamer Verbindungsaufbau"
```

---

## Task 2: Wegpunkt-Positionen aus dem Graphen

**Files:**
- Create: `src/spotlab/maps/__init__.py`, `src/spotlab/maps/geometry.py`, `tests/test_maps_geometry.py`

**Interfaces:**
- Consumes: `bosdyn.api.graph_nav.map_pb2`, `bosdyn.client.math_helpers.SE3Pose`
- Produces:
  - `Punkt(id: str, name: str, x: float, y: float)` — frozen dataclass
  - `Grundriss(punkte: list[Punkt], kanten: list[tuple[str, str]], quelle: str, hinweis: str)` — frozen dataclass; `quelle` ist `"anker"`, `"kette"` oder `"leer"`
  - `grundriss(graph) -> Grundriss`

**Zwei Wege, weil `anchoring` nicht immer befüllt ist** — `view_map.py` aus dem SDK prüft das ausdrücklich und zeichnet sonst über die Kantenkette.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_maps_geometry.py`

```python
from bosdyn.api.graph_nav import map_pb2

from spotlab.maps.geometry import grundriss


def _wegpunkt(graph, kennung, name=""):
    wp = graph.waypoints.add()
    wp.id = kennung
    wp.annotations.name = name
    wp.waypoint_tform_ko.rotation.w = 1.0
    return wp


def _kante(graph, von, nach, dx=1.0, dy=0.0):
    kante = graph.edges.add()
    kante.id.from_waypoint = von
    kante.id.to_waypoint = nach
    kante.from_tform_to.rotation.w = 1.0
    kante.from_tform_to.position.x = dx
    kante.from_tform_to.position.y = dy
    return kante


def _anker(graph, kennung, x, y):
    anker = graph.anchoring.anchors.add()
    anker.id = kennung
    anker.seed_tform_waypoint.rotation.w = 1.0
    anker.seed_tform_waypoint.position.x = x
    anker.seed_tform_waypoint.position.y = y


def test_anker_werden_bevorzugt():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a", "start")
    _wegpunkt(graph, "b", "kueche")
    _kante(graph, "a", "b")
    _anker(graph, "a", 0.0, 0.0)
    _anker(graph, "b", 3.0, 4.0)

    ergebnis = grundriss(graph)
    assert ergebnis.quelle == "anker"
    nach_id = {p.id: p for p in ergebnis.punkte}
    assert (nach_id["b"].x, nach_id["b"].y) == (3.0, 4.0)
    assert nach_id["b"].name == "kueche"
    assert ergebnis.kanten == [("a", "b")]


def test_ohne_anker_ueber_die_kantenkette():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _wegpunkt(graph, "c")
    _kante(graph, "a", "b", dx=1.0)
    _kante(graph, "b", "c", dx=1.0)

    ergebnis = grundriss(graph)
    assert ergebnis.quelle == "kette"
    nach_id = {p.id: p for p in ergebnis.punkte}
    assert abs(nach_id["a"].x - 0.0) < 1e-9
    assert abs(nach_id["b"].x - 1.0) < 1e-9
    assert abs(nach_id["c"].x - 2.0) < 1e-9


def test_kette_laeuft_auch_rueckwaerts():
    """Die Kante zeigt von b nach a — der Weg muss trotzdem gefunden werden."""
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "b", "a", dx=2.0)

    nach_id = {p.id: p for p in grundriss(graph).punkte}
    assert abs(abs(nach_id["a"].x - nach_id["b"].x) - 2.0) < 1e-9


def test_kette_traegt_den_hinweis_auf_rundungsfehler():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "a", "b")
    assert "Rundung" in grundriss(graph).hinweis or "genau" in grundriss(graph).hinweis


def test_leerer_graph():
    ergebnis = grundriss(map_pb2.Graph())
    assert ergebnis.quelle == "leer"
    assert ergebnis.punkte == []
    assert ergebnis.hinweis


def test_ein_wegpunkt_ohne_kanten_ist_zeichenbar():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a", "start")
    ergebnis = grundriss(graph)
    assert len(ergebnis.punkte) == 1
    assert ergebnis.punkte[0].x == 0.0


def test_mehrere_wegpunkte_ohne_kanten_sind_nicht_verortbar():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    ergebnis = grundriss(graph)
    assert ergebnis.quelle == "leer"
    assert "Kanten" in ergebnis.hinweis


def test_unvollstaendige_anker_fallen_auf_die_kette_zurueck():
    """Anker nur für einen von zwei Wegpunkten — dann ist die Kette ehrlicher."""
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "a", "b")
    _anker(graph, "a", 0.0, 0.0)

    assert grundriss(graph).quelle == "kette"
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_maps_geometry.py -q`, erwartet `ModuleNotFoundError`

- [ ] **Step 3: `maps/__init__.py` anlegen**

```python
"""GraphNav-Karten: aufzeichnen, ablegen, zeichnen.

Dieses Paket ist per Bauart LEASELOS — hier gibt es keinen Lease-Client und
keinen E-Stop-Endpunkt. Nur deshalb darf die GUI es benutzen, ohne die
Grundsatzentscheidung H1 zu brechen.
"""
```

- [ ] **Step 4: `maps/geometry.py` implementieren**

```python
"""Wegpunkte in eine zeichenbare Ebene bringen.

Zwei Wege, weil graph.anchoring nicht immer befüllt ist — view_map.py aus dem
SDK prüft das ausdrücklich und zeichnet sonst über die Kantenkette:

anker   Positionen direkt aus anchoring. Genauer, weil global optimiert.
kette   Ab einem Wurzel-Wegpunkt edge.from_tform_to aufmultiplizieren.
"""

from dataclasses import dataclass

from bosdyn.client.math_helpers import SE3Pose

HINWEIS_KETTE = (
    "Gezeichnet über die Kantenkette, weil die Karte keine Anker hat. "
    "Über lange Wege summieren sich dabei Rundungsfehler — eine Schleife "
    "schliesst sich dann sichtbar nicht ganz. Das ist keine Fehlfunktion."
)
HINWEIS_LEER = "Diese Karte enthält keine Wegpunkte."
HINWEIS_UNVERBUNDEN = (
    "Diese Karte hat mehrere Wegpunkte, aber keine Kanten dazwischen — "
    "ohne Kanten lässt sich ihre Lage zueinander nicht bestimmen."
)


@dataclass(frozen=True)
class Punkt:
    id: str
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class Grundriss:
    punkte: list
    kanten: list
    quelle: str
    hinweis: str


def _kanten_paare(graph):
    return [(k.id.from_waypoint, k.id.to_waypoint) for k in graph.edges]


def _namen(graph):
    return {wp.id: (wp.annotations.name or "") for wp in graph.waypoints}


def _aus_ankern(graph):
    anker = {a.id: a.seed_tform_waypoint.position for a in graph.anchoring.anchors}
    if not anker or any(wp.id not in anker for wp in graph.waypoints):
        return None                     # unvollständig ⇒ die Kette ist ehrlicher
    namen = _namen(graph)
    return [
        Punkt(wp.id, namen[wp.id], float(anker[wp.id].x), float(anker[wp.id].y))
        for wp in graph.waypoints
    ]


def _aus_kette(graph):
    """Breitensuche ab dem ersten Wegpunkt, Transformationen aufmultiplizieren."""
    if not graph.waypoints:
        return None
    nachbarn = {}
    for kante in graph.edges:
        pose = SE3Pose.from_proto(kante.from_tform_to)
        nachbarn.setdefault(kante.id.from_waypoint, []).append(
            (kante.id.to_waypoint, pose))
        nachbarn.setdefault(kante.id.to_waypoint, []).append(
            (kante.id.from_waypoint, pose.inverse()))

    wurzel = graph.waypoints[0].id
    posen = {wurzel: SE3Pose.from_identity()}
    warteschlange = [wurzel]
    while warteschlange:
        aktuell = warteschlange.pop(0)
        for ziel, versatz in nachbarn.get(aktuell, ()):
            if ziel in posen:
                continue
            posen[ziel] = posen[aktuell].mult(versatz)
            warteschlange.append(ziel)

    if len(posen) < len(graph.waypoints):
        return None                     # nicht alles erreichbar
    namen = _namen(graph)
    return [
        Punkt(wp.id, namen[wp.id], float(posen[wp.id].x), float(posen[wp.id].y))
        for wp in graph.waypoints
    ]


def grundriss(graph):
    kanten = _kanten_paare(graph)

    punkte = _aus_ankern(graph)
    if punkte is not None:
        return Grundriss(punkte, kanten, "anker", "")

    punkte = _aus_kette(graph)
    if punkte is not None:
        return Grundriss(punkte, kanten, "kette", HINWEIS_KETTE)

    hinweis = HINWEIS_LEER if not graph.waypoints else HINWEIS_UNVERBUNDEN
    return Grundriss([], kanten, "leer", hinweis)
```

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_maps_geometry.py -q`, erwartet 8 PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/maps tests/test_maps_geometry.py
git commit -m "feat(maps): Wegpunkt-Positionen aus Ankern oder Kantenkette"
```

---

## Task 3: Karten ablegen und finden

**Files:**
- Create: `src/spotlab/maps/store.py`, `tests/test_maps_store.py`

**Interfaces:**
- Consumes: `map_pb2.Graph`
- Produces:
  - `KARTEN_ORDNER = "karten"`, `METADATEN = "karte.json"`
  - `karten_wurzel(workspace) -> Path`
  - `sicherer_name(name) -> str`
  - `MapInfo(name, dir, aufgezeichnet, roboter, wegpunkte, kanten)` — frozen dataclass
  - `speichere_metadaten(kartenordner, name, roboter, graph) -> None`
  - `karten(workspace) -> list[MapInfo]` — neueste zuerst
  - `lade_graph(kartenordner) -> map_pb2.Graph`
  - `finde(workspace, name) -> Path` — wirft `SpotlabError` mit Aufzählung
  - `loesche(kartenordner) -> None`

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_maps_store.py`

```python
import json

import pytest
from bosdyn.api.graph_nav import map_pb2

from spotlab.errors import SpotlabError
from spotlab.maps.store import (
    MapInfo,
    finde,
    karten,
    karten_wurzel,
    lade_graph,
    loesche,
    sicherer_name,
    speichere_metadaten,
)


def _graph(n=3):
    graph = map_pb2.Graph()
    for i in range(n):
        wp = graph.waypoints.add()
        wp.id = f"wp{i}"
    for i in range(n - 1):
        kante = graph.edges.add()
        kante.id.from_waypoint = f"wp{i}"
        kante.id.to_waypoint = f"wp{i + 1}"
    return graph


def _lege_an(workspace, name, n=3):
    ordner = karten_wurzel(workspace) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph(n).SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph(n))
    return ordner


def test_wurzel_heisst_karten(tmp_path):
    assert karten_wurzel(tmp_path).name == "karten"


def test_namen_werden_entschaerft():
    assert "/" not in sicherer_name("Turn/Halle")
    assert sicherer_name("  ") == "karte"


def test_karte_wird_gefunden_und_beschrieben(tmp_path):
    _lege_an(tmp_path, "turnhalle", n=4)
    liste = karten(tmp_path)
    assert len(liste) == 1
    eintrag = liste[0]
    assert isinstance(eintrag, MapInfo)
    assert eintrag.name == "turnhalle"
    assert eintrag.wegpunkte == 4
    assert eintrag.kanten == 3
    assert eintrag.roboter == "SN-1"


def test_leerer_arbeitsordner(tmp_path):
    assert karten(tmp_path) == []


def test_fehlender_kartenordner(tmp_path):
    assert karten(tmp_path / "gibtsnicht") == []


def test_beschaedigte_metadaten_machen_die_karte_nicht_unbrauchbar(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle", n=5)
    (ordner / "karte.json").write_text("{kaputt", encoding="utf-8")

    eintrag = karten(tmp_path)[0]
    assert eintrag.name == "turnhalle"
    assert eintrag.wegpunkte == 5          # aus dem Graphen zurückgefallen


def test_graph_wird_gelesen(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle", n=2)
    assert len(lade_graph(ordner).waypoints) == 2


def test_finde_liefert_den_ordner(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle")
    assert finde(tmp_path, "turnhalle") == ordner


def test_finde_zaehlt_vorhandene_auf(tmp_path):
    _lege_an(tmp_path, "turnhalle")
    _lege_an(tmp_path, "aula")
    with pytest.raises(SpotlabError) as info:
        finde(tmp_path, "keller")
    assert "turnhalle" in str(info.value) and "aula" in str(info.value)


def test_finde_ohne_jede_karte(tmp_path):
    with pytest.raises(SpotlabError) as info:
        finde(tmp_path, "keller")
    assert "keine" in str(info.value).lower()


def test_loeschen_entfernt_alles(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle")
    loesche(ordner)
    assert not ordner.exists()
    assert karten(tmp_path) == []


def test_metadaten_sind_lesbares_json(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle", n=3)
    daten = json.loads((ordner / "karte.json").read_text(encoding="utf-8"))
    assert daten["name"] == "turnhalle"
    assert daten["wegpunkte"] == 3
    assert daten["spotlab_version"]
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_maps_store.py -q`

- [ ] **Step 3: `maps/store.py` implementieren**

```python
"""Karten auf der Platte — im Format des SDK.

graph, waypoint_snapshots/ und edge_snapshots/ schreibt
GraphNavClient.write_graph_and_snapshots; daran ändern wir nichts. Nur
karte.json kommt dazu, mit dem, was das SDK nicht speichert.

Der Grund für dieses Format ist Austauschbarkeit: eine mit spotlab
aufgezeichnete Karte lässt sich unverändert an graph_nav_command_line.py und
view_map.py verfüttern — und umgekehrt.
"""

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bosdyn.api.graph_nav import map_pb2

from spotlab.errors import SpotlabError

KARTEN_ORDNER = "karten"
METADATEN = "karte.json"


@dataclass(frozen=True)
class MapInfo:
    name: str
    dir: Path
    aufgezeichnet: str | None
    roboter: str | None
    wegpunkte: int
    kanten: int


def karten_wurzel(workspace):
    return Path(workspace) / KARTEN_ORDNER


def sicherer_name(name):
    sauber = re.sub(r"[^\w.-]+", "-", str(name).strip()).strip("-.")
    return sauber or "karte"


def speichere_metadaten(kartenordner, name, roboter, graph):
    from spotlab import __version__

    (Path(kartenordner) / METADATEN).write_text(
        json.dumps(
            {
                "name": name,
                "aufgezeichnet": datetime.now(UTC).isoformat(),
                "roboter": roboter,
                "wegpunkte": len(graph.waypoints),
                "kanten": len(graph.edges),
                "spotlab_version": __version__,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def lade_graph(kartenordner):
    graph = map_pb2.Graph()
    graph.ParseFromString((Path(kartenordner) / "graph").read_bytes())
    return graph


def _beschreibe(ordner):
    meta = {}
    try:
        meta = json.loads((ordner / METADATEN).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}

    wegpunkte = meta.get("wegpunkte")
    kanten = meta.get("kanten")
    if wegpunkte is None or kanten is None:
        # Beschädigte Metadaten dürfen eine Karte nicht unbrauchbar machen —
        # der Graph selbst ist die Wahrheit.
        try:
            graph = lade_graph(ordner)
            wegpunkte, kanten = len(graph.waypoints), len(graph.edges)
        except OSError:
            wegpunkte, kanten = 0, 0

    return MapInfo(
        name=meta.get("name", ordner.name),
        dir=ordner,
        aufgezeichnet=meta.get("aufgezeichnet"),
        roboter=meta.get("roboter"),
        wegpunkte=int(wegpunkte),
        kanten=int(kanten),
    )


def karten(workspace):
    wurzel = karten_wurzel(workspace)
    if not wurzel.is_dir():
        return []
    ordner = [p for p in wurzel.iterdir() if p.is_dir() and (p / "graph").exists()]
    ordner.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_beschreibe(p) for p in ordner]


def finde(workspace, name):
    ziel = karten_wurzel(workspace) / sicherer_name(name)
    if ziel.is_dir() and (ziel / "graph").exists():
        return ziel
    vorhanden = [k.name for k in karten(workspace)]
    if not vorhanden:
        return _fehlt(f"Es gibt noch keine Karten in {karten_wurzel(workspace)}.")
    return _fehlt(
        f"Die Karte '{name}' gibt es nicht. Vorhanden: {', '.join(vorhanden)}."
    )


def _fehlt(text):
    raise SpotlabError(text)


def loesche(kartenordner):
    shutil.rmtree(Path(kartenordner), ignore_errors=True)
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_maps_store.py -q`, erwartet 12 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/maps/store.py tests/test_maps_store.py
git commit -m "feat(maps): Karten ablegen, auflisten, finden, loeschen"
```

---

## Task 4: GraphNav-Statuscodes übersetzen

**Files:**
- Create: `src/spotlab/errors/graphnav.py`, `tests/test_errors_graphnav.py`
- Modify: `src/spotlab/errors/__init__.py`

**Interfaces:**
- Produces:
  - `MapError(SpotlabError)`, `NavigationError(SpotlabError)`, `NotLocalized(SpotlabError)`
  - `AUFNAHME_TEXTE: dict[int, str]` — `StartRecordingResponse.Status` → Klartext
  - `WEGPUNKT_TEXTE: dict[int, str]` — `CreateWaypointResponse.Status` → Klartext
  - `NAVIGATION_TEXTE: dict[int, str]` — `NavigationFeedbackResponse.Status` → Klartext
  - `nav_status(status_wert) -> NavStatus`

- [ ] **Step 1: Fehlschlagenden Test schreiben** — `tests/test_errors_graphnav.py`

```python
from bosdyn.api.graph_nav import graph_nav_pb2, recording_pb2

from spotlab.errors.graphnav import (
    AUFNAHME_TEXTE,
    NAVIGATION_TEXTE,
    WEGPUNKT_TEXTE,
    nav_status,
)


def test_fehlendes_fiducial_sagt_was_zu_tun_ist():
    text = AUFNAHME_TEXTE[recording_pb2.StartRecordingResponse.STATUS_MISSING_FIDUCIALS]
    assert "Fiducial" in text
    assert "hinstellen" in text.lower() or "hin, dass" in text


def test_alte_karte_auf_dem_roboter_wird_erklaert():
    text = AUFNAHME_TEXTE[
        recording_pb2.StartRecordingResponse.STATUS_NOT_LOCALIZED_TO_EXISTING_MAP
    ]
    assert "Karte" in text and "leeren" in text


def test_wegpunkt_ohne_aufnahme():
    text = WEGPUNKT_TEXTE[recording_pb2.CreateWaypointResponse.STATUS_NOT_RECORDING]
    assert "Aufnahme" in text


def test_am_ziel_ist_fertig():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_REACHED_GOAL)
    assert zustand.fertig is True and zustand.gescheitert is False


def test_unterwegs_ist_weder_fertig_noch_gescheitert():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_FOLLOWING_ROUTE)
    assert zustand.fertig is False and zustand.gescheitert is False


def test_verloren_ist_gescheitert_und_deutsch():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_LOST)
    assert zustand.gescheitert is True
    assert "verloren" in zustand.status


def test_steckengeblieben_fragt_nach_hindernissen():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_STUCK)
    assert zustand.gescheitert is True
    assert "Weg" in zustand.status


def test_ohne_lokalisierung_verweist_auf_localize():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_NO_LOCALIZATION)
    assert "localize" in zustand.status


def test_alle_texte_sind_deutsche_saetze():
    for tabelle in (AUFNAHME_TEXTE, WEGPUNKT_TEXTE, NAVIGATION_TEXTE):
        for text in tabelle.values():
            assert text and text[0].isupper() and text.endswith((".", "?"))


def test_unbekannter_status_faellt_nicht_um():
    zustand = nav_status(99999)
    assert zustand.gescheitert is True
    assert zustand.status
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_errors_graphnav.py -q`

- [ ] **Step 3: `errors/graphnav.py` implementieren**

```python
"""GraphNav-Statuscodes in deutschen Klartext.

Dieselbe Arbeit, die errors/translate.py für die Verbindungsseite leistet:
roh sind das englische Enum-Namen, übersetzt sind es Sätze, die einem Schüler
sagen, was zu tun ist.
"""

from bosdyn.api.graph_nav import graph_nav_pb2, recording_pb2

from spotlab.backends.base import NavStatus
from spotlab.errors import SpotlabError

_S = recording_pb2.StartRecordingResponse
_W = recording_pb2.CreateWaypointResponse
_N = graph_nav_pb2.NavigationFeedbackResponse


class MapError(SpotlabError):
    """Etwas mit der Karte stimmt nicht."""


class NavigationError(SpotlabError):
    """Die autonome Fahrt ist gescheitert."""


class NotLocalized(SpotlabError):
    """Der Roboter weiss nicht, wo er auf der Karte steht."""


AUFNAHME_TEXTE = {
    _S.STATUS_MISSING_FIDUCIALS:
        "Der Spot sieht kein Fiducial. Stell ihn so hin, dass eine der Markierungen "
        "im Kamerabild ist, und starte die Aufnahme neu.",
    _S.STATUS_NOT_LOCALIZED_TO_EXISTING_MAP:
        "Auf dem Roboter liegt noch eine andere Karte. Kreuze beim Starten "
        "'Karte auf dem Roboter leeren' an.",
    _S.STATUS_COULD_NOT_CREATE_WAYPOINT:
        "Der Roboter konnte keinen Wegpunkt anlegen. Steht er zu nah an einer Wand?",
    _S.STATUS_FOLLOWING_ROUTE:
        "Der Roboter fährt gerade eine Route ab. Warte, bis er fertig ist.",
    _S.STATUS_TOO_FAR_FROM_EXISTING_MAP:
        "Der Spot steht zu weit von der bestehenden Karte entfernt.",
    _S.STATUS_FIDUCIAL_POSE_NOT_OK:
        "Das Fiducial wurde erkannt, aber die Lage ist unsicher. Fahr näher heran "
        "und achte auf gute Beleuchtung.",
    _S.STATUS_MAP_TOO_LARGE_LICENSE:
        "Die Karte ist zu gross für die Lizenz dieses Roboters.",
    _S.STATUS_ROBOT_IMPAIRED:
        "Der Roboter meldet eine Störung. Prüfe mit 'spotlab doctor'.",
}

WEGPUNKT_TEXTE = {
    _W.STATUS_NOT_RECORDING:
        "Es läuft gerade keine Aufnahme. Starte zuerst die Aufnahme.",
    _W.STATUS_COULD_NOT_CREATE_WAYPOINT:
        "Der Roboter konnte hier keinen Wegpunkt anlegen. Fahr ein Stück weiter.",
    _W.STATUS_MISSING_FIDUCIALS:
        "Der Spot sieht kein Fiducial. Stell ihn so hin, dass eine Markierung "
        "im Kamerabild ist.",
    _W.STATUS_FIDUCIAL_POSE_NOT_OK:
        "Das Fiducial wurde erkannt, aber die Lage ist unsicher.",
    _W.STATUS_MAP_TOO_LARGE_LICENSE:
        "Die Karte ist zu gross für die Lizenz dieses Roboters.",
}

NAVIGATION_TEXTE = {
    _N.STATUS_REACHED_GOAL: "Angekommen.",
    _N.STATUS_FOLLOWING_ROUTE: "Unterwegs.",
    _N.STATUS_NO_ROUTE: "Von hier führt kein Weg zum Ziel.",
    _N.STATUS_NO_LOCALIZATION:
        "Der Spot weiss nicht, wo er ist — rufe zuerst spot.localize() auf.",
    _N.STATUS_NOT_LOCALIZED_TO_ROUTE:
        "Der Spot steht nicht auf dieser Route — verorte ihn neu mit spot.localize().",
    _N.STATUS_LOST:
        "Der Spot hat sich auf der Karte verloren. Fahr ihn zurück zu einem "
        "Fiducial und verorte neu.",
    _N.STATUS_STUCK: "Der Spot kommt nicht weiter. Steht etwas im Weg?",
    _N.STATUS_COMMAND_TIMED_OUT:
        "Das Navigationskommando ist abgelaufen. Das ist ein Fehler in spotlab.",
    _N.STATUS_ROBOT_IMPAIRED:
        "Der Roboter meldet eine Störung. Prüfe mit 'spotlab doctor'.",
    _N.STATUS_CONSTRAINT_FAULT:
        "Die Route lässt sich mit den gesetzten Grenzen nicht abfahren.",
    _N.STATUS_COMMAND_OVERRIDDEN:
        "Ein anderes Kommando hat die Fahrt überschrieben.",
}

_FERTIG = {_N.STATUS_REACHED_GOAL}
_LAEUFT = {_N.STATUS_FOLLOWING_ROUTE}


def nav_status(status_wert):
    """NavigationFeedbackResponse.Status → NavStatus mit deutschem Text."""
    text = NAVIGATION_TEXTE.get(status_wert)
    if text is None:
        return NavStatus(
            fertig=False,
            status=f"Unbekannte Rückmeldung der Navigation ({status_wert}).",
            gescheitert=True,
        )
    if status_wert in _FERTIG:
        return NavStatus(fertig=True, status=text, gescheitert=False)
    if status_wert in _LAEUFT:
        return NavStatus(fertig=False, status=text, gescheitert=False)
    return NavStatus(fertig=False, status=text, gescheitert=True)
```

- [ ] **Step 4: `errors/__init__.py` ergänzen** — am Ende der Datei, nach dem bestehenden `translate`-Import:

```python
from spotlab.errors.graphnav import (  # noqa: E402
    MapError,
    NavigationError,
    NotLocalized,
)

__all__ += ["MapError", "NavigationError", "NotLocalized"]
```

**Achtung Importzyklus:** `errors/graphnav.py` importiert `NavStatus` aus `backends/base.py`, und `backends/base.py` importiert `UnsupportedCapability` aus `errors`. Der Import in `errors/__init__.py` muss deshalb **ganz am Dateiende** stehen, nach der Definition aller Ausnahmeklassen — dann ist `SpotlabError` bereits vorhanden, wenn `graphnav.py` geladen wird.

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_errors_graphnav.py -q`, erwartet 10 PASS. Danach `pytest -q` als Zyklus-Probe.

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/errors tests/test_errors_graphnav.py
git commit -m "feat(errors): GraphNav-Statuscodes in deutschen Klartext"
```

---

## Task 5: Die Aufzeichnungssitzung

**Files:**
- Create: `src/spotlab/maps/session.py`, `tests/test_maps_session.py`

**Interfaces:**
- Consumes: `verbinde`, `AUFNAHME_TEXTE`, `WEGPUNKT_TEXTE`, `MapError`, `store.speichere_metadaten`
- Produces:
  - `RecordingStatus(laeuft: bool, wegpunkte: int, kanten: int, meldung: str)` — frozen dataclass
  - `RecordingSession(robot, recording_client, graph_client)` mit Klassenmethode
    `connect(cfg, verbinder=None) -> RecordingSession`
  - `.start(graph_leeren=False)`, `.waypoint(name) -> str`, `.status() -> RecordingStatus`,
    `.stop()`, `.download(ziel, name, roboter=None) -> Path`, `.close()`

**Leaselos, und das wird geprüft**: kein `LeaseClient`, kein `EstopClient`.

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_maps_session.py`

```python
import pytest
from bosdyn.api.graph_nav import map_pb2, recording_pb2

from spotlab.errors import MapError
from spotlab.maps.session import RecordingSession, RecordingStatus


class FakeRecording:
    def __init__(self, start_status=None, wegpunkt_status=None):
        self.protokoll = []
        self._start_status = (
            recording_pb2.StartRecordingResponse.STATUS_OK
            if start_status is None else start_status)
        self._wegpunkt_status = (
            recording_pb2.CreateWaypointResponse.STATUS_OK
            if wegpunkt_status is None else wegpunkt_status)
        self.laeuft = False

    def start_recording_full(self, **kw):
        self.protokoll.append("start")
        antwort = recording_pb2.StartRecordingResponse(status=self._start_status)
        if self._start_status == recording_pb2.StartRecordingResponse.STATUS_OK:
            self.laeuft = True
        return antwort

    def stop_recording(self, **kw):
        self.protokoll.append("stop")
        self.laeuft = False

    def create_waypoint(self, waypoint_name=None, **kw):
        self.protokoll.append(f"waypoint:{waypoint_name}")
        antwort = recording_pb2.CreateWaypointResponse(status=self._wegpunkt_status)
        antwort.created_waypoint.id = "wp-neu"
        return antwort

    def get_record_status(self, **kw):
        antwort = recording_pb2.GetRecordStatusResponse(is_recording=self.laeuft)
        antwort.map_stats.waypoints.count = 7
        antwort.map_stats.edges.count = 6
        return antwort


class FakeGraphNav:
    def __init__(self):
        self.protokoll = []

    def clear_graph(self, **kw):
        self.protokoll.append("clear")

    def download_graph(self, **kw):
        graph = map_pb2.Graph()
        graph.waypoints.add().id = "wp0"
        return graph

    def write_graph_and_snapshots(self, verzeichnis):
        self.protokoll.append(f"write:{verzeichnis}")


def _sitzung(**kw):
    return RecordingSession(robot=object(), recording_client=FakeRecording(**kw),
                            graph_client=FakeGraphNav())


def test_start_stop_reihenfolge():
    sitzung = _sitzung()
    sitzung.start()
    sitzung.stop()
    assert sitzung._recording.protokoll == ["start", "stop"]


def test_graph_leeren_vor_dem_start():
    sitzung = _sitzung()
    sitzung.start(graph_leeren=True)
    assert sitzung._graph.protokoll == ["clear"]
    assert sitzung._recording.protokoll == ["start"]


def test_ohne_leeren_wird_nichts_geloescht():
    sitzung = _sitzung()
    sitzung.start()
    assert sitzung._graph.protokoll == []


def test_fehlendes_fiducial_wird_zu_klartext():
    sitzung = _sitzung(
        start_status=recording_pb2.StartRecordingResponse.STATUS_MISSING_FIDUCIALS)
    with pytest.raises(MapError) as info:
        sitzung.start()
    assert "Fiducial" in str(info.value)


def test_alte_karte_nennt_den_ausweg():
    sitzung = _sitzung(
        start_status=recording_pb2.StartRecordingResponse.STATUS_NOT_LOCALIZED_TO_EXISTING_MAP)
    with pytest.raises(MapError) as info:
        sitzung.start()
    assert "leeren" in str(info.value)


def test_wegpunkt_gibt_die_id_zurueck():
    sitzung = _sitzung()
    sitzung.start()
    assert sitzung.waypoint("kueche") == "wp-neu"
    assert "waypoint:kueche" in sitzung._recording.protokoll


def test_wegpunkt_ohne_aufnahme_wird_zu_klartext():
    sitzung = _sitzung(
        wegpunkt_status=recording_pb2.CreateWaypointResponse.STATUS_NOT_RECORDING)
    with pytest.raises(MapError) as info:
        sitzung.waypoint("kueche")
    assert "Aufnahme" in str(info.value)


def test_status_kommt_aus_map_stats():
    sitzung = _sitzung()
    sitzung.start()
    zustand = sitzung.status()
    assert isinstance(zustand, RecordingStatus)
    assert zustand.laeuft is True
    assert zustand.wegpunkte == 7 and zustand.kanten == 6


def test_status_vor_dem_start():
    assert _sitzung().status().laeuft is False


def test_download_schreibt_und_legt_metadaten_an(tmp_path):
    sitzung = _sitzung()
    ziel = sitzung.download(tmp_path, name="turnhalle", roboter="SN-1")
    assert f"write:{ziel}" in sitzung._graph.protokoll
    assert (ziel / "karte.json").exists()


def test_session_ist_leaselos():
    """Grundsatzentscheidung N2: maps/ nimmt keine Kontrolle an sich."""
    import pathlib

    import spotlab.maps.session as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    assert "LeaseClient" not in quelle
    assert "EstopClient" not in quelle
    assert "EstopEndpoint" not in quelle
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_maps_session.py -q`

- [ ] **Step 3: `maps/session.py` implementieren**

```python
"""Eine Kartenaufzeichnung — leaselos.

Der Ablauf im Unterricht: Aufnahme starten, den Spot MIT DEM TABLET durch den
Raum fahren, dabei entstehen automatisch Wegpunkte, an interessanten Stellen
eine benannte Marke setzen, am Ende beenden und herunterladen.

Laut SDK-README braucht der Aufzeichnungsdienst kein Lease und keinen E-Stop:
er läuft passiv mit, während ein anderer Dienst den Roboter steuert. Genau
deshalb darf die GUI ihn bedienen, ohne H1 zu brechen — und deshalb kommt in
dieser Datei kein Lease- und kein E-Stop-Client vor.
"""

from dataclasses import dataclass
from pathlib import Path

from bosdyn.api.graph_nav import recording_pb2
from bosdyn.client.graph_nav import GraphNavClient
from bosdyn.client.recording import GraphNavRecordingServiceClient

from spotlab.errors import MapError, translate
from spotlab.errors.graphnav import AUFNAHME_TEXTE, WEGPUNKT_TEXTE
from spotlab.maps.store import sicherer_name, speichere_metadaten

_S = recording_pb2.StartRecordingResponse
_W = recording_pb2.CreateWaypointResponse


@dataclass(frozen=True)
class RecordingStatus:
    laeuft: bool
    wegpunkte: int
    kanten: int
    meldung: str


class RecordingSession:
    def __init__(self, robot, recording_client, graph_client):
        self._robot = robot
        self._recording = recording_client
        self._graph = graph_client

    @classmethod
    def connect(cls, cfg, verbinder=None):
        from spotlab.backends.real.verbindung import verbinde

        robot = (verbinder or verbinde)(cfg)
        return cls(
            robot=robot,
            recording_client=robot.ensure_client(
                GraphNavRecordingServiceClient.default_service_name),
            graph_client=robot.ensure_client(GraphNavClient.default_service_name),
        )

    # ------------------------------------------------------------- Aufnahme

    def start(self, graph_leeren=False):
        if graph_leeren:
            self._versuche(self._graph.clear_graph, "Karte auf dem Roboter leeren")
        antwort = self._versuche(self._recording.start_recording_full,
                                 "Aufnahme starten")
        if antwort.status != _S.STATUS_OK:
            raise MapError(
                AUFNAHME_TEXTE.get(
                    antwort.status,
                    f"Die Aufnahme liess sich nicht starten (Status {antwort.status})."))

    def waypoint(self, name):
        antwort = self._versuche(
            lambda: self._recording.create_waypoint(waypoint_name=sicherer_name(name)),
            "Wegpunkt setzen")
        if antwort.status != _W.STATUS_OK:
            raise MapError(
                WEGPUNKT_TEXTE.get(
                    antwort.status,
                    f"Der Wegpunkt liess sich nicht setzen (Status {antwort.status})."))
        return antwort.created_waypoint.id

    def stop(self):
        self._versuche(self._recording.stop_recording, "Aufnahme beenden")

    def status(self):
        try:
            antwort = self._recording.get_record_status()
        except Exception as fehler:
            return RecordingStatus(False, 0, 0, f"Status nicht abrufbar: {fehler}")
        return RecordingStatus(
            laeuft=bool(antwort.is_recording),
            wegpunkte=int(antwort.map_stats.waypoints.count),
            kanten=int(antwort.map_stats.edges.count),
            meldung="Aufnahme läuft" if antwort.is_recording else "Keine Aufnahme",
        )

    # ------------------------------------------------------------- Speichern

    def download(self, wurzel, name, roboter=None):
        """Karte in <wurzel>/<name>/ ablegen. Gibt den Ordner zurück."""
        ziel = Path(wurzel) / sicherer_name(name)
        ziel.mkdir(parents=True, exist_ok=True)
        self._versuche(lambda: self._graph.write_graph_and_snapshots(str(ziel)),
                       "Karte herunterladen")
        graph = self._versuche(self._graph.download_graph, "Karte lesen")
        speichere_metadaten(ziel, sicherer_name(name), roboter, graph)
        return ziel

    def close(self):
        pass          # kein Lease, kein E-Stop — es gibt nichts freizugeben

    # ------------------------------------------------------------- intern

    @staticmethod
    def _versuche(aufruf, was):
        try:
            return aufruf()
        except Exception as fehler:
            uebersetzt = translate(fehler)
            if uebersetzt is not None:
                raise uebersetzt from fehler
            raise MapError(f"{was} ist fehlgeschlagen: {fehler}") from fehler
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_maps_session.py -q`, erwartet 11 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/maps/session.py tests/test_maps_session.py
git commit -m "feat(maps): leaselose Aufzeichnungssitzung"
```

---

## Task 6: Der optionale GraphNav-Protokollteil

**Files:**
- Create: `src/spotlab/backends/real/graphnav.py`, `tests/test_real_graphnav.py`
- Modify: `src/spotlab/backends/real/session.py`

**Interfaces:**
- Consumes: `nav_status`, `NotLocalized`, `MapError`
- Produces, alle in `graphnav.py` als freie Funktionen auf einem `robot`:
  - `clear_map(robot) -> None`
  - `upload_map(robot, kartenordner) -> map_pb2.Graph`
  - `localize(robot) -> str`
  - `travel_params(limits, max_distance=0.4, max_yaw=0.15)` → `graph_nav_pb2.TravelParams`
  - `navigate_step(robot, waypoint_id, dauer_s, params, command_id=None) -> int`
  - `navigation_status(robot, command_id) -> NavStatus`
- `RealSpot` bekommt `Capability.GRAPH_NAV` und reicht `self._robot` über die vorhandene
  Eigenschaft `robot` durch (bereits vorhanden, keine Änderung nötig)

- [ ] **Step 1: Fehlschlagende Tests schreiben** — `tests/test_real_graphnav.py`

```python
import pytest
from bosdyn.api.graph_nav import graph_nav_pb2, map_pb2

from spotlab.backends.base import Capability
from spotlab.backends.real.graphnav import (
    localize,
    navigate_step,
    navigation_status,
    travel_params,
    upload_map,
)
from spotlab.config import Limits
from spotlab.errors import NotLocalized


class FakeGraphNav:
    def __init__(self, unbekannte_snapshots=()):
        self.protokoll = []
        self._unbekannt = list(unbekannte_snapshots)
        self.letzte_params = None

    def clear_graph(self, **kw):
        self.protokoll.append("clear")

    def upload_graph(self, graph=None, generate_new_anchoring=False, **kw):
        self.protokoll.append(f"upload_graph:{len(graph.waypoints)}")
        antwort = graph_nav_pb2.UploadGraphResponse()
        for kennung in self._unbekannt:
            antwort.unknown_waypoint_snapshot_ids.append(kennung)
        return antwort

    def upload_waypoint_snapshot(self, waypoint_snapshot, **kw):
        self.protokoll.append(f"upload_wp:{waypoint_snapshot.id}")

    def upload_edge_snapshot(self, edge_snapshot, **kw):
        self.protokoll.append(f"upload_edge:{edge_snapshot.id}")

    def set_localization(self, initial_guess_localization, fiducial_init=None, **kw):
        self.protokoll.append(f"localize:{fiducial_init}")

    def get_localization_state(self, **kw):
        antwort = graph_nav_pb2.GetLocalizationStateResponse()
        antwort.localization.waypoint_id = "wp-hier"
        return antwort

    def navigate_to(self, destination_waypoint_id, cmd_duration, travel_params=None,
                    command_id=None, **kw):
        self.letzte_params = travel_params
        self.protokoll.append(f"nav:{destination_waypoint_id}:{cmd_duration}")
        return 42

    def navigation_feedback(self, command_id=0, **kw):
        antwort = graph_nav_pb2.NavigationFeedbackResponse()
        antwort.status = graph_nav_pb2.NavigationFeedbackResponse.STATUS_REACHED_GOAL
        return antwort


class FakeRobot:
    def __init__(self, graphnav):
        self._graphnav = graphnav

    def ensure_client(self, name):
        return self._graphnav


def _karte(tmp_path, snapshots=()):
    graph = map_pb2.Graph()
    wp = graph.waypoints.add()
    wp.id = "wp0"
    wp.snapshot_id = "snap0"
    ordner = tmp_path / "turnhalle"
    (ordner / "waypoint_snapshots").mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    for kennung in snapshots:
        schnappschuss = map_pb2.WaypointSnapshot()
        schnappschuss.id = kennung
        (ordner / "waypoint_snapshots" / kennung).write_bytes(
            schnappschuss.SerializeToString())
    return ordner


def test_hochladen_leert_zuerst_und_laedt_dann(tmp_path):
    fake = FakeGraphNav()
    upload_map(FakeRobot(fake), _karte(tmp_path))
    assert fake.protokoll[0] == "clear"
    assert "upload_graph:1" in fake.protokoll


def test_fehlende_schnappschuesse_werden_nachgeladen(tmp_path):
    fake = FakeGraphNav(unbekannte_snapshots=["snap0"])
    upload_map(FakeRobot(fake), _karte(tmp_path, snapshots=["snap0"]))
    assert "upload_wp:snap0" in fake.protokoll


def test_lokalisieren_nutzt_das_naechste_fiducial():
    fake = FakeGraphNav()
    kennung = localize(FakeRobot(fake))
    assert kennung == "wp-hier"
    erwartet = graph_nav_pb2.SetLocalizationRequest.FIDUCIAL_INIT_NEAREST
    assert f"localize:{erwartet}" in fake.protokoll


def test_lokalisieren_ohne_ergebnis_wirft_klartext():
    class OhneVerortung(FakeGraphNav):
        def get_localization_state(self, **kw):
            return graph_nav_pb2.GetLocalizationStateResponse()

    with pytest.raises(NotLocalized) as info:
        localize(FakeRobot(OhneVerortung()))
    assert "Fiducial" in str(info.value)


def test_travel_params_tragen_den_geschwindigkeitsdeckel():
    params = travel_params(Limits(max_speed=0.35, max_turn_rate=0.5))
    assert abs(params.velocity_limit.max_vel.linear.x - 0.35) < 1e-9
    assert abs(params.velocity_limit.max_vel.angular - 0.5) < 1e-9


def test_travel_params_setzen_auch_die_untergrenze():
    """Ohne min_vel bremst der Roboter nur vorwärts, nicht rückwärts."""
    params = travel_params(Limits(max_speed=0.35, max_turn_rate=0.5))
    assert abs(params.velocity_limit.min_vel.linear.x + 0.35) < 1e-9


def test_navigationsschritt_reicht_params_durch():
    fake = FakeGraphNav()
    params = travel_params(Limits())
    kennung = navigate_step(FakeRobot(fake), "wp1", 1.0, params)
    assert kennung == 42
    assert fake.letzte_params is params
    assert "nav:wp1:1.0" in fake.protokoll


def test_rueckmeldung_wird_uebersetzt():
    zustand = navigation_status(FakeRobot(FakeGraphNav()), 42)
    assert zustand.fertig is True
    assert "Angekommen" in zustand.status


def test_realspot_kann_graph_nav():
    from spotlab.backends.real.session import RealSpot

    koennen = RealSpot.capabilities(None)
    assert koennen & Capability.GRAPH_NAV
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_real_graphnav.py -q`

- [ ] **Step 3: `backends/real/graphnav.py` implementieren**

```python
"""GraphNav am echten Roboter: hochladen, verorten, fahren.

Freie Funktionen auf einem robot-Objekt statt einer Klasse — dieser
Protokollteil ist optional (nur RealSpot erfüllt ihn) und hat keinen eigenen
Zustand ausser dem, was ohnehin auf dem Roboter liegt.
"""

from pathlib import Path

from bosdyn.api import geometry_pb2
from bosdyn.api.graph_nav import graph_nav_pb2, map_pb2, nav_pb2
from bosdyn.client.graph_nav import GraphNavClient

from spotlab.errors import MapError, NotLocalized
from spotlab.errors.graphnav import nav_status

FIDUCIAL_NEAREST = graph_nav_pb2.SetLocalizationRequest.FIDUCIAL_INIT_NEAREST


def _client(robot):
    return robot.ensure_client(GraphNavClient.default_service_name)


def clear_map(robot):
    _client(robot).clear_graph()


def upload_map(robot, kartenordner):
    """Karte aus dem Ordner auf den Roboter laden. Gibt den Graphen zurück.

    Fehlende Schnappschüsse werden nachgereicht: der Roboter meldet in
    unknown_*_snapshot_ids, was ihm fehlt.
    """
    ordner = Path(kartenordner)
    graph = map_pb2.Graph()
    try:
        graph.ParseFromString((ordner / "graph").read_bytes())
    except OSError as fehler:
        raise MapError(f"Die Karte in {ordner} lässt sich nicht lesen.") from fehler

    client = _client(robot)
    client.clear_graph()
    antwort = client.upload_graph(graph=graph, generate_new_anchoring=True)

    for kennung in antwort.unknown_waypoint_snapshot_ids:
        pfad = ordner / "waypoint_snapshots" / kennung
        if not pfad.exists():
            continue
        schnappschuss = map_pb2.WaypointSnapshot()
        schnappschuss.ParseFromString(pfad.read_bytes())
        client.upload_waypoint_snapshot(schnappschuss)

    for kennung in antwort.unknown_edge_snapshot_ids:
        pfad = ordner / "edge_snapshots" / kennung
        if not pfad.exists():
            continue
        schnappschuss = map_pb2.EdgeSnapshot()
        schnappschuss.ParseFromString(pfad.read_bytes())
        client.upload_edge_snapshot(schnappschuss)

    return graph


def localize(robot):
    """Über das nächste sichtbare Fiducial verorten. Gibt die Wegpunkt-ID zurück."""
    client = _client(robot)
    client.set_localization(
        initial_guess_localization=nav_pb2.Localization(),
        fiducial_init=FIDUCIAL_NEAREST,
    )
    kennung = client.get_localization_state().localization.waypoint_id
    if not kennung:
        raise NotLocalized(
            "Der Spot konnte sich nicht verorten. Stell ihn so hin, dass ein "
            "Fiducial im Kamerabild ist, und versuche es noch einmal."
        )
    return kennung


def travel_params(limits, max_distance=0.4, max_yaw=0.15):
    """TravelParams mit unserem Geschwindigkeitsdeckel.

    Ohne velocity_limit führe die autonome Fahrt schneller als die von Hand
    gesteuerte — der Deckel aus config.toml gilt sonst nur für walk() und
    move(). min_vel muss mitgesetzt werden, sonst bremst nur die Vorwärtsfahrt.
    """
    grenze = geometry_pb2.SE2VelocityLimit(
        max_vel=geometry_pb2.SE2Velocity(
            linear=geometry_pb2.Vec2(x=limits.max_speed, y=limits.max_speed),
            angular=limits.max_turn_rate,
        ),
        min_vel=geometry_pb2.SE2Velocity(
            linear=geometry_pb2.Vec2(x=-limits.max_speed, y=-limits.max_speed),
            angular=-limits.max_turn_rate,
        ),
    )
    return GraphNavClient.generate_travel_params(max_distance, max_yaw, grenze)


def navigate_step(robot, waypoint_id, dauer_s, params, command_id=None):
    """Ein Navigationskommando absetzen. Gibt die Kommando-ID zurück.

    Navigationskommandos verfallen wie Geschwindigkeitskommandos; der Aufrufer
    ruft das hier in einer Schleife auf.
    """
    return _client(robot).navigate_to(
        waypoint_id, dauer_s, travel_params=params, command_id=command_id)


def navigation_status(robot, command_id):
    antwort = _client(robot).navigation_feedback(command_id=command_id)
    return nav_status(antwort.status)
```

- [ ] **Step 4: `RealSpot` um die Fähigkeit erweitern** — in `backends/real/session.py` in `capabilities()` ergänzen:

```python
            | Capability.GRAPH_NAV
```

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_real_graphnav.py -q`, erwartet 9 PASS

- [ ] **Step 6: Gesamtsuite** — `pytest -q`

- [ ] **Step 7: Commit**

```bash
git add src/spotlab/backends/real tests/test_real_graphnav.py
git commit -m "feat(real): GraphNav hochladen, verorten, fahren mit Geschwindigkeitsdeckel"
```

---

*Fortsetzung: `2026-08-07-spotlab-graphnav-teil2.md` (Tasks 7–12: Verben, GUI, CLI, Doku).*
