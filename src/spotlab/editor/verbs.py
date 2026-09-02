"""Die eigene API als Vorschlagsliste — gelesen, nicht importiert.

api/spot.py zieht ueber motion/posture/state/perception bosdyn, numpy und
Pillow herein. Ein Import waere der bequeme Weg und ketten den Editor an das
SDK. Mit ast bleibt die Vervollstaendigung auch dort brauchbar, wo das SDK
gar nicht installiert ist, und hat keine Seiteneffekte.

Die Quelldateien werden ueber reine Pfadarithmetik gefunden: editor/ und api/
sind Geschwister unter src/spotlab/. Kein Import, keine Ladereihenfolge.
"""

import ast
import functools
import re
from dataclasses import dataclass
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
SPOT_QUELLE = WURZEL / "api" / "spot.py"
PAKET_QUELLE = WURZEL / "__init__.py"

ZIELE = ("spot", "spotlab")
ZIEL_MUSTER = re.compile(r"(?P<ziel>[A-Za-z_][A-Za-z_0-9]*)\.[A-Za-z_0-9]*$")


@dataclass(frozen=True)
class Vorschlag:
    name: str
    signatur: str   # "move(forward=0.0, left=0.0, ...)" — bei @property nur der Name
    hilfe: str      # erste Docstring-Zeile, deutsch; "" wenn keine
    art: str = ""   # "methode" | "eigenschaft" | jedi-Arten; steuert das Icon


def _erste_zeile(knoten):
    text = (ast.get_docstring(knoten) or "").strip()
    return text.splitlines()[0].strip() if text else ""


def _ist_property(knoten):
    return any(
        isinstance(d, ast.Name) and d.id == "property" for d in knoten.decorator_list
    )


def _vorschlag(knoten):
    if _ist_property(knoten):
        # Eine Eigenschaft mit Klammern anzuzeigen waere eine Falle.
        return Vorschlag(knoten.name, knoten.name, _erste_zeile(knoten), "eigenschaft")
    try:
        args = ast.unparse(knoten.args)
    except Exception:
        args = ""
    args = args.removeprefix("self").removeprefix(", ")
    return Vorschlag(knoten.name, f"{knoten.name}({args})", _erste_zeile(knoten), "methode")


def _oeffentliche(koerper):
    for knoten in koerper:
        passend = isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
        if passend and not knoten.name.startswith("_"):
            yield _vorschlag(knoten)


def _baum(quelltext):
    try:
        return ast.parse(quelltext)
    except (SyntaxError, ValueError):
        return None


def methoden(quelltext, klasse):
    baum = _baum(quelltext)
    if baum is None:
        return []
    for knoten in baum.body:
        if isinstance(knoten, ast.ClassDef) and knoten.name == klasse:
            return list(_oeffentliche(knoten.body))
    return []


def funktionen(quelltext):
    baum = _baum(quelltext)
    return [] if baum is None else list(_oeffentliche(baum.body))


def _lies(pfad):
    try:
        return pfad.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


@functools.lru_cache(maxsize=1)
def spot_verben():
    return tuple(methoden(_lies(SPOT_QUELLE), "Spot"))


@functools.lru_cache(maxsize=1)
def spotlab_verben():
    return tuple(funktionen(_lies(PAKET_QUELLE)))


def praefix(text_vor_cursor):
    """Das Ziel links vom Punkt — oder None.

    Eine Namensregel, keine Inferenz, und das soll sie sein: unsere Vorlage
    schreibt `with spotlab.connect() as spot:`, und praktisch jedes
    Schuelerskript uebernimmt das. Wer die Variable `roboter` nennt, bekommt
    von uns nichts — dort greift jedi, das den Typ wirklich herleiten kann.
    """
    zeile = text_vor_cursor.rsplit("\n", 1)[-1]
    if "#" in zeile:
        # Grob, aber in die sichere Richtung: `print("# spot.")` verliert nur
        # einen Vorschlag, statt einen im Kommentar aufzudraengen.
        return None
    treffer = ZIEL_MUSTER.search(zeile)
    if treffer is None:
        return None
    ziel = treffer.group("ziel")
    return ziel if ziel in ZIELE else None


def teilwort(text_vor_cursor):
    """Das angefangene Wort am Cursor — der Praefix fuer die Filterung."""
    zeile = text_vor_cursor.rsplit("\n", 1)[-1]
    ende = len(zeile)
    while ende > 0 and (zeile[ende - 1].isalnum() or zeile[ende - 1] == "_"):
        ende -= 1
    return zeile[ende:]
