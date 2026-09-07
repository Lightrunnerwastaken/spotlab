"""Das Gelaende: ein Hoehenraster als Grund des Raums.

Reine Standardbibliothek wie der Rest von `welt/`. Der Grund ist das Gelaende,
wo es eines gibt, sonst 0 -- und nur `hoehe.py::boden_bei` entscheidet das.
Das Gelaende wird nie von Hand gesetzt: es kommt aus `maps/gelaende_bau.py`,
gerechnet aus Waenden, gelaufenem Weg und Pauspapier.

Knoten liegen auf einem Gitter mit Abstand `zelle` ab `(x0, y0)`, zeilenweise
ab y0; `None` heisst „kein Boden" (in der Datei NaN). Zwischen den Knoten wird
bilinear gemittelt; MuJoCo trianguliert dasselbe Raster, die Abweichung liegt
unter einem Zentimeter.
"""

import math
import struct
from array import array
from dataclasses import dataclass, replace
from pathlib import Path

from spotlab.errors import SpotlabError
from spotlab.welt.raum import MAX_STUFE_M

GELAENDE_ZELLE_M = 0.2
PLATEAU_NEIGUNG_GRAD = 2.0     # flacher als das: ein Plateau-Knoten
PLATEAU_KNOTEN = 50            # so viele Knoten (2 m2 bei 0.2 m) bilden eine Ebene


@dataclass(frozen=True)
class Gelaende:
    x0: float
    y0: float
    zelle: float
    zeilen: int
    spalten: int
    hoehen: tuple          # zeilen * spalten Werte, zeilenweise ab y0; None = kein Boden

    def __post_init__(self):
        if self.zeilen < 2 or self.spalten < 2:
            raise ValueError("Ein Gelaende braucht mindestens 2 x 2 Knoten.")
        hoehen = tuple(self.hoehen)
        if len(hoehen) != self.zeilen * self.spalten:
            raise ValueError("hoehen passt nicht zu zeilen x spalten.")
        object.__setattr__(self, "hoehen", hoehen)
        # Der Umriss der gueltigen Knoten, EINMAL beim Bau: `huelle(raum)` fragt ihn,
        # und der Raumplot fragt `huelle` je gezeichnetem Punkt -- ueber alle Knoten
        # zu laufen kostete dort 56 s je Bild (Katakomben, 07.09.2026).
        object.__setattr__(self, "_umriss", _umriss_rechnen(self))

    def knoten(self, i, j):
        """Die Hoehe am Knoten (Zeile i, Spalte j); ausserhalb None."""
        if 0 <= i < self.zeilen and 0 <= j < self.spalten:
            return self.hoehen[i * self.spalten + j]
        return None

    def hoehe_bei(self, x, y):
        """Bilinear aus den vier umgebenden Knoten. Ausserhalb oder ohne gueltigen
        Knoten None; bei teils fehlenden Knoten der naechste gueltige."""
        fx = (x - self.x0) / self.zelle
        fy = (y - self.y0) / self.zelle
        if fx < 0 or fy < 0 or fx > self.spalten - 1 or fy > self.zeilen - 1:
            return None
        j = min(int(fx), self.spalten - 2)
        i = min(int(fy), self.zeilen - 2)
        tx, ty = fx - j, fy - i
        ecken = ((self.knoten(i, j), 0.0, 0.0), (self.knoten(i, j + 1), 1.0, 0.0),
                 (self.knoten(i + 1, j), 0.0, 1.0), (self.knoten(i + 1, j + 1), 1.0, 1.0))
        gueltig = [e for e in ecken if e[0] is not None]
        if not gueltig:
            return None
        if len(gueltig) == 4:
            h00, h10, h01, h11 = (e[0] for e in ecken)
            return (h00 * (1 - tx) * (1 - ty) + h10 * tx * (1 - ty)
                    + h01 * (1 - tx) * ty + h11 * tx * ty)
        return min(gueltig, key=lambda e: (e[1] - tx) ** 2 + (e[2] - ty) ** 2)[0]

    def neigung_bei(self, x, y):
        """(dz/dx, dz/dy) aus zentralen Differenzen ueber eine halbe Zelle."""
        h = self.zelle / 2
        mitte = self.hoehe_bei(x, y)
        if mitte is None:
            return 0.0, 0.0

        def ableitung(a, b):
            if a is not None and b is not None:
                return (b - a) / (2 * h)
            if b is not None:
                return (b - mitte) / h
            if a is not None:
                return (mitte - a) / h
            return 0.0

        return (ableitung(self.hoehe_bei(x - h, y), self.hoehe_bei(x + h, y)),
                ableitung(self.hoehe_bei(x, y - h), self.hoehe_bei(x, y + h)))


