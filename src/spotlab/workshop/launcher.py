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
ENV_NUR_TROCKEN = "SPOTLAB_NUR_TROCKEN"


def _umgebung(dryrun, nur_trocken=False, backend=None):
    umgebung = dict(os.environ)
    # `backend` schlaegt `dryrun`: jenes ist nur die aeltere Schreibweise fuer
    # denselben Schalter. Ohne beides bleibt die Variable WEG -- dann
    # entscheidet `default_backend` aus der Konfiguration, wie bisher.
    name = backend or ("dryrun" if dryrun else None)
    if name:
        umgebung[ENV_BACKEND] = name
    if nur_trocken:
        # Obergrenze: connect() weist damit auch ein explizites backend="real" ab.
        umgebung[ENV_NUR_TROCKEN] = "1"

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


def start_script(
    pfad, dryrun=False, argumente=(), nur_trocken=False, starter=subprocess.Popen,
    ausgabe=None, backend=None,
):
    """Startet das Skript und kehrt SOFORT zurück. Gibt den Prozess-Handle zurück.

    stdout und stderr laufen zusammen: die GUI muss dann nur einen Leser
    betreiben, und die Reihenfolge von print und Traceback bleibt so erhalten,
    wie sie im Terminal erschiene.

    `ausgabe` ist für Aufrufer, die NICHT mitlesen. Ohne sie schreibt der
    Prozess in eine Pipe, und wer die Pipe nicht leert, lässt das Skript beim
    vollen Puffer (unter Windows rund 64 KB) für immer stehenbleiben — ohne
    Fehler, ohne Ende, mitten in einer Bewegung. Genau das tat der MCP-Server.
    Wird eine offene Datei übergeben, geht die Ausgabe dorthin und es gibt
    keinen Puffer, der volllaufen kann.

    `argumente` wird als Liste an den Prozess gereicht, nie über eine Shell
    zusammengesetzt. `nur_trocken` setzt die Obergrenze aus __init__.py.

    `backend` nennt das Backend beim Namen ("real", "dryrun", "sim") und ist
    der Weg der GUI; `dryrun=True` bleibt die Kurzform für "dryrun".
    """
    skript = Path(pfad).resolve()
    if not skript.exists():
        raise SpotlabError(f"Die Datei {skript} gibt es nicht.")

    return starter(
        [sys.executable, "-u", str(skript), *argumente],
        cwd=str(skript.parent),
        env=_umgebung(dryrun, nur_trocken=nur_trocken, backend=backend),
        stdout=subprocess.PIPE if ausgabe is None else ausgabe,
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
