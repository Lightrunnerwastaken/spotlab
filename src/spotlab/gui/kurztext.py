"""Ein Label, das sich kürzt statt das Fenster zu verbreitern.

Ein QLabel ohne Umbruch verlangt so viel Breite wie sein Text. Ein langer
Pfad oder eine lange Meldung zog damit das ganze Hauptfenster auseinander --
auf einem Schul-Laptop mit 150 % Skalierung über den Bildschirmrand
(23.09.2026: ein Arbeitsordner-Pfad machte das Fenster 1229 px breit).
`Kurztext` zeigt, was Platz hat, mit „…“ an der gewählten Stelle; der volle
Text steht im Tooltip und bleibt über `text()` lesbar.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy, QStyle, QStyleOption


class Kurztext(QLabel):
    def __init__(self, text="", kuerzen=Qt.ElideRight, parent=None):
        super().__init__(text, parent)
        self._kuerzen = kuerzen
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self):
        hinweis = super().minimumSizeHint()
        hinweis.setWidth(40)
        return hinweis

    def paintEvent(self, _ereignis):
        maler = QPainter(self)
        # Hintergrund und Rand aus dem Stylesheet, wie ein gewoehnliches QLabel.
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PE_Widget, option, maler, self)
        rahmen = self.contentsRect()
        gekuerzt = self.fontMetrics().elidedText(self.text(), self._kuerzen, rahmen.width())
        maler.setPen(self.palette().color(self.foregroundRole()))
        maler.drawText(rahmen, int(self.alignment()), gekuerzt)
