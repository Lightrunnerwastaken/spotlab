"""Tracebacks in anklickbare Stellen zerlegen.

Anklickbar wird nur, was in der Werkstatt liegt. Ein Traceback zeigt fast
immer mehr Rahmen aus fremdem Code als aus eigenem; waere alles anklickbar,
landete ein Schueler mit einem Klick in bosdyn/client/robot_command.py und
aenderte es.

Die Offsets sind relativ zum uebergebenen Text. Die Ansicht ruft die Funktion
je angehaengter Ausgabezeile auf, die Tests ueber ganze Tracebacks — beides
geht, weil die Funktion ueber den Text nichts annimmt.
"""

import re
from dataclasses import dataclass
from pathlib import Path

MUSTER = re.compile(r'File "(?P<pfad>[^"]+)", line (?P<zeile>\d+)')


@dataclass(frozen=True)
class Stelle:
    pfad: Path
    zeile: int
    von: int
    bis: int


def finde_stellen(text, wurzel):
    """Fundstellen unterhalb `wurzel`, mit Offsets relativ zu `text`."""
    try:
        grenze = Path(wurzel).resolve()
    except (OSError, ValueError):
        return []

    gefunden = []
    for treffer in MUSTER.finditer(text):
        try:
            pfad = Path(treffer.group("pfad")).resolve()
        except (OSError, ValueError):
            continue
        # is_file() faengt "<string>", "<stdin>", geloeschte temporaere Dateien
        # und ungueltige Windows-Namen ab: Path.is_file schluckt OSError und
        # ValueError und liefert dann False.
        if not pfad.is_file():
            continue
        if not pfad.is_relative_to(grenze):
            continue
        gefunden.append(
            Stelle(
                pfad=pfad,
                zeile=int(treffer.group("zeile")),
                von=treffer.start(),
                bis=treffer.end(),
            )
        )
    return gefunden
