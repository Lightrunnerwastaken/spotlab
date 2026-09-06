"""Wie hoch ist der Boden hier? -- die eine Antwort fuer alle Sichten.

Reine Standardbibliothek. `boden_bei` ist die einzige Stelle, die entscheidet,
auf welchem Boden ein Punkt liegt; 2D-Sim, MuJoCo-Welt, 3D-Sicht, Ebenen im
Editor und die Pruefungen rufen sie. `kaesten_fuer` ist die einzige Zerlegung
eines Bodens in Kaesten -- MuJoCo und die 3D-Sicht bekommen dieselben.

DIE Regel fuer Hindernisse steht in raum.py: ein Hoehensprung ueber MAX_STUFE_M.
Hier wird sie zu Klippen (Kanten, an denen der Boden springt) und zum
Koerperband (was eine Wand oder ein Block treffen kann).

Treppen: vorwaerts hoch, rueckwaerts runter -- die Regel von Boston Dynamics.
`treppe_erlaubt` formuliert sie einmal; der Sim verweigert den Rest, bis
Abnahmepunkt A25 etwas anderes ergibt.
"""

import math
from dataclasses import dataclass

from spotlab.welt.kollision import sicht_frei
from spotlab.welt.raum import MAX_STUFE_M, Block, Boden, RaumTag, Wand

# Was den Koerper trifft: dieses Band ueber dem Boden, auf dem er steht. Unten
# eine Zelle Luft (ein Fuss hebt sich), oben die Rueckenhoehe des stehenden Spot.
KOERPER_BAND_M = (0.10, 0.70)
# Bis hierhin gilt eine Treppe als "vor dem Roboter" (Fuss- oder Kopfkante).
TREPPE_SICHT_M = 1.5
# So schraeg darf die Nase zur Bergauf-Achse stehen, damit die Treppe zaehlt.
TREPPE_WINKEL_GRAD = 45.0
# Eine Rampe ist in MuJoCo und in 3D ein geneigter Kasten dieser Dicke.
RAMPE_DICKE_M = 0.20
# Ein Tag ist von einer anderen Ebene aus unsichtbar, wenn er so viel hoeher
# oder tiefer haengt als die Kameras (Annahme; A22 misst die Reichweite).
TAG_HOEHENFENSTER_M = 1.5

__all__ = [
    "MAX_STUFE_M", "KOERPER_BAND_M", "TREPPE_SICHT_M", "TREPPE_WINKEL_GRAD",
    "RAMPE_DICKE_M", "TAG_HOEHENFENSTER_M", "Treppenlage",
    "boden_bei", "neigung_bei", "nick_grad", "ebenen", "boden_z", "hoehenband",
    "auf_ebene", "trifft_koerper", "klippen", "treppe_vor", "treppen_in_sicht",
    "bergauf_achse", "treppe_erlaubt", "kaesten_fuer",
]


# ------------------------------------------------------------- der Boden


def boden_bei(raum, x, y, z_nahe=None, ohne=None):
    """(z, boden | None): der Boden unter dem Punkt.

    Kandidaten sind der Grundboden (0.0) und jeder Boden, der den Punkt
    enthaelt. Ohne `z_nahe` (eine frische Frage: Editor, Start) gilt der
    hoechste -- der Grund unter einem Podest ist kein Boden. Mit `z_nahe`
    (ein Roboter, der schon irgendwo steht) gilt der hoechste ERREICHBARE
    (innerhalb MAX_STUFE_M), sonst der naechste: so bleibt ein Roboter unter
    einer Bruecke unten, einer auf der Bruecke oben, und ein Podest eine Stufe
    hoeher nimmt er mit. `ohne` schliesst einen Boden aus: was liegt NEBEN
    diesem Boden?
    """
    kandidaten = [(0.0, None)]
    for boden in raum.boeden:
        if boden is ohne:
            continue
        lx, ly = boden.lokal(x, y)
        if abs(lx) <= boden.breite / 2 and abs(ly) <= boden.tiefe / 2:
            kandidaten.append((boden.hoehe_lokal(lx), boden))
    if z_nahe is None:
        return max(kandidaten, key=lambda k: (k[0], k[1] is not None))
    erreichbar = [k for k in kandidaten if abs(k[0] - z_nahe) <= MAX_STUFE_M]
    if erreichbar:
        return max(erreichbar, key=lambda k: (k[0], k[1] is not None))
    return min(kandidaten, key=lambda k: (abs(k[0] - z_nahe), -k[0]))


