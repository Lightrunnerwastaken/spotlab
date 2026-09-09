"""Die Fassade, die ein Schüler sieht.

Die Abkürzung ist keine Mauer: `spot.robot` und `spot.send()` führen jederzeit
zum vollen SDK — ohne Lease, Not-Aus und Aufzeichnung aufzugeben.
"""

from spotlab.api import motion, navigation, perception, posture, world
from spotlab.api.state import from_proto
from spotlab.config import Limits
from spotlab.record.messfenster import RESERVIERT, Messfenster  # noqa: F401  (Re-Export)


class Spot:
    def __init__(self, backend, recorder=None, limits=None, robot=None,
                 workspace=None, active_map=None, sampler=None):
        self.backend = backend
        self.recorder = recorder
        self.limits = limits or Limits()
        self.sampler = sampler
        self._robot = robot
        self._karte = None
        self._workspace = workspace
        self._active_map = active_map
        self._fenster = Messfenster(recorder, sampler)

    # ------------------------------------------------------------ Leistung

    def power_on(self):
        """Schaltet die Motoren ein. Spot steht davon noch nicht auf."""
        self.backend.power_on()
        if self.recorder is not None:
            self.recorder.event("power_on")

    def power_off(self, safe=True):
        """Schaltet die Motoren ab; mit safe=True setzt Spot sich vorher hin."""
        self.backend.power_off(safe=safe)
        if self.recorder is not None:
            self.recorder.event("power_off", safe=safe)

    @property
    def is_powered(self):
        """True, solange die Motoren eingeschaltet sind."""
        return self.backend.is_powered

    @property
    def battery(self):
        """Ladestand des Akkus in Prozent."""
        return self.state.battery

    # ------------------------------------------------------------ Haltung

    def stand(self, height=0.0, timeout=10.0, schlaf=None):
        """Steht auf. height hebt oder senkt den Körper in Metern."""
        posture.stand(
            self.backend,
            self.recorder,
            height=height,
            timeout=timeout,
            **({"schlaf": schlaf} if schlaf else {}),
        )

    def sit(self, timeout=10.0, schlaf=None):
        """Setzt sich hin."""
        posture.sit(
            self.backend,
            self.recorder,
            timeout=timeout,
            **({"schlaf": schlaf} if schlaf else {}),
        )

    # ------------------------------------------------------------ Bewegung

    def move(self, forward=0.0, left=0.0, turn=0.0, timeout=30.0):
        """Geht eine feste Strecke in Metern und dreht sich um turn in Grad."""
        motion.move(
            self.backend,
            self.recorder,
            self.limits,
            forward=forward,
            left=left,
            turn=turn,
            timeout=timeout,
        )

    def walk(self, vx=0.0, vy=0.0, wz=0.0, duration=1.0, stop=True):
        """Fährt duration Sekunden lang mit den angegebenen Geschwindigkeiten.

        vx, vy in m/s (vorwärts, links), wz in rad/s (links positiv). Mit
        `stop=False` kehrt der Aufruf sofort zurück und hält am Ende nicht an —
        für Schleifen, die laufend neu lenken; Spot fährt dann höchstens eine
        Sekunde weiter, bis das nächste Kommando kommt.
        """
        motion.walk(
            self.backend, self.recorder, self.limits, vx=vx, vy=vy, wz=wz,
            duration=duration, stop=stop,
        )

    def stop(self):
        """Hält sofort an."""
        motion.stop(self.backend, self.recorder)

    # ------------------------------------------------------------ Wahrnehmung

    def supports(self, feature):
        """Prueft look, camera, tags, stairs, navigate_to, pose, lights oder beep."""
        from spotlab.api.features import supports

        return supports(self, feature)

    def look(self, max_distance=1.8, margin=0.3, start=0.0):
        """Umgebung relativ zu Spot: front/left/right/back mit status, distance und known."""
        from spotlab.api.convenience import look

        return look(self.backend, self.recorder, max_distance, margin, start)

    def lights(self, color='blue', duration=2.0, brightness=0.25):
        """LEDs fuer duration Sekunden; blockierend, mit anschliessendem Aufraeumen."""
        from spotlab.api.signals import lights

        lights(self, color, duration, brightness)

    def beep(self, note='C', octave=5, duration=0.3):
        """Spielt eine Note auf dem Summer; blockiert bis zum Ende (keine WAV-Wiedergabe)."""
        from spotlab.api.signals import beep

        beep(self, note, octave, duration)

    def pose(self, roll=0.0, pitch=0.0, yaw=0.0, height=0.0, timeout=10.0):
        """Richtet den Koerper im Stand aus: Winkel in Grad, Hoehenversatz in Metern."""
        from spotlab.api.body import pose

        pose(self, roll, pitch, yaw, height, timeout)

    def cameras(self):
        """Nennt die Namen der Kameras, die dieser Spot hat."""
        return perception.cameras(self.backend)

    def camera(self, name):
        """Holt ein Bild der genannten Kamera und zeichnet es auf."""
        return perception.camera(self.backend, self.recorder, name)

    def depth(self, name="frontleft"):
        """Tiefenbild in Metern mit valid-Maske, Kalibrierung und Aufnahmezeit."""
        from spotlab.api import sensors

        return sensors.depth(self, name)

    def point_cloud(self, name="frontleft", frame="body", stride=2,
                    min_distance=0.0, max_distance=5.0):
        """Punktwolke in Metern aus einer Tiefenaufnahme, mit angegebenem Rahmen."""
        from spotlab.api import sensors

        return sensors.point_cloud(self, name, frame, stride, min_distance, max_distance)

    def grid_types(self):
        """Nennt die vom Backend angebotenen LocalGrid-Ebenen."""
        from spotlab.api import sensors

        return sensors.grid_types(self)

    def local_grid(self, name="obstacle_distance"):
        """Liest eine LocalGrid-Ebene; terrain nutzt auch terrain_valid."""
        from spotlab.api import sensors

        return sensors.local_grid(self, name)

    def world_objects(self, kinds=None):
        """Nennt alles, was Spot gerade als Objekt führt — nächstes zuerst."""
        return world.world_objects(self.backend, self.recorder, kinds=kinds)

    def tags(self, id=None):
        """Die sichtbaren AprilTags, nächstes zuerst. Peilung in Grad.

        `spot.move(turn=spot.tags()[0].bearing)` dreht zum nächsten Tag.
        """
        return world.tags(self.backend, self.recorder, id=id)

    def stairs(self):
        """Die Treppen in Sicht, nächste zuerst: Richtung („auf"/„ab"), Stufen, Achse.

        `spot.move(turn=treppe.axis_bearing)` stellt die Nase bergauf — und so
        geht es: vorwärts hoch, rückwärts runter.
        """
        return world.stairs(self.backend, self.recorder)

    def obstacles(self):
        """Das Hindernisgitter: wo ist Platz, wo nicht."""
        return world.obstacles(self.backend, self.recorder)

    @property
    def state(self):
        """Der aktuelle Zustand: Pose, Geschwindigkeit, Füsse, Akku."""
        return from_proto(self.backend.robot_state())

    # ------------------------------------------------------------ Karten

    def load_map(self, name=None):
        """Lädt eine GraphNav-Karte; ohne Namen die aktive aus der Konfiguration."""
        self._karte = navigation.load_map(
            self.backend, self.recorder, self._workspace, name, self._active_map
        )
        return self._karte

    def localize(self):
        """Bestimmt über ein Fiducial, wo Spot auf der geladenen Karte steht."""
        return navigation.localize(self.backend, self.recorder)

    def map_pose(self):
        """Wo Spot auf der geladenen Karte steht: (x, y, grad) im Kartenrahmen.

        `None`, solange `localize()` nicht gelaufen ist. Zusammen mit
        `welt.raum.aus_karte` wird daraus die Lage im rekonstruierten Raum --
        damit weiss ein Programm, ob es in einer Sperrzone steht.
        """
        return navigation.map_pose(self.backend, self.recorder)

    def navigate_to(self, ziel, timeout=120.0):
        """Fährt autonom zum genannten Wegpunkt der geladenen Karte."""
        if self._karte is None:
            from spotlab.errors import SpotlabError

            raise SpotlabError(
                "Es ist keine Karte geladen — rufe zuerst spot.load_map() auf."
            )
        navigation.navigate_to(
            self.backend, self.recorder, self._karte, ziel, self.limits, timeout=timeout
        )

    def waypoints(self):
        """Nennt die Wegpunkte der geladenen Karte."""
        return self._karte.waypoints if self._karte else []

    # ------------------------------------------------------------ Rohzugang

    @property
    def robot(self):
        """Das rohe bosdyn-Robot-Objekt (None im Trockenlauf)."""
        return self._robot

    def send(self, command, end_time_secs=None):
        """Schickt ein rohes RobotCommand-Protobuf an den Roboter."""
        if self.recorder is not None:
            self.recorder.event("kommando", name="send", roh=True)
        return self.backend.send_command(command, end_time_secs=end_time_secs)

    # ------------------------------------------------------------ Messung

    def messfenster(self, name, hz=50.0, **felder):
        """Markiert ein Messfenster und tastet darin dicht und vollständig ab.

        Innerhalb des Blocks läuft die Abtastung mit `hz` und schreibt den vollen
        Umfang; danach wieder wie zuvor. Die Marken landen als Ereignisse in der
        Aufzeichnung, damit später feststeht, welche Abtastungen zu welcher
        Bedingung gehören.

            with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
                spot.walk(vx=0.30, duration=8.0)

        Das Protokoll selbst liegt in `record/messfenster.py` — der
        Beobachter-Modus benutzt dieselbe Definition.
        """
        return self._fenster.oeffne(name, hz=hz, **felder)

    def close(self):
        """Beendet die Verbindung. connect() ruft das am Ende selbst auf."""
        self.backend.close()
