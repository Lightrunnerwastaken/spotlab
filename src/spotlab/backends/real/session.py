"""Die Sitzung am echten Spot: Aufbau, Betrieb, garantierter Abbau.

Der Abbau ist die einzige nicht verhandelbare Invariante: er läuft immer, auch
bei Ausnahme, Ctrl-C oder Lease-Verlust. Ein hart getöteter Prozess dagegen
lässt die Keepalives sterben — dann geht der Roboter von selbst in den sicheren
Zustand, und genau das ist der Not-Aus, den man nicht kaputtprogrammieren kann.
"""

import time

from bosdyn.client.estop import EstopClient
from bosdyn.client.image import ImageClient, build_image_request
from bosdyn.client.lease import LeaseClient
from bosdyn.client.robot_command import RobotCommandBuilder, RobotCommandClient
from bosdyn.client.robot_state import RobotStateClient

from spotlab import protokoll
from spotlab.backends import mobility
from spotlab.backends.base import Capability, SafetyStatus
from spotlab.backends.real.estop import EstopGuard
from spotlab.backends.real.feedback import to_feedback
from spotlab.backends.real.lease import LeaseGuard, holder_of
from spotlab.backends.real.verbindung import verbinde
from spotlab.errors import NotPowered, translate

AUFBAU_SCHRITTE = ("auth", "time_sync", "estop", "lease", "aufzeichnung")
ABBAU_SCHRITTE = (
    "bewegung_stoppen",
    "sicher_ausschalten",
    "lease_zurückgeben",
    "estop_abmelden",
    "verbindung_schliessen",
)

def _rollback(lease, wache):
    """Aufbau rückgängig machen, in umgekehrter Reihenfolge.

    Jeder Schritt einzeln gekapselt und stumm: hier läuft bereits ein Fehler
    nach oben, und der ist die Nachricht, die der Schüler braucht. Ein
    Folgefehler beim Aufräumen dürfte ihn nicht überschreiben — er verdeckte
    die eigentliche Ursache.
    """
    for schritt in (lease, wache):
        if schritt is None:
            continue
        try:
            schritt.stop()
        except BaseException:
            pass


# Zeitgrenze eines Bildabrufs: ein abgerissenes WLAN darf keinen Thread ewig halten.
BILD_FRIST_S = 3.0


