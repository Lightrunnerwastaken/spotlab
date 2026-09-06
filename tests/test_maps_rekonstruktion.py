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


def synthetische_karte(ordner, mit_wolken=True, drehung_grad=0.0):
    """Gang 6 x 2 m (Waende y = 0 und y = 2), Tuer in der oberen Wand, Tag 7 rechts."""
    ordner = Path(ordner)
    (ordner / "waypoint_snapshots").mkdir(parents=True)
    (ordner / "edge_snapshots").mkdir()
    dreh = SE3Pose(0, 0, 0, Quat.from_yaw(math.radians(drehung_grad)))   # Seed-Rahmen schief

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
    ergebnis = rk.rekonstruiere(ordner)
    assert ergebnis.bericht["quelle"] == "schlauch"
    assert len(ergebnis.raum.waende) == 2 * 5                  # zwei je Kante
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
