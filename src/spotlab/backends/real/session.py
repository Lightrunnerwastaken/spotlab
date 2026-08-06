"""Die Sitzung am echten Spot: Aufbau, Betrieb, garantierter Abbau.

Der Abbau ist die einzige nicht verhandelbare Invariante: er läuft immer, auch
bei Ausnahme, Ctrl-C oder Lease-Verlust. Ein hart getöteter Prozess dagegen
lässt die Keepalives sterben — dann geht der Roboter von selbst in den sicheren
Zustand, und genau das ist der Not-Aus, den man nicht kaputtprogrammieren kann.
"""

from bosdyn.client import create_standard_sdk
from bosdyn.client.estop import EstopClient
from bosdyn.client.image import ImageClient, build_image_request
from bosdyn.client.lease import LeaseClient
from bosdyn.client.robot_command import RobotCommandBuilder, RobotCommandClient
from bosdyn.client.robot_state import RobotStateClient

from spotlab.backends.base import Capability, SafetyStatus
from spotlab.backends.real.estop import EstopGuard
from spotlab.backends.real.feedback import to_feedback
from spotlab.backends.real.lease import LeaseGuard, holder_of
from spotlab.config import load_password
from spotlab.errors import NotPowered, TimeSyncFailed, translate

AUFBAU_SCHRITTE = ("auth", "time_sync", "estop", "lease", "aufzeichnung")
ABBAU_SCHRITTE = (
    "bewegung_stoppen",
    "sicher_ausschalten",
    "lease_zurückgeben",
    "estop_abmelden",
    "verbindung_schliessen",
)

SDK_NAME = "spotlab"


def _standard_robot(cfg):
    sdk = create_standard_sdk(SDK_NAME)
    return sdk.create_robot(cfg.ip)


class RealSpot:
    """Backend für den echten Roboter."""

    def __init__(
        self,
        robot,
        command_client,
        state_client,
        image_client,
        lease_guard,
        estop_guard,
        recorder=None,
    ):
        self._robot = robot
        self._commands = command_client
        self._state = state_client
        self._images = image_client
        self._lease = lease_guard
        self._estop = estop_guard
        self._recorder = recorder
        self._geschlossen = False
        self._quellen = None

    # ------------------------------------------------------------- Aufbau

    @classmethod
    def connect(
        cls, cfg, recorder=None, take=False, robot_bauen=None, estop_bauen=None,
        passwort_lesen=None,
    ):
        robot_bauen = robot_bauen or _standard_robot
        passwort_lesen = passwort_lesen or load_password
        robot = robot_bauen(cfg)

        try:
            robot.authenticate(cfg.username, passwort_lesen(cfg.username))
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

        estop_client = robot.ensure_client(EstopClient.default_service_name)
        wache = (estop_bauen or EstopGuard)(estop_client)
        wache.start()

        lease_client = robot.ensure_client(LeaseClient.default_service_name)
        lease = LeaseGuard(lease_client, take=take)
        lease.start()
        if take and lease.previous_holder and recorder is not None:
            recorder.event("lease_übernommen", von=lease.previous_holder)

        backend = cls(
            robot=robot,
            command_client=robot.ensure_client(RobotCommandClient.default_service_name),
            state_client=robot.ensure_client(RobotStateClient.default_service_name),
            image_client=robot.ensure_client(ImageClient.default_service_name),
            lease_guard=lease,
            estop_guard=wache,
            recorder=recorder,
        )

        if recorder is not None:
            kennung = robot.get_id()
            recorder.set_robot_info(
                roboter_seriennummer=getattr(kennung, "serial_number", None),
                roboter_nickname=getattr(kennung, "nickname", None),
                roboter_software=getattr(
                    getattr(kennung, "software_release", None), "version", None
                ),
                uebernommen=bool(take),
            )
            recorder.event("verbunden", backend="real", ip=cfg.ip)
        return backend

    # ------------------------------------------------------------- Protokoll

    def capabilities(self):
        return (
            Capability.LOCOMOTION
            | Capability.POSTURE
            | Capability.POWER
            | Capability.DEPTH_CAMERAS
            | Capability.GRAY_CAMERAS
            | Capability.LEASE
            | Capability.ESTOP
        )

    def send_command(self, command, end_time_secs=None):
        self._lease.raise_if_lost()
        if not self.is_powered:
            raise NotPowered("Die Motoren sind aus — rufe zuerst `spot.power_on()` auf.")
        try:
            return self._commands.robot_command(command, end_time_secs=end_time_secs)
        except Exception as fehler:
            uebersetzt = translate(fehler)
            if uebersetzt is not None:
                raise uebersetzt from fehler
            raise

    def command_feedback(self, command_id):
        return to_feedback(self._commands.robot_command_feedback(command_id))

    def robot_state(self):
        return self._state.get_robot_state()

    def frame_tree_snapshot(self):
        return self._robot.get_frame_tree_snapshot()

    def image_sources(self):
        if self._quellen is None:
            self._quellen = [q.name for q in self._images.list_image_sources()]
        return list(self._quellen)

    def images(self, sources):
        return self._images.get_image([build_image_request(name) for name in sources])

    def power_on(self):
        self._lease.raise_if_lost()
        try:
            self._robot.power_on(timeout_sec=20)
        except Exception as fehler:
            uebersetzt = translate(fehler)
            if uebersetzt is not None:
                raise uebersetzt from fehler
            raise

    def power_off(self, safe=True):
        self._robot.power_off(cut_immediately=not safe, timeout_sec=20)

    @property
    def is_powered(self):
        return bool(self._robot.is_powered_on())

    def safety_status(self):
        halter = None
        stufe = None
        try:
            halter = holder_of(self._robot.ensure_client(LeaseClient.default_service_name))
        except Exception:
            pass
        try:
            stufe = self._estop.level()
        except Exception:
            pass
        return SafetyStatus(lease_holder=halter, estop_level=stufe)

    @property
    def robot(self):
        return self._robot

    # ------------------------------------------------------------- Abbau

    def close(self):
        """Geordnetes Ende. Jeder Schritt ist gekapselt — der Abbau läuft immer durch."""
        if self._geschlossen:
            return
        self._geschlossen = True
        self._versuche(
            lambda: self._commands.robot_command(RobotCommandBuilder.stop_command())
        )
        self._versuche(lambda: self._robot.power_off(cut_immediately=False, timeout_sec=20))
        self._versuche(self._lease.stop)
        self._versuche(self._estop.stop)

    @staticmethod
    def _versuche(schritt):
        try:
            schritt()
        except Exception:
            pass
