"""Darf der Roboter dorthin, und was sieht er von hier aus?

Reine Standardbibliothek, keine Physik -- Abstaende zwischen Punkten, Strecken
und achsparallelen Rechtecken. Was daraus eine spotlab-Form macht, tut
`backends/sim.py`.

DER ROBOTER IST EIN KREIS mit 0.27 m Radius: breiter als Spots halbe Breite
(0.25 m bei rund 1.1 x 0.5 m Grundflaeche), aber eine Gitterzelle KLEINER als
der Vorgabe-Rand von `ObstacleGrid.is_free` (0.3 m). Was das Gitter frei nennt,
muss im Sim auch begehbar sein -- sonst folgt ein Programm der freien Strecke
und bleibt an einer Tuerkante haengen, wie am 06.09.2026 mit 0.35 m Radius; die
Zelle Luft braucht es, weil das Gitter Abstaende nur je Zellmitte kennt. Die
Vereinfachung hat eine Richtung: ein Kreis kann sich nicht seitlich durch eine
schmale Luecke drehen, ein echter Spot schon, und beim Drehen streift ein
Kreis nie mit der Nase (siehe `bewege`). `tests/test_welt_kollision.py` haelt
die Kopplung an den Gitter-Rand fest.

Bloecke sind gedreht: ein Pruefpunkt wird in den Rahmen des Blocks gedreht
(`Block.lokal`), danach ist der Abstand der zum achsparallelen Rechteck --
dasselbe Prinzip in `wahrnehmung.py` und `backends/mujoco.py`. Waende haben
eine Dicke je Raum; die halbe Dicke zaehlt zum Radius.

Hoehe (Fassung 3): mit `z` zaehlt eine Wand oder ein Block nur, wenn sein
Hoehenband den Koerper trifft (`hoehe.trifft_koerper`), und Klippen -- Kanten,
an denen der Boden um mehr als MAX_STUFE_M springt -- sind Hindernislinien
namens "Kante". `bewege_mit_hoehe` fuehrt die Hoehe mit; `bewege` bleibt fuer
alle, die keine kennen. Die Importe aus `hoehe.py` sind spaet, weil jenes
`sicht_frei` von hier braucht.
"""

import math

from spotlab.welt.raum import MAX_STUFE_M

ROBOTER_RADIUS_M = 0.27
# Laengere Schritte werden zerlegt. `dt` kommt aus der Wanduhr und haengt daran,
# wie oft ein Skript den Zustand abfragt; ohne Zerlegung haenge die Zusicherung
# "kein Programm faehrt durch eine Wand" an der Abfragehaeufigkeit.
MAX_SCHRITT_M = 0.10

# Sicherheitsabstand um eine Sperrzone, zusaetzlich zum Roboterradius. Am echten
# Roboter kommt die Pose aus der GraphNav-Verortung; die driftet, und eine Zone
# ist genau dort noetig, wo kein Sensor nachhilft.
ZONE_RAND_M = 0.15


