"""`fahrt.json` im Lauf-Verzeichnis: der Fahrbefehl der Tastatur fuer `fahren.py`.

Das Uebungsfenster schreibt ihn bei jeder Tastenaenderung und alle 200 ms,
solange eine Taste gedrueckt ist; `workshop/fahren.py` liest ihn mit 20 Hz und
faehrt. Ein Befehl, der aelter ist als TOTMANN_S, heisst Stopp -- eine
losgelassene Taste, eine eingeschlafene oder geschlossene GUI halten den
Roboter an, ohne dass jemand daran denken muss. Reine Standardbibliothek,
dasselbe Muster wie `record/kamera.py`: die Platte ist der einzige Kanal.
"""

import json
import math
import time
from pathlib import Path

from spotlab.record import atomar

DATEI = "fahrt.json"
TOTMANN_S = 0.5
STILL = (0.0, 0.0, 0.0)

# Die Tastenbelegung des Uebungsfensters -- hier, damit sie ohne Qt prueffbar ist.
# Gemaechlich; die Grenzen aus config.toml deckeln wie bei jedem Programm.
TEMPO_M_S = 0.4
QUER_M_S = 0.3
DREH_RAD_S = math.radians(45.0)
TASTEN = {
    "w": (TEMPO_M_S, 0.0, 0.0), "s": (-TEMPO_M_S, 0.0, 0.0),
    "a": (0.0, QUER_M_S, 0.0), "d": (0.0, -QUER_M_S, 0.0),
    "q": (0.0, 0.0, DREH_RAD_S), "e": (0.0, 0.0, -DREH_RAD_S),
}


def befehl_aus_tasten(tasten, faktor=1.0):
    """(vx, vy, wz) aus den gedrueckten Buchstaben; Gegenspieler heben sich auf.

    `faktor` drosselt alle drei Achsen gleich -- „Langsam" am echten Roboter.
    """
    vx = vy = wz = 0.0
    for taste in tasten:
        dx, dy, dw = TASTEN.get(taste, (0.0, 0.0, 0.0))
        vx, vy, wz = vx + dx, vy + dy, wz + dw
    return (vx * faktor, vy * faktor, wz * faktor)


def schreibe(lauf_dir, vx, vy, wz, jetzt=time.time):
    """Atomar: erst `.tmp`, dann ersetzen. `jetzt` ist die Wanduhr (auch im Leser)."""
    atomar.schreibe_atomar(
        Path(lauf_dir) / DATEI,
        json.dumps({"vx": float(vx), "vy": float(vy), "wz": float(wz), "t": float(jetzt())}),
    )


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
