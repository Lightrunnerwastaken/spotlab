"""Der Gelaendebau: aus Waenden, gelaufenem Weg und Pauspapier ein Hoehenraster.

numpy, keine Karte, kein bosdyn -- der Korrigierer im Editor ruft es mit dem
`Raum`, dem Weg (x, y, Bodenhoehe) und den Pauspapier-Punkten (PAUS2).

Das Raster ist ein Knotenraster; "Zelle" meint die Umgebung eines Knotens.
1. Sperren: Knoten an Waenden, in Bloecken, mit vielen Pauspapier-Punkten
   (kleine Flecken sind Rauschen); Wegknoten sind immer frei.
2. Weg: das geglaettete Hoehenprofil liegt auf den Wegknoten (fest).
3. Region: Flut von den Wegknoten ueber freie Knoten bis `abstand` neben dem
   Weg.
4. Offene Raender: Regionsknoten mit freiem Nachbarn ausserhalb -- dort hielt
   nichts auf, der Autor sieht sie in der 2D-Sicht.
5. Loecher: freie Knoten, die der Gitterrand ueber freie Knoten nicht erreicht
   (eingeschlossen von Region, Waenden oder Punkten -- ein Punktfleck im Gang,
   die Tasche hinter einem Punktband, ein umschlossener Raum), kommen zur
   Region: ein Loch im Gang waere eine Klippe, die es nicht gibt.
6. Membran: jede freie Regionszelle ist der Mittelwert ihrer Nachbarn
   (Ueber-Relaxation, Rot-Schwarz), Wegknoten bleiben fest -- vorher raeumlich
   geglaettet (`glaettung`), damit zwei Fahrten mit Drift durch denselben Gang
   keine Klippe reissen. Quer zum Gang eben, laengs das Gefaelle.
7. Flaechenglaettung: `glaettung_flaeche` Durchgaenge eines Fuenf-Punkte-Mittels
   ueber die Region -- die Stufe am Ende eines Wegstummels, den die Membran
   sonst scharf gegen das Nachbarniveau setzt, wird ein Uebergang.
8. Gesperrte Zusammenhaenge, die die Region beruehren (die Wand selbst, ein
   Punktband davor), bekommen danach die Hoehe ihres Nachbarn kopiert: unter
   einer Wand liegt kein Graben, und der Rand des Gelaendes liegt hinter den
   Waenden. Sie rechnen in der Membran NICHT mit -- eine Wand, die Hoehe an
   sich entlang leitete, verzerrte den Gang daneben. Freie Taschen, die erst
   jetzt einen Regionsnachbarn haben (ein Knoten hinter einem Punktband),
   bekommen ebenfalls eine Kopie.
9. Der tiefste Knoten wird 0.
"""

import math
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

from spotlab.errors import SpotlabError
from spotlab.welt.gelaende import GELAENDE_ZELLE_M, Gelaende
from spotlab.welt.polylinie import douglas_peucker
from spotlab.welt.raum import huelle

NACHBARN = ((1, 0), (-1, 0), (0, 1), (0, -1))
NACHBARN_8 = NACHBARN + ((1, 1), (1, -1), (-1, 1), (-1, -1))


@dataclass(frozen=True)
class Einstellungen:
    zelle: float = GELAENDE_ZELLE_M      # Knotenabstand
    abstand: float = 2.0                 # Boden neben dem Weg, wo nichts aufhaelt
    punkte_je_zelle: int = 5             # ab hier sperrt das Pauspapier einen Knoten
    min_fleck: int = 3                   # kleinere gesperrte Flecken sind Rauschen
    profil_toleranz: float = 0.10        # Douglas-Peucker auf dem Wegprofil
    glaettung: float = 1.0               # Wegknoten mitteln sich mit Wegknoten in diesem Umkreis
    glaettung_flaeche: int = 1           # Durchgaenge des Fuenf-Punkte-Mittels nach der Membran
    hoechstens_iterationen: int = 3000
    genau_m: float = 0.001
    rand: float = 1.0                    # Raster ueber die Huelle hinaus


@dataclass(frozen=True)
class Ergebnis:
    gelaende: Gelaende
    offene_raender: list      # [(x, y)] Knoten am Flutrand, an denen nichts aufhielt
    bericht: dict


# ------------------------------------------------------------- Helfer


