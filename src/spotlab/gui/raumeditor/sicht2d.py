"""Die 2D-Sicht des Raumeditors: zeichnen, zoomen, schwenken -- und Ereignisse
in METERN an die Steuerung melden.

Kein Modell, keine Regeln: was ein Klick bedeutet, entscheidet `steuerung.py`.
Farben nur aus dem Theme.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from spotlab.gui.raumzeichnung import (
    zeichne_anstoesse,
    zeichne_raum,
    zeichne_spot,
    zeichne_spur,
)
from spotlab.welt.raum import huelle

RAND = 24
GRIFF_PX = 5
TOLERANZ_PX = 8
FEINES_RASTER_AB = 100.0          # Pixel je Meter, ab da 5-cm-Linien

TASTEN = {
    Qt.Key_Return: "return", Qt.Key_Enter: "return", Qt.Key_Escape: "escape",
    Qt.Key_Delete: "delete", Qt.Key_Backspace: "backspace", Qt.Key_Period: ".",
    Qt.Key_Comma: ".", Qt.Key_Minus: "-", Qt.Key_Tab: "tab",
}


class Sicht2D(QWidget):
    gedrueckt = Signal(float, float, str, bool, bool)      # x, y, "links"/"rechts", shift, ctrl
    bewegt = Signal(float, float, bool)                    # x, y, ctrl
    losgelassen = Signal(float, float, bool, bool)         # x, y, shift, ctrl
    taste_gedrueckt = Signal(str, bool, bool, bool)        # name, shift, ctrl, alt

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self._raum = None
        self._auswahl = frozenset()
        self._griffe = []
        self._rahmen = None
        self._kette = None
        self._zeiger = None
        self._spur = []
        self._anstoesse = []
        self._pauspapier = []
        self._ebene = None
        self._klippen = []
        self.skala = 60.0             # Pixel je Meter
        self._ursprung = (RAND, 0.0)  # Pixel des Weltpunkts (0, 0); y wird gespiegelt
        self._schwenk = None

    # ------------------------------------------------------------ Fuellen

    def zeige(self, raum, auswahl=frozenset(), griffe=(), rahmen=None, kette=None,
              ebene=None, klippen_=()):
        self._raum, self._auswahl = raum, frozenset(auswahl)
        self._griffe, self._rahmen, self._kette = list(griffe), rahmen, kette
        self._ebene, self._klippen = ebene, list(klippen_)
        self.update()

    def setze_spur(self, punkte):
        self._spur = list(punkte)
        self.update()

    def setze_anstoesse(self, punkte):
        self._anstoesse = list(punkte)
        self.update()

    def setze_pauspapier(self, punkte):
        self._pauspapier = list(punkte)
        self.update()

    # -------------------------------------------------------- Umrechnung

    def meter_zu_schirm(self, x, y):
        return self._ursprung[0] + x * self.skala, self._ursprung[1] - y * self.skala

    def schirm_zu_meter(self, px, py):
        return (px - self._ursprung[0]) / self.skala, (self._ursprung[1] - py) / self.skala

    def toleranz_m(self):
        return TOLERANZ_PX / self.skala

    def alles_zeigen(self):
        if self._raum is None:
            return
        x0, y0, x1, y1 = huelle(self._raum)
        breite, hoehe = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        self.skala = min(max(self.width() - 2 * RAND, 1) / breite,
                         max(self.height() - 2 * RAND, 1) / hoehe)
        self._ursprung = ((self.width() - breite * self.skala) / 2 - x0 * self.skala,
                          (self.height() + hoehe * self.skala) / 2 + y0 * self.skala)
        self.update()

    def zoome(self, faktor, px, py):
        """Um den Bildschirmpunkt (px, py) zoomen -- der Punkt darunter bleibt stehen."""
        x, y = self.schirm_zu_meter(px, py)
        self.skala = max(5.0, min(2000.0, self.skala * faktor))
        self._ursprung = (px - x * self.skala, py + y * self.skala)
        self.update()

    # ------------------------------------------------------- Ereignisse

    @staticmethod
    def _tasten(ereignis):
        m = ereignis.modifiers()
        return bool(m & Qt.ShiftModifier), bool(m & Qt.ControlModifier), bool(m & Qt.AltModifier)

    @staticmethod
    def _punkt(ereignis):
        p = ereignis.position()
        return p.x(), p.y()

    def mousePressEvent(self, ereignis):
        self.setFocus()
        px, py = self._punkt(ereignis)
        if ereignis.button() == Qt.MiddleButton:
            self._schwenk = (px, py)
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        taste = "rechts" if ereignis.button() == Qt.RightButton else "links"
        x, y = self.schirm_zu_meter(px, py)
        self.gedrueckt.emit(x, y, taste, shift, ctrl)

    def mouseMoveEvent(self, ereignis):
        px, py = self._punkt(ereignis)
        if self._schwenk is not None:
            dx, dy = px - self._schwenk[0], py - self._schwenk[1]
            self._ursprung = (self._ursprung[0] + dx, self._ursprung[1] + dy)
            self._schwenk = (px, py)
            self.update()
            return
        self._zeiger = (px, py)
        _shift, ctrl, _alt = self._tasten(ereignis)
        x, y = self.schirm_zu_meter(px, py)
        self.bewegt.emit(x, y, ctrl)
        if self._kette is not None:
            self.update()

    def mouseReleaseEvent(self, ereignis):
        if ereignis.button() == Qt.MiddleButton:
            self._schwenk = None
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        x, y = self.schirm_zu_meter(*self._punkt(ereignis))
        self.losgelassen.emit(x, y, shift, ctrl)

    def wheelEvent(self, ereignis):
        schritte = ereignis.angleDelta().y() / 120.0
        p = ereignis.position()
        self.zoome(1.15 ** schritte, p.x(), p.y())

    def keyPressEvent(self, ereignis):
        taste = ereignis.key()
        if taste == Qt.Key_Home:
            self.alles_zeigen()
            return
        shift, ctrl, alt = self._tasten(ereignis)
        if taste in TASTEN:
            name = TASTEN[taste]
        elif Qt.Key_0 <= taste <= Qt.Key_9:
            name = chr(taste)
        elif Qt.Key_A <= taste <= Qt.Key_Z:
            name = chr(taste).lower()
        else:
            super().keyPressEvent(ereignis)
            return
        self.taste_gedrueckt.emit(name, shift, ctrl, alt)

    # ---------------------------------------------------------- Zeichnen

    def _raster(self, maler):
        x0, y0 = self.schirm_zu_meter(0, self.height())
        x1, y1 = self.schirm_zu_meter(self.width(), 0)
        schritte = [1.0]
        if self.skala >= FEINES_RASTER_AB:
            schritte.insert(0, 0.05)
        for schritt in schritte:
            farbe = QColor(self._p.rand)
            if schritt < 1.0:
                farbe.setAlpha(70)
            maler.setPen(QPen(farbe, 1))
            k = math.floor(x0 / schritt)
            while k * schritt <= x1:
                px, _ = self.meter_zu_schirm(k * schritt, 0)
                maler.drawLine(QPointF(px, 0), QPointF(px, self.height()))
                k += 1
            k = math.floor(y0 / schritt)
            while k * schritt <= y1:
                _, py = self.meter_zu_schirm(0, k * schritt)
                maler.drawLine(QPointF(0, py), QPointF(self.width(), py))
                k += 1

    def paintEvent(self, _ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        maler.fillRect(self.rect(), QColor(self._p.hintergrund))
        if self._raum is None:
            maler.setPen(QColor(self._p.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Kein Raum geöffnet.")
            return
        self._raster(maler)

        if self._pauspapier:
            farbe = QColor(self._p.gedaempft)
            farbe.setAlpha(120)
            maler.setPen(QPen(farbe, 2))
            for x, y in self._pauspapier:
                maler.drawPoint(QPointF(*self.meter_zu_schirm(x, y)))

        zeichne_raum(maler, self._raum, self.meter_zu_schirm, self.skala, self._p, self._auswahl,
                     ebene=self._ebene, klippen_=self._klippen)
        zeichne_spur(maler, self._spur, self.meter_zu_schirm, self._p)
        zeichne_anstoesse(maler, self._anstoesse, self.meter_zu_schirm, self._p)
        sx, sy, sgrad = self._raum.start
        px, py = self.meter_zu_schirm(sx, sy)
        zeichne_spot(maler, px, py, sgrad, self.skala, self._p,
                     gewaehlt=("start",) in self._auswahl)

        maler.setPen(QPen(QColor(self._p.akzent), 1))
        maler.setBrush(QBrush(QColor(self._p.flaeche)))
        for _s, art, x, y in self._griffe:
            gx, gy = self.meter_zu_schirm(x, y)
            if art == "drehring":
                maler.drawEllipse(QPointF(gx, gy), GRIFF_PX + 1, GRIFF_PX + 1)
            else:
                maler.drawRect(QRectF(gx - GRIFF_PX, gy - GRIFF_PX, 2 * GRIFF_PX, 2 * GRIFF_PX))

        if self._rahmen is not None:
            x1, y1, x2, y2 = self._rahmen
            a, b_ = self.meter_zu_schirm(x1, y1), self.meter_zu_schirm(x2, y2)
            maler.setPen(QPen(QColor(self._p.akzent), 1, Qt.DashLine))
            maler.setBrush(Qt.NoBrush)
            maler.drawRect(QRectF(QPointF(*a), QPointF(*b_)).normalized())

        if self._kette is not None and self._zeiger is not None:
            maler.setPen(QPen(QColor(self._p.warnung), 2, Qt.DashLine))
            maler.drawLine(QPointF(*self.meter_zu_schirm(*self._kette)), QPointF(*self._zeiger))
