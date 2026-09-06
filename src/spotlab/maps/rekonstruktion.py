"""Ein Raum aus einer GraphNav-Karte: Waende aus der Punktwolke, Tags aus den
Ankern, der Start am ersten Wegpunkt.

Darf bosdyn und numpy -- wie `maps/` ueberhaupt. Die GUI ruft
`rekonstruiere()` in einem Arbeiter-Thread und bekommt `Ergebnis(raum,
pauspapier, bericht)`; sie sieht nie ein Protobuf.

Die Transformationskette der Punktwolken stammt aus dem Kartenbetrachter des
Autors (`Spot Projects/src/map_viewer/transformer.py`):
    seed_tform_waypoint · waypoint_tform_ko · odom_tform_cloud
Gemessen an `map_catacombs_01` (06.09.2026): Wolke als XYZ float32 (encoding 1),
Quellrahmen `sensor_origin_generated`; der Boden (5. Perzentil der z-Werte
EINES Schnappschusses) liegt 0.54 m unter dem Wegpunkt; die z-Achse des
Fiducial-Rahmens zeigt aus der Tag-Flaeche zu den Beobachtern -- sie ist die
Blickrichtung des Tags. Der Boden wird je Schnappschuss bestimmt, nicht ueber die
ganze Karte: die Katakomben haben Niveauunterschiede, und ein globaler Boden
schnitt das Hoehenband oben falsch ab und hob die Tags auf 2.9 m.

RANSAC mit festem Seed: dieselbe Karte gibt denselben Raum.
"""

import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from bosdyn.api.graph_nav import map_pb2
from bosdyn.client.frame_helpers import ODOM_FRAME_NAME, get_a_tform_b
from bosdyn.client.math_helpers import SE3Pose

from spotlab.errors import SpotlabError
from spotlab.maps.geometry import HINWEIS_KETTE
from spotlab.welt.raum import RAND_M, Raum, RaumTag, Wand

ENCODING_XYZ_32F = 1
KOERPER_UEBER_BODEN_M = 0.54     # Wegpunkt ueber dem Boden, wenn keine Wolke den Boden zeigt
MAX_LINIEN = 300


@dataclass(frozen=True)
class Einstellungen:
    band: tuple = (0.3, 1.6)        # Meter ueber dem Boden
    zelle: float = 0.05             # Belegungsgitter
    mindestens_punkte: int = 3      # je Zelle
    inlier: float = 0.06            # RANSAC-Abstand
    min_laenge: float = 0.5         # Segmente darunter fallen weg
    luecke: float = 0.4             # Segment wird an groesseren Luecken geteilt -- Tueren
    ausrichten: bool = True         # haeufigste Wandrichtung -> x-Achse
    sichtpruefung: bool = True      # Zellen, durch die Strahlen hindurchgehen, sind frei
    begradigen: bool = True         # Winkel bis 7 Grad auf 0/90 rasten, Doppelwaende vereinen
    schlauch_breite: float = 2.0    # Notnagel ohne Wolken
    pauspapier_max: int = 200_000


@dataclass(frozen=True)
class Ergebnis:
    raum: Raum
    pauspapier: list        # [(x, y), ...]
    bericht: dict


# ------------------------------------------------------------------ Laden


def lade_karte(ordner):
    """(graph, {wegpunkt_id: WaypointSnapshot}, fehlende Schnappschuesse)."""
    ordner = Path(ordner)
    graph_pfad = ordner / "graph"
    if not graph_pfad.is_file():
        raise SpotlabError(
            f"Das ist kein Kartenordner: es fehlt die Datei `graph` in {ordner}. "
            f"Einen Ordner mit `graph` und `waypoint_snapshots/` waehlen."
        )
    graph = map_pb2.Graph()
    try:
        graph.ParseFromString(graph_pfad.read_bytes())
    except Exception as fehler:
        raise SpotlabError(f"{graph_pfad} liess sich nicht lesen: {fehler}") from fehler
    schnappschuesse, fehlend = {}, 0
    for wp in graph.waypoints:
        pfad = ordner / "waypoint_snapshots" / wp.snapshot_id
        if not wp.snapshot_id or not pfad.is_file():
            fehlend += 1
            continue
        snap = map_pb2.WaypointSnapshot()
        try:
            snap.ParseFromString(pfad.read_bytes())
        except Exception:
            fehlend += 1
            continue
        schnappschuesse[wp.id] = snap
    return graph, schnappschuesse, fehlend


