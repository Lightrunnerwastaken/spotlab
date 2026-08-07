"""Was ein Backend können muss — und was es ehrlich zugeben muss, nicht zu können.

Verbindung, Lease und Not-Aus stehen bewusst NICHT im Protokoll: der spätere
Sim-Spot hat sie nicht und müsste sie sonst fälschen. Nach oben dringt
stattdessen die Fähigkeitsmenge.
"""

import enum
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
