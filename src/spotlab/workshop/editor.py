"""Projekt im Editor öffnen.

Windows-Fallstrick, der hier gelöst wird: Python startet Prozesse über
CreateProcess. Das durchsucht zwar den PATH, hängt beim Suchen aber nur `.exe`
an und wertet PATHEXT NICHT aus. VS Code liefert `code.cmd`, kein `code.exe` —
in jeder Shell funktioniert `code`, aus subprocess heraus nicht.

Deshalb wird der Befehl zuerst mit shutil.which() aufgelöst (das kennt PATHEXT)
und dann mit vollem Pfad gestartet.
"""

import shutil
import subprocess
from pathlib import Path

from spotlab.errors import SpotlabError


def finde_editor(command, sucher=shutil.which):
    """Vollen Pfad zum Editor-Befehl, oder None.

    Ein bereits vollständiger Pfad wird durchgereicht (damit man in
    config.toml unter [editor] command auch ein Programm ausserhalb des PATH
    eintragen kann); ein blosser Name wird über den PATH aufgelöst.
    """
    kandidat = Path(command)
    if kandidat.is_absolute() or any(z in command for z in ("/", "\\")):
        return str(kandidat) if kandidat.exists() else None
    return sucher(command)


def open_in_editor(pfad, command="code", starter=subprocess.run, sucher=shutil.which):
    ziel = Path(pfad)
    aufgeloest = finde_editor(command, sucher)
    if aufgeloest is None:
        raise SpotlabError(
            f"'{command}' wurde nicht gefunden. Ist VS Code installiert?\n"
            f"Falls ja: in VS Code F1 drücken und "
            f"\"Shell Command: Install 'code' command in PATH\" ausführen.\n"
            f"Sonst den Ordner {ziel} von Hand öffnen — oder in "
            f"~/.spotlab/config.toml unter [editor] command den vollen Pfad zum "
            f"Programm eintragen."
        )
    try:
        starter([aufgeloest, str(ziel)], shell=False, check=False)
    except OSError as fehler:
        raise SpotlabError(
            f"'{aufgeloest}' liess sich nicht starten: {fehler}. "
            f"Öffne den Ordner {ziel} von Hand."
        ) from fehler
