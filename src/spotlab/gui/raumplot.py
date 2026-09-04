"""Draufsicht auf den Uebungsraum: Waende, Hindernisse, Tags, Spur, Spot.

Gezeichnet mit QPainter, wie mapplot.py -- jenes zeichnet GraphNav-Grundrisse
und hat mit Raumgeometrie nichts gemein ausser der Technik.

Importiert `welt.raum` (reine Standardbibliothek), aber weder bosdyn noch
`spotlab.backends`: die Regel aus CLAUDE.md gilt auch hier.
"""

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

RAND = 16
SPOT_R_M = 0.35


class RaumPlot(QWidget):
    start_gewaehlt = Signal(float, float)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self._p = palette
        self._raum = None
        self._spur = []
        self._anstoesse = []
        self._start = None
        # Blickrichtung in Grad. Frueher las paintEvent sie fest aus `_start` --
        # ein `move(turn=90)` war in der Zeichnung dadurch nicht zu sehen.
        self._blick = 0.0

    # ------------------------------------------------------------- Fuellen

    def setze_raum(self, raum):
        self._raum = raum
        self.update()

    def setze_spur(self, punkte):
        self._spur = list(punkte)
        self.update()

    def setze_anstoesse(self, punkte):
        self._anstoesse = list(punkte)
        self.update()

    def setze_start(self, pose):
        # Ein neuer Start heisst: neuer Lauf. Die alte Spur stehenzulassen
        # zeigte zwei Fahrten uebereinander.
        self._start = pose
        self._spur = [(pose[0], pose[1])] if pose else []
        self._blick = pose[2] if pose else 0.0
        self.update()

    def haenge_pose_an(self, x, y, grad=None):
        """Eine gemessene Pose anfuegen -- der Weg fuer den laufenden Lauf."""
        self._spur.append((x, y))
        if grad is not None:
            self._blick = grad
        self.update()

    # ------------------------------------------------------------- Auskunft

    def raum(self):
        return self._raum

    def start(self):
        return self._start

    def spur(self):
        return list(self._spur)

    def anstoesse(self):
        return list(self._anstoesse)

    def blick(self):
        return self._blick

    # --------------------------------------------------------- Umrechnung

    def _massstab(self):
        """Pixel je Meter, Seitenverhaeltnis erhalten."""
        if self._raum is None:
            return 1.0, RAND, self.height() - RAND
        breite, hoehe = self._raum.groesse
        nutzbar_x = max(self.width() - 2 * RAND, 1)
        nutzbar_y = max(self.height() - 2 * RAND, 1)
        skala = min(nutzbar_x / max(breite, 1e-6), nutzbar_y / max(hoehe, 1e-6))
        # Zentriert, und y wird gespiegelt: im Raum waechst y nach oben.
        links = (self.width() - breite * skala) / 2
        unten = (self.height() + hoehe * skala) / 2
        return skala, links, unten

    def meter_zu_schirm(self, x, y):
        skala, links, unten = self._massstab()
        return links + x * skala, unten - y * skala

    def schirm_zu_meter(self, px, py):
        skala, links, unten = self._massstab()
        return (px - links) / skala, (unten - py) / skala

    # ------------------------------------------------------------ Zeichnen

    def mousePressEvent(self, ereignis):
        if self._raum is None:
            return
        punkt = ereignis.position() if hasattr(ereignis, "position") else ereignis.pos()
        x, y = self.schirm_zu_meter(punkt.x(), punkt.y())
        self.start_gewaehlt.emit(x, y)

    def paintEvent(self, _ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        maler.fillRect(self.rect(), QColor(self._p.hintergrund))
        if self._raum is None:
            maler.setPen(QColor(self._p.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Kein Raum gewählt.")
            return

        skala, _links, _unten = self._massstab()

        maler.setPen(Qt.NoPen)
        maler.setBrush(QBrush(QColor(self._p.flaeche)))
        for hindernis in self._raum.hindernisse:
            hx, hy, breite, hoehe = hindernis.rechteck
            ecke = self.meter_zu_schirm(hx, hy + hoehe)
            maler.drawRect(int(ecke[0]), int(ecke[1]),
                           int(breite * skala), int(hoehe * skala))

        maler.setPen(QPen(QColor(self._p.text), 2))
        for x1, y1, x2, y2 in self._raum.waende:
            a = self.meter_zu_schirm(x1, y1)
            b = self.meter_zu_schirm(x2, y2)
            maler.drawLine(QPointF(*a), QPointF(*b))

        if len(self._spur) > 1:
            maler.setPen(QPen(QColor(self._p.akzent), 2, Qt.DotLine))
            for erster, zweiter in zip(self._spur, self._spur[1:]):
                maler.drawLine(QPointF(*self.meter_zu_schirm(*erster)),
                               QPointF(*self.meter_zu_schirm(*zweiter)))

        maler.setPen(QPen(QColor(self._p.zahl), 2))
        maler.setBrush(Qt.NoBrush)
        for tag in self._raum.tags:
            px, py = self.meter_zu_schirm(tag.x, tag.y)
            maler.drawRect(int(px) - 6, int(py) - 6, 12, 12)
            maler.drawText(int(px) + 9, int(py) + 4, str(tag.id))

        maler.setPen(QPen(QColor(self._p.gefahr), 2))
        for x, y in self._anstoesse:
            px, py = self.meter_zu_schirm(x, y)
            maler.drawLine(int(px) - 5, int(py) - 5, int(px) + 5, int(py) + 5)
            maler.drawLine(int(px) - 5, int(py) + 5, int(px) + 5, int(py) - 5)

        pose = self._spur[-1] if self._spur else None
        blick = self._blick
        if pose is None and self._start is not None:
            pose = (self._start[0], self._start[1])
        if pose is not None:
            px, py = self.meter_zu_schirm(pose[0], pose[1])
            r = max(4.0, SPOT_R_M * skala)
            maler.setPen(QPen(QColor(self._p.funktion), 2))
            maler.setBrush(Qt.NoBrush)
            maler.drawEllipse(QPointF(px, py), r, r)
            maler.drawLine(QPointF(px, py), QPointF(
                px + r * math.cos(math.radians(blick)),
                py - r * math.sin(math.radians(blick)),
            ))
