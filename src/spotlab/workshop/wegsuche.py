"""A*-Wegsuche auf der Skizze der Steuerzentrale — nur über bekannten freien Boden.

Die Klickfahrt fragt hier nach einem Weg vom Roboter zum angeklickten Punkt. Gesucht
wird auf der Skizze (`workshop/skizze.py`), vergröbert auf 10-cm-Zellen: Wände werden
um den Randabstand aufgedickt, Unbekanntes ist zu — Spot geht nur, wo er Boden
GESEHEN hat. Ausnahme ist der Körperschatten: unter und dicht um sich sieht Spot nie
etwas (die Frontkameras treffen den Boden erst 0.9 m vor der Mitte), deshalb gilt um
den Start alles ausser einer echten Wand als begehbar.

A* (das Standardverfahren für kürzeste Wege auf einem Raster): 8 Nachbarn, keine
Ecke wird geschnitten, Schätzung über die Oktil-Distanz. Danach wird der Weg auf die
Punkte vereinfacht, zwischen denen freie Sicht ist.

Rein rechnerisch, ohne Roboter prüfbar.
"""

import heapq
import math

import numpy as np

from spotlab.workshop import skizze as sk

PLAN_FAKTOR = 2            # geplant wird auf 2 x 2 Skizzenzellen, also 10 cm
KOERPER_M = 0.6            # um den Start gilt Unbekanntes als frei: dort liegt der Körperschatten
_WURZEL2 = math.sqrt(2.0)
_NACHBARN = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, _WURZEL2), (1, -1, _WURZEL2), (-1, 1, _WURZEL2), (-1, -1, _WURZEL2))


def aufdicken(maske, r):
    """Jede wahre Zelle zu einer Scheibe mit Radius `r` Zellen ausweiten — ohne Umlauf am Rand."""
    maske = np.asarray(maske, bool)
    if r <= 0:
        return maske.copy()
    hoehe, breite = maske.shape
    gepolstert = np.pad(maske, r)
    aus = np.zeros_like(maske)
    for dz in range(-r, r + 1):
        for ds in range(-r, r + 1):
            if dz * dz + ds * ds <= r * r:
                aus |= gepolstert[r + dz:r + dz + hoehe, r + ds:r + ds + breite]
    return aus


