"""Pfadhygiene, die mehr als ein Teilsystem braucht.

sicherer_name lag bis Stufe 6 in maps/store.py. Die Anbindung braucht dieselbe
Regel — sie aus maps/store.py zu importieren hiesse aber, sie an die
GraphNav-Ablage zu koppeln, und maps/store.py zieht dafuer bosdyn herein.
Ein gemeinsamer Ort loest beides, ohne zwei Umsetzungen zu haben, die
auseinanderlaufen koennen.
"""

import re

MUSTER = re.compile(r"[^\w.-]+")


def sicherer_name(name, ersatz="ordner"):
    """Ein Name, der garantiert ein einzelnes Verzeichnis unterhalb bleibt."""
    sauber = MUSTER.sub("-", str(name).strip()).strip("-.")
    return sauber or ersatz