def neigung_bei(raum, x, y, z_nahe=None):
    """(dz/dx, dz/dy) im Weltframe des Bodens unter dem Punkt; (0, 0) auf Podest und Grund."""
    _z, boden = boden_bei(raum, x, y, z_nahe)
    if boden is None or boden.anstieg == 0.0 or boden.breite <= 0:
        return 0.0, 0.0
    steigung = boden.anstieg / boden.breite
    winkel = math.radians(boden.drehung)
    return steigung * math.cos(winkel), steigung * math.sin(winkel)


def nick_grad(raum, x, y, yaw, z_nahe=None):
    """Nick des Koerpers entlang der Fahrtrichtung in Grad. `yaw` im Bogenmass.

    EINE Konvention fuer Nick, hier wie ueberall: Drehung um die y-Achse nach
    der Rechte-Hand-Regel, also NEGATIV bei Nase hoch -- so liest
    `api/state.py::rpy_aus` den echten Spot, so rechnet MuJoCo. Bergauf fahren
    gibt einen negativen Wert.
    """
    dzdx, dzdy = neigung_bei(raum, x, y, z_nahe)
    return -math.degrees(math.atan(dzdx * math.cos(yaw) + dzdy * math.sin(yaw)))


def ebenen(raum):
    """Sortierte, auf 0.1 m gerundete Bodenhoehen: 0.0, jedes z und z_oben der Boeden."""
    hoehen = {0.0}
    for boden in raum.boeden:
        hoehen.add(round(boden.z, 1))
        hoehen.add(round(boden.z_oben, 1))
    return sorted(hoehen)


def boden_z(raum):
    """Der tiefste Boden im Raum -- dort liegt die Bodenebene der 3D-Welt."""
    return min([0.0] + [min(b.z, b.z_oben) for b in raum.boeden])


def hoehenband(element, raum):
    """(unten, oben) eines Elements ueber dem Grundboden."""
    if isinstance(element, Wand):
        return (element.z, element.z + raum.wand_hoehe)
    if isinstance(element, Block):
        return (element.z, element.z + element.hoehe)
    if isinstance(element, RaumTag):
        return (element.z + element.hoehe, element.z + element.hoehe)
    if isinstance(element, Boden):
        return (min(element.z, element.z_oben), max(element.z, element.z_oben))
    raise TypeError(f"kein Raumelement: {element!r}")


def auf_ebene(element, raum, ebene, toleranz=0.3):
    """Gehoert das Element zur Ebene?

    Wand, Block und Tag stehen auf dem Boden ihres `z`: sie gehoeren zur Ebene,
    auf der sie stehen (± toleranz). Ein Boden gehoert zu jeder Ebene, die
    sein Hoehenband beruehrt -- eine Treppe also zu beiden, die sie verbindet.
    """
    if isinstance(element, Boden):
        unten, oben = hoehenband(element, raum)
        return unten - toleranz <= ebene <= oben + toleranz
    return abs(element.z - ebene) <= toleranz


def trifft_koerper(band, z):
    """Trifft ein Element mit diesem Hoehenband den Koerper, der auf Hoehe z steht?"""
    unten, oben = band
    return unten <= z + KOERPER_BAND_M[1] and oben >= z + KOERPER_BAND_M[0]


# ------------------------------------------------------------- Klippen


def _kante_stuecke(a, b, schritt):
    """Die Strecke a-b in Stuecken von hoechstens `schritt`: [(x1, y1, x2, y2)]."""
    laenge = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, math.ceil(laenge / schritt))
    return [
        (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n,
         a[0] + (b[0] - a[0]) * (i + 1) / n, a[1] + (b[1] - a[1]) * (i + 1) / n)
        for i in range(n)
    ]


def klippen(raum, schritt=0.05, alles=False):
    """[(x1, y1, x2, y2)]: Kanten, an denen der Boden um mehr als MAX_STUFE_M springt.

    Je Boden werden die vier Kanten in `schritt`-Stuecken abgetastet: innen
    gilt die eigene Hoehe, aussen der Boden daneben (ohne diesen) bei der
    eigenen Hoehe als z_nahe. Eine Rampe hat so keine Klippe am Fuss und keine
    am Kopf, aber an den Seiten, sobald sie hoeher als eine Stufe ueber dem
    Nachbarboden liegt. `alles=True` macht jede Kante einer Rampe oder Treppe
    zur Klippe -- der Treppenmodus ist aus.
    Zusammenhaengende Stuecke einer Kante werden zu einer Strecke.
    """
    versatz = 1e-3
    ergebnis = []
    for boden in raum.boeden:
        ecken = boden.ecken()
        for erste, zweite in zip(ecken, ecken[1:] + ecken[:1]):
            # Nach innen zeigende Normale der Kante (Ecken laufen gegen den Uhrzeigersinn).
            dx, dy = zweite[0] - erste[0], zweite[1] - erste[1]
            laenge = math.hypot(dx, dy)
            if laenge <= 0:
                continue
            nx, ny = -dy / laenge, dx / laenge
            offen = None
            for stueck in _kante_stuecke(erste, zweite, schritt):
                mx, my = (stueck[0] + stueck[2]) / 2, (stueck[1] + stueck[3]) / 2
                innen = boden.hoehe_lokal(boden.lokal(mx + nx * versatz, my + ny * versatz)[0])
                aussen, _ = boden_bei(raum, mx - nx * versatz, my - ny * versatz,
                                      z_nahe=innen, ohne=boden)
                klippe = abs(innen - aussen) > MAX_STUFE_M or (alles and boden.anstieg != 0.0)
                if klippe:
                    offen = (offen[0], offen[1], stueck[2], stueck[3]) if offen else stueck
                elif offen is not None:
                    ergebnis.append(offen)
                    offen = None
            if offen is not None:
                ergebnis.append(offen)
    return ergebnis


