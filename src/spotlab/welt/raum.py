"""Ein Zimmer als Geometrie: Waende, Bloecke, Tags.

Reine Standardbibliothek. Das ist kein Zufall, sondern der Grund, warum die GUI
dieses Modul importieren darf: es zieht weder Qt noch bosdyn noch numpy herein,
und die Regel "kein spotlab.backends unterhalb von gui/" bleibt unberuehrt.

Einheiten wie in der Schueler-API: Meter und GRAD, links positiv. Wer
`spot.move(turn=90)` kennt, liest eine Raumdatei ohne Umrechnung.

Fassung 2 (06.09.2026): Waende sind Linien mit Dicke und Hoehe je Raum, Bloecke
sind drehbare Kaesten mit Hoehe, Tags haben eine Haengehoehe. Die alte
Schreibweise `hindernisse = [{rechteck=...}]` wird weiter gelesen; gespeichert
wird immer die neue.
"""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError

VORLAGEN = Path(__file__).parent / "vorlagen"
EIGENE_ORDNER = "raeume"

# Vorgaben der Geometrie in 3D. Die Vorlagen kennen keine Hoehen -- das sind
# ANNAHMEN: eine Uebungswand von 1 m reicht der Puppe, Bloecke tischhoch, Tags
# auf Kniehoehe (so steht es auch in backends/base.py::richtung).
WAND_DICKE_M = 0.06
WAND_HOEHE_M = 1.0
BLOCK_HOEHE_M = 0.75
TAG_HOEHE_M = 0.30
RAND_M = 0.5           # Rand der Huelle, wenn `groesse` fehlt


