"""Das Tastenfeld: welche Fahrtasten gedrückt sind, welche Tempostufe gilt, ob die
Tastatur gerade fährt.

Für den Tab „Fahren“ (echter Spot) und das Übungsfenster (Fahrmodus). Vor dem
23.09.2026 stand die Belegung in 10 px, und „Tasten sind scharf“ wurde von der
ersten Positionszeile überschrieben -- am echten Roboter sah man nicht mehr,
dass die Tastatur fährt.

Keine Farben im Code: die Kappen sind QLabels mit `objectName` und einer
dynamischen Eigenschaft; wie sie aussehen, sagt das Stylesheet (`theme.py`,
`QLabel#Taste[gedrueckt="true"]`, `QLabel#Stufe[aktiv="true"]`).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from spotlab.record import fahrt

# (Name, Aufschrift, was sie tut) -- die Belegung selbst steht in record/fahrt.py.
TASTEN = (
    ("q", "Q", "links drehen"), ("w", "W", "vor"), ("e", "E", "rechts drehen"),
    ("a", "A", "nach links"), ("s", "S", "zurück"), ("d", "D", "nach rechts"),
)
AKTIV = "● Tasten fahren"
AUS = "○ Tasten aus"


def _neu_zeichnen(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Tastenfeld(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Flaeche")
        self._kappen = {}
        gitter = QGridLayout()
        gitter.setSpacing(6)
        for nummer, (name, aufschrift, bedeutung) in enumerate(TASTEN):
            kappe = QLabel(aufschrift)
            kappe.setObjectName("Taste")
            kappe.setAlignment(Qt.AlignCenter)
            kappe.setFixedSize(40, 36)
            kappe.setToolTip(f"{aufschrift}: {bedeutung}")
            kappe.setProperty("gedrueckt", False)
            self._kappen[name] = kappe
            gitter.addWidget(kappe, nummer // 3, nummer % 3)

        self._stufen = {}
        stufen = QHBoxLayout()
        stufen.setSpacing(4)
        for ziffer, (name, faktor) in enumerate(fahrt.STUFEN, start=1):
            marke = QLabel(f"{ziffer} {name}")
            marke.setObjectName("Stufe")
            marke.setToolTip(f"Taste {ziffer}: {fahrt.TEMPO_M_S * faktor:.1f} m/s")
            marke.setProperty("aktiv", False)
            self._stufen[name] = marke
            stufen.addWidget(marke)
        self._stufe = None

        self._zustand = QLabel(AUS)
        self._zustand.setObjectName("Gedaempft")
        halt = QLabel("Leertaste oder Esc hält")
        halt.setObjectName("Kachelname")

        anordnung = QVBoxLayout(self)
        anordnung.setContentsMargins(12, 10, 12, 10)
        anordnung.addWidget(self._zustand)
        anordnung.addLayout(gitter)
        anordnung.addLayout(stufen)
        anordnung.addWidget(halt)

    # ------------------------------------------------------------- Anzeige

    def zeige_tasten(self, namen):
        for name, kappe in self._kappen.items():
            an = name in namen
            if kappe.property("gedrueckt") != an:
                kappe.setProperty("gedrueckt", an)
                _neu_zeichnen(kappe)

    def zeige_stufe(self, name):
        self._stufe = name
        for stufe, marke in self._stufen.items():
            an = stufe == name
            if marke.property("aktiv") != an:
                marke.setProperty("aktiv", an)
                _neu_zeichnen(marke)

    def zeige_aktiv(self, an):
        self._zustand.setText(AKTIV if an else AUS)
        self._zustand.setObjectName("Ok" if an else "Gedaempft")
        _neu_zeichnen(self._zustand)
        if not an:
            self.zeige_tasten(set())

    # ------------------------------------------------------------- Abfrage

    def gedrueckt(self):
        return {name for name, kappe in self._kappen.items() if kappe.property("gedrueckt")}

    def stufe(self):
        return self._stufe

    def aktiv(self):
        return self._zustand.text() == AKTIV
