"""Die Beschreibung eines fremden Projekts.

Sie liegt im fremden Repo und nicht in spotlabs Arbeitsordner: dort gehoert sie
hin, dort liegt sie in git, und wer das Repo klont, bekommt die Anbindung mit.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError

DATEINAME = "spotlab.toml"


class ManifestFehler(SpotlabError):
    """Nennt immer Datei UND Feld — sonst sucht man in der falschen Zeile."""


@dataclass(frozen=True)
class Skript:
    name: str
    datei: Path             # absolut, gegen das Projektverzeichnis aufgeloest
    argumente: tuple
    roboter: bool           # faehrt dieses Skript den echten Spot?
    beschreibung: str


@dataclass(frozen=True)
class Manifest:
    name: str
    beschreibung: str
    projekt: Path
    skripte: tuple


def lies(projektpfad):
    """Liest <projektpfad>/spotlab.toml. Wirft ManifestFehler mit deutschem Text."""
    projekt = Path(projektpfad).resolve()
    datei = projekt / DATEINAME
    if not datei.is_file():
        raise ManifestFehler(
            f"In {projekt} liegt keine {DATEINAME}. Lege sie dort an, damit spotlab "
            "das Projekt anbinden kann."
        )
    try:
        roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as fehler:
        raise ManifestFehler(f"{datei} liess sich nicht lesen: {fehler}") from fehler

    kopf = roh.get("projekt") or {}
    name = str(kopf.get("name") or "").strip()
    if not name:
        raise ManifestFehler(f"In {datei} fehlt unter [projekt] das Feld `name`.")

    skripte = tuple(
        _skript(eintrag, nummer, projekt, datei)
        for nummer, eintrag in enumerate(roh.get("skript") or [], start=1)
    )
    return Manifest(
        name=name,
        beschreibung=str(kopf.get("beschreibung") or ""),
        projekt=projekt,
        skripte=skripte,
    )


def _skript(eintrag, nummer, projekt, datei):
    name = str(eintrag.get("name") or "").strip()
    if not name:
        raise ManifestFehler(f"In {datei} fehlt bei Skript {nummer} das Feld `name`.")
    roh_datei = str(eintrag.get("datei") or "").strip()
    if not roh_datei:
        raise ManifestFehler(
            f"In {datei} fehlt bei Skript {nummer} („{name}“) das Feld `datei`."
        )
    argumente = eintrag.get("argumente") or []
    if not all(isinstance(a, str) for a in argumente):
        raise ManifestFehler(
            f"In {datei} müssen bei Skript {nummer} („{name}“) alle `argumente` Texte "
            'sein — auch Zahlen, also ["--episoden", "20"].'
        )
    return Skript(
        name=name,
        datei=(projekt / roh_datei).resolve(),
        argumente=tuple(argumente),
        # Kein Standardwert True: das machte den haeufigen Fall zur Ausnahme, und
        # Leute schrieben ueberall roboter = false hin, ohne nachzudenken. Die
        # Sicherheit haengt an der Schranke in spotlab/__init__.py, nicht hier.
        roboter=bool(eintrag.get("roboter", False)),
        beschreibung=str(eintrag.get("beschreibung") or ""),
    )


def als_json(manifest):
    return {
        "name": manifest.name,
        "beschreibung": manifest.beschreibung,
        "projekt": str(manifest.projekt),
        "skripte": [
            {
                "name": s.name,
                "datei": str(s.datei),
                "argumente": list(s.argumente),
                "roboter": s.roboter,
                "beschreibung": s.beschreibung,
            }
            for s in manifest.skripte
        ],
    }


def aus_json(daten):
    return Manifest(
        name=daten.get("name", ""),
        beschreibung=daten.get("beschreibung", ""),
        projekt=Path(daten.get("projekt", "")),
        skripte=tuple(
            Skript(
                name=s.get("name", ""),
                datei=Path(s.get("datei", "")),
                argumente=tuple(s.get("argumente") or ()),
                roboter=bool(s.get("roboter", False)),
                beschreibung=s.get("beschreibung", ""),
            )
            for s in daten.get("skripte") or []
        ),
    )


def skript_von(manifest, name):
    for skript in manifest.skripte:
        if skript.name == name:
            return skript
    return None
