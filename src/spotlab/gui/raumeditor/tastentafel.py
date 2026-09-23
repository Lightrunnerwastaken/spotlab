"""Die Tafel aller Tasten des Raumeditors (F1 oder „Tasten ?").

Die Belegung selbst steht in `steuerung.py` (Blender-Tasten) und in den Sichten;
hier steht nur, was ein Mensch davon wissen muss -- als Daten (`TAFEL`, ohne Qt
pruefbar) und als Fenster. Bis zum 23.09.2026 standen die Tasten nirgends: G, R,
S, die Achsen, Zahl und Enter kannte nur, wer Blender kannte.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

TAFEL = (
    ("Auswählen und Zeichnen", (
        ("Klick", "wählt ein Element; Umschalt+Klick ergänzt oder nimmt heraus"),
        ("Ziehen im Leeren", "Rahmen: wählt alles, was darin liegt"),
        ("Griffe ziehen", "Wandenden, Ecken, Drehring, Blickrichtung"),
        ("Strg beim Ziehen", "ohne Raster (sonst 5 cm und 5°)"),
        ("Esc / Rechtsklick", "beendet eine Wandkette"),
        ("A  ·  Alt+A", "alles wählen  ·  nichts wählen"),
        ("Entf", "löscht die Auswahl (nicht in einem Eingabefeld)"),
    )),
    ("Bewegen wie in Blender", (
        ("G  ·  R  ·  S", "bewegen  ·  drehen  ·  skalieren — die Maus führt"),
        ("X / Y / Z", "nur entlang einer Achse; G, dann Z hebt die Auswahl"),
        ("Zahl, dann Enter", "genau: G X 1.5 Enter schiebt 1.5 m nach rechts"),
        ("Enter / Linksklick", "bestätigt"),
        ("Esc / Rechtsklick", "bricht ab, nichts ändert sich"),
        ("Umschalt+D", "verdoppelt die Auswahl und bewegt die Kopie"),
    )),
    ("Ansicht", (
        ("Mausrad", "zoomt um den Zeiger"),
        ("Mittlere Maustaste ziehen", "schwenkt"),
        ("Leertaste + Ziehen", "schwenkt (Touchpad)"),
        ("Rechts ziehen", "schwenkt; ein Rechtsklick ohne Ziehen bricht ab"),
        ("Pfeiltasten", "schwenken"),
        ("Home  ·  F", "alles zeigen  ·  die Auswahl einrahmen"),
        ("Tab", "zwischen 2D und 3D wechseln"),
        ("3D: rechts ziehen", "dreht die Kamera, mit Umschalt schwenkt sie"),
    )),
    ("Datei", (
        ("Strg+S", "speichern"),
        ("Strg+Z  ·  Strg+Y", "rückgängig  ·  wiederholen"),
        ("F1", "diese Tafel"),
    )),
)


class Tastentafel(QDialog):
    """Nicht modal: man kann sie offen lassen und daneben weiterarbeiten."""

    def __init__(self, eltern=None):
        super().__init__(eltern)
        self.setWindowTitle("Tasten im Raumeditor")
        self.setModal(False)
        spalten = QHBoxLayout()
        for haelfte in (TAFEL[:2], TAFEL[2:]):
            spalte = QVBoxLayout()
            for titel, zeilen in haelfte:
                kopf = QLabel(titel)
                kopf.setObjectName("Titel")
                spalte.addWidget(kopf)
                raster = QGridLayout()
                raster.setHorizontalSpacing(14)
                raster.setVerticalSpacing(4)
                for i, (taste, was) in enumerate(zeilen):
                    links = QLabel(f"<b>{taste}</b>")
                    links.setTextFormat(Qt.RichText)
                    rechts = QLabel(was)
                    rechts.setWordWrap(True)
                    raster.addWidget(links, i, 0, Qt.AlignTop)
                    raster.addWidget(rechts, i, 1)
                raster.setColumnStretch(1, 1)
                spalte.addLayout(raster)
                spalte.addSpacing(10)
            spalte.addStretch(1)
            spalten.addLayout(spalte, 1)
        zu = QPushButton("Schliessen")
        zu.clicked.connect(self.close)
        unten = QHBoxLayout()
        unten.addStretch(1)
        unten.addWidget(zu)
        aussen = QVBoxLayout(self)
        aussen.addLayout(spalten)
        aussen.addLayout(unten)
        self.resize(820, 470)
