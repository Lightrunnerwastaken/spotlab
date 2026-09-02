# spotlab Stufe 9 „Umwelt" — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spot beantwortet „was siehst du gerade" als Schüler-API, als GUI-Ansicht und als leaselose Sonde; die Geräte-Diagnose sagt autoritativ, was dieser Roboter kann.

**Architecture:** Neutrale Datenklassen in `backends/base.py`, Protokollarbeit in `backends/real/wahrnehmung.py`, Verben in `api/world.py`, Attrappen in `dryrun`/`sim`. Die GUI bleibt SDK-frei und liest ausschliesslich Lauf-Verzeichnisse; die Sonde läuft als gewöhnliches Skript über den vorhandenen `workshop/launcher.py`. `matura-spot` wird zuletzt Klient.

**Tech Stack:** Python 3.11+, bosdyn-client 5.0.1.2 (`world_object`, `local_grid`, `license`, `payload`), PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-spotlab-umwelt-design.md`

**Zweig:** `stufe-9-umwelt` (bereits angelegt, Spec committet als `74c7397`)

## Global Constraints

- **Einheiten:** Peilung in **Grad**, links positiv; Distanz in **Meter**, in der Bodenebene. Nie Radiant nach aussen.
- **Bezeichner englisch, Meldungen deutsch.** `api/` ist durchgehend englisch; Fehlertexte und Docstrings deutsch.
- **`api/` bleibt protobuf-frei.** Kein `bosdyn`-Import in `api/world.py`.
- **`gui/` bleibt SDK-frei.** Laut CLAUDE.md: **kein `import bosdyn` UND kein
  `import spotlab.backends` unterhalb von `src/spotlab/gui/`** — auch nicht
  mittelbar. Deshalb dekodiert die GUI kein Protobuf; siehe Task 6.
- **Neue Faehigkeit ⇒ Eintrag in `Capability`, Pruefung ueber `require()`, UND ein
  neuer Punkt in `docs/ABNAHME.md`** (CLAUDE.md). Gilt fuer WORLD_OBJECTS und LOCAL_GRID.
- **Jede Abhaengigkeit hat eine Obergrenze** in `pyproject.toml` (CLAUDE.md).
- **Farben nur aus `gui/theme.py`** — kein Farbliteral in der neuen Ansicht.
- **`ruff check .` muss gruen sein**, und zwar vor den Tests.
- **Schichtrichtung:** `backends/` importiert **nie** aus `api/`. (Deshalb die Abweichung unten.)
- **„Nichts gesehen" ist eine Antwort:** leere Rückgabe ist `[]`, nie `None`, nie eine Ausnahme.
- **Diagnose-Zeilen, deren Abfrage scheitert, sind `ok=True`** mit Detail „nicht ermittelbar" — ein fehlender Befund ist kein Defekt.
- Jeder Task endet mit einem Commit. Deutsche Commit-Botschaften ohne Umlaute (Repo-Konvention: `feat(karte): ... Karten-Panel war diagonal gespiegelt`).

### Begründete Abweichungen von der Spec

**(2) Objektabfragen gehen nach `ereignisse.jsonl`, nicht nach `zustand.jsonl`.**
Die Spec (§4.2, §5) nennt `Recorder.sample()`. Bei der Umsetzung zeigte sich: das
etablierte Muster fuer „ein Verb wurde aufgerufen" ist `_protokolliere` in
`api/navigation.py`, und das schreibt `recorder.event("kommando", …)` nach
`ereignisse.jsonl`. `zustand.jsonl` ist der 10-Hz-Telemetriestrom mit festen
Schluesseln, die laut CLAUDE.md unveraendert bleiben muessen. Eine Abfrage ist ein
Ereignis, kein Abtastwert. Die Ansicht (Task 8) liest entsprechend
`ereignisse.jsonl`.

### (1) Begründete Abweichung von der Spec

Die Spec (§3, §4.1) legt die Datenklassen nach `api/world.py`. Bei der Umsetzung zeigte sich: **`backends/` importiert heute nirgends aus `api/`**, und der reale Backend muss die Protobuf→Datenklasse-Umwandlung machen (nur dort ist `frame_helpers` zu Hause). Die Datenklassen liegen deshalb in **`backends/base.py`**, neben `Feedback` und `NavStatus`, deren Docstring genau diese Naht begründet („api/ bleibt dadurch protobuf-frei"). `api/world.py` re-exportiert sie, damit `from spotlab.api.world import Tag` weiterhin die Schülerschnittstelle ist. `backends/base.py` importiert nur `enum`, `dataclasses`, `typing` und `spotlab.errors` — es ist SDK-frei, die GUI kann daraus importieren.

---

## File Structure

| Datei | Verantwortung | Task |
|---|---|---|
| `src/spotlab/backends/base.py` | + `WorldObject`, `Tag`, `ObstacleGrid`, 2 Capabilities, 2 Protokollmethoden | 1, 2 |
| `src/spotlab/api/world.py` | Verben + Re-Export der Datenklassen | 1, 3 |
| `src/spotlab/backends/dryrun.py` | deterministische Attrappe | 2 |
| `src/spotlab/backends/sim.py` | leere, ehrliche Antwort | 2 |
| `src/spotlab/api/spot.py` | drei Fassadenmethoden | 4 |
| `src/spotlab/backends/real/wahrnehmung.py` | SDK: WorldObject- und LocalGrid-Client | 5 |
| `src/spotlab/beobachtung/gitter.py` | Gitter-Mitschnitt (Umzug aus matura-spot) | 6 |
| `src/spotlab/workshop/sonde.py` | leaselose Abfrage als Skript | 7 |
| `src/spotlab/gui/views/umwelt.py` | Ansicht „Umwelt" | 8 |
| `src/spotlab/workshop/doctor.py` | + Lizenz, Nutzlasten, Dienste, Zertifikat | 9, 10 |
| `src/spotlab/workshop/zertifikat.py` | TLS-Zertifikat ungeprüft abholen | 10 |
| `src/spotlab/gui/views/checkup.py` | + Abschnitt „Gerät", kopierbar | 9 |

---

## Task 1: Datenklassen und Umrechnung

**Files:**
- Modify: `src/spotlab/backends/base.py` (nach `NavStatus`, vor `SafetyStatus`)
- Create: `src/spotlab/api/world.py`
- Test: `tests/test_api_world.py`

**Interfaces:**
- Consumes: nichts
- Produces: `WorldObject(name, kind, bearing, distance, world_xy, time)`, `Tag(… , id, filtered)`, `ObstacleGrid(cells, cell_size, origin, time)` mit `distance_at(x, y)` und `is_free(x, y, margin=0.3)`; `richtung(x, y) -> (bearing_grad, distance_m)`

- [ ] **Step 1: Write the failing test**

`tests/test_api_world.py`:

```python
import math

import pytest

from spotlab.api.world import ObstacleGrid, Tag, WorldObject, richtung


def test_richtung_rechnet_in_grad_und_meter():
    bearing, distance = richtung(3.0, 4.0)
    assert distance == pytest.approx(5.0)
    assert bearing == pytest.approx(math.degrees(math.atan2(4.0, 3.0)))


def test_richtung_links_ist_positiv():
    links, _ = richtung(1.0, 1.0)
    rechts, _ = richtung(1.0, -1.0)
    assert links > 0
    assert rechts < 0


def test_richtung_geradeaus_ist_null_grad():
    bearing, distance = richtung(2.0, 0.0)
    assert bearing == pytest.approx(0.0)
    assert distance == pytest.approx(2.0)


def test_tag_erbt_die_felder_des_objekts():
    tag = Tag(
        name="world_obj_apriltag_001", kind="apriltag", bearing=-23.4,
        distance=2.7, world_xy=(1.0, 2.0), time=100.0, id=1, filtered=True,
    )
    assert isinstance(tag, WorldObject)
    assert tag.id == 1
    assert tag.kind == "apriltag"


def test_gitter_meldet_abstand_und_freiheit():
    import numpy as np

    zellen = np.full((10, 10), 2.0)
    zellen[5, 5] = 0.1
    gitter = ObstacleGrid(cells=zellen, cell_size=0.03, origin=(0.0, 0.0), time=100.0)
    assert gitter.distance_at(5 * 0.03, 5 * 0.03) == pytest.approx(0.1)
    assert not gitter.is_free(5 * 0.03, 5 * 0.03, margin=0.3)
    assert gitter.is_free(1 * 0.03, 1 * 0.03, margin=0.3)


def test_gitter_ausserhalb_gilt_als_unbekannt_nicht_als_frei():
    import numpy as np

    gitter = ObstacleGrid(
        cells=np.full((10, 10), 2.0), cell_size=0.03, origin=(0.0, 0.0), time=100.0
    )
    assert gitter.distance_at(99.0, 99.0) is None
    assert not gitter.is_free(99.0, 99.0)


def test_unbeobachtete_zelle_ist_nicht_frei_obwohl_der_wert_gross_ist():
    """Der Fehler, der einen Roboter in eine Wand faehrt: Unbekannt != frei."""
    import numpy as np

    bekannt = np.ones((10, 10), dtype=bool)
    bekannt[3, 3] = False
    gitter = ObstacleGrid(
        cells=np.full((10, 10), 5.0), cell_size=0.03, origin=(0.0, 0.0),
        time=100.0, known=bekannt,
    )
    assert gitter.distance_at(3 * 0.03, 3 * 0.03) is None
    assert not gitter.is_free(3 * 0.03, 3 * 0.03)
    assert gitter.is_free(4 * 0.03, 4 * 0.03)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_world.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.api.world'`

- [ ] **Step 3: Write minimal implementation**

In `src/spotlab/backends/base.py`, direkt nach `NavStatus`:

