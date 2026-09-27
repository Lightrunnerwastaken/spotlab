"""Kartenwände und Abgleich der Steuerzentrale (Teil 3): was Spot von einer Karte wiedererkennt.

Eine geladene GraphNav-Karte bringt Punktwolken je Wegpunkt mit. `Kartenwaende.aus_ordner`
macht daraus EINMAL die Wandzellen im Seed-Rahmen der Karte — mit derselben Rechnung wie die
Rekonstruktion (`maps/rekonstruktion.wandzellen`: Band über dem Boden je Schnappschuss,
Sichtprüfung), damit Zentrale und Raumeditor dieselben Wände sehen.

Mit einer `Verortung` (Lage des Körpers im Seed UND in „vision“ aus derselben Antwort) fallen
die Wände auf die Skizze: `vision_von_seed` und `in_vision`. `abgleich` vergleicht dann im
BLICKFELD — Skizzenzellen, die höchstens `FRISCH_S` alt sind und höchstens `BLICK_M` von Spot
liegen — mit `NAH_M` Toleranz:

    erkannt   Kartenwand, an der Spot jetzt eine Wand sieht
    neu       Wand, die Spot sieht, ohne Kartenwand in der Nähe (Kiste, Tür zu, ein Mensch)
    fehlt     Kartenwand, wo Spot jetzt freien Boden sieht (Tür offen, Möbel weg)
    sonst     Kartenwand ausserhalb des Blickfelds: nicht geprüft

Die Zahl ist erkannt ÷ (erkannt + neu), gezählt in gesehenen Wandzellen, erst ab
`MIN_WANDZELLEN`. Ist Spot verloren, wird nichts verglichen: der Vergleich wäre geraten.

Das Raster liegt im Zellgitter der Skizze (Ursprung auf Vielfachen von `ZELLE_M`), hat aber eine
eigene Ausdehnung — die Karte darf über das hinausreichen, was Spot in dieser Fahrt gesehen hat.
Glas sieht Spot nicht; die Karte kennt nur, was bei der Aufnahme im Blick war.
"""

import io
import math
from dataclasses import dataclass

import numpy as np

from spotlab.record.zentrale import KARTE_ERKANNT, KARTE_FEHLT, KARTE_NEU, KARTE_UNGEPRUEFT
from spotlab.workshop import skizze as skizzenmodul

ZELLE_M = skizzenmodul.ZELLE_M
FRISCH_S = skizzenmodul.FRISCH_S
BLICK_M = 4.0
NAH_M = 0.15
MIN_WANDZELLEN = 20
_HAUCH = 1e-6


@dataclass(frozen=True)
class Kartenwaende:
    zellen: np.ndarray        # (M, 2) Wandzellen-Mitten im Seed-Rahmen der Karte
    wegpunkte: list           # [(x, y, name)] im Seed-Rahmen
    kanten: list              # [(i, j)] Indizes in `wegpunkte`
    quelle: str               # "anker" (optimiert) oder "kette" (rohe Odometrie)

    @classmethod
    def aus_ordner(cls, ordner):
        from spotlab.maps import rekonstruktion

        graph, schnappschuesse, _ = rekonstruktion.lade_karte(ordner)
        posen, quelle = rekonstruktion.posen(graph)
        befund = rekonstruktion.wandzellen(graph, schnappschuesse, posen)
        zellen = befund.zellen if befund is not None else np.zeros((0, 2))
        index, wegpunkte = {}, []
        for wp in graph.waypoints:
            pose = posen.get(wp.id)
            if pose is None:
                continue
            index[wp.id] = len(wegpunkte)
            wegpunkte.append((float(pose.x), float(pose.y), wp.annotations.name or ""))
        kanten = [(index[k.id.from_waypoint], index[k.id.to_waypoint]) for k in graph.edges
                  if k.id.from_waypoint in index and k.id.to_waypoint in index]
        return cls(np.asarray(zellen, float).reshape(-1, 2), wegpunkte, kanten, quelle)


def vision_von_seed(verortung):
    """(tx, ty, dgier): ein Seed-Punkt p liegt in „vision“ bei R(dgier)·p + t. None ohne vision."""
    if verortung is None or verortung.vision is None:
        return None
    sx, sy, sg = verortung.seed
    vx, vy, vg = verortung.vision
    dg = vg - sg
    c, s = math.cos(dg), math.sin(dg)
    return vx - (c * sx - s * sy), vy - (s * sx + c * sy), dg


def in_vision(punkte, trafo):
    """(N, 2) Seed-Punkte → (N, 2) in „vision“."""
    p = np.asarray(punkte, float).reshape(-1, 2)
    tx, ty, dg = trafo
    c, s = math.cos(dg), math.sin(dg)
    return np.column_stack([c * p[:, 0] - s * p[:, 1] + tx, s * p[:, 0] + c * p[:, 1] + ty])


@dataclass(frozen=True)
class Abgleich:
    raster: np.ndarray        # (hoehe, breite) Farbnummern, Zeile 0 = UNTEN (kleinstes y)
    ursprung: tuple           # Ecke der Zelle [0, 0] in „vision“
    breite: int
    hoehe: int
    erkannt: int              # gesehene Wandzellen mit Kartenwand in NAH_M
    neu: int                  # gesehene Wandzellen ohne
    fehlt: int                # Kartenwandzellen, die Spot jetzt frei sieht
    anteil: float | None      # erkannt ÷ (erkannt + neu), None unter MIN_WANDZELLEN


