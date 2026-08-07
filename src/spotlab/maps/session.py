"""Eine Kartenaufzeichnung — leaselos.

Der Ablauf im Unterricht: Aufnahme starten, den Spot MIT DEM TABLET durch den
Raum fahren, dabei entstehen automatisch Wegpunkte, an interessanten Stellen
eine benannte Marke setzen, am Ende beenden und herunterladen.

Laut SDK-README braucht der Aufzeichnungsdienst kein Lease und keinen E-Stop:
er läuft passiv mit, während ein anderer Dienst den Roboter steuert. Genau
deshalb darf die GUI ihn bedienen, ohne H1 zu brechen — und deshalb kommt in
dieser Datei kein Lease- und kein E-Stop-Client vor.
"""

from dataclasses import dataclass
from pathlib import Path

from bosdyn.api.graph_nav import recording_pb2
from bosdyn.client.graph_nav import GraphNavClient
from bosdyn.client.recording import GraphNavRecordingServiceClient

from spotlab.errors import MapError, translate
from spotlab.errors.graphnav import AUFNAHME_TEXTE, WEGPUNKT_TEXTE
from spotlab.maps.store import sicherer_name, speichere_metadaten

_S = recording_pb2.StartRecordingResponse
_W = recording_pb2.CreateWaypointResponse


@dataclass(frozen=True)
class RecordingStatus:
    laeuft: bool
    wegpunkte: int
    kanten: int
    meldung: str


class RecordingSession:
    def __init__(self, robot, recording_client, graph_client):
        self._robot = robot
        self._recording = recording_client
        self._graph = graph_client

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