class RealSpot:
    """Backend für den echten Roboter."""

    # Erlaubnis für `workshop/blick.py`: hier kommt der Blick beim Fahren aus den
    # Frontkameras. Eine ERLAUBNIS, keine Sperrliste — ein Sim, der Kameras
    # vortäuscht und die Ansicht selbst rendert, bekommt sonst zwei Schreiber
    # auf `ansicht.jpg`.
    blick_aus_kameras = True

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
        self._farbe_moeglich = None     # None: noch nicht gefragt
        # Lesedienste, erst bei Bedarf angelegt (siehe Abschnitt Wahrnehmung).
        self._welt = None
        self._gitter = None

    # ------------------------------------------------------------- Aufbau

    @classmethod
    def connect(
        cls, cfg, recorder=None, take=False, robot_bauen=None, estop_bauen=None,
        passwort_lesen=None,
    ):
        robot = verbinde(cfg, robot_bauen=robot_bauen, passwort_lesen=passwort_lesen)

        estop_client = robot.ensure_client(EstopClient.default_service_name)
        wache = (estop_bauen or EstopGuard)(estop_client)
        wache.start()

        # Ab hier ist ein Not-Aus-Endpunkt registriert und ein Keepalive-Thread
        # unterwegs. Scheitert irgendein weiterer Schritt, MUSS beides wieder
        # weg — sonst hält ein Prozess ohne Sitzung den Not-Aus des Roboters,
        # und der nächste Schüler findet einen scheinbar defekten Spot.
        # `BaseException`, nicht `Exception`: Strg-C ist der häufigste Abbruch
        # überhaupt und wäre sonst genau der Fall, der etwas zurücklässt.
        lease = None
        try:
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
        except BaseException:
            _rollback(lease, wache)
            raise

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
            | Capability.STAIRS
            | Capability.GRAPH_NAV
            | Capability.WORLD_OBJECTS
            | Capability.LOCAL_GRID
        )

    # ----------------------------------------------------------- Wahrnehmung
    #
    # Beide Clients werden bei Bedarf angelegt statt im Konstruktor: sie sind
    # reine Lesedienste, und eine Sitzung, die sie nie benutzt, soll auch keine
    # Verbindung dafür aufbauen.

    def _welt_client(self):
        from bosdyn.client.world_object import WorldObjectClient

        if self._welt is None:
            self._welt = self._robot.ensure_client(WorldObjectClient.default_service_name)
        return self._welt

    def _gitter_client(self):
        from bosdyn.client.local_grid import LocalGridClient

        if self._gitter is None:
            self._gitter = self._robot.ensure_client(LocalGridClient.default_service_name)
        return self._gitter

    def world_objects(self, kinds=None):
        """Kein Lease, kein Kommando — `WorldObjectClient` liest nur."""
        from spotlab.backends.real import wahrnehmung

        # Wanduhr, keine Roboterzeit: `t_robot` wird nicht umgerechnet (CLAUDE.md),
        # und dieses Feld liegt in derselben Zeitbasis wie `t` in zustand.jsonl.
        return wahrnehmung.objekte_holen(self._welt_client(), time.time(), kinds=kinds)

    def stairs(self):
        """Erkannte Treppen der Firmware -- derselbe Lesedienst wie `world_objects`."""
        return self.world_objects(kinds=["staircase"])

    def local_grid(self):
        """Kein Lease, kein Kommando — `LocalGridClient` liest nur."""
        from spotlab.backends.real import wahrnehmung

        return wahrnehmung.gitter_holen(self._gitter_client())

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

    def mobility_params(self, limits):
        return mobility.mit_grenze(limits)

    def image_sources(self):
        if self._quellen is None:
            self._quellen = [q.name for q in self._images.list_image_sources()]
        return list(self._quellen)

    def images(self, sources, farbe=False, guete=None):
        """Bilder der Quellen. `farbe`: RGB erbitten, wo die Kamera es kann.

        Neuere Spots haben farbige Frontkameras (das Tablet zeigt sie so), ältere
        nur Graustufen. Erbeten wird RGB mit Graustufen als Rückfall; ein Roboter,
        dessen Software den Rückfall nicht kennt, weist RGB ab — dann wird ohne
        Farbe erneut gefragt und das Ergebnis gemerkt, damit die Frage nicht bei
        jedem Bild zweimal über das WLAN geht.
        """
        from bosdyn.api import image_pb2
        from bosdyn.client.image import UnsupportedPixelFormatRequestedError

        guete = 75 if guete is None else guete
        if farbe and self._farbe_moeglich is not False:
            anfragen = [
                build_image_request(
                    name, quality_percent=guete,
                    pixel_format=image_pb2.Image.PIXEL_FORMAT_RGB_U8,
                    fallback_formats=[image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8])
                for name in sources]
            try:
                antworten = self._images.get_image(anfragen, timeout=BILD_FRIST_S)
            except UnsupportedPixelFormatRequestedError:
                self._farbe_moeglich = False
            else:
                self._farbe_moeglich = True
                return antworten
        return self._images.get_image(
            [build_image_request(name, quality_percent=guete) for name in sources],
            timeout=BILD_FRIST_S)

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

    # ------------------------------------------------------------- GraphNav

    def upload_map(self, kartenordner):
        from spotlab.backends.real import graphnav

        self._lease.raise_if_lost()
        return graphnav.upload_map(self._robot, kartenordner)

    def localize(self):
        from spotlab.backends.real import graphnav

        self._lease.raise_if_lost()
        return graphnav.localize(self._robot)

    def map_pose(self):
        from spotlab.backends.real import graphnav

        return graphnav.localization_pose(self._robot)

    def localization(self):
        from spotlab.backends.real import graphnav

        return graphnav.localization(self._robot)

    def travel_params(self, limits):
        from spotlab.backends.real import graphnav

        return graphnav.travel_params(limits)

    def navigate_step(self, waypoint_id, dauer_s, params, command_id=None):
        from spotlab.backends.real import graphnav

        self._lease.raise_if_lost()
        return graphnav.navigate_step(
            self._robot, waypoint_id, dauer_s, params, command_id=command_id
        )

    def navigation_status(self, command_id):
        from spotlab.backends.real import graphnav

        return graphnav.navigation_status(self._robot, command_id)

    # ------------------------------------------------------------- Abbau

    def close(self):
        """Geordnetes Ende. Jeder Schritt ist gekapselt — der Abbau läuft immer durch.

        „Immer" schliesst Strg-C ein. `_versuche` fing früher nur `Exception`;
        ein KeyboardInterrupt im ersten Schritt sprang damit aus `close()`
        heraus, und power_off, Lease-Rückgabe und E-Stop-Abmeldung liefen nie.
        Der Prozess starb, die Keepalives starben, der Roboter schnitt die
        Motorleistung ab — und ein STEHENDER Spot fällt dabei um, statt sich
        hinzusetzen. Genau den Fall soll der geordnete Abbau verhindern.

        Ein Abbruch wird deshalb gemerkt und erst NACH allen Schritten weiter
        nach oben gereicht. Ihn zu verschlucken wäre schlimmer als das Problem:
        der Lauf würde als „ok" verbucht, obwohl ihn jemand abgebrochen hat.
        """
        if self._geschlossen:
            return
        self._geschlossen = True
        abbruch = None
        for schritt in (
            lambda: self._commands.robot_command(RobotCommandBuilder.stop_command()),
            lambda: self._robot.power_off(cut_immediately=False, timeout_sec=20),
            self._lease.stop,
            self._estop.stop,
        ):
            abbruch = self._versuche(schritt) or abbruch
        if abbruch is not None:
            raise abbruch

    @staticmethod
    def _versuche(schritt):
        """Einen Abbauschritt ausführen. Gibt einen Abbruch zurück, statt ihn zu werfen.

        Gewöhnliche Fehler bleiben stumm (bestehende Zusicherung: ein
        fehlgeschlagener Schritt darf die folgenden nicht verhindern).
        KeyboardInterrupt und SystemExit sind kein Fehler, sondern
        Ablaufsteuerung — sie werden zurückgegeben und ganz am Ende geworfen.
        """
        try:
            schritt()
        except Exception as fehler:
            # Stumm bleibt der ABLAUF, nicht die Aufzeichnung: ein
            # fehlgeschlagener Abbauschritt war bisher nirgends nachlesbar, und
            # nach einem Vorfall liess sich nicht sagen, warum der Spot sich
            # nicht hingesetzt hat.
            protokoll.notiere(f"Abbauschritt gescheitert: {schritt!r}", fehler)
        except BaseException as abbruch:
            return abbruch
        return None
