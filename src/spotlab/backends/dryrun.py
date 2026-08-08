"""Trockenlauf: baut und prüft echte Protobufs, bewegt nichts.

Doppelrolle — Standard-Testdouble der Testsuite UND ausgeliefertes Feature:
`spotlab run --dryrun` lässt einen Schüler zu Hause ohne Roboter und ohne Netz
prüfen, ob sein Skript überhaupt durchläuft.
"""

import itertools
import time

from bosdyn.api import geometry_pb2, robot_command_pb2, robot_state_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, VISION_FRAME_NAME
from google.protobuf import wrappers_pb2

from spotlab.backends.base import Capability, Feedback, SafetyStatus
from spotlab.errors import NotPowered, UnsupportedCapability

STANDHOEHE = 0.42       # m, plausible Standhöhe des echten Spot
REIBWERT = 0.6          # erfunden, aber plausibel — lauf.json sagt `backend: dryrun`

GELENKE = [
    "fl.hx", "fl.hy", "fl.kn",
    "fr.hx", "fr.hy", "fr.kn",
    "hl.hx", "hl.hy", "hl.kn",
    "hr.hx", "hr.hy", "hr.kn",
]


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
                f"{type(command).__name__}"
            )
        return command

    # ------------------------------------------------------------- Zustand

    def robot_state(self):
        """Plausible Werte auch für die Kalibrierfelder.

        Ohne sie liesse sich die Kette Messfahrt → Fensterauswertung → Vergleich
        nicht ohne Roboter üben, und die erste echte Messfahrt wäre zugleich der
        erste Test. Am Spot-Termin ist dafür keine Zeit. Die Zahlen sind erfunden,
        und die Aufzeichnung sagt das: `backend: "dryrun"` steht in lauf.json.
        """
        zustand = robot_state_pb2.RobotState()
        akku = zustand.battery_states.add()
        akku.charge_percentage.CopyFrom(wrappers_pb2.DoubleValue(value=87.0))
        akku.voltage.CopyFrom(wrappers_pb2.DoubleValue(value=56.2))
        akku.current.CopyFrom(wrappers_pb2.DoubleValue(value=-12.4))
        akku.temperatures.extend([31.0, 32.5])

        zustand.power_state.motor_power_state = (
            robot_state_pb2.PowerState.STATE_ON
            if self._powered
            else robot_state_pb2.PowerState.STATE_OFF
        )
        zustand.behavior_state.state = (
            robot_state_pb2.BehaviorState.STATE_STANDING
            if self._powered
            else robot_state_pb2.BehaviorState.STATE_NOT_READY
        )

        zustand.kinematic_state.acquisition_timestamp.FromNanoseconds(int(time.time() * 1e9))

        for name in GELENKE:
            gelenk = zustand.kinematic_state.joint_states.add()
            gelenk.name = name
            gelenk.position.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.velocity.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.acceleration.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.load.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            motor = zustand.system_state.motor_temperatures.add()
            motor.name = name
            motor.temperature = 40.0

        for _ in range(4):
            fuss = zustand.foot_state.add()
            fuss.contact = robot_state_pb2.FootState.CONTACT_MADE
            fuss.foot_position_rt_body.z = -STANDHOEHE
            fuss.terrain.ground_mu_est = REIBWERT
            fuss.terrain.ground_contact_normal_rt_frame.z = 1.0

        zustand.kinematic_state.transforms_snapshot.CopyFrom(self.frame_tree_snapshot())
        return zustand

    def frame_tree_snapshot(self):
        schnappschuss = geometry_pb2.FrameTreeSnapshot()
        schnappschuss.child_to_parent_edge_map[VISION_FRAME_NAME].CopyFrom(
            geometry_pb2.FrameTreeSnapshot.ParentEdge()
        )
        schnappschuss.child_to_parent_edge_map[ODOM_FRAME_NAME].CopyFrom(
            _identitaets_kante(VISION_FRAME_NAME)
        )
        koerper = _identitaets_kante(ODOM_FRAME_NAME)
        koerper.parent_tform_child.position.z = STANDHOEHE
        schnappschuss.child_to_parent_edge_map[BODY_FRAME_NAME].CopyFrom(koerper)
        return schnappschuss

    # ------------------------------------------------------------- Rest

    def image_sources(self):
        return []

    def images(self, sources):
        raise UnsupportedCapability(
            "Der Trockenlauf hat keine Kameras. Für Bilder brauchst du den echten Spot."
        )

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
