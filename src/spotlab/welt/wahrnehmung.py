"""Was von einer Pose aus zu sehen ist -- als rohe Zahlen.

Hier ist numpy erlaubt, in `raum.py` und `kollision.py` nicht: das Gitter hat
16384 Zellen, und in reiner Python-Schleife kostete ein Abruf rund zwei Zehntel
Sekunden. `raum.py` wird von der GUI importiert und bleibt deshalb leicht;
dieses Modul importiert nur `backends/sim.py`.

Rueckgabe sind LISTEN und rohe dx/dy im Koerperframe -- keine spotlab-Formen.
Ein `Tag` oder ein `ObstacleGrid` daraus zu bauen ist Sache von sim.py, weil
`richtung()` in backends/base.py wohnt und welt/ nichts aus backends/ importiert.
"""

import math

import numpy as np

from spotlab.welt.kollision import sicht_frei

# Geschaetzt, NICHT gemessen. Abnahmepunkt A22 misst den echten Wert am Geraet;
# die Simulation rechnet bislang mit rund 12 m, real werden 2-3 m erwartet.
TAG_REICHWEITE_M = 3.0

# Masse des echten LocalGrid: 128 x 128 Zellen a 3 cm sind 3.84 m Kantenlaenge.
# Der Roboter steht in der Mitte, das Gitter reicht also nur 1.92 m weit -- in
# einem 6-m-Zimmer nicht bis zur gegenueberliegenden Wand. Der echte kann es
# auch nicht.
GITTER_ZELLEN = 128
GITTER_ZELLE_M = 0.03

# Sichtbarkeit wird auf einem groeberen Raster geprueft: 16384 Sichtlinien
# waeren zu teuer, jede vierte Zelle reicht fuer eine Uebungsumgebung.
SICHT_RASTER = 4


def sichtbare_tags(raum, pose):
    """[(RaumTag, dx, dy)] im Koerperframe, naechster zuerst.

    KEIN Blickfeld-Kegel: der echte Spot hat fuenf Kameras und sieht rundum.
    Ein Tag zaehlt, wenn er in Reichweite ist und die Sichtlinie frei.
    """
    x, y, yaw = pose
    gefunden = []
    for tag in raum.tags:
        dx_welt, dy_welt = tag.x - x, tag.y - y
        if math.hypot(dx_welt, dy_welt) > TAG_REICHWEITE_M:
            continue
        if not sicht_frei(raum, (x, y), (tag.x, tag.y)):
            continue
        cos, sin = math.cos(-yaw), math.sin(-yaw)
        gefunden.append((
            tag,
            dx_welt * cos - dy_welt * sin,
            dx_welt * sin + dy_welt * cos,
        ))
    gefunden.sort(key=lambda eintrag: math.hypot(eintrag[1], eintrag[2]))
    return gefunden


def _abstaende(raum, xs, ys):
    """Je Zelle der Abstand zum naechsten Hindernis, vektorisiert."""
    abstand = np.full(xs.shape, np.inf)
    for x1, y1, x2, y2 in raum.waende:
        dx, dy = x2 - x1, y2 - y1
        laenge2 = dx * dx + dy * dy
        if laenge2 == 0.0:
            abstand = np.minimum(abstand, np.hypot(xs - x1, ys - y1))
            continue
        t = np.clip(((xs - x1) * dx + (ys - y1) * dy) / laenge2, 0.0, 1.0)
        abstand = np.minimum(abstand, np.hypot(xs - (x1 + t * dx), ys - (y1 + t * dy)))
    for hindernis in raum.hindernisse:
        hx, hy, breite, hoehe = hindernis.rechteck
        dx = np.maximum(np.maximum(hx - xs, 0.0), xs - (hx + breite))
        dy = np.maximum(np.maximum(hy - ys, 0.0), ys - (hy + hoehe))
        abstand = np.minimum(abstand, np.hypot(dx, dy))
    return abstand


def abstandsgitter(raum, pose):
    """(werte, bekannt, ursprung) -- Listen, damit welt/ formfrei bleibt.

    `bekannt` ist False, wo die Sichtlinie durch eine Wand oder ein Hindernis
    laeuft. Unbekannt ist NICHT frei -- das ist der Fehler, der einen Roboter in
    eine Wand faehrt.
    """
    x, y, _yaw = pose
    kante = GITTER_ZELLEN * GITTER_ZELLE_M
    ursprung = (x - kante / 2, y - kante / 2)

    achse = np.arange(GITTER_ZELLEN) * GITTER_ZELLE_M
    xs = ursprung[0] + achse[np.newaxis, :]
    ys = ursprung[1] + achse[:, np.newaxis]
    xs, ys = np.broadcast_arrays(xs, ys)

    werte = _abstaende(raum, xs, ys)

    bekannt = np.ones(werte.shape, dtype=bool)
    for zeile in range(0, GITTER_ZELLEN, SICHT_RASTER):
        for spalte in range(0, GITTER_ZELLEN, SICHT_RASTER):
            zx = ursprung[0] + spalte * GITTER_ZELLE_M
            zy = ursprung[1] + zeile * GITTER_ZELLE_M
            if not sicht_frei(raum, (x, y), (zx, zy)):
                bekannt[zeile:zeile + SICHT_RASTER,
                        spalte:spalte + SICHT_RASTER] = False

    # Zellen IM Hindernis sind bekannt: der Roboter sieht das Hindernis, das
    # ihm die Sicht nimmt -- seine Vorderseite gehoert zum Bekannten.
    # NICHT `werte < ROBOTER_RADIUS_M`: das machte auch Zellen 30 cm DAHINTER
    # bekannt und widerspraeche genau der Zusicherung, um die es hier geht.
    bekannt |= werte <= 0.0

    return werte.tolist(), bekannt.tolist(), ursprung
