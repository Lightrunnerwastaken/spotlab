"""Panels: was ein fremdes Projekt zu sagen hat, als Daten statt als Code.

Fuenf Arten, jede auf ein Widget, das spotlab schon hat. Ein Panel waehlt KEINE
Farben — sonst gibt es einen Hell/Dunkel-Modus, in dem fremde Daten unlesbar
sind.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from spotlab.anbindung.speicher import panelordner
from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name

ARTEN = ("kennzahlen", "tabelle", "reihe", "bild", "text")


@dataclass(frozen=True)
class Panel:
    name: str
    titel: str
    art: str
    stand: str
    inhalt: object
    fehler: str | None = None


def pruefe_inhalt(art, inhalt):
    """Gibt einen deutschen Grund zurueck — oder None, wenn der Inhalt passt."""
    if art == "kennzahlen":
        if not isinstance(inhalt, list):
            return "`inhalt` muss bei `kennzahlen` eine Liste sein."
        for eintrag in inhalt:
            if not isinstance(eintrag, dict) or "name" not in eintrag or "wert" not in eintrag:
                return "Jede Kennzahl braucht `name` und `wert`."
        return None

    if art == "tabelle":
        if not isinstance(inhalt, dict) or "spalten" not in inhalt or "zeilen" not in inhalt:
            return "`inhalt` braucht bei `tabelle` die Felder `spalten` und `zeilen`."
        spalten = inhalt["spalten"]
        if not isinstance(spalten, list) or not isinstance(inhalt["zeilen"], list):
            return "`spalten` und `zeilen` müssen Listen sein."
        for zeile in inhalt["zeilen"]:
            if not isinstance(zeile, list) or len(zeile) != len(spalten):
                return f"Jede Zeile braucht genau {len(spalten)} Werte."
        return None

    if art == "reihe":
        if not isinstance(inhalt, dict) or "x" not in inhalt or "y" not in inhalt:
            return "`inhalt` braucht bei `reihe` die Felder `x` und `y`."
        if not isinstance(inhalt["x"], list) or not isinstance(inhalt["y"], list):
            return "`x` und `y` müssen Listen sein."
        if len(inhalt["x"]) != len(inhalt["y"]):
            return "`x` und `y` müssen gleich lang sein."
        return None

    if art == "bild":
        if not isinstance(inhalt, dict) or not inhalt.get("pfad"):
            return "`inhalt` braucht bei `bild` das Feld `pfad`."
        return None

    if art == "text":
        if not isinstance(inhalt, dict) or not isinstance(inhalt.get("absaetze"), list):
            return "`inhalt` braucht bei `text` das Feld `absaetze` als Liste."
        return None

    return f"Unbekannte Art „{art}“. Bekannt sind: {', '.join(ARTEN)}."


def schreibe(anbindung, name, art, titel, inhalt, jetzt=None):
    grund = pruefe_inhalt(art, inhalt)
    if grund is not None:
        raise SpotlabError(grund)
    ordner = panelordner(anbindung)
    ordner.mkdir(parents=True, exist_ok=True)
    sicher = sicherer_name(name, ersatz="panel")
    ziel = ordner / f"{sicher}.json"
    daten = {
        "titel": str(titel),
        "art": art,
        "stand": (jetzt or datetime.now(UTC)).isoformat(),
        "inhalt": inhalt,
    }
    # Atomar: erst daneben, dann umbenennen. Ein Leser sieht nie eine halbe Datei.
    zwischen = ordner / f"{sicher}.json.neu"
    zwischen.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(zwischen, ziel)
    return ziel


def lies(pfad):
    """Wirft NIE.

    Ein Panel, das im Sekundentakt ueberschrieben wird, ist regelmaessig fuer
    Millisekunden halb geschrieben. Eine Ansicht, die daran leer wird, flackert
    im Betrieb — und EIN kaputtes Panel darf die anderen vier nicht loeschen.
    Das atomare Schreiben oben schwaecht das nicht ab: es faengt nur unsere
    eigenen Schreiber, nicht fremde.
    """
    pfad = Path(pfad)
    name = pfad.stem
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as fehler:
        return Panel(name, name, "", "", None, f"Datei nicht lesbar: {fehler}")
    if not isinstance(daten, dict):
        return Panel(name, name, "", "", None, "Die Datei enthält kein JSON-Objekt.")
    art = str(daten.get("art") or "")
    titel = str(daten.get("titel") or name)
    stand = str(daten.get("stand") or "")
    inhalt = daten.get("inhalt")
    return Panel(name, titel, art, stand, inhalt, pruefe_inhalt(art, inhalt))


def panels(anbindung):
    try:
        dateien = sorted(panelordner(anbindung).glob("*.json"), key=lambda p: p.name)
    except OSError:
        return []
    return [lies(p) for p in dateien]


def entferne(anbindung, name):
    ziel = panelordner(anbindung) / f"{sicherer_name(name, ersatz='panel')}.json"
    try:
        ziel.unlink()
    except OSError:
        return False
    return True


def bild_erlaubt(pfad, anbindung):
    """Nur unterhalb des Projekts oder des Anbindungsordners.

    Dieselbe Regel und derselbe Grund wie bei den anklickbaren Tracebacks in
    Stufe 5: eine Datei, die sagt „zeig das hier", darf nicht auf Beliebiges im
    Dateisystem deuten.
    """
    try:
        ziel = Path(pfad).resolve()
    except (OSError, ValueError):
        return False
    for erlaubt in (anbindung.quelle, anbindung.ordner):
        try:
            if ziel.is_relative_to(Path(erlaubt).resolve()):
                return True
        except (OSError, ValueError):
            continue
    return False
