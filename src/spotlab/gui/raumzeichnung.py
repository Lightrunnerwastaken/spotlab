"""Raeume zeichnen -- einmal, fuer Raumeditor und Uebungsfenster.

QPainter wie ueberall. Farben nur aus dem Theme. Die Umrechnung Meter -> Pixel
bringt der Aufrufer mit (`meter_zu_schirm`), weil Editor und Uebungsfenster
verschieden zoomen; `skala` sind Pixel je Meter fuer Radien und Dicken.
Zwei Zeichner, die die Drehung getrennt lernten, wichen voneinander ab, ohne
dass es auffiele -- deshalb gibt es genau einen.
"""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF

from spotlab.welt.kollision import ROBOTER_RADIUS_M

TAG_KANTE_M = 0.15
PFEIL_M = 0.4


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


def zeichne_raum(maler, raum, meter_zu_schirm, skala, palette, auswahl=frozenset()):
    """Waende, Bloecke, Tags. Die Auswahl in Akzentfarbe."""
    for i, block in enumerate(raum.bloecke):
        gewaehlt = ("block", i) in auswahl
        maler.setPen(QPen(QColor(palette.akzent if gewaehlt else palette.rand), 2))
        maler.setBrush(QBrush(QColor(palette.flaeche)))
        maler.drawPolygon(_polygon(block.ecken(), meter_zu_schirm))
        px, py = meter_zu_schirm(block.x, block.y)
        maler.setPen(QColor(palette.gedaempft))
        maler.drawText(int(px) + 4, int(py) - 4, block.name)

    for i, wand in enumerate(raum.waende):
        gewaehlt = ("wand", i) in auswahl
        farbe = QColor(palette.akzent if gewaehlt else palette.text)
        maler.setPen(QPen(farbe, 1))
        maler.setBrush(QBrush(farbe))
        # Mindestens zwei Pixel breit, sonst verschwindet eine Wand beim Herauszoomen.
        dicke = max(raum.wand_dicke, 2.0 / max(skala, 1e-6))
        maler.drawPolygon(_polygon(wand_polygon(wand, dicke), meter_zu_schirm))

    maler.setBrush(Qt.NoBrush)
    for i, tag in enumerate(raum.tags):
        gewaehlt = ("tag", i) in auswahl
        maler.setPen(QPen(QColor(palette.akzent if gewaehlt else palette.zahl), 2))
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
