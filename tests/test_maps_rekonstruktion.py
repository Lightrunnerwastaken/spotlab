"""Rekonstruktion eines Raums aus einer GraphNav-Karte.

Die Fixture ist eine SYNTHETISCHE Karte: ein Gang 6 x 2 m mit einer Tuer in der
oberen Wand, Boden- und Deckenpunkte, die das Hoehenband verwerfen muss, ein
verankertes Tag. Dazu ein Abnahmetest gegen die echte Katakomben-Karte, wenn
sie auf diesem Rechner liegt.
"""
import math
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("bosdyn.api")

from bosdyn.api.graph_nav import map_pb2  # noqa: E402
from bosdyn.client.math_helpers import Quat, SE3Pose  # noqa: E402

from spotlab.maps import rekonstruktion as rk  # noqa: E402

KATAKOMBEN = Path(r"D:\Users\janis\Documents\Spot Projects\maps\map_catacombs_01")
TUER = (2.5, 3.4)          # x-Bereich der Tuer in der oberen Wand (y = 2)


def _wandpunkte(x0, x1, y, z0=0.3, z1=1.5, schritt=0.03, ausser=None):
    xs = np.arange(x0, x1 + 1e-9, schritt)
    if ausser is not None:
        xs = xs[(xs < ausser[0]) | (xs > ausser[1])]
    zs = np.arange(z0, z1 + 1e-9, schritt)
    X, Z = np.meshgrid(xs, zs)
    return np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()])


def _flaeche(x0, x1, y0, y1, z, schritt=0.1):
    xs = np.arange(x0, x1 + 1e-9, schritt)
    ys = np.arange(y0, y1 + 1e-9, schritt)
    X, Y = np.meshgrid(xs, ys)
    return np.column_stack([X.ravel(), Y.ravel(), np.full(X.size, z)])


def _se3(x, y, z=0.0, yaw=0.0):
    return SE3Pose(x, y, z, Quat.from_yaw(yaw))


