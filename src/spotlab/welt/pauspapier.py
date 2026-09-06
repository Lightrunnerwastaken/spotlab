"""Das Pauspapier: die Punktwolke einer Rekonstruktion, neben der Raumdatei.

Eine flache Punktliste (x, y) in Metern, Weltframe des Raums -- als kleine
Binaerdatei, damit die GUI sie ohne numpy und ohne bosdyn zeichnen kann.
Format: Kennung b"PAUS1", uint32 Anzahl, dann float32-Paare. Hoechstens
MAX_PUNKTE, gleichmaessig gedünnt (200 000 Punkte sind ~1.6 MB).
Reine Standardbibliothek wie der Rest von `welt/`.
"""

import math
import struct
from array import array
from pathlib import Path

from spotlab.errors import SpotlabError

KENNUNG = b"PAUS1"
MAX_PUNKTE = 200_000
ENDUNG = ".pauspapier"


def pfad_zu(raumpfad):
    """`raeume/gang.toml` -> `raeume/gang.pauspapier`."""
    raumpfad = Path(raumpfad)
    return raumpfad.with_suffix(ENDUNG)


def schreibe(pfad, punkte):
    punkte = list(punkte)
    if len(punkte) > MAX_PUNKTE:
        schritt = math.ceil(len(punkte) / MAX_PUNKTE)
        punkte = punkte[::schritt]
    werte = array("f")
    for x, y in punkte:
        werte.append(float(x))
        werte.append(float(y))
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "wb") as datei:
        datei.write(struct.pack("<5sI", KENNUNG, len(punkte)))
        datei.write(werte.tobytes())


def lies(pfad):
    """[(x, y), ...]; eine fehlende Datei ist eine leere Liste, kein Fehler."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return []
    roh = pfad.read_bytes()
    if len(roh) < 9 or roh[:5] != KENNUNG:
        raise SpotlabError(
            f"{pfad.name} ist kein Pauspapier (Kennung fehlt). Die Datei loeschen und "
            f"den Raum aus der Karte neu rekonstruieren."
        )
    anzahl = struct.unpack("<I", roh[5:9])[0]
    werte = array("f")
    werte.frombytes(roh[9:9 + anzahl * 8])
    return [(werte[i], werte[i + 1]) for i in range(0, len(werte) - 1, 2)]
