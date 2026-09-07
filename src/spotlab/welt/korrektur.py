"""Der Korrigierer: Wandluecken schliessen, das Gelaende uebernehmen.

Reine Standardbibliothek. Eine rekonstruierte Karte hat Waende mit Luecken an
Ecken und mitten im Gang, und manche Linie liegt quer ueber den Weg. Hier
werden Kandidaten gesucht (Luecke, Ecke, Anschluss, kreuzende Wand), mit dem
gelaufenen Weg und dem Pauspapier beurteilt -- der Roboter lief hindurch: ein
Durchgang; Punkte in der Luecke: eine Wand -- und auf Entscheid angewendet.
Unklares bleibt liegen, bis der Autor entscheidet.

Alles Geometrie auf dem `Raum`; die GUI zeigt nur die Liste und leuchtet die
Strecken auf.
"""

import math
from dataclasses import dataclass, replace

MAX_LUECKE_M = 1.5          # weiter auseinander schliesst der Korrigierer nichts
WINKEL_LUECKE_GRAD = 15.0   # so schraeg duerfen Wand und Wand fuer Luecke und Ecke stehen
WINKEL_ANSCHLUSS_GRAD = 25.0
BERUEHRT_M = 0.02           # naeher ist schon geschlossen
INDEX_ZELLE_M = 0.1         # Zellen des Punktindex
PROBE_M = 0.05              # Abtastung der Lueckenstrecken
PUNKTE_JE_ZELLE = 2         # ab hier "hat Punkte"
ANTEIL_WAND = 0.6           # so viele Proben mit Punkten machen eine Wand


@dataclass(frozen=True)
class Luecke:
    art: str          # "luecke" | "ecke" | "anschluss" | "kreuzt"
    waende: tuple     # Indizes im Raum: (i, j) bzw. (i,) bei "kreuzt"
    enden: tuple      # je rueckendem Ende: 1 oder 2, in der Reihenfolge von `waende`
    ziel: tuple       # (x, y): wohin die Enden ruecken (bei "kreuzt": die Wandmitte)
    strecken: tuple   # [(x1, y1, x2, y2)]: was Wand wuerde (bei "kreuzt": die Wand)
    laenge: float
    vorschlag: str    # "wand" | "durchgang" | "loeschen" | "unklar"
    grund: str


# ------------------------------------------------------------- Geometrie


def _ende(wand, nummer):
    return (wand.x1, wand.y1) if nummer == 1 else (wand.x2, wand.y2)


def _winkel_diff(a, b):
    return abs(((a - b) + 90.0) % 180.0 - 90.0)