def synthetische_karte(ordner, mit_wolken=True, drehung_grad=0.0, rauschen=True):
    """Gang 6 x 2 m (Waende y = 0 und y = 2), Tuer in der oberen Wand, Tag 7 rechts.

    `rauschen`: Tiefen-Artefakte entlang der Blickrichtung ("flying pixels") --
    Punkte auf dem Strahl vom Wegpunkt zur Wand, im Ganginneren. Echte Karten
    sind voll davon (Katakomben, 06.09.2026); die Sichtpruefung muss sie loeschen.
    """
    ordner = Path(ordner)
    (ordner / "waypoint_snapshots").mkdir(parents=True)
    (ordner / "edge_snapshots").mkdir()
    dreh = SE3Pose(0, 0, 0, Quat.from_yaw(math.radians(drehung_grad)))   # Seed-Rahmen schief
    rng = np.random.default_rng(7)

    welt = np.vstack([
        _wandpunkte(0.0, 6.0, 0.0),
        _wandpunkte(0.0, 6.0, 2.0, ausser=TUER),
        _flaeche(0.0, 6.0, 0.0, 2.0, 0.0),        # Boden
        _flaeche(0.0, 6.0, 0.0, 2.0, 2.4),        # Decke
    ])
    graph = map_pb2.Graph()
    vorher_id, vorher_pose = None, None
    for i in range(6):
        wp = graph.waypoints.add()
        wp.id = f"wp{i}"
        wp.snapshot_id = f"s{i}"
        wp.annotations.name = f"waypoint_{i}"
        pose = dreh * _se3(0.5 + i * 1.0, 1.0, 0.54)       # Koerper 0.54 m ueber dem Boden
        wp.waypoint_tform_ko.CopyFrom(SE3Pose.from_identity().to_proto())
        anker = graph.anchoring.anchors.add()
        anker.id = wp.id
        anker.seed_tform_waypoint.CopyFrom(pose.to_proto())
        if vorher_id is not None:
            kante = graph.edges.add()
            kante.id.from_waypoint = vorher_id
            kante.id.to_waypoint = wp.id
            kante.from_tform_to.CopyFrom((vorher_pose.inverse() * pose).to_proto())
        vorher_id, vorher_pose = wp.id, pose
        # Die Wolke im Rahmen des Wegpunkts: Weltpunkte um die Pose zurueckgerechnet.
        snap = map_pb2.WaypointSnapshot()
        snap.id = wp.snapshot_id
        if mit_wolken:
            nah = welt[np.abs(welt[:, 0] - (0.5 + i)) <= 1.2]
            if rauschen:
                # 400 Punkte auf Strahlen vom Wegpunkt (0.5 + i, 1.0) zu Wandpunkten,
                # bei 30-90 % der Strecke -- mitten im Gang, in Wandhoehe.
                wand = nah[(nah[:, 2] > 0.2) & (nah[:, 2] < 1.6)]
                ziel = wand[rng.integers(0, len(wand), 400)]
                anteil = rng.uniform(0.3, 0.9, (400, 1))
                start = np.array([0.5 + i, 1.0, 0.0])
                nah = np.vstack([nah, start + anteil * (ziel - start) * np.array([1, 1, 0]) + np.array([0, 0, 1]) * ziel[:, 2:3]])
            # Der Seed-Rahmen liegt schief: die Welt selbst ist gedreht, nicht nur die Pose.
            nah = (np.hstack([nah, np.ones((len(nah), 1))]) @ dreh.to_matrix().T)[:, :3]
            m = np.linalg.inv(pose.to_matrix())
            lokal = (np.hstack([nah, np.ones((len(nah), 1))]) @ m.T)[:, :3].astype(np.float32)
            snap.point_cloud.num_points = len(lokal)
            snap.point_cloud.encoding = 1
            snap.point_cloud.data = lokal.tobytes()
            snap.point_cloud.source.frame_name_sensor = "sensor"
            baum = snap.point_cloud.source.transforms_snapshot
            baum.child_to_parent_edge_map["odom"].parent_frame_name = ""
            edge = baum.child_to_parent_edge_map["sensor"]
            edge.parent_frame_name = "odom"
            edge.parent_tform_child.CopyFrom(SE3Pose.from_identity().to_proto())
        (ordner / "waypoint_snapshots" / snap.id).write_bytes(snap.SerializeToString())
    # Tag 7 an der oberen Wand rechts, Blick nach -y (in den Gang), 0.9 m hoch
    obj = graph.anchoring.objects.add()
    obj.id = "7"
    # Die z-Achse des Fiducial-Rahmens ist die Blickrichtung (gemessen an den
    # Katakomben): Drehung um x um +90 Grad bildet (0, 0, 1) auf (0, -1, 0) ab.
    rot = Quat.from_roll(math.pi / 2)
    obj.seed_tform_object.CopyFrom((dreh * SE3Pose(5.0, 2.0, 0.9, rot)).to_proto())
    (ordner / "graph").write_bytes(graph.SerializeToString())
    return ordner


@pytest.fixture
def karte(tmp_path):
    return synthetische_karte(tmp_path / "gang")


def test_die_synthetische_karte_wird_zu_einem_gang_mit_tuer(karte):
    ergebnis = rk.rekonstruiere(karte)
    raum, bericht = ergebnis.raum, ergebnis.bericht
    assert bericht["wegpunkte"] == 6 and bericht["posen"] == "anker" and bericht["quelle"] == "wolke"
    assert len(raum.waende) >= 3
    laengen = sorted((w.laenge for w in raum.waende), reverse=True)
    assert laengen[0] >= 5.5                                  # die untere Wand in einem Stueck
    # Alle Waende liegen auf y = 0 oder y = 2 (bis 10 cm), nach dem Ausrichten verschoben:
    ys = sorted({round(w.y1, 1) for w in raum.waende})
    assert len(ys) == 2 and abs((ys[1] - ys[0]) - 2.0) < 0.15
    obere = [w for w in raum.waende if abs(w.y1 - ys[1]) < 0.15]
    assert len(obere) == 2, [list(w) for w in obere]
    links, rechts = sorted(obere, key=lambda w: min(w.x1, w.x2))
    luecke = min(rechts.x1, rechts.x2) - max(links.x1, links.x2)
    assert abs(luecke - (TUER[1] - TUER[0])) < 0.15
    assert len(raum.tags) == 1 and raum.tags[0].id == 7
    tag = raum.tags[0]
    assert abs(tag.y - ys[1]) < 0.1 and abs(tag.hoehe - 0.9) < 0.1
    assert abs(((tag.grad - 270.0) + 180) % 360 - 180) < 10.0
    assert raum.groesse is None
    x, y, grad = raum.start
    assert abs(y - (ys[0] + 1.0)) < 0.1 and abs(grad) < 10.0
    assert 1000 < len(ergebnis.pauspapier) <= 200_000


