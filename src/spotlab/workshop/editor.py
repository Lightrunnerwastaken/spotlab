"""Projekt im Editor öffnen."""

import subprocess
from pathlib import Path

from spotlab.errors import SpotlabError


def open_in_editor(pfad, command="code", starter=subprocess.run):
    ziel = Path(pfad)
    try:
        starter([command, str(ziel)], shell=False, check=False)
    except FileNotFoundError as fehler:
        raise SpotlabError(
            f"'{command}' wurde nicht gefunden. In VS Code F1 drücken und "
            f"\"Shell Command: Install 'code' command in PATH\" ausführen — "
            f"oder den Ordner {ziel} von Hand öffnen."
        ) from fehler