def posen(graph):
    """({wegpunkt_id: SE3Pose im Seed-Rahmen}, "anker" | "kette") -- wie maps/geometry."""
    anker = {a.id: SE3Pose.from_proto(a.seed_tform_waypoint) for a in graph.anchoring.anchors}
    if anker and all(wp.id in anker for wp in graph.waypoints):
        return anker, "anker"
    nachbarn = {}
    for kante in graph.edges:
        pose = SE3Pose.from_proto(kante.from_tform_to)
        nachbarn.setdefault(kante.id.from_waypoint, []).append((kante.id.to_waypoint, pose))
        nachbarn.setdefault(kante.id.to_waypoint, []).append((kante.id.from_waypoint, pose.inverse()))
    ergebnis = {}
    if graph.waypoints:
        wurzel = graph.waypoints[0].id
        ergebnis[wurzel] = SE3Pose.from_identity()
        warteschlange = [wurzel]
        while warteschlange:
            aktuell = warteschlange.pop(0)
            for ziel, versatz in nachbarn.get(aktuell, ()):
                if ziel in ergebnis:
                    continue
                ergebnis[ziel] = ergebnis[aktuell].mult(versatz)
                warteschlange.append(ziel)
    return ergebnis, "kette"


def wolke_im_seed(waypoint, snapshot, seed_tform_wp):
    """Die Punktwolke des Schnappschusses im Seed-Rahmen, (N, 3)."""
    pc = snapshot.point_cloud
    if pc.num_points == 0 or not pc.data or pc.encoding != ENCODING_XYZ_32F:
        return np.zeros((0, 3))
    punkte = np.frombuffer(pc.data, dtype=np.float32).reshape(-1, 3)
    odom_tform_cloud = get_a_tform_b(pc.source.transforms_snapshot, ODOM_FRAME_NAME,
                                     pc.source.frame_name_sensor)
    if odom_tform_cloud is None:
        return np.zeros((0, 3))
    wp_tform_cloud = SE3Pose.from_proto(waypoint.waypoint_tform_ko) * odom_tform_cloud
    matrix = (seed_tform_wp * wp_tform_cloud).to_matrix()
    homogen = np.hstack([punkte, np.ones((len(punkte), 1), dtype=np.float32)])
    return (homogen @ matrix.T)[:, :3]


# --------------------------------------------------------- Boden und Gitter


def boden_hoehe(z):
    """Der Boden: das 5. Perzentil -- robust gegen einzelne Ausreisser unter dem Boden."""
    return float(np.percentile(z, 5)) if len(z) else 0.0


def belegte_zellen(xy, zelle, mindestens):
    """Mitten aller Zellen mit mindestens `mindestens` Punkten, (M, 2)."""
    if len(xy) == 0:
        return np.zeros((0, 2))
    ij = np.floor(np.asarray(xy) / zelle).astype(np.int64)
    eindeutig, anzahl = np.unique(ij, axis=0, return_counts=True)
    return (eindeutig[anzahl >= mindestens] + 0.5) * zelle


# ------------------------------------------------------------ Sichtpruefung
#
# Eine Wand wird nie durchquert. Tiefen-Artefakte ("flying pixels") liegen auf
# dem Strahl zwischen Kamera und Wand -- die Strahlen zu den Punkten dahinter
# gehen durch sie hindurch. Je Schnappschuss: die getroffenen Zellen und die
# Zellen, die ein Strahl bis 2 Zellen vor seinem Treffer durchlaeuft. Eine
# Zelle bleibt, wenn sie von MEHR Schnappschuessen getroffen als durchquert
# wurde -- ein Gleichstand (einmal getroffen, einmal durchquert) ist ein
# Artefakt, das ein einziger fremder Strahl entlarvt hat. Gemessen an den
# Katakomben (06.09.2026): 41 663 -> 12 922 Zellen, 261 -> ~100 Wandstuecke,
# die Gaenge sauber umrandet.