def _zur_strecke(xs, ys, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return np.hypot(xs - x1, ys - y1)
    t = np.clip(((xs - x1) * dx + (ys - y1) * dy) / laenge2, 0.0, 1.0)
    return np.hypot(xs - (x1 + t * dx), ys - (y1 + t * dy))


def _flut(start, erlaubt):
    """Erreichbare Knoten (4er-Nachbarschaft) ab `start` innerhalb `erlaubt` -- als Maske."""
    zeilen, spalten = erlaubt.shape
    gesehen = np.zeros_like(erlaubt, dtype=bool)
    schlange = deque()
    for i, j in zip(*np.nonzero(start)):
        gesehen[i, j] = True
        schlange.append((int(i), int(j)))
    while schlange:
        i, j = schlange.popleft()
        for di, dj in NACHBARN:
            ni, nj = i + di, j + dj
            if 0 <= ni < zeilen and 0 <= nj < spalten and erlaubt[ni, nj] and not gesehen[ni, nj]:
                gesehen[ni, nj] = True
                schlange.append((ni, nj))
    return gesehen


def _flecken(maske, nachbarn=NACHBARN):
    """Zusammenhaengende Flecken einer Maske (4er-, mit NACHBARN_8 8er-Nachbarschaft)."""
    zeilen, spalten = maske.shape
    gesehen = np.zeros_like(maske, dtype=bool)
    flecken = []
    for i0, j0 in zip(*np.nonzero(maske)):
        if gesehen[i0, j0]:
            continue
        fleck, schlange = [], deque([(int(i0), int(j0))])
        gesehen[i0, j0] = True
        while schlange:
            i, j = schlange.popleft()
            fleck.append((i, j))
            for di, dj in nachbarn:
                ni, nj = i + di, j + dj
                if 0 <= ni < zeilen and 0 <= nj < spalten and maske[ni, nj] and not gesehen[ni, nj]:
                    gesehen[ni, nj] = True
                    schlange.append((ni, nj))
        flecken.append(fleck)
    return flecken


# ------------------------------------------------------------- Schritte


def _gitter(raum, weg, pauspapier, e):
    x_min, y_min, x_max, y_max = huelle(raum)
    xs = [p[0] for p in weg] + [p[0] for p in pauspapier]
    ys = [p[1] for p in weg] + [p[1] for p in pauspapier]
    if xs:
        x_min, x_max = min(x_min, min(xs)), max(x_max, max(xs))
        y_min, y_max = min(y_min, min(ys)), max(y_max, max(ys))
    x0 = math.floor((x_min - e.rand) / e.zelle) * e.zelle
    y0 = math.floor((y_min - e.rand) / e.zelle) * e.zelle
    spalten = int(math.ceil((x_max + e.rand - x0) / e.zelle)) + 1
    zeilen = int(math.ceil((y_max + e.rand - y0) / e.zelle)) + 1
    return x0, y0, max(2, zeilen), max(2, spalten)


def _knoten(x, y, x0, y0, zelle):
    return int(round((y - y0) / zelle)), int(round((x - x0) / zelle))


def _gesperrt(raum, pauspapier, X, Y, x0, y0, e):
    """Maske der gesperrten Knoten: Waende (mit Dicke, wasserdicht), Bloecke, dichtes Pauspapier."""
    zeilen, spalten = X.shape
    schwelle = max(raum.wand_dicke, 1.5 * e.zelle) / 2
    hart = np.zeros(X.shape, dtype=bool)
    for wand in raum.waende:
        if wand.laenge <= 0:
            continue
        hart |= _zur_strecke(X, Y, wand.x1, wand.y1, wand.x2, wand.y2) <= schwelle
    for block in raum.bloecke:
        c = math.cos(math.radians(-block.drehung))
        s = math.sin(math.radians(-block.drehung))
        dx, dy = X - block.x, Y - block.y
        lx, ly = dx * c - dy * s, dx * s + dy * c
        hart |= (np.abs(lx) <= block.breite / 2) & (np.abs(ly) <= block.tiefe / 2)
    zaehler = np.zeros(X.shape, dtype=np.int64)
    if len(pauspapier):
        p = np.asarray(pauspapier, dtype=float)
        ii = np.rint((p[:, 1] - y0) / e.zelle).astype(np.int64)
        jj = np.rint((p[:, 0] - x0) / e.zelle).astype(np.int64)
        drin = (ii >= 0) & (ii < zeilen) & (jj >= 0) & (jj < spalten)
        np.add.at(zaehler, (ii[drin], jj[drin]), 1)
    punkte = (zaehler >= e.punkte_je_zelle) & ~hart
    for fleck in _flecken(punkte):
        if len(fleck) < e.min_fleck:
            for i, j in fleck:
                punkte[i, j] = False
    return hart | punkte, int(hart.sum()), int(punkte.sum())


def _wegknoten(weg, X, Y, x0, y0, e):
    """(fest, werte, abstand): Wegknoten mit geglaetteter Hoehe und der Abstand jedes
    Knotens zur Wegpolylinie."""
    s = [0.0]
    for p, q in zip(weg, weg[1:]):
        s.append(s[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    zs = [p[2] for p in weg]
    stuetzen = douglas_peucker(list(zip(s, zs)), e.profil_toleranz)

    def glatt(s_wert):
        for a, b in zip(stuetzen, stuetzen[1:]):
            if s[a] <= s_wert <= s[b]:
                anteil = 0.0 if s[b] == s[a] else (s_wert - s[a]) / (s[b] - s[a])
                return zs[a] + (zs[b] - zs[a]) * anteil
        return zs[stuetzen[-1]]

    zeilen, spalten = X.shape
    summe = np.zeros(X.shape)
    anzahl = np.zeros(X.shape)
    abstand = np.full(X.shape, np.inf)
    for k, (p, q) in enumerate(zip(weg, weg[1:])):
        laenge = s[k + 1] - s[k]
        n = max(1, int(math.ceil(laenge / (e.zelle / 2))))
        for m in range(n + 1):
            t = m / n
            x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
            i, j = _knoten(x, y, x0, y0, e.zelle)
            if 0 <= i < zeilen and 0 <= j < spalten:
                summe[i, j] += glatt(s[k] + laenge * t)
                anzahl[i, j] += 1
        abstand = np.minimum(abstand, _zur_strecke(X, Y, p[0], p[1], q[0], q[1]))
    fest = anzahl > 0
    werte = np.where(fest, summe / np.where(fest, anzahl, 1.0), 0.0)
    return fest, werte, abstand


def _region(gesperrt, fest, werte, abstand, e):
    """(region, startwerte): Flut von den Wegknoten ueber freie Knoten bis `abstand`."""
    zeilen, spalten = gesperrt.shape
    frei = ~gesperrt
    region = fest.copy()
    start = werte.copy()
    schlange = deque((int(i), int(j)) for i, j in zip(*np.nonzero(fest)))
    while schlange:
        i, j = schlange.popleft()
        for di, dj in NACHBARN:
            ni, nj = i + di, j + dj
            if (0 <= ni < zeilen and 0 <= nj < spalten and frei[ni, nj]
                    and not region[ni, nj] and abstand[ni, nj] <= e.abstand):
                region[ni, nj] = True
                start[ni, nj] = start[i, j]
                schlange.append((ni, nj))
    return region, start


def _wachse(region, start, dazu):
    """Knoten aus `dazu` an die Region anschliessen, Startwert vom Nachbarn (Flutreihenfolge)."""
    zeilen, spalten = region.shape
    schlange = deque((int(i), int(j)) for i, j in zip(*np.nonzero(region)))
    while schlange:
        i, j = schlange.popleft()
        for di, dj in NACHBARN:
            ni, nj = i + di, j + dj
            if 0 <= ni < zeilen and 0 <= nj < spalten and dazu[ni, nj] and not region[ni, nj]:
                region[ni, nj] = True
                start[ni, nj] = start[i, j]
                schlange.append((ni, nj))
    return region, start


def _fuelle_loecher(region, start, gesperrt):
    """Freie Knoten, die der Gitterrand ueber freie Nicht-Regionsknoten nicht erreicht,
    sind eingeschlossen und werden Boden (Membranknoten); gesperrte Flecken darin
    ebenfalls -- sie liegen mitten im Gang."""
    frei = ~gesperrt
    rand = np.zeros_like(region)
    rand[0, :] = rand[-1, :] = rand[:, 0] = rand[:, -1] = True
    draussen = _flut(rand & frei & ~region, frei & ~region)
    loecher = frei & ~region & ~draussen
    if loecher.any():
        region, start = _wachse(region, start, loecher)
    # Gesperrte Flecken, die nur Region beruehren (kein Weg nach draussen ueber Sperren
    # bis zum Rand), sind Rauschen mitten im Boden: ebenfalls Membran.
    aussen_gesperrt = _flut(rand & gesperrt & ~region, gesperrt & ~region)
    nachbar = np.zeros_like(region)
    for di, dj in NACHBARN:
        nachbar |= _nachbar(region.astype(np.int8), di, dj) > 0
    ring = gesperrt & ~region & nachbar
    if ring.any():
        cluster = _flut(ring, gesperrt & ~region)
        innen = cluster & ~aussen_gesperrt
        if innen.any():
            region, start = _wachse(region, start, innen)
    return region, start


def _glaette_flaeche(h, region, durchgaenge):
    """Fuenf-Punkte-Mittel ueber die Region (Nachbarn ausserhalb zaehlen nicht)."""
    r = region.astype(float)
    for _ in range(int(durchgaenge)):
        summe = h * r + sum(_nachbar(h * r, di, dj) for di, dj in NACHBARN)
        anzahl = r + sum(_nachbar(r, di, dj) for di, dj in NACHBARN)
        h = np.where(region, summe / np.where(anzahl > 0, anzahl, 1.0), h)
    return h


def _fuelle_taschen(region, h, gesperrt):
    """Freie Knoten, die der Gitterrand ueber freie Nicht-Regionsknoten nicht erreicht,
    bekommen die Hoehe ihres Nachbarn kopiert -- nach dem Cluster-Schritt haben auch
    Taschen hinter einem Punktband einen Regionsnachbarn."""
    frei = ~gesperrt
    rand = np.zeros_like(region)
    rand[0, :] = rand[-1, :] = rand[:, 0] = rand[:, -1] = True
    draussen = _flut(rand & frei & ~region, frei & ~region)
    taschen = frei & ~region & ~draussen
    if not taschen.any():
        return region, h
    return _wachse(region.copy(), h, taschen)


def _fuelle_cluster(region, h, gesperrt):
    """Gesperrte Zusammenhaenge, die die Region beruehren, bekommen die Hoehe ihres
    Nachbarn kopiert (nach der Membran, sie rechnen nicht mit)."""
    nachbar = np.zeros_like(region)
    for di, dj in NACHBARN:
        nachbar |= _nachbar(region.astype(np.int8), di, dj) > 0
    ring = gesperrt & ~region & nachbar
    if not ring.any():
        return region, h
    cluster = _flut(ring, gesperrt & ~region)
    return _wachse(region.copy(), h, cluster)


def _glaette_fest(fest, werte, radius_knoten):
    """Jeder Wegknoten wird das Mittel der Wegknoten in seinem Umkreis."""
    ii, jj = np.nonzero(fest)
    if len(ii) == 0 or radius_knoten <= 0:
        return werte
    lage = np.column_stack([ii, jj]).astype(float)
    z = werte[ii, jj]
    d2 = ((lage[:, None, :] - lage[None, :, :]) ** 2).sum(axis=2)
    nah = d2 <= radius_knoten ** 2
    glatt = (nah * z[None, :]).sum(axis=1) / nah.sum(axis=1)
    ergebnis = werte.copy()
    ergebnis[ii, jj] = glatt
    return ergebnis


def _offene_raender(region, gesperrt):
    zeilen, spalten = region.shape
    offen = np.zeros_like(region)
    frei = ~gesperrt
    for di, dj in NACHBARN:
        nachbar_frei = np.zeros_like(region)
        nachbar_region = np.zeros_like(region)
        quelle_i = slice(max(di, 0), zeilen + min(di, 0))
        ziel_i = slice(max(-di, 0), zeilen + min(-di, 0))
        quelle_j = slice(max(dj, 0), spalten + min(dj, 0))
        ziel_j = slice(max(-dj, 0), spalten + min(-dj, 0))
        nachbar_frei[ziel_i, ziel_j] = frei[quelle_i, quelle_j]
        nachbar_region[ziel_i, ziel_j] = region[quelle_i, quelle_j]
        offen |= region & nachbar_frei & ~nachbar_region
    # Ein Rand ist eine Kurve, auch wenn sie treppenfoermig ueber die Knoten laeuft: 8er-Nachbarn.
    laeufe = len(_flecken(offen, NACHBARN_8)) if offen.any() else 0
    return offen, laeufe


def _nachbar(a, di, dj):
    """Der Wert des Nachbarn (i + di, j + dj) je Knoten; 0 ausserhalb."""
    b = np.zeros_like(a)
    if di == 1:
        b[:-1, :] = a[1:, :]
    elif di == -1:
        b[1:, :] = a[:-1, :]
    elif dj == 1:
        b[:, :-1] = a[:, 1:]
    else:
        b[:, 1:] = a[:, :-1]
    return b


def _membran(h, fest, region, e):
    """Ueber-Relaxation in Rot-Schwarz-Ordnung; Wegknoten fest, Neumann am Regionsrand."""
    zeilen, spalten = h.shape
    frei = region & ~fest
    if not frei.any():
        return h, 0
    ii, jj = np.indices(h.shape)
    rot = (ii + jj) % 2 == 0
    omega = 2.0 / (1.0 + math.sin(math.pi / max(zeilen, spalten)))
    r = region.astype(float)
    anzahl = sum(_nachbar(r, di, dj) for di, dj in NACHBARN)
    anzahl = np.where(anzahl > 0, anzahl, 1.0)
    h = np.where(region, h, 0.0)
    iteration = 0
    for iteration in range(1, e.hoechstens_iterationen + 1):
        delta = 0.0
        for farbe in (rot, ~rot):
            summe = sum(_nachbar(h * r, di, dj) for di, dj in NACHBARN)
            neu = (1.0 - omega) * h + omega * summe / anzahl
            maske = frei & farbe
            delta = max(delta, float(np.abs(neu[maske] - h[maske]).max()))
            h[maske] = neu[maske]
        if delta < e.genau_m:
            break
    return h, iteration


# ------------------------------------------------------------- Zusammenbau


def baue_gelaende(raum, weg, pauspapier, einstellungen=None, fortschritt=None):
    """Ein `Ergebnis` mit dem Gelaende; `weg` sind (x, y, z) in Laufreihenfolge."""
    e = einstellungen or Einstellungen()
    weg = [tuple(float(v) for v in p[:3]) for p in weg]
    if len(weg) < 2:
        raise SpotlabError("Kein Weg gespeichert — das Gelände braucht den gelaufenen Weg "
                           "aus der Rekonstruktion.")
    pauspapier = list(pauspapier)
    t0 = time.monotonic()

    def melde(text):
        if fortschritt is not None:
            fortschritt(text)

    melde("Sperren")
    x0, y0, zeilen, spalten = _gitter(raum, weg, pauspapier, e)
    X = x0 + np.arange(spalten)[np.newaxis, :] * e.zelle
    Y = y0 + np.arange(zeilen)[:, np.newaxis] * e.zelle
    X, Y = np.broadcast_arrays(X, Y)
    gesperrt, hart, punkte = _gesperrt(raum, pauspapier, X, Y, x0, y0, e)
    fest, werte, abstand = _wegknoten(weg, X, Y, x0, y0, e)
    werte = _glaette_fest(fest, werte, e.glaettung / e.zelle)
    gesperrt &= ~fest                      # der Roboter war dort: frei
    melde("Fluten")
    region, start = _region(gesperrt, fest, werte, abstand, e)
    offen, laeufe = _offene_raender(region, gesperrt)
    region, start = _fuelle_loecher(region, start, gesperrt)
    melde("Membran")
    h, iterationen = _membran(np.where(fest, werte, start), fest, region, e)
    h = _glaette_flaeche(h, region, e.glaettung_flaeche)
    region, h = _fuelle_cluster(region, h, gesperrt)
    region, h = _fuelle_taschen(region, h, gesperrt)
    melde(f"Membran {iterationen} Iterationen")
    tiefster = float(h[region].min()) if region.any() else 0.0
    h = h - tiefster
    hoehen = tuple(float(v) if drin else None
                   for v, drin in zip(h.ravel().tolist(), region.ravel().tolist()))
    gelaende = Gelaende(x0, y0, e.zelle, zeilen, spalten, hoehen)
    offene_raender = [(float(X[i, j]), float(Y[i, j])) for i, j in zip(*np.nonzero(offen))]
    bericht = {
        "knoten": int(region.sum()), "zeilen": zeilen, "spalten": spalten,
        "gesperrt": int(gesperrt.sum()), "gesperrt_waende": hart, "gesperrt_punkte": punkte,
        "wegknoten": int(fest.sum()), "offen": laeufe, "offene_knoten": int(offen.sum()),
        "z_min": 0.0, "z_max": float(h[region].max()) if region.any() else 0.0,
        "verschiebung": tiefster, "iterationen": iterationen,
        "dauer_s": round(time.monotonic() - t0, 2),
    }
    return Ergebnis(gelaende, offene_raender, bericht)
