"""Der Anbindungsordner — Ablage und Datenkanal in einem.

<arbeitsordner>/anbindungen/<name>/
    anbindung.json          Manifest-Kopie, Quellpfad, Zeitpunkt
    panels/<name>.json

Registrieren heisst: diesen Ordner anlegen. Etwas zeigen heisst: eine Datei
hineinschreiben. Ein Begriff, nicht zwei.

Das Manifest wird HINEINKOPIERT, nicht nur verlinkt: dann braucht die GUI das
fremde Repo nicht. Ist die Platte ab oder der Ordner umbenannt, bleiben die
Panels sichtbar und nur die Skript-Knoepfe gehen aus.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from spotlab.anbindung.manifest import Manifest, als_json, aus_json, lies
from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name

ORDNER = "anbindungen"
BESCHREIBUNG = "anbindung.json"
PANELS = "panels"


@dataclass(frozen=True)
class Anbindung:
    name: str
    ordner: Path
    manifest: Manifest
    quelle: Path
    angebunden: str
    vorhanden: bool


def wurzel(workspace):
    return Path(workspace) / ORDNER


def panelordner(anbindung):
    return anbindung.ordner / PANELS


def binde_an(workspace, projektpfad, jetzt=None):
    """Liest das Manifest und legt den Anbindungsordner an. Idempotent.

    Erneutes Anbinden erneuert anbindung.json und laesst die Panels stehen —
    ein Agent, der nach jeder Manifestaenderung neu anbindet, verliert nichts.
    """
    manifest = lies(projektpfad)
    ordner = wurzel(workspace) / sicherer_name(manifest.name, ersatz="projekt")
    (ordner / PANELS).mkdir(parents=True, exist_ok=True)
    zeit = (jetzt or datetime.now(UTC)).isoformat()
    (ordner / BESCHREIBUNG).write_text(
        json.dumps(
            {
                "quelle": str(manifest.projekt),
                "angebunden": zeit,
                "manifest": als_json(manifest),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return _lade(ordner)


def anbindungen(workspace):
    try:
        eintraege = sorted(
            (p for p in wurzel(workspace).iterdir() if p.is_dir()), key=lambda p: p.name
        )
    except OSError:
        return []
    gefunden = []
    for eintrag in eintraege:
        geladen = _lade(eintrag)
        if geladen is not None:
            gefunden.append(geladen)
    return gefunden


def finde(workspace, name):
    for anbindung in anbindungen(workspace):
        if anbindung.name == name or anbindung.ordner.name == name:
            return anbindung
    raise SpotlabError(
        f"Es ist kein Projekt namens „{name}“ angebunden. "
        "Bekannte Projekte zeigt die Ansicht „Anbindungen“."
    )


def loese(workspace, name):
    try:
        anbindung = finde(workspace, name)
    except SpotlabError:
        return False
    shutil.rmtree(anbindung.ordner, ignore_errors=True)
    return not anbindung.ordner.exists()


def lauf_verzeichnisse_von(anbindung):
    """Wo die Laeufe dieses Projekts landen.

    start_script startet mit cwd=<skriptordner>, und connect() legt Laeufe unter
    <skriptordner>/runs/ an. Das liegt AUSSERHALB des Arbeitsordners, den der
    RunWatcher durchsucht — ohne diese Ableitung bliebe „Live-Lauf" bei fremden
    Projekten leer, obwohl der Lauf laeuft. Derselbe Fehler wie in Stufe 3.

    Abgeleitet statt gesucht: nur die Ordner, die im Manifest stehen, kein
    rekursives Absuchen fremder Repos.
    """
    gesehen = {}
    for skript in anbindung.manifest.skripte:
        runs = (skript.datei.parent / "runs").resolve()
        gesehen[str(runs)] = runs
    return list(gesehen.values())


def _lade(ordner):
    datei = Path(ordner) / BESCHREIBUNG
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    manifest = aus_json(daten.get("manifest") or {})
    quelle = Path(daten.get("quelle") or "")
    return Anbindung(
        name=manifest.name or Path(ordner).name,
        ordner=Path(ordner),
        manifest=manifest,
        quelle=quelle,
        angebunden=daten.get("angebunden") or "",
        vorhanden=quelle.is_dir(),
    )
