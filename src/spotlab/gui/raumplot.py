"""Draufsicht auf den Uebungsraum: Waende, Hindernisse, Tags, Spur, Spot.

Gezeichnet mit QPainter, wie mapplot.py -- jenes zeichnet GraphNav-Grundrisse
und hat mit Raumgeometrie nichts gemein ausser der Technik.

Importiert `welt.raum` und `welt.kollision` (reine Standardbibliothek), aber
weder bosdyn noch `spotlab.backends`: die Regel aus CLAUDE.md gilt auch hier.
"""


from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from spotlab.gui.raumzeichnung import (
    zeichne_anstoesse,
    zeichne_raum,
    zeichne_spot,
    zeichne_spur,
)
from spotlab.welt.raum import huelle

RAND = 16


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
        # Ein neuer Start heisst: neuer Lauf, also leere Spur -- die alte
        # stehenzulassen zeigte zwei Fahrten uebereinander.
        #
        # Und die Spur faengt LEER an, nicht mit dem Startpunkt darin: der ist
        # eine Annahme der GUI, keine Messung. Weicht er vom echten Start ab,
        # zeichnet er einen Weg, den Spot nie gefahren ist. Der Kreis steht
        # trotzdem hier, bis die erste gemessene Pose kommt (siehe paintEvent).
        self._start = pose
        self._spur = []
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
        x0, y0, x1, y1 = huelle(self._raum)          # groesse oder die Huelle
        breite, hoehe = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        nutzbar_x = max(self.width() - 2 * RAND, 1)
        nutzbar_y = max(self.height() - 2 * RAND, 1)
        skala = min(nutzbar_x / breite, nutzbar_y / hoehe)
        # Zentriert, und y wird gespiegelt: im Raum waechst y nach oben.
        links = (self.width() - breite * skala) / 2 - x0 * skala
        unten = (self.height() + hoehe * skala) / 2 + y0 * skala
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
        zeichne_raum(maler, self._raum, self.meter_zu_schirm, skala, self._p)
        zeichne_spur(maler, self._spur, self.meter_zu_schirm, self._p)
        zeichne_anstoesse(maler, self._anstoesse, self.meter_zu_schirm, self._p)

        pose = self._spur[-1] if self._spur else None
        blick = self._blick
        if pose is None and self._start is not None:
            pose = (self._start[0], self._start[1])
        if pose is not None:
            px, py = self.meter_zu_schirm(pose[0], pose[1])
            zeichne_spot(maler, px, py, blick, skala, self._p)
