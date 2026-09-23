"""Zwei Paletten, hell und dunkel.

Bewusst Qt-frei: das Auslesen der Windows-Einstellung braucht Qt und liegt in
app.py. Nur so bleibt die Palettenwahl ohne Fenster prüfbar — und nur so
lassen sich Farbliterale im Widget-Code verhindern, denn die einzige Quelle
für Farben ist dieses Modul.
"""

from dataclasses import dataclass
from pathlib import Path

# Das Häkchen der Kästchen. Ein Bild, weil Qt-Stylesheets kein Häkchen
# zeichnen; weiss auf Akzent, in beiden Themen gleich.
HAKEN = (Path(__file__).resolve().parent / "bilder" / "haken.svg").as_posix()


@dataclass(frozen=True)
class Palette:
    hintergrund: str
    flaeche: str
    rand: str
    text: str
    gedaempft: str
    akzent: str
    # Aktive Flächen (gedrückte Werkzeuge, Auswahl in Listen): der Akzent,
    # stark zurückgenommen -- sichtbar, ohne zu schreien.
    akzent_flaeche: str
    # Schrift auf einem Knopf in Akzentfarbe (der Hauptknopf einer Ansicht).
    auf_akzent: str
    ok: str
    warnung: str
    gefahr: str
    # Elemente auf einer ANDEREN Ebene des Raumeditors: sichtbar, aber blass,
    # damit man beim Setzen einer Treppe sieht, wo sie oben ankommt.
    blass: str
    # Syntaxhervorhebung. Angewendet werden sie ueber QTextCharFormat, nicht
    # ueber das Stylesheet — deshalb tauchen sie unten nicht noch einmal auf.
    schluesselwort: str
    zeichenkette: str
    kommentar: str
    zahl: str
    funktion: str


DUNKEL = Palette(
    hintergrund="#1e1f22",
    flaeche="#26282c",
    rand="#34373d",
    text="#d7dae0",
    gedaempft="#868d97",
    akzent="#579dff",
    akzent_flaeche="#1f3354",
    auf_akzent="#ffffff",
    ok="#3fb950",
    warnung="#d29922",
    gefahr="#e5484d",
    blass="#3a3f4a",
    schluesselwort="#c678dd",
    zeichenkette="#98c379",
    kommentar="#7f848e",
    zahl="#d19a66",
    funktion="#61afef",
)

HELL = Palette(
    hintergrund="#f4f5f7",
    flaeche="#ffffff",
    rand="#dfe1e6",
    text="#1f2328",
    gedaempft="#6b7280",
    akzent="#0b5cd5",
    akzent_flaeche="#e2ecfb",
    auf_akzent="#ffffff",
    ok="#1a7f37",
    warnung="#9a6700",
    gefahr="#d1372f",
    blass="#d0d4da",
    schluesselwort="#a626a4",
    zeichenkette="#2a7d3f",
    kommentar="#8a9099",
    zahl="#97600a",
    funktion="#2f5fd0",
)


def palette_fuer(dunkel):
    return DUNKEL if dunkel else HELL


def mische(a, b, t):
    """Die Farbe zwischen zwei Palettenfarben: t = 0 ist a, t = 1 ist b.

    Die einzige Stelle, die Farben mischt -- das Gelaende faerbt seine Hoehen
    damit, ohne eigene Farbwerte zu kennen.
    """
    t = min(1.0, max(0.0, float(t)))

    def kanal(k):
        return round(int(a[k:k + 2], 16) * (1 - t) + int(b[k:k + 2], 16) * t)

    return f"#{kanal(1):02x}{kanal(3):02x}{kanal(5):02x}"