def abgleich(skizze, waende_vision, spot_xy, t, verloren=False):
    """Kartenwände (in „vision“) gegen die Skizze — ein `Abgleich`, oder None ohne beides."""
    z = ZELLE_M
    wp = np.asarray(waende_vision, float).reshape(-1, 2)
    karte = (np.unique(np.floor(wp / z + _HAUCH).astype(np.int64), axis=0) if len(wp)
             else np.zeros((0, 2), np.int64))                     # (i = x, j = y), global
    leer = np.zeros((0, 2), np.int64)
    erkannt_k, fehlt_k, neu_s = leer, leer, leer
    erkannt = neu = fehlt = 0
    if not skizze.leer and not verloren:
        erkannt_k, fehlt_k, neu_s, erkannt, neu, fehlt = _vergleiche(skizze, karte, spot_xy, t)
    alle = np.vstack([karte, neu_s])
    if not len(alle):
        return None
    i0, j0 = alle.min(axis=0)
    i1, j1 = alle.max(axis=0)
    breite, hoehe = int(i1 - i0 + 1), int(j1 - j0 + 1)
    raster = np.zeros((hoehe, breite), np.uint8)
    for zellen, code in ((karte, KARTE_UNGEPRUEFT), (erkannt_k, KARTE_ERKANNT),
                         (fehlt_k, KARTE_FEHLT), (neu_s, KARTE_NEU)):
        if len(zellen):
            raster[zellen[:, 1] - j0, zellen[:, 0] - i0] = code
    gesehen = erkannt + neu
    anteil = erkannt / gesehen if gesehen >= MIN_WANDZELLEN else None
    return Abgleich(raster, (float(i0 * z), float(j0 * z)), breite, hoehe, erkannt, neu, fehlt,
                    anteil)


def _vergleiche(skizze, karte, spot_xy, t):
    """Im Fenster um Spot: (erkannt_karte, fehlt_karte, neu_skizze, n_erkannt, n_neu, n_fehlt)."""
    z = ZELLE_M
    r = int(math.ceil((BLICK_M + NAH_M) / z)) + 1
    si, sj = int(math.floor(spot_xy[0] / z)), int(math.floor(spot_xy[1] / z))
    n = 2 * r + 1
    fi, fj = si - r, sj - r                                  # globaler Index der Fensterecke
    oi = int(round(skizze.ursprung[0] / z))
    oj = int(round(skizze.ursprung[1] / z))
    zustand = np.full((n, n), skizzenmodul.UNBEKANNT, np.uint8)
    zeit = np.full((n, n), -np.inf)
    hoehe, breite = skizze.zustand.shape
    # Überlappung Fenster/Skizze in Skizzenindizes
    a_z, b_z = max(fj - oj, 0), min(fj - oj + n, hoehe)
    a_s, b_s = max(fi - oi, 0), min(fi - oi + n, breite)
    if a_z < b_z and a_s < b_s:
        zustand[a_z - (fj - oj):b_z - (fj - oj), a_s - (fi - oi):b_s - (fi - oi)] = \
            skizze.zustand[a_z:b_z, a_s:b_s]
        zeit[a_z - (fj - oj):b_z - (fj - oj), a_s - (fi - oi):b_s - (fi - oi)] = \
            skizze.zeit[a_z:b_z, a_s:b_s]
    jj, ii = np.mgrid[0:n, 0:n]
    abstand = np.hypot((fi + ii + 0.5) * z - spot_xy[0], (fj + jj + 0.5) * z - spot_xy[1])
    blick = (abstand <= BLICK_M) & (t - zeit <= FRISCH_S) & (zustand != skizzenmodul.UNBEKANNT)
    s_wand = blick & (zustand == skizzenmodul.WAND)
    s_frei = blick & (zustand == skizzenmodul.FREI)
    k = np.zeros((n, n), bool)
    if len(karte):
        drin = ((karte[:, 0] >= fi) & (karte[:, 0] < fi + n)
                & (karte[:, 1] >= fj) & (karte[:, 1] < fj + n))
        k[karte[drin, 1] - fj, karte[drin, 0] - fi] = True
    rad = int(round(NAH_M / z))
    k_nah, s_wand_nah = _weite(k, rad), _weite(s_wand, rad)
    erkannt_k = k & s_wand_nah
    fehlt_k = k & ~s_wand_nah & s_frei
    treffer = s_wand & k_nah
    neu = s_wand & ~k_nah

    def global_(maske):
        jz, iz = np.nonzero(maske)
        return np.column_stack([iz + fi, jz + fj]).astype(np.int64)

    return (global_(erkannt_k), global_(fehlt_k), global_(neu),
            int(treffer.sum()), int(neu.sum()), int(fehlt_k.sum()))


def _weite(maske, r):
    """Jede wahre Zelle wächst um eine Scheibe mit Halbmesser r Zellen."""
    if r <= 0 or not maske.any():
        return maske.copy()
    h, w = maske.shape
    p = np.pad(maske, r)
    aus = np.zeros_like(maske)
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            if di * di + dj * dj <= r * r:
                aus |= p[r + di:r + di + h, r + dj:r + dj + w]
    return aus


def png(abgleich_):
    """Das Raster als PNG mit Palette (Zeile 0 = oben) — die GUI legt ihre Farben darüber."""
    from PIL import Image

    bild = Image.fromarray(np.flipud(abgleich_.raster), mode="P")
    grau = []
    for i in range(256):
        grau += [i, i, i]
    bild.putpalette(grau)
    puffer = io.BytesIO()
    bild.save(puffer, format="PNG")
    return puffer.getvalue()