_VERSATZ = 1 << 20
_BREITE = 1 << 21


def _schluessel(ij):
    """Zellenindizes (M, 2) -> eindeutige int64-Schluessel."""
    return (ij[:, 0] + _VERSATZ) * _BREITE + (ij[:, 1] + _VERSATZ)


def _strahlen_frei(ursprung, mitten, zelle):
    """Schluessel der Zellen, die Strahlen vom Ursprung zu den Zellmitten durchlaufen."""
    d = mitten - ursprung
    laenge = np.hypot(d[:, 0], d[:, 1])
    ok = laenge > 4 * zelle
    d, laenge = d[ok], laenge[ok]
    if not len(d):
        return np.zeros(0, dtype=np.int64)
    schritte = np.arange(0.0, float(laenge.max()), zelle)
    proben = ursprung + (schritte[None, :, None] / laenge[:, None, None]) * d[:, None, :]
    gueltig = schritte[None, :] < (laenge - 2 * zelle)[:, None]
    proben = proben[gueltig]
    return np.unique(_schluessel(np.floor(proben / zelle).astype(np.int64)))


def _je_schluessel(schluessel, schnappschuss):
    """{schluessel: Zahl der Schnappschuesse}, aus je einem Paar je (Zelle, Schnappschuss)."""
    if not len(schluessel):
        return {}
    paare = np.unique(np.column_stack([schluessel, schnappschuss]), axis=0)
    werte, zahl = np.unique(paare[:, 0], return_counts=True)
    return dict(zip(werte.tolist(), zahl.tolist()))


# ------------------------------------------------------------------ Linien


def linien_ransac(punkte, inlier, min_inlier=10, versuche=200, rng=None):
    """[(mittel, richtung, inlier_punkte)] -- Linien in den Zellmitten, beste zuerst."""
    rng = rng if rng is not None else np.random.default_rng(0)
    rest = np.asarray(punkte, dtype=float)
    linien = []
    while len(rest) >= 20 and len(linien) < MAX_LINIEN:
        beste, beste_anzahl = None, 0
        for _ in range(versuche):
            i, j = rng.choice(len(rest), 2, replace=False)
            d = rest[j] - rest[i]
            laenge = math.hypot(d[0], d[1])
            if laenge < 0.2:
                continue
            normale = np.array([-d[1], d[0]]) / laenge
            drin = np.abs((rest - rest[i]) @ normale) <= inlier
            anzahl = int(drin.sum())
            if anzahl > beste_anzahl:
                beste, beste_anzahl = drin, anzahl
        if beste is None or beste_anzahl < min_inlier:
            break
        # Verfeinern: Hauptachse der Inlier, dann die Inlier gegen die neue Linie
        pts = rest[beste]
        mittel = pts.mean(axis=0)
        kovarianz = np.cov((pts - mittel).T)
        _werte, vektoren = np.linalg.eigh(kovarianz)
        richtung = vektoren[:, 1]
        normale = np.array([-richtung[1], richtung[0]])
        abstand = np.abs((rest - mittel) @ normale)
        drin = abstand <= inlier
        if int(drin.sum()) < min_inlier:
            drin = beste
            abstand = np.where(beste, 0.0, np.inf)
        linien.append((mittel, richtung, rest[drin]))
        # Eine Wand ist in der Wolke 5-15 cm dick: mehrere Zellreihen nebeneinander.
        # Ohne diese Sperre wurde jede Reihe eine eigene "Wand" (Katakomben:
        # 733 Stuecke statt Waende, 06.09.2026). Die Nachbarreihen fallen weg,
        # gezaehlt wird die Wand nur einmal.
        rest = rest[abstand > 3.0 * inlier]
    return linien