def test_das_band_verwirft_boden_und_decke(karte):
    graph, schnappschuesse, _fehlend = rk.lade_karte(karte)
    posen, _quelle = rk.posen(graph)
    wolke = np.vstack([rk.wolke_im_seed(wp, schnappschuesse[wp.id], posen[wp.id]) for wp in graph.waypoints])
    boden = rk.boden_hoehe(wolke[:, 2])
    assert abs(boden - 0.0) < 0.05
    band = wolke[(wolke[:, 2] >= boden + 0.3) & (wolke[:, 2] <= boden + 1.6)]
    assert band[:, 2].min() >= 0.29 and band[:, 2].max() <= 1.61


def test_ohne_wolken_gibt_es_den_schlauch(tmp_path):
    ordner = synthetische_karte(tmp_path / "leer", mit_wolken=False)
    ergebnis = rk.rekonstruiere(ordner, rk.Einstellungen(begradigen=False))
    assert ergebnis.bericht["quelle"] == "schlauch"
    assert len(ergebnis.raum.waende) == 2 * 5                  # zwei je Kante
    begradigt = rk.rekonstruiere(ordner)
    assert len(begradigt.raum.waende) == 2                     # begradigt: je Seite eine Wand
    assert ergebnis.pauspapier == []
    assert any("Schlauch" in h for h in ergebnis.bericht["hinweise"])


def test_ausrichten_dreht_eine_schiefe_karte_gerade(tmp_path):
    schief = synthetische_karte(tmp_path / "schief", drehung_grad=30.0)
    ergebnis = rk.rekonstruiere(schief)
    assert abs(abs(ergebnis.bericht["ausricht_grad"]) - 30.0) < 3.0
    laengste = max(ergebnis.raum.waende, key=lambda w: w.laenge)
    assert abs(laengste.y1 - laengste.y2) < 0.1                 # liegt jetzt waagrecht
    ohne = rk.rekonstruiere(schief, rk.Einstellungen(ausrichten=False))
    laengste = max(ohne.raum.waende, key=lambda w: w.laenge)
    assert abs(laengste.winkel % 180 - 30.0) < 3.0


def test_die_katakomben_karte_liefert_31_tags_und_waende():
    if not (KATAKOMBEN / "graph").is_file():
        pytest.skip("Katakomben-Karte fehlt auf diesem Rechner")
    t0 = time.monotonic()
    ergebnis = rk.rekonstruiere(KATAKOMBEN)
    dauer = time.monotonic() - t0
    assert len(ergebnis.raum.tags) == 31
    assert len(ergebnis.raum.waende) >= 20
    assert dauer < 60.0, dauer
    assert ergebnis.bericht["posen"] == "anker"


def test_die_sichtpruefung_loescht_strahlenrauschen_im_gang(karte):
    """Ohne Sichtpruefung werden die Artefakte zu Waenden mitten im Gang."""
    mit = rk.rekonstruiere(karte)
    ohne = rk.rekonstruiere(karte, rk.Einstellungen(sichtpruefung=False))

    def innen(raum):
        ys = sorted({round(w.y1, 1) for w in raum.waende})
        unten, oben = ys[0], ys[-1]
        return [w for w in raum.waende
                if min(w.y1, w.y2) > unten + 0.3 and max(w.y1, w.y2) < oben - 0.3]

    assert innen(ohne.raum), "die Fixture traegt kein Rauschen mehr"
    assert innen(mit.raum) == [], [list(w) for w in innen(mit.raum)]
    assert mit.bericht["zellen"] < ohne.bericht["zellen"]


def test_begradigen_rastet_winkel_und_vereint_parallele_doppel():
    from spotlab.welt.raum import Wand

    schief = Wand(0.0, 0.0, 4.0, 0.25)                       # ~3.6 Grad
    doppel_a = Wand(5.0, 1.0, 9.0, 1.0)
    doppel_b = Wand(6.0, 1.15, 10.0, 1.15)                   # parallel, 15 cm daneben, ueberlappt
    diagonal = Wand(0.0, 5.0, 2.0, 7.0)                      # 45 Grad bleibt
    neu = rk.begradige([schief, doppel_a, doppel_b, diagonal])
    assert len(neu) == 3
    gerade = next(w for w in neu if abs(w.laenge - 4.0) < 0.1)
    assert gerade.y1 == gerade.y2
    vereint = next(w for w in neu if w.laenge > 4.5)
    assert (min(vereint.x1, vereint.x2), max(vereint.x1, vereint.x2)) == (5.0, 10.0)
    assert 1.0 <= vereint.y1 <= 1.15 and vereint.y1 == vereint.y2
    assert any(abs(w.winkel - 45.0) < 1e-6 for w in neu)


