"""Ein Backend, das sich nach gemessenen Daten bewegt.

Die Naht ist dieselbe wie bei `DryRunBackend` und `RealSpot`: echte
`RobotCommand`-Protobufs herein, echte `RobotState`-Protobufs heraus. Alles
darüber — Aufzeichnung, Messfenster, Auswertung, GUI, Live-Ansicht — merkt
keinen Unterschied und ist unverändert getestet.

Der Unterschied zu `DryRunBackend`: dort steht der Zustand still. Hier bewegt
er sich, und zwar so, wie der echte Spot am 12.08.2026 gemessen wurde.

WAS DAS IST
    Eine Interpolation zwischen gemessenen Gangarten. Bei 0.36 m/s bewegen
    sich die Gelenke so, wie sie sich am echten Roboter bei 0.36 m/s bewegt
    haben.

WAS DAS NICHT IST
    Physik. Es gibt keine Massen, keine Kontaktkräfte, keinen Regler. Der
    Roboter kann hier nicht umfallen, nicht rutschen und nicht an einer Kante
    hängenbleiben. Ein Skript, das hier durchläuft, ist NICHT erprobt — es ist
    gegen eine Interpolation gelaufen.

    Deshalb steht `backend: "sim"` in `lauf.json`, deshalb sagt
    `hinweis_zur_gueltigkeit()` es im Klartext, und deshalb hat dieses Backend
    weder Kameras noch GraphNav: für beides gibt es keine Messung, und ein
    erfundenes Bild wäre schlimmer als gar keins.
"""

import itertools
import math
import time

from bosdyn.api import robot_command_pb2, robot_state_pb2
from bosdyn.client.frame_helpers import ODOM_FRAME_NAME
from google.protobuf import wrappers_pb2

from spotlab.backends import mobility
from spotlab.backends.base import (
    Capability,
    Feedback,
    ObstacleGrid,
    SafetyStatus,
    Tag,
    richtung,
)
from spotlab.errors import CommandRejected, NotPowered, UnsupportedCapability

# Wie lange ein Fahrkommando gilt, wenn keine Endzeit mitkommt. Der echte Spot
# hält ohne Nachschub an; das muss hier genauso sein, sonst liefe ein Skript im
# Sim ewig weiter, das am Roboter nach einer Sekunde stehenbliebe.
NACHLAUF_S = 1.0

# Wann ein Ziel als erreicht gilt. Grosszügiger als die Rechengenauigkeit, weil
# sonst um den Zielpunkt herum gependelt würde: der Schritt je Takt ist bei
# 0.2 m/s und 20 ms rund 4 mm.
ZIEL_TOLERANZ_M = 0.02
ZIEL_TOLERANZ_RAD = 0.03

HINWEIS = (
    "Dieser Lauf ist NICHT am Roboter erprobt. Das Sim-Backend interpoliert "
    "gemessene Gangarten — es kennt keine Physik: nichts kann umfallen, "
    "rutschen oder hängenbleiben."
)


