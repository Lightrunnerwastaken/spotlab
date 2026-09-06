"""Der Ordner „Beispiele" im Arbeitsordner — immer da, immer in der GUI zu finden.

Die Beispielprogramme liegen als Dateien in DIESEM Paket. Beim Start legt die
GUI `<arbeitsordner>/Beispiele/` als gewöhnliches Projekt an (mit `runs/`, daran
erkennt `projekte_in` ein Projekt) und kopiert hinein, was fehlt. Nur was
fehlt: ändert ein Schüler ein Beispiel, bleibt seine Fassung — löscht er es,
kommt das Original beim nächsten Start wieder.

Warum eine Kopie und kein Verweis auf das Paket: Läufe landen neben dem
Skript unter `runs/`. Direkt aus dem Paket gestartet, lägen sie in
`site-packages` — und ein Schüler, der ein Beispiel ändert, änderte spotlab.
"""

import json
import sys
from importlib import resources
from pathlib import Path

ORDNER = "Beispiele"

# Aus dem Vorlagen-Paket (die beiden, die auch jedes neue Projekt bekommt) und
# aus diesem Paket alles, was kein Python-Modul ist.
VORLAGEN = ("hallo_spot.py", "uebungsraum.py")


def _quellen():
    vorlagen = resources.files("spotlab.workshop.templates")
    for name in VORLAGEN:
        yield name, vorlagen.joinpath(name)
    eigene = resources.files("spotlab.workshop.beispiele")
    for eintrag in sorted(eigene.iterdir(), key=lambda e: e.name):
        if eintrag.name.startswith("__") or eintrag.name.endswith((".pyc",)):
            continue
        if eintrag.name.endswith((".py", ".md")):
            yield eintrag.name, eintrag


def bereitstellen(arbeitsordner):
    """(Ordner, neu kopierte Dateinamen). Wirft nur bei einem unbrauchbaren Pfad."""
    ziel = Path(arbeitsordner) / ORDNER
    (ziel / "runs").mkdir(parents=True, exist_ok=True)
    (ziel / ".vscode").mkdir(exist_ok=True)
    einstellungen = ziel / ".vscode" / "settings.json"
    if not einstellungen.exists():
        einstellungen.write_text(json.dumps({
            "python.defaultInterpreterPath": sys.executable,
            "python.terminal.activateEnvironment": True,
            "files.encoding": "utf8",
        }, indent=2), encoding="utf-8")
    ignorieren = ziel / ".gitignore"
    if not ignorieren.exists():
        ignorieren.write_text("runs/\n__pycache__/\n", encoding="utf-8")

    neu = []
    for name, quelle in _quellen():
        datei = ziel / name
        if datei.exists():
            continue
        datei.write_text(quelle.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        neu.append(name)
    return ziel, neu
