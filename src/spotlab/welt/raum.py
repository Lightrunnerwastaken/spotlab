"""Ein Zimmer als Geometrie: Waende, Bloecke, Boeden, Tags.

Reine Standardbibliothek. Das ist kein Zufall, sondern der Grund, warum die GUI
dieses Modul importieren darf: es zieht weder Qt noch bosdyn noch numpy herein,
und die Regel "kein spotlab.backends unterhalb von gui/" bleibt unberuehrt.

Einheiten wie in der Schueler-API: Meter und GRAD, links positiv. Wer
`spot.move(turn=90)` kennt, liest eine Raumdatei ohne Umrechnung.

Fassung 2 (06.09.2026): Waende sind Linien mit Dicke und Hoehe je Raum, Bloecke
sind drehbare Kaesten mit Hoehe, Tags haben eine Haengehoehe. Die alte
Schreibweise `hindernisse = [{rechteck=...}]` wird weiter gelesen; gespeichert
wird immer die neue.

Fassung 3 (06.09.2026): Hoehe. Waende, Bloecke und Tags haben ein `z` (ihre
Unterkante ueber dem Grundboden), und es gibt `Boden`: ein begehbares Rechteck
als Podest, Rampe oder Treppe. Der Start bleibt (x, y, grad) -- seine Hoehe
folgt aus dem Boden darunter (`welt/hoehe.py::boden_bei`). Ein Raum ohne Hoehe
sieht gespeichert genau so aus wie in Fassung 2.
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

# DIE Regel fuer Hoehe: ein Hindernis ist ein Hoehensprung ueber MAX_STUFE_M.
# Kollision (Koerperband, Klippen), das 2D-Gitter und das Tiefengitter der Puppe
# (spotsim/local_grid.py, dieselbe Zahl, geprueft in tests/test_naht_spotsim.py)
# formulieren nur sie. Eine Normstufe von 17 cm liegt darunter, eine Tischkante
# von 75 cm darueber. STUFE_VORGABE_M ist die Steigung, mit der die
# Rekonstruktion Stufen zaehlt -- eine Annahme, sie steht im Bericht.
MAX_STUFE_M = 0.25
STUFE_VORGABE_M = 0.17


def _ecken(x, y, breite, tiefe, drehung):
    """Die vier Ecken eines gedrehten Rechtecks, gegen den Uhrzeigersinn ab links-unten."""
    c = math.cos(math.radians(drehung))
    s = math.sin(math.radians(drehung))
    hb, ht = breite / 2, tiefe / 2
    return tuple(
        (x + lx * c - ly * s, y + lx * s + ly * c)
        for lx, ly in ((-hb, -ht), (hb, -ht), (hb, ht), (-hb, ht))
    )


def _lokal(x, y, drehung, px, py):
    """Ein Weltpunkt im Rahmen eines gedrehten Rechtecks (Mitte = Ursprung)."""
    c = math.cos(math.radians(-drehung))
    s = math.sin(math.radians(-drehung))
    dx, dy = px - x, py - y
    return dx * c - dy * s, dx * s + dy * c


@dataclass(frozen=True)
class Wand:
    """Eine Linie; Dicke und Hoehe gelten je Raum. `z` ist die Unterkante."""

    x1: float
    y1: float
    x2: float
    y2: float
    z: float = 0.0

    def __iter__(self):
        # Vier Werte, wie alle Aufrufer entpacken; die Hoehe fragt man einzeln.
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
    """Ein Kasten: Mitte, Groesse, Drehung um die Hochachse, Unterkante `z`."""

    name: str
    x: float
    y: float
    breite: float        # entlang der eigenen x-Achse
    tiefe: float
    hoehe: float = BLOCK_HOEHE_M
    drehung: float = 0.0  # Grad, links positiv
    z: float = 0.0

    def ecken(self):
        """Die vier Ecken im Weltframe, gegen den Uhrzeigersinn ab links-unten."""
        return _ecken(self.x, self.y, self.breite, self.tiefe, self.drehung)

    def lokal(self, px, py):
        """Ein Weltpunkt im Rahmen des Blocks (Mitte = Ursprung, x entlang der Breite)."""
        return _lokal(self.x, self.y, self.drehung, px, py)


@dataclass(frozen=True)
class Boden:
    """Ein begehbares Rechteck: Podest, Rampe oder Treppe.

    Um die Hochachse gedreht wie ein Block. Entlang der EIGENEN x-Achse steigt
    er von `z` (Kante bei -breite/2) auf `z + anstieg` (Kante bei +breite/2).
    Ohne Anstieg ein Podest, mit Anstieg eine Rampe, mit Anstieg und Stufen
    eine Treppe -- ein Element, drei Erscheinungen, damit Kollision, Gitter,
    Editor und Puppe eine Formulierung teilen.
    """

    name: str
    x: float
    y: float
    breite: float        # entlang der Anstiegsrichtung
    tiefe: float
    z: float = 0.0
    anstieg: float = 0.0
    stufen: int = 0
    drehung: float = 0.0

    def ecken(self):
        return _ecken(self.x, self.y, self.breite, self.tiefe, self.drehung)

    def lokal(self, px, py):
        return _lokal(self.x, self.y, self.drehung, px, py)

    def hoehe_lokal(self, lx):
        """Bodenhoehe an lokaler x-Position -- glatt, auch bei Stufen (der Koerper gleitet)."""
        if self.breite <= 0:
            return self.z
        anteil = min(1.0, max(0.0, lx / self.breite + 0.5))
        return self.z + self.anstieg * anteil

    def stufe_lokal(self, lx):
        """Bodenhoehe als Trittflaeche: die Stufe, auf der lx liegt (ohne Stufen: die Flaeche)."""
        if self.stufen <= 0 or self.breite <= 0:
            return self.hoehe_lokal(lx)
        anteil = min(1.0, max(0.0, lx / self.breite + 0.5))
        nummer = min(self.stufen - 1, int(anteil * self.stufen))
        return self.z + self.anstieg * (nummer + 1) / self.stufen

    @property
    def art(self):
        if self.anstieg == 0.0:
            return "podest"
        return "treppe" if self.stufen > 0 else "rampe"

    @property
    def neigung_grad(self):
        """Neigung der (glatten) Flaeche in Grad; 0 fuer ein Podest."""
        if self.anstieg == 0.0 or self.breite <= 0:
            return 0.0
        return math.degrees(math.atan2(self.anstieg, self.breite))

    @property
    def z_oben(self):
        return self.z + self.anstieg


@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float
    y: float
    grad: float          # Blickrichtung des Tags
    hoehe: float = TAG_HOEHE_M   # Haengehoehe ueber dem Boden, auf dem er steht
    z: float = 0.0               # der Tag haengt bei z + hoehe


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
    boeden: tuple = ()   # Boden, ...

    def __post_init__(self):
        # Tupel aus Tests und alten Aufrufern werden Waende; Listen werden Tupel.
        object.__setattr__(self, "waende", tuple(
            w if isinstance(w, Wand) else Wand(*(float(v) for v in w)) for w in self.waende
        ))
        object.__setattr__(self, "bloecke", tuple(self.bloecke))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "boeden", tuple(self.boeden))
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
    for boden in raum.boeden:
        punkte += list(boden.ecken())
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


def _waende(daten, pfad):
    waende = []
    for wand in daten.get("waende", []):
        werte = [float(w) for w in wand]
        if len(werte) not in (4, 5):
            raise SpotlabError(
                f"In {pfad.name} hat eine Wand {len(werte)} Werte -- erwartet sind "
                f"[x1, y1, x2, y2] oder [x1, y1, x2, y2, z]."
            )
        waende.append(Wand(*werte))
    return tuple(waende)


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
            z=float(b.get("z", 0.0)),
        ))
    return tuple(bloecke)


def _boeden(roh, pfad):
    boeden = []
    for b in roh.get("boden", []):
        mitte = _feld(b, "mitte", pfad, "bei einem [[boden]]")
        groesse = _feld(b, "groesse", pfad, "bei einem [[boden]]")
        boeden.append(Boden(
            name=str(b.get("name", "Boden")),
            x=float(mitte[0]), y=float(mitte[1]),
            breite=float(groesse[0]), tiefe=float(groesse[1]),
            z=float(b.get("z", 0.0)), anstieg=float(b.get("anstieg", 0.0)),
            stufen=int(b.get("stufen", 0)), drehung=float(b.get("drehung", 0.0)),
        ))
    return tuple(boeden)


def raum_laden_pfad(pfad):
    """Einen Raum aus einer Datei laden -- Fassung 1, 2 oder 3."""
    pfad = Path(pfad)
    try:
        roh = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as fehler:
        raise SpotlabError(f"{pfad.name} ist kein gueltiges TOML: {fehler}") from fehler

    daten = roh.get("raum")
    if not isinstance(daten, dict):
        raise SpotlabError(f"In {pfad.name} fehlt der Abschnitt [raum].")

    tags = tuple(
        RaumTag(id=int(t["id"]), x=float(t["pose"][0]), y=float(t["pose"][1]),
                grad=float(t["pose"][2]), hoehe=float(t.get("hoehe", TAG_HOEHE_M)),
                z=float(t.get("z", 0.0)))
        for t in roh.get("tag", [])
    )
    groesse = daten.get("groesse")
    return Raum(
        name=str(_feld(daten, "name", pfad)),
        beschreibung=str(daten.get("beschreibung", "")),
        start=tuple(float(w) for w in _feld(daten, "start", pfad)),
        waende=_waende(daten, pfad),
        bloecke=_bloecke(daten, roh, pfad),
        tags=tags,
        groesse=tuple(float(w) for w in groesse) if groesse is not None else None,
        wand_dicke=float(daten.get("wand_dicke", WAND_DICKE_M)),
        wand_hoehe=float(daten.get("wand_hoehe", WAND_HOEHE_M)),
        boeden=_boeden(roh, pfad),
    )


def raum_laden(name, workspace=None):
    """Einen Raum laden. Der Arbeitsordner geht vor den Vorlagen."""
    return raum_laden_pfad(_pfad(name, workspace))


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
    """Den Raum als TOML schreiben -- immer in der neuen Schreibweise.

    Hoehen stehen nur, wo sie nicht 0 sind, und `[[boden]]` nur, wenn es Boeden
    gibt: ein Raum ohne Hoehe bleibt Zeile fuer Zeile die Datei aus Fassung 2.
    `fassung` sagt, welcher Leser die Datei verstehen muss.
    """
    mit_hoehe = bool(raum.boeden) or any(
        e.z != 0.0 for e in (*raum.waende, *raum.bloecke, *raum.tags)
    )
    zeilen = [
        "[raum]",
        f"name         = {_text(raum.name)}",
    ]
    if mit_hoehe:
        zeilen.append("fassung      = 3")
    zeilen += [
        f"beschreibung = {_text(raum.beschreibung)}",
        f"start        = {_liste(raum.start)}",
    ]
    if raum.groesse is not None:
        zeilen.append(f"groesse      = {_liste(raum.groesse)}")
    zeilen.append(f"wand_dicke   = {_zahl(raum.wand_dicke)}")
    zeilen.append(f"wand_hoehe   = {_zahl(raum.wand_hoehe)}")
    zeilen.append("waende = [")
    for wand in raum.waende:
        werte = (wand.x1, wand.y1, wand.x2, wand.y2) + ((wand.z,) if wand.z != 0.0 else ())
        zeilen.append(f"    {_liste(werte)},")
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
        if block.z != 0.0:
            zeilen.append(f"z       = {_zahl(block.z)}")
    for boden in raum.boeden:
        zeilen += [
            "",
            "[[boden]]",
            f"name    = {_text(boden.name)}",
            f"mitte   = {_liste((boden.x, boden.y))}",
            f"groesse = {_liste((boden.breite, boden.tiefe))}",
            f"z       = {_zahl(boden.z)}",
            f"anstieg = {_zahl(boden.anstieg)}",
            f"stufen  = {int(boden.stufen)}",
            f"drehung = {_zahl(boden.drehung)}",
        ]
    for tag in raum.tags:
        zeilen += [
            "",
            "[[tag]]",
            f"id    = {int(tag.id)}",
            f"pose  = {_liste((tag.x, tag.y, tag.grad))}",
            f"hoehe = {_zahl(tag.hoehe)}",
        ]
        if tag.z != 0.0:
            zeilen.append(f"z     = {_zahl(tag.z)}")
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8", newline="\n")
