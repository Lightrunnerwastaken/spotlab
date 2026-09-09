"""Draufsicht auf eine Karte — und die Wegpunkte darin sind anklickbar.

Gezeichnet mit QPainter — dieselbe Überlegung wie bei der Tempo-Kurve: das
SDK-Beispiel graph_nav_view_map braucht VTK, eine 3D-Rendering-Bibliothek von
rund hundert Megabyte, um Punkte und Linien zu zeichnen. Auf zwanzig
Schullaptops steht das in keinem Verhältnis.

Ein Klick nahe einem Wegpunkt (`TREFFER_PX`) meldet dessen Kennung
(`wegpunkt_geklickt`); was damit geschieht, entscheidet die Ansicht. Für die
Navigation zeichnet der Plot dazu das Ziel (Ring), den Wegpunkt, an dem Spot
verortet ist (gefüllt), und den Roboter selbst (Pfeil in Blickrichtung) — alle
drei setzt die Ansicht aus `navigation.json`, der Plot rechnet nichts nach.
"""

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from spotlab.gui.theme import DUNKEL
from spotlab.maps.geometry import Grundriss

RAND = 30
PUNKT_R = 4
ZIEL_R = PUNKT_R + 5
ROBOTER_PX = 9
TREFFER_PX = 12          # so nah muss ein Klick an einem Wegpunkt liegen