```python
@dataclass(frozen=True)
class WorldObject:
    """Ein Objekt, das Spots Firmware gerade führt — backend-unabhängig.

    Dieselbe Naht wie Feedback und NavStatus: der Backend wandelt Protobufs
    hier hinein, damit api/ protobuf-frei bleibt.
    """

    name: str
    kind: str            # "apriltag" | "dock" | "door" | "image_coordinates" | …
    bearing: float       # Grad, links positiv, im Koerper-Frame
    distance: float      # Meter, in der Bodenebene
    world_xy: tuple | None   # Position im vision-Frame
    time: float          # Erfassungszeitpunkt, Zeitbasis wie zustand.jsonl


@dataclass(frozen=True)
class Tag(WorldObject):
    """Ein AprilTag — ein WorldObject mit aufgedruckter Nummer."""

    id: int
    filtered: bool       # geglaettete Pose (True) oder rohe Einzelmessung


@dataclass(frozen=True)
class ObstacleGrid:
    """Spots Hindernisgitter: je Zelle der Abstand zum naechsten Hindernis.

    `known` traegt Spots eigene Aussage darueber, welche Zellen ueberhaupt
    beobachtet wurden. Ohne diese Maske laese man unbeobachtete Zellen als
    "frei" — genau der Optimismus, der einen Roboter in eine Wand faehrt.
    """

    cells: "object"      # np.ndarray, Meter je Zelle
    cell_size: float     # Kantenlaenge einer Zelle, Meter
    origin: tuple        # Weltkoordinate der Zelle [0, 0]
    time: float
    known: "object" = None   # np.ndarray bool, oder None = alles bekannt

    def _zelle(self, x, y):
        spalte = int(round((x - self.origin[0]) / self.cell_size))
        zeile = int(round((y - self.origin[1]) / self.cell_size))
        hoehe, breite = self.cells.shape
        if not (0 <= zeile < hoehe and 0 <= spalte < breite):
            return None
        return zeile, spalte

    def distance_at(self, x, y):
        """Meter bis zum naechsten Hindernis.

        None, wenn die Stelle ausserhalb des Gitters liegt ODER Spot sie nicht
        beobachtet hat. Eine fehlende Zahl ist ehrlicher als eine erfundene.
        """
        ort = self._zelle(x, y)
        if ort is None:
            return None
        zeile, spalte = ort
        if self.known is not None and not bool(self.known[zeile, spalte]):
            return None
        return float(self.cells[zeile, spalte])

    def is_free(self, x, y, margin=0.3):
        """Ist dort Platz? Unbekannt gilt als NICHT frei — Vorsicht vor Optimismus."""
        abstand = self.distance_at(x, y)
        return abstand is not None and abstand >= margin
```

`src/spotlab/api/world.py`:

```python
"""Was Spot gerade sieht: Objekte, AprilTags, Hindernisgitter.

Alles in Grad und Metern, damit `spot.move(turn=tag.bearing)` ohne Umrechnung
funktioniert. Die Datenklassen liegen in `backends/base.py` neben Feedback und
NavStatus — dort, wo die backend-unabhaengigen Formen wohnen — und werden hier
re-exportiert, weil `from spotlab.api.world import Tag` die Schuelertuer ist.
"""

import math

from spotlab.backends.base import ObstacleGrid, Tag, WorldObject  # noqa: F401  (Re-Export)

__all__ = ["WorldObject", "Tag", "ObstacleGrid", "richtung"]


def richtung(x, y):
    """Aus einer Position im Koerper-Frame: (Peilung in Grad, Distanz in Meter).

    Links positiv, wie bei `move(left=…)`. Die Distanz liegt in der Bodenebene:
    ein Tag haengt auf Kniehoehe, seine Hoehe interessiert beim Hinfahren
    niemanden.
    """
    return math.degrees(math.atan2(y, x)), math.hypot(x, y)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_world.py -v`
Expected: PASS, 7 Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/base.py src/spotlab/api/world.py tests/test_api_world.py
git commit -m "feat(umwelt): Datenklassen und Grad-Umrechnung fuer Objekte und Gitter"
```

---

## Task 2: Fähigkeiten und Attrappen

**Files:**
- Modify: `src/spotlab/backends/base.py` (`Capability`, `_EINZELN`, `SpotBackend`)
- Modify: `src/spotlab/backends/dryrun.py`
- Modify: `src/spotlab/backends/sim.py`
- Test: `tests/test_dryrun.py` (anhängen), `tests/test_backend_base.py` (anhängen)

**Interfaces:**
- Consumes: `WorldObject`, `Tag`, `ObstacleGrid` aus Task 1
- Produces: `Capability.WORLD_OBJECTS`, `Capability.LOCAL_GRID`; Backend-Methoden `world_objects(kinds=None) -> list[WorldObject]` und `local_grid() -> ObstacleGrid`

- [ ] **Step 1: Write the failing test**

An `tests/test_dryrun.py` anhängen:

```python
def test_dryrun_meldet_wahrnehmungsfaehigkeiten():
    from spotlab.backends.base import Capability

    backend = DryRunBackend()
    assert backend.capabilities() & Capability.WORLD_OBJECTS
    assert backend.capabilities() & Capability.LOCAL_GRID


def test_dryrun_liefert_zwei_tags_und_ein_dock():
    backend = DryRunBackend()
    objekte = backend.world_objects()
    arten = sorted(o.kind for o in objekte)
    assert arten == ["apriltag", "apriltag", "dock"]


def test_dryrun_tags_sind_deterministisch():
    erste = DryRunBackend().world_objects()
    zweite = DryRunBackend().world_objects()
    assert [(o.name, o.distance) for o in erste] == [(o.name, o.distance) for o in zweite]


def test_dryrun_filtert_nach_art():
    backend = DryRunBackend()
    nur_tags = backend.world_objects(kinds=["apriltag"])
    assert len(nur_tags) == 2
    assert all(o.kind == "apriltag" for o in nur_tags)


def test_dryrun_gitter_hat_eine_wand():
    backend = DryRunBackend()
    gitter = backend.local_grid()
    assert gitter.cell_size > 0
    assert gitter.cells.min() < 0.2      # irgendwo ist die Wand
    assert gitter.cells.max() > 1.0      # und irgendwo ist frei
```

An `tests/test_backend_base.py` anhängen:

```python
def test_neue_faehigkeiten_sind_einzeln_lesbar():
    from spotlab.backends.base import Capability, _lesbar

    text = _lesbar(Capability.WORLD_OBJECTS | Capability.LOCAL_GRID)
    assert "world_objects" in text
    assert "local_grid" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dryrun.py tests/test_backend_base.py -v -k "wahrnehmung or tags or dock or gitter or faehigkeiten"`
Expected: FAIL — `AttributeError: WORLD_OBJECTS`

- [ ] **Step 3: Write minimal implementation**

In `backends/base.py`, in `Capability` nach `GRAPH_NAV`:

```python
    WORLD_OBJECTS = enum.auto()
    LOCAL_GRID = enum.auto()
```

In `_EINZELN` ergänzen: `Capability.WORLD_OBJECTS,` und `Capability.LOCAL_GRID,`

Im `SpotBackend`-Protocol ergänzen:

```python
    def world_objects(self, kinds=None) -> list: ...
    def local_grid(self): ...
```

In `backends/dryrun.py`:

```python
import numpy as np

from spotlab.backends.base import Capability, Feedback, ObstacleGrid, SafetyStatus, Tag, WorldObject

# Feste Attrappen-Umgebung: zwei Tags und ein Dock in bekannter Lage, eine Wand
# bei y = 2 m. Deterministisch, damit Tests darauf zusichern koennen.
ATTRAPPEN_OBJEKTE = (
    ("world_obj_apriltag_001", "apriltag", 2.0, 0.5, 1),
    ("world_obj_apriltag_002", "apriltag", 4.0, -1.5, 2),
    ("world_obj_dock_003", "dock", 1.0, 0.0, None),
)
GITTER_ZELLE_M = 0.03
GITTER_ZELLEN = 128
```

`capabilities()` erweitern:

```python
    def capabilities(self):
        return (
            Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
            | Capability.WORLD_OBJECTS | Capability.LOCAL_GRID
        )
```

Und die zwei Methoden:

```python
    def world_objects(self, kinds=None):
        from spotlab.api.world import richtung

        gefunden = []
        for name, art, x, y, nummer in ATTRAPPEN_OBJEKTE:
            if kinds is not None and art not in kinds:
                continue
            peilung, distanz = richtung(x, y)
            gemeinsam = dict(
                name=name, kind=art, bearing=peilung, distance=distanz,
                world_xy=(x, y), time=self._jetzt(),
            )
            if art == "apriltag":
                gefunden.append(Tag(**gemeinsam, id=nummer, filtered=True))
            else:
                gefunden.append(WorldObject(**gemeinsam))
        return sorted(gefunden, key=lambda o: o.distance)

    def local_grid(self):
        # Freies Feld mit einer Wand bei y = 2 m: der Abstand faellt zur Wand hin.
        zellen = np.full((GITTER_ZELLEN, GITTER_ZELLEN), 2.0)
        wandzeile = int(2.0 / GITTER_ZELLE_M)
        if wandzeile < GITTER_ZELLEN:
            zellen[wandzeile, :] = 0.05
        return ObstacleGrid(
            cells=zellen, cell_size=GITTER_ZELLE_M, origin=(0.0, 0.0), time=self._jetzt()
        )
```

In `backends/sim.py` dieselben zwei Methoden, aber ehrlich leer — die MuJoCo-Sim
kennt keine World Objects:

```python
    def world_objects(self, kinds=None):
        return []

    def local_grid(self):
        raise UnsupportedCapability(
            "Die Simulation fuehrt keine Hindernisgitter. Nutze den Trockenlauf "
            "oder den echten Roboter."
        )
```

`sim.py` meldet die Fähigkeiten entsprechend **nicht** — `capabilities()` bleibt dort unverändert.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dryrun.py tests/test_backend_base.py -v`
Expected: PASS, alle bisherigen plus 6 neue

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/base.py src/spotlab/backends/dryrun.py src/spotlab/backends/sim.py tests/test_dryrun.py tests/test_backend_base.py
git commit -m "feat(umwelt): Faehigkeiten WORLD_OBJECTS und LOCAL_GRID plus Attrappen"
```

---

## Task 3: Die Verben

**Files:**
- Modify: `src/spotlab/api/world.py`
- Test: `tests/test_api_world.py` (anhängen)

**Interfaces:**
- Consumes: Task 1 und 2
- Produces: `world_objects(backend, recorder, kinds=None)`, `tags(backend, recorder, id=None)`, `obstacles(backend, recorder)`

- [ ] **Step 1: Write the failing test**

An `tests/test_api_world.py` anhängen:

```python
from spotlab.api import world
from spotlab.backends.dryrun import DryRunBackend


class Mitschreiber:
    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))


