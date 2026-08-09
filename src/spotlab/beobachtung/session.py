"""Eine Beobachtungssitzung: mitschreiben, während ein Mensch steuert.

Aufgebaut wie `maps/session.py::RecordingSession` — `verbinde()` liefert einen
angemeldeten, zeitsynchronen Roboter OHNE Lease und OHNE E-Stop-Endpunkt.
Deshalb steht dieses Werkzeug nicht hinter Abnahmepunkt A1: es nimmt dem Tablet
nichts weg und kann den Roboter nicht bewegen.

Darum herum die unveränderte Aufzeichnungsmaschinerie: `RunRecorder`,
`StateSampler`, `Messfenster`. Nichts davon wird hier nachgebaut — zwei Stellen
mit den kalibrierkritischen Zeitregeln („nichts nachholen", Ratenwechsel,
Lückenmeldung) wären eine zu viel.
"""

import math
from pathlib import Path

from spotlab.beobachtung.quelle import Zustandsquelle
from spotlab.record.messfenster import Messfenster
from spotlab.record.run import RunRecorder
from spotlab.record.sampler import StateSampler

BACKEND_NAME = "beobachter"
ABTASTRATE_HZ = 10.0        # ausserhalb der Messfenster, wie bei spotlab.connect()

# Zeitfenster der Live-Zahlen. Nach ZEIT ausgewählt, nicht nach Anzahl — damit
# die Zahl unabhängig von der gerade eingestellten Abtastrate ist.
LIVE_FENSTER_S = 2.0
LIVE_MINDESTPUNKTE = 4


class Beobachtung:
    def __init__(self, quelle, recorder, sampler):
        self.quelle = quelle
        self.recorder = recorder
        self.sampler = sampler
        self._fenster = Messfenster(recorder, sampler)
        self._beendet = False

    # ------------------------------------------------------------- Aufbau

    @classmethod
    def connect(cls, cfg, runs_dir=None, verbinder=None, skript=None):
        """Leaselos verbinden und aufzeichnen.

        `verbinde()` prüft `SPOTLAB_NUR_TROCKEN` mit — ein Agent kann also auch
        keinen Beobachter auf den echten Roboter loslassen.
        """
        from bosdyn.client.robot_state import RobotStateClient

        from spotlab.backends.real.verbindung import verbinde

        robot = (verbinder or verbinde)(cfg)
        quelle = Zustandsquelle(
            robot.ensure_client(RobotStateClient.default_service_name)
        )
        return cls._bauen(quelle, runs_dir, skript)

    @classmethod
    def trocken(cls, runs_dir=None, skript=None):
        """Ohne Roboter. `DryRunBackend` hat `robot_state()` und plausible Werte.

        Damit lässt sich ein ganzes Drehbuch durchspielen, bevor jemand mit dem
        Spot in der Halle steht.
        """
        from spotlab.backends.dryrun import DryRunBackend

        return cls._bauen(DryRunBackend(), runs_dir, skript)

    @classmethod
    def _bauen(cls, quelle, runs_dir, skript):
        ziel = Path(runs_dir) if runs_dir else Path.cwd() / "runs"
        recorder = RunRecorder(ziel, skript, backend=BACKEND_NAME)
        sampler = StateSampler(quelle, recorder, hz=ABTASTRATE_HZ)
        sitzung = cls(quelle, recorder, sampler)
        recorder.event("verbunden", backend=BACKEND_NAME)
        sampler.start()
        return sitzung

    @property
    def lauf_verzeichnis(self):
        return self.recorder.dir

    # ------------------------------------------------------------- Betrieb

    def messfenster(self, name, hz=50.0, **felder):
        """Wie `Spot.messfenster` — dieselbe Definition, dasselbe Modul."""
        return self._fenster.oeffne(name, hz=hz, **felder)

    def zustand(self):
        """Die zuletzt geschriebene Abtastung, oder None."""
        verlauf = self.sampler.verlauf()
        return verlauf[-1] if verlauf else None

    def _live_punkte(self):
        """(t_robot, x, y, yaw) der letzten `LIVE_FENSTER_S`, sonst leere Liste.

        Zeitbasis ist die ROBOTERUHR: für Abstände innerhalb eines Laufs zählt
        sie, und die Unsicherheit der Zeitsynchronisierung gehört nicht in eine
        Geschwindigkeit hinein.
        """
        punkte = []
        for satz in self.sampler.verlauf():
            t, pose = satz.get("t_robot"), satz.get("pose")
            if t is None or not pose or len(pose) < 3:
                continue
            punkte.append((float(t), float(pose[0]), float(pose[1]), float(pose[2])))
        if len(punkte) < LIVE_MINDESTPUNKTE:
            return []
        ende = punkte[-1][0]
        drin = [p for p in punkte if ende - p[0] <= LIVE_FENSTER_S]
        return drin if len(drin) >= LIVE_MINDESTPUNKTE else []

    def tempo(self):
        """Bodengeschwindigkeit in m/s über die letzten Sekunden, oder None.

        BETRAG, nicht x-Komponente: beim Tablet-Fahren liegt die Fahrtrichtung
        nicht auf der odom-x-Achse. Der Sim misst `dp[0]/dt` entlang seiner
        Fahrtrichtung — beide Zahlen sind nur bei GERADEAUSFAHRT dasselbe.
        Deshalb steht „geradeaus, nicht lenken" in jedem Fahrt-Abschnitt des
        Drehbuchs.
        """
        drin = self._live_punkte()
        if not drin:
            return None
        dt = drin[-1][0] - drin[0][0]
        if dt <= 0:
            return None
        return math.hypot(drin[-1][1] - drin[0][1], drin[-1][2] - drin[0][2]) / dt

    def drehrate(self):
        """Gierrate in rad/s aus dem AUFSUMMIERTEN Winkel, oder None.

        Eine Endwert-Differenz mit Umschlag bei ±pi zeigte eine Drehung von
        2pi + x als x an; ein viel zu schnell drehender Roboter sähe perfekt aus.
        """
        drin = self._live_punkte()
        if not drin:
            return None
        dt = drin[-1][0] - drin[0][0]
        if dt <= 0:
            return None
        summe = 0.0
        for erst, zweit in zip(drin, drin[1:]):
            summe += (zweit[3] - erst[3] + math.pi) % (2 * math.pi) - math.pi
        return summe / dt

    # ------------------------------------------------------------- Abbau

    def beende(self, ergebnis="ok", fehler=None):
        """Abtaster stoppen und Lauf abschliessen. Läuft immer durch.

        Dieselbe verschachtelte Kette wie in `spotlab.connect()`: die Markierung
        zuerst, damit der Lauf während des Abbaus nicht schon als tot gilt,
        dann der Abtaster, und `finish()` in jedem Fall.
        """
        if self._beendet:
            return
        self._beendet = True
        self.recorder.abbau_beginnt()
        try:
            self.sampler.stop()
        finally:
            self.recorder.finish(ergebnis, fehler)

    def __enter__(self):
        return self

    def __exit__(self, art, wert, spur):
        if art is None:
            self.beende("ok")
        elif issubclass(art, KeyboardInterrupt):
            self.beende("abgebrochen", "Vom Benutzer abgebrochen (Ctrl-C)")
        else:
            self.beende("fehler", f"{art.__name__}: {wert}")
        return False
