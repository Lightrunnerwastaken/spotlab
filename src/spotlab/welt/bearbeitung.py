"""Einen Raum bearbeiten -- reine Funktionen, ohne Qt.

Der `Raum` ist unveraenderlich; jede Operation gibt einen neuen zurueck. Damit
ist Rueckgaengig eine Liste von Schnappschuessen (`Verlauf`), und die Griffe
der 2D-Sicht, die Blender-Tasten (`Modus`) und die Zahlenfelder rufen dieselben
Funktionen. Alles hier ist ohne Fenster testbar -- und Standardbibliothek, wie
der Rest von `welt/`.

Ein Element wird ueber einen Schluessel angesprochen:
    ("wand", i)  ("block", i)  ("tag", i)  ("start",)  ("raum",)
Eine Auswahl ist ein frozenset solcher Schluessel. Indizes gelten fuer den Raum,
aus dem sie stammen: `loesche` gibt deshalb die leere Auswahl zurueck.
"""

import math
from dataclasses import replace

from spotlab.welt.kollision import abstand_block, hindernis_bei
from spotlab.welt.raum import BLOCK_HOEHE_M, MAX_STUFE_M, Block, Boden, RaumTag, Wand

RASTER_M = 0.05
RASTER_GRAD = 5.0
FANG_M = 0.10            # Wandenden fangen sich an anderen Wandenden
MINDESTKANTE_M = 0.05
GRIFF_RADIUS_M = 0.15    # Treffer fuer Tag und Start
VERSATZ_KOPIE_M = 0.5
RING_ABSTAND_M = 0.3     # Drehring: so weit ausserhalb des Blocks
PFEIL_M = 0.4            # Richtungsgriff von Tag und Start
START = ("start",)
RAUM = ("raum",)

FELDER = {
    "wand": ("x1", "y1", "x2", "y2", "z"),
    "block": ("name", "x", "y", "breite", "tiefe", "hoehe", "drehung", "z"),
    "boden": ("name", "x", "y", "breite", "tiefe", "z", "anstieg", "stufen", "drehung"),
    "tag": ("id", "x", "y", "grad", "hoehe", "z"),
    "start": ("x", "y", "grad"),
    "raum": ("name", "beschreibung", "wand_dicke", "wand_hoehe"),
}


def raste(wert, raster=RASTER_M):
    return round(wert / raster) * raster


def _drehe_punkt(x, y, um, grad):
    c, s = math.cos(math.radians(grad)), math.sin(math.radians(grad))
    dx, dy = x - um[0], y - um[1]
    return um[0] + dx * c - dy * s, um[1] + dx * s + dy * c


# ------------------------------------------------------------- Zugriff


def element(raum, schluessel):
    art = schluessel[0]
    if art == "wand":
        return raum.waende[schluessel[1]]
    if art == "block":
        return raum.bloecke[schluessel[1]]
    if art == "boden":
        return raum.boeden[schluessel[1]]
    if art == "tag":
        return raum.tags[schluessel[1]]
    if art == "start":
        return raum.start
    return raum


def lage(raum, schluessel):
    e = element(raum, schluessel)
    art = schluessel[0]
    if art == "wand":
        return e.mitte
    if art in ("block", "boden", "tag"):
        return (e.x, e.y)
    if art == "start":
        return (e[0], e[1])
    return (0.0, 0.0)


def mitte(raum, auswahl):
    """Mitte der Auswahl -- Drehpunkt fuer Drehen und Skalieren."""
    if not auswahl:
        return (raum.start[0], raum.start[1])
    lagen = [lage(raum, s) for s in sorted(auswahl)]
    return (sum(p[0] for p in lagen) / len(lagen), sum(p[1] for p in lagen) / len(lagen))


