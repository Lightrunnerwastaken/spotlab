"""Wegpunkte in eine zeichenbare Ebene bringen.

Zwei Wege, weil graph.anchoring nicht immer befüllt ist — view_map.py aus dem
SDK prüft das ausdrücklich und zeichnet sonst über die Kantenkette:

anker   Positionen direkt aus anchoring. Genauer, weil global optimiert.
kette   Ab einem Wurzel-Wegpunkt edge.from_tform_to aufmultiplizieren.
"""

from dataclasses import dataclass

from bosdyn.client.math_helpers import SE3Pose

HINWEIS_KETTE = (
    "Gezeichnet über die Kantenkette, weil die Karte keine Anker hat. "
    "Über lange Wege summieren sich dabei Rundungsfehler — eine Schleife "
    "schliesst sich dann sichtbar nicht ganz. Das ist keine Fehlfunktion."
)
HINWEIS_LEER = "Diese Karte enthält keine Wegpunkte."
HINWEIS_UNVERBUNDEN = (
    "Diese Karte hat mehrere Wegpunkte, aber keine Kanten dazwischen — "
    "ohne Kanten lässt sich ihre Lage zueinander nicht bestimmen."
)


@dataclass(frozen=True)
class Punkt:
    id: str
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class Grundriss:
    punkte: list
    kanten: list
    quelle: str
    hinweis: str


def _kanten_paare(graph):
    return [(k.id.from_waypoint, k.id.to_waypoint) for k in graph.edges]


def _namen(graph):
    return {wp.id: (wp.annotations.name or "") for wp in graph.waypoints}


def _aus_ankern(graph):
    anker = {a.id: a.seed_tform_waypoint.position for a in graph.anchoring.anchors}
    if not anker or any(wp.id not in anker for wp in graph.waypoints):
        return None  # unvollständig ⇒ die Kette ist ehrlicher
    namen = _namen(graph)
    return [
        Punkt(wp.id, namen[wp.id], float(anker[wp.id].x), float(anker[wp.id].y))
        for wp in graph.waypoints
    ]


def _aus_kette(graph):
    """Breitensuche ab dem ersten Wegpunkt, Transformationen aufmultiplizieren."""
    if not graph.waypoints:
        return None
    nachbarn = {}
    for kante in graph.edges:
        pose = SE3Pose.from_proto(kante.from_tform_to)
        nachbarn.setdefault(kante.id.from_waypoint, []).append((kante.id.to_waypoint, pose))
        nachbarn.setdefault(kante.id.to_waypoint, []).append(
            (kante.id.from_waypoint, pose.inverse())
        )

    wurzel = graph.waypoints[0].id
    posen = {wurzel: SE3Pose.from_identity()}
    warteschlange = [wurzel]
    while warteschlange:
        aktuell = warteschlange.pop(0)
        for ziel, versatz in nachbarn.get(aktuell, ()):
            if ziel in posen:
                continue
            posen[ziel] = posen[aktuell].mult(versatz)
            warteschlange.append(ziel)

    if len(posen) < len(graph.waypoints):
        return None  # nicht alles erreichbar
    namen = _namen(graph)
    return [
        Punkt(wp.id, namen[wp.id], float(posen[wp.id].x), float(posen[wp.id].y))
        for wp in graph.waypoints
    ]


def grundriss(graph):
    kanten = _kanten_paare(graph)

    punkte = _aus_ankern(graph)
    if punkte is not None:
        return Grundriss(punkte, kanten, "anker", "")

    punkte = _aus_kette(graph)
    if punkte is not None:
        return Grundriss(punkte, kanten, "kette", HINWEIS_KETTE)

    hinweis = HINWEIS_LEER if not graph.waypoints else HINWEIS_UNVERBUNDEN
    return Grundriss([], kanten, "leer", hinweis)
