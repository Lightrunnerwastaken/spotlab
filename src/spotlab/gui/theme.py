"""Zwei Paletten, hell und dunkel.

Bewusst Qt-frei: das Auslesen der Windows-Einstellung braucht Qt und liegt in
app.py. Nur so bleibt die Palettenwahl ohne Fenster prüfbar — und nur so
lassen sich Farbliterale im Widget-Code verhindern, denn die einzige Quelle
für Farben ist dieses Modul.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    hintergrund: str
    flaeche: str
    rand: str
    text: str
    gedaempft: str
    akzent: str
    ok: str
    warnung: str
    gefahr: str


DUNKEL = Palette(
    hintergrund="#1e1f22",
    flaeche="#26282c",
    rand="#34373d",
    text="#d7dae0",
    gedaempft="#868d97",
    akzent="#579dff",
    ok="#3fb950",
    warnung="#d29922",
    gefahr="#e5484d",
)

HELL = Palette(
    hintergrund="#f4f5f7",
    flaeche="#ffffff",
    rand="#dfe1e6",
    text="#1f2328",
    gedaempft="#6b7280",
    akzent="#0b5cd5",
    ok="#1a7f37",
    warnung="#9a6700",
    gefahr="#d1372f",
)


def palette_fuer(dunkel):
    return DUNKEL if dunkel else HELL


def stylesheet(p):
    """Qt-Stylesheet aus der Palette. Einzige Stelle mit Farbwerten im Programm."""
    return f"""
QWidget {{
    background: {p.hintergrund};
    color: {p.text};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}
QFrame#Flaeche, QListWidget, QTableWidget, QPlainTextEdit, QLineEdit, QDoubleSpinBox {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 8px;
}}
QLineEdit, QDoubleSpinBox {{ padding: 6px 8px; }}
QLabel#Gedaempft {{ color: {p.gedaempft}; }}
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
QPushButton:disabled {{ color: {p.gedaempft}; }}
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
"""