def _ersetze(raum, schluessel, neu):
    art = schluessel[0]
    if art == "wand":
        waende = list(raum.waende)
        waende[schluessel[1]] = neu
        return replace(raum, waende=tuple(waende))
    if art == "block":
        bloecke = list(raum.bloecke)
        bloecke[schluessel[1]] = neu
        return replace(raum, bloecke=tuple(bloecke))
    if art == "boden":
        boeden = list(raum.boeden)
        boeden[schluessel[1]] = neu
        return replace(raum, boeden=tuple(boeden))
    if art == "tag":
        tags = list(raum.tags)
        tags[schluessel[1]] = neu
        return replace(raum, tags=tuple(tags))
    if art == "start":
        return replace(raum, start=tuple(neu))
    return neu


def _kante(wert):
    return max(float(wert), MINDESTKANTE_M)


# ---------------------------------------------------------- Operationen


def verschiebe(raum, auswahl, dx, dy):
    for s in auswahl:
        e = element(raum, s)
        if s[0] == "wand":
            neu = replace(e, x1=e.x1 + dx, y1=e.y1 + dy, x2=e.x2 + dx, y2=e.y2 + dy)
        elif s[0] in ("block", "boden", "tag"):
            neu = replace(e, x=e.x + dx, y=e.y + dy)
        elif s[0] == "start":
            neu = (e[0] + dx, e[1] + dy, e[2])
        else:
            continue
        raum = _ersetze(raum, s, neu)
    return raum


def hebe(raum, auswahl, dz):
    """Die Auswahl um `dz` in der Hoehe -- Blender "G, dann Z". Der Start bleibt:
    seine Hoehe folgt aus dem Boden unter ihm."""
    for s in auswahl:
        if s[0] not in ("wand", "block", "boden", "tag"):
            continue
        e = element(raum, s)
        raum = _ersetze(raum, s, replace(e, z=e.z + dz))
    return raum


def drehe(raum, auswahl, grad, um=None):
    """Um `um` (Vorgabe: Mitte der Auswahl); Waende drehen ihre Enden, Bloecke,
    Tags und Start ausserdem ihre eigene Richtung."""
    um = um if um is not None else mitte(raum, auswahl)
    for s in auswahl:
        e = element(raum, s)
        if s[0] == "wand":
            a = _drehe_punkt(e.x1, e.y1, um, grad)
            z = _drehe_punkt(e.x2, e.y2, um, grad)
            neu = replace(e, x1=a[0], y1=a[1], x2=z[0], y2=z[1])
        elif s[0] in ("block", "boden"):
            x, y = _drehe_punkt(e.x, e.y, um, grad)
            neu = replace(e, x=x, y=y, drehung=(e.drehung + grad) % 360.0)
        elif s[0] == "tag":
            x, y = _drehe_punkt(e.x, e.y, um, grad)
            neu = replace(e, x=x, y=y, grad=(e.grad + grad) % 360.0)
        elif s[0] == "start":
            x, y = _drehe_punkt(e[0], e[1], um, grad)
            neu = (x, y, (e[2] + grad) % 360.0)
        else:
            continue
        raum = _ersetze(raum, s, neu)
    return raum


def skaliere(raum, auswahl, fx, fy, fz=1.0, um=None):
    """Lagen um `um` strecken; Bloecke ausserdem in Breite (fx), Tiefe (fy) und Hoehe (fz)."""
    um = um if um is not None else mitte(raum, auswahl)

    def p(x, y):
        return um[0] + (x - um[0]) * fx, um[1] + (y - um[1]) * fy

    for s in auswahl:
        e = element(raum, s)
        if s[0] == "wand":
            a, z = p(e.x1, e.y1), p(e.x2, e.y2)
            neu = replace(e, x1=a[0], y1=a[1], x2=z[0], y2=z[1])
        elif s[0] == "block":
            x, y = p(e.x, e.y)
            neu = replace(e, x=x, y=y, breite=_kante(e.breite * fx),
                          tiefe=_kante(e.tiefe * fy), hoehe=_kante(e.hoehe * fz))
        elif s[0] == "boden":
            # Der Anstieg bleibt: eine laengere Rampe wird flacher, nicht hoeher.
            x, y = p(e.x, e.y)
            neu = replace(e, x=x, y=y, breite=_kante(e.breite * fx), tiefe=_kante(e.tiefe * fy))
        elif s[0] == "tag":
            x, y = p(e.x, e.y)
            neu = replace(e, x=x, y=y)
        elif s[0] == "start":
            x, y = p(e[0], e[1])
            neu = (x, y, e[2])
        else:
            continue
        raum = _ersetze(raum, s, neu)
    return raum