class MapPlot(QWidget):
    wegpunkt_geklickt = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.grundriss = Grundriss([], [], "leer", "Keine Karte gewählt.")
        self.palette_ = DUNKEL
        self._ziel = None
        self._standort = None
        self._roboter = None

    def setze_grundriss(self, grundriss, palette=None):
        self.grundriss = grundriss
        if palette is not None:
            self.palette_ = palette
        # Eine andere Karte: Ziel, Standort und Roboter gehoerten zur alten.
        self._ziel = self._standort = self._roboter = None
        self.update()

    # ----------------------------------------------------------- Navigation

    @property
    def ziel(self):
        return self._ziel

    @property
    def standort(self):
        return self._standort

    @property
    def roboter(self):
        return self._roboter

    def setze_ziel(self, kennung):
        self._ziel = kennung or None
        self.update()

    def setze_standort(self, kennung):
        self._standort = kennung or None
        self.update()

    def setze_roboter(self, lage):
        """(x, y, grad) im Grundriss -- oder None."""
        self._roboter = tuple(lage) if lage is not None else None
        self.update()

    def leere_navigation(self):
        self._ziel = self._standort = self._roboter = None
        self.update()

    # ------------------------------------------------------------ Projektion

    def _projektion(self):
        """(Kennung -> Schirmpunkt, Meter -> Schirmpunkt) fuer die aktuelle Groesse."""
        punkte = self.grundriss.punkte
        breite = max(self.width() - 2 * RAND, 1)
        hoehe = max(self.height() - 2 * RAND, 1)
        if not punkte:
            return {}, None
        x_werte = [p.x for p in punkte]
        y_werte = [p.y for p in punkte]
        spanne_x = max(max(x_werte) - min(x_werte), 1e-6)
        spanne_y = max(max(y_werte) - min(y_werte), 1e-6)
        # Massstab gemeinsam, damit die Karte nicht verzerrt
        massstab = min(breite / spanne_x, hoehe / spanne_y) * 0.9
        mitte_x = (max(x_werte) + min(x_werte)) / 2
        mitte_y = (max(y_werte) + min(y_werte)) / 2

        def auf_schirm(x, y):
            return (
                int(RAND + breite / 2 + (x - mitte_x) * massstab),
                # y nach oben: Bildschirmkoordinaten laufen andersherum
                int(RAND + hoehe / 2 - (y - mitte_y) * massstab),
            )

        return {p.id: auf_schirm(p.x, p.y) for p in punkte}, auf_schirm

    def lagen_auf_schirm(self):
        """Kennung -> (x, y) in Pixeln, so wie gerade gezeichnet."""
        return self._projektion()[0]

    def wegpunkt_bei(self, x_px, y_px):
        """Die Kennung des Wegpunkts unter dem Punkt -- oder None."""
        beste, abstand = None, TREFFER_PX
        for kennung, (x, y) in self._projektion()[0].items():
            d = math.hypot(x - x_px, y - y_px)
            if d <= abstand:
                beste, abstand = kennung, d
        return beste

    def mousePressEvent(self, ereignis):
        if ereignis.button() == Qt.LeftButton:
            lage = ereignis.position()
            kennung = self.wegpunkt_bei(lage.x(), lage.y())
            if kennung is not None:
                self.wegpunkt_geklickt.emit(kennung)
                ereignis.accept()
                return
        super().mousePressEvent(ereignis)

    # ------------------------------------------------------------- Zeichnen

    def paintEvent(self, ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        breite = max(self.width() - 2 * RAND, 1)
        hoehe = max(self.height() - 2 * RAND, 1)

        maler.setPen(QPen(QColor(self.palette_.rand), 1))
        maler.drawRect(RAND, RAND, breite, hoehe)

        punkte = self.grundriss.punkte
        if not punkte:
            maler.setPen(QColor(self.palette_.gedaempft))
            maler.drawText(
                self.rect(), Qt.AlignCenter,
                self.grundriss.hinweis or "Keine Wegpunkte."
            )
            return

        lage, auf_schirm = self._projektion()

        maler.setPen(QPen(QColor(self.palette_.gedaempft), 1))
        for von, nach in self.grundriss.kanten:
            if von in lage and nach in lage:
                maler.drawLine(*lage[von], *lage[nach])

        for punkt in punkte:
            x, y = lage[punkt.id]
            benannt = bool(punkt.name)
            farbe = QColor(self.palette_.ok if benannt else self.palette_.akzent)
            maler.setPen(QPen(farbe, 2))
            # Der Wegpunkt, an dem Spot verortet ist: gefuellt.
            maler.setBrush(QBrush(farbe) if punkt.id == self._standort else Qt.NoBrush)
            maler.drawEllipse(x - PUNKT_R, y - PUNKT_R, 2 * PUNKT_R, 2 * PUNKT_R)
            maler.setBrush(Qt.NoBrush)
            if benannt:
                maler.setPen(QColor(self.palette_.text))
                maler.drawText(x + PUNKT_R + 3, y - PUNKT_R, punkt.name)

        if self._ziel in lage:
            x, y = lage[self._ziel]
            maler.setPen(QPen(QColor(self.palette_.warnung), 2))
            maler.drawEllipse(x - ZIEL_R, y - ZIEL_R, 2 * ZIEL_R, 2 * ZIEL_R)
            maler.drawText(x + ZIEL_R + 3, y + ZIEL_R + 4, "Ziel")

        if self._roboter is not None:
            rx, ry, grad = self._roboter
            x, y = auf_schirm(rx, ry)
            w = math.radians(grad)
            vorn = (math.cos(w), -math.sin(w))          # Schirm-y laeuft nach unten
            quer = (math.sin(w), math.cos(w))
            spitze = QPointF(x + vorn[0] * ROBOTER_PX, y + vorn[1] * ROBOTER_PX)
            links = QPointF(x - vorn[0] * ROBOTER_PX * 0.6 + quer[0] * ROBOTER_PX * 0.55,
                            y - vorn[1] * ROBOTER_PX * 0.6 + quer[1] * ROBOTER_PX * 0.55)
            rechts = QPointF(x - vorn[0] * ROBOTER_PX * 0.6 - quer[0] * ROBOTER_PX * 0.55,
                             y - vorn[1] * ROBOTER_PX * 0.6 - quer[1] * ROBOTER_PX * 0.55)
            maler.setPen(QPen(QColor(self.palette_.text), 1))
            maler.setBrush(QBrush(QColor(self.palette_.akzent)))
            maler.drawPolygon(QPolygonF([spitze, links, rechts]))
            maler.setBrush(Qt.NoBrush)

        maler.setPen(QColor(self.palette_.gedaempft))
        maler.drawText(
            RAND, RAND - 10,
            f"{len(punkte)} Wegpunkte · Quelle: {self.grundriss.quelle}"
        )
