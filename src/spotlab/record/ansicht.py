"""`ansicht.json` im Lauf-Verzeichnis: was der Blick des Laufs zeigen soll.

Der Gegenweg zu `ansicht.jpg`. Die Ansicht „Fahren" schreibt diese Datei, wenn
man den Schalter umlegt; `workshop/blick.py` liest sie im Laufprozess und
zeichnet dann die Kästen des Gesichtserkenners ins Bild. Dasselbe Muster wie
`record/fahrt.py`: reine Standardbibliothek, die Platte ist der einzige Kanal
zwischen GUI und Lauf.

KEIN TOTMANN. `fahrt.lies` gibt Stillstand zurück, sobald der Befehl älter als
eine halbe Sekunde ist — eine losgelassene Taste oder eine eingeschlafene GUI
halten den Roboter an. Für einen Schalter wäre dieselbe Regel falsch: wer eine
halbe Stunde geradeaus fährt, ohne eine Taste zu bewegen, soll die Kästen nicht
verlieren. Deshalb trägt diese Datei gar keine Zeitmarke — was nicht da ist,
kann auch niemand versehentlich prüfen.
"""

import json
from pathlib import Path

from spotlab.record import atomar

DATEI = "ansicht.json"


SCHALTER = ("gesicht", "hand")


def schreibe(lauf_dir, gesicht, hand=False):
    """Beide Schalterstände ablegen. Atomar, weil der Blick im selben Augenblick liest."""
    atomar.schreibe_atomar(
        Path(lauf_dir) / DATEI, json.dumps({"gesicht": bool(gesicht), "hand": bool(hand)})
    )


def schalter(lauf_dir):
    """`{"gesicht": bool, "hand": bool}` — beides aus, wenn die Datei fehlt oder kaputt ist.

    Fehlt die Datei, ist sie halb geschrieben oder steht Unsinn darin, heisst es
    aus. Ein Blick, der an der Schalterdatei stirbt, wäre schlimmer als einer
    ohne Kästen: ohne Bild fährt man weiter, ohne Fahrbefehle nicht. Eine ältere
    Datei ohne `hand` heisst: Hand aus — nur ein echtes `true` zählt.
    """
    aus = {name: False for name in SCHALTER}
    try:
        roh = json.loads((Path(lauf_dir) / DATEI).read_text(encoding="utf-8"))
        return {name: roh.get(name) is True for name in SCHALTER}
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return aus


def lies(lauf_dir):
    """True, wenn die Gesichtserkennung an ist — sonst False. Für die Hand: `schalter()`."""
    return schalter(lauf_dir)["gesicht"]