# ------------------------------------------------------------- Hoehe (Stufe 13)

TREPPE_X = (6.0, 8.0)          # steigt von 0 auf 1.0 in sechs Stufen
RAMPE_X = (12.0, 17.0)         # steigt ab 1.0 mit 4 Grad
RAMPE_GRAD = 4.0


def _boden_hoehe_bei(x):
    """Der Boden der Karte mit Hoehe: Gang A (0), Treppe, Gang B (1.0), Rampe."""
    if x < TREPPE_X[0]:
        return 0.0
    if x < TREPPE_X[1]:
        stufe = int((x - TREPPE_X[0]) / ((TREPPE_X[1] - TREPPE_X[0]) / 6))
        return (min(stufe, 5) + 1) / 6.0                      # Trittflaechen
    if x < RAMPE_X[0]:
        return 1.0
    return 1.0 + (min(x, RAMPE_X[1]) - RAMPE_X[0]) * math.tan(math.radians(RAMPE_GRAD))


def _wegpunkt_hoehe(x):
    """Glatte Hoehe fuer den Koerper (auf der Treppe die Rampenlinie)."""
    if TREPPE_X[0] <= x < TREPPE_X[1]:
        return (x - TREPPE_X[0]) / (TREPPE_X[1] - TREPPE_X[0])
    return _boden_hoehe_bei(x)


def synthetische_karte_mit_hoehe(ordner, versatz_z=0.0):
    """Gang 17 x 2 m mit Treppe (x 6..8, +1 m, sechs Stufen), oberem Gang und
    4-Grad-Rampe (x 12..17). Tag 7 an der oberen Wand bei x = 10 (Ebene 1.0).
    `versatz_z` verschiebt die ganze Karte in der Hoehe -- die Rekonstruktion
    macht den tiefsten Boden zur 0."""
    ordner = Path(ordner)
    (ordner / "waypoint_snapshots").mkdir(parents=True)
    (ordner / "edge_snapshots").mkdir()
    xs = np.arange(0.0, 17.0 + 1e-9, 0.05)
    boden = np.array([_boden_hoehe_bei(x) for x in xs]) + versatz_z
    teile = []
    for x, h in zip(xs, boden):
        zs = np.arange(h + 0.3, h + 1.5 + 1e-9, 0.05)
        for y in (0.0, 2.0):
            teile.append(np.column_stack([np.full(zs.size, x), np.full(zs.size, y), zs]))
        ys = np.arange(0.0, 2.0 + 1e-9, 0.1)
        teile.append(np.column_stack([np.full(ys.size, x), ys, np.full(ys.size, h)]))          # Boden
        teile.append(np.column_stack([np.full(ys.size, x), ys, np.full(ys.size, h + 2.4)]))    # Decke
    welt = np.vstack(teile)

    wegpunkte_x = [0.5 + i for i in range(17)]
    treppen_kanten = {(5, 6), (6, 7), (7, 8)}
    graph = map_pb2.Graph()
    vorher_id, vorher_pose = None, None
    for i, wx in enumerate(wegpunkte_x):
        wp = graph.waypoints.add()
        wp.id = f"wp{i}"
        wp.snapshot_id = f"s{i}"
        wp.annotations.name = f"waypoint_{i}"
        wp.annotations.creation_time.seconds = 1000 + i
        pose = _se3(wx, 1.0, _wegpunkt_hoehe(wx) + versatz_z + rk.KOERPER_UEBER_BODEN_M)
        wp.waypoint_tform_ko.CopyFrom(SE3Pose.from_identity().to_proto())
        anker = graph.anchoring.anchors.add()
        anker.id = wp.id
        anker.seed_tform_waypoint.CopyFrom(pose.to_proto())
        if vorher_id is not None:
            kante = graph.edges.add()
            kante.id.from_waypoint = vorher_id
            kante.id.to_waypoint = wp.id
            kante.from_tform_to.CopyFrom((vorher_pose.inverse() * pose).to_proto())
            if (i - 1, i) in treppen_kanten:
                kante.annotations.stairs.state = map_pb2.ANNOTATION_STATE_SET
        vorher_id, vorher_pose = wp.id, pose
        snap = map_pb2.WaypointSnapshot()
        snap.id = wp.snapshot_id
        nah = welt[np.abs(welt[:, 0] - wx) <= 1.2]
        m = np.linalg.inv(pose.to_matrix())
        lokal = (np.hstack([nah, np.ones((len(nah), 1))]) @ m.T)[:, :3].astype(np.float32)
        snap.point_cloud.num_points = len(lokal)
        snap.point_cloud.encoding = 1
        snap.point_cloud.data = lokal.tobytes()
        snap.point_cloud.source.frame_name_sensor = "sensor"
        baum = snap.point_cloud.source.transforms_snapshot
        baum.child_to_parent_edge_map["odom"].parent_frame_name = ""
        edge = baum.child_to_parent_edge_map["sensor"]
        edge.parent_frame_name = "odom"
        edge.parent_tform_child.CopyFrom(SE3Pose.from_identity().to_proto())
        (ordner / "waypoint_snapshots" / snap.id).write_bytes(snap.SerializeToString())
    obj = graph.anchoring.objects.add()
    obj.id = "7"
    obj.seed_tform_object.CopyFrom(SE3Pose(10.0, 2.0, 1.0 + 0.9 + versatz_z, Quat.from_roll(math.pi / 2)).to_proto())
    (ordner / "graph").write_bytes(graph.SerializeToString())
    return ordner


