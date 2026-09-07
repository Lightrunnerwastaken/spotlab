"""Raeume zeichnen -- einmal, fuer Raumeditor und Uebungsfenster.

QPainter wie ueberall. Farben nur aus dem Theme. Die Umrechnung Meter -> Pixel
bringt der Aufrufer mit (`meter_zu_schirm`), weil Editor und Uebungsfenster
verschieden zoomen; `skala` sind Pixel je Meter fuer Radien und Dicken.
Zwei Zeichner, die die Drehung getrennt lernten, wichen voneinander ab, ohne
dass es auffiele -- deshalb gibt es genau einen.
"""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPen, QPolygonF

from spotlab.gui.theme import mische
from spotlab.welt.hoehe import auf_ebene
from spotlab.welt.kollision import ROBOTER_RADIUS_M

TAG_KANTE_M = 0.15
PFEIL_M = 0.4
ZACKE_PX = 4               # Kammlinie der Klippen


def _auf(element, raum, ebene):
    return ebene is None or auf_ebene(element, raum, ebene)


def zeichne_boden(maler, boden, meter_zu_schirm, skala, palette, gewaehlt=False, blass=False):
    """Ein Boden: helle Flaeche, bei Anstieg Pfeil bergauf und die Hoehen, je Stufe eine Linie."""
    rand = palette.akzent if gewaehlt else (palette.blass if blass else palette.gedaempft)
    fuellung = QColor(palette.blass if blass else palette.flaeche)
    maler.setPen(QPen(QColor(rand), 2 if gewaehlt else 1))
    maler.setBrush(QBrush(fuellung))
    maler.drawPolygon(_polygon(boden.ecken(), meter_zu_schirm))
    c, s = math.cos(math.radians(boden.drehung)), math.sin(math.radians(boden.drehung))

    def welt(lx, ly):
        return boden.x + lx * c - ly * s, boden.y + lx * s + ly * c

    maler.setPen(QPen(QColor(rand), 1))
    if boden.stufen > 0:
        tiefe = boden.breite / boden.stufen
        for i in range(1, boden.stufen):
            lx = -boden.breite / 2 + i * tiefe
            a, b_ = welt(lx, -boden.tiefe / 2), welt(lx, boden.tiefe / 2)
            maler.drawLine(QPointF(*meter_zu_schirm(*a)), QPointF(*meter_zu_schirm(*b_)))
    if boden.anstieg != 0.0:
        laenge = min(boden.breite * 0.4, 0.6)
        richtung = 1.0 if boden.anstieg > 0 else -1.0
        a, b_ = welt(-richtung * laenge, 0.0), welt(richtung * laenge, 0.0)
        pa, pb = meter_zu_schirm(*a), meter_zu_schirm(*b_)
        maler.setPen(QPen(QColor(rand), 2))
        maler.drawLine(QPointF(*pa), QPointF(*pb))
        winkel = math.atan2(pb[1] - pa[1], pb[0] - pa[0])
        for seite in (0.8, -0.8):
            maler.drawLine(QPointF(*pb), QPointF(pb[0] - 8 * math.cos(winkel + seite),
                                                 pb[1] - 8 * math.sin(winkel + seite)))
    px, py = meter_zu_schirm(boden.x, boden.y)
    maler.setPen(QColor(palette.blass if blass else palette.gedaempft))
    text = boden.name if boden.anstieg == 0.0 else f"{boden.name} {boden.z:.2f}→{boden.z_oben:.2f}"
    if boden.anstieg == 0.0:
        text = f"{boden.name} {boden.z:.2f} m"
    maler.drawText(int(px) + 4, int(py) + 14, text)


