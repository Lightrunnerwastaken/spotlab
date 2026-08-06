# spotlab Fundament — Implementierungsplan, Teil 2 (Backends und Bibliothek)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Fortsetzung von `2026-08-06-spotlab-fundament.md`. **Global Constraints** von dort gelten unverändert weiter.

**Umfang dieses Teils:** Tasks 6–12 — Backend-Protokoll, Trockenlauf-Backend, die Schülerverben, `connect()` und der Zustandsabtaster.

---

## Task 6: Backend-Protokoll und Fähigkeiten

**Files:**
- Create: `src/spotlab/backends/__init__.py`, `src/spotlab/backends/base.py`, `tests/test_backend_base.py`

**Interfaces:**
- Consumes: `spotlab.errors.UnsupportedCapability`
- Produces:
  - `Capability(enum.Flag)` mit `NONE, LOCOMOTION, POSTURE, POWER, DEPTH_CAMERAS, GRAY_CAMERAS, COLOR_CAMERAS, LEASE, ESTOP` und dem Alias `CAMERAS = DEPTH_CAMERAS | GRAY_CAMERAS | COLOR_CAMERAS`
  - `Feedback(done: bool, status: str, rejected: bool = False)` — frozen dataclass
  - `SafetyStatus(lease_holder: str | None, estop_level: str | None)` — frozen dataclass
  - `SpotBackend` (`typing.Protocol`) mit `capabilities()`, `send_command(cmd, end_time_secs=None) -> str`, `command_feedback(cmd_id) -> Feedback`, `robot_state()`, `frame_tree_snapshot()`, `image_sources() -> list[str]`, `images(sources) -> list`, `power_on()`, `power_off(safe=True)`, `is_powered -> bool`, `safety_status() -> SafetyStatus`, `close()`
  - `require(backend, capability, wofuer: str) -> None` — wirft `UnsupportedCapability` mit deutschem Klartext

**Warum `Feedback` und nicht das rohe Protobuf:** die Rückmeldungsstruktur des SDK ist tief verschachtelt (`synchronized_feedback.mobility_command_feedback.stand_feedback.status`). Läge das Auslesen in `api/`, müsste jedes Verb Protobuf-Interna kennen und das Trockenlauf-Backend sie nachbauen. `Feedback` ist die schmale Naht; das rohe Protobuf bleibt über `spot.robot` erreichbar.

- [ ] **Step 1: Test schreiben** — `tests/test_backend_base.py`

```python
import pytest

from spotlab.backends.base import Capability, Feedback, SafetyStatus, require
from spotlab.errors import UnsupportedCapability


class Attrappe:
    def __init__(self, koennen):
        self._koennen = koennen

    def capabilities(self):
        return self._koennen


def test_kameras_alias_deckt_alle_drei_arten():
    assert Capability.DEPTH_CAMERAS in Capability.CAMERAS
    assert Capability.GRAY_CAMERAS in Capability.CAMERAS
    assert Capability.COLOR_CAMERAS in Capability.CAMERAS
    assert Capability.LOCOMOTION not in Capability.CAMERAS


def test_require_laesst_vorhandene_faehigkeit_durch():
    require(Attrappe(Capability.LOCOMOTION | Capability.POWER),
            Capability.LOCOMOTION, "gehen")


def test_require_meldet_fehlende_faehigkeit_auf_deutsch():
    with pytest.raises(UnsupportedCapability) as info:
        require(Attrappe(Capability.LOCOMOTION), Capability.CAMERAS, "Kamerabilder")
    text = str(info.value)
    assert "Kamerabilder" in text
    assert "Backend" in text


def test_require_akzeptiert_teilmenge_bei_alias():
    """Ein Backend mit nur Tiefenkameras erfüllt die Anforderung CAMERAS."""
    require(Attrappe(Capability.DEPTH_CAMERAS), Capability.CAMERAS, "Kamerabilder")


def test_feedback_ist_unveraenderlich():
    rueck = Feedback(done=True, status="steht")
    with pytest.raises(AttributeError):
        rueck.done = False


def test_safety_status_darf_leer_sein():
    zustand = SafetyStatus(lease_holder=None, estop_level=None)
    assert zustand.lease_holder is None
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_backend_base.py -v`

- [ ] **Step 3: `backends/base.py` implementieren**

```python
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

    CAMERAS = DEPTH_CAMERAS | GRAY_CAMERAS | COLOR_CAMERAS


@dataclass(frozen=True)
class Feedback:
    """Rückmeldung zu einem laufenden Kommando, backend-unabhängig."""
    done: bool
    status: str                 # deutscher Klartext, z. B. "steht", "unterwegs"
    rejected: bool = False


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


def require(backend, capability, wofuer):
    """Prüft eine Fähigkeit. Beim Alias CAMERAS genügt eine der drei Kameraarten."""
    vorhanden = backend.capabilities()
    if vorhanden & capability:
        return
    raise UnsupportedCapability(
        f"Dieses Backend kann {wofuer} nicht. "
        f"Vorhanden: {_lesbar(vorhanden)}.")


def _lesbar(faehigkeiten):
    namen = [glied.name.lower() for glied in Capability
             if glied.name and glied is not Capability.NONE
             and glied.name != "CAMERAS" and glied & faehigkeiten]
    return ", ".join(namen) if namen else "nichts"
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_backend_base.py -v`, erwartet 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends tests/test_backend_base.py && git commit -m "feat(backends): Protokoll, Fähigkeiten und Rückmeldungstyp"
```

---

## Task 7: Trockenlauf-Backend

**Files:**
- Create: `src/spotlab/backends/dryrun.py`, `tests/test_dryrun.py`

**Interfaces:**
- Consumes: `Capability`, `Feedback`, `SafetyStatus`, `UnsupportedCapability`, `NotPowered`
- Produces: `DryRunBackend(recorder=None)` — erfüllt `SpotBackend`; Fähigkeiten `LOCOMOTION | POSTURE | POWER`; Attribut `.gesendet: list[RobotCommand]` für Tests

**Verhalten:** validiert das eingehende Protobuf (muss `bosdyn.api.RobotCommand` sein und ein `synchronized_command` tragen), legt es ab, meldet beim ersten `command_feedback` „unterwegs" und danach „fertig". Liefert einen schema-korrekten `RobotState` mit `kinematic_state.transforms_snapshot` (vision→odom→body), damit `move()` auch trocken baubar ist.

- [ ] **Step 1: Test schreiben** — `tests/test_dryrun.py`

```python
import pytest
from bosdyn.api import robot_command_pb2
from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.backends.base import Capability
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import NotPowered, UnsupportedCapability


