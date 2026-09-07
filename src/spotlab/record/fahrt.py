"""`fahrt.json` im Lauf-Verzeichnis: der Fahrbefehl der Tastatur fuer `fahren.py`.

Das Uebungsfenster schreibt ihn bei jeder Tastenaenderung und alle 200 ms,
solange eine Taste gedrueckt ist; `workshop/fahren.py` liest ihn mit 20 Hz und
faehrt. Ein Befehl, der aelter ist als TOTMANN_S, heisst Stopp -- eine
losgelassene Taste, eine eingeschlafene oder geschlossene GUI halten den
Roboter an, ohne dass jemand daran denken muss. Reine Standardbibliothek,
dasselbe Muster wie `record/kamera.py`: die Platte ist der einzige Kanal.
"""

import json
import os
import time
from pathlib import Path

DATEI = "fahrt.json"
TOTMANN_S = 0.5
STILL = (0.0, 0.0, 0.0)


def schreibe(lauf_dir, vx, vy, wz, jetzt=time.time):
    """Atomar: erst `.tmp`, dann ersetzen. `jetzt` ist die Wanduhr (auch im Leser)."""
    ziel = Path(lauf_dir) / DATEI
    temporaer = ziel.with_suffix(".tmp")
    temporaer.write_text(
        json.dumps({"vx": float(vx), "vy": float(vy), "wz": float(wz), "t": float(jetzt())}),
        encoding="utf-8",
    )
    os.replace(temporaer, ziel)


def lies(lauf_dir, jetzt=time.time):
    """(vx, vy, wz) -- oder Stillstand, wenn die Datei fehlt, kaputt oder alt ist."""
    pfad = Path(lauf_dir) / DATEI
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        vx, vy, wz, t = (float(roh[k]) for k in ("vx", "vy", "wz", "t"))
    except (OSError, ValueError, TypeError, KeyError):
        return STILL
    if jetzt() - t > TOTMANN_S:
        return STILL
    return (vx, vy, wz)
