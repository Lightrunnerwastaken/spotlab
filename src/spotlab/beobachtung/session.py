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

from spotlab.beobachtung.bilder import Bildmitschnitt
from spotlab.beobachtung.quelle import Zustandsquelle
from spotlab.record.messfenster import Messfenster
from spotlab.record.run import RunRecorder
from spotlab.record.sampler import StateSampler

BACKEND_NAME = "beobachter"
# Eigener Name für die Probe. Beide „beobachter" zu nennen war ein Fehler: eine
# Trockenprobe und eine echte Messfahrt waren in `lauf.json` nicht zu
# unterscheiden — nur matura-spots eigenes Protokoll wusste es, und davon weiss
# spotlab nichts. Aufgefallen beim Bau der Gangkennlinie am 12.08.2026, wo eine
# Probe beinahe in die Kalibrierdaten gelaufen wäre. Sie fiel nur deshalb heraus,
# weil `DryRunBackend` alle vier Füsse am Boden lässt und damit null Gangzyklen
# erzeugt — also aus Versehen, nicht aus Absicht. Sobald das Sim-Backend die
# Beine bewegt, fiele sie nicht mehr heraus.
# Dieselbe Regel wie bei `dryrun`: die Aufzeichnung sagt, was sie ist.
BACKEND_NAME_TROCKEN = "beobachter-trocken"
ABTASTRATE_HZ = 10.0        # ausserhalb der Messfenster, wie bei spotlab.connect()

# Ausserhalb der Messfenster wird REICH abgetastet — anders als im Schülerlauf.
# Begründung: dort ist der schlanke Satz richtig (50 RPCs/s über WLAN für Daten,
# die niemand ansieht). Eine Messfahrt ist der umgekehrte Fall — sie findet
# einmal statt, und was zwischen den Fenstern nicht mitgeschrieben wurde, ist
# weg. Reich kostet rund das Neunfache an Bytes, bei 10 Hz also gut 70 MB je
# Stunde; das ist gegen einen zweiten Roboterzugang kein Preis.
# Nur im reichen Satz stehen µ, Schlupf, Motortemperaturen und Faults.
REICH_AUSSERHALB = True

BILDRATE_HZ = 1.0           # Vorgabe des Bildmitschnitts; 0 schaltet ihn ab

# Zeitfenster der Live-Zahlen. Nach ZEIT ausgewählt, nicht nach Anzahl — damit
# die Zahl unabhängig von der gerade eingestellten Abtastrate ist.
LIVE_FENSTER_S = 2.0
LIVE_MINDESTPUNKTE = 4


