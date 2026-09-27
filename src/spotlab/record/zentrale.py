"""Die Dateien zwischen dem Tab „Fahren“ (Steuerzentrale) und `workshop/zentrale.py`.

Dasselbe Muster wie `fahrt.json` (`record/fahrt.py`): die Platte ist der einzige
Kanal, jede Datei wird atomar ersetzt (`record/atomar.py`), und der Leser nimmt
eine fehlende, halb geschriebene oder kaputte Datei als „nichts da“. Reine
Standardbibliothek — die GUI importiert dieses Modul.

klickziel.json  Tab → Programm: wohin Spot per Klick gehen soll, mit Lebenszeichen.
aktion.json     Tab → Programm: Licht und Ton, jede Nummer genau einmal.
lagebild.json   Programm → Tab: Skizze (Bild daneben), Spot, Tags, Klickfahrt.
lagebild.png    Programm → Tab: die Skizze, ein Pixel je Zelle, Farbnummer = Zustand und Alter.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from spotlab.record import atomar

KLICKZIEL = "klickziel.json"
AKTION = "aktion.json"
LAGEBILD = "lagebild.json"
LAGEBILD_BILD = "lagebild.png"
# Wie bei `fahrt.json`: ein Lebenszeichen, das aelter ist, heisst Stopp. Der Tab
# frischt es alle 200 ms auf, solange er sichtbar ist -- Reiterwechsel, Alt-Tab
# oder ein eingefrorenes Fenster halten die Klickfahrt an.
TOTMANN_S = 0.5
FARBEN = ("aus", "blau", "gruen", "gelb", "rot")
ZUSTAENDE = ("keine", "unterwegs", "angekommen", "abgelehnt", "versperrt", "abgebrochen")
# Die Farbnummern im Bild: 0 unbekannt, 1..ALTERSSTUFEN frei (frisch -> alt),
# ALTERSSTUFEN+1..2*ALTERSSTUFEN Wand. Die Farben legt die GUI darueber
# (`gui/lagebild.py`, aus `gui/theme.py`) -- so stimmen sie in hell und dunkel.
ALTERSSTUFEN = 8
_FEHLER = (OSError, ValueError, TypeError, KeyError, IndexError)


@dataclass(frozen=True)
class Klickziel:
    nummer: int
    ziel: tuple | None           # (x, y) im Rahmen der Skizze („vision“), None = abbrechen
    stufe: str                   # Tempostufe aus `record/fahrt.STUFEN`
    lebt: float                  # Wanduhr des Tabs beim letzten Auffrischen


def schreibe_klickziel(lauf_dir, nummer, ziel, stufe, jetzt=time.time):
    daten = {
        "nummer": int(nummer),
        "ziel": None if ziel is None else [float(ziel[0]), float(ziel[1])],
        "stufe": str(stufe),
        "lebt": float(jetzt()),
    }
    return atomar.schreibe_atomar(Path(lauf_dir) / KLICKZIEL, json.dumps(daten))


def lies_klickziel(lauf_dir):
    """Das Klickziel — oder None, wenn die Datei fehlt, halb geschrieben oder kaputt ist."""
    try:
        roh = json.loads((Path(lauf_dir) / KLICKZIEL).read_text(encoding="utf-8"))
        ziel = roh["ziel"]
        ziel = None if ziel is None else (float(ziel[0]), float(ziel[1]))
        return Klickziel(int(roh["nummer"]), ziel, str(roh["stufe"]), float(roh["lebt"]))
    except _FEHLER:
        return None


def lebt(klickziel, jetzt=time.time):
    """Ist das Lebenszeichen frisch genug, dass Spot der Klickfahrt weiter folgen darf?"""
    return klickziel is not None and jetzt() - klickziel.lebt <= TOTMANN_S


def schreibe_aktion(lauf_dir, nummer, art, farbe=None):
    """Licht (`farbe` aus FARBEN) oder Ton. Unbekanntes wird abgewiesen, nicht geschrieben."""
    if art not in ("licht", "ton"):
        raise ValueError(f"Aktion {art!r} -- erwartet „licht“ oder „ton“.")
    if art == "licht" and farbe not in FARBEN:
        raise ValueError(f"Farbe {farbe!r} -- erwartet eine von {list(FARBEN)}.")
    daten = {"nummer": int(nummer), "art": art, "farbe": farbe if art == "licht" else None}
    return atomar.schreibe_atomar(Path(lauf_dir) / AKTION, json.dumps(daten))


def lies_aktion(lauf_dir):
    try:
        roh = json.loads((Path(lauf_dir) / AKTION).read_text(encoding="utf-8"))
        return {"nummer": int(roh["nummer"]), "art": str(roh["art"]), "farbe": roh.get("farbe")}
    except _FEHLER:
        return None


def schreibe_lagebild(lauf_dir, daten, bild):
    """Erst das Bild, dann die Beschreibung: wer ein neues `lagebild.json` sieht, findet das
    Bild dazu schon vor. `bild=None` (noch keine Skizze) schreibt nur die Beschreibung."""
    lauf_dir = Path(lauf_dir)
    gut = True
    if bild is not None:
        gut = atomar.schreibe_atomar(lauf_dir / LAGEBILD_BILD, bytes(bild))
    return atomar.schreibe_atomar(lauf_dir / LAGEBILD, json.dumps(daten, ensure_ascii=False)) and gut


def lies_lagebild(lauf_dir):
    try:
        roh = json.loads((Path(lauf_dir) / LAGEBILD).read_text(encoding="utf-8"))
    except _FEHLER:
        return None
    return roh if isinstance(roh, dict) else None