def stylesheet(p):
    """Qt-Stylesheet aus der Palette. Einzige Stelle mit Farbwerten im Programm."""
    return f"""
QWidget {{
    background: {p.hintergrund};
    color: {p.text};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}
QFrame#Flaeche, QListWidget, QTableWidget, QPlainTextEdit, QLineEdit, QDoubleSpinBox,
QSpinBox {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 8px;
}}
QLineEdit, QDoubleSpinBox, QSpinBox {{ padding: 6px 8px; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus {{ border-color: {p.akzent}; }}
QListWidget::item, QTableWidget::item {{ padding: 3px 4px; }}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: {p.akzent_flaeche};
    color: {p.text};
}}
QListWidget::item:hover {{ background: {p.rand}; }}
QLabel#Gedaempft {{ color: {p.gedaempft}; }}
QLabel#Statuszeile {{
    color: {p.gedaempft};
    border-top: 1px solid {p.rand};
    padding: 5px 14px 6px 14px;
}}
QLabel#Titel {{ font-size: 16px; font-weight: 600; }}
QLabel#Kachelwert {{ font-family: Consolas, monospace; font-size: 17px; font-weight: 600; }}
QLabel#Kachelname {{ color: {p.gedaempft}; font-size: 10px; }}
QLabel#Ok {{ color: {p.ok}; }}
QLabel#Warnung {{ color: {p.warnung}; }}
QLabel#Gefahr {{ color: {p.gefahr}; }}
QPushButton {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 7px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {p.akzent}; }}
QPushButton:pressed {{ background: {p.rand}; }}
QPushButton:checked {{
    background: {p.akzent_flaeche};
    border-color: {p.akzent};
    font-weight: 600;
}}
QPushButton:disabled {{ color: {p.gedaempft}; border-color: {p.rand}; }}
QPushButton#Primaer {{
    background: {p.akzent};
    color: {p.auf_akzent};
    border: 1px solid {p.akzent};
    font-weight: 600;
}}
QPushButton#Primaer:hover {{ border-color: {p.text}; }}
QPushButton#Primaer:disabled {{
    background: {p.rand};
    color: {p.gedaempft};
    border-color: {p.rand};
}}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox:disabled {{ color: {p.gedaempft}; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {p.gedaempft};
    border-radius: 4px;
    background: {p.flaeche};
}}
QCheckBox::indicator:hover {{ border-color: {p.akzent}; }}
QCheckBox::indicator:checked {{
    background: {p.akzent};
    border-color: {p.akzent};
    image: url("{HAKEN}");
}}
QCheckBox::indicator:disabled {{ background: {p.hintergrund}; border-color: {p.rand}; }}
QCheckBox::indicator:checked:disabled {{ background: {p.rand}; }}
QPushButton#Notaus {{
    background: {p.gefahr};
    color: {p.flaeche};
    border: none;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 10px 20px;
}}
QPushButton#Navi {{
    background: transparent;
    border: none;
    text-align: left;
    padding: 8px 10px;
}}
QPushButton#Navi:checked {{ background: {p.rand}; font-weight: 600; }}
QHeaderView::section {{
    background: {p.flaeche};
    color: {p.gedaempft};
    border: none;
    border-bottom: 1px solid {p.rand};
    padding: 6px;
}}
QTableWidget {{ gridline-color: {p.rand}; }}
QPlainTextEdit {{ font-family: Consolas, monospace; font-size: 12px; }}
QTreeView {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 8px;
}}
QTreeView::item {{ padding: 3px 2px; }}
QTreeView::item:selected {{ background: {p.rand}; color: {p.text}; }}
QTabWidget::pane {{ border: 1px solid {p.rand}; border-radius: 8px; }}
QTabBar::tab {{
    background: transparent;
    color: {p.gedaempft};
    padding: 6px 12px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.akzent}; }}
QComboBox {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 7px;
    padding: 5px 8px;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    selection-background-color: {p.akzent_flaeche};
    selection-color: {p.text};
    outline: none;
}}
QSplitter::handle {{ background: {p.rand}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.rand}; border-radius: 3px; min-height: 28px; }}
QScrollBar::handle:horizontal {{ background: {p.rand}; border-radius: 3px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {p.gedaempft}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QToolTip {{
    background: {p.flaeche};
    color: {p.text};
    border: 1px solid {p.rand};
    padding: 6px 8px;
}}
QMenu {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.akzent_flaeche}; }}
QMenu::item:disabled {{ color: {p.gedaempft}; }}
QMenu::separator {{ height: 1px; background: {p.rand}; margin: 4px 8px; }}
QGroupBox {{
    border: 1px solid {p.rand};
    border-radius: 8px;
    margin-top: 16px;
    padding: 10px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {p.gedaempft};
}}
QListView#Vorschlaege {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 6px;
    padding: 4px 0;
    outline: none;
    font-family: Consolas, monospace;
    font-size: 12px;
}}
QFrame#Hilfekasten {{
    background: {p.flaeche};
    color: {p.text};
    border: 1px solid {p.rand};
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 12px;
}}
"""