def teile_an_luecken(mittel, richtung, punkte, luecke, min_laenge, zelle=0.05, dichte=0.5):
    """Eine Linie in Wandstuecke: getrennt an Luecken (Tueren); kurze und DUENNE
    Stuecke fallen weg.

    Duenn heisst: weniger als `dichte` der Zellen entlang des Stuecks sind belegt.
    Eine echte Wand ist fast lueckenlos; eine Kette zufaellig kollinearer
    Kruemel (Stuehle, Kabel, Rauschen) quer durch die Karte ist es nicht --
    ohne diese Schwelle bestand die Katakomben-Karte zu drei Vierteln aus
    solchen Ketten (06.09.2026).
    """
    t = np.sort((np.asarray(punkte) - mittel) @ richtung)
    if len(t) == 0:
        return []
    stuecke = []
    anfang = vorher = t[0]
    anzahl = 1
    for wert in t[1:]:
        if wert - vorher > luecke:
            stuecke.append((anfang, vorher, anzahl))
            anfang, anzahl = wert, 0
        vorher = wert
        anzahl += 1
    stuecke.append((anfang, vorher, anzahl))
    waende = []
    for a, b, n in stuecke:
        if b - a < min_laenge:
            continue
        if n < dichte * ((b - a) / zelle + 1):
            continue
        p1 = mittel + a * richtung
        p2 = mittel + b * richtung
        waende.append(Wand(round(float(p1[0]), 2), round(float(p1[1]), 2),
                           round(float(p2[0]), 2), round(float(p2[1]), 2)))
    return waende


def _winkelabstand(a, b):
    return abs(((a - b) + 90.0) % 180.0 - 90.0)


def verschmelze(waende, winkel_grad=5.0, abstand=0.2):
    """Kollineare Nachbarn (fast gleicher Winkel, Enden nahe, seitlich auf einer Linie) vereinen."""
    waende = list(waende)
    geaendert = True
    while geaendert:
        geaendert = False
        for i in range(len(waende)):
            for j in range(i + 1, len(waende)):
                a, b = waende[i], waende[j]
                if _winkelabstand(a.winkel, b.winkel) > winkel_grad:
                    continue
                enden_a = [(a.x1, a.y1), (a.x2, a.y2)]
                enden_b = [(b.x1, b.y1), (b.x2, b.y2)]
                naechste = min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in enden_a for q in enden_b)
                if naechste > abstand:
                    continue
                # seitlicher Versatz der Mitte von b zur Linie von a
                dx, dy = a.x2 - a.x1, a.y2 - a.y1
                laenge = math.hypot(dx, dy) or 1.0
                mx, my = b.mitte
                seitlich = abs((mx - a.x1) * dy - (my - a.y1) * dx) / laenge
                if seitlich > 0.1:
                    continue
                punkte = enden_a + enden_b
                p, q = max(((p, q) for p in punkte for q in punkte),
                           key=lambda pq: math.hypot(pq[0][0] - pq[1][0], pq[0][1] - pq[1][1]))
                waende[i] = Wand(p[0], p[1], q[0], q[1])
                del waende[j]
                geaendert = True
                break
            if geaendert:
                break
    return waende


def begradige(waende, toleranz_grad=7.0, versatz=0.25):
    """Im rechtwinkligen Rahmen: Winkel bis `toleranz_grad` auf 0/90 rasten,
    parallele Doppelwaende (Versatz <= `versatz`, ueberlappend) vereinen --
    Anker-Drift legt dieselbe Wand von verschiedenen Wegpunkten aus ein paar
    Zentimeter versetzt ab."""
    gerade, schraeg = [], []
    for w in waende:
        wink = w.winkel % 180.0
        mx, my = w.mitte
        halb = w.laenge / 2
        if min(wink, 180.0 - wink) <= toleranz_grad:
            gerade.append(("x", my, mx - halb, mx + halb))
        elif abs(wink - 90.0) <= toleranz_grad:
            gerade.append(("y", mx, my - halb, my + halb))
        else:
            schraeg.append(w)
    geaendert = True
    while geaendert:
        geaendert = False
        for i in range(len(gerade)):
            for j in range(i + 1, len(gerade)):
                a, b = gerade[i], gerade[j]
                if a[0] != b[0] or abs(a[1] - b[1]) > versatz:
                    continue
                if min(a[3], b[3]) - max(a[2], b[2]) < -0.05:
                    continue
                la, lb = a[3] - a[2], b[3] - b[2]
                lage = (a[1] * la + b[1] * lb) / max(la + lb, 1e-9)
                gerade[i] = (a[0], lage, min(a[2], b[2]), max(a[3], b[3]))
                del gerade[j]
                geaendert = True
                break
            if geaendert:
                break
    ergebnis = list(schraeg)
    for achse, lage, von, bis in gerade:
        lage, von, bis = round(lage, 2), round(von, 2), round(bis, 2)
        if achse == "x":
            ergebnis.append(Wand(von, lage, bis, lage))
        else:
            ergebnis.append(Wand(lage, von, lage, bis))
    return ergebnis