def test_tags_sind_nach_distanz_sortiert():
    gefunden = world.tags(DryRunBackend(), None)
    assert [t.id for t in gefunden] == [1, 2]


def test_tags_filtert_auf_eine_nummer():
    gefunden = world.tags(DryRunBackend(), None, id=2)
    assert [t.id for t in gefunden] == [2]


def test_tags_ohne_treffer_liefert_leere_liste_keinen_fehler():
    assert world.tags(DryRunBackend(), None, id=99) == []


def test_jede_abfrage_wird_protokolliert_auch_die_erfolglose():
    schreiber = Mitschreiber()
    world.tags(DryRunBackend(), schreiber, id=99)
    art, daten = schreiber.ereignisse[-1]
    assert daten["name"] == "tags"
    assert daten["treffer"] == 0


def test_protokoll_nennt_ids_und_distanzen():
    schreiber = Mitschreiber()
    world.tags(DryRunBackend(), schreiber)
    _, daten = schreiber.ereignisse[-1]
    assert daten["ids"] == [1, 2]
    assert len(daten["distanzen"]) == 2


def test_world_objects_liefert_auch_nicht_tags():
    arten = {o.kind for o in world.world_objects(DryRunBackend(), None)}
    assert "dock" in arten


def test_obstacles_liefert_ein_gitter():
    gitter = world.obstacles(DryRunBackend(), None)
    assert gitter.cell_size > 0


