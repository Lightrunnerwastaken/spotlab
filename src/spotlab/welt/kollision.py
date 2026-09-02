"""Darf der Roboter dorthin, und was sieht er von hier aus?

Reine Standardbibliothek, keine Physik -- Abstaende zwischen Punkten, Strecken
und achsparallelen Rechtecken. Was daraus eine spotlab-Form macht, tut
`backends/sim.py`.

DER ROBOTER IST EIN KREIS mit 0.35 m Radius, abgeleitet aus Spots Grundflaeche
(rund 1.1 x 0.5 m). Die Vereinfachung ist bewusst und hat eine Richtung: ein
Kreis kann sich nicht seitlich durch eine schmale Luecke drehen, ein echter Spot
schon. Der Sim bleibt damit eher zu vorsichtig als zu optimistisch -- ausser
beim Drehen (siehe `bewege`).
"""

import math

ROBOTER_RADIUS_M = 0.35
# Laengere Schritte werden zerlegt. `dt` kommt aus der Wanduhr und haengt daran,
# wie oft ein Skript den Zustand abfragt; ohne Zerlegung haenge die Zusicherung
# "kein Programm faehrt durch eine Wand" an der Abfragehaeufigkeit.
MAX_SCHRITT_M = 0.10


def _abstand_punkt_strecke(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / laenge2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _abstand_punkt_rechteck(px, py, x, y, breite, hoehe):
    dx = max(x - px, 0.0, px - (x + breite))
    dy = max(y - py, 0.0, py - (y + hoehe))
    return math.hypot(dx, dy)


def hindernis_bei(raum, x, y, radius=ROBOTER_RADIUS_M):
    """Name dessen, was hier im Weg steht -- oder None."""
    for wand in raum.waende:
        if _abstand_punkt_strecke(x, y, *wand) < radius:
            return "Wand"
    for hindernis in raum.hindernisse:
        if _abstand_punkt_rechteck(x, y, *hindernis.rechteck) < radius:
            return hindernis.name
    return None


def frei(raum, x, y, radius=ROBOTER_RADIUS_M):
    return hindernis_bei(raum, x, y, radius) is None


def bewege(raum, von, nach):
    """(neue Pose, Name des Hindernisses oder None).

    Die DREHUNG wird immer uebernommen: ein Kreis, der sich dreht, ueberstreicht
    keine neue Flaeche. Ein Spot in einer Ecke kann sich also herausdrehen -- was
    er in Wirklichkeit auch kann, wenn auch nicht so muehelos.
    """
    x0, y0, _yaw0 = von
    x1, y1, yaw1 = nach
    strecke = math.hypot(x1 - x0, y1 - y0)
    if strecke < 1e-9:
        return (x0, y0, yaw1), None

    schritte = max(1, math.ceil(strecke / MAX_SCHRITT_M))
    letztes_gutes = (x0, y0)
    for i in range(1, schritte + 1):
        anteil = i / schritte
        px = x0 + (x1 - x0) * anteil
        py = y0 + (y1 - y0) * anteil
        getroffen = hindernis_bei(raum, px, py)
        if getroffen is not None:
            return (letztes_gutes[0], letztes_gutes[1], yaw1), getroffen
        letztes_gutes = (px, py)
    return (x1, y1, yaw1), None


def _schneiden(a1, a2, b1, b2):
    """Kreuzen sich die Strecken a und b?"""
    def kreuz(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    d1, d2 = kreuz(b1, b2, a1), kreuz(b1, b2, a2)
    d3, d4 = kreuz(a1, a2, b1), kreuz(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def sicht_frei(raum, a, b):
    """Freie Sichtlinie von a nach b? Waende und Hindernisse verdecken."""
    for x1, y1, x2, y2 in raum.waende:
        if _schneiden(a, b, (x1, y1), (x2, y2)):
            return False
    for hindernis in raum.hindernisse:
        x, y, breite, hoehe = hindernis.rechteck
        ecken = [(x, y), (x + breite, y), (x + breite, y + hoehe), (x, y + hoehe)]
        for erste, zweite in zip(ecken, ecken[1:] + ecken[:1]):
            if _schneiden(a, b, erste, zweite):
                return False
    return True