def _freie_nummer(belegt):
    belegt = set(belegt)
    n = 1
    while n in belegt:
        n += 1
    return n


def dupliziere(raum, auswahl):
    """(Raum, neue Auswahl): Kopien VERSATZ_KOPIE_M nach rechts oben, angehaengt."""
    d = VERSATZ_KOPIE_M
    waende, bloecke, tags = list(raum.waende), list(raum.bloecke), list(raum.tags)
    boeden = list(raum.boeden)
    neue = set()
    for s in sorted(auswahl):
        e = element(raum, s)
        if s[0] == "wand":
            waende.append(replace(e, x1=e.x1 + d, y1=e.y1 + d, x2=e.x2 + d, y2=e.y2 + d))
            neue.add(("wand", len(waende) - 1))
        elif s[0] == "block":
            bloecke.append(replace(e, x=e.x + d, y=e.y + d, name=f"{e.name} Kopie"))
            neue.add(("block", len(bloecke) - 1))
        elif s[0] == "boden":
            boeden.append(replace(e, x=e.x + d, y=e.y + d, name=f"{e.name} Kopie"))
            neue.add(("boden", len(boeden) - 1))
        elif s[0] == "tag":
            tags.append(replace(e, x=e.x + d, y=e.y + d, id=_freie_nummer(t.id for t in tags)))
            neue.add(("tag", len(tags) - 1))
    return (
        replace(raum, waende=tuple(waende), bloecke=tuple(bloecke), tags=tuple(tags),
                boeden=tuple(boeden)),
        frozenset(neue),
    )


def loesche(raum, auswahl):
    """(Raum, leere Auswahl). Der Start bleibt immer."""
    weg = {s for s in auswahl if s[0] in ("wand", "block", "boden", "tag")}
    return replace(
        raum,
        waende=tuple(w for i, w in enumerate(raum.waende) if ("wand", i) not in weg),
        bloecke=tuple(b for i, b in enumerate(raum.bloecke) if ("block", i) not in weg),
        boeden=tuple(b for i, b in enumerate(raum.boeden) if ("boden", i) not in weg),
        tags=tuple(t for i, t in enumerate(raum.tags) if ("tag", i) not in weg),
    ), frozenset()


def neue_wand(raum, x1, y1, x2, y2, z=0.0):
    waende = raum.waende + (Wand(float(x1), float(y1), float(x2), float(y2), float(z)),)
    return replace(raum, waende=waende), ("wand", len(waende) - 1)


def _freier_name(vorhandene, stamm):
    nummern = set()
    for name in vorhandene:
        teile = name.split()
        if len(teile) == 2 and teile[0] == stamm and teile[1].isdigit():
            nummern.add(int(teile[1]))
    return f"{stamm} {_freie_nummer(nummern)}"


def neuer_block(raum, x, y, breite, tiefe, hoehe=BLOCK_HOEHE_M, name=None, z=0.0):
    if name is None:
        name = _freier_name((b.name for b in raum.bloecke), "Block")
    block = Block(name, float(x), float(y), _kante(breite), _kante(tiefe), _kante(hoehe),
                  z=float(z))
    bloecke = raum.bloecke + (block,)
    return replace(raum, bloecke=bloecke), ("block", len(bloecke) - 1)