def zeichne_klippen(maler, klippen_, meter_zu_schirm, palette):
    """Absturzkanten als Kammlinie in der Warnfarbe."""
    maler.setPen(QPen(QColor(palette.warnung), 1))
    for x1, y1, x2, y2 in klippen_:
        pa, pb = meter_zu_schirm(x1, y1), meter_zu_schirm(x2, y2)
        maler.drawLine(QPointF(*pa), QPointF(*pb))
        laenge = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if laenge < 1e-6:
            continue
        nx, ny = -(pb[1] - pa[1]) / laenge, (pb[0] - pa[0]) / laenge
        n = max(1, int(laenge // (2 * ZACKE_PX)))
        for i in range(n + 1):
            t = i / n
            qx, qy = pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t
            maler.drawLine(QPointF(qx, qy), QPointF(qx + nx * ZACKE_PX, qy + ny * ZACKE_PX))


def wand_polygon(wand, dicke):
    """Die vier Ecken des Wandbalkens (Weltkoordinaten)."""
    x1, y1, x2, y2 = wand
    laenge = math.hypot(x2 - x1, y2 - y1)
    if laenge == 0.0:
        nx, ny = 0.0, dicke / 2
    else:
        nx, ny = -(y2 - y1) / laenge * dicke / 2, (x2 - x1) / laenge * dicke / 2
    return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]


def _polygon(punkte, meter_zu_schirm):
    return QPolygonF([QPointF(*meter_zu_schirm(x, y)) for x, y in punkte])


def zeichne_raum(maler, raum, meter_zu_schirm, skala, palette, auswahl=frozenset(),
                 ebene=None, klippen_=()):
    """Boeden, Waende, Bloecke, Tags. Die Auswahl in Akzentfarbe.

    `ebene` (eine Bodenhoehe oder None = alle): was auf einer anderen Ebene
    liegt, wird blass gezeichnet, nicht weg -- beim Setzen einer Treppe muss
    man sehen, wo sie oben ankommt. Boeden liegen unter allem; Klippen kommen
    als Kammlinie darueber.
    """
    for i, boden in enumerate(raum.boeden):
        zeichne_boden(maler, boden, meter_zu_schirm, skala, palette,
                      gewaehlt=("boden", i) in auswahl, blass=not _auf(boden, raum, ebene))
    zeichne_klippen(maler, klippen_, meter_zu_schirm, palette)

    for i, block in enumerate(raum.bloecke):
        gewaehlt = ("block", i) in auswahl
        blass = not _auf(block, raum, ebene)
        maler.setPen(QPen(QColor(palette.akzent if gewaehlt else (palette.blass if blass else palette.rand)), 2))
        maler.setBrush(QBrush(QColor(palette.blass if blass else palette.flaeche)))
        maler.drawPolygon(_polygon(block.ecken(), meter_zu_schirm))
        px, py = meter_zu_schirm(block.x, block.y)
        maler.setPen(QColor(palette.blass if blass else palette.gedaempft))
        maler.drawText(int(px) + 4, int(py) - 4, block.name)

    for i, wand in enumerate(raum.waende):
        gewaehlt = ("wand", i) in auswahl
        blass = not _auf(wand, raum, ebene)
        farbe = QColor(palette.akzent if gewaehlt else (palette.blass if blass else palette.text))
        maler.setPen(QPen(farbe, 1))
        maler.setBrush(QBrush(farbe))
        # Mindestens zwei Pixel breit, sonst verschwindet eine Wand beim Herauszoomen.
        dicke = max(raum.wand_dicke, 2.0 / max(skala, 1e-6))
        maler.drawPolygon(_polygon(wand_polygon(wand, dicke), meter_zu_schirm))

    maler.setBrush(Qt.NoBrush)
    for i, tag in enumerate(raum.tags):
        gewaehlt = ("tag", i) in auswahl
        blass = not _auf(tag, raum, ebene)
        maler.setPen(QPen(QColor(palette.akzent if gewaehlt else (palette.blass if blass else palette.zahl)), 2))
        px, py = meter_zu_schirm(tag.x, tag.y)
        halb = max(6.0, TAG_KANTE_M / 2 * skala)
        maler.drawRect(int(px - halb), int(py - halb), int(2 * halb), int(2 * halb))
        sx, sy = meter_zu_schirm(tag.x + PFEIL_M * math.cos(math.radians(tag.grad)),
                                 tag.y + PFEIL_M * math.sin(math.radians(tag.grad)))
        maler.drawLine(QPointF(px, py), QPointF(sx, sy))
        maler.drawText(int(px + halb) + 3, int(py) + 4, str(tag.id))


def zeichne_spur(maler, spur, meter_zu_schirm, palette):
    if len(spur) < 2:
        return
    maler.setPen(QPen(QColor(palette.akzent), 2, Qt.DotLine))
    for erster, zweiter in zip(spur, spur[1:]):
        maler.drawLine(QPointF(*meter_zu_schirm(*erster)), QPointF(*meter_zu_schirm(*zweiter)))


def zeichne_anstoesse(maler, punkte, meter_zu_schirm, palette):
    maler.setPen(QPen(QColor(palette.gefahr), 2))
    for x, y in punkte:
        px, py = meter_zu_schirm(x, y)
        maler.drawLine(int(px) - 5, int(py) - 5, int(px) + 5, int(py) + 5)
        maler.drawLine(int(px) - 5, int(py) + 5, int(px) + 5, int(py) - 5)


def zeichne_spot(maler, px, py, blick_grad, skala, palette, gewaehlt=False):
    """Spot als Kreis mit Blickstrich -- `px, py` schon in Pixeln."""
    r = max(4.0, ROBOTER_RADIUS_M * skala)
    maler.setPen(QPen(QColor(palette.akzent if gewaehlt else palette.funktion), 2))
    maler.setBrush(Qt.NoBrush)
    maler.drawEllipse(QPointF(px, py), r, r)
    maler.drawLine(QPointF(px, py), QPointF(
        px + r * math.cos(math.radians(blick_grad)),
        py - r * math.sin(math.radians(blick_grad)),
    ))


# ------------------------------------------------------------- Gelaende

HOEHENLINIE_M = 0.25       # Hoehenlinie alle 0.25 m
EBENE_TOLERANZ_M = 0.3     # so weit ab von einer Ebene ist ein Knoten blass
GELAENDE_ALPHA = 200


def gelaende_rechteck(gelaende):
    """(x_min, y_min, x_max, y_max): das Knotengitter plus eine halbe Zelle rundum."""
    halb = gelaende.zelle / 2
    return (gelaende.x0 - halb, gelaende.y0 - halb,
            gelaende.x0 + (gelaende.spalten - 1) * gelaende.zelle + halb,
            gelaende.y0 + (gelaende.zeilen - 1) * gelaende.zelle + halb)


def gelaende_bild(gelaende, palette, ebene=None):
    """Ein Pixel je Knoten, Zeile 0 oben (die y-Achse der Sicht zeigt nach oben).

    Hoehe heller nach oben (zwischen `flaeche` und `gedaempft`), Hoehenlinie
    alle HOEHENLINIE_M in `gedaempft`, ohne Boden durchsichtig; mit `ebene`
    werden Knoten ausserhalb EBENE_TOLERANZ_M blass. Einmal je Raum gerechnet,
    die Sicht zeichnet das Bild skaliert.
    """
    bild = QImage(gelaende.spalten, gelaende.zeilen, QImage.Format_ARGB32)
    bild.fill(QColor(0, 0, 0, 0))
    werte = [h for h in gelaende.hoehen if h is not None]
    if not werte:
        return bild
    h_min, spanne = min(werte), max(werte) - min(werte)
    for i in range(gelaende.zeilen):
        for j in range(gelaende.spalten):
            h = gelaende.knoten(i, j)
            if h is None:
                continue
            if ebene is not None and abs(h - ebene) > EBENE_TOLERANZ_M:
                farbe = QColor(palette.blass)
            else:
                stufe = math.floor(h / HOEHENLINIE_M + 1e-9)
                linie = any(
                    n is not None and math.floor(n / HOEHENLINIE_M + 1e-9) != stufe
                    for n in (gelaende.knoten(i, j + 1), gelaende.knoten(i + 1, j))
                )
                if linie:
                    farbe = QColor(palette.gedaempft)
                else:
                    t = 0.0 if spanne <= 0 else (h - h_min) / spanne
                    farbe = QColor(mische(palette.flaeche, palette.gedaempft, 0.15 + 0.45 * t))
            farbe.setAlpha(GELAENDE_ALPHA)
            bild.setPixelColor(j, gelaende.zeilen - 1 - i, farbe)
    return bild