def _abstand(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _schnitt(a1, a2, b1, b2):
    """Schnittpunkt der Geraden durch a1-a2 und b1-b2, None bei parallel."""
    d = (a2[0] - a1[0]) * (b2[1] - b1[1]) - (a2[1] - a1[1]) * (b2[0] - b1[0])
    if abs(d) < 1e-9:
        return None
    t = ((b1[0] - a1[0]) * (b2[1] - b1[1]) - (b1[1] - a1[1]) * (b2[0] - b1[0])) / d
    return (a1[0] + t * (a2[0] - a1[0]), a1[1] + t * (a2[1] - a1[1]))


def _fusspunkt(p, a, b):
    """(Fusspunkt von p auf der Geraden a-b, Parameter t: 0 bei a, 1 bei b)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
    return (a[0] + t * dx, a[1] + t * dy), t


def _kreuzt(a1, a2, b1, b2):
    """Schneiden sich die Strecken a1-a2 und b1-b2 (echt, nicht nur beruehrend)?"""
    def seite(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    s1, s2 = seite(a1, a2, b1), seite(a1, a2, b2)
    s3, s4 = seite(b1, b2, a1), seite(b1, b2, a2)
    return (s1 * s2 < 0) and (s3 * s4 < 0)


def _durch_dritte(raum, strecke, ausser):
    a, b = (strecke[0], strecke[1]), (strecke[2], strecke[3])
    return any(i not in ausser and _kreuzt(a, b, (w.x1, w.y1), (w.x2, w.y2))
               for i, w in enumerate(raum.waende))


# ------------------------------------------------------------- Kandidaten


def _kandidaten_fuer_ende(raum, i, ende, max_luecke, winkel_grad):
    wand = raum.waende[i]
    e = _ende(wand, ende)
    treffer = []
    for j, andere in enumerate(raum.waende):
        if j == i or andere.laenge <= 0:
            continue
        diff = _winkel_diff(wand.winkel, andere.winkel)
        f_nummer = min((1, 2), key=lambda n: _abstand(e, _ende(andere, n)))
        f = _ende(andere, f_nummer)
        if diff <= winkel_grad:
            d = _abstand(e, f)
            if BERUEHRT_M < d <= max_luecke:
                treffer.append(Luecke("luecke", (i, j), (ende, f_nummer), f, ((*e, *f),),
                                      d, "unklar", ""))
        elif abs(diff - 90.0) <= winkel_grad:
            s = _schnitt((wand.x1, wand.y1), (wand.x2, wand.y2),
                         (andere.x1, andere.y1), (andere.x2, andere.y2))
            if s is not None:
                d_e, d_f = _abstand(e, s), _abstand(f, s)
                if BERUEHRT_M < d_e <= max_luecke and d_f <= max_luecke:
                    strecken = tuple(st for st in ((*e, *s), (*f, *s))
                                     if _abstand(st[:2], st[2:]) > BERUEHRT_M)
                    treffer.append(Luecke("ecke", (i, j), (ende, f_nummer), s, strecken,
                                          d_e + d_f, "unklar", ""))
        if abs(diff - 90.0) <= WINKEL_ANSCHLUSS_GRAD:
            p, t = _fusspunkt(e, (andere.x1, andere.y1), (andere.x2, andere.y2))
            d = _abstand(e, p)
            if 0.05 <= t <= 0.95 and BERUEHRT_M < d <= max_luecke:
                treffer.append(Luecke("anschluss", (i, j), (ende,), p, ((*e, *p),),
                                      d, "unklar", ""))
    treffer = [t for t in treffer
               if not any(_durch_dritte(raum, st, set(t.waende)) for st in t.strecken)]
    return min(treffer, key=lambda t: t.laenge) if treffer else None


def _schluessel(luecke):
    """Dieselbe Luecke, von beiden Enden aus gesehen, ist eine: das Paar und die Strecke."""
    punkte = frozenset((round(x, 3), round(y, 3))
                       for st in luecke.strecken for x, y in ((st[0], st[1]), (st[2], st[3])))
    return (frozenset(luecke.waende), luecke.art, punkte)


def _kreuzende(raum, weg):
    """Waende, die eine Strecke des gelaufenen Wegs schneiden: Fehler der Linienfindung."""
    gefunden = []
    strecken = list(zip(weg, weg[1:]))
    for i, wand in enumerate(raum.waende):
        a, b = (wand.x1, wand.y1), (wand.x2, wand.y2)
        if any(_kreuzt(a, b, (p[0], p[1]), (q[0], q[1])) for p, q in strecken):
            gefunden.append(Luecke("kreuzt", (i,), (), wand.mitte, ((*a, *b),), wand.laenge,
                                   "loeschen", "kreuzt den Weg des Roboters"))
    return gefunden


# ------------------------------------------------------------- Vorschlaege


def punktindex(pauspapier, zelle=INDEX_ZELLE_M):
    """Zelle -> Anzahl Punkte; einmal ueber das Pauspapier, dann sind Anfragen billig."""
    index = {}
    for x, y in pauspapier:
        schluessel = (math.floor(x / zelle), math.floor(y / zelle))
        index[schluessel] = index.get(schluessel, 0) + 1
    return index


def _hat_punkte(index, x, y, zelle=INDEX_ZELLE_M, mindestens=PUNKTE_JE_ZELLE):
    i, j = math.floor(x / zelle), math.floor(y / zelle)
    return any(index.get((i + di, j + dj), 0) >= mindestens
               for di in (-1, 0, 1) for dj in (-1, 0, 1))


def _punkte_entlang(strecken, index, schritt=PROBE_M):
    """Anteil der Proben entlang der Strecken, an denen das Pauspapier Punkte hat."""
    proben, mit = 0, 0
    for x1, y1, x2, y2 in strecken:
        laenge = math.hypot(x2 - x1, y2 - y1)
        n = max(1, math.ceil(laenge / schritt))
        for k in range(n + 1):
            t = k / n
            proben += 1
            if _hat_punkte(index, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t):
                mit += 1
    return mit / proben if proben else 0.0


def _weg_kreuzt(strecken, weg):
    for p, q in zip(weg, weg[1:]):
        for x1, y1, x2, y2 in strecken:
            if _kreuzt((x1, y1), (x2, y2), (p[0], p[1]), (q[0], q[1])):
                return True
    return False


def _mit_vorschlag(luecke, weg, index):
    if luecke.art == "kreuzt":
        return luecke
    if _weg_kreuzt(luecke.strecken, weg):
        return replace(luecke, vorschlag="durchgang", grund="der Roboter lief hindurch")
    if index and _punkte_entlang(luecke.strecken, index) >= ANTEIL_WAND:
        return replace(luecke, vorschlag="wand", grund="Punkte in der Lücke")
    return replace(luecke, vorschlag="unklar", grund="kein Weg, keine Punkte — bitte entscheiden")


def finde_luecken(raum, weg=(), pauspapier=(), max_luecke=MAX_LUECKE_M,
                  winkel_grad=WINKEL_LUECKE_GRAD):
    """Die Kandidaten des Raums, kuerzeste zuerst, je mit Vorschlag und Grund.

    Je Wandende der kuerzeste Anschluss (Luecke, Ecke, Anschluss) bis
    `max_luecke`; jedes Paar einmal; dazu die Waende, die den Weg kreuzen.
    """
    gefunden, gesehen = [], set()
    for i, wand in enumerate(raum.waende):
        if wand.laenge <= 0:
            continue
        for ende in (1, 2):
            luecke = _kandidaten_fuer_ende(raum, i, ende, max_luecke, winkel_grad)
            if luecke is None:
                continue
            schluessel = _schluessel(luecke)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            gefunden.append(luecke)
    gefunden += _kreuzende(raum, weg)
    index = punktindex(pauspapier)
    gefunden = [_mit_vorschlag(lk, list(weg), index) for lk in gefunden]
    return sorted(gefunden, key=lambda lk: lk.laenge)


# ------------------------------------------------------------- Anwenden


def wende_an(raum, luecken, entscheide):
    """Die Entscheide anwenden: {index: "wand" | "durchgang" | "loeschen" | "lassen"}.

    "wand" rueckt die genannten Enden auf das Ziel -- die Waende bleiben
    getrennte Elemente und beruehren sich dort, kein Verschmelzen, keine
    Indexverschiebung. "loeschen" merkt die Wand vor; geloescht wird am Ende.
    "durchgang" und "lassen" tun nichts. Das `z` der Waende bleibt.
    """
    waende = list(raum.waende)
    weg = set()
    for index, luecke in enumerate(luecken):
        entscheid = entscheide.get(index, "lassen")
        if entscheid == "wand" and luecke.art != "kreuzt":
            for wand_index, ende in zip(luecke.waende, luecke.enden):
                w = waende[wand_index]
                x, y = round(luecke.ziel[0], 3), round(luecke.ziel[1], 3)
                waende[wand_index] = replace(w, x1=x, y1=y) if ende == 1 else replace(w, x2=x, y2=y)
        elif entscheid == "loeschen":
            weg.update(luecke.waende)
    if not weg and all(a is b for a, b in zip(waende, raum.waende)):
        return raum
    return replace(raum, waende=tuple(w for i, w in enumerate(waende) if i not in weg))


def uebernimm_gelaende(raum, gelaende, boeden_aufloesen):
    """Das Gelaende in den Raum: Rampen und Podeste gehen darin auf (wenn gewuenscht),
    Waende und Tags bekommen das `z` des Grunds unter ihrer Mitte, Treppen bleiben."""
    boeden = raum.boeden
    if boeden_aufloesen:
        boeden = tuple(b for b in raum.boeden if b.stufen > 0)

    def z_von(x, y, sonst):
        h = gelaende.hoehe_bei(x, y)
        return sonst if h is None else round(h, 3)

    waende = tuple(replace(w, z=z_von(*w.mitte, w.z)) for w in raum.waende)
    tags = tuple(replace(t, z=z_von(t.x, t.y, t.z)) for t in raum.tags)
    return replace(raum, gelaende=gelaende, boeden=boeden, waende=waende, tags=tags)
