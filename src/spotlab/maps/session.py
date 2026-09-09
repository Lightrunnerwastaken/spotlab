"""Eine Kartenaufzeichnung — leaselos.

Der Ablauf im Unterricht: Aufnahme starten, den Spot MIT DEM TABLET durch den
Raum fahren, dabei entstehen automatisch Wegpunkte, an interessanten Stellen
eine benannte Marke setzen, am Ende beenden und herunterladen.

Vor dem Herunterladen wird die Karte NACHBEARBEITET: Schleifen schliessen und
Anker optimieren (`nachbearbeiten`). Ohne das bleibt die Aufnahme eine Kette —
wer zweimal durch denselben Gang fährt, bekommt zwei Stränge nebeneinander
statt einer Verbindung, und Spot fährt „wie auf Schienen" die aufgezeichnete
Strecke ab, statt den kurzen Weg zu nehmen.

Laut SDK-README braucht der Aufzeichnungsdienst kein Lease und keinen E-Stop:
er läuft passiv mit, während ein anderer Dienst den Roboter steuert. Dasselbe
gilt für den Nachbearbeitungsdienst — seine Anfragen haben gar kein Lease-Feld.
Genau deshalb darf die GUI beides bedienen, ohne H1 zu brechen, und deshalb
kommt in dieser Datei kein Lease- und kein E-Stop-Client vor.
"""

from dataclasses import dataclass
from pathlib import Path

from bosdyn.api.graph_nav import map_processing_pb2, recording_pb2
from bosdyn.client.graph_nav import GraphNavClient
from bosdyn.client.map_processing import MapProcessingServiceClient
from bosdyn.client.recording import GraphNavRecordingServiceClient
from google.protobuf import wrappers_pb2

from spotlab.errors import MapError, translate
from spotlab.errors.graphnav import AUFNAHME_TEXTE, WEGPUNKT_TEXTE
from spotlab.maps.store import sicherer_name, speichere_metadaten

_S = recording_pb2.StartRecordingResponse
_W = recording_pb2.CreateWaypointResponse

# Die Nachbearbeitung rechnet auf dem Roboter und dauert bei einer Schulkarte
# Sekunden. Zwei Fristen, damit weder der Dienst noch die GUI ewig wartet: der
# Dienst hört von selbst auf (`timeout_seconds`, er meldet dann `timed_out` und
# liefert, was er hat), die RPC-Frist liegt darüber und ist nur das Netz darunter.
SERVER_FRIST_S = 90.0
RPC_FRIST_S = 120.0


@dataclass(frozen=True)
class Nachbearbeitung:
    """Was die Nachbearbeitung erreicht hat. `None` heisst: nicht gelaufen."""

    neue_kanten: int | None = None
    schritte: int | None = None
    meldungen: tuple = ()

    @property
    def gelaufen(self):
        return self.neue_kanten is not None or self.schritte is not None


@dataclass(frozen=True)
class RecordingStatus:
    laeuft: bool
    wegpunkte: int
    kanten: int
    meldung: str