class Beobachtung:
    def __init__(self, quelle, recorder, sampler, mitschnitt=None, bild_hinweis=None):
        self.quelle = quelle
        self.recorder = recorder
        self.sampler = sampler
        self.mitschnitt = mitschnitt
        # Warum kein Bild aufgezeichnet wird, falls keins aufgezeichnet wird.
        # Muss nach oben sichtbar sein: eine Messfahrt, die still ohne Bilder
        # läuft, merkt niemand, bis der Roboter wieder weg ist.
        self.bild_hinweis = bild_hinweis
        self._fenster = Messfenster(recorder, sampler)
        self._beendet = False

    # ------------------------------------------------------------- Aufbau

    @classmethod
    def connect(
        cls, cfg, runs_dir=None, verbinder=None, skript=None,
        bilder_hz=BILDRATE_HZ, tiefe=False,
    ):
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
        bildquelle, hinweis = cls._bildquelle(robot, bilder_hz, tiefe)
        return cls._bauen(quelle, runs_dir, skript, bildquelle, bilder_hz, hinweis)

    @staticmethod
    def _bildquelle(robot, bilder_hz, tiefe):
        """Bildquelle aufbauen — und beim Scheitern den Grund zurückgeben.

        Die Zustandsabtastung ist die Hauptmessung. Sie darf nicht daran
        scheitern, dass ein Kameradienst fehlt oder anders heisst. Umgekehrt
        darf das Fehlen nicht stillschweigend passieren, deshalb ein Text
        statt eines stummen None.
        """
        if bilder_hz <= 0:
            return None, "Bildmitschnitt ausgeschaltet (--bilder 0)."
        from bosdyn.client.image import ImageClient

        from spotlab.beobachtung.bildquelle import (
            Bildquelle,
            gemeldete_quellen,
            waehle_quellen,
        )

        try:
            client = robot.ensure_client(ImageClient.default_service_name)
            gemeldet = gemeldete_quellen(client)
            quellen = waehle_quellen(gemeldet, tiefe=tiefe)
        except Exception as fehler:
            return None, f"Kameradienst nicht erreichbar ({type(fehler).__name__}: {fehler})."
        if not quellen:
            # Die gemeldeten Namen MIT ausgeben: ohne sie steht der Bediener vor
            # „geht nicht" und kann am Messtag nichts damit anfangen. Mit ihnen
            # ist die Abweichung in einer Minute zu sehen.
            return None, (
                "Keine der erwarteten Kameraquellen. Der Roboter meldet: "
                + (", ".join(sorted(gemeldet)) or "gar keine")
                + "."
            )
        return Bildquelle(client, quellen), None

    @classmethod
    def trocken(cls, runs_dir=None, skript=None, bilder_hz=BILDRATE_HZ, tiefe=False):
        """Ohne Roboter. `DryRunBackend` hat `robot_state()` und plausible Werte.

        Damit lässt sich ein ganzes Drehbuch durchspielen, bevor jemand mit dem
        Spot in der Halle steht — Bildweg eingeschlossen: `TrockeneBildquelle`
        baut echte `ImageResponse`-Protos, die Probe durchläuft also dieselbe
        Kodier-, Schreib- und Indexlogik wie später am Roboter.
        """
        from spotlab.backends.dryrun import DryRunBackend
        from spotlab.beobachtung.bildquelle import FISHEYE, TIEFE, TrockeneBildquelle

        bildquelle = None
        hinweis = "Bildmitschnitt ausgeschaltet (--bilder 0)."
        if bilder_hz > 0:
            bildquelle = TrockeneBildquelle(FISHEYE + TIEFE if tiefe else FISHEYE)
            hinweis = None
        return cls._bauen(
            DryRunBackend(), runs_dir, skript, bildquelle, bilder_hz, hinweis,
            backend=BACKEND_NAME_TROCKEN,
        )

    @classmethod
    def _bauen(cls, quelle, runs_dir, skript, bildquelle=None,
               bilder_hz=BILDRATE_HZ, bild_hinweis=None, backend=BACKEND_NAME):
        ziel = Path(runs_dir) if runs_dir else Path.cwd() / "runs"
        recorder = RunRecorder(ziel, skript, backend=backend)
        sampler = StateSampler(quelle, recorder, hz=ABTASTRATE_HZ)
        sampler.setze_takt(ABTASTRATE_HZ, REICH_AUSSERHALB)
        mitschnitt = None
        if bildquelle is not None:
            mitschnitt = Bildmitschnitt(bildquelle, recorder, hz=bilder_hz)
        sitzung = cls(quelle, recorder, sampler, mitschnitt, bild_hinweis)
        recorder.event(
            "verbunden",
            backend=backend,
            reich=REICH_AUSSERHALB,
            bilder_hz=bilder_hz if mitschnitt is not None else 0.0,
        )
        sampler.start()
        if mitschnitt is not None:
            mitschnitt.start()
        return sitzung

    @property
    def lauf_verzeichnis(self):
        return self.recorder.dir

    # ------------------------------------------------------------- Betrieb

    def messfenster(self, name, hz=50.0, **felder):
        """Wie `Spot.messfenster` — dieselbe Definition, dasselbe Modul."""
        return self._fenster.oeffne(name, hz=hz, **felder)

    def bildzaehler(self):
        """Zählerstand des Bildmitschnitts, oder None wenn keiner läuft."""
        return self.mitschnitt.zaehler() if self.mitschnitt is not None else None

    def setze_bildrate(self, hz):
        """Bildtakt ändern — wirkungslos, wenn kein Mitschnitt läuft."""
        if self.mitschnitt is not None:
            self.mitschnitt.setze_rate(hz)

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
            try:
                # Auch der Bildthread muss stehen, bevor der Lauf fertig heisst
                # — sonst schriebe er noch Dateien in ein abgeschlossenes
                # Verzeichnis. Eigenes try: ein Fehler hier darf `finish()`
                # nicht verhindern, sonst bliebe der Lauf für immer auf „läuft".
                if self.mitschnitt is not None:
                    self.mitschnitt.stop()
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