def test_faehigkeiten_sind_ehrlich():
    koennen = DryRunBackend().capabilities()
    assert koennen & Capability.LOCOMOTION
    assert not (koennen & Capability.CAMERAS)
    assert not (koennen & Capability.LEASE)


def test_echtes_protobuf_wird_angenommen_und_abgelegt():
    backend = DryRunBackend()
    backend.power_on()
    kommando = RobotCommandBuilder.synchro_stand_command()
    kennung = backend.send_command(kommando)
    assert isinstance(kennung, str)
    assert len(backend.gesendet) == 1
    assert backend.gesendet[0].HasField("synchronized_command")


def test_bytes_werden_ebenfalls_akzeptiert():
    """Wie über gRPC: dasselbe Kommando als serialisierte Bytes."""
    backend = DryRunBackend()
    backend.power_on()
    roh = RobotCommandBuilder.synchro_velocity_command(0.5, 0.0, 0.0).SerializeToString()
    backend.send_command(roh)
    assert backend.gesendet[0].synchronized_command.mobility_command.HasField(
        "se2_velocity_request")


def test_fremdes_protobuf_wird_abgelehnt():
    backend = DryRunBackend()
    backend.power_on()
    with pytest.raises(ValueError, match="RobotCommand"):
        backend.send_command(robot_command_pb2.RobotCommandResponse())


def test_kommando_ohne_strom_wird_abgelehnt():
    backend = DryRunBackend()
    with pytest.raises(NotPowered):
        backend.send_command(RobotCommandBuilder.synchro_stand_command())


def test_rueckmeldung_wird_nach_einem_abruf_fertig():
    backend = DryRunBackend()
    backend.power_on()
    kennung = backend.send_command(RobotCommandBuilder.synchro_stand_command())
    assert backend.command_feedback(kennung).done is False
    assert backend.command_feedback(kennung).done is True


def test_robot_state_hat_batterie_und_gelenke():
    zustand = DryRunBackend().robot_state()
    assert zustand.battery_states[0].charge_percentage.value > 0
    assert len(zustand.kinematic_state.joint_states) == 12


def test_frame_tree_snapshot_enthaelt_body_und_odom():
    schnappschuss = DryRunBackend().frame_tree_snapshot()
    assert "body" in schnappschuss.child_to_parent_edge_map
    assert "odom" in schnappschuss.child_to_parent_edge_map


def test_kameras_werden_ehrlich_verweigert():
    backend = DryRunBackend()
    assert backend.image_sources() == []
    with pytest.raises(UnsupportedCapability):
        backend.images(["frontleft_fisheye_image"])


def test_safety_status_ist_leer():
    zustand = DryRunBackend().safety_status()
    assert zustand.lease_holder is None and zustand.estop_level is None
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_dryrun.py -v`

- [ ] **Step 3: `backends/dryrun.py` implementieren**

```python
"""Trockenlauf: baut und prüft echte Protobufs, bewegt nichts.

Doppelrolle — Standard-Testdouble der Testsuite UND ausgeliefertes Feature:
`spotlab run --dryrun` lässt einen Schüler zu Hause ohne Roboter und ohne Netz
prüfen, ob sein Skript überhaupt durchläuft.
"""

import itertools

from bosdyn.api import geometry_pb2, robot_command_pb2, robot_state_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, VISION_FRAME_NAME
from google.protobuf import wrappers_pb2

from spotlab.backends.base import Capability, Feedback, SafetyStatus
from spotlab.errors import NotPowered, UnsupportedCapability

GELENKE = ["fl.hx", "fl.hy", "fl.kn", "fr.hx", "fr.hy", "fr.kn",
           "hl.hx", "hl.hy", "hl.kn", "hr.hx", "hr.hy", "hr.kn"]


def _identitaets_kante(parent):
    kante = geometry_pb2.FrameTreeSnapshot.ParentEdge(parent_frame_name=parent)
    kante.parent_tform_child.rotation.w = 1.0
    return kante


class DryRunBackend:
    def __init__(self, recorder=None):
        self._recorder = recorder
        self._powered = False
        self._zaehler = itertools.count(1)
        self._offen = {}
        self.gesendet = []

    def capabilities(self):
        return Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER

    # ------------------------------------------------------------- Kommandos

    def send_command(self, command, end_time_secs=None):
        if not self._powered:
            raise NotPowered("Die Motoren sind aus — rufe zuerst `spot.power_on()` auf.")
        kommando = self._als_robot_command(command)
        self.gesendet.append(kommando)
        kennung = f"dryrun-{next(self._zaehler)}"
        self._offen[kennung] = 0
        return kennung

    def command_feedback(self, command_id):
        abrufe = self._offen.get(command_id, 0)
        self._offen[command_id] = abrufe + 1
        if abrufe == 0:
            return Feedback(done=False, status="unterwegs (Trockenlauf)")
        return Feedback(done=True, status="fertig (Trockenlauf)")

    @staticmethod
    def _als_robot_command(command):
        if isinstance(command, (bytes, bytearray)):
            kommando = robot_command_pb2.RobotCommand()
            kommando.ParseFromString(bytes(command))
            return kommando
        if not isinstance(command, robot_command_pb2.RobotCommand):
            raise ValueError(
                f"Erwartet wird ein bosdyn RobotCommand-Protobuf, bekommen: "
                f"{type(command).__name__}")
        return command

    # ------------------------------------------------------------- Zustand

    def robot_state(self):
        zustand = robot_state_pb2.RobotState()
        akku = zustand.battery_states.add()
        akku.charge_percentage.CopyFrom(wrappers_pb2.DoubleValue(value=87.0))
        zustand.power_state.motor_power_state = (
            robot_state_pb2.PowerState.STATE_ON if self._powered
            else robot_state_pb2.PowerState.STATE_OFF)
        for name in GELENKE:
            gelenk = zustand.kinematic_state.joint_states.add()
            gelenk.name = name
            gelenk.position.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.velocity.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.load.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
        for _ in range(4):
            fuss = zustand.foot_state.add()
            fuss.contact = robot_state_pb2.FootState.CONTACT_MADE
        zustand.kinematic_state.transforms_snapshot.CopyFrom(self.frame_tree_snapshot())
        return zustand

    def frame_tree_snapshot(self):
        schnappschuss = geometry_pb2.FrameTreeSnapshot()
        schnappschuss.child_to_parent_edge_map[VISION_FRAME_NAME].CopyFrom(
            geometry_pb2.FrameTreeSnapshot.ParentEdge())
        schnappschuss.child_to_parent_edge_map[ODOM_FRAME_NAME].CopyFrom(
            _identitaets_kante(VISION_FRAME_NAME))
        schnappschuss.child_to_parent_edge_map[BODY_FRAME_NAME].CopyFrom(
            _identitaets_kante(ODOM_FRAME_NAME))
        return schnappschuss

    # ------------------------------------------------------------- Rest

    def image_sources(self):
        return []

    def images(self, sources):
        raise UnsupportedCapability(
            "Der Trockenlauf hat keine Kameras. Für Bilder brauchst du den echten Spot.")

    def power_on(self):
        self._powered = True

    def power_off(self, safe=True):
        self._powered = False

    @property
    def is_powered(self):
        return self._powered

    def safety_status(self):
        return SafetyStatus(lease_holder=None, estop_level=None)

    def close(self):
        self._powered = False
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_dryrun.py -v`, erwartet 10 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/dryrun.py tests/test_dryrun.py && git commit -m "feat(backends): Trockenlauf-Backend mit echter Protobuf-Prüfung"
```

