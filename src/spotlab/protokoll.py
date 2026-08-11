"""Diagnose-Protokoll — für das, was sonst spurlos verschluckt wird.

Die Abbaupfade fangen absichtlich alles: `RealSpot.close()`, `EstopGuard.stop()`,
`LeaseGuard.stop()` müssen durchlaufen, egal was passiert. Der Preis war, dass
nach einem Vorfall nichts rekonstruierbar blieb — „der Spot hat sich nicht
hingesetzt" ohne jede Spur, warum.

**Niemals auf stdout oder stderr.** Die Ausgabe eines Laufs hat genau einen
Leser, und der MCP-Server spricht über stdin/stdout ein Protokoll. Ein
`StreamHandler` dort hinein zerstörte beides. Deshalb ausschliesslich in eine
Datei neben der Aufzeichnung.

Qt-frei und SDK-frei: jede Schicht darf hierher schreiben.
"""

import datetime
import os
import threading
import traceback
from pathlib import Path

DATEINAME = "diagnose.log"

_sperre = threading.Lock()
_ziel = None


def setze_ziel(verzeichnis):
    """Wohin geschrieben wird — üblicherweise das Lauf-Verzeichnis.

    Ohne Ziel wird nichts geschrieben. Das ist Absicht: ein Import von spotlab
    soll keine Datei irgendwo anlegen.
    """
    global _ziel
    _ziel = Path(verzeichnis) if verzeichnis else None


def ziel():
    return _ziel


def notiere(text, fehler=None):
    """Eine Zeile ins Protokoll. Wirft NIE.

    Sie wird aus Abbaupfaden gerufen, in denen schon etwas schiefgegangen ist —
    ein Fehler beim Protokollieren dürfte den Abbau nicht zusätzlich stören.
    """
    if _ziel is None:
        return
    jetzt = datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds")
    zeilen = [f"{jetzt}  pid={os.getpid()}  {text}"]
    if fehler is not None:
        spur = "".join(
            traceback.format_exception(type(fehler), fehler, fehler.__traceback__)
        )
        zeilen.append(spur.rstrip())
    try:
        with _sperre:
            _ziel.mkdir(parents=True, exist_ok=True)
            with (_ziel / DATEINAME).open("a", encoding="utf-8", newline="\n") as datei:
                datei.write("\n".join(zeilen) + "\n")
    except Exception:
        # Bewusst ALLES: ein ungültiger Pfad wirft ValueError, ein Rechteproblem
        # OSError, und was der Dateiname auf Windows sonst noch auslöst, ist
        # nicht abschliessend aufzuzählen. Protokollieren darf den Abbau, in dem
        # es gerufen wird, unter keinen Umständen zusätzlich stören.
        pass
