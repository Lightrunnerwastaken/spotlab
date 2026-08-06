"""Ein Schülerskript starten.

Die Aufzeichnung hängt an connect(), nicht an diesem Starter — wer in VS Code
F5 drückt, bekommt sie genauso. run_script() ergänzt nur die Backend-Wahl per
Umgebungsvariable und einen Rückgabecode für die Kommandozeile.
"""

import os
import subprocess
import sys
from pathlib import Path

from spotlab.errors import SpotlabError

ENV_BACKEND = "SPOTLAB_BACKEND"


def run_script(pfad, dryrun=False, starter=subprocess.run):
    skript = Path(pfad).resolve()
    if not skript.exists():
        raise SpotlabError(f"Die Datei {skript} gibt es nicht.")

    umgebung = dict(os.environ)
    if dryrun:
        umgebung[ENV_BACKEND] = "dryrun"

    # UTF-8 im Kindprozess erzwingen: die Meldungen der Bibliothek sind deutsch,
    # und eine Windows-Konsole mit cp1252 macht daraus sonst Buchstabensalat.
    umgebung["PYTHONUTF8"] = "1"

    # Den Importpfad des Elternprozesses weiterreichen: wer spotlab hier
    # importieren kann, muss es auch im Kindprozess können. Ohne das scheitert
    # `spotlab run` in jedem Quellcode-Checkout ohne Installation.
    umgebung["PYTHONPATH"] = os.pathsep.join(
        [p for p in sys.path if p] + [umgebung.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    ergebnis = starter(
        [sys.executable, str(skript)], cwd=str(skript.parent), env=umgebung, check=False
    )
    return int(getattr(ergebnis, "returncode", 0))
