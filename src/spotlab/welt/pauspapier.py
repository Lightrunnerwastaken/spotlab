"""Das Pauspapier: die Punktwolke einer Rekonstruktion, neben der Raumdatei.

Eine flache Punktliste (x, y) in Metern, Weltframe des Raums -- als kleine
Binaerdatei, damit die GUI sie ohne numpy und ohne bosdyn zeichnen kann.
Format PAUS2: Kennung, uint32 Anzahl, float32-Paare, dann uint32 Anzahl und
float32-Tripel (x, y, Bodenhoehe) des gelaufenen Wegs in Laufreihenfolge. Der
Weg ist die Stuetze des Gelaendes und das Signal „der Roboter lief hindurch"
im Korrigierer. PAUS1 (nur Punkte) wird weiter gelesen, der Weg ist dann leer.
Hoechstens MAX_PUNKTE, gleichmaessig gedünnt (200 000 Punkte sind ~1.6 MB).
Reine Standardbibliothek wie der Rest von `welt/`.
"""

import math
import struct
from array import array
from pathlib import Path

from spotlab.errors import SpotlabError

KENNUNG = b"PAUS2"
KENNUNG_ALT = b"PAUS1"
MAX_PUNKTE = 200_000
ENDUNG = ".pauspapier"


def pfad_zu(raumpfad):
    """`raeume/gang.toml` -> `raeume/gang.pauspapier`."""
    raumpfad = Path(raumpfad)
    return raumpfad.with_suffix(ENDUNG)


def schreibe(pfad, punkte, weg=()):
    punkte = list(punkte)
    if len(punkte) > MAX_PUNKTE:
        schritt = math.ceil(len(punkte) / MAX_PUNKTE)
        punkte = punkte[::schritt]
    werte = array("f")
    for x, y in punkte:
        werte.append(float(x))
        werte.append(float(y))
    wegwerte = array("f")
    weg = list(weg)
    for x, y, z in weg:
        wegwerte.append(float(x))
        wegwerte.append(float(y))
        wegwerte.append(float(z))
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "wb") as datei:
        datei.write(struct.pack("<5sI", KENNUNG, len(punkte)))
        datei.write(werte.tobytes())
        datei.write(struct.pack("<I", len(weg)))
        datei.write(wegwerte.tobytes())


def _lies_roh(pfad):
    """(punkte, weg); eine fehlende Datei ist leer, kein Fehler."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return [], []
    roh = pfad.read_bytes()
    if len(roh) < 9 or roh[:5] not in (KENNUNG, KENNUNG_ALT):
        raise SpotlabError(
            f"{pfad.name} ist kein Pauspapier (Kennung fehlt). Die Datei loeschen und "
            f"den Raum aus der Karte neu rekonstruieren."
        )
    anzahl = struct.unpack("<I", roh[5:9])[0]
    werte = array("f")
    ende = 9 + anzahl * 8
    werte.frombytes(roh[9:ende])
    punkte = [(werte[i], werte[i + 1]) for i in range(0, len(werte) - 1, 2)]
    weg = []
    if roh[:5] == KENNUNG and len(roh) >= ende + 4:
        n = struct.unpack("<I", roh[ende:ende + 4])[0]
        wegwerte = array("f")
        wegwerte.frombytes(roh[ende + 4:ende + 4 + n * 12])
        weg = [(wegwerte[i], wegwerte[i + 1], wegwerte[i + 2]) for i in range(0, len(wegwerte) - 2, 3)]
    return punkte, weg


def lies(pfad):
    """[(x, y), ...]; eine fehlende Datei ist eine leere Liste, kein Fehler."""
    return _lies_roh(pfad)[0]


def lies_weg(pfad):
    """[(x, y, z), ...] -- der gelaufene Weg; leer bei PAUS1 oder ohne Datei."""
    return _lies_roh(pfad)[1]