---

## Task 8: Zustandsschnappschuss

**Files:**
- Create: `src/spotlab/api/__init__.py`, `src/spotlab/api/state.py`, `tests/test_api_state.py`

**Interfaces:**
- Consumes: `robot_state_pb2.RobotState`
- Produces:
  - `State` frozen dataclass: `battery: float`, `powered: bool`, `pose: tuple[float,float,float]` (x, y, yaw in rad), `velocity: tuple[float,float,float]` (vx, vy, wz), `joints: dict[str, JointState]`, `feet: tuple[bool,bool,bool,bool]`
  - `JointState` frozen dataclass: `position, velocity, load`
  - `from_proto(zustand) -> State`
  - `as_sample(zustand) -> dict` — flache, JSON-fähige Abbildung für `zustand.jsonl`

- [ ] **Step 1: Test schreiben** — `tests/test_api_state.py`

```python
import math

from spotlab.api.state import as_sample, from_proto
from spotlab.backends.dryrun import DryRunBackend


def test_zustand_aus_protobuf():
    backend = DryRunBackend()
    backend.power_on()
    zustand = from_proto(backend.robot_state())
    assert zustand.battery == 87.0
    assert zustand.powered is True
    assert len(zustand.joints) == 12
    assert zustand.joints["fl.hx"].position == 0.0
    assert zustand.feet == (True, True, True, True)


def test_pose_aus_identitaet_ist_ursprung():
    zustand = from_proto(DryRunBackend().robot_state())
    x, y, yaw = zustand.pose
    assert (x, y) == (0.0, 0.0)
    assert math.isclose(yaw, 0.0, abs_tol=1e-9)


def test_abtastung_ist_flach_und_json_faehig():
    import json
    probe = as_sample(DryRunBackend().robot_state())
    json.dumps(probe)               # darf nicht werfen
    assert probe["battery"] == 87.0
    assert probe["pose"] == [0.0, 0.0, 0.0]
    assert probe["joints"]["fl.hy"]["position"] == 0.0
    assert probe["feet"] == [True, True, True, True]
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_api_state.py -v`

- [ ] **Step 3: `api/state.py` implementieren**

```python
"""Roboterzustand als handliche Datenklasse — und als flache Abtastung für zustand.jsonl.

Die flache Form ist die Kalibrierdatenquelle für Real→Sim: kommandierte gegen
gemessene Geschwindigkeit, Gelenkverläufe, Fusskontakt-Timing.
"""

import math
from dataclasses import dataclass

from bosdyn.api import robot_state_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b


@dataclass(frozen=True)
class JointState:
    position: float
    velocity: float
    load: float


@dataclass(frozen=True)
class State:
    battery: float
    powered: bool
    pose: tuple
    velocity: tuple
    joints: dict
    feet: tuple


def _yaw_aus(quaternion):
    w, x, y, z = quaternion.w, quaternion.x, quaternion.y, quaternion.z
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def from_proto(zustand):
    akku = zustand.battery_states[0].charge_percentage.value if zustand.battery_states else 0.0
    kinematik = zustand.kinematic_state

    x = y = yaw = 0.0
    try:
        odom_tform_body = get_a_tform_b(
            kinematik.transforms_snapshot, ODOM_FRAME_NAME, BODY_FRAME_NAME)
        if odom_tform_body is not None:
            x = odom_tform_body.position.x
            y = odom_tform_body.position.y
            yaw = _yaw_aus(odom_tform_body.rotation)
    except Exception:            # Schnappschuss unvollständig — Pose bleibt Ursprung
        pass

    geschwindigkeit = kinematik.velocity_of_body_in_odom
    return State(
        battery=akku,
        powered=zustand.power_state.motor_power_state == robot_state_pb2.PowerState.STATE_ON,
        pose=(x, y, yaw),
        velocity=(geschwindigkeit.linear.x, geschwindigkeit.linear.y,
                  geschwindigkeit.angular.z),
        joints={g.name: JointState(g.position.value, g.velocity.value, g.load.value)
                for g in kinematik.joint_states},
        feet=tuple(f.contact == robot_state_pb2.FootState.CONTACT_MADE
                   for f in zustand.foot_state),
    )


def as_sample(zustand):
    s = from_proto(zustand)
    return {
        "battery": s.battery,
        "powered": s.powered,
        "pose": list(s.pose),
        "velocity": list(s.velocity),
        "joints": {name: {"position": g.position, "velocity": g.velocity, "load": g.load}
                   for name, g in s.joints.items()},
        "feet": list(s.feet),
    }
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_api_state.py -v`, erwartet 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/api tests/test_api_state.py && git commit -m "feat(api): Zustandsschnappschuss und flache Abtastung"
```

---

## Task 9: Haltung — stand und sit

**Files:**
- Create: `src/spotlab/api/posture.py`, `tests/test_api_posture.py`

**Interfaces:**
- Consumes: `Capability`, `require`, `Feedback`, `RobotCommandBuilder`
- Produces:
  - `stand(backend, recorder, height=0.0, timeout=10.0, schlaf=time.sleep) -> None`
  - `sit(backend, recorder, timeout=10.0, schlaf=time.sleep) -> None`
  - `warte_auf(backend, kennung, timeout, was, schlaf) -> None` — pollt `command_feedback`, wirft `CommandRejected` bei `rejected`, `SpotlabError` bei Zeitüberschreitung

**Der `schlaf`-Parameter** ist die Testnaht: die Tests reichen eine Attrappe herein, damit kein Test real wartet.

- [ ] **Step 1: Test schreiben** — `tests/test_api_posture.py`

```python
import pytest

