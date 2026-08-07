"""Draufsicht auf eine Karte.

Gezeichnet mit QPainter — dieselbe Überlegung wie bei der Tempo-Kurve: das
SDK-Beispiel graph_nav_view_map braucht VTK, eine 3D-Rendering-Bibliothek von
rund hundert Megabyte, um Punkte und Linien zu zeichnen. Auf zwanzig
Schullaptops steht das in keinem Verhältnis.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from spotlab.gui.theme import DUNKEL
from spotlab.maps.geometry import Grundriss

RAND = 30
PUNKT_R = 4


class MapPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.grundriss = Grundriss([], [], "leer", "Keine Karte gewählt.")
        self.palette_ = DUNKEL

    def setze_grundriss(self, grundriss, palette=None):
        self.grundriss = grundriss
        if palette is not None:
            self.palette_ = palette
        self.update()

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

        x_werte = [p.x for p in punkte]
        y_werte = [p.y for p in punkte]
        spanne_x = max(max(x_werte) - min(x_werte), 1e-6)
        spanne_y = max(max(y_werte) - min(y_werte), 1e-6)
        # Massstab gemeinsam, damit die Karte nicht verzerrt
        massstab = min(breite / spanne_x, hoehe / spanne_y) * 0.9
        mitte_x = (max(x_werte) + min(x_werte)) / 2
        mitte_y = (max(y_werte) + min(y_werte)) / 2

        def auf_schirm(punkt):
            return (
                int(RAND + breite / 2 + (punkt.x - mitte_x) * massstab),
                # y nach oben: Bildschirmkoordinaten laufen andersherum
                int(RAND + hoehe / 2 - (punkt.y - mitte_y) * massstab),
            )

        lage = {p.id: auf_schirm(p) for p in punkte}

        maler.setPen(QPen(QColor(self.palette_.gedaempft), 1))
        for von, nach in self.grundriss.kanten:
            if von in lage and nach in lage:
                maler.drawLine(*lage[von], *lage[nach])

        for punkt in punkte:
            x, y = lage[punkt.id]
            benannt = bool(punkt.name)
            maler.setPen(
                QPen(QColor(self.palette_.ok if benannt else self.palette_.akzent), 2)
            )
            maler.drawEllipse(x - PUNKT_R, y - PUNKT_R, 2 * PUNKT_R, 2 * PUNKT_R)
            if benannt:
                maler.setPen(QColor(self.palette_.text))
                maler.drawText(x + PUNKT_R + 3, y - PUNKT_R, punkt.name)

        maler.setPen(QColor(self.palette_.gedaempft))
        maler.drawText(
            RAND, RAND - 10,
            f"{len(punkte)} Wegpunkte · Quelle: {self.grundriss.quelle}"
        )
