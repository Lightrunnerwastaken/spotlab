"""Navigation links — dieselbe Anordnung wie VS Code, das die Schüler daneben offen haben."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QPushButton, QVBoxLayout, QWidget

EINTRAEGE = (
    ("projekte", "Projekte"),
    ("code", "Code"),
    ("live", "Live-Lauf"),
    ("laeufe", "Läufe"),
    ("karten", "Karten"),
    ("umwelt", "Umwelt"),
    ("uebungsraum", "Übungsraum"),
    ("anbindungen", "Anbindungen"),
    ("spot", "Spot"),
)


class Sidebar(QWidget):
    gewaehlt = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(150)
        self.knoepfe = {}
        gruppe = QButtonGroup(self)
        gruppe.setExclusive(True)

        anordnung = QVBoxLayout(self)
        anordnung.setContentsMargins(8, 12, 8, 12)
        anordnung.setSpacing(2)
        for schluessel, beschriftung in EINTRAEGE:
            knopf = QPushButton(beschriftung)
            knopf.setObjectName("Navi")
            knopf.setCheckable(True)
            knopf.clicked.connect(lambda _=False, s=schluessel: self.gewaehlt.emit(s))
            gruppe.addButton(knopf)
            anordnung.addWidget(knopf)
            self.knoepfe[schluessel] = knopf
        anordnung.addStretch(1)
        self.knoepfe["projekte"].setChecked(True)

    def waehle(self, schluessel):
        self.knoepfe[schluessel].setChecked(True)
