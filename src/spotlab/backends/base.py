"""Was ein Backend können muss — und was es ehrlich zugeben muss, nicht zu können.

Verbindung, Lease und Not-Aus stehen bewusst NICHT im Protokoll: der spätere
Sim-Spot hat sie nicht und müsste sie sonst fälschen. Nach oben dringt
stattdessen die Fähigkeitsmenge.

`frame_tree_snapshot()` und `mobility_params()` liefern rohe Protobufs nach
oben. Das ist kein Bruch der Regel „api/ bleibt protobuf-frei", sondern ihr
Zweck: `api/` reicht diese Objekte nur an den `RobotCommandBuilder` durch und
liest sie nie. Gebaut werden sie dort, wo bosdyn ohnehin zu Hause ist.
"""

import enum
import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from spotlab.errors import UnsupportedCapability


class Capability(enum.Flag):
    NONE = 0
    LOCOMOTION = enum.auto()
    POSTURE = enum.auto()
    POWER = enum.auto()
    DEPTH_CAMERAS = enum.auto()
    GRAY_CAMERAS = enum.auto()
    COLOR_CAMERAS = enum.auto()
    LEASE = enum.auto()
    ESTOP = enum.auto()
    GRAPH_NAV = enum.auto()

    CAMERAS = DEPTH_CAMERAS | GRAY_CAMERAS | COLOR_CAMERAS


@dataclass(frozen=True)
class Feedback:
    """Rückmeldung zu einem laufenden Kommando, backend-unabhängig."""

    done: bool
    status: str  # deutscher Klartext, z. B. "steht", "unterwegs"
    rejected: bool = False


@dataclass(frozen=True)
class NavStatus:
    """Rückmeldung einer laufenden Navigation, backend-unabhängig.

    Dieselbe Naht wie Feedback: api/ bleibt dadurch protobuf-frei.
    """

    fertig: bool
    status: str  # deutscher Klartext
    gescheitert: bool = False


def richtung(x, y):
    """Aus einer Position im Koerper-Frame: (Peilung in Grad, Distanz in Meter).

    Links positiv, wie bei `move(left=…)`. Die Distanz liegt in der Bodenebene:
    ein Tag haengt auf Kniehoehe, seine Hoehe interessiert beim Hinfahren
    niemanden.

    Steht hier und nicht in `api/world.py`, weil die Backends sie fuer die
    Umwandlung brauchen und `backends/` nie aus `api/` importiert.
    """
    return math.degrees(math.atan2(y, x)), math.hypot(x, y)


@dataclass(frozen=True)
class WorldObject:
    """Ein Objekt, das Spots Firmware gerade fuehrt — backend-unabhaengig.

    Dieselbe Naht wie Feedback und NavStatus: der Backend wandelt Protobufs hier
    hinein, damit api/ protobuf-frei bleibt.
    """

    name: str
    kind: str                # "apriltag" | "dock" | "door" | "image_coordinates" | …
    bearing: float           # Grad, links positiv, im Koerper-Frame
    distance: float          # Meter, in der Bodenebene
    world_xy: tuple | None   # Position im vision-Frame
    time: float              # Erfassungszeitpunkt, Zeitbasis wie zustand.jsonl


@dataclass(frozen=True)
class Tag(WorldObject):
    """Ein AprilTag — ein WorldObject mit aufgedruckter Nummer."""

    id: int
    filtered: bool           # geglaettete Pose (True) oder rohe Einzelmessung


@dataclass(frozen=True)
class ObstacleGrid:
    """Spots Hindernisgitter: je Zelle der Abstand zum naechsten Hindernis.

    `known` traegt Spots eigene Aussage darueber, welche Zellen ueberhaupt
    beobachtet wurden. Ohne diese Maske laese man unbeobachtete Zellen als
    "frei" — genau der Optimismus, der einen Roboter in eine Wand faehrt.
    """

    cells: object            # np.ndarray, Meter je Zelle
    cell_size: float         # Kantenlaenge einer Zelle, Meter
    origin: tuple            # Weltkoordinate der Zelle [0, 0]
    time: float
    known: object = None     # np.ndarray bool, oder None = alles bekannt

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


@dataclass(frozen=True)
class SafetyStatus:
    lease_holder: str | None
    estop_level: str | None


@runtime_checkable
class SpotBackend(Protocol):
    def capabilities(self) -> Capability: ...
    def send_command(self, command, end_time_secs=None) -> str: ...
    def command_feedback(self, command_id) -> Feedback: ...
    def robot_state(self): ...
    def frame_tree_snapshot(self): ...
    def mobility_params(self, limits): ...
    def image_sources(self) -> list: ...
    def images(self, sources) -> list: ...
    def power_on(self) -> None: ...
    def power_off(self, safe=True) -> None: ...
    @property
    def is_powered(self) -> bool: ...
    def safety_status(self) -> SafetyStatus: ...
    def close(self) -> None: ...


_EINZELN = (
    Capability.LOCOMOTION,
    Capability.POSTURE,
    Capability.POWER,
    Capability.DEPTH_CAMERAS,
    Capability.GRAY_CAMERAS,
    Capability.COLOR_CAMERAS,
    Capability.LEASE,
    Capability.ESTOP,
    Capability.GRAPH_NAV,
)


def require(backend, capability, wofuer):
    """Prüft eine Fähigkeit. Beim Alias CAMERAS genügt eine der drei Kameraarten."""
    vorhanden = backend.capabilities()
    if vorhanden & capability:
        return
    raise UnsupportedCapability(
        f"Dieses Backend beherrscht '{wofuer}' nicht. Vorhanden: {_lesbar(vorhanden)}."
    )


def _lesbar(faehigkeiten):
    namen = [glied.name.lower() for glied in _EINZELN if glied & faehigkeiten]
    return ", ".join(namen) if namen else "nichts"