@dataclass(frozen=True)
class Wand:
    """Eine Linie; Dicke und Hoehe gelten je Raum."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __iter__(self):
        return iter((self.x1, self.y1, self.x2, self.y2))

    @property
    def laenge(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def mitte(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def winkel(self):
        """Richtung von (x1, y1) nach (x2, y2) in Grad."""
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))


@dataclass(frozen=True)
class Block:
    """Ein Kasten auf dem Boden: Mitte, Groesse, Drehung um die Hochachse."""

    name: str
    x: float
    y: float
    breite: float        # entlang der eigenen x-Achse
    tiefe: float
    hoehe: float = BLOCK_HOEHE_M
    drehung: float = 0.0  # Grad, links positiv

    def ecken(self):
        """Die vier Ecken im Weltframe, gegen den Uhrzeigersinn ab links-unten."""
        c = math.cos(math.radians(self.drehung))
        s = math.sin(math.radians(self.drehung))
        hb, ht = self.breite / 2, self.tiefe / 2
        return tuple(
            (self.x + lx * c - ly * s, self.y + lx * s + ly * c)
            for lx, ly in ((-hb, -ht), (hb, -ht), (hb, ht), (-hb, ht))
        )

    def lokal(self, px, py):
        """Ein Weltpunkt im Rahmen des Blocks (Mitte = Ursprung, x entlang der Breite)."""
        c = math.cos(math.radians(-self.drehung))
        s = math.sin(math.radians(-self.drehung))
        dx, dy = px - self.x, py - self.y
        return dx * c - dy * s, dx * s + dy * c


@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float
    y: float
    grad: float          # Blickrichtung des Tags
    hoehe: float = TAG_HOEHE_M


@dataclass(frozen=True)
class Raum:
    name: str
    beschreibung: str
    start: tuple         # (x, y, grad)
    waende: tuple = ()   # Wand, ...
    bloecke: tuple = ()  # Block, ...
    tags: tuple = ()     # RaumTag, ...
    groesse: tuple | None = None   # (breite, hoehe) oder None -> Huelle
    wand_dicke: float = WAND_DICKE_M
    wand_hoehe: float = WAND_HOEHE_M

    def __post_init__(self):
        # Tupel aus Tests und alten Aufrufern werden Waende; Listen werden Tupel.
        object.__setattr__(self, "waende", tuple(
            w if isinstance(w, Wand) else Wand(*(float(v) for v in w)) for w in self.waende
        ))
        object.__setattr__(self, "bloecke", tuple(self.bloecke))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "start", tuple(float(v) for v in self.start))
        if self.groesse is not None:
            object.__setattr__(self, "groesse", tuple(float(v) for v in self.groesse))


def huelle(raum):
    """(x_min, y_min, x_max, y_max): die Zeichenflaeche.

    Mit `groesse` das Rechteck ab dem Ursprung wie bisher; ohne die Bounding-Box
    aller Elemente plus RAND_M -- eine rekonstruierte Karte hat keine Groesse.
    """
    if raum.groesse is not None:
        return (0.0, 0.0, raum.groesse[0], raum.groesse[1])
    punkte = [(raum.start[0], raum.start[1])]
    for wand in raum.waende:
        punkte += [(wand.x1, wand.y1), (wand.x2, wand.y2)]
    for block in raum.bloecke:
        punkte += list(block.ecken())
    punkte += [(t.x, t.y) for t in raum.tags]
    xs = [p[0] for p in punkte]
    ys = [p[1] for p in punkte]
    return (min(xs) - RAND_M, min(ys) - RAND_M, max(xs) + RAND_M, max(ys) + RAND_M)


def vorlagen():
    """Die mitgelieferten Raeume, ohne Endung."""
    return sorted(p.stem for p in VORLAGEN.glob("*.toml"))


def eigene_raeume(workspace):
    """Die Raeume unter <arbeitsordner>/raeume, ohne Endung."""
    if not workspace:
        return []
    ordner = Path(workspace) / EIGENE_ORDNER
    if not ordner.is_dir():
        return []
    return sorted(p.stem for p in ordner.glob("*.toml"))


def raum_pfad(workspace, name):
    """Wo ein eigener Raum dieses Namens liegt (oder liegen wird)."""
    return Path(workspace) / EIGENE_ORDNER / f"{name}.toml"


def _pfad(name, workspace):
    if workspace:
        eigen = raum_pfad(workspace, name)
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


def _feld(daten, name, pfad, wo="unter [raum]"):
    if name not in daten:
        raise SpotlabError(f"In {pfad.name} fehlt das Feld '{name}' {wo}.")
    return daten[name]


def _bloecke(daten, roh, pfad):
    bloecke = []
    # Alte Schreibweise: achsparallele Rechtecke, tischhoch.
    for h in daten.get("hindernisse", []):
        x, y, breite, hoehe = (float(v) for v in h["rechteck"])
        bloecke.append(Block(
            name=str(h.get("name", "Hindernis")),
            # Auf 4 Stellen gerundet, wie `raum_speichern` schreibt -- sonst ist ein
            # geladener und wieder gespeicherter Raum nicht mehr derselbe.
            x=round(x + breite / 2, 4), y=round(y + hoehe / 2, 4), breite=breite, tiefe=hoehe,
            hoehe=BLOCK_HOEHE_M, drehung=0.0,
        ))
    for b in roh.get("block", []):
        mitte = _feld(b, "mitte", pfad, "bei einem [[block]]")
        groesse = _feld(b, "groesse", pfad, "bei einem [[block]]")
        bloecke.append(Block(
            name=str(b.get("name", "Block")),
            x=float(mitte[0]), y=float(mitte[1]),
            breite=float(groesse[0]), tiefe=float(groesse[1]),
            hoehe=float(groesse[2]) if len(groesse) > 2 else BLOCK_HOEHE_M,
            drehung=float(b.get("drehung", 0.0)),
        ))
    return tuple(bloecke)


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

    tags = tuple(
        RaumTag(id=int(t["id"]), x=float(t["pose"][0]), y=float(t["pose"][1]),
                grad=float(t["pose"][2]), hoehe=float(t.get("hoehe", TAG_HOEHE_M)))
        for t in roh.get("tag", [])
    )
    groesse = daten.get("groesse")
    return Raum(
        name=str(_feld(daten, "name", pfad)),
        beschreibung=str(daten.get("beschreibung", "")),
        start=tuple(float(w) for w in _feld(daten, "start", pfad)),
        waende=tuple(Wand(*(float(w) for w in wand)) for wand in daten.get("waende", [])),
        bloecke=_bloecke(daten, roh, pfad),
        tags=tags,
        groesse=tuple(float(w) for w in groesse) if groesse is not None else None,
        wand_dicke=float(daten.get("wand_dicke", WAND_DICKE_M)),
        wand_hoehe=float(daten.get("wand_hoehe", WAND_HOEHE_M)),
    )


# ------------------------------------------------------------------ Speichern
#
# tomllib liest nur. Der Schreiber deckt genau das ab, was ein Raum braucht:
# Zeichenketten, Zahlen, Zahlenlisten, Tabellen-Arrays.


def _zahl(wert):
    text = f"{float(wert):.4f}".rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        text = "0"
    return text if "." in text else text + ".0"


def _text(wert):
    return '"' + str(wert).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _liste(werte):
    return "[" + ", ".join(_zahl(w) for w in werte) + "]"


def raum_speichern(raum, pfad):
    """Den Raum als TOML schreiben -- immer in der neuen Schreibweise."""
    zeilen = [
        "[raum]",
        f"name         = {_text(raum.name)}",
        f"beschreibung = {_text(raum.beschreibung)}",
        f"start        = {_liste(raum.start)}",
    ]
    if raum.groesse is not None:
        zeilen.append(f"groesse      = {_liste(raum.groesse)}")
    zeilen.append(f"wand_dicke   = {_zahl(raum.wand_dicke)}")
    zeilen.append(f"wand_hoehe   = {_zahl(raum.wand_hoehe)}")
    zeilen.append("waende = [")
    for wand in raum.waende:
        zeilen.append(f"    {_liste(wand)},")
    zeilen.append("]")
    for block in raum.bloecke:
        zeilen += [
            "",
            "[[block]]",
            f"name    = {_text(block.name)}",
            f"mitte   = {_liste((block.x, block.y))}",
            f"groesse = {_liste((block.breite, block.tiefe, block.hoehe))}",
            f"drehung = {_zahl(block.drehung)}",
        ]
    for tag in raum.tags:
        zeilen += [
            "",
            "[[tag]]",
            f"id    = {int(tag.id)}",
            f"pose  = {_liste((tag.x, tag.y, tag.grad))}",
            f"hoehe = {_zahl(tag.hoehe)}",
        ]
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8", newline="\n")
