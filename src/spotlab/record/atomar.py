"""Eine kleine Datei atomar ersetzen -- geduldig gegen den Windows-Lesekonflikt.

`os.replace` scheitert unter Windows mit PermissionError, solange ein anderer
Prozess die Zieldatei gerade offen hat -- der Leser von `fahrt.json` oder
`kamera.json` tut das zwanzigmal je Sekunde. Der Schreiber wiederholt kurz und
gibt dann auf, ohne zu werfen: der naechste Takt schreibt ohnehin, und ein
Kamerawunsch oder Fahrbefehl darf nie eine GUI oder einen Lauf anhalten
(gesehen in der Gesamtsuite am 07.09.2026).
"""

import os
import time
from pathlib import Path

VERSUCHE = 5
PAUSE_S = 0.01

_ersetze = os.replace          # austauschbar fuer Tests


def schreibe_atomar(ziel, text, versuche=VERSUCHE, pause_s=PAUSE_S):
    """`text` nach `ziel`: erst `.tmp`, dann ersetzen. True, wenn es gelang."""
    ziel = Path(ziel)
    temporaer = ziel.with_suffix(".tmp")
    temporaer.write_text(text, encoding="utf-8")
    for versuch in range(versuche):
        try:
            _ersetze(temporaer, ziel)
            return True
        except PermissionError:
            if versuch + 1 < versuche:
                time.sleep(pause_s)
    try:
        temporaer.unlink()
    except OSError:
        pass
    return False