def test_backend_ohne_faehigkeit_wird_deutlich_abgewiesen():
    from spotlab.errors import UnsupportedCapability

    class Ohne:
        def capabilities(self):
            from spotlab.backends.base import Capability

            return Capability.LOCOMOTION

    with pytest.raises(UnsupportedCapability) as fehler:
        world.tags(Ohne(), None)
    assert "Objekte" in str(fehler.value) or "objekte" in str(fehler.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_world.py -v -k "sortiert or filtert or protokoll or obstacles or abgewiesen"`
Expected: FAIL — `AttributeError: module 'spotlab.api.world' has no attribute 'tags'`

- [ ] **Step 3: Write minimal implementation**

An `src/spotlab/api/world.py` anhängen:

```python
from spotlab.backends.base import Capability, require


def _protokolliere(recorder, name, **daten):
    if recorder is not None:
        recorder.event("kommando", name=name, **daten)


def world_objects(backend, recorder, kinds=None):
    """Alles, was Spots Firmware gerade als Objekt fuehrt, nach Distanz sortiert."""
    require(backend, Capability.WORLD_OBJECTS, "Objekte in der Umgebung nennen")
    gefunden = sorted(backend.world_objects(kinds=kinds), key=lambda o: o.distance)
    _protokolliere(
        recorder, "world_objects",
        treffer=len(gefunden),
        arten=sorted({o.kind for o in gefunden}),
        distanzen=[round(o.distance, 2) for o in gefunden],
    )
    return gefunden


def tags(backend, recorder, id=None):
    """Die sichtbaren AprilTags, naechster zuerst. Ohne `id` zaehlt jeder.

    `spot.tags()[0]` ist damit ohne Nachdenken das naechste Ziel.
    """
    require(backend, Capability.WORLD_OBJECTS, "Objekte in der Umgebung nennen")
    gefunden = [
        o for o in backend.world_objects(kinds=["apriltag"])
        if id is None or getattr(o, "id", None) == id
    ]
    gefunden.sort(key=lambda t: t.distance)
    # Auch die erfolglose Abfrage wird protokolliert: "vier Sekunden lang nichts
    # gesehen" ist eine Information, die man nachher braucht.
    _protokolliere(
        recorder, "tags",
        treffer=len(gefunden),
        ids=[t.id for t in gefunden],
        distanzen=[round(t.distance, 2) for t in gefunden],
    )
    return gefunden


def obstacles(backend, recorder):
    """Das Hindernisgitter: je Zelle der Abstand zum naechsten Hindernis."""
    require(backend, Capability.LOCAL_GRID, "das Hindernisgitter lesen")
    gitter = backend.local_grid()
    _protokolliere(recorder, "obstacles", zellengroesse=gitter.cell_size)
    return gitter
```

`__all__` erweitern um `"world_objects", "tags", "obstacles"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_world.py -v`
Expected: PASS, 15 Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/api/world.py tests/test_api_world.py
git commit -m "feat(umwelt): Verben world_objects, tags und obstacles mit Protokoll"
```

---

## Task 4: Die Fassade

**Files:**
- Modify: `src/spotlab/api/spot.py` (Import-Zeile und Abschnitt „Wahrnehmung")
- Test: `tests/test_api_spot.py` (anhängen)

**Interfaces:**
- Consumes: Task 3
- Produces: `spot.world_objects(kinds=None)`, `spot.tags(id=None)`, `spot.obstacles()`

- [ ] **Step 1: Write the failing test**

An `tests/test_api_spot.py` anhängen:

```python
def test_spot_reicht_tags_durch():
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend

    spot = Spot(DryRunBackend())
    assert [t.id for t in spot.tags()] == [1, 2]


def test_spot_tags_nimmt_eine_nummer():
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend

    spot = Spot(DryRunBackend())
    assert [t.id for t in spot.tags(id=2)] == [2]


def test_spot_bearing_taugt_direkt_fuer_move():
    """Die Zusicherung hinter der Grad-Entscheidung: kein math.degrees noetig."""
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend

    spot = Spot(DryRunBackend())
    winkel = spot.tags()[0].bearing
    assert -180.0 <= winkel <= 180.0
    spot.move(turn=winkel)          # darf nicht werfen


def test_spot_obstacles_liefert_gitter():
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend

    assert Spot(DryRunBackend()).obstacles().cell_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_spot.py -v -k "tags or bearing or obstacles"`
Expected: FAIL — `AttributeError: 'Spot' object has no attribute 'tags'`

- [ ] **Step 3: Write minimal implementation**

Import-Zeile in `api/spot.py` ändern:

```python
from spotlab.api import motion, navigation, perception, posture, world
```

Im Abschnitt „Wahrnehmung", nach `camera()`:

```python
    def world_objects(self, kinds=None):
        """Nennt alles, was Spot gerade als Objekt fuehrt — naechstes zuerst."""
        return world.world_objects(self.backend, self.recorder, kinds=kinds)

    def tags(self, id=None):
        """Die sichtbaren AprilTags, naechstes zuerst. Peilung in Grad."""
        return world.tags(self.backend, self.recorder, id=id)

    def obstacles(self):
        """Das Hindernisgitter: wo ist Platz, wo nicht."""
        return world.obstacles(self.backend, self.recorder)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_spot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/api/spot.py tests/test_api_spot.py
git commit -m "feat(umwelt): drei Fassadenmethoden auf dem Spot-Objekt"
```

---

## Task 5: Der reale Backend

**Files:**
- Create: `src/spotlab/backends/real/wahrnehmung.py`
- Modify: `src/spotlab/backends/real/session.py` (Methoden anschliessen, Capabilities melden)
- Test: `tests/test_backend_wahrnehmung.py`

**Interfaces:**
- Consumes: Task 1
- Produces: `objekte_aus(antwort, jetzt) -> list[WorldObject|Tag]`, `gitter_aus(antwort) -> ObstacleGrid`

- [ ] **Step 1: Write the failing test**

`tests/test_backend_wahrnehmung.py` — gegen echte Protobufs, ohne Roboter:

```python
import pytest

from spotlab.backends.base import Tag, WorldObject


def _apriltag(nummer, x, y):
    """Ein WorldObject-Protobuf mit einer Fiducial-Pose im Koerper-Frame."""
    from bosdyn.api import geometry_pb2, world_object_pb2
    from bosdyn.client.frame_helpers import BODY_FRAME_NAME

    obj = world_object_pb2.WorldObject()
    obj.name = f"world_obj_apriltag_{nummer:03d}"
    obj.apriltag_properties.tag_id = nummer
    rahmen = f"fiducial_{nummer}"
    obj.apriltag_properties.frame_name_fiducial = rahmen
    kante = obj.transforms_snapshot.child_to_parent_edge_map[rahmen]
    kante.parent_frame_name = BODY_FRAME_NAME
    kante.parent_tform_child.position.x = x
    kante.parent_tform_child.position.y = y
    kante.parent_tform_child.rotation.w = 1.0
    obj.transforms_snapshot.child_to_parent_edge_map[BODY_FRAME_NAME].CopyFrom(
        geometry_pb2.FrameTreeSnapshot.ParentEdge()
    )
    return obj


class Antwort:
    def __init__(self, objekte):
        self.world_objects = objekte


def test_apriltag_wird_zu_einem_tag_in_grad():
    from spotlab.backends.real.wahrnehmung import objekte_aus

    gefunden = objekte_aus(Antwort([_apriltag(1, 3.0, 4.0)]), jetzt=100.0)
    assert len(gefunden) == 1
    tag = gefunden[0]
    assert isinstance(tag, Tag)
    assert tag.id == 1
    assert tag.distance == pytest.approx(5.0)
    assert tag.bearing == pytest.approx(53.13, abs=0.1)


def test_objekt_ohne_transformation_wird_uebersprungen_nicht_genullt():
    """Eine falsche Zahl ist schlimmer als eine fehlende."""
    from bosdyn.api import world_object_pb2

    from spotlab.backends.real.wahrnehmung import objekte_aus

    kaputt = world_object_pb2.WorldObject()
    kaputt.name = "world_obj_apriltag_009"
    kaputt.apriltag_properties.tag_id = 9
    kaputt.apriltag_properties.frame_name_fiducial = "gibt_es_nicht"
    assert objekte_aus(Antwort([kaputt]), jetzt=100.0) == []


def test_gefilterte_pose_wird_bevorzugt_und_ausgewiesen():
    from bosdyn.client.frame_helpers import BODY_FRAME_NAME

    from spotlab.backends.real.wahrnehmung import objekte_aus

    obj = _apriltag(1, 3.0, 4.0)
    obj.apriltag_properties.frame_name_fiducial_filtered = "filtered_1"
    kante = obj.transforms_snapshot.child_to_parent_edge_map["filtered_1"]
    kante.parent_frame_name = BODY_FRAME_NAME
    kante.parent_tform_child.position.x = 1.0
    kante.parent_tform_child.position.y = 0.0
    kante.parent_tform_child.rotation.w = 1.0

    tag = objekte_aus(Antwort([obj]), jetzt=100.0)[0]
    assert tag.filtered is True
    assert tag.distance == pytest.approx(1.0)


def test_nicht_tag_objekt_wird_zu_worldobject():
    from bosdyn.api import world_object_pb2
    from bosdyn.client.frame_helpers import BODY_FRAME_NAME

    from spotlab.backends.real.wahrnehmung import objekte_aus

    obj = world_object_pb2.WorldObject()
    obj.name = "world_obj_dock_003"
    obj.dock_properties.dock_id = 3
    kante = obj.transforms_snapshot.child_to_parent_edge_map["dock_3"]
    kante.parent_frame_name = BODY_FRAME_NAME
    kante.parent_tform_child.position.x = 1.0
    kante.parent_tform_child.rotation.w = 1.0

    gefunden = objekte_aus(Antwort([obj]), jetzt=100.0)
    assert len(gefunden) == 1
    assert type(gefunden[0]) is WorldObject
    assert gefunden[0].kind == "dock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_wahrnehmung.py -v`
Expected: FAIL — `ModuleNotFoundError: spotlab.backends.real.wahrnehmung`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/backends/real/wahrnehmung.py`:

```python
"""Objekte und Hindernisgitter vom echten Spot.

WorldObjectClient und LocalGridClient sind reine LESEDIENSTE: kein Lease, kein
Kommando, keine Moeglichkeit, den Roboter zu bewegen. Deshalb darf die Sonde
(workshop/sonde.py) sie neben einem fremden Lease benutzen.

Hier faellt die Protobuf-Grenze: nach oben gehen ausschliesslich die
Datenklassen aus backends/base.py.
"""

import numpy as np
from bosdyn.api import world_object_pb2 as wo
from bosdyn.client import frame_helpers as fh

from spotlab.api.world import richtung
from spotlab.backends.base import ObstacleGrid, Tag, WorldObject

GITTERTYP = "obstacle_distance"

ARTEN = {
    "apriltag_properties": "apriltag",
    "dock_properties": "dock",
    "door_properties": "door",
    "image_properties": "image_coordinates",
}


def _art_und_rahmen(obj):
    """(Art, Rahmenname, gefiltert) — oder (None, None, False), wenn unbekannt."""
    if obj.HasField("apriltag_properties"):
        props = obj.apriltag_properties
        gefiltert = bool(props.frame_name_fiducial_filtered)
        return "apriltag", (props.frame_name_fiducial_filtered
                            or props.frame_name_fiducial), gefiltert
    for feld, art in ARTEN.items():
        if feld != "apriltag_properties" and obj.HasField(feld):
            # Nicht-Tags fuehren ihren Rahmen unter dem Objektnamen.
            return art, obj.name, False
    return None, None, False


def objekte_aus(antwort, jetzt):
    """Protobuf-Antwort in Datenklassen. Ueberspringt, was sich nicht verorten laesst."""
    gefunden = []
    for obj in antwort.world_objects:
        art, rahmen, gefiltert = _art_und_rahmen(obj)
        if art is None or not rahmen:
            continue
        try:
            koerper = fh.get_a_tform_b(obj.transforms_snapshot, fh.BODY_FRAME_NAME, rahmen)
        except Exception:
            koerper = None
        if koerper is None:
            continue
        peilung, distanz = richtung(float(koerper.x), float(koerper.y))
        welt = None
        try:
            v = fh.get_a_tform_b(obj.transforms_snapshot, fh.VISION_FRAME_NAME, rahmen)
            if v is not None:
                welt = (float(v.x), float(v.y))
        except Exception:
            pass
        gemeinsam = dict(name=obj.name, kind=art, bearing=peilung,
                         distance=distanz, world_xy=welt, time=jetzt)
        if art == "apriltag":
            gefunden.append(Tag(**gemeinsam, id=int(obj.apriltag_properties.tag_id),
                                filtered=gefiltert))
        else:
            gefunden.append(WorldObject(**gemeinsam))
    return sorted(gefunden, key=lambda o: o.distance)


ZELLFORMATE = None      # wird beim ersten Aufruf gefuellt, siehe _dtypen()


def _dtypen():
    """Zellformat-Enum → numpy-dtype. Lazy, damit der Import billig bleibt."""
    from bosdyn.api import local_grid_pb2 as lg

    return {
        lg.LocalGrid.CELL_FORMAT_FLOAT32: np.float32,
        lg.LocalGrid.CELL_FORMAT_FLOAT64: np.float64,
        lg.LocalGrid.CELL_FORMAT_INT16: "<i2",
        lg.LocalGrid.CELL_FORMAT_UINT16: "<u2",
        lg.LocalGrid.CELL_FORMAT_INT8: np.int8,
        lg.LocalGrid.CELL_FORMAT_UINT8: np.uint8,
    }


def gitter_aus(antwort):
    """Eine LocalGridResponse in ein ObstacleGrid.

    Portiert aus `matura-spot: spotsim/local_grid.py: grid_aus_proto()`.
    Das SDK bringt KEINEN Entpacker mit — `expand_data_by_rle_count` und
    `unpack_grid` liegen nur im Beispiel `examples/visualizer/`, nicht im
    installierten Paket. Die portierte Fassung ist ohnehin besser: sie entpackt
    RLE vektorisiert (`np.repeat` statt Python-Doppelschleife) und wertet
    `unknown_cells` aus, was das Beispiel gar nicht tut.
    """
    from bosdyn.api import local_grid_pb2 as lg

    g = antwort.local_grid
    n = (g.extent.num_cells_x, g.extent.num_cells_y)
    roh = np.frombuffer(g.data, dtype=_dtypen()[g.cell_format])
    if g.encoding == lg.LocalGrid.ENCODING_RLE:
        roh = np.repeat(roh, np.asarray(g.rle_counts, dtype=np.int64))
    zellen = roh.reshape(n).astype(np.float64) * g.cell_value_scale + g.cell_value_offset

    bekannt = None
    if g.unknown_cells:
        unbekannt = np.unpackbits(
            np.frombuffer(g.unknown_cells, dtype=np.uint8),
            count=n[0] * n[1], bitorder="little",
        ).reshape(n).astype(bool)
        bekannt = ~unbekannt

    ursprung = None
    try:
        ursprung = fh.get_a_tform_b(
            g.transforms_snapshot, fh.VISION_FRAME_NAME, g.frame_name_local_grid_data
        )
    except Exception:
        pass
    return ObstacleGrid(
        cells=zellen,
        cell_size=g.extent.cell_size,
        origin=(float(ursprung.x), float(ursprung.y)) if ursprung else (0.0, 0.0),
        time=g.acquisition_time.seconds + g.acquisition_time.nanos / 1e9,
        known=bekannt,
    )


def objekte_holen(client, jetzt, kinds=None):
    """Reiner Lesedienst — nie ein Kommando."""
    typen = None
    if kinds is not None and "apriltag" in kinds and len(kinds) == 1:
        typen = [wo.WORLD_OBJECT_APRILTAG]
    antwort = client.list_world_objects(object_type=typen) if typen \
        else client.list_world_objects()
    gefunden = objekte_aus(antwort, jetzt)
    if kinds is None:
        return gefunden
    return [o for o in gefunden if o.kind in kinds]
```

In `backends/real/session.py`: die zwei Clients anlegen (`WorldObjectClient`,
`LocalGridClient`), die Methoden `world_objects(kinds=None)` und `local_grid()`
darauf abbilden, und `capabilities()` um `Capability.WORLD_OBJECTS | Capability.LOCAL_GRID` erweitern.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend_wahrnehmung.py -v`
Expected: PASS, 4 Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/real/wahrnehmung.py src/spotlab/backends/real/session.py tests/test_backend_wahrnehmung.py
git commit -m "feat(umwelt): WorldObject- und LocalGrid-Client am echten Spot"
```

---

## Task 6: Der Gitter-Mitschnitt zieht um

**Files:**
- Create: `src/spotlab/beobachtung/gitter.py` (Umzug aus `matura-spot/src/spotsim/gitter_mitschnitt.py`, 232 Z.)
- Test: `tests/test_beobachtung_gitter.py`

**Interfaces:**
- Consumes: Task 5 (`GITTERTYP`)
- Produces: `Gittermitschnitt(client, verzeichnis, hz=2.0, typen=TYPEN)` mit `start()`, `stop(timeout)`, `zaehler()`; `lies_mitschnitt(lauf_verzeichnis, typ="obstacle_distance")`

- [ ] **Step 1: Write the failing test**

`tests/test_beobachtung_gitter.py`:

```python
import json

import pytest


class AttrappenClient:
    """Liefert serialisierbare Antworten und zaehlt Abrufe."""

    def __init__(self, fehler_ab=None):
        self.abrufe = 0
        self._fehler_ab = fehler_ab

    def get_local_grids(self, typen):
        from bosdyn.api import local_grid_pb2

        self.abrufe += 1
        if self._fehler_ab is not None and self.abrufe >= self._fehler_ab:
            raise RuntimeError("Netz weg")
        antwort = local_grid_pb2.LocalGridResponse()
        antwort.local_grid.local_grid_type_name = typen[0]
        antwort.local_grid.extent.cell_size = 0.03
        antwort.local_grid.extent.num_cells_x = 4
        antwort.local_grid.extent.num_cells_y = 4
        return [antwort]


def test_legt_gitter_und_index_ab(tmp_path):
    from spotlab.beobachtung.gitter import Gittermitschnitt

    mitschnitt = Gittermitschnitt(AttrappenClient(), tmp_path, hz=50.0)
    mitschnitt.start()
    mitschnitt.stop()

    index = tmp_path / "gitter" / "gitter.jsonl"
    assert index.exists()
    zeilen = [json.loads(z) for z in index.read_text(encoding="utf-8").splitlines() if z]
    assert zeilen
    assert (tmp_path / "gitter" / zeilen[0]["datei"]).exists()


def test_speichert_die_serialisierte_antwort_nicht_ein_eigenformat(tmp_path):
    """Die Garantie, dass GUI, Replay und Sim identisch dekodieren."""
    from bosdyn.api import local_grid_pb2

    from spotlab.beobachtung.gitter import Gittermitschnitt

    mitschnitt = Gittermitschnitt(AttrappenClient(), tmp_path, hz=50.0)
    mitschnitt.start()
    mitschnitt.stop()

    index = tmp_path / "gitter" / "gitter.jsonl"
    erste = json.loads(index.read_text(encoding="utf-8").splitlines()[0])
    roh = (tmp_path / "gitter" / erste["datei"]).read_bytes()
    wieder = local_grid_pb2.LocalGridResponse()
    wieder.ParseFromString(roh)          # muss ohne Fehler gelingen
    assert wieder.local_grid.extent.cell_size == pytest.approx(0.03)


def test_fehler_werden_gezaehlt_nicht_geworfen(tmp_path):
    from spotlab.beobachtung.gitter import Gittermitschnitt

    mitschnitt = Gittermitschnitt(AttrappenClient(fehler_ab=1), tmp_path, hz=50.0)
    mitschnitt.start()
    mitschnitt.stop()                    # darf nicht werfen
    assert mitschnitt.zaehler()["fehler"] > 0


def test_wiedereinlesen_liefert_die_antworten_zurueck(tmp_path):
    from spotlab.beobachtung.gitter import Gittermitschnitt, lies_mitschnitt

    mitschnitt = Gittermitschnitt(AttrappenClient(), tmp_path, hz=50.0)
    mitschnitt.start()
    mitschnitt.stop()
    gelesen = list(lies_mitschnitt(tmp_path))
    assert gelesen
    assert gelesen[0].local_grid.extent.num_cells_x == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_beobachtung_gitter.py -v`
Expected: FAIL — `ModuleNotFoundError: spotlab.beobachtung.gitter`

- [ ] **Step 3: Write minimal implementation**

Datei kopieren und anpassen:

```bash
cp ../matura-spot/src/spotsim/gitter_mitschnitt.py src/spotlab/beobachtung/gitter.py
```

Dann in `src/spotlab/beobachtung/gitter.py`:
1. Modul-Docstring anpassen — der Verweis auf `scripts/karte_replay.py` gehört nach matura-spot, hier steht stattdessen der Verweis auf die Ansicht „Umwelt" und die Sonde. **Beide Kernentscheidungen im Docstring behalten:** serialisierte `LocalGridResponse` statt Eigenformat, und „wirft nie nach aussen".
2. Alle `spotsim.`-Importe auf `spotlab.` umstellen.
3. Ablageordner von `gitter/` beibehalten, Index `gitter/gitter.jsonl`.
4. Sicherstellen, dass `zaehler()` ein Dict mit mindestens `{"abgelegt": int, "fehler": int}` liefert.
5. **Neu gegenueber dem Original: neben jedem `.pb` eine `.png`-Vorschau ablegen.**
   Begruendung: die GUI darf laut CLAUDE.md weder `bosdyn` noch `spotlab.backends`
   importieren, auch nicht mittelbar — sie kann das Protobuf also nicht dekodieren.
   Dasselbe Verhaeltnis wie bei `kamera/`: die Rohdaten sind die Wahrheit, das Bild
   ist fuer die Anzeige. Das Protobuf bleibt die Quelle fuer Replay und Auswertung.

```python
def _vorschau(self, nummer, gitter):
    """Graustufen-PNG neben dem Protobuf — die Anzeige-Tuer fuer die GUI.

    Die GUI darf kein bosdyn importieren und kann das Gitter deshalb nicht selbst
    dekodieren. Sie bekommt ein Bild, so wie sie Kamerabilder bekommt.
    Unbekannte Zellen werden schwarz, nicht "sehr frei" — eine erfundene Freiheit
    im Bild waere derselbe Fehler wie eine erfundene Zahl in der API.
    """
    from PIL import Image

    werte = np.clip(gitter.cells / VORSCHAU_MAX_M, 0.0, 1.0)
    if gitter.known is not None:
        werte = np.where(gitter.known, werte, 0.0)
    bild = Image.fromarray((werte * 255).astype(np.uint8), mode="L")
    bild.save(self._ordner / f"{nummer:04d}.png")
```

`VORSCHAU_MAX_M = 2.0` als Modulkonstante. Die Dekodierung dafuer kommt aus
`backends.real.wahrnehmung.gitter_aus` — `beobachtung/` darf aus `backends/`
importieren (`session.py` tut es bereits), umgekehrt nicht.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_beobachtung_gitter.py -v`
Expected: PASS, 4 Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/beobachtung/gitter.py tests/test_beobachtung_gitter.py
git commit -m "feat(umwelt): LocalGrid-Mitschnitt aus matura-spot heimgeholt"
```

---

## Task 7: Die Sonde

**Files:**
- Create: `src/spotlab/workshop/sonde.py`
- Test: `tests/test_sonde.py`

**Interfaces:**
- Consumes: Task 3, 4
- Produces: `sonde(spot, dauer_s=5.0, hz=2.0, schlaf=time.sleep, jetzt=time.monotonic) -> dict`; ausführbar als `python -m spotlab.workshop.sonde`

- [ ] **Step 1: Write the failing test**

`tests/test_sonde.py`:

```python
import ast
from pathlib import Path

BEWEGUNGSVERBEN = {
    "walk", "move", "stand", "sit", "power_on", "power_off",
    "navigate_to", "send_command", "send",
}


def test_sonde_ruft_keine_bewegungsfunktion_auf():
    """Das Gate hinter der Leaselosigkeit.

    Eine Naht ist erst eine Naht, wenn sie reisst, sobald jemand durchgreift.
    Dieser Test reisst.
    """
    quelle = Path("src/spotlab/workshop/sonde.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    gerufen = {
        knoten.func.attr
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
    }
    verboten = gerufen & BEWEGUNGSVERBEN
    assert not verboten, f"Die Sonde darf nichts bewegen, ruft aber: {sorted(verboten)}"


def test_sonde_importiert_kein_motion_modul():
    quelle = Path("src/spotlab/workshop/sonde.py").read_text(encoding="utf-8")
    assert "api.motion" not in quelle
    assert "api.posture" not in quelle


def test_sonde_sammelt_objekte_und_gitter():
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend
    from spotlab.workshop.sonde import sonde

    takte = iter([0.0, 0.5, 1.0, 1.5, 2.0, 99.0])
    ergebnis = sonde(
        Spot(DryRunBackend()), dauer_s=2.0, hz=2.0,
        schlaf=lambda _s: None, jetzt=lambda: next(takte),
    )
    assert ergebnis["abtastungen"] >= 1
    assert ergebnis["objekte_gesehen"] >= 1
    assert "gitter" in ergebnis


def test_sonde_ueberlebt_ein_backend_ohne_gitter():
    """Die Sim kann kein Gitter — die Sonde soll trotzdem Objekte melden."""
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend
    from spotlab.errors import UnsupportedCapability
    from spotlab.workshop.sonde import sonde

    class OhneGitter(DryRunBackend):
        def local_grid(self):
            raise UnsupportedCapability("kein Gitter")

    takte = iter([0.0, 0.5, 99.0])
    ergebnis = sonde(
        Spot(OhneGitter()), dauer_s=1.0, hz=2.0,
        schlaf=lambda _s: None, jetzt=lambda: next(takte),
    )
    assert ergebnis["objekte_gesehen"] >= 1
    assert ergebnis["gitter"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sonde.py -v`
Expected: FAIL — `FileNotFoundError` bzw. `ModuleNotFoundError: spotlab.workshop.sonde`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/workshop/sonde.py`:

```python
"""„Spot, was siehst du gerade?" — eine Abfrage, kein Kommando.

Die Sonde haelt KEIN Lease und bewegt nichts. WorldObjectClient und
LocalGridClient sind reine Lesedienste; sie funktionieren neben einem fremden
Lease, etwa waehrend das Tablet fuehrt. Genau das macht sie zum Werkzeug fuer
den Moment VOR einem Lauf: erkennt Spot den Tag ueberhaupt?

Dass hier nichts bewegt wird, ist nicht nur behauptet, sondern in
`tests/test_sonde.py` als Gate festgeschrieben.
"""

import time

from spotlab.errors import SpotlabError, UnsupportedCapability


def sonde(spot, dauer_s=5.0, hz=2.0, schlaf=time.sleep, jetzt=time.monotonic):
    """Fragt `dauer_s` lang mit `hz` die Umgebung ab und fasst zusammen."""
    ende = jetzt() + dauer_s
    takt = 1.0 / hz
    abtastungen = 0
    gesehen = {}
    letztes_gitter = None

    while jetzt() < ende:
        abtastungen += 1
        for objekt in spot.world_objects():
            schluessel = (objekt.kind, getattr(objekt, "id", objekt.name))
            vorher = gesehen.get(schluessel)
            if vorher is None or objekt.distance < vorher.distance:
                gesehen[schluessel] = objekt
        try:
            letztes_gitter = spot.obstacles()
        except (UnsupportedCapability, SpotlabError):
            letztes_gitter = None
        schlaf(takt)

    return {
        "abtastungen": abtastungen,
        "objekte_gesehen": len(gesehen),
        "objekte": sorted(gesehen.values(), key=lambda o: o.distance),
        "gitter": letztes_gitter,
    }


def _hauptprogramm():
    """Als Skript ueber workshop/launcher.py gestartet — schreibt ein Lauf-Verzeichnis."""
    import spotlab

    with spotlab.connect() as spot:
        ergebnis = sonde(spot)
    print(f"{ergebnis['abtastungen']} Abtastungen, "
          f"{ergebnis['objekte_gesehen']} Objekte gesehen.")
    for objekt in ergebnis["objekte"]:
        kennung = getattr(objekt, "id", objekt.name)
        print(f"  {objekt.kind} {kennung}: "
              f"{objekt.distance:.2f} m, {objekt.bearing:+.0f} Grad")


if __name__ == "__main__":
    _hauptprogramm()
```

- [ ] **Step 4: Test, der die Sonde als echten Prozess startet**

CLAUDE.md: „Wo ein externer Prozess im Spiel ist, braucht es mindestens einen
Test, der ihn wirklich startet." Attrappen prüfen nur, dass die richtigen
Argumente gebaut werden — nicht, dass das Betriebssystem etwas damit anfängt.
Genau daran ist „In VS Code öffnen" durch die ganze Suite gegangen.

An `tests/test_sonde.py` anhängen:

```python
def test_sonde_laeuft_wirklich_als_prozess(tmp_path, monkeypatch):
    import subprocess
    import sys

    from tests.tests_zeitgrenzen import TEST_TIMEOUT_S

    umgebung = dict(os.environ, SPOTLAB_NUR_TROCKEN="1", SPOTLAB_BACKEND="dryrun")
    ergebnis = subprocess.run(
        [sys.executable, "-m", "spotlab.workshop.sonde"],
        capture_output=True, text=True, timeout=TEST_TIMEOUT_S, env=umgebung,
    )
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Objekte gesehen" in ergebnis.stdout
```

`import os` oben in der Testdatei ergänzen.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_sonde.py -v`
Expected: PASS, 5 Tests

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/workshop/sonde.py tests/test_sonde.py
git commit -m "feat(umwelt): leaselose Sonde plus Gate gegen jede Bewegung"
```

---

## Task 8: Ansicht „Umwelt"

**Files:**
- Create: `src/spotlab/gui/views/umwelt.py`
- Modify: `src/spotlab/gui/app.py` (Ansicht registrieren), `src/spotlab/gui/sidebar.py` (Eintrag)
- Test: `tests/test_gui_umwelt.py`

**Interfaces:**
- Consumes: Task 6 (`lies_mitschnitt`), Task 7 (Sonde als Skript)
- Produces: `UmweltView(parent=None)` mit `lade(lauf_verzeichnis)` und Signal `meldung`

- [ ] **Step 1: Write the failing test**

`tests/test_gui_umwelt.py`:

```python
import json
from pathlib import Path


def test_ansicht_importiert_weder_bosdyn_noch_backends():
    """CLAUDE.md: kein bosdyn UND kein spotlab.backends unterhalb von gui/."""
    quelle = Path("src/spotlab/gui/views/umwelt.py").read_text(encoding="utf-8")
    assert "bosdyn" not in quelle
    assert "spotlab.backends" not in quelle


def test_ansicht_zeigt_die_vorschau_nicht_das_protobuf(tmp_path):
    """Die GUI kann kein Protobuf dekodieren — sie bekommt ein Bild."""
    from spotlab.gui.views.umwelt import UmweltView

    gitter = tmp_path / "gitter"
    gitter.mkdir()
    (gitter / "0001.pb").write_bytes(b"nicht lesbar fuer die GUI")
    (gitter / "0001.png").write_bytes(_winziges_png())

    ansicht = UmweltView()
    ansicht.lade(tmp_path)
    assert ansicht.gitterbild() is not None


def _winziges_png():
    import io as _io

    from PIL import Image

    puffer = _io.BytesIO()
    Image.new("L", (4, 4), 128).save(puffer, format="PNG")
    return puffer.getvalue()


def _lauf_mit_objekten(tmp_path):
    zeilen = [
        {"t": 1.0, "art": "kommando",
         "daten": {"name": "tags", "treffer": 2, "ids": [1, 2],
                   "distanzen": [2.06, 4.27]}},
    ]
    (tmp_path / "ereignisse.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    return tmp_path


def test_zeigt_gesehene_objekte_aus_dem_lauf(qapp, tmp_path):
    from spotlab.gui.views.umwelt import UmweltView

    ansicht = UmweltView()
    ansicht.lade(_lauf_mit_objekten(tmp_path))
    texte = ansicht.objekttexte()
    assert any("1" in t and "2.06" in t for t in texte)


def test_leeres_lauf_verzeichnis_meldet_klartext_statt_zu_stuerzen(qapp, tmp_path):
    from spotlab.gui.views.umwelt import UmweltView

    ansicht = UmweltView()
    ansicht.lade(tmp_path)                 # nichts darin
    assert ansicht.objekttexte() == []


def test_alter_der_beobachtung_wird_angezeigt(qapp, tmp_path):
    """Eine Objektliste ohne Alter suggeriert Gegenwart."""
    from spotlab.gui.views.umwelt import UmweltView

    ansicht = UmweltView()
    ansicht.lade(_lauf_mit_objekten(tmp_path))
    assert any("s" in t for t in ansicht.objekttexte())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gui_umwelt.py -v`
Expected: FAIL — `ModuleNotFoundError: spotlab.gui.views.umwelt`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/gui/views/umwelt.py` — Aufbau streng nach `views/live.py`:

- Kopf mit Knopf „Umgebung abfragen" → startet `spotlab.workshop.sonde` über
  `workshop.launcher.starte`
- links `QListWidget` mit den Objekten (`objekttexte()` gibt die Zeilen als
  Liste zurück — das ist die Testtür)
- rechts das jüngste `gitter/*.png` als `QPixmap` — **nicht** das Protobuf; die
  Dekodierung ist beim Schreiben passiert (Task 6). Zugriffstür für den Test:
  `gitterbild()`. Farben ausschliesslich aus `gui/theme.py`.
- Zeilenformat: `f"{art} {kennung}   {distanz:.2f} m   {peilung:+.0f}°   vor {alter:.0f} s"`
- Fehlende Dateien: leere Liste, keine Ausnahme

**Kein `bosdyn`- und kein `spotlab.backends`-Import**, auch nicht mittelbar. Die
Ansicht liest ausschliesslich Dateien: `ereignisse.jsonl` und `gitter/*.png`.

In `gui/app.py` und `gui/sidebar.py` die Ansicht als siebten Eintrag „Umwelt"
registrieren, dem Muster der bestehenden sechs folgend.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gui_umwelt.py tests/test_gui_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/views/umwelt.py src/spotlab/gui/app.py src/spotlab/gui/sidebar.py tests/test_gui_umwelt.py
git commit -m "feat(umwelt): Ansicht Umwelt mit Objektliste, Gitter und Sonden-Knopf"
```

---

## Task 9: Diagnose — Lizenz, Nutzlasten, Dienste

**Files:**
- Modify: `src/spotlab/workshop/doctor.py` (`STUFEN`, neue Prüffunktionen, `diagnose`)
- Modify: `src/spotlab/gui/views/checkup.py` (Abschnitt „Gerät", kopierbar)
- Test: `tests/test_doctor.py` (anhängen)

**Interfaces:**
- Consumes: nichts
- Produces: `_lizenz(robot) -> Check`, `_nutzlasten(robot) -> Check`, `_dienste(robot) -> Check`

- [ ] **Step 1: Write the failing test**

An `tests/test_doctor.py` anhängen:

```python
class AttrappenLizenz:
    def __init__(self, features, bis="2027-01-01T00:00:00Z", werfen=False):
        self._features = features
        self._bis = bis
        self._werfen = werfen

    def get_license_info(self):
        if self._werfen:
            raise RuntimeError("kein Lizenzdienst")

        class Info:
            pass

        info = Info()
        info.licensed_features = self._features
        info.not_valid_after = self._bis
        return info


def test_lizenz_nennt_die_freigeschalteten_features():
    from spotlab.workshop.doctor import _lizenz

    pruefung = _lizenz(AttrappenLizenz(["joint_control", "graph_nav"]))
    assert pruefung.ok
    assert "joint_control" in pruefung.detail


def test_lizenz_ohne_dienst_ist_kein_defekt():
    """Ein fehlender Befund ist kein Defekt — ein rotes Kreuz waere Falschaussage."""
    from spotlab.workshop.doctor import _lizenz

    pruefung = _lizenz(AttrappenLizenz([], werfen=True))
    assert pruefung.ok is True
    assert "nicht ermittelbar" in pruefung.detail


def test_lizenz_warnt_vor_dem_ablauf():
    from spotlab.workshop.doctor import _lizenz

    pruefung = _lizenz(AttrappenLizenz(["graph_nav"], bis="2026-09-10T00:00:00Z"))
    assert "2026-09-10" in pruefung.detail


def test_nutzlasten_beantworten_die_gps_frage():
    from spotlab.workshop.doctor import _nutzlasten

    class Attrappe:
        def list_payloads(self):
            class P:
                pass

            p = P()
            p.name = "Spot CORE"
            p.is_authorized = True
            return [p]

    pruefung = _nutzlasten(Attrappe())
    assert "Spot CORE" in pruefung.detail


def test_keine_nutzlast_ist_eine_gueltige_antwort():
    from spotlab.workshop.doctor import _nutzlasten

    class Leer:
        def list_payloads(self):
            return []

    pruefung = _nutzlasten(Leer())
    assert pruefung.ok
    assert "keine" in pruefung.detail.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_doctor.py -v -k "lizenz or nutzlast"`
Expected: FAIL — `ImportError: cannot import name '_lizenz'`

- [ ] **Step 3: Write minimal implementation**

In `workshop/doctor.py`, `STUFEN` erweitern um `"Lizenz", "Nutzlasten", "Dienste", "Zertifikat"`.

```python
def _lizenz(license_client):
    """Was ist auf diesem Roboter freigeschaltet — autoritativ, nicht geraten.

    Loest die Heuristik in `_zustandsstrom` ab, die aus der Dienstliste schloss.
    Beide bleiben: "lizenziert, aber Dienst laeuft nicht" ist ein anderes
    Problem als "nicht lizenziert", und nur wer beides fragt, unterscheidet sie.
    """
    try:
        info = license_client.get_license_info()
    except Exception as fehler:
        return Check("Lizenz", True, f"nicht ermittelbar ({type(fehler).__name__})",
                     "Ohne die Angabe bleibt es bei der Dienstlisten-Auskunft.")
    features = list(getattr(info, "licensed_features", []) or [])
    bis = str(getattr(info, "not_valid_after", "") or "")
    detail = ", ".join(features) if features else "keine Features gemeldet"
    if bis:
        detail += f" — gueltig bis {bis[:10]}"
    return Check("Lizenz", True, detail,
                 "Auch die Lizenz hat ein Ablaufdatum. Vor einem Messtag hinschauen.")


def _nutzlasten(payload_client):
    """Beantwortet GPS? Lidar? — statt es zu vermuten."""
    try:
        nutzlasten = list(payload_client.list_payloads())
    except Exception as fehler:
        return Check("Nutzlasten", True, f"nicht ermittelbar ({type(fehler).__name__})", "")
    if not nutzlasten:
        return Check("Nutzlasten", True, "keine verbaut",
                     "Ohne Nutzlast kein GPS und kein Lidar.")
    namen = ", ".join(
        f"{getattr(p, 'name', '?')}"
        f"{'' if getattr(p, 'is_authorized', True) else ' (nicht freigegeben)'}"
        for p in nutzlasten
    )
    return Check("Nutzlasten", True, namen, "")


def _dienste(robot):
    try:
        namen = sorted({getattr(d, "name", "") for d in robot.list_services()})
    except Exception as fehler:
        return Check("Dienste", True, f"nicht ermittelbar ({type(fehler).__name__})", "")
    return Check("Dienste", True, f"{len(namen)} Dienste", ", ".join(namen))
```

In `diagnose()` nach der Akku-Zeile anhängen — jede in eigenem `try`, damit ein
Ausfall die anderen nicht mitreisst.

In `gui/views/checkup.py`: aufklappbarer Abschnitt „Gerät", der `detail` und
`rat` dieser vier Zeilen zeigt, plus Knopf „Als Text kopieren"
(`QApplication.clipboard().setText(...)`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_doctor.py tests/test_gui_checkup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/workshop/doctor.py src/spotlab/gui/views/checkup.py tests/test_doctor.py
git commit -m "feat(diagnose): Lizenz, Nutzlasten und Dienste autoritativ statt geraten"
```

---

## Task 10: Diagnose — Zertifikat

**Files:**
- Create: `src/spotlab/workshop/zertifikat.py` (Portierung aus `matura-spot/scripts/zertifikat_pruefen.py`)
- Modify: `src/spotlab/workshop/doctor.py`
- Test: `tests/test_zertifikat.py`

**Interfaces:**
- Consumes: nichts
- Produces: `hole_zertifikat(host, port=443, timeout=3.0) -> str` (PEM), `fenster_aus(pem) -> (notBefore, notAfter)`, `_zertifikat(ip, jetzt, holen) -> Check`

- [ ] **Step 1: Write the failing test**

`tests/test_zertifikat.py`:

```python
from datetime import UTC, datetime

# Ein echtes, laengst abgelaufenes Testzertifikat waere hier ideal; da keines
# im Repo liegen soll, wird das Zeitfenster direkt geprueft.


def test_abgelaufenes_zertifikat_wird_als_nicht_ok_gemeldet():
    from spotlab.workshop.doctor import _zertifikat

    def holen(_ip):
        return (datetime(2025, 2, 5, tzinfo=UTC), datetime(2026, 3, 10, tzinfo=UTC))

    pruefung = _zertifikat("192.168.80.3", jetzt=datetime(2026, 9, 2, tzinfo=UTC),
                           holen=holen)
    assert pruefung.ok is False
    assert "2026-03-10" in pruefung.detail
    assert "neu" in pruefung.rat.lower()      # Rat: Roboter neu starten


def test_gueltiges_zertifikat_nennt_das_ablaufdatum():
    from spotlab.workshop.doctor import _zertifikat

    def holen(_ip):
        return (datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 6, 1, tzinfo=UTC))

    pruefung = _zertifikat("192.168.80.3", jetzt=datetime(2026, 9, 2, tzinfo=UTC),
                           holen=holen)
    assert pruefung.ok is True
    assert "2027-06-01" in pruefung.detail


def test_bald_ablaufend_wird_zur_warnung():
    from spotlab.workshop.doctor import _zertifikat

    def holen(_ip):
        return (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 9, 20, tzinfo=UTC))

    pruefung = _zertifikat("192.168.80.3", jetzt=datetime(2026, 9, 2, tzinfo=UTC),
                           holen=holen)
    assert pruefung.ok is True
    assert "18 Tage" in pruefung.detail or "18" in pruefung.detail


def test_nicht_erreichbar_ist_kein_defekt():
    from spotlab.workshop.doctor import _zertifikat

    def holen(_ip):
        raise OSError("keine Verbindung")

    pruefung = _zertifikat("192.168.80.3", jetzt=datetime(2026, 9, 2, tzinfo=UTC),
                           holen=holen)
    assert pruefung.ok is True
    assert "nicht ermittelbar" in pruefung.detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_zertifikat.py -v`
Expected: FAIL — `ImportError: cannot import name '_zertifikat'`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/workshop/zertifikat.py` — aus `matura-spot/scripts/zertifikat_pruefen.py` portieren, als Bibliothek statt Skript:

```python
"""Das TLS-Zertifikat des Roboters ansehen — UNGEPRUEFT abgeholt.

Ungeprueft ist der Punkt: an ein abgelaufenes Zertifikat kaeme man sonst nie
heran, und genau dann will man es sehen. Braucht kein openssl.

Anlass: am 02.09.2026 scheiterte der Handshake an einem abgelaufenen
Roboter-Zertifikat (notAfter 2026-03-10), ein Neustart behob es, die Ursache
blieb offen. Diese Zeile macht den Zustand kuenftig sichtbar, BEVOR er zubeisst.
"""

import socket
import ssl
from datetime import UTC, datetime


def hole_zertifikat(host, port=443, timeout=3.0):
    """Das PEM des Servers, ohne jede Pruefung."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as roh:
        with ctx.wrap_socket(roh, server_hostname=host) as sicher:
            der = sicher.getpeercert(binary_form=True)
    return ssl.DER_cert_to_PEM_cert(der)


def fenster_aus(pem):
    """(notBefore, notAfter) als aware datetimes."""
    from cryptography import x509

    zert = x509.load_pem_x509_certificate(pem.encode())
    vor = getattr(zert, "not_valid_before_utc", None) or \
        zert.not_valid_before.replace(tzinfo=UTC)
    nach = getattr(zert, "not_valid_after_utc", None) or \
        zert.not_valid_after.replace(tzinfo=UTC)
    return vor, nach


def fenster_von(host, port=443):
    return fenster_aus(hole_zertifikat(host, port))
```

In `workshop/doctor.py`:

```python
WARNFRIST_TAGE = 30


def _zertifikat(ip, jetzt=None, holen=None):
    """Laeuft das Roboter-Zertifikat bald ab? Die Lehre aus dem 02.09.2026."""
    from spotlab.workshop.zertifikat import fenster_von

    jetzt = jetzt or datetime.now(UTC)
    holen = holen or fenster_von
    try:
        _vor, nach = holen(ip)
    except Exception as fehler:
        return Check("Zertifikat", True, f"nicht ermittelbar ({type(fehler).__name__})",
                     "Nur im WLAN des Spot pruefbar.")
    tage = (nach - jetzt).days
    datum = nach.strftime("%Y-%m-%d")
    if tage < 0:
        return Check(
            "Zertifikat", False, f"abgelaufen am {datum} (seit {-tage} Tagen)",
            "Den Roboter neu starten — das hat am 02.09.2026 geholfen. "
            "Die Laptop-Uhr NICHT zurueckstellen.",
        )
    if tage <= WARNFRIST_TAGE:
        return Check("Zertifikat", True, f"gueltig bis {datum} — noch {tage} Tage",
                     "Vor dem naechsten Messtag einen Neustart einplanen.")
    return Check("Zertifikat", True, f"gueltig bis {datum}", "")
```

`from datetime import UTC, datetime` oben in `doctor.py` ergänzen.

**Und `pyproject.toml`:** `zertifikat.py` benutzt `cryptography`. Das Paket ist
heute nur mittelbar da (bosdyn-client zieht es), und CLAUDE.md verlangt für jede
Abhängigkeit eine Obergrenze. Also ausdrücklich eintragen:

```toml
dependencies = [
    "bosdyn-client==5.0.1.2",
    "bosdyn-api==5.0.1.2",
    "cryptography>=42,<47",
    "keyring>=24,<26",
    "numpy>=1.26,<3",
    "Pillow>=10,<13",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_zertifikat.py tests/test_doctor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/workshop/zertifikat.py src/spotlab/workshop/doctor.py tests/test_zertifikat.py
git commit -m "feat(diagnose): Zertifikatsablauf sichtbar machen, bevor er zubeisst"
```

---

## Task 11: Abnahmepunkte in `docs/ABNAHME.md`

**Files:**
- Modify: `docs/ABNAHME.md`

CLAUDE.md macht das zur Pflicht, nicht zur Kür: „Neue Fähigkeit ⇒ neuer Eintrag in
`Capability`, Prüfung über `require()`, **und** ein neuer Punkt in
`docs/ABNAHME.md`." Task 2 hat zwei Fähigkeiten angelegt; hier wird die Schuld
beglichen. Und: „Was nur am Gerät prüfbar ist, gehört in `docs/ABNAHME.md`, nicht
in einen Test, der Sicherheit bloss behauptet."

- [ ] **Step 1: A19 und A20 im Hausformat anhängen**

Format wie die bestehenden Punkte — Überschrift, **Erwartung**, **Gegenprobe**,
**Ergebnis** _(offen)_:

```markdown
## A19 — Die Sonde ist leaselos

**Vorgehen** Mit dem Tablet das Lease nehmen und den Spot stehen lassen. Dann am
Laptop in der Ansicht „Umwelt" auf „Umgebung abfragen" drücken.

**Erwartung**
- (1) Die Sonde läuft durch und listet Objekte — obwohl das Tablet das Lease hält.
- (2) Das Tablet **verliert sein Lease nicht** und meldet keine Übernahme.
- (3) Der Spot bewegt sich während der ganzen Abfrage um keinen Millimeter.

**Gegenprobe** Während die Sonde läuft, am Tablet fahren. Muss ungestört gehen —
ein reiner Lesedienst darf die Führung nicht beeinträchtigen.

**Ergebnis** _(offen)_

---

## A20 — Erkennungsreichweite der Fiducials

**Vorgehen** Einen AprilTag an eine Wand kleben, gemessene Kantenlänge notieren.
Den Spot in 1-m-Schritten entfernen, an jeder Stelle die Sonde auslösen.

**Erwartung** Die Entfernung notieren, ab der der Tag nicht mehr gemeldet wird.
Die Simulation rechnet mit rund 12 m; real werden 2–3 m erwartet.

**Gegenprobe** Am Tablet nachsehen, ob Spot den Tag dort noch anzeigt. Zeigt das
Tablet ihn und die Sonde nicht, liegt es an der Abfrage, nicht am Tag.

**Ergebnis** _(offen)_
```

**Der gemessene Wert aus A20 gehört als Versuchsbedingung in die Maturaarbeit**,
nicht nur in dieses Dokument.

- [ ] **Step 2: Commit**

```bash
git add docs/ABNAHME.md
git commit -m "docs(abnahme): A19 Sonde leaselos und A20 Tag-Reichweite"
```

---

## Task 12: Gesamtlauf spotlab

**Files:** keine Änderung, nur Nachweis

- [ ] **Step 1: Linter zuerst**

CLAUDE.md: die CI führt `ruff` **vor** den Tests aus — es hat einen `NameError`
in einem Abbaupfad gefunden, den 844 Tests nicht sahen.

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 2: Vollständige Suite**

Run: `python -m pytest -q`
Expected: alle grün, keine Warnungen aus den neuen Modulen

- [ ] **Step 3: Der Trockenlauf von aussen**

Run:
```bash
python -c "import spotlab; s=spotlab.connect(backend='dryrun'); print([ (t.id, round(t.distance,2), round(t.bearing)) for t in s.tags() ])"
```
Expected: `[(1, 2.06, 14), (2, 4.27, -21)]`

- [ ] **Step 4: Die Sonde gegen den Trockenlauf**

Run: `python -m spotlab.workshop.sonde` (bei gesetzter Trockenlauf-Konfiguration)
Expected: nennt Abtastungen und Objekte, endet mit Rückgabewert 0

- [ ] **Step 5: Commit (falls Korrekturen nötig waren)**

```bash
git add -A && git commit -m "test(umwelt): Gesamtlauf gruen"
```

---

## Task 13: matura-spot wird Klient — `detect_target`

**Files:**
- Modify: `../matura-spot/src/spotsim/sdk_real.py:125-165`
- Test: `../matura-spot/tests/test_sdk_real.py`

**Interfaces:**
- Consumes: `spotlab.api.world.tags` (Task 3), Grad
- Produces: unverändert `(pixel, peilung_rad, distanz, quelle)` — die Explorer-Signatur

**Voraussetzung:** Tasks 1–12 grün. Geht die Zeit aus, wird dieser Task **nicht** begonnen; matura-spot bleibt unberührt lauffähig.

- [ ] **Step 1: Ausgangslage sichern**

Run: `cd ../matura-spot && python -m pytest -q`
Expected: **212 Tests grün.** Diese Zahl ist der Referenzwert.

- [ ] **Step 2: Write the failing test**

An `../matura-spot/tests/test_sdk_real.py` anhängen:

```python
def test_detect_target_rechnet_grad_der_spotlab_schicht_in_radiant():
    """spotlab liefert Grad, der Explorer erwartet Radiant."""
    import math

    from spotsim.sdk_real import SpotSdkReal

    class Tag:
        id, bearing, distance, world_xy = 1, 90.0, 2.0, (1.0, 2.0)

    backend = SpotSdkReal.__new__(SpotSdkReal)
    backend.tag_id = 1
    backend.tag_welt = None
    backend._tags = lambda: [Tag()]

    _pixel, peilung, distanz, quelle = backend.detect_target()
    assert peilung == pytest.approx(math.pi / 2)
    assert distanz == pytest.approx(2.0)
    assert quelle == "apriltag_1"


def test_detect_target_ohne_treffer_meldet_unendlich():
    from spotsim.sdk_real import SpotSdkReal

    backend = SpotSdkReal.__new__(SpotSdkReal)
    backend.tag_id = 1
    backend.tag_welt = None
    backend._tags = lambda: []

    pixel, peilung, distanz, quelle = backend.detect_target()
    assert (pixel, peilung, distanz, quelle) == (0, 0.0, float("inf"), None)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ../matura-spot && python -m pytest tests/test_sdk_real.py -v -k "grad or unendlich"`
Expected: FAIL — `AttributeError: _tags`

- [ ] **Step 4: Write minimal implementation**

`detect_target` in `src/spotsim/sdk_real.py` ersetzen:

```python
    def _tags(self):
        """Die Wahrnehmung kommt aus spotlab — hier wird nur uebersetzt."""
        from spotlab.api import world

        return world.tags(self._spotlab_backend, None, id=self.tag_id)

    def detect_target(self, _ziel_rgb=None):
        """(pixel, peilung, distanz, quelle) — wie `detect_color()`, aus AprilTags.

        Duenner Adapter ueber `spotlab.api.world.tags()`: dort Grad, hier
        Radiant, weil der Explorer in Radiant rechnet. Der naechste gewinnt.
        """
        import math

        gefunden = self._tags()
        if not gefunden:
            return 0, 0.0, float("inf"), None
        tag = gefunden[0]                       # spotlab sortiert nach Distanz
        if tag.world_xy is not None:
            self.tag_welt = tag.world_xy
        return (GESEHEN_PIXEL, math.radians(tag.bearing), tag.distance,
                f"apriltag_{tag.id}")
```

`peilung_und_distanz` wird damit unbenutzt und **entfällt** — samt seines Tests.

- [ ] **Step 5: Run tests to verify**

Run: `cd ../matura-spot && python -m pytest -q`
Expected: grün, Anzahl ≥ 212 (die zwei neuen dazu, der Test von
`peilung_und_distanz` entfernt)

Run: `cd ../matura-spot && python -m pytest tests/test_explorer_naht.py -v`
Expected: **PASS** — die Naht hält

- [ ] **Step 6: Commit**

```bash
cd ../matura-spot
git add src/spotsim/sdk_real.py tests/test_sdk_real.py
git commit -m "refactor(real): AprilTag-Auswertung kommt jetzt aus spotlab"
```

---

## Task 14: matura-spot wird Klient — Gitter-Mitschnitt

**Files:**
- Delete: `../matura-spot/src/spotsim/gitter_mitschnitt.py`
- Modify: alle Importstellen in `../matura-spot`
- Test: `../matura-spot/tests/` (bestehende Gitter-Tests umhängen)

- [ ] **Step 1: Importstellen finden**

Run: `cd ../matura-spot && grep -rn "gitter_mitschnitt" --include=*.py .`
Erwartet: die Fundstellen in `scripts/` und `tests/`

- [ ] **Step 2: Importe umstellen**

Jede Fundstelle:
```python
from spotsim.gitter_mitschnitt import Gittermitschnitt, lies_mitschnitt
```
wird zu:
```python
from spotlab.beobachtung.gitter import Gittermitschnitt, lies_mitschnitt
```

- [ ] **Step 3: Alte Datei löschen**

```bash
git rm src/spotsim/gitter_mitschnitt.py
```

- [ ] **Step 4: Run tests to verify**

Run: `cd ../matura-spot && python -m pytest -q`
Expected: grün. Bei Fehlschlag: **Task rückgängig machen** (`git checkout -- .`)
und melden — matura-spots Lauffähigkeit hat Vorrang vor der Entdopplung.

- [ ] **Step 5: Commit**

```bash
cd ../matura-spot
git add -A
git commit -m "refactor(karte): Gitter-Mitschnitt kommt jetzt aus spotlab"
```

---

## Self-Review

**Spec-Abdeckung:**

| Spec | Task |
|---|---|
| §4.1 Datenklassen | 1 |
| §4.2 Verben + Aufzeichnung | 3 |
| §4.3 Gitter-Mitschnitt | 6 |
| §4.4 realer Backend | 5 |
| §4.5 Attrappen | 2 |
| §4.6 Sonde + Gate | 7 |
| §4.7 Ansicht „Umwelt" | 8 |
| §4.8 Diagnose | 9, 10 |
| §5 Datenfluss | 3 (Protokoll), 6 (Gitterablage), 8 (Anzeige) |
| §6 Fehlerbehandlung | 1 (`distance_at` → None), 3 (leer statt Fehler), 6 (Fehler gezählt), 7 (Gitter fehlt), 9/10 (`ok=True`) |
| §7 Prüfung | in jedem Task, Gesamtlauf in 11 |
| §8 Abnahme A19/A20 | 11 (Eintrag in ABNAHME.md); die Messung selbst am Gerät |
| §11 Reihenfolge | Tasks 1–12 spotlab, 13–14 matura-spot zuletzt |

**Korrekturen aus dieser Selbstprüfung** (alle bereits eingearbeitet):

1. **`expand_data_by_rle_count` gibt es im installierten SDK nicht** — nur im
   Beispiel `examples/visualizer/`. Task 5 referenzierte eine Funktion, die zur
   Laufzeit fehlt. Ersetzt durch die Portierung aus `matura-spot`, die ohnehin
   besser ist (vektorisiertes `np.repeat`, plus `unknown_cells`).
2. **`ObstacleGrid` brauchte eine Bekannt-Maske.** Ohne sie läse man unbeobachtete
   Zellen als „frei" — genau der Optimismus, vor dem §6 der Spec warnt.
3. **Die GUI darf laut CLAUDE.md auch `spotlab.backends` nicht importieren**, nicht
   nur `bosdyn`. Sie kann das Gitter-Protobuf also nicht dekodieren; Task 6 legt
   deshalb eine PNG-Vorschau neben das `.pb`, wie `kamera/` es mit Bildern hält.
4. **Neue `Capability` verpflichtet zu `docs/ABNAHME.md`** — daraus wurde Task 11.
5. **`cryptography` war nicht deklariert**, wird aber von `zertifikat.py` gebraucht;
   CLAUDE.md verlangt für jede Abhängigkeit eine Obergrenze.
6. **Die Sonde braucht einen Test, der sie als echten Prozess startet** — CLAUDE.md,
   und der Grund dafür ist dokumentiert („In VS Code öffnen" kam durch die Suite).
7. **Objektabfragen gehen nach `ereignisse.jsonl`**, nicht `zustand.jsonl` wie in
   der Spec; dessen Schlüssel dürfen sich laut CLAUDE.md nicht ändern.

**Bewusst nicht im Plan:** die Messungen für A19 und A20 selbst. Sie finden am
Roboter statt; Task 11 legt nur die Formulare dafür an.

**Typkonsistenz geprüft:** `richtung()` gibt `(bearing, distance)` in dieser
Reihenfolge — so verwendet in Task 2 (dryrun), Task 5 (realer Backend) und
getestet in Task 1. `WorldObject`-Feldreihenfolge ist in Tasks 1, 2 und 5
identisch. `tags()` hat überall die Signatur `(backend, recorder, id=None)`.
`Gittermitschnitt.zaehler()` gibt in Task 6 ein Dict, so geprüft im Test.
