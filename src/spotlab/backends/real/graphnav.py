"""GraphNav am echten Roboter: hochladen, verorten, fahren.

Freie Funktionen auf einem robot-Objekt statt einer Klasse — dieser
Protokollteil ist optional (nur RealSpot erfüllt ihn) und hat keinen eigenen
Zustand ausser dem, was ohnehin auf dem Roboter liegt.

Hier liegt auch nav_status(): die Abbildung eines Protobuf-Status auf den
neutralen NavStatus ist Backend-Arbeit. In errors/ wäre sie ein Importzyklus.
"""

from pathlib import Path

from bosdyn.api import geometry_pb2
from bosdyn.api.graph_nav import graph_nav_pb2, map_pb2, nav_pb2
from bosdyn.client.graph_nav import GraphNavClient

from spotlab.backends import mobility
from spotlab.backends.base import NavStatus
from spotlab.errors import MapError, NotLocalized
from spotlab.errors.graphnav import (
    FERTIG,
    LAEUFT,
    NAVIGATION_TEXTE,
    unbekannter_status,
)

FIDUCIAL_NEAREST = graph_nav_pb2.SetLocalizationRequest.FIDUCIAL_INIT_NEAREST


def nav_status(status_wert):
    """NavigationFeedbackResponse.Status → NavStatus mit deutschem Text."""
    text = NAVIGATION_TEXTE.get(status_wert)
    if text is None:
        return NavStatus(
            fertig=False, status=unbekannter_status(status_wert), gescheitert=True
        )
    if status_wert in FERTIG:
        return NavStatus(fertig=True, status=text, gescheitert=False)
    if status_wert in LAEUFT:
        return NavStatus(fertig=False, status=text, gescheitert=False)
    return NavStatus(fertig=False, status=text, gescheitert=True)


def _client(robot):
    return robot.ensure_client(GraphNavClient.default_service_name)


def clear_map(robot):
    _client(robot).clear_graph()


def upload_map(robot, kartenordner):
    """Karte aus dem Ordner auf den Roboter laden. Gibt den Graphen zurück.

    Fehlende Schnappschüsse werden nachgereicht: der Roboter meldet in
    unknown_*_snapshot_ids, was ihm fehlt. Sie vorsorglich alle zu schicken
    wäre teuer — jeder Wegpunkt bringt eine Punktwolke mit.
    """
    ordner = Path(kartenordner)
    graph = map_pb2.Graph()
    try:
        graph.ParseFromString((ordner / "graph").read_bytes())
    except OSError as fehler:
        raise MapError(f"Die Karte in {ordner} lässt sich nicht lesen.") from fehler

    client = _client(robot)
    client.clear_graph()
    antwort = client.upload_graph(graph=graph, generate_new_anchoring=True)

    for kennung in antwort.unknown_waypoint_snapshot_ids:
        pfad = ordner / "waypoint_snapshots" / kennung
        if not pfad.exists():
            continue
        schnappschuss = map_pb2.WaypointSnapshot()
        schnappschuss.ParseFromString(pfad.read_bytes())
        client.upload_waypoint_snapshot(schnappschuss)

    for kennung in antwort.unknown_edge_snapshot_ids:
        pfad = ordner / "edge_snapshots" / kennung
        if not pfad.exists():
            continue
        schnappschuss = map_pb2.EdgeSnapshot()
        schnappschuss.ParseFromString(pfad.read_bytes())
        client.upload_edge_snapshot(schnappschuss)

    return graph


def localize(robot):
    """Über das nächste sichtbare Fiducial verorten. Gibt die Wegpunkt-ID zurück."""
    client = _client(robot)
    client.set_localization(
        initial_guess_localization=nav_pb2.Localization(),
        fiducial_init=FIDUCIAL_NEAREST,
    )
    kennung = client.get_localization_state().localization.waypoint_id
    if not kennung:
        raise NotLocalized(
            "Der Spot konnte sich nicht verorten. Stell ihn so hin, dass ein "
            "Fiducial im Kamerabild ist, und versuche es noch einmal."
        )
    return kennung


def travel_params(limits, max_distance=0.4, max_yaw=0.15):
    """TravelParams mit unserem Geschwindigkeitsdeckel.

    Ohne velocity_limit führe die autonome Fahrt schneller als die von Hand
    gesteuerte. Die Grenze selbst kommt aus `backends/mobility.py` — denselben
    Wert zweimal zu formulieren wären zwei Gelegenheiten, ihn unterschiedlich
    falsch zu schreiben. Genau das war er: der frühere Kommentar hier behauptete,
    der Deckel gelte „sonst nur für walk() und move()", während `move()` ihn in
    Wahrheit gar nicht anwandte.
    """
    return GraphNavClient.generate_travel_params(
        max_distance, max_yaw, mobility.se2_grenze(limits)
    )


def navigate_step(robot, waypoint_id, dauer_s, params, command_id=None):
    """Ein Navigationskommando absetzen. Gibt die Kommando-ID zurück.

    Navigationskommandos verfallen wie Geschwindigkeitskommandos; der Aufrufer
    ruft das hier in einer Schleife auf.
    """
    return _client(robot).navigate_to(
        waypoint_id, dauer_s, travel_params=params, command_id=command_id
    )


def navigation_status(robot, command_id):
    antwort = _client(robot).navigation_feedback(command_id=command_id)
    return nav_status(antwort.status)
