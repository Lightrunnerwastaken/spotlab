"""Ein Schülerskript starten.

Die Aufzeichnung hängt an connect(), nicht an diesem Starter — wer in VS Code
F5 drückt, bekommt sie genauso. Hier kommen nur die Backend-Wahl per
Umgebungsvariable, der Importpfad und die Ausgabe-Pipe dazu.

start_script() kehrt sofort zurück und ist der Weg der GUI; run_script()
wartet und ist der Weg der Kommandozeile. Beide bauen denselben Prozess auf,
damit es keinen zweiten Code-Pfad gibt.
"""

import os
import subprocess
import sys
from pathlib import Path

from spotlab.errors import SpotlabError

ENV_BACKEND = "SPOTLAB_BACKEND"


def _umgebung(dryrun):
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
    return umgebung


def start_script(pfad, dryrun=False, starter=subprocess.Popen):
    """Startet das Skript und kehrt SOFORT zurück. Gibt den Prozess-Handle zurück.

    stdout und stderr laufen zusammen in eine Text-Pipe: die GUI muss dann nur
    einen Leser betreiben, und die Reihenfolge von print und Traceback bleibt
    so erhalten, wie sie im Terminal erschiene.
    """
    skript = Path(pfad).resolve()
    if not skript.exists():
        raise SpotlabError(f"Die Datei {skript} gibt es nicht.")

    return starter(
        [sys.executable, "-u", str(skript)],
        cwd=str(skript.parent),
        env=_umgebung(dryrun),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def run_script(pfad, dryrun=False, starter=subprocess.Popen):
    """Blockierende Variante für die Kommandozeile."""
    prozess = start_script(pfad, dryrun=dryrun, starter=starter)
    if getattr(prozess, "stdout", None) is not None:
        for zeile in prozess.stdout:
            print(zeile, end="")
    return int(prozess.wait())
