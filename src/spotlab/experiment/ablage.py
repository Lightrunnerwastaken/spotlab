"""Wo die Dateien des Gehzeit-Versuchs im Lauf liegen — an genau einer Stelle.

Drei Seiten fragen danach: das Programm, das schreibt (`workshop/gehzeit.py`),
der Nachtrag, der liest und ergaenzt (`experiment/nachtrag.py`), und die Ansicht
im Fenster (`gui/views/gehzeit.py`). Zwei Formulierungen desselben Pfades waeren
der Fehler aus Stufe 3 in neuem Gewand — und er faellt erst auf, wenn eine Seite
eine Tabelle nicht findet, die die andere geschrieben hat.

Hier steht die Ablage deshalb ohne jede Abhaengigkeit: reine Pfadarithmetik.
Dadurch darf auch `gui/` sie importieren, ohne etwas aus `workshop/` oder
`backends/` mitzuziehen.
"""

from pathlib import Path

# Alles, was der Versuch schreibt, liegt in EINEM Unterordner des Laufs. Die
# gewohnte Aufzeichnung daneben (ereignisse.jsonl, zustand.jsonl, kamera/)
# bleibt unberuehrt — sie gehoert dem Lauf, nicht dem Versuch.
ORDNER = "gehzeit"
CSV = "gehzeit.csv"
STRECKE = "strecke.json"
QUERUNGEN = "querungen.jsonl"

# Die Bilder liegen NICHT im Versuchsordner: sie kommen aus dem gewoehnlichen
# Bildmitschnitt und tragen dessen Index mit derselben Zeitbasis. Ein zweiter
# Bildstrom neben dem ersten waere doppelte Bandbreite fuer dieselben Kameras.
BILDER = "kamera"
BILDINDEX = "kamera/kamera.jsonl"


def ordner(lauf):
    return Path(lauf) / ORDNER


def csv_pfad(lauf):
    return ordner(lauf) / CSV


def strecke_pfad(lauf):
    return ordner(lauf) / STRECKE


def querungen_pfad(lauf):
    return ordner(lauf) / QUERUNGEN


def bilder_ordner(lauf):
    return Path(lauf) / BILDER


def bildindex(lauf):
    return Path(lauf) / BILDINDEX


def hat_versuch(lauf):
    """Ob in diesem Lauf ueberhaupt eine Gehzeit-Tabelle liegt."""
    return csv_pfad(lauf).is_file()
