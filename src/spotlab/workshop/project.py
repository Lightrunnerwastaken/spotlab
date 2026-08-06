"""Ein neues Schülerprojekt anlegen — vollständig, nicht als leeres Gerüst."""

import json
import re
import sys
from importlib import resources
from pathlib import Path

PROJEKT_DATEIEN = ("hallo_spot.py", "README.md", ".vscode/settings.json")

README = """# {name}

Ein Spot-Projekt.

## Losfahren

```
spotlab doctor          # prüft Netz, Anmeldung, Not-Aus, Lease, Akku
spotlab run hallo_spot.py
```

Oder in VS Code `hallo_spot.py` öffnen und F5 drücken — der Lauf wird so oder so
in `runs/` aufgezeichnet.

## Ohne Roboter üben

```
spotlab run hallo_spot.py --dryrun
```

Baut und prüft alle Kommandos, bewegt aber nichts. Kameras gibt es dabei nicht.

## Läufe ansehen

```
spotlab runs
```
"""


def _sicherer_name(name):
    sauber = re.sub(r"[^\w.-]+", "-", name.strip()).strip("-.")
    return sauber or "spot-projekt"


def create_project(name, wurzel=None):
    wurzel = Path(wurzel) if wurzel else Path.cwd()
    ordner = wurzel / _sicherer_name(name)
    if ordner.exists():
        raise FileExistsError(f"Den Ordner {ordner} gibt es schon. Wähle einen anderen Namen.")

    (ordner / ".vscode").mkdir(parents=True)
    (ordner / "runs").mkdir()

    vorlage = resources.files("spotlab.workshop.templates").joinpath("hallo_spot.py")
    (ordner / "hallo_spot.py").write_text(
        vorlage.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (ordner / "README.md").write_text(README.format(name=ordner.name), encoding="utf-8")
    (ordner / ".vscode" / "settings.json").write_text(
        json.dumps(
            {
                "python.defaultInterpreterPath": sys.executable,
                "python.terminal.activateEnvironment": True,
                "files.encoding": "utf8",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (ordner / ".gitignore").write_text("runs/\n__pycache__/\n", encoding="utf-8")
    return ordner