def neuer_boden(raum, x, y, breite, tiefe, z=0.0, anstieg=0.0, stufen=0, name=None):
    """Ein Podest; Anstieg und Stufen machen daraus im Zahlenfeld eine Rampe oder Treppe."""
    if name is None:
        name = _freier_name((b.name for b in raum.boeden), "Boden")
    boden = Boden(name, float(x), float(y), _kante(breite), _kante(tiefe),
                  z=float(z), anstieg=float(anstieg), stufen=max(0, int(stufen)))
    boeden = raum.boeden + (boden,)
    return replace(raum, boeden=boeden), ("boden", len(boeden) - 1)


def neuer_tag(raum, x, y, grad=0.0, z=0.0):
    tag = RaumTag(_freie_nummer(t.id for t in raum.tags), float(x), float(y), float(grad),
                  z=float(z))
    tags = raum.tags + (tag,)
    return replace(raum, tags=tags), ("tag", len(tags) - 1)


def setze_start(raum, x, y, grad):
    return replace(raum, start=(float(x), float(y), float(grad)))


def setze_feld(raum, schluessel, feld, wert):
    """Ein Zahlen- oder Textfeld setzen -- der Weg der Eigenschaften-Felder."""
    art = schluessel[0]
    if feld not in FELDER.get(art, ()):
        raise ValueError(f"Ein Element der Art '{art}' hat kein Feld '{feld}'.")
    e = element(raum, schluessel)
    if art == "start":
        werte = {"x": e[0], "y": e[1], "grad": e[2]}
        werte[feld] = float(wert)
        return replace(raum, start=(werte["x"], werte["y"], werte["grad"] % 360.0))
    if feld in ("breite", "tiefe", "hoehe", "wand_dicke", "wand_hoehe"):
        wert = _kante(wert)
    elif feld in ("name", "beschreibung"):
        wert = str(wert)
    elif feld == "id":
        wert = int(wert)
    elif feld == "stufen":
        wert = int(wert)
        if wert < 0:
            raise ValueError("Stufen koennen nicht negativ sein.")
    elif feld in ("drehung", "grad"):
        wert = float(wert) % 360.0
    else:
        wert = float(wert)
    return _ersetze(raum, schluessel, replace(e, **{feld: wert}))


# ------------------------------------------------- Rasten, Fang, Treffer