def _grob(zustand, faktor):
    """(frei, wand) je Block aus `faktor` x `faktor` Zellen: eine Wand im Block macht ihn zur Wand."""
    hoehe, breite = zustand.shape
    gh, gb = -(-hoehe // faktor), -(-breite // faktor)
    gepolstert = np.zeros((gh * faktor, gb * faktor), np.uint8)   # UNBEKANNT = 0
    gepolstert[:hoehe, :breite] = zustand
    bloecke = gepolstert.reshape(gh, faktor, gb, faktor)
    wand = (bloecke == sk.WAND).any(axis=(1, 3))
    frei = (bloecke == sk.FREI).any(axis=(1, 3)) & ~wand
    return frei, wand


class _Plan:
    """Das vergröberte Raster einer Skizze mit Durchlass, Rahmen und Umrechnung."""

    def __init__(self, skizze, rand_m, start_xy, koerper_m):
        self.zelle_m = skizze.zelle_m * PLAN_FAKTOR
        self.ursprung = skizze.ursprung
        frei, self.wand = _grob(skizze.zustand, PLAN_FAKTOR)
        r = int(math.ceil(rand_m / self.zelle_m - 1e-9))
        self.durchlass = frei & ~aufdicken(self.wand, r)
        # Körperschatten: um den Start alles ausser echter Wand.
        z0, s0 = self.zelle(*start_xy)
        rk = koerper_m / self.zelle_m
        zz, ss = np.ogrid[:self.wand.shape[0], :self.wand.shape[1]]
        kreis = (zz - z0) ** 2 + (ss - s0) ** 2 <= rk * rk
        self.durchlass |= kreis & ~self.wand

    def zelle(self, x, y):
        return (int(math.floor((y - self.ursprung[1]) / self.zelle_m)),
                int(math.floor((x - self.ursprung[0]) / self.zelle_m)))

    def welt(self, z, s):
        return (self.ursprung[0] + (s + 0.5) * self.zelle_m,
                self.ursprung[1] + (z + 0.5) * self.zelle_m)

    def drin(self, z, s):
        hoehe, breite = self.durchlass.shape
        return 0 <= z < hoehe and 0 <= s < breite


def suche(frei, start, ziel):
    """A* von `start` zu `ziel` (Zeile, Spalte) über `frei` — die Zellenliste oder None."""
    hoehe, breite = frei.shape

    def drin(z, s):
        return 0 <= z < hoehe and 0 <= s < breite

    if not (drin(*start) and drin(*ziel) and frei[start] and frei[ziel]):
        return None

    def schaetzung(z, s):
        dz, ds = abs(z - ziel[0]), abs(s - ziel[1])
        return max(dz, ds) + (_WURZEL2 - 1.0) * min(dz, ds)

    kosten = {start: 0.0}
    herkunft = {start: None}
    offen = [(schaetzung(*start), 0.0, start)]
    while offen:
        _, bisher, knoten = heapq.heappop(offen)
        if knoten == ziel:
            break
        if bisher > kosten[knoten]:
            continue
        z, s = knoten
        for dz, ds, schritt in _NACHBARN:
            nz, ns = z + dz, s + ds
            if not drin(nz, ns) or not frei[nz, ns]:
                continue
            if dz and ds and not (frei[z + dz, s] and frei[z, s + ds]):
                continue                           # keine Ecke schneiden
            neu = bisher + schritt
            if neu < kosten.get((nz, ns), math.inf):
                kosten[(nz, ns)] = neu
                herkunft[(nz, ns)] = knoten
                heapq.heappush(offen, (neu + schaetzung(nz, ns), neu, (nz, ns)))
    if ziel not in herkunft:
        return None
    pfad, knoten = [], ziel
    while knoten is not None:
        pfad.append(knoten)
        knoten = herkunft[knoten]
    return pfad[::-1]


def _sicht(frei, a, b):
    """Liegt jede Zelle auf der Geraden von a nach b im Durchlass? (Bresenham)"""
    (z0, s0), (z1, s1) = a, b
    dz, ds = abs(z1 - z0), abs(s1 - s0)
    sz, ss = (1 if z1 > z0 else -1), (1 if s1 > s0 else -1)
    fehler = ds - dz
    z, s = z0, s0
    while True:
        if not frei[z, s]:
            return False
        if (z, s) == (z1, s1):
            return True
        doppelt = 2 * fehler
        if doppelt > -dz:
            fehler -= dz
            s += ss
        if doppelt < ds:
            fehler += ds
            z += sz


def _vereinfacht(frei, pfad):
    """Nur die Punkte, zwischen denen freie Sicht ist — ohne den Start."""
    punkte, i = [], 0
    while i < len(pfad) - 1:
        j = len(pfad) - 1
        while j > i + 1 and not _sicht(frei, pfad[i], pfad[j]):
            j -= 1
        punkte.append(pfad[j])
        i = j
    return punkte


def weg(skizze, start_xy, ziel_xy, rand_m=0.3, koerper_m=KOERPER_M):
    """Wegpunkte (x, y) vom Start zum Ziel — der letzte ist das Ziel genau — oder None."""
    if skizze.leer:
        return None
    plan = _Plan(skizze, rand_m, start_xy, koerper_m)
    start, ziel = plan.zelle(*start_xy), plan.zelle(*ziel_xy)
    if not (plan.drin(*start) and plan.drin(*ziel)) or plan.wand[ziel]:
        return None
    # Die Zielzelle selbst: `pruefe_ziel` hat den Randabstand in voller Auflösung
    # geprüft; der gröbere Plan soll sie deshalb nicht noch einmal sperren.
    plan.durchlass[ziel] = True
    if start == ziel:
        return [tuple(ziel_xy)]
    pfad = suche(plan.durchlass, start, ziel)
    if pfad is None:
        return None
    punkte = [plan.welt(z, s) for z, s in _vereinfacht(plan.durchlass, pfad)]
    punkte[-1] = (float(ziel_xy[0]), float(ziel_xy[1]))
    return punkte


def pruefe_ziel(skizze, start_xy, ziel_xy, rand_m, max_weite_m):
    """"" für ein gutes Ziel — sonst der Grund in Worten, für den Menschen am Tab."""
    weite = math.dist(start_xy, ziel_xy)
    if weite > max_weite_m:
        return f"zu weit ({weite:.1f} m, höchstens {max_weite_m:.0f} m je Klick)"
    zelle = skizze.zelle(*ziel_xy)
    if zelle is None or skizze.zustand[zelle] == sk.UNBEKANNT:
        return "unbekannt — dort hat Spot noch keinen Boden gesehen"
    r = int(math.ceil(rand_m / skizze.zelle_m))
    z, s = zelle
    hoehe, breite = skizze.zustand.shape
    fenster = skizze.zustand[max(0, z - r):min(hoehe, z + r + 1), max(0, s - r):min(breite, s + r + 1)]
    wz, ws = np.nonzero(fenster == sk.WAND)
    if len(wz):
        wx = skizze.ursprung[0] + (ws + max(0, s - r) + 0.5) * skizze.zelle_m
        wy = skizze.ursprung[1] + (wz + max(0, z - r) + 0.5) * skizze.zelle_m
        if float(np.min(np.hypot(wx - ziel_xy[0], wy - ziel_xy[1]))) < rand_m:
            return f"in der Wand oder näher als {rand_m:.1f} m daran"
    return ""