# --------------------------------------------------------------- Ausrichten


def _drehe(x, y, grad):
    c, s = math.cos(math.radians(grad)), math.sin(math.radians(grad))
    return x * c - y * s, x * s + y * c


def ausrichten(waende, tags, start, pauspapier):
    """Die haeufigste Wandrichtung (laengengewichtet, modulo 90 Grad) auf die
    x-Achse drehen und alles so verschieben, dass die Huelle bei (0, 0) beginnt.
    Gibt (waende, tags, start, pauspapier, drehung_grad) zurueck."""
    klassen = np.zeros(90)
    for w in waende:
        klassen[int(round(w.winkel)) % 90] += w.laenge
    haupt = int(np.argmax(klassen)) if waende else 0
    dreh = float(-haupt if haupt <= 45 else 90 - haupt)
    waende = [Wand(*_drehe(w.x1, w.y1, dreh), *_drehe(w.x2, w.y2, dreh)) for w in waende]
    tags = [RaumTag(t.id, *_drehe(t.x, t.y, dreh), (t.grad + dreh) % 360.0, t.hoehe) for t in tags]
    sx, sy = _drehe(start[0], start[1], dreh)
    start = (sx, sy, (start[2] + dreh) % 360.0)
    punkte = [(w.x1, w.y1) for w in waende] + [(w.x2, w.y2) for w in waende]
    punkte += [(t.x, t.y) for t in tags] + [(sx, sy)]
    versatz_x = RAND_M - min(p[0] for p in punkte)
    versatz_y = RAND_M - min(p[1] for p in punkte)
    waende = [Wand(round(w.x1 + versatz_x, 2), round(w.y1 + versatz_y, 2),
                   round(w.x2 + versatz_x, 2), round(w.y2 + versatz_y, 2)) for w in waende]
    tags = [RaumTag(t.id, round(t.x + versatz_x, 3), round(t.y + versatz_y, 3),
                    round(t.grad, 1), t.hoehe) for t in tags]
    start = (round(start[0] + versatz_x, 3), round(start[1] + versatz_y, 3), round(start[2], 1))
    if len(pauspapier):
        p = np.asarray(pauspapier, dtype=float)
        c, s = math.cos(math.radians(dreh)), math.sin(math.radians(dreh))
        p = np.column_stack([p[:, 0] * c - p[:, 1] * s + versatz_x,
                             p[:, 0] * s + p[:, 1] * c + versatz_y])
        pauspapier = p
    return waende, tags, start, pauspapier, dreh


# --------------------------------------------------------- Tags und Start


def _boden_finder(posen_, boeden):
    """(x, y) -> Bodenhoehe des naechsten Wegpunkts, der einen Boden kennt."""
    bekannt = [(p.x, p.y, boeden[wp_id]) for wp_id, p in posen_.items() if wp_id in boeden]

    def boden_bei(x, y):
        if not bekannt:
            return 0.0
        return min(bekannt, key=lambda b: (b[0] - x) ** 2 + (b[1] - y) ** 2)[2]

    return boden_bei


def _tag_aus_pose(nummer, pose, boden_bei):
    achse_z = pose.rot.to_matrix()[:, 2]
    grad = math.degrees(math.atan2(achse_z[1], achse_z[0])) % 360.0
    return RaumTag(nummer, round(pose.x, 3), round(pose.y, 3), round(grad, 1),
                   round(max(pose.z - boden_bei(pose.x, pose.y), 0.05), 3))


def tags_aus_anker(graph, boden_bei):
    tags = []
    for objekt in graph.anchoring.objects:
        try:
            nummer = int(objekt.id)
        except ValueError:
            continue
        tags.append(_tag_aus_pose(nummer, SE3Pose.from_proto(objekt.seed_tform_object), boden_bei))
    return tags