def gitter(x0, y0, zelle, zeilen, spalten, funktion):
    """Ein Gelaende aus einer Funktion (x, y) -> Hoehe oder None."""
    hoehen = tuple(funktion(x0 + j * zelle, y0 + i * zelle)
                   for i in range(zeilen) for j in range(spalten))
    return Gelaende(x0, y0, zelle, zeilen, spalten, hoehen)


def _umriss_rechnen(gelaende):
    zeilen, spalten, h = gelaende.zeilen, gelaende.spalten, gelaende.hoehen
    i_min = i_max = j_min = j_max = None
    for i in range(zeilen):
        zeile = h[i * spalten:(i + 1) * spalten]
        gueltig = [j for j, wert in enumerate(zeile) if wert is not None]
        if not gueltig:
            continue
        i_min = i if i_min is None else i_min
        i_max = i
        j_min = gueltig[0] if j_min is None else min(j_min, gueltig[0])
        j_max = gueltig[-1] if j_max is None else max(j_max, gueltig[-1])
    if i_min is None:
        return None
    z, x0, y0 = gelaende.zelle, gelaende.x0, gelaende.y0
    return (x0 + j_min * z, y0 + i_min * z, x0 + j_max * z, y0 + i_max * z)


def umriss(gelaende):
    """(x_min, y_min, x_max, y_max) der gueltigen Knoten; None ohne Boden. Gemerkt."""
    return gelaende._umriss


def verschoben(gelaende, dx, dy, dz):
    return replace(gelaende, x0=gelaende.x0 + dx, y0=gelaende.y0 + dy,
                   hoehen=tuple(None if h is None else h + dz for h in gelaende.hoehen))


def zusammenfassung(gelaende):
    werte = [h for h in gelaende.hoehen if h is not None]
    if not werte:
        return "Gelände · ohne Boden"
    return (f"Gelände · {gelaende.zelle:g} m · {len(werte)} Knoten · "
            f"{min(werte):.2f} bis {max(werte):.2f} m")


# ------------------------------------------------------------- Klippen, Plateaus


def _laeufe(indizes):
    """[3, 4, 5, 8] -> [(3, 5), (8, 8)]: zusammenhaengende Indizes als Laeufe."""
    laeufe = []
    for k in sorted(indizes):
        if laeufe and laeufe[-1][1] == k - 1:
            laeufe[-1] = (laeufe[-1][0], k)
        else:
            laeufe.append((k, k))
    return laeufe


def klippen(gelaende):
    """[(x1, y1, x2, y2)]: Zellgrenzen, an denen der Grund um mehr als MAX_STUFE_M springt.

    Ein fehlender Knoten -- auch ausserhalb des Rasters -- gilt als Grund 0:
    wo das Gelaende hoch endet, ist sein Rand eine Klippe. Aufeinanderfolgende
    Stuecke auf einer Linie werden eine Strecke.
    """
    z, x0, y0 = gelaende.zelle, gelaende.x0, gelaende.y0

    def wert(i, j):
        h = gelaende.knoten(i, j)
        return 0.0 if h is None else h

    def springt(i, j, i2, j2):
        if gelaende.knoten(i, j) is None and gelaende.knoten(i2, j2) is None:
            return False
        return abs(wert(i, j) - wert(i2, j2)) > MAX_STUFE_M

    ergebnis = []
    for j in range(-1, gelaende.spalten):            # senkrechte Grenzen zwischen j und j+1
        zeilen = [i for i in range(gelaende.zeilen) if springt(i, j, i, j + 1)]
        x = x0 + (j + 0.5) * z
        for a, b in _laeufe(zeilen):
            ergebnis.append((x, y0 + (a - 0.5) * z, x, y0 + (b + 0.5) * z))
    for i in range(-1, gelaende.zeilen):             # waagrechte Grenzen zwischen i und i+1
        spalten = [j for j in range(gelaende.spalten) if springt(i, j, i + 1, j)]
        y = y0 + (i + 0.5) * z
        for a, b in _laeufe(spalten):
            ergebnis.append((x0 + (a - 0.5) * z, y, x0 + (b + 0.5) * z, y))
    return ergebnis


