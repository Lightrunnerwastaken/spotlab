"""GraphNav-Statuscodes in deutschen Klartext.

Dieselbe Arbeit, die errors/translate.py für die Verbindungsseite leistet:
roh sind das englische Enum-Namen, übersetzt sind es Sätze, die einem Schüler
sagen, was zu tun ist.

Dieses Modul hängt bewusst an KEINEM Backend: die Abbildung eines Protobuf-
Status auf den neutralen NavStatus ist Backend-Arbeit und liegt in
backends/real/graphnav.py. Andersherum entstünde ein Importzyklus
(backends.base → errors → errors.graphnav → backends.base).
"""

from bosdyn.api.graph_nav import graph_nav_pb2, recording_pb2

from spotlab.errors import SpotlabError

_S = recording_pb2.StartRecordingResponse
_W = recording_pb2.CreateWaypointResponse
_N = graph_nav_pb2.NavigationFeedbackResponse


class MapError(SpotlabError):
    """Etwas mit der Karte stimmt nicht."""


class NavigationError(SpotlabError):
    """Die autonome Fahrt ist gescheitert."""


class NotLocalized(SpotlabError):
    """Der Roboter weiss nicht, wo er auf der Karte steht."""


AUFNAHME_TEXTE = {
    _S.STATUS_MISSING_FIDUCIALS: (
        "Der Spot sieht kein Fiducial. Stell ihn so hin, dass eine der Markierungen "
        "im Kamerabild ist, und starte die Aufnahme neu."
    ),
    _S.STATUS_NOT_LOCALIZED_TO_EXISTING_MAP: (
        "Auf dem Roboter liegt noch eine andere Karte. Kreuze beim Starten "
        "'Karte auf dem Roboter leeren' an."
    ),
    _S.STATUS_COULD_NOT_CREATE_WAYPOINT: (
        "Der Roboter konnte keinen Wegpunkt anlegen. Steht er zu nah an einer Wand?"
    ),
    _S.STATUS_FOLLOWING_ROUTE: (
        "Der Roboter fährt gerade eine Route ab. Warte, bis er fertig ist."
    ),
    _S.STATUS_TOO_FAR_FROM_EXISTING_MAP: (
        "Der Spot steht zu weit von der bestehenden Karte entfernt."
    ),
    _S.STATUS_FIDUCIAL_POSE_NOT_OK: (
        "Das Fiducial wurde erkannt, aber die Lage ist unsicher. Fahr näher heran "
        "und achte auf gute Beleuchtung."
    ),
    _S.STATUS_MAP_TOO_LARGE_LICENSE: (
        "Die Karte ist zu gross für die Lizenz dieses Roboters."
    ),
    _S.STATUS_ROBOT_IMPAIRED: (
        "Der Roboter meldet eine Störung. Prüfe mit 'spotlab doctor'."
    ),
}

WEGPUNKT_TEXTE = {
    _W.STATUS_NOT_RECORDING: (
        "Es läuft gerade keine Aufnahme. Starte zuerst die Aufnahme."
    ),
    _W.STATUS_COULD_NOT_CREATE_WAYPOINT: (
        "Der Roboter konnte hier keinen Wegpunkt anlegen. Fahr ein Stück weiter."
    ),
    _W.STATUS_MISSING_FIDUCIALS: (
        "Der Spot sieht kein Fiducial. Stell ihn so hin, dass eine Markierung "
        "im Kamerabild ist."
    ),
    _W.STATUS_FIDUCIAL_POSE_NOT_OK: (
        "Das Fiducial wurde erkannt, aber die Lage ist unsicher."
    ),
    _W.STATUS_MAP_TOO_LARGE_LICENSE: (
        "Die Karte ist zu gross für die Lizenz dieses Roboters."
    ),
}

NAVIGATION_TEXTE = {
    _N.STATUS_REACHED_GOAL: "Angekommen.",
    _N.STATUS_FOLLOWING_ROUTE: "Unterwegs.",
    _N.STATUS_NO_ROUTE: "Von hier führt kein Weg zum Ziel.",
    _N.STATUS_NO_LOCALIZATION: (
        "Der Spot weiss nicht, wo er ist — rufe zuerst spot.localize() auf."
    ),
    _N.STATUS_NOT_LOCALIZED_TO_ROUTE: (
        "Der Spot steht nicht auf dieser Route — verorte ihn neu mit spot.localize()."
    ),
    _N.STATUS_LOST: (
        "Der Spot hat sich auf der Karte verloren. Fahr ihn zurück zu einem "
        "Fiducial und verorte neu."
    ),
    _N.STATUS_STUCK: "Der Spot kommt nicht weiter. Steht etwas im Weg?",
    _N.STATUS_COMMAND_TIMED_OUT: (
        "Das Navigationskommando ist abgelaufen. Das ist ein Fehler in spotlab."
    ),
    _N.STATUS_ROBOT_IMPAIRED: (
        "Der Roboter meldet eine Störung. Prüfe mit 'spotlab doctor'."
    ),
    _N.STATUS_CONSTRAINT_FAULT: (
        "Die Route lässt sich mit den gesetzten Grenzen nicht abfahren."
    ),
    _N.STATUS_COMMAND_OVERRIDDEN: "Ein anderes Kommando hat die Fahrt überschrieben.",
}

FERTIG = frozenset({_N.STATUS_REACHED_GOAL})
LAEUFT = frozenset({_N.STATUS_FOLLOWING_ROUTE})


def unbekannter_status(status_wert):
    return f"Unbekannte Rückmeldung der Navigation ({status_wert})."