# ------------------------------------------------------------- Treppen


@dataclass(frozen=True)
class Treppenlage:
    boden: Boden
    richtung: str            # "auf" (der Roboter steht am Fuss) | "ab" (am Kopf)
    abstand: float           # zur naechsten Kante, Meter
    peilung_grad: float      # zur Kante, links positiv, 0 = geradeaus
    achsenwinkel_grad: float # Fahrtrichtung gegen die Bergauf-Achse, 0..180


def _naechster_punkt(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return a
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / laenge2))
    return (a[0] + t * dx, a[1] + t * dy)


def _winkel_diff(a, b):
    """|a - b| in Grad, auf 0..180."""
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def bergauf_achse(boden):
    """Richtung der Bergauf-Achse eines Bodens in Grad (Weltframe)."""
    return (boden.drehung + (180.0 if boden.anstieg < 0 else 0.0)) % 360.0


def treppen_in_sicht(raum, x, y, grad, reichweite, z_nahe=None):
    """Alle Treppen, deren naechste Kante (Fuss oder Kopf) in `reichweite` liegt
    und frei zu sehen ist -- als Treppenlagen, naechste zuerst.

    `richtung` sagt, wo der Roboter steht: am Fuss ("auf") oder am Kopf ("ab");
    `peilung_grad` zeigt zur naechsten Kante; `achsenwinkel_grad` ist der
    Winkel zwischen seiner Nase und der Bergauf-Achse.
    """
    lagen = []
    for boden in raum.boeden:
        if boden.stufen <= 0 or boden.anstieg == 0.0:
            continue
        ecken = boden.ecken()
        # Ecken: 0 = (-hb, -ht), 1 = (hb, -ht), 2 = (hb, ht), 3 = (-hb, ht).
        # Fusskante bei -breite/2 (Ecken 3-0), Kopfkante bei +breite/2 (1-2);
        # bei negativem Anstieg ist es umgekehrt.
        fuss, kopf = (ecken[3], ecken[0]), (ecken[1], ecken[2])
        if boden.anstieg < 0:
            fuss, kopf = kopf, fuss
        beste = None
        for richtung, kante in (("auf", fuss), ("ab", kopf)):
            punkt = _naechster_punkt(x, y, *kante)
            abstand = math.hypot(punkt[0] - x, punkt[1] - y)
            if abstand > reichweite or not sicht_frei(raum, (x, y), punkt):
                continue
            peilung = math.degrees(math.atan2(punkt[1] - y, punkt[0] - x)) - grad
            peilung = (peilung + 180.0) % 360.0 - 180.0
            if peilung <= -180.0 + 1e-9:
                peilung = 180.0
            lage = Treppenlage(boden, richtung, abstand, peilung,
                               _winkel_diff(grad, bergauf_achse(boden)))
            if beste is None or lage.abstand < beste.abstand:
                beste = lage
        if beste is not None:
            lagen.append(beste)
    return sorted(lagen, key=lambda lage: lage.abstand)


def treppe_vor(raum, x, y, grad, z_nahe=None):
    """Die naechste Treppe im Weg -- oder None.

    Im Weg heisst: Fuss- oder Kopfkante liegt naeher als TREPPE_SICHT_M, vor
    oder hinter dem Roboter (Peilung innerhalb 45 Grad von 0 oder 180), und die
    Sichtlinie zur Kante ist frei. Die Regel (`treppe_erlaubt`) entscheidet
    aus dem Achsenwinkel.
    """
    for lage in treppen_in_sicht(raum, x, y, grad, TREPPE_SICHT_M, z_nahe):
        if lage.abstand <= 1e-9 or min(_winkel_diff(lage.peilung_grad, 0.0),
                                        _winkel_diff(lage.peilung_grad, 180.0)) <= TREPPE_WINKEL_GRAD:
            return lage
    return None