def tags_aus_schnappschuessen(graph, schnappschuesse, posen_, boden_bei, schon_da):
    """Tags, die nur in Schnappschuessen vorkommen: ueber die Wegpunktpose."""
    tags = []
    gesehen = set(schon_da)
    for wp in graph.waypoints:
        snap = schnappschuesse.get(wp.id)
        seed_tform_wp = posen_.get(wp.id)
        if snap is None or seed_tform_wp is None:
            continue
        for objekt in snap.objects:
            if not objekt.HasField("apriltag_properties"):
                continue
            nummer = int(objekt.apriltag_properties.tag_id)
            if nummer in gesehen:
                continue
            odom_tform_tag = get_a_tform_b(objekt.transforms_snapshot, ODOM_FRAME_NAME,
                                           objekt.apriltag_properties.frame_name_fiducial)
            if odom_tform_tag is None:
                continue
            pose = seed_tform_wp * SE3Pose.from_proto(wp.waypoint_tform_ko) * odom_tform_tag
            tags.append(_tag_aus_pose(nummer, pose, boden_bei))
            gesehen.add(nummer)
    return tags


def start_aus(graph, posen_):
    pose = posen_[graph.waypoints[0].id]
    return (round(pose.x, 3), round(pose.y, 3), round(math.degrees(pose.rot.to_yaw()) % 360.0, 1))


def schlauch(graph, posen_, breite):
    """Notnagel ohne Wolken: je Kante zwei Waende im Abstand +-breite/2."""
    waende = []
    for kante in graph.edges:
        a = posen_.get(kante.id.from_waypoint)
        b = posen_.get(kante.id.to_waypoint)
        if a is None or b is None:
            continue
        dx, dy = b.x - a.x, b.y - a.y
        laenge = math.hypot(dx, dy)
        if laenge < 1e-6:
            continue
        nx, ny = -dy / laenge * breite / 2, dx / laenge * breite / 2
        waende.append(Wand(round(a.x + nx, 2), round(a.y + ny, 2), round(b.x + nx, 2), round(b.y + ny, 2)))
        waende.append(Wand(round(a.x - nx, 2), round(a.y - ny, 2), round(b.x - nx, 2), round(b.y - ny, 2)))
    return waende


# ---------------------------------------------------------------- Ganzes


def _duenne(punkte, hoechstens):
    if len(punkte) <= hoechstens:
        return punkte
    schritt = math.ceil(len(punkte) / hoechstens)
    return punkte[::schritt]


