"""Die Dateien zwischen dem Tab „Fahren“ (Steuerzentrale) und `workshop/zentrale.py`.

Dasselbe Muster wie `fahrt.json` (`record/fahrt.py`): die Platte ist der einzige
Kanal, jede Datei wird atomar ersetzt (`record/atomar.py`), und der Leser nimmt
eine fehlende, halb geschriebene oder kaputte Datei als „nichts da“. Reine
Standardbibliothek — die GUI importiert dieses Modul.

klickziel.json  Tab → Programm: wohin Spot per Klick gehen soll, mit Lebenszeichen.
aktion.json     Tab → Programm: Licht und Ton, jede Nummer genau einmal.
lagebild.json   Programm → Tab: Skizze (Bild daneben), Spot, Tags, Klickfahrt.
lagebild.png    Programm → Tab: die Skizze, ein Pixel je Zelle, Farbnummer = Zustand und Alter.
kartenauftrag.json  Tab → Programm: Karte laden, Aufnahme starten/beenden, Wegpunkt (Teil 3).
lagebild_karte.png  Programm → Tab: die geladene Karte im Raster der Skizze, Farbnummer = Abgleich.
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
# Teil 3: eine EIGENE Datei für Kartenaufträge -- in `aktion.json` könnte ein Licht-Klick ein
# „Aufnahme beenden“ überschreiben, bevor das Programm es gelesen hat.
KARTENAUFTRAG = "kartenauftrag.json"
KARTENAUFTRAEGE = ("laden", "aufnahme_start", "aufnahme_stopp", "wegpunkt")
LAGEBILD_KARTE = "lagebild_karte.png"
# Die Farbnummern im Kartenbild (0 = nichts): Kartenwand ausserhalb des Blickfelds, erkannt,
# fehlt jetzt, und eine Wand, die Spot sieht, die aber nicht in der Karte steht.
KARTE_UNGEPRUEFT, KARTE_ERKANNT, KARTE_FEHLT, KARTE_NEU = 1, 2, 3, 4
# Wie bei `fahrt.json`: ein Lebenszeichen, das aelter ist, heisst Stopp. Der Tab
# frischt es alle 200 ms auf, solange er sichtbar ist -- Reiterwechsel, Alt-Tab
# oder ein eingefrorenes Fenster halten die Klickfahrt an.
TOTMANN_S = 0.5
FARBEN = ("aus", "blau", "gruen", "gelb", "rot")
ZUSTAENDE = ("keine", "unterwegs", "angekommen", "abgelehnt", "versperrt", "abgebrochen", "folgt")
# Die Menschensuche (Teil 2): wie viel Rechenzeit sie bekommt -- aus, vorne selten, vorne so oft
# es geht, dazu Seiten- und Rückkamera.
SUCHSTUFEN = ("aus", "sparsam", "normal", "rundum")
# Ein Klick meint einen Ort (Klickfahrt) oder einen Menschen (folgen).
KLICKARTEN = ("ort", "mensch")
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
    art: str = "ort"             # "ort" (Klickfahrt) oder "mensch" (folgen)


def schreibe_klickziel(lauf_dir, nummer, ziel, stufe, jetzt=time.time, art="ort"):
    if art not in KLICKARTEN:
        raise ValueError(f"Klickart {art!r} -- erwartet eine von {list(KLICKARTEN)}.")
    daten = {
        "art": art,
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
        art = str(roh.get("art", "ort"))
        if art not in KLICKARTEN:
            return None
        return Klickziel(int(roh["nummer"]), ziel, str(roh["stufe"]), float(roh["lebt"]), art)
    except _FEHLER:
        return None


def lebt(klickziel, jetzt=time.time):
    """Ist das Lebenszeichen frisch genug, dass Spot der Klickfahrt weiter folgen darf?"""
    return klickziel is not None and jetzt() - klickziel.lebt <= TOTMANN_S


def schreibe_aktion(lauf_dir, nummer, art, farbe=None, stufe=None):
    """Licht (`farbe` aus FARBEN), Ton oder die Suchstufe (`stufe` aus SUCHSTUFEN).
    Unbekanntes wird abgewiesen, nicht geschrieben."""
    if art not in ("licht", "ton", "suche"):
        raise ValueError(f"Aktion {art!r} -- erwartet „licht“, „ton“ oder „suche“.")
    if art == "licht" and farbe not in FARBEN:
        raise ValueError(f"Farbe {farbe!r} -- erwartet eine von {list(FARBEN)}.")
    if art == "suche" and stufe not in SUCHSTUFEN:
        raise ValueError(f"Suchstufe {stufe!r} -- erwartet eine von {list(SUCHSTUFEN)}.")
    daten = {"nummer": int(nummer), "art": art, "farbe": farbe if art == "licht" else None}
    if art == "suche":
        daten["stufe"] = stufe
    return atomar.schreibe_atomar(Path(lauf_dir) / AKTION, json.dumps(daten))


def lies_aktion(lauf_dir):
    try:
        roh = json.loads((Path(lauf_dir) / AKTION).read_text(encoding="utf-8"))
        aktion = {"nummer": int(roh["nummer"]), "art": str(roh["art"]), "farbe": roh.get("farbe")}
        if roh.get("stufe") is not None:
            aktion["stufe"] = str(roh["stufe"])
        return aktion
    except _FEHLER:
        return None


def schreibe_kartenauftrag(lauf_dir, nummer, was, name=None):
    """Ein Kartenauftrag (`was` aus KARTENAUFTRAEGE). Unbekanntes wird abgewiesen."""
    if was not in KARTENAUFTRAEGE:
        raise ValueError(f"Kartenauftrag {was!r} -- erwartet einer von {list(KARTENAUFTRAEGE)}.")
    daten = {"nummer": int(nummer), "was": was, "name": None if name is None else str(name)}
    return atomar.schreibe_atomar(Path(lauf_dir) / KARTENAUFTRAG, json.dumps(daten))


def lies_kartenauftrag(lauf_dir):
    """{nummer, was, name} — oder None (fehlt, halb geschrieben, kaputt, unbekanntes `was`)."""
    try:
        roh = json.loads((Path(lauf_dir) / KARTENAUFTRAG).read_text(encoding="utf-8"))
        was = str(roh["was"])
        if was not in KARTENAUFTRAEGE:
            return None
        name = roh.get("name")
        return {"nummer": int(roh["nummer"]), "was": was,
                "name": None if name is None else str(name)}
    except _FEHLER:
        return None


def schreibe_lagebild(lauf_dir, daten, bild, kartenbild=None):
    """Erst die Bilder, dann die Beschreibung: wer ein neues `lagebild.json` sieht, findet die
    Bilder dazu schon vor. `bild=None` (noch keine Skizze) schreibt nur die Beschreibung,
    `kartenbild=None` (keine Karte geladen) lässt das Kartenbild weg."""
    lauf_dir = Path(lauf_dir)
    gut = True
    if bild is not None:
        gut = atomar.schreibe_atomar(lauf_dir / LAGEBILD_BILD, bytes(bild))
    if kartenbild is not None:
        gut = atomar.schreibe_atomar(lauf_dir / LAGEBILD_KARTE, bytes(kartenbild)) and gut
    return atomar.schreibe_atomar(lauf_dir / LAGEBILD, json.dumps(daten, ensure_ascii=False)) and gut


def lies_lagebild(lauf_dir):
    try:
        roh = json.loads((Path(lauf_dir) / LAGEBILD).read_text(encoding="utf-8"))
    except _FEHLER:
        return None
    return roh if isinstance(roh, dict) else None