def _abstand_strecke(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / laenge2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def fange_ende(raum, x, y, ausser=None):
    """Der naechste fremde Wandendpunkt innerhalb FANG_M, sonst (x, y) selbst."""
    beste, bester_abstand = (x, y), FANG_M
    for i, wand in enumerate(raum.waende):
        if ausser is not None and ausser == ("wand", i):
            continue
        for ex, ey in ((wand.x1, wand.y1), (wand.x2, wand.y2)):
            d = math.hypot(ex - x, ey - y)
            if d < bester_abstand:
                beste, bester_abstand = (ex, ey), d
    return beste


_RANG = {"start": 0, "tag": 1, "block": 2, "boden": 3, "wand": 4}


def treffer(raum, x, y, toleranz=0.1):
    """Der Schluessel unter dem Zeiger oder None. Das Kleinere liegt oben."""
    kandidaten = []
    d = math.hypot(raum.start[0] - x, raum.start[1] - y)
    if d <= GRIFF_RADIUS_M + toleranz:
        kandidaten.append((max(d - GRIFF_RADIUS_M, 0.0), _RANG["start"], START))
    for i, tag in enumerate(raum.tags):
        d = math.hypot(tag.x - x, tag.y - y)
        if d <= GRIFF_RADIUS_M + toleranz:
            kandidaten.append((max(d - GRIFF_RADIUS_M, 0.0), _RANG["tag"], ("tag", i)))
    for i, block in enumerate(raum.bloecke):
        d = abstand_block(block, x, y)
        if d <= toleranz:
            kandidaten.append((d, _RANG["block"], ("block", i)))
    for i, boden in enumerate(raum.boeden):
        d = abstand_block(boden, x, y)              # dieselbe Rechnung: gedrehtes Rechteck
        if d <= toleranz:
            kandidaten.append((d, _RANG["boden"], ("boden", i)))
    halbe_dicke = raum.wand_dicke / 2
    for i, wand in enumerate(raum.waende):
        d = _abstand_strecke(x, y, *wand)
        if d <= toleranz + halbe_dicke:
            kandidaten.append((max(d - halbe_dicke, 0.0), _RANG["wand"], ("wand", i)))
    if not kandidaten:
        return None
    return min(kandidaten)[2]


def im_rahmen(raum, x1, y1, x2, y2):
    """Alle Elemente, deren Lage im Rechteck liegt."""
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    schluessel = [("wand", i) for i in range(len(raum.waende))]
    schluessel += [("block", i) for i in range(len(raum.bloecke))]
    schluessel += [("boden", i) for i in range(len(raum.boeden))]
    schluessel += [("tag", i) for i in range(len(raum.tags))]
    schluessel.append(START)
    return frozenset(
        s for s in schluessel
        if lo_x <= lage(raum, s)[0] <= hi_x and lo_y <= lage(raum, s)[1] <= hi_y
    )


# ----------------------------------------------------------------- Griffe


def drehring_lage(block):
    c, s = math.cos(math.radians(block.drehung)), math.sin(math.radians(block.drehung))
    r = block.breite / 2 + RING_ABSTAND_M
    return (block.x + r * c, block.y + r * s)


def richtung_lage(x, y, grad):
    return (x + PFEIL_M * math.cos(math.radians(grad)), y + PFEIL_M * math.sin(math.radians(grad)))


def griffe(raum, auswahl):
    """[(schluessel, art, x, y)] -- was die 2D-Sicht als Anfasser zeichnet."""
    ergebnis = []
    for s in sorted(auswahl):
        e = element(raum, s)
        if s[0] == "wand":
            ergebnis.append((s, "ende_a", e.x1, e.y1))
            ergebnis.append((s, "ende_b", e.x2, e.y2))
        elif s[0] in ("block", "boden"):
            for i, (x, y) in enumerate(e.ecken()):
                ergebnis.append((s, f"ecke{i}", x, y))
            ergebnis.append((s, "drehring", *drehring_lage(e)))
        elif s[0] == "tag":
            ergebnis.append((s, "richtung", *richtung_lage(e.x, e.y, e.grad)))
        elif s[0] == "start":
            ergebnis.append((s, "richtung", *richtung_lage(e[0], e[1], e[2])))
    return ergebnis


def ziehe_ecke(raum, schluessel, ecke, x, y):
    """Ecke `ecke` (0..3) eines Blocks oder Bodens auf (x, y) ziehen; die Gegenecke bleibt."""
    block = element(raum, schluessel)
    lx, ly = block.lokal(x, y)
    vorzeichen = ((-1, -1), (1, -1), (1, 1), (-1, 1))[ecke]
    gx, gy = -vorzeichen[0] * block.breite / 2, -vorzeichen[1] * block.tiefe / 2
    breite = _kante(abs(lx - gx))
    tiefe = _kante(abs(ly - gy))
    mx, my = (lx + gx) / 2, (ly + gy) / 2
    c, s = math.cos(math.radians(block.drehung)), math.sin(math.radians(block.drehung))
    neu = replace(block, x=block.x + mx * c - my * s, y=block.y + mx * s + my * c,
                  breite=breite, tiefe=tiefe)
    return _ersetze(raum, schluessel, neu)


# ---------------------------------------------------------------- Pruefung


def pruefe(raum):
    """Hinweise auf Unstimmiges -- als Liste, die der Editor zeigt."""
    from spotlab.welt.hoehe import boden_bei, klippen

    hinweise = []
    z_start, _ = boden_bei(raum, raum.start[0], raum.start[1])
    getroffen = hindernis_bei(raum, raum.start[0], raum.start[1], z=z_start,
                              klippen_=klippen(raum) if raum.boeden else None)
    if getroffen == "Kante":
        hinweise.append("Der Start steht an einer Kante. Verschiebe ihn oder setze einen Boden davor.")
    elif getroffen is not None:
        was = "einer Wand" if getroffen == "Wand" else f"„{getroffen}“"
        hinweise.append(f"Der Start steht in {was}. Verschiebe ihn im Raumeditor.")
    for boden in raum.boeden:
        if min(boden.breite, boden.tiefe) < MINDESTKANTE_M:
            hinweise.append(f"Boden „{boden.name}“ hat keine Fläche.")
        if boden.stufen > 0 and abs(boden.anstieg) / boden.stufen > MAX_STUFE_M:
            hinweise.append(
                f"Treppe „{boden.name}“: {abs(boden.anstieg) / boden.stufen:.2f} m je Stufe ist "
                f"höher als {MAX_STUFE_M:.2f} m — mehr Stufen oder weniger Anstieg."
            )
        if min(boden.z, boden.z_oben) < 0.0:
            hinweise.append(
                f"Boden „{boden.name}“ liegt unter dem Grundboden — der tiefste Boden ist die Höhe 0."
            )
    for i, wand in enumerate(raum.waende):
        if wand.laenge < MINDESTKANTE_M:
            hinweise.append(f"Wand {i + 1} hat keine Laenge.")
    for block in raum.bloecke:
        if min(block.breite, block.tiefe, block.hoehe) < MINDESTKANTE_M:
            hinweise.append(f"„{block.name}“ hat eine Kante unter {MINDESTKANTE_M} m.")
    gesehen = set()
    for tag in raum.tags:
        if tag.id in gesehen:
            hinweise.append(f"Tag {tag.id} ist doppelt vergeben.")
        gesehen.add(tag.id)
        for block in raum.bloecke:
            if abstand_block(block, tag.x, tag.y) == 0.0:
                hinweise.append(f"Tag {tag.id} steckt in „{block.name}“.")
    return hinweise


# ---------------------------------------------------------------- Verlauf


class Verlauf:
    """Rueckgaengig als Liste von Schnappschuessen -- der Raum ist unveraenderlich."""

    def __init__(self, grenze=200):
        self._grenze = grenze
        self._schnappschuesse = []
        self._stelle = -1

    @property
    def aktuell(self):
        return self._schnappschuesse[self._stelle] if self._stelle >= 0 else None

    @property
    def kann_zurueck(self):
        return self._stelle > 0

    @property
    def kann_vor(self):
        return self._stelle < len(self._schnappschuesse) - 1

    def merke(self, raum):
        del self._schnappschuesse[self._stelle + 1:]
        self._schnappschuesse.append(raum)
        if len(self._schnappschuesse) > self._grenze:
            del self._schnappschuesse[0]
        self._stelle = len(self._schnappschuesse) - 1

    def zurueck(self):
        if not self.kann_zurueck:
            return None
        self._stelle -= 1
        return self.aktuell

    def vor(self):
        if not self.kann_vor:
            return None
        self._stelle += 1
        return self.aktuell


# ------------------------------------------------------------------ Modus


class Modus:
    """Die Blender-Tasten: G bewegen, R drehen, S skalieren -- als Automat.

    Eingabe sind Tasten und der Zeiger in METERN auf dem Boden; die Sicht
    rechnet Pixel um. So arbeiten 2D und 3D identisch, und der Automat ist ohne
    Fenster testbar. Die Vorschau ist ein Raum; bestaetigt legt der Aufrufer
    sie in den Verlauf.
    """

    RUHE, BEWEGEN, DREHEN, SKALIEREN = "ruhe", "bewegen", "drehen", "skalieren"

    def __init__(self):
        self._ruhe()

    def _ruhe(self):
        self.art = self.RUHE
        self._raum = None
        self._auswahl = frozenset()
        self._start = (0.0, 0.0)
        self._zeiger = (0.0, 0.0)
        self._um = (0.0, 0.0)
        self._frei = False
        self.achse = None
        self.zahl = ""

    @property
    def aktiv(self):
        return self.art != self.RUHE

    def beginne(self, art, raum, auswahl, zeiger):
        if not auswahl:
            return
        self._ruhe()
        self.art = art
        self._raum = raum
        self._auswahl = frozenset(auswahl)
        self._start = self._zeiger = (float(zeiger[0]), float(zeiger[1]))
        self._um = mitte(raum, self._auswahl)

    def zeiger(self, x, y, frei=False):
        self._zeiger = (float(x), float(y))
        self._frei = frei

    def taste(self, name):
        """True, wenn die Taste zum Modus gehoert hat."""
        if not self.aktiv:
            return False
        name = name.lower()
        if name in ("x", "y", "z"):
            self.achse = None if self.achse == name else name
            return True
        if len(name) == 1 and name in "0123456789.-":
            self.zahl += name
            return True
        if name == "backspace":
            self.zahl = self.zahl[:-1]
            return True
        return False

    def _wert(self):
        try:
            return float(self.zahl)
        except ValueError:
            return None

    def vorschau(self):
        if not self.aktiv:
            return self._raum
        wert = self._wert()
        if self.art == self.BEWEGEN:
            if self.achse == "z":
                # Blender "G, dann Z": die Hoehe folgt der Mausbewegung nach oben.
                dz = wert if wert is not None else self._zeiger[1] - self._start[1]
                if wert is None and not self._frei:
                    dz = raste(dz)
                return hebe(self._raum, self._auswahl, dz)
            if wert is not None:
                dx, dy = (0.0, wert) if self.achse == "y" else (wert, 0.0)
            else:
                dx = self._zeiger[0] - self._start[0]
                dy = self._zeiger[1] - self._start[1]
                if not self._frei:
                    dx, dy = raste(dx), raste(dy)
                if self.achse == "x":
                    dy = 0.0
                elif self.achse == "y":
                    dx = 0.0
            return verschiebe(self._raum, self._auswahl, dx, dy)
        if self.art == self.DREHEN:
            if wert is not None:
                grad = wert
            else:
                a0 = math.atan2(self._start[1] - self._um[1], self._start[0] - self._um[0])
                a1 = math.atan2(self._zeiger[1] - self._um[1], self._zeiger[0] - self._um[0])
                grad = math.degrees(a1 - a0)
                if not self._frei:
                    grad = raste(grad, RASTER_GRAD)
            return drehe(self._raum, self._auswahl, grad, um=self._um)
        if wert is not None:
            f = wert
        else:
            vorher = math.hypot(self._start[0] - self._um[0], self._start[1] - self._um[1])
            nachher = math.hypot(self._zeiger[0] - self._um[0], self._zeiger[1] - self._um[1])
            f = nachher / vorher if vorher > 1e-9 else 1.0
            if not self._frei:
                f = raste(f, 0.05)
        f = max(f, 0.01)
        if self.achse == "x":
            fx, fy, fz = f, 1.0, 1.0
        elif self.achse == "y":
            fx, fy, fz = 1.0, f, 1.0
        elif self.achse == "z":
            fx, fy, fz = 1.0, 1.0, f
        else:
            fx, fy, fz = f, f, 1.0
        return skaliere(self._raum, self._auswahl, fx, fy, fz, um=self._um)

    def bestaetige(self):
        raum = self.vorschau()
        self._ruhe()
        return raum

    def abbruch(self):
        raum = self._raum
        self._ruhe()
        return raum