def rekonstruiere(ordner, einstellungen=None, fortschritt=None):
    """Ein `Ergebnis` aus dem Kartenordner. `fortschritt(text)` wird je Schnappschuss gerufen."""
    e = einstellungen or Einstellungen()
    t0 = time.monotonic()
    ordner = Path(ordner)
    graph, schnappschuesse, fehlend = lade_karte(ordner)
    if not graph.waypoints:
        raise SpotlabError("Diese Karte enthält keine Wegpunkte.")
    posen_, quelle_posen = posen(graph)
    hinweise = [] if quelle_posen == "anker" else [HINWEIS_KETTE]

    baender, gesamt = [], 0
    boeden = {}                      # wegpunkt_id -> Bodenhoehe dort
    treffer_s, treffer_i, frei_s, frei_i = [], [], [], []
    for i, wp in enumerate(graph.waypoints):
        if fortschritt is not None:
            fortschritt(f"Schnappschuss {i + 1}/{len(graph.waypoints)}")
        snap, seed_tform_wp = schnappschuesse.get(wp.id), posen_.get(wp.id)
        if snap is None or seed_tform_wp is None:
            continue
        wolke = wolke_im_seed(wp, snap, seed_tform_wp)
        if not len(wolke):
            continue
        gesamt += len(wolke)
        # Der Boden je Schnappschuss: Karten mit Niveauunterschieden haben keinen
        # einen Boden. Zeigt die Wolke keinen (zu wenige Punkte), gilt der
        # Wegpunkt minus Koerperhoehe.
        boden_hier = boden_hoehe(wolke[:, 2]) if len(wolke) >= 200 else seed_tform_wp.z - KOERPER_UEBER_BODEN_M
        boeden[wp.id] = boden_hier
        z = wolke[:, 2]
        band_hier = wolke[(z >= boden_hier + e.band[0]) & (z <= boden_hier + e.band[1])]
        baender.append(band_hier)
        if e.sichtpruefung and len(band_hier):
            zellen_hier = np.unique(np.floor(band_hier[:, :2] / e.zelle).astype(np.int64), axis=0)
            schluessel = _schluessel(zellen_hier)
            treffer_s.append(schluessel)
            treffer_i.append(np.full(len(schluessel), i))
            frei = _strahlen_frei(np.array([seed_tform_wp.x, seed_tform_wp.y]),
                                  (zellen_hier + 0.5) * e.zelle, e.zelle)
            frei_s.append(frei)
            frei_i.append(np.full(len(frei), i))

    bericht = {
        "wegpunkte": len(graph.waypoints), "schnappschuesse": len(schnappschuesse),
        "fehlend": fehlend, "posen": quelle_posen, "punkte": 0, "im_band": 0,
        "zellen": 0, "linien": 0, "waende": 0, "verworfen": 0, "tags": 0,
        "ausricht_grad": 0.0, "quelle": "wolke", "hinweise": hinweise,
    }
    if baender:
        band = np.vstack(baender)
        zellen = belegte_zellen(band[:, :2], e.zelle, e.mindestens_punkte)
        if e.sichtpruefung and treffer_s:
            getroffen = _je_schluessel(np.concatenate(treffer_s), np.concatenate(treffer_i))
            durchquert = _je_schluessel(np.concatenate(frei_s), np.concatenate(frei_i))
            schluessel = _schluessel(np.floor(zellen / e.zelle).astype(np.int64))
            solide = np.array([durchquert.get(k, 0) < getroffen.get(k, 0)
                               for k in schluessel.tolist()], dtype=bool)
            bericht["durchquert"] = int((~solide).sum())
            zellen = zellen[solide]
        if fortschritt is not None:
            fortschritt(f"Linien in {len(zellen)} Zellen suchen")
        linien = linien_ransac(zellen, e.inlier, rng=np.random.default_rng(0))
        waende, verworfen = [], 0
        for mittel, richtung, pts in linien:
            stuecke = teile_an_luecken(mittel, richtung, pts, e.luecke, e.min_laenge, e.zelle)
            verworfen += 0 if stuecke else 1
            waende += stuecke
        vorher = len(waende)
        waende = verschmelze(waende)
        pauspapier = _duenne(band[:, :2], e.pauspapier_max)
        bericht.update(punkte=gesamt, im_band=int(len(band)), zellen=int(len(zellen)),
                       linien=len(linien), verworfen=verworfen + (vorher - len(waende)))
    else:
        boeden = {wp_id: p.z - KOERPER_UEBER_BODEN_M for wp_id, p in posen_.items()}
        waende = schlauch(graph, posen_, e.schlauch_breite)
        pauspapier = np.zeros((0, 2))
        bericht["quelle"] = "schlauch"
        hinweise.append(
            f"Keine Punktwolken in der Karte — der Pfad wurde als Schlauch von "
            f"{e.schlauch_breite:.1f} m Breite angelegt. Waende im Raumeditor nachziehen."
        )
    boden_bei = _boden_finder(posen_, boeden)
    tags = tags_aus_anker(graph, boden_bei)
    tags += tags_aus_schnappschuessen(graph, schnappschuesse, posen_, boden_bei, [t.id for t in tags])
    start = start_aus(graph, posen_)
    dreh = 0.0
    if e.ausrichten and waende:
        waende, tags, start, pauspapier, dreh = ausrichten(waende, tags, start, pauspapier)
        if e.begradigen:
            waende = begradige(waende)
    raum = Raum(
        name=ordner.name,
        beschreibung=f"Rekonstruiert aus der Karte „{ordner.name}“ ({bericht['quelle']}).",
        start=start, waende=tuple(waende), bloecke=(), tags=tuple(tags),
    )
    bericht.update(waende=len(waende), tags=len(tags), ausricht_grad=dreh,
                   dauer_s=round(time.monotonic() - t0, 2))
    return Ergebnis(raum, [(float(x), float(y)) for x, y in np.asarray(pauspapier)], bericht)
