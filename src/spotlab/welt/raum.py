"""Ein Zimmer als Geometrie: Waende, Hindernisse, Tags.

Reine Standardbibliothek. Das ist kein Zufall, sondern der Grund, warum die GUI
dieses Modul importieren darf: es zieht weder Qt noch bosdyn noch numpy herein,
und die Regel "kein spotlab.backends unterhalb von gui/" bleibt unberuehrt.

Einheiten wie in der Schueler-API: Meter und GRAD, links positiv. Wer
`spot.move(turn=90)` kennt, liest eine Raumdatei ohne Umrechnung.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError

VORLAGEN = Path(__file__).parent / "vorlagen"


@dataclass(frozen=True)
class Hindernis:
    name: str
    rechteck: tuple      # (x, y, breite, hoehe), achsparallel, Meter


@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float
    y: float
    grad: float          # Blickrichtung des Tags


@dataclass(frozen=True)
class Raum:
    name: str
    beschreibung: str
    groesse: tuple       # (breite, hoehe) in Metern
    start: tuple         # (x, y, grad)
    waende: tuple        # ((x1, y1, x2, y2), …)
    hindernisse: tuple
    tags: tuple


def vorlagen():
    """Die mitgelieferten Raeume, ohne Endung."""
    return sorted(p.stem for p in VORLAGEN.glob("*.toml"))


def _pfad(name, workspace):
    if workspace:
        eigen = Path(workspace) / "raeume" / f"{name}.toml"
        if eigen.is_file():
            return eigen
    mitgeliefert = VORLAGEN / f"{name}.toml"
    if mitgeliefert.is_file():
        return mitgeliefert
    vorhanden = ", ".join(vorlagen())
    raise SpotlabError(
        f"Den Raum '{name}' gibt es nicht. Vorhanden: {vorhanden}. "
        f"Eigene Raeume liegen unter <arbeitsordner>/raeume/<name>.toml."
    )


def _feld(daten, name, pfad):
    if name not in daten:
        raise SpotlabError(f"In {pfad.name} fehlt das Feld '{name}' unter [raum].")
    return daten[name]


def raum_laden(name, workspace=None):
    """Einen Raum laden. Der Arbeitsordner geht vor den Vorlagen."""
    pfad = _pfad(name, workspace)
    try:
        roh = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as fehler:
        raise SpotlabError(f"{pfad.name} ist kein gueltiges TOML: {fehler}") from fehler

    daten = roh.get("raum")
    if not isinstance(daten, dict):
        raise SpotlabError(f"In {pfad.name} fehlt der Abschnitt [raum].")

    hindernisse = tuple(
        Hindernis(name=str(h.get("name", "Hindernis")), rechteck=tuple(h["rechteck"]))
        for h in daten.get("hindernisse", [])
    )
    tags = tuple(
        RaumTag(id=int(t["id"]), x=float(t["pose"][0]),
                y=float(t["pose"][1]), grad=float(t["pose"][2]))
        for t in roh.get("tag", [])
    )
    return Raum(
        name=str(_feld(daten, "name", pfad)),
        beschreibung=str(daten.get("beschreibung", "")),
        groesse=tuple(float(w) for w in _feld(daten, "groesse", pfad)),
        start=tuple(float(w) for w in _feld(daten, "start", pfad)),
        waende=tuple(tuple(float(w) for w in wand)
                     for wand in _feld(daten, "waende", pfad)),
        hindernisse=hindernisse,
        tags=tags,
    )