class RecordingSession:
    def __init__(self, robot, recording_client, graph_client, processing_client=None):
        self._robot = robot
        self._recording = recording_client
        self._graph = graph_client
        # Darf fehlen: eine ältere Roboter-Software hat den Dienst nicht, und
        # eine Aufnahme ohne Nachbearbeitung ist besser als gar keine.
        self._processing = processing_client

    @classmethod
    def connect(cls, cfg, verbinder=None):
        from spotlab.backends.real.verbindung import verbinde

        robot = (verbinder or verbinde)(cfg)
        return cls(
            robot=robot,
            recording_client=robot.ensure_client(
                GraphNavRecordingServiceClient.default_service_name
            ),
            graph_client=robot.ensure_client(GraphNavClient.default_service_name),
            processing_client=robot.ensure_client(
                MapProcessingServiceClient.default_service_name
            ),
        )

    # ------------------------------------------------------------- Aufnahme

    def start(self, graph_leeren=False):
        if graph_leeren:
            self._versuche(self._graph.clear_graph, "Karte auf dem Roboter leeren")
        antwort = self._versuche(self._recording.start_recording_full, "Aufnahme starten")
        if antwort.status != _S.STATUS_OK:
            raise MapError(
                AUFNAHME_TEXTE.get(
                    antwort.status,
                    f"Die Aufnahme liess sich nicht starten (Status {antwort.status}).",
                )
            )

    def waypoint(self, name):
        antwort = self._versuche(
            lambda: self._recording.create_waypoint(waypoint_name=sicherer_name(name, ersatz="karte")),
            "Wegpunkt setzen",
        )
        if antwort.status != _W.STATUS_OK:
            raise MapError(
                WEGPUNKT_TEXTE.get(
                    antwort.status,
                    f"Der Wegpunkt liess sich nicht setzen (Status {antwort.status}).",
                )
            )
        return antwort.created_waypoint.id

    def stop(self):
        self._versuche(self._recording.stop_recording, "Aufnahme beenden")

    def status(self):
        try:
            antwort = self._recording.get_record_status()
        except Exception as fehler:
            return RecordingStatus(False, 0, 0, f"Status nicht abrufbar: {fehler}")
        return RecordingStatus(
            laeuft=bool(antwort.is_recording),
            wegpunkte=int(antwort.map_stats.waypoints.count),
            kanten=int(antwort.map_stats.edges.count),
            meldung="Aufnahme läuft" if antwort.is_recording else "Keine Aufnahme",
        )

    # --------------------------------------------------------- Nachbearbeitung

    def schliesse_schleifen(self, fiducial=True, odometrie=True, frist_s=RPC_FRIST_S):
        """Schleifen im Graphen suchen und schliessen. Gibt (neue Kanten, abgelaufen).

        Der Aufzeichnungsdienst legt Wegpunkte in einer KETTE an: er weiss nicht,
        dass der Gang, durch den Spot zum zweiten Mal fährt, derselbe ist. Erst
        dieser Schritt verbindet die Enden — über gesehene Fiducials und über die
        Odometrie. Ohne ihn gibt es zwischen zwei Punkten immer nur den einen
        aufgezeichneten Weg.

        `modify_map_on_server=True`: die Karte auf dem Roboter wird geändert, und
        genau die laden wir gleich herunter.
        """
        params = map_processing_pb2.ProcessTopologyRequest.Params(
            do_fiducial_loop_closure=wrappers_pb2.BoolValue(value=bool(fiducial)),
            do_odometry_loop_closure=wrappers_pb2.BoolValue(value=bool(odometrie)),
            timeout_seconds=SERVER_FRIST_S,
        )
        antwort = self._versuche(
            lambda: self._prozessor().process_topology(
                params=params, modify_map_on_server=True, timeout=frist_s
            ),
            "Schleifen schliessen",
        )
        return len(antwort.new_subgraph.edges), bool(antwort.timed_out)

    def optimiere_anker(self, frist_s=RPC_FRIST_S):
        """Die Anker global optimieren. Gibt die Zahl der Rechenschritte zurück.

        Anker sind die Lage jedes Wegpunkts in EINEM gemeinsamen Rahmen. Ohne
        die Optimierung stehen sie so da, wie die Odometrie sie beim Fahren
        gesehen hat — eine Runde durch das Schulhaus schliesst sich dann sichtbar
        nicht. Daran hängt mehr als die Zeichnung: `maps/geometry.py` bevorzugt
        die Anker, und die Rekonstruktion eines Raums rechnet im selben Rahmen.
        """
        antwort = self._versuche(
            lambda: self._prozessor().process_anchoring(
                params=map_processing_pb2.ProcessAnchoringRequest.Params(),
                modify_anchoring_on_server=True,
                stream_intermediate_results=False,
                timeout=frist_s,
            ),
            "Anker optimieren",
        )
        return int(antwort.iteration)

    def nachbearbeiten(self, melde=None, fiducial=True, odometrie=True):
        """Schleifen schliessen und Anker optimieren — der Schritt, der aus einer
        Kette eine Karte macht. Wirft NIE.

        Jeder Schritt einzeln gekapselt, wie der Abbau in `RealSpot.close()`:
        eine gescheiterte Nachbearbeitung darf die Aufnahme nicht kosten. Wer
        eine Stunde durch das Schulhaus gefahren ist, bekommt seine Karte —
        notfalls unbearbeitet, aber mit dem Grund in der Meldung.
        """
        def sagen(text):
            meldungen.append(text)
            if melde is not None:
                melde(text)

        meldungen = []
        neue_kanten = schritte = None

        sagen("Schleifen werden gesucht…")
        try:
            neue_kanten, abgelaufen = self.schliesse_schleifen(fiducial, odometrie)
            sagen(
                f"{neue_kanten} neue Verbindung{'en' if neue_kanten != 1 else ''}."
                if neue_kanten
                else "Keine neue Verbindung gefunden."
            )
            if abgelaufen:
                sagen("Die Suche brach nach der Frist ab — die Karte ist trotzdem brauchbar.")
        except Exception as fehler:
            sagen(f"Schleifen nicht geschlossen: {fehler}")

        sagen("Anker werden optimiert…")
        try:
            schritte = self.optimiere_anker()
            sagen(f"Anker optimiert ({schritte} Rechenschritte).")
        except Exception as fehler:
            sagen(f"Anker nicht optimiert: {fehler}")

        return Nachbearbeitung(neue_kanten, schritte, tuple(meldungen))

    def _prozessor(self):
        if self._processing is None:
            raise MapError(
                "Dieser Roboter bietet die Kartennachbearbeitung nicht an "
                "(Dienst map-processing-service). Die Karte wird ohne sie gespeichert."
            )
        return self._processing

    # ------------------------------------------------------------- Speichern

    def download(self, wurzel, name, roboter=None):
        """Karte in <wurzel>/<name>/ ablegen. Gibt den Ordner zurück."""
        ziel = Path(wurzel) / sicherer_name(name, ersatz="karte")
        ziel.mkdir(parents=True, exist_ok=True)
        self._versuche(
            lambda: self._graph.write_graph_and_snapshots(str(ziel)),
            "Karte herunterladen",
        )
        graph = self._versuche(self._graph.download_graph, "Karte lesen")
        speichere_metadaten(ziel, sicherer_name(name, ersatz="karte"), roboter, graph)
        return ziel

    def close(self):
        pass  # kein Lease, kein E-Stop — es gibt nichts freizugeben

    # ------------------------------------------------------------- intern

    @staticmethod
    def _versuche(aufruf, was):
        try:
            return aufruf()
        except Exception as fehler:
            uebersetzt = translate(fehler)
            if uebersetzt is not None:
                raise uebersetzt from fehler
            raise MapError(f"{was} ist fehlgeschlagen: {fehler}") from fehler
