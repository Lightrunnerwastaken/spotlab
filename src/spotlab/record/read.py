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
        ergebnis=meta.get("ergebnis", "unbekannt"),
        fehler=meta.get("fehler"),
        skript=meta.get("skript"),
        benutzer=meta.get("benutzer"),
        ereignisse_n=len(read_jsonl(verzeichnis / "ereignisse.jsonl")),
        abtastungen_n=len(read_jsonl(verzeichnis / "zustand.jsonl")),
    )


def list_runs(runs_dir):
    wurzel = Path(runs_dir)
    if not wurzel.is_dir():
        return []
    verzeichnisse = [p for p in wurzel.iterdir() if p.is_dir()]
    verzeichnisse.sort(key=lambda p: p.name, reverse=True)
    return [read_run(p) for p in verzeichnisse]