from spotlab.api.posture import sit, stand, warte_auf
from spotlab.backends.base import Feedback
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import CommandRejected, SpotlabError


def _backend():
    backend = DryRunBackend()
    backend.power_on()
    return backend


def test_stand_baut_ein_echtes_stand_protobuf():
    backend = _backend()
    stand(backend, None, schlaf=lambda _: None)
    kommando = backend.gesendet[0].synchronized_command.mobility_command
    assert kommando.HasField("stand_request")


def test_stand_reicht_koerperhoehe_durch():
    backend = _backend()
    stand(backend, None, height=0.05, schlaf=lambda _: None)
    params = backend.gesendet[0].synchronized_command.mobility_command.params
    assert params.value  # MobilityParams sind gesetzt


def test_sit_baut_ein_echtes_sit_protobuf():
    backend = _backend()
    sit(backend, None, schlaf=lambda _: None)
    kommando = backend.gesendet[0].synchronized_command.mobility_command
    assert kommando.HasField("sit_request")


def test_abgelehntes_kommando_wird_zu_klartext():
    class Abweisend(DryRunBackend):
        def command_feedback(self, command_id):
            return Feedback(done=False, status="abgelehnt", rejected=True)

    backend = Abweisend()
    backend.power_on()
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    assert "abgelehnt" in str(info.value)


def test_zeitueberschreitung_meldet_klartext():
    class Endlos(DryRunBackend):
        def command_feedback(self, command_id):
            return Feedback(done=False, status="unterwegs")

    backend = Endlos()
    backend.power_on()
    uhr = iter([0.0, 5.0, 20.0, 40.0])
    with pytest.raises(SpotlabError) as info:
        warte_auf(backend, "x", timeout=10.0, was="aufstehen",
                  schlaf=lambda _: None, jetzt=lambda: next(uhr))
    assert "aufstehen" in str(info.value)


def test_ereignisse_werden_aufgezeichnet(tmp_path):
    from spotlab.record.run import RunRecorder
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    stand(_backend(), rec, schlaf=lambda _: None)
    rec.finish("ok")
    text = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert '"kommando"' in text and "stand" in text
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_api_posture.py -v`

- [ ] **Step 3: `api/posture.py` implementieren**

```python
"""Haltung: aufstehen und hinsetzen.

Beide blockieren, bis der Roboter die Haltung tatsächlich MELDET — nicht bis
eine geschätzte Zeit vergangen ist. sleep() lügt, Rückmeldung nicht.
"""

import time

from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.backends.base import Capability, require
from spotlab.errors import CommandRejected, SpotlabError

POLL_S = 0.25


def warte_auf(backend, kennung, timeout, was, schlaf=time.sleep, jetzt=time.monotonic):
    ende = jetzt() + timeout
    while True:
        rueck = backend.command_feedback(kennung)
        if rueck.rejected:
            raise CommandRejected(
                f"Der Roboter hat das Kommando '{was}' abgelehnt: {rueck.status}")
        if rueck.done:
            return
        if jetzt() >= ende:
            raise SpotlabError(
                f"Der Roboter hat '{was}' nicht innerhalb von {timeout:.0f} s "
                f"abgeschlossen (zuletzt: {rueck.status}).")
        schlaf(POLL_S)


def _protokolliere(recorder, name, **daten):
    if recorder is not None:
        recorder.event("kommando", name=name, **daten)


