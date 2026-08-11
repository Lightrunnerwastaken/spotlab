"""Läufe lesen — absturztolerant.

Ein Lauf, dessen Prozess getötet wurde, hat eine halbe letzte jsonl-Zeile und
ein lauf.json, das noch auf "läuft" steht. Beides muss lesbar bleiben, sonst
verliert man genau die Läufe, die man untersuchen will.
"""

import json
from dataclasses import dataclass
from pathlib import Path


def read_jsonl(path):
    pfad = Path(path)
    if not pfad.exists():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8", errors="replace").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue  # abgeschnittene Zeile eines getöteten Prozesses
    return saetze


@dataclass(frozen=True)
class RunSummary:
    id: str
    dir: Path
    gestartet: str | None
    dauer_s: float
    backend: str
    nickname: str
    ergebnis: str
    fehler: str | None
    skript: str | None
    benutzer: str | None
    ereignisse_n: int
    abtastungen_n: int
    spotlab_version: str | None = None


def _zeilen(pfad):
    """Nichtleere Zeilen zählen, ohne sie zu parsen.

    Die Übersicht braucht nur die Anzahl. Jede Zeile durch `json.loads` zu
    schicken kostete bei einem 50-Hz-Lauf über zwanzig Minuten Hunderttausende
    Aufrufe — und die Läufe-Ansicht tut das bei JEDEM Auffrischen für JEDEN
    Lauf, im GUI-Thread.

    Eine abgeschnittene letzte Zeile — der getötete Prozess mitten im Schreiben —
    zählt NICHT mit: sie ist kein vollständiges Ereignis. Erkennbar daran, dass
    die Datei nicht mit einem Zeilenumbruch endet; dafür genügt das letzte
    Zeichen, es muss nichts geparst werden.
    """
    try:
        with Path(pfad).open("r", encoding="utf-8", errors="replace") as datei:
            anzahl, letzte = 0, ""
            for zeile in datei:
                letzte = zeile
                if zeile.strip():
                    anzahl += 1
    except OSError:
        return 0
    if letzte and not letzte.endswith("\n"):
        anzahl -= 1
    return max(anzahl, 0)


def read_run(run_dir):
    verzeichnis = Path(run_dir)
    meta = {}
    lauf = verzeichnis / "lauf.json"
    if lauf.exists():
        try:
            meta = json.loads(lauf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    return RunSummary(
        id=meta.get("id", verzeichnis.name),
        dir=verzeichnis,
        gestartet=meta.get("gestartet"),
        dauer_s=float(meta.get("dauer_s", 0.0)),
        backend=meta.get("backend", "?"),
        nickname=meta.get("nickname", ""),
        ergebnis=_ergebnis(meta, verzeichnis),
        fehler=meta.get("fehler"),
        skript=meta.get("skript"),
        benutzer=meta.get("benutzer"),
        ereignisse_n=_zeilen(verzeichnis / "ereignisse.jsonl"),
        abtastungen_n=_zeilen(verzeichnis / "zustand.jsonl"),
        spotlab_version=meta.get("spotlab_version"),
    )


def _ergebnis(meta, verzeichnis):
    """„läuft" nur, solange er wirklich läuft.

    `finish()` schreibt das Ergebnis; nach einem harten Abbruch, Stromausfall
    oder Absturz läuft es nie. Der Eintrag bliebe dann für immer auf „läuft"
    stehen, mit `0.0 s` Dauer — und jede Ansicht zeigte einen toten Lauf als
    aktiv an. Hier ist die eine Stelle, an der die Prüfung steht; GUI und CLI
    bekommen sie dadurch gemeinsam.
    """
    ergebnis = meta.get("ergebnis", "unbekannt")
    if ergebnis != "läuft":
        return ergebnis
    from spotlab.workshop.control import ist_aktiv

    return ergebnis if ist_aktiv(verzeichnis) else "abgebrochen"


def list_runs(runs_dir):
    wurzel = Path(runs_dir)
    if not wurzel.is_dir():
        return []
    verzeichnisse = [p for p in wurzel.iterdir() if p.is_dir()]
    verzeichnisse.sort(key=lambda p: p.name, reverse=True)
    return [read_run(p) for p in verzeichnisse]
