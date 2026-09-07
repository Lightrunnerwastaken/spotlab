"""Das Symbol von spotlab -- Fenster, Taskleiste, Verknuepfung.

`spotlab.png` liegt NEBEN diesem Modul, nicht neben der Wurzel: nur so findet
es ein `pip install .` wieder (Eintrag in `pyproject.toml` unter
`package-data`). Die Datei ist FREIGESTELLT -- runde Ecken mit Transparenz
aussen herum; ein Symbol mit eigenem Hintergrund saesse in der Taskleiste in
einem grauen Kasten. Dieselbe Vorlage steckt in `spotlab.ico` im Wurzelordner,
das die Desktop-Verknuepfung traegt (`verknuepfung.ps1`).

Fehlt die Datei, gibt es ein leeres `QIcon` -- Qt zeigt dann sein Standardbild.
Ein fehlendes Bild darf die GUI nie anhalten; sie ist das Fenster mit dem
NOT-AUS-Knopf.
"""

from pathlib import Path

DATEI = Path(__file__).resolve().parent / "spotlab.png"


def symbol():
    """Das Fenstersymbol als `QIcon` -- leer, wenn die Datei fehlt."""
    from PySide6.QtGui import QIcon

    return QIcon(str(DATEI)) if DATEI.is_file() else QIcon()