def _abstand_punkt_strecke(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / laenge2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def abstand_block(block, px, py):
    """Abstand eines Weltpunkts zum (gedrehten) Block; 0 im Block."""
    lx, ly = block.lokal(px, py)
    dx = max(abs(lx) - block.breite / 2, 0.0)
    dy = max(abs(ly) - block.tiefe / 2, 0.0)
    return math.hypot(dx, dy)


_KLIPPEN_MEMO = {}


def klippen_von(raum, alles=False):
    """Die Klippen des Raums, einmal je Raum gerechnet (reine Geometrie ohne Pose).

    Gemerkt wird das letzte Ergebnis je (Boeden, Gelaende, alles) -- ueber die
    Identitaet der beiden unveraenderlichen Tupel bzw. Objekte. Der Editor fragt
    bei jeder Mausbewegung; ein Gelaende hat zehntausende Knoten.
    """
    from spotlab.welt.hoehe import klippen

    schluessel = (id(raum.boeden), id(raum.gelaende), alles)
    treffer = _KLIPPEN_MEMO.get(schluessel)
    if treffer is not None and treffer[0] is raum.boeden and treffer[1] is raum.gelaende:
        return treffer[2]
    ergebnis = klippen(raum, alles=alles)
    _KLIPPEN_MEMO.clear()
    _KLIPPEN_MEMO[schluessel] = (raum.boeden, raum.gelaende, ergebnis)
    return ergebnis


def zone_bei(raum, x, y, radius=None):
    """Name der Sperrzone, in deren Rand der Punkt faellt -- oder None.

    ABSICHTLICH nicht in `hindernis_bei`: eine Zone ist eine Regel, kein
    Hindernis. Sie darf im Hindernisgitter nicht auftauchen, sonst wuerde ein
    Programm, das der freien Strecke folgt, sie umfahren statt sie zu
    respektieren -- und der Sensor haette wieder das letzte Wort. Genau das
    soll die Zone aufheben (Glasfront am echten Spot, 07.09.2026).

    Der Rand ist Roboterradius plus `ZONE_RAND_M`.
    """
    if not raum.sperrzonen:
        return None
    if radius is None:
        radius = ROBOTER_RADIUS_M + ZONE_RAND_M
    for zone in raum.sperrzonen:
        lx, ly = zone.lokal(x, y)
        if abs(lx) <= zone.breite / 2 + radius and abs(ly) <= zone.tiefe / 2 + radius:
            return zone.name
    return None


def zone_voraus(raum, pose, strecke=1.0, schritt=0.1):
    """Name der Sperrzone, die vor dem Roboter liegt -- oder None.

    Prueft den Weg von der Pose aus `strecke` weit geradeaus. Der Roboter soll
    schon anhalten, BEVOR er die Zone beruehrt: am echten Gerät kommt die
    Pose aus der GraphNav-Verortung und der Befehl gilt gut eine Sekunde.
    Was hinter oder neben ihm liegt, zaehlt nicht -- rueckwaerts und drehen
    bleiben der Weg aus der Falle.
    """
    if not raum.sperrzonen:
        return None
    x, y, grad = pose
    bogen = math.radians(grad)
    dx, dy = math.cos(bogen), math.sin(bogen)
    schritte = max(1, int(round(strecke / schritt)))
    for i in range(schritte + 1):
        d = strecke * i / schritte
        zone = zone_bei(raum, x + dx * d, y + dy * d)
        if zone is not None:
            return zone
    return None


def hindernis_bei(raum, x, y, radius=ROBOTER_RADIUS_M, z=None, klippen_=None):
    """Name dessen, was hier im Weg steht -- oder None.

    Ohne `z` wie immer: jede Wand, jeder Block. Mit `z` (Hoehe des Bodens unter
    dem Koerper) nur, was das Koerperband trifft -- ein Block auf dem Podest
    steht dem Roboter darunter nicht im Weg. Klippen zaehlen, sobald sie
    uebergeben werden.
    """
    halbe_dicke = raum.wand_dicke / 2
    if z is None:
        def trifft(_element):
            return True
    else:
        from spotlab.welt.hoehe import hoehenband, trifft_koerper

        def trifft(element):
            return trifft_koerper(hoehenband(element, raum), z)
    for wand in raum.waende:
        if trifft(wand) and _abstand_punkt_strecke(x, y, *wand) < radius + halbe_dicke:
            return "Wand"
    for block in raum.bloecke:
        if trifft(block) and abstand_block(block, x, y) < radius:
            return block.name
    for kante in klippen_ or ():
        if _abstand_punkt_strecke(x, y, *kante) < radius:
            return "Kante"
    return None


def frei(raum, x, y, radius=ROBOTER_RADIUS_M):
    return hindernis_bei(raum, x, y, radius) is None


def bewege(raum, von, nach):
    """(neue Pose, Name des Hindernisses oder None).

    Die DREHUNG wird immer uebernommen: ein Kreis, der sich dreht, ueberstreicht
    keine neue Flaeche. Ein Spot in einer Ecke kann sich also herausdrehen -- was
    er in Wirklichkeit auch kann, wenn auch nicht so muehelos.
    """
    x0, y0, _yaw0 = von
    x1, y1, yaw1 = nach
    strecke = math.hypot(x1 - x0, y1 - y0)
    if strecke < 1e-9:
        return (x0, y0, yaw1), None

    schritte = max(1, math.ceil(strecke / MAX_SCHRITT_M))
    letztes_gutes = (x0, y0)
    for i in range(1, schritte + 1):
        anteil = i / schritte
        px = x0 + (x1 - x0) * anteil
        py = y0 + (y1 - y0) * anteil
        getroffen = hindernis_bei(raum, px, py)
        if getroffen is not None:
            return (letztes_gutes[0], letztes_gutes[1], yaw1), getroffen
        letztes_gutes = (px, py)
    return (x1, y1, yaw1), None


def bewege_mit_hoehe(raum, von, nach, z, klippen_):
    """((x, y, yaw), z, Hindernis | None) -- wie `bewege`, mit der Hoehe im Gepaeck.

    Nach jedem Teilschritt fragt `boden_bei` mit der bisherigen Hoehe als
    `z_nahe`; springt der Boden um mehr als eine Stufe, ist das die Klippe von
    innen gesehen, und Spot bleibt am letzten guten Punkt.
    """
    from spotlab.welt.hoehe import boden_bei

    x0, y0, _yaw0 = von
    x1, y1, yaw1 = nach
    strecke = math.hypot(x1 - x0, y1 - y0)
    if strecke < 1e-9:
        return (x0, y0, yaw1), z, None

    schritte = max(1, math.ceil(strecke / MAX_SCHRITT_M))
    letztes_gutes, z_gut = (x0, y0), z
    for i in range(1, schritte + 1):
        anteil = i / schritte
        px = x0 + (x1 - x0) * anteil
        py = y0 + (y1 - y0) * anteil
        getroffen = hindernis_bei(raum, px, py, z=z_gut, klippen_=klippen_)
        if getroffen is None:
            # Eine Sperrzone haelt nur beim HINEINfahren. Wer drinsteht -- von
            # Hand hingestellt, Drift, nachtraeglich eingezeichnet --, muss
            # herauskommen; sonst waere die Regel eine Falle.
            zone = zone_bei(raum, px, py)
            if zone is not None and zone_bei(raum, x0, y0) != zone:
                getroffen = f"Sperrzone {zone}"
        if getroffen is not None:
            return (letztes_gutes[0], letztes_gutes[1], yaw1), z_gut, getroffen
        z_neu, _boden = boden_bei(raum, px, py, z_nahe=z_gut)
        if abs(z_neu - z_gut) > MAX_STUFE_M:
            return (letztes_gutes[0], letztes_gutes[1], yaw1), z_gut, "Kante"
        letztes_gutes, z_gut = (px, py), z_neu
    return (x1, y1, yaw1), z_gut, None


def _schneiden(a1, a2, b1, b2):
    """Kreuzen sich die Strecken a und b?"""
    def kreuz(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    d1, d2 = kreuz(b1, b2, a1), kreuz(b1, b2, a2)
    d3, d4 = kreuz(a1, a2, b1), kreuz(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def sicht_frei(raum, a, b):
    """Freie Sichtlinie von a nach b? Waende und Bloecke verdecken."""
    for x1, y1, x2, y2 in raum.waende:
        if _schneiden(a, b, (x1, y1), (x2, y2)):
            return False
    for block in raum.bloecke:
        ecken = block.ecken()
        for erste, zweite in zip(ecken, ecken[1:] + ecken[:1]):
            if _schneiden(a, b, erste, zweite):
                return False
    return True