def stand(backend, recorder, height=0.0, timeout=10.0, schlaf=time.sleep):
    require(backend, Capability.POSTURE, "aufstehen")
    kommando = RobotCommandBuilder.synchro_stand_command(body_height=float(height))
    _protokolliere(recorder, "stand", height=float(height))
    kennung = backend.send_command(kommando)
    warte_auf(backend, kennung, timeout, "aufstehen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="stand", status="steht")


def sit(backend, recorder, timeout=10.0, schlaf=time.sleep):
    require(backend, Capability.POSTURE, "hinsetzen")
    kommando = RobotCommandBuilder.synchro_sit_command()
    _protokolliere(recorder, "sit")
    kennung = backend.send_command(kommando)
    warte_auf(backend, kennung, timeout, "hinsetzen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="sit", status="sitzt")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_api_posture.py -v`, erwartet 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/api/posture.py tests/test_api_posture.py && git commit -m "feat(api): stand und sit mit echter Rückmeldung"
```

---

## Task 10: Bewegung — move, walk, stop

**Files:**
- Create: `src/spotlab/api/motion.py`, `tests/test_api_motion.py`

**Interfaces:**
- Consumes: `Capability`, `require`, `warte_auf`, `Limits`, `RobotCommandBuilder`
- Produces:
  - `clamp(vx, vy, wz, limits) -> tuple[float, float, float]`
  - `move(backend, recorder, limits, forward=0.0, left=0.0, turn=0.0, timeout=30.0, schlaf=time.sleep) -> None` — `turn` in **Grad**
  - `walk(backend, recorder, limits, vx=0.0, vy=0.0, wz=0.0, duration=1.0, schlaf=time.sleep, jetzt=time.monotonic) -> None`
  - `stop(backend, recorder) -> None`
  - `NACHSENDE_INTERVALL_S = 0.4`, `KOMMANDO_GUELTIGKEIT_S = 1.0`

**Warum `walk` nachsendet:** Geschwindigkeitskommandos verfallen beim echten Spot. Ein Schüler, der `walk(vx=0.3, duration=10)` schreibt, würde sonst nach einer Sekunde stehen. Das Nachsenden gehört in die Bibliothek, nicht in jedes Schülerskript.

- [ ] **Step 1: Test schreiben** — `tests/test_api_motion.py`

```python
import math

import pytest

from spotlab.api.motion import clamp, move, stop, walk
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits


def _backend():
    backend = DryRunBackend()
    backend.power_on()
    return backend


def test_geschwindigkeit_wird_geklemmt_nicht_abgewiesen():
    vx, vy, wz = clamp(5.0, 0.0, 9.0, Limits(max_speed=0.6, max_turn_rate=0.8))
    assert vx == 0.6 and wz == 0.8


def test_klemmen_erhaelt_die_richtung():
    vx, vy, _ = clamp(3.0, 4.0, 0.0, Limits(max_speed=0.5, max_turn_rate=0.8))
    assert math.isclose(math.hypot(vx, vy), 0.5, rel_tol=1e-9)
    assert math.isclose(vx / vy, 3 / 4, rel_tol=1e-9)


def test_negative_werte_werden_symmetrisch_geklemmt():
    vx, _, wz = clamp(-5.0, 0.0, -9.0, Limits(max_speed=0.6, max_turn_rate=0.8))
    assert vx == -0.6 and wz == -0.8


def test_walk_baut_geschwindigkeitskommandos_und_sendet_nach():
    backend = _backend()
    uhr = iter([0.0, 0.0, 0.5, 1.0, 1.5])
    walk(backend, None, Limits(), vx=0.3, duration=1.2,
         schlaf=lambda _: None, jetzt=lambda: next(uhr))
    assert len(backend.gesendet) >= 2          # nachgesendet, nicht einmalig
    mobility = backend.gesendet[0].synchronized_command.mobility_command
    assert mobility.HasField("se2_velocity_request")
    assert math.isclose(mobility.se2_velocity_request.velocity.linear.x, 0.3, rel_tol=1e-6)


def test_walk_beendet_mit_stopp():
    backend = _backend()
    uhr = iter([0.0, 0.0, 2.0])
    walk(backend, None, Limits(), vx=0.3, duration=1.0,
         schlaf=lambda _: None, jetzt=lambda: next(uhr))
    letztes = backend.gesendet[-1].synchronized_command.mobility_command
    assert letztes.HasField("stop_request")


def test_move_baut_eine_trajektorie():
    backend = _backend()
    move(backend, None, Limits(), forward=1.0, schlaf=lambda _: None)
    mobility = backend.gesendet[0].synchronized_command.mobility_command
    assert mobility.HasField("se2_trajectory_request")


def test_move_rechnet_grad_in_bogenmass():
    backend = _backend()
    move(backend, None, Limits(), turn=90.0, schlaf=lambda _: None)
    ziel = backend.gesendet[0].synchronized_command.mobility_command.se2_trajectory_request
    punkt = ziel.trajectory.points[0].pose
    assert math.isclose(punkt.angle, math.pi / 2, rel_tol=1e-6)


def test_move_ohne_ziel_macht_nichts():
    backend = _backend()
    move(backend, None, Limits(), schlaf=lambda _: None)
    assert backend.gesendet == []


def test_stop_baut_ein_stopp_kommando():
    backend = _backend()
    stop(backend, None)
    assert backend.gesendet[0].synchronized_command.mobility_command.HasField("stop_request")


def test_bewegung_ohne_faehigkeit_wird_verweigert():
    from spotlab.backends.base import Capability
    from spotlab.errors import UnsupportedCapability

    class OhneBeine(DryRunBackend):
        def capabilities(self):
            return Capability.POWER

    backend = OhneBeine()
    backend.power_on()
    with pytest.raises(UnsupportedCapability):
        walk(backend, None, Limits(), vx=0.1, duration=0.1,
             schlaf=lambda _: None, jetzt=lambda: 0.0)
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_api_motion.py -v`

- [ ] **Step 3: `api/motion.py` implementieren**

```python
"""Bewegung auf zwei Ebenen.

move()  — relative Zieltrajektorie: „geh einen Meter" ohne Zeitintegration.
walk()  — Geschwindigkeitskommando des SDK, Andockpunkt für Regelschleifen
          und spätere neuronale Netze.

Der Geschwindigkeitsdeckel klemmt und weist nicht ab: ein Tippfehler soll
langsam sein, nicht knallen.
"""

import math
import time

from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.api.posture import warte_auf
from spotlab.backends.base import Capability, require

NACHSENDE_INTERVALL_S = 0.4
KOMMANDO_GUELTIGKEIT_S = 1.0


def clamp(vx, vy, wz, limits):
    """Klemmt auf die Konfigurationsgrenzen und erhält dabei die Fahrtrichtung."""
    betrag = math.hypot(vx, vy)
    if betrag > limits.max_speed and betrag > 0.0:
        faktor = limits.max_speed / betrag
        vx, vy = vx * faktor, vy * faktor
    wz = max(-limits.max_turn_rate, min(limits.max_turn_rate, wz))
    return float(vx), float(vy), float(wz)


def walk(backend, recorder, limits, vx=0.0, vy=0.0, wz=0.0, duration=1.0,
         schlaf=time.sleep, jetzt=time.monotonic):
    """Fährt `duration` Sekunden mit der gegebenen Geschwindigkeit.

    Geschwindigkeitskommandos verfallen beim echten Spot — deshalb sendet diese
    Funktion laufend nach. Genau das soll kein Schüler selbst bauen müssen.
    """
    require(backend, Capability.LOCOMOTION, "gehen")
    vx, vy, wz = clamp(vx, vy, wz, limits)
    if recorder is not None:
        recorder.event("kommando", name="walk", vx=vx, vy=vy, wz=wz, duration=duration)

    ende = jetzt() + float(duration)
    while jetzt() < ende:
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=vx, v_y=vy, v_rot=wz),
            end_time_secs=KOMMANDO_GUELTIGKEIT_S)
        schlaf(NACHSENDE_INTERVALL_S)
    stop(backend, recorder)