@pytest.fixture
def karte_mit_hoehe(tmp_path):
    return synthetische_karte_mit_hoehe(tmp_path / "hoehe")


def test_das_profil_folgt_den_wegpunkten(karte_mit_hoehe):
    graph, _schnapp, _fehlend = rk.lade_karte(karte_mit_hoehe)
    posen, _quelle = rk.posen(graph)
    weg = rk.weg(graph)
    assert weg[:3] == ["wp0", "wp1", "wp2"] and len(weg) == 17
    profil = rk.profil(graph, posen)
    assert profil["wp0"] == pytest.approx(0.0, abs=0.02)
    assert profil["wp8"] == pytest.approx(1.0, abs=0.02)
    assert profil["wp16"] == pytest.approx(1.0 + 4.5 * math.tan(math.radians(4.0)), abs=0.03)


def test_douglas_peucker_findet_die_knicke():
    punkte = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.5), (4.0, 1.0), (5.0, 1.0)]
    assert rk.douglas_peucker(punkte, 0.1) == [0, 2, 4, 5]
    assert rk.douglas_peucker(punkte, 2.0) == [0, 5]


def test_die_karte_mit_hoehe_liefert_treppe_rampe_und_podest(karte_mit_hoehe):
    from spotlab.welt.hoehe import ebenen

    ergebnis = rk.rekonstruiere(karte_mit_hoehe)
    raum, bericht = ergebnis.raum, ergebnis.bericht
    treppen = [b for b in raum.boeden if b.art == "treppe"]
    rampen = [b for b in raum.boeden if b.art == "rampe"]
    podeste = [b for b in raum.boeden if b.art == "podest"]
    assert len(treppen) == 1, [b.name for b in raum.boeden]
    treppe = treppen[0]
    assert treppe.anstieg == pytest.approx(1.0, abs=0.15) and treppe.stufen == 6
    assert 2.0 <= treppe.breite <= 3.6 and 1.6 <= treppe.tiefe <= 2.4
    assert treppe.z == pytest.approx(0.0, abs=0.1)
    assert rampen, "keine Rampe gefunden"
    assert all(abs(abs(r.neigung_grad) - RAMPE_GRAD) < 1.5 for r in rampen), [r.neigung_grad for r in rampen]
    assert 3.5 <= sum(r.breite for r in rampen) <= 6.0
    assert podeste and all(abs(p.z - 1.0) < 0.15 for p in podeste), [p.z for p in podeste]
    assert ebenen(raum)[:2] == [0.0, 1.0]
    assert bericht["treppen"] == 1 and bericht["rampen"] >= 1 and bericht["boeden"] >= 3
    assert abs(bericht["gefaelle_grad"] - RAMPE_GRAD) < 1.5
    assert bericht["stufe_m"] == pytest.approx(0.17)
    tag = raum.tags[0]
    assert tag.id == 7 and tag.z == pytest.approx(1.0, abs=0.15) and tag.hoehe == pytest.approx(0.9, abs=0.15)
    # Der Start liegt im unteren Gang, die Waende haben ihr z: die obere Wand des Gangs B bei 1.0.
    assert any(abs(w.z - 1.0) < 0.15 for w in raum.waende), sorted({round(w.z, 1) for w in raum.waende})