def plateaus(gelaende):
    """Sortierte Hoehen (auf 0.1 m) der ebenen Flaechen: Knoten, die zu allen vier
    Nachbarn flacher als PLATEAU_NEIGUNG_GRAD liegen, in Gruppen ab PLATEAU_KNOTEN."""
    grenze = math.tan(math.radians(PLATEAU_NEIGUNG_GRAD)) * gelaende.zelle
    zaehler = {}
    for i in range(gelaende.zeilen):
        for j in range(gelaende.spalten):
            h = gelaende.knoten(i, j)
            if h is None:
                continue
            nachbarn = [gelaende.knoten(i + di, j + dj)
                        for di, dj in ((0, 1), (0, -1), (1, 0), (-1, 0))]
            if any(n is None or abs(n - h) > grenze for n in nachbarn):
                continue
            stufe = round(h, 1)
            zaehler[stufe] = zaehler.get(stufe, 0) + 1
    return sorted(s for s, n in zaehler.items() if n >= PLATEAU_KNOTEN)


# ------------------------------------------------------------- Datei
#
# Neben der Raumdatei, wie das Pauspapier: Kennung, Kopf (x0, y0, zelle als
# double, zeilen und spalten als uint32), dann float32 je Knoten, NaN fuer None.

KENNUNG = b"GEL1"
ENDUNG = ".gelaende"
_KOPF = "<4sdddII"


def pfad_zu(raumpfad):
    """`raeume/gang.toml` -> `raeume/gang.gelaende`."""
    return Path(raumpfad).with_suffix(ENDUNG)


def schreibe(pfad, gelaende):
    werte = array("f", (math.nan if h is None else float(h) for h in gelaende.hoehen))
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "wb") as datei:
        datei.write(struct.pack(_KOPF, KENNUNG, gelaende.x0, gelaende.y0, gelaende.zelle,
                                gelaende.zeilen, gelaende.spalten))
        datei.write(werte.tobytes())


def lies(pfad):
    """Das Gelaende aus der Datei; eine fehlende Datei ist None, kein Fehler."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return None
    roh = pfad.read_bytes()
    kopf = struct.calcsize(_KOPF)
    if len(roh) < kopf or roh[:4] != KENNUNG:
        raise SpotlabError(
            f"{pfad.name} ist keine Gelände-Datei (Kennung fehlt). Die Datei löschen und "
            f"den Raum neu korrigieren."
        )
    _kennung, x0, y0, zelle, zeilen, spalten = struct.unpack(_KOPF, roh[:kopf])
    werte = array("f")
    werte.frombytes(roh[kopf:kopf + zeilen * spalten * 4])
    if len(werte) != zeilen * spalten:
        raise SpotlabError(f"{pfad.name} ist unvollständig. Den Raum neu korrigieren.")
    return Gelaende(x0, y0, zelle, zeilen, spalten,
                    tuple(None if math.isnan(w) else float(w) for w in werte))


__all__ = ["GELAENDE_ZELLE_M", "PLATEAU_NEIGUNG_GRAD", "PLATEAU_KNOTEN", "MAX_STUFE_M",
           "Gelaende", "gitter", "umriss", "verschoben", "zusammenfassung",
           "klippen", "plateaus", "KENNUNG", "ENDUNG", "pfad_zu", "schreibe", "lies"]
