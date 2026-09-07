"""GraphNav am echten Roboter: hochladen, verorten, fahren.

Freie Funktionen auf einem robot-Objekt statt einer Klasse — dieser
Protokollteil ist optional (nur RealSpot erfüllt ihn) und hat keinen eigenen
Zustand ausser dem, was ohnehin auf dem Roboter liegt.

Hier liegt auch nav_status(): die Abbildung eines Protobuf-Status auf den
neutralen NavStatus ist Backend-Arbeit. In errors/ wäre sie ein Importzyklus.
"""

from pathlib import Path

from bosdyn.api.graph_nav import graph_nav_pb2, map_pb2, nav_pb2
from bosdyn.client.graph_nav import GraphNavClient

from spotlab.backends import mobility
from spotlab.backends.base import NavStatus
from spotlab.errors import MapError, NotLocalized, translate
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
    _versuche(client.clear_graph)
    antwort = _versuche(client.upload_graph, graph=graph, generate_new_anchoring=True)

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


def _uebersetze(fehler):
    """SDK-Fehler in deutschen Klartext — oder unveraendert weiterreichen.

    Ohne das kamen bei `upload_map`, `localize` und `navigate_step` rohe
    SDK-Ausnahmen bis zum Schueler durch. Und `CannotModifyMapDuringRecording`
    ist der haeufigste davon: wer eine Karte aufnimmt und gleichzeitig eine
    hochladen will, bekam einen englischen Klassennamen statt eines Hinweises.
    """
    from bosdyn.client.graph_nav import CannotModifyMapDuringRecordingError

    if isinstance(fehler, CannotModifyMapDuringRecordingError):
        return MapError(
            "Auf dem Roboter laeuft gerade eine Kartenaufnahme. Beende sie "
            "zuerst in der Kartenansicht, dann laesst sich eine Karte hochladen."
        )
    return translate(fehler)


def _versuche(aufruf, *args, **kw):
    """Einen GraphNav-Aufruf machen und seine Fehler uebersetzen."""
    try:
        return aufruf(*args, **kw)
    except Exception as fehler:
        uebersetzt = _uebersetze(fehler)
        if uebersetzt is not None:
            raise uebersetzt from fehler
        raise


def localize(robot):
    """Über das nächste sichtbare Fiducial verorten. Gibt die Wegpunkt-ID zurück."""
    client = _client(robot)
    _versuche(
        client.set_localization,
        initial_guess_localization=nav_pb2.Localization(),
        fiducial_init=FIDUCIAL_NEAREST,
    )
    kennung = _versuche(client.get_localization_state).localization.waypoint_id
    if not kennung:
        raise NotLocalized(
            "Der Spot konnte sich nicht verorten. Stell ihn so hin, dass ein "
            "Fiducial im Kamerabild ist, und versuche es noch einmal."
        )
    return kennung


def localization_pose(robot):
    """(x, y, grad) des Koerpers im SEED-Rahmen der Karte -- oder None.

    Derselbe Rahmen, in dem `maps/rekonstruktion.py` den Raum baut. Damit
    laesst sich fragen, wo im REKONSTRUIERTEN RAUM der Roboter gerade steht
    (`welt/raum.py::aus_karte`) -- die Voraussetzung fuer Sperrzonen am
    echten Roboter.

    `None`, solange nicht verortet ist: `waypoint_id` ist dann leer, und die
    Pose im Protobuf waere ein Ursprung, also eine erfundene Position. Wer
    Zonen will, muss `localize()` gerufen haben.
    """
    import math

    from bosdyn.client.math_helpers import SE3Pose

    zustand = _versuche(_client(robot).get_localization_state)
    ortung = zustand.localization
    if not ortung.waypoint_id:
        return None
    pose = SE3Pose.from_proto(ortung.seed_tform_body)
    return (float(pose.x), float(pose.y), math.degrees(pose.rot.to_yaw()) % 360.0)


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
    return _versuche(
        _client(robot).navigate_to,
        waypoint_id, dauer_s, travel_params=params, command_id=command_id,
    )


def navigation_status(robot, command_id):
    antwort = _versuche(_client(robot).navigation_feedback, command_id=command_id)
    return nav_status(antwort.status)