def move(backend, recorder, limits, forward=0.0, left=0.0, turn=0.0,
         timeout=30.0, schlaf=time.sleep):
    """Relatives Ziel im Körperframe. `turn` in GRAD (Schülerfreundlichkeit)."""
    require(backend, Capability.LOCOMOTION, "gehen")
    if forward == 0.0 and left == 0.0 and turn == 0.0:
        return
    winkel = math.radians(float(turn))
    if recorder is not None:
        recorder.event("kommando", name="move", forward=float(forward),
                       left=float(left), turn_grad=float(turn))
    kommando = RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
        goal_x_rt_body=float(forward),
        goal_y_rt_body=float(left),
        goal_heading_rt_body=winkel,
        frame_tree_snapshot=backend.frame_tree_snapshot())
    kennung = backend.send_command(kommando)
    warte_auf(backend, kennung, timeout, "ankommen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="move", status="angekommen")


def stop(backend, recorder):
    require(backend, Capability.LOCOMOTION, "anhalten")
    if recorder is not None:
        recorder.event("kommando", name="stop")
    backend.send_command(RobotCommandBuilder.stop_command())
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_api_motion.py -v`, erwartet 10 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/api/motion.py tests/test_api_motion.py && git commit -m "feat(api): move, walk mit Nachsenden, stop und Geschwindigkeitsdeckel"
```

---

## Task 11: Wahrnehmung — Kameras

**Files:**
- Create: `src/spotlab/api/perception.py`, `tests/test_api_perception.py`

**Interfaces:**
- Consumes: `Capability`, `require`, `image_pb2`
- Produces:
  - `Image` Klasse: `.source: str`, `.width`, `.height`, `.array -> numpy.ndarray`, `.raw: bytes`, `.intrinsics: dict`, `.save(pfad) -> Path`
  - `KURZNAMEN: dict[str, tuple[str, ...]]` — `"frontleft"` → Kandidatenliste echter Quellnamen
  - `cameras(backend) -> list[str]` — Kurznamen, die dieses Backend wirklich hat
  - `camera(backend, recorder, name) -> Image`
  - `aufloesen(name, vorhandene) -> str` — Kurzname → echter Quellname, sonst `SpotlabError` mit Aufzählung

- [ ] **Step 1: Test schreiben** — `tests/test_api_perception.py`

```python
import numpy as np
import pytest
from bosdyn.api import image_pb2

from spotlab.api.perception import Image, aufloesen, camera, cameras
from spotlab.backends.base import Capability, SafetyStatus
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import SpotlabError, UnsupportedCapability

QUELLEN = ["frontleft_fisheye_image", "frontleft_depth", "back_fisheye_image"]


class MitKamera(DryRunBackend):
    def capabilities(self):
        return (Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
                | Capability.GRAY_CAMERAS | Capability.DEPTH_CAMERAS)

    def image_sources(self):
        return list(QUELLEN)

    def images(self, sources):
        antwort = image_pb2.ImageResponse()
        antwort.source.name = sources[0]
        antwort.shot.image.cols = 4
        antwort.shot.image.rows = 2
        antwort.shot.image.pixel_format = image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8
        antwort.shot.image.format = image_pb2.Image.FORMAT_RAW
        antwort.shot.image.data = bytes(range(8))
        antwort.source.pinhole.intrinsics.focal_length.x = 200.0
        return [antwort]


def test_kurznamen_werden_aufgeloest():
    assert aufloesen("frontleft", QUELLEN) == "frontleft_fisheye_image"


def test_echter_quellname_geht_direkt_durch():
    assert aufloesen("back_fisheye_image", QUELLEN) == "back_fisheye_image"


def test_unbekannter_name_zaehlt_die_vorhandenen_auf():
    with pytest.raises(SpotlabError) as info:
        aufloesen("oben", QUELLEN)
    assert "frontleft" in str(info.value)


def test_cameras_meldet_nur_vorhandene_kurznamen():
    assert set(cameras(MitKamera())) == {"frontleft", "back"}


def test_bild_wird_zu_numpy_array():
    bild = camera(MitKamera(), None, "frontleft")
    assert isinstance(bild, Image)
    assert bild.array.shape == (2, 4)
    assert bild.array.dtype == np.uint8


def test_bild_traegt_intrinsics():
    bild = camera(MitKamera(), None, "frontleft")
    assert bild.intrinsics["focal_length_x"] == 200.0


def test_bild_speichern_erzeugt_datei(tmp_path):
    ziel = camera(MitKamera(), None, "frontleft").save(tmp_path / "vorne.png")
    assert ziel.exists() and ziel.stat().st_size > 0


def test_bild_wird_im_lauf_verzeichnet(tmp_path):
    from spotlab.record.run import RunRecorder
    rec = RunRecorder(tmp_path, None, backend="test")
    camera(MitKamera(), rec, "frontleft")
    rec.finish("ok")
    assert (rec.dir / "bilder" / "bilder.json").exists()


def test_ohne_kamera_faehigkeit_klare_verweigerung():
    with pytest.raises(UnsupportedCapability):
        camera(DryRunBackend(), None, "frontleft")
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_api_perception.py -v`

- [ ] **Step 3: `api/perception.py` implementieren**

```python
"""Kamerabilder.

Die Quellnamen des echten Spot sind sperrig (`frontleft_fisheye_image`). Die
Bibliothek nimmt Kurznamen entgegen und löst sie gegen die vom Roboter
GEMELDETEN Quellen auf — nicht gegen eine fest verdrahtete Liste, denn die
Benennung ist eine unbestätigte Annahme (Spec A2).
"""

import io
from pathlib import Path

import numpy as np
from bosdyn.api import image_pb2

from spotlab.backends.base import Capability, require
from spotlab.errors import SpotlabError

KURZNAMEN = {
    "frontleft": ("frontleft_fisheye_image", "frontleft_depth"),
    "frontright": ("frontright_fisheye_image", "frontright_depth"),
    "left": ("left_fisheye_image", "left_depth"),
    "right": ("right_fisheye_image", "right_depth"),
    "back": ("back_fisheye_image", "back_depth"),
}

_FORMATE = {
    image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8: (np.uint8, 1),
    image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U16: (np.uint16, 1),
    image_pb2.Image.PIXEL_FORMAT_DEPTH_U16: (np.uint16, 1),
    image_pb2.Image.PIXEL_FORMAT_RGB_U8: (np.uint8, 3),
    image_pb2.Image.PIXEL_FORMAT_RGBA_U8: (np.uint8, 4),
}


class Image:
    """Ein Kamerabild mit Rohdaten, Array und Intrinsics."""

    def __init__(self, antwort):
        self._antwort = antwort
        aufnahme = antwort.shot.image
        self.source = antwort.source.name
        self.width = aufnahme.cols
        self.height = aufnahme.rows
        self.raw = aufnahme.data
        self.pixel_format = aufnahme.pixel_format
        self.is_jpeg = aufnahme.format == image_pb2.Image.FORMAT_JPEG
        pinhole = antwort.source.pinhole.intrinsics
        self.intrinsics = {
            "focal_length_x": pinhole.focal_length.x,
            "focal_length_y": pinhole.focal_length.y,
            "principal_point_x": pinhole.principal_point.x,
            "principal_point_y": pinhole.principal_point.y,
        }

    @property
    def array(self):
        if self.is_jpeg:
            from PIL import Image as PILImage
            return np.asarray(PILImage.open(io.BytesIO(self.raw)))
        dtype, kanaele = _FORMATE.get(self.pixel_format, (np.uint8, 1))
        daten = np.frombuffer(self.raw, dtype=dtype)
        if kanaele == 1:
            return daten.reshape(self.height, self.width)
        return daten.reshape(self.height, self.width, kanaele)

    def to_png_bytes(self):
        from PIL import Image as PILImage
        feld = self.array
        if feld.dtype == np.uint16:                 # Tiefe für die Anzeige normieren
            gueltig = feld[feld > 0]
            obergrenze = int(gueltig.max()) if gueltig.size else 1
            feld = (feld.astype(np.float32) / max(obergrenze, 1) * 255).astype(np.uint8)
        puffer = io.BytesIO()
        PILImage.fromarray(feld).save(puffer, format="PNG")
        return puffer.getvalue()

    def save(self, pfad):
        ziel = Path(pfad)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(self.to_png_bytes())
        return ziel

    def __repr__(self):
        return f"<Image {self.source} {self.width}x{self.height}>"


def aufloesen(name, vorhandene):
    if name in vorhandene:
        return name
    for kandidat in KURZNAMEN.get(name, ()):
        if kandidat in vorhandene:
            return kandidat
    kurz = sorted({k for k, werte in KURZNAMEN.items()
                   if any(w in vorhandene for w in werte)})
    raise SpotlabError(
        f"Kamera '{name}' gibt es nicht. Verfügbar: {', '.join(kurz) or 'keine'}.")


def cameras(backend):
    vorhandene = set(backend.image_sources())
    return [kurz for kurz, werte in KURZNAMEN.items()
            if any(w in vorhandene for w in werte)]


def camera(backend, recorder, name):
    require(backend, Capability.CAMERAS, "Kamerabilder aufnehmen")
    quelle = aufloesen(name, backend.image_sources())
    antwort = backend.images([quelle])[0]
    bild = Image(antwort)
    if recorder is not None:
        recorder.image(name, bild.to_png_bytes(),
                       {"source": bild.source, "width": bild.width,
                        "height": bild.height, "intrinsics": bild.intrinsics})
    return bild
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_api_perception.py -v`, erwartet 9 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/api/perception.py tests/test_api_perception.py && git commit -m "feat(api): Kamerabilder mit Kurznamen und Intrinsics"
```

---

## Task 12: Spot-Fassade, Abtaster und connect()

**Files:**
- Create: `src/spotlab/api/spot.py`, `src/spotlab/record/sampler.py`, `tests/test_api_spot.py`, `tests/test_sampler.py`
- Modify: `src/spotlab/__init__.py`

**Interfaces:**
- Consumes: alles aus Tasks 6–11
- Produces:
  - `Spot(backend, recorder=None, limits=Limits())` mit `power_on/power_off/is_powered/battery/stand/sit/move/walk/stop/cameras/camera/state/robot/send/close`
  - `StateSampler(backend, recorder, hz=10.0)` mit `.start()`, `.stop()`
  - `spotlab.connect(backend=None, runs_dir=None, script=None, take=False, config_path=None)` — Kontextmanager, liefert `Spot`

- [ ] **Step 1: Test schreiben** — `tests/test_sampler.py`

```python
import threading

from spotlab.backends.dryrun import DryRunBackend
from spotlab.record.run import RunRecorder
from spotlab.record.sampler import StateSampler


def test_abtaster_schreibt_und_stoppt(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.15)
    abtaster.stop()
    rec.finish("ok")

    zeilen = (rec.dir / "zustand.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) >= 2
    assert abtaster._thread is None or not abtaster._thread.is_alive()


def test_abtaster_ueberlebt_fehler_im_backend(tmp_path):
    class Kaputt(DryRunBackend):
        def robot_state(self):
            raise RuntimeError("Verbindung weg")

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(Kaputt(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.1)
    abtaster.stop()          # darf nicht werfen
    rec.finish("ok")
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_sampler.py -v`

- [ ] **Step 3: `record/sampler.py` implementieren**

```python
"""10-Hz-Abtastung des Roboterzustands in einem Hintergrund-Thread.

Läuft unabhängig davon, was das Schülerskript tut — auch ein Skript, das nur
wartet, produziert damit verwertbare Messdaten für die Sim-Kalibrierung.
"""

import threading
import time

from spotlab.api.state import as_sample


class StateSampler:
    def __init__(self, backend, recorder, hz=10.0):
        self._backend = backend
        self._recorder = recorder
        self._periode = 1.0 / float(hz)
        self._stopp = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._schleife, name="spotlab-sampler",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout=2.0):
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            try:
                self._recorder.sample(as_sample(self._backend.robot_state()))
            except Exception as fehler:      # Abtastung darf den Lauf nie kippen
                self._stopp.wait(self._periode)
                _ = fehler
                continue
            rest = self._periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
```

- [ ] **Step 4: Test für die Fassade** — `tests/test_api_spot.py`

```python
import pytest

from spotlab.api.spot import Spot
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits
from spotlab.errors import NotPowered


def _spot(**kw):
    return Spot(DryRunBackend(), recorder=None, limits=Limits(), **kw)


def test_verben_sind_verkettbar():
    spot = _spot()
    spot.power_on()
    spot.stand(schlaf=lambda _: None)
    spot.stop()
    assert spot.is_powered is True


def test_stand_ohne_strom_sagt_was_zu_tun_ist():
    spot = _spot()
    with pytest.raises(NotPowered) as info:
        spot.stand(schlaf=lambda _: None)
    assert "power_on" in str(info.value)


def test_battery_kommt_aus_dem_zustand():
    assert _spot().battery == 87.0


def test_state_liefert_datenklasse():
    zustand = _spot().state
    assert zustand.battery == 87.0
    assert len(zustand.joints) == 12


def test_send_reicht_rohes_protobuf_durch():
    from bosdyn.client.robot_command import RobotCommandBuilder
    spot = _spot()
    spot.power_on()
    spot.send(RobotCommandBuilder.synchro_stand_command())
    assert len(spot.backend.gesendet) == 1


def test_close_schaltet_ab():
    spot = _spot()
    spot.power_on()
    spot.close()
    assert spot.is_powered is False
```

- [ ] **Step 5: `api/spot.py` implementieren**

```python
"""Die Fassade, die ein Schüler sieht.

Die Abkürzung ist keine Mauer: `spot.robot` und `spot.send()` führen jederzeit
zum vollen SDK — ohne Lease, Not-Aus und Aufzeichnung aufzugeben.
"""

from spotlab.api import motion, perception, posture
from spotlab.api.state import from_proto
from spotlab.config import Limits


class Spot:
    def __init__(self, backend, recorder=None, limits=None, robot=None):
        self.backend = backend
        self.recorder = recorder
        self.limits = limits or Limits()
        self._robot = robot

    # ------------------------------------------------------------ Leistung

    def power_on(self):
        self.backend.power_on()
        if self.recorder is not None:
            self.recorder.event("power_on")

    def power_off(self, safe=True):
        self.backend.power_off(safe=safe)
        if self.recorder is not None:
            self.recorder.event("power_off", safe=safe)

    @property
    def is_powered(self):
        return self.backend.is_powered

    @property
    def battery(self):
        return self.state.battery

    # ------------------------------------------------------------ Haltung

    def stand(self, height=0.0, timeout=10.0, schlaf=None):
        posture.stand(self.backend, self.recorder, height=height, timeout=timeout,
                      **({"schlaf": schlaf} if schlaf else {}))

    def sit(self, timeout=10.0, schlaf=None):
        posture.sit(self.backend, self.recorder, timeout=timeout,
                    **({"schlaf": schlaf} if schlaf else {}))

    # ------------------------------------------------------------ Bewegung

    def move(self, forward=0.0, left=0.0, turn=0.0, timeout=30.0):
        motion.move(self.backend, self.recorder, self.limits,
                    forward=forward, left=left, turn=turn, timeout=timeout)

    def walk(self, vx=0.0, vy=0.0, wz=0.0, duration=1.0):
        motion.walk(self.backend, self.recorder, self.limits,
                    vx=vx, vy=vy, wz=wz, duration=duration)

    def stop(self):
        motion.stop(self.backend, self.recorder)

    # ------------------------------------------------------------ Wahrnehmung

    def cameras(self):
        return perception.cameras(self.backend)

    def camera(self, name):
        return perception.camera(self.backend, self.recorder, name)

    @property
    def state(self):
        return from_proto(self.backend.robot_state())

    # ------------------------------------------------------------ Rohzugang

    @property
    def robot(self):
        """Das rohe bosdyn-Robot-Objekt (None im Trockenlauf)."""
        return self._robot

    def send(self, command, end_time_secs=None):
        if self.recorder is not None:
            self.recorder.event("kommando", name="send", roh=True)
        return self.backend.send_command(command, end_time_secs=end_time_secs)

    def close(self):
        self.backend.close()
```

- [ ] **Step 6: `__init__.py` um `connect()` erweitern**

```python
"""spotlab — den Spot programmieren, ohne vorher SDK-Betriebsmechanik zu lernen."""

import contextlib
import sys
from pathlib import Path

__version__ = "0.1.0"


@contextlib.contextmanager
def connect(backend=None, runs_dir=None, script=None, take=False, config_path=None,
            nickname=None):
    """Verbindet, zeichnet auf und baut am Ende garantiert sauber ab.

    Die Motoren gehen dabei NICHT an — `spot.power_on()` ist eine eigene Zeile,
    die jemand geschrieben haben muss.
    """
    from spotlab.api.spot import Spot
    from spotlab.config import Limits, load_config
    from spotlab.errors import ConfigMissing, LeaseLost, SpotlabError
    from spotlab.record.run import RunRecorder
    from spotlab.record.sampler import StateSampler

    try:
        cfg = load_config(config_path) if config_path else load_config()
    except ConfigMissing:
        cfg = None

    art = backend or (cfg.default_backend if cfg else "dryrun")
    grenzen = cfg.limits if cfg else Limits()
    spitzname = nickname or (cfg.nickname if cfg else "")

    skript = Path(script) if script else _skript_pfad()
    ziel = Path(runs_dir) if runs_dir else _runs_verzeichnis(skript)
    recorder = RunRecorder(ziel, skript, backend=art, nickname=spitzname)

    if art == "dryrun":
        from spotlab.backends.dryrun import DryRunBackend
        roher_roboter, unten = None, DryRunBackend(recorder)
        recorder.event("verbunden", backend="dryrun")
    else:
        from spotlab.backends.real import RealSpot
        if cfg is None:
            recorder.finish("fehler", "Keine Konfiguration")
            raise ConfigMissing("Keine Konfiguration. Einrichten mit `spotlab login`.")
        unten = RealSpot.connect(cfg, recorder=recorder, take=take)
        roher_roboter = unten.robot

    spot = Spot(unten, recorder=recorder, limits=grenzen, robot=roher_roboter)
    abtaster = StateSampler(unten, recorder)
    abtaster.start()

    ergebnis, fehlertext = "ok", None
    try:
        yield spot
    except KeyboardInterrupt:
        ergebnis, fehlertext = "abgebrochen", "Vom Benutzer abgebrochen (Ctrl-C)"
        raise
    except LeaseLost as fehler:
        ergebnis, fehlertext = "lease_verloren", str(fehler)
        raise
    except SpotlabError as fehler:
        ergebnis, fehlertext = "fehler", str(fehler)
        raise
    except BaseException as fehler:
        ergebnis, fehlertext = "fehler", f"{type(fehler).__name__}: {fehler}"
        raise
    finally:
        abtaster.stop()
        try:
            spot.close()
        finally:
            recorder.finish(ergebnis, fehlertext)


def _skript_pfad():
    haupt = sys.argv[0] if sys.argv else ""
    pfad = Path(haupt).resolve() if haupt else None
    return pfad if pfad and pfad.suffix == ".py" and pfad.exists() else None


def _runs_verzeichnis(skript):
    wurzel = skript.parent if skript else Path.cwd()
    return wurzel / "runs"
```

- [ ] **Step 7: Tests laufen lassen** — `pytest tests/test_api_spot.py tests/test_sampler.py -v`, erwartet 8 PASS

- [ ] **Step 8: Commit**

```bash
git add src/spotlab tests && git commit -m "feat(api): Spot-Fassade, Zustandsabtaster und connect()"
```

---

*Fortsetzung: `2026-08-06-spotlab-fundament-teil3.md` (Tasks 13–21: echtes Backend, Werkstatt, CLI, Doku).*