def test_dieselbe_treppe_hoch_und_runter_ist_eine_treppe():
    from spotlab.welt.raum import Boden

    hoch = Boden("Treppe 1", 5.0, 2.0, 3.4, 0.9, z=0.16, anstieg=1.78, stufen=10, drehung=2.0)
    runter = Boden("Treppe 2", 5.4, 2.1, 2.5, 0.9, z=0.18, anstieg=1.39, stufen=8, drehung=181.0)
    andere = Boden("Treppe 3", 12.0, 2.0, 2.0, 1.0, z=0.0, anstieg=1.0, stufen=6, drehung=90.0)
    eine = rk.verschmelze_treppen([hoch, runter, andere])
    assert [t.anstieg for t in eine] == [1.78, 1.0] and [t.name for t in eine] == ["Treppe 1", "Treppe 2"]


def test_kurze_teilstuecke_gehen_im_nachbarn_auf():
    punkte = [(0.0, 0.0), (2.0, 0.0), (2.3, 0.3), (2.5, 2.5), (2.5, 5.0)]
    stuecke = rk._gerade_stuecke(punkte, 0, 4, 20.0)
    assert stuecke == [(0, 2), (2, 4)]                          # das 0.4-m-Stueck haengt am ersten


def test_der_tiefste_boden_wird_zur_null(tmp_path):
    tief = synthetische_karte_mit_hoehe(tmp_path / "tief", versatz_z=-1.8)
    ergebnis = rk.rekonstruiere(tief)
    boeden = ergebnis.raum.boeden
    assert min(min(b.z, b.z_oben) for b in boeden) >= -0.05
    assert any(b.art == "treppe" and abs(b.z) < 0.1 for b in boeden)
    assert any(b.art == "podest" and abs(b.z - 1.0) < 0.15 for b in boeden)
    assert ergebnis.raum.tags[0].z == pytest.approx(1.0, abs=0.15)


def test_ein_ebener_gang_bekommt_keine_boeden(karte):
    ergebnis = rk.rekonstruiere(karte)
    assert ergebnis.raum.boeden == () and ergebnis.bericht["boeden"] == 0
    assert ergebnis.bericht["ebenen"] == [0.0]


def test_die_katakomben_haben_eine_treppe_und_ein_gefaelle():
    if not (KATAKOMBEN / "graph").is_file():
        pytest.skip("Katakomben-Karte fehlt auf diesem Rechner")
    t0 = time.monotonic()
    ergebnis = rk.rekonstruiere(KATAKOMBEN)
    dauer = time.monotonic() - t0
    treppen = [b for b in ergebnis.raum.boeden if b.art == "treppe"]
    assert treppen, ergebnis.bericht
    assert any(1.0 <= b.anstieg <= 2.2 for b in treppen), [b.anstieg for b in treppen]
    assert 1.0 <= ergebnis.bericht["gefaelle_grad"] <= 8.0, ergebnis.bericht["gefaelle_grad"]
    assert min(min(b.z, b.z_oben) for b in ergebnis.raum.boeden) >= -0.05
    assert dauer < 30.0, dauer


def test_das_ergebnis_traegt_den_weg_mit_bodenhoehe(karte_mit_hoehe):
    ergebnis = rk.rekonstruiere(karte_mit_hoehe)
    assert len(ergebnis.weg) == 17
    unten = [z for _x, _y, z in ergebnis.weg[:5]]
    oben = [z for _x, _y, z in ergebnis.weg[9:12]]
    assert max(abs(z) for z in unten) < 0.1 and all(abs(z - 1.0) < 0.15 for z in oben)
    # Der Weg liegt im Raumrahmen: die Wegpunkte laufen durch den Gang zwischen den Waenden.
    xs = [x for x, _y, _z in ergebnis.weg]
    assert min(xs) >= 0.0 and max(xs) - min(xs) == pytest.approx(16.0, abs=0.5)
    assert any("Korrigieren" in h for h in ergebnis.bericht["hinweise"])