def treppe_erlaubt(richtung, vx, achsenwinkel_grad):
    """(erlaubt, verlangt): auf einer Treppe zeigt die Nase bergauf -- immer.

    Das ist die ganze Regel: vorwaerts hoch und rueckwaerts runter sind beide
    "Nase bergauf"; vorwaerts runter und rueckwaerts hoch sind beide "Nase
    bergab" und verboten. Stehen und Drehen darf man. `richtung` ("auf" am
    Fuss, "ab" am Kopf) bestimmt nur, was die Meldung verlangt.
    """
    verlangt = "vorwärts hoch" if richtung == "auf" else "rückwärts runter"
    if abs(vx) <= 1e-9:
        return True, verlangt
    return achsenwinkel_grad <= TREPPE_WINKEL_GRAD, verlangt


# ------------------------------------------------------------- Kaesten


def _kasten(name, boden, lx, breite_lokal, z_unten, z_oben, pitch_grad=0.0):
    """Ein Kasten im Rahmen des Bodens: (name, x, y, z_mitte, hx, hy, hz, yaw, pitch)."""
    c, s = math.cos(math.radians(boden.drehung)), math.sin(math.radians(boden.drehung))
    return (name, boden.x + lx * c, boden.y + lx * s, (z_unten + z_oben) / 2,
            breite_lokal / 2, boden.tiefe / 2, (z_oben - z_unten) / 2,
            boden.drehung, pitch_grad)


def kaesten_fuer(boden, boden_z):
    """Die Kaesten eines Bodens ueber der Bodenebene `boden_z`.

    Tupel (name, x, y, z_mitte, hx, hy, hz, yaw_grad, pitch_grad) mit halben
    Kantenlaengen wie MuJoCo; `pitch_grad` ist die Drehung um die eigene
    y-Achse nach der Rechte-Hand-Regel -- NEGATIV, wenn das +x-Ende sich hebt
    (dieselbe Konvention wie `nick_grad`, `State.pitch` und MuJoCo).
    Podest: ein Kasten von boden_z bis z (keiner, wenn z <= boden_z).
    Treppe: je Stufe ein Kasten bis zur Trittflaeche. Rampe: ein geneigter
    Kasten der Dicke RAMPE_DICKE_M, dessen Oberkante auf der Rampenlinie liegt,
    plus ein Fuellkasten bis zum tieferen Ende. Namen beginnen mit boden_,
    stufe_, rampe_ -- die Puppe ignoriert Beruehrungen damit wie mit `floor`.
    """
    kaesten = []
    if boden.breite <= 0 or boden.tiefe <= 0:
        return kaesten
    if boden.art == "podest":
        if boden.z > boden_z + 1e-9:
            kaesten.append(_kasten(f"boden_{boden.name}", boden, 0.0, boden.breite, boden_z, boden.z))
        return kaesten
    if boden.art == "treppe":
        tiefe = boden.breite / boden.stufen
        for i in range(boden.stufen):
            lx = -boden.breite / 2 + (i + 0.5) * tiefe
            oben = boden.z + boden.anstieg * (i + 1) / boden.stufen
            unten = boden_z
            if oben <= unten + 1e-9:
                continue
            kaesten.append(_kasten(f"stufe_{boden.name}_{i}", boden, lx, tiefe, unten, oben))
        return kaesten
    # Rampe: Dicke senkrecht zur Flaeche; die Kastenmitte liegt um die halbe
    # Dicke unter der Rampenlinie, entlang der Flaechennormalen.
    neigung = math.radians(boden.neigung_grad)
    hyp = math.hypot(boden.breite, boden.anstieg)
    mitte_z = (boden.z + boden.z_oben) / 2 - (RAMPE_DICKE_M / 2) * math.cos(neigung)
    lx = (RAMPE_DICKE_M / 2) * math.sin(neigung)   # die Normale zeigt bergab-waerts nach hinten
    c, s = math.cos(math.radians(boden.drehung)), math.sin(math.radians(boden.drehung))
    kaesten.append((f"rampe_{boden.name}", boden.x + lx * c, boden.y + lx * s, mitte_z,
                    hyp / 2, boden.tiefe / 2, RAMPE_DICKE_M / 2, boden.drehung,
                    -boden.neigung_grad))
    tiefes_ende = min(boden.z, boden.z_oben)
    if tiefes_ende > boden_z + 1e-9:
        kaesten.append(_kasten(f"boden_{boden.name}", boden, 0.0, boden.breite, boden_z, tiefes_ende))
    return kaesten
