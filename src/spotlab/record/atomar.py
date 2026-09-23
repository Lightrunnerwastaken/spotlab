"""Eine kleine Datei atomar ersetzen -- geduldig gegen den Windows-Lesekonflikt.

`os.replace` scheitert unter Windows mit PermissionError, solange ein anderer
Prozess die Zieldatei gerade offen hat -- der Leser von `fahrt.json` oder
`kamera.json` tut das zwanzigmal je Sekunde. Der Schreiber wiederholt kurz und
gibt dann auf, ohne zu werfen: der naechste Takt schreibt ohnehin, und ein
Kamerawunsch oder Fahrbefehl darf nie eine GUI oder einen Lauf anhalten
(gesehen in der Gesamtsuite am 07.09.2026).
"""

import os
import tempfile
import time
from pathlib import Path

VERSUCHE = 5
PAUSE_S = 0.01

_ersetze = os.replace          # austauschbar fuer Tests


def schreibe_atomar(ziel, inhalt, versuche=VERSUCHE, pause_s=PAUSE_S):
    """`inhalt` nach `ziel`: erst eine Temp-Datei, dann ersetzen. True, wenn es gelang.

    Text wird als UTF-8 geschrieben, `bytes` woertlich -- dasselbe Verfahren
    traegt `fahrt.json` und das Bild `ansicht.jpg`, das die GUI im selben
    Augenblick liest.

    Die Temp-Datei gehoert GENAU DIESEM Schreibvorgang: `<name>.<zufall>.tmp`
    neben dem Ziel, exklusiv angelegt. Bis zum 23.09.2026 hiess sie
    `ziel.with_suffix(".tmp")` -- fuer `ansicht.jpg` (Blick, MuJoCo) und
    `ansicht.json` (Schalter der GUI) beide `ansicht.tmp`, und zwei Faeden an
    demselben Ziel teilten sie ohnehin. Folge: vertauschte Inhalte (ein JPEG in
    der Schalterdatei) und FileNotFoundError, obwohl dieses Modul verspricht,
    nie zu werfen. Jetzt wirft es auch dann nicht, wenn der Ordner fehlt (der
    Lauf ist schon aufgeraeumt) oder die Platte voll ist: False.
    """
    ziel = Path(ziel)
    daten = bytes(inhalt) if isinstance(inhalt, (bytes, bytearray)) else inhalt.encode("utf-8")
    try:
        griff, name = tempfile.mkstemp(dir=ziel.parent, prefix=ziel.name + ".", suffix=".tmp")
    except OSError:
        return False
    temporaer = Path(name)
    try:
        with os.fdopen(griff, "wb") as datei:
            datei.write(daten)
        for versuch in range(versuche):
            try:
                _ersetze(temporaer, ziel)
                return True
            except PermissionError:
                # Der Leser hat das Ziel gerade offen (Windows) -- kurz warten.
                if versuch + 1 < versuche:
                    time.sleep(pause_s)
    except OSError:
        pass
    try:
        temporaer.unlink()
    except OSError:
        pass
    return False