class SimBackend:
    """Bewegt sich nach der Gangkennlinie. Kein Roboter, keine Physik."""

    def __init__(self, recorder=None, jetzt=time.time, modell=None,
                 raum=None, start=None):
        from spotlab.kalibrierung.modell import lade_modell

        # Stufe 10: ein Zimmer um den Sim herum. OHNE Raum verhaelt sich alles
        # exakt wie vorher -- daran haengt jeder bestehende Lauf und jeder
        # bestehende Test.
        self._raum = raum
        self._angestossen = False      # Flanke, damit das Protokoll lesbar bleibt

        self._recorder = recorder
        self._jetzt = jetzt
        self._modell = modell or lade_modell()
        self._powered = False
        self._zaehler = itertools.count(1)
        self._offen = {}
        self.gesendet = []

        self._t = jetzt()
        if start is not None:
            # Raum- und odom-Koordinaten fallen damit zusammen; die Ansicht muss
            # nichts umrechnen.
            self._pose = (float(start[0]), float(start[1]), math.radians(start[2]))
        else:
            self._pose = (0.0, 0.0, 0.0)
        self._phase = 0.0
        self._soll = (0.0, 0.0, 0.0)
        self._gueltig_bis = 0.0
        self._sitzt = False
        self._ziel = None
        self._hoehe = self._modell.hoehe_m
        # Getrennt gezaehlt: Takte sind Zeitschritte, Ziele sind Kommandos.
        self._takte_bewegt = 0
        self._ausserhalb_takte = 0
        self._ziele = 0

    # ------------------------------------------------------------- Auskunft

    def capabilities(self):
        # Keine Kameras, kein GraphNav: dafür gibt es keine Messung. Ein
        # erfundenes Bild wäre schlimmer als gar keins, und `require()` sagt
        # dem Schüler dann ehrlich, was fehlt.
        koennen = Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
        if self._raum is not None:
            # Mit Raum ist die Wahrnehmung keine Erfindung mehr, sondern
            # Geometrie: sie folgt aus dem, was in der Raumdatei steht.
            koennen |= Capability.WORLD_OBJECTS | Capability.LOCAL_GRID
        return koennen

    def world_objects(self, kinds=None):
        """Ohne Raum leer — und das ist die Wahrheit, nicht ein Fehler.

        Die Gangart-Interpolation weiss nichts über die Umgebung. Zwei erfundene
        Tags sähen aus wie eine Messung und liefen in jede Auswertung.

        MIT Raum ist es keine Erfindung, sondern Geometrie. Die Übersetzung in
        `Tag` passiert HIER und nicht in `welt/`, weil `richtung()` in
        `backends/base.py` wohnt und `welt/` nichts aus `backends/` importiert.
        """
        if self._raum is None:
            return []
        if kinds is not None and "apriltag" not in kinds:
            return []
        from spotlab.welt.wahrnehmung import sichtbare_tags

        self._fortschreiben()
        gefunden = []
        for tag, dx, dy in sichtbare_tags(self._raum, self._pose):
            peilung, distanz = richtung(dx, dy)
            gefunden.append(Tag(
                name=f"world_obj_apriltag_{tag.id:03d}", kind="apriltag",
                bearing=peilung, distance=distanz, world_xy=(tag.x, tag.y),
                time=self._jetzt(), id=tag.id, filtered=False,
            ))
        return gefunden

    def local_grid(self):
        if self._raum is None:
            raise UnsupportedCapability(
                "Die Simulation führt ohne Übungsraum kein Hindernisgitter. "
                "Wähle einen Raum in der Ansicht 'Übungsraum' oder gib ihn an: "
                "spotlab.connect(backend='sim', raum='moebliert')."
            )
        import numpy as np

        from spotlab.welt.wahrnehmung import GITTER_ZELLE_M, abstandsgitter

        self._fortschreiben()
        werte, bekannt, ursprung = abstandsgitter(self._raum, self._pose)
        return ObstacleGrid(
            cells=np.asarray(werte), cell_size=GITTER_ZELLE_M,
            origin=ursprung, time=self._jetzt(), known=np.asarray(bekannt),
        )

    def _bewege_gegen_welt(self, von, nach):
        """Ohne Raum unveraendert. Mit Raum: an Waenden bleibt Spot stehen.

        Kein Fehler, kein Abbruch -- der echte Spot wirft auch keine Ausnahme,
        wenn er vor einem Hindernis stehenbleibt. Das Programm laeuft weiter und
        `move()` erreicht sein Ziel eben nicht.

        Gemeldet wird nur die FLANKE. Ein Programm, das zehn Sekunden gegen eine
        Wand drueckt, schriebe sonst hundert gleiche Zeilen ins Protokoll.
        """
        if self._raum is None:
            return nach
        from spotlab.welt.kollision import bewege

        pose, getroffen = bewege(self._raum, von, nach)
        if getroffen is None:
            self._angestossen = False
        elif not self._angestossen:
            self._angestossen = True
            if self._recorder is not None:
                self._recorder.event(
                    "angestossen",
                    x=round(pose[0], 3), y=round(pose[1], 3), hindernis=getroffen,
                )
        return pose

    @staticmethod
    def hinweis_zur_gueltigkeit():
        return HINWEIS

    def mobility_params(self, limits):
        return mobility.mit_grenze(limits)

    def image_sources(self):
        return []

    def images(self, sources):
        raise UnsupportedCapability(
            "Das Sim-Backend hat keine Kameras. Bilder gibt es nur am echten Spot — "
            "erfundene Bilder wären schlimmer als gar keine."
        )

    def safety_status(self):
        return SafetyStatus(lease_holder=None, estop_level=None)

    @property
    def is_powered(self):
        return self._powered

    def power_on(self):
        self._powered = True

    def power_off(self, safe=True):
        self._fortschreiben()
        self._powered = False
        self._soll = (0.0, 0.0, 0.0)
        self._sitzt = True

    def close(self):
        self._powered = False

    @property
    def ausserhalb_der_messung(self):
        """Wie oft nach einer Bewegung gefragt wurde, die nie vermessen wurde."""
        return self._ausserhalb_takte + self._ziele

    def bericht(self):
        """Was dieser Lauf über seine eigene Gültigkeit weiss.

        Gehört beim Abbau in `lauf.json`. Ohne diese Zahlen sieht ein Sim-Lauf
        aus wie jeder andere — und niemand erkennt, dass die Hälfte davon
        ausserhalb der vermessenen Gangarten lag.

        Takte und Zieltrajektorien werden GETRENNT gezählt: das eine sind
        Zeitschritte, das andere Kommandos. Sie in eine Zahl zu addieren gäbe
        ein Verhältnis, das von der Abtastrate abhinge.
        """
        tempo_von, tempo_bis = self._modell.tempo_bereich
        dreh_von, dreh_bis = self._modell.dreh_bereich
        anteil = (
            round(self._ausserhalb_takte / self._takte_bewegt, 3)
            if self._takte_bewegt else None
        )
        return {
            "hinweis": HINWEIS,
            "takte_in_bewegung": self._takte_bewegt,
            "takte_ausserhalb_der_messung": self._ausserhalb_takte,
            "anteil_ausserhalb": anteil,
            # Für eine Zieltrajektorie gibt es GAR KEINE Messung — der echte
            # Spot wählt sein Tempo selbst, und das wurde nie aufgezeichnet.
            "zieltrajektorien": self._ziele,
            "kennlinie": {
                "stuetzstellen_fahrt": len(self._modell.fahren),
                "stuetzstellen_drehung": len(self._modell.drehen),
                "tempo_bereich_m_s": [round(tempo_von, 3), round(tempo_bis, 3)],
                "drehrate_bereich_rad_s": [round(dreh_von, 3), round(dreh_bis, 3)],
                "standhoehe_m": round(self._modell.hoehe_m, 4),
            },
        }

    # ------------------------------------------------------------- Kommandos

    def send_command(self, command, end_time_secs=None):
        if not self._powered:
            raise NotPowered("Die Motoren sind aus — rufe zuerst `spot.power_on()` auf.")
        jetzt = self._jetzt()
        if end_time_secs is not None:
            self._pruefe_endzeit(float(end_time_secs), jetzt)
        kommando = self._als_robot_command(command)
        self.gesendet.append(kommando)
        self._fortschreiben()
        self._uebernehmen(kommando, end_time_secs, jetzt)
        kennung = f"sim-{next(self._zaehler)}"
        # Merken, ob dieses Kommando ein ZIEL hatte: nur dann darf die
        # Rückmeldung erst bei Ankunft „fertig" sagen. Sonst kehrte `move()`
        # zurück, während der Roboter noch unterwegs ist.
        self._offen[kennung] = "ziel" if self._ziel is not None else 0
        return kennung

    @staticmethod
    def _pruefe_endzeit(endzeit, jetzt):
        """Wie `DryRunBackend`, aus demselben Grund: `end_time_secs` ist ein
        ZEITPUNKT. Ein Sim, der eine abgelaufene Endzeit annimmt, liesse den
        Fehler durch, an dem der echte Spot sich nie bewegt hätte."""
        if endzeit <= jetzt:
            raise CommandRejected(
                f"Das Kommando war beim Absenden schon abgelaufen (Endzeit "
                f"{endzeit:.1f}, jetzt {jetzt:.1f}). `end_time_secs` ist ein "
                f"Zeitpunkt in Sekunden seit dem 1.1.1970, keine Dauer."
            )

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

    def _uebernehmen(self, kommando, end_time_secs, jetzt):
        """Aus dem Protobuf lesen, was gefahren werden soll."""
        mobil = kommando.synchronized_command.mobility_command
        art = mobil.WhichOneof("command")
        # Jedes neue Kommando hebt ein laufendes Ziel auf. Sonst arbeitete ein
        # `walk()` nach einem `move()` gegen den Zielregler, und beide schrieben
        # abwechselnd in `_soll`.
        if art != "se2_trajectory_request":
            self._ziel = None
        if art == "se2_velocity_request":
            # `angular` ist bei SE2Velocity ein SKALAR, kein Vektor — anders als
            # bei der Geschwindigkeit im RobotState, wo `angular.z` steht.
            v = mobil.se2_velocity_request.velocity
            self._soll = (v.linear.x, v.linear.y, v.angular)
            self._sitzt = False
            self._gueltig_bis = (
                float(end_time_secs) if end_time_secs is not None else jetzt + NACHLAUF_S
            )
        elif art == "stand_request":
            self._soll = (0.0, 0.0, 0.0)
            self._sitzt = False
            self._hoehe = self._modell.hoehe_m + self._hoehenversatz(mobil)
        elif art == "sit_request":
            self._soll = (0.0, 0.0, 0.0)
            self._sitzt = True
        elif art == "se2_trajectory_request":
            # Eine Zieltrajektorie: der echte Spot wählt sein TEMPO selbst, und
            # welches, wurde nie vermessen — im Beobachter-Modus hat niemand
            # kommandiert. Angefahren wird das Ziel trotzdem, mit einem Tempo
            # aus der Mitte des vermessenen Bereichs. Das ist eine WAHL, keine
            # Messung, und sie wird als ausserhalb der Messung gezählt.
            #
            # Die Alternative wäre gewesen, `move()` im Sim gar nichts tun zu
            # lassen. Ein stilles Nichtstun ist für einen Schüler die
            # schlechteste Antwort: sein Programm läuft durch und er lernt
            # nichts daraus.
            self._ziele += 1
            self._sitzt = False
            self._ziel = self._ziel_aus(mobil.se2_trajectory_request)
            self._soll = (0.0, 0.0, 0.0)
            self._gueltig_bis = (
                float(end_time_secs) if end_time_secs is not None else jetzt + NACHLAUF_S
            )
        else:
            # stop_command und alles andere: anhalten.
            self._soll = (0.0, 0.0, 0.0)
            self._gueltig_bis = jetzt

    def _ziel_aus(self, anfrage):
        """Zielpose (x, y, yaw) im odom-Frame, oder None.

        `synchro_trajectory_command_in_body_frame()` rechnet das Körperziel
        schon in den odom-Frame um — der Rahmenname steht in der Anfrage. Ein
        anderer Rahmen wird NICHT geraten: dann gibt es kein Ziel, und
        `command_feedback` meldet sofort fertig, statt woandershin zu fahren.
        """
        if anfrage.se2_frame_name != ODOM_FRAME_NAME or not anfrage.trajectory.points:
            return None
        pose = anfrage.trajectory.points[-1].pose
        return (pose.position.x, pose.position.y, pose.angle)

    def _zum_ziel(self):
        """Sollgeschwindigkeit im Körperframe, um dem Ziel näherzukommen.

        Verschieben und Drehen laufen GLEICHZEITIG, jedes hört für sich auf,
        wenn seine Toleranz erreicht ist. Ein Nacheinander („erst drehen, dann
        fahren") wäre ein erfundener Regler — der echte Spot läuft auch schräg.
        """
        x, y, yaw = self._pose
        zx, zy, zyaw = self._ziel
        dx, dy = zx - x, zy - y
        abstand = math.hypot(dx, dy)
        dyaw = (zyaw - yaw + math.pi) % (2 * math.pi) - math.pi

        fertig_weg = abstand <= ZIEL_TOLERANZ_M
        fertig_dreh = abs(dyaw) <= ZIEL_TOLERANZ_RAD
        if fertig_weg and fertig_dreh:
            return None

        vx = vy = 0.0
        if not fertig_weg:
            tempo = self._modell.tempo_vorschlag
            # Richtung in den Körperframe drehen: die Geschwindigkeit im
            # Kommando ist körperfest, der Abstand steht in odom.
            richtung = math.atan2(dy, dx) - yaw
            vx, vy = tempo * math.cos(richtung), tempo * math.sin(richtung)
        wz = 0.0
        if not fertig_dreh:
            wz = math.copysign(self._modell.drehrate_vorschlag, dyaw)
        return vx, vy, wz

    @staticmethod
    def _hoehenversatz(mobil):
        """Die Körperhöhe aus `synchro_stand_command(body_height=...)`.

        Sie steht nicht im `stand_request`, sondern in den `params` des
        Mobility-Kommandos — einem `Any`, das erst als `MobilityParams`
        ausgepackt werden muss. Der Weg dorthin ist lang und versionsabhängig;
        scheitert er, gilt die gemessene Standhöhe. Eine falsche Höhe ist ein
        Schönheitsfehler, ein Absturz beim `spot.stand()` eines Schülers nicht.
        """
        try:
            from bosdyn.api.spot import robot_command_pb2 as spot_pb2

            if not mobil.HasField("params"):
                return 0.0
            params = spot_pb2.MobilityParams()
            mobil.params.Unpack(params)
            punkte = params.body_control.base_offset_rt_footprint.points
            return punkte[0].pose.position.z if punkte else 0.0
        except Exception:
            return 0.0

    def command_feedback(self, command_id):
        stand = self._offen.get(command_id, 0)
        if stand == "ziel":
            self._fortschreiben()
            if self._ziel is None:
                return Feedback(done=True, status="angekommen (Sim)")
            return Feedback(done=False, status="unterwegs (Sim)")
        self._offen[command_id] = stand + 1
        if stand == 0:
            return Feedback(done=False, status="unterwegs (Sim)")
        return Feedback(done=True, status="fertig (Sim)")

    # ------------------------------------------------------------- Zustand

    def _fortschreiben(self):
        """Die Welt bis jetzt weiterlaufen lassen."""
        from spotlab.kalibrierung.modell import integriere

        jetzt = self._jetzt()
        dt = jetzt - self._t
        self._t = jetzt
        if dt <= 0:
            return

        abgelaufen = jetzt > self._gueltig_bis
        if abgelaufen:
            # Ein verfallenes Kommando gilt auch für eine Zieltrajektorie: der
            # echte Spot hält an, wenn die Endzeit erreicht ist, ohne das Ziel
            # zu haben. `api/motion.move()` setzt sie genau auf seine Geduld.
            self._ziel = None
        if self._ziel is not None:
            gefunden = self._zum_ziel()
            if gefunden is None:
                self._ziel = None
                self._soll = (0.0, 0.0, 0.0)
            else:
                self._soll = gefunden

        vx, vy, wz = self._soll if not abgelaufen else (0.0, 0.0, 0.0)
        if not self._powered or self._sitzt:
            vx = vy = wz = 0.0
        tempo = math.hypot(vx, vy)
        if tempo > 1e-6 or abs(wz) > 1e-6:
            self._takte_bewegt += 1
            if self._modell.rand(tempo, wz):
                self._ausserhalb_takte += 1
            dauer = self._modell.zyklusdauer(tempo, wz)
            if dauer > 0:
                self._phase = (self._phase + dt / dauer) % 1.0
            neu = integriere(self._pose, vx, vy, wz, dt)
            self._pose = self._bewege_gegen_welt(self._pose, neu)

    def robot_state(self):
        self._fortschreiben()
        vx, vy, wz = (
            self._soll if (self._powered and not self._sitzt
                           and self._jetzt() <= self._gueltig_bis)
            else (0.0, 0.0, 0.0)
        )
        tempo = math.hypot(vx, vy)
        steht_still = tempo <= 1e-6 and abs(wz) <= 1e-6

        zustand = robot_state_pb2.RobotState()
        akku = zustand.battery_states.add()
        akku.charge_percentage.CopyFrom(wrappers_pb2.DoubleValue(value=88.0))
        akku.voltage.CopyFrom(wrappers_pb2.DoubleValue(value=55.9))
        akku.current.CopyFrom(wrappers_pb2.DoubleValue(value=-3.3))
        zustand.power_state.motor_power_state = (
            robot_state_pb2.PowerState.STATE_ON
            if self._powered
            else robot_state_pb2.PowerState.STATE_OFF
        )
        # Der Enum kennt: UNKNOWN, NOT_READY, TRANSITION, STANDING, STEPPING —
        # kein Sitzen. NOT_READY ist die Deutung „kann gerade nicht laufen"; was
        # der echte Spot im Sitzen meldet, ist UNGEPRUEFT (unsere Messfahrten
        # zeigen 1668-mal STANDING und nie etwas anderes). Steht so in
        # docs/ABNAHME.md.
        if self._sitzt:
            zustand.behavior_state.state = robot_state_pb2.BehaviorState.STATE_NOT_READY
        elif steht_still:
            zustand.behavior_state.state = robot_state_pb2.BehaviorState.STATE_STANDING
        else:
            zustand.behavior_state.state = robot_state_pb2.BehaviorState.STATE_STEPPING

        winkel = self._modell.gelenke(tempo, wz, self._phase)
        kontakte = (
            [True] * 4 if steht_still
            else self._modell.fusskontakte(tempo, wz, self._phase)
        )
        for name in self._modell.gelenknamen:
            gelenk = zustand.kinematic_state.joint_states.add()
            gelenk.name = name
            gelenk.position.CopyFrom(wrappers_pb2.DoubleValue(value=winkel[name]))
            # Geschwindigkeit, Beschleunigung und Last bleiben NULL und das ist
            # eine Aussage: die Kennlinie trägt nur Winkel. Erfundene Momente
            # sähen aus wie Messwerte und liefen in jede Auswertung.
            gelenk.velocity.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.acceleration.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.load.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))

        for kontakt in kontakte:
            fuss = zustand.foot_state.add()
            fuss.contact = (
                robot_state_pb2.FootState.CONTACT_MADE
                if kontakt
                else robot_state_pb2.FootState.CONTACT_LOST
            )
            fuss.foot_position_rt_body.z = -self._hoehe
            # KEIN terrain: `ground_mu_est` wurde nicht modelliert, und eine
            # erfundene 0.6 mittelte sich durch jede Kalibrierauswertung.

        zustand.kinematic_state.acquisition_timestamp.seconds = int(self._t)
        zustand.kinematic_state.acquisition_timestamp.nanos = int((self._t % 1) * 1e9)
        geschwindigkeit = zustand.kinematic_state.velocity_of_body_in_odom
        geschwindigkeit.linear.x = vx
        geschwindigkeit.linear.y = vy
        geschwindigkeit.angular.z = wz
        zustand.kinematic_state.transforms_snapshot.CopyFrom(self.frame_tree_snapshot())
        return zustand

    def frame_tree_snapshot(self):
        from bosdyn.api import geometry_pb2
        from bosdyn.client.frame_helpers import (
            BODY_FRAME_NAME,
            ODOM_FRAME_NAME,
            VISION_FRAME_NAME,
        )

        x, y, yaw = self._pose
        baum = geometry_pb2.FrameTreeSnapshot()
        baum.child_to_parent_edge_map[VISION_FRAME_NAME].CopyFrom(
            geometry_pb2.FrameTreeSnapshot.ParentEdge()
        )
        nach_odom = geometry_pb2.FrameTreeSnapshot.ParentEdge(
            parent_frame_name=VISION_FRAME_NAME
        )
        nach_odom.parent_tform_child.rotation.w = 1.0
        baum.child_to_parent_edge_map[ODOM_FRAME_NAME].CopyFrom(nach_odom)

        koerper = geometry_pb2.FrameTreeSnapshot.ParentEdge(
            parent_frame_name=ODOM_FRAME_NAME
        )
        koerper.parent_tform_child.position.x = x
        koerper.parent_tform_child.position.y = y
        koerper.parent_tform_child.position.z = self._hoehe
        koerper.parent_tform_child.rotation.w = math.cos(yaw / 2.0)
        koerper.parent_tform_child.rotation.z = math.sin(yaw / 2.0)
        baum.child_to_parent_edge_map[BODY_FRAME_NAME].CopyFrom(koerper)
        return baum
