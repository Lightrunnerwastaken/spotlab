"""Geometrie und Kamera der 3D-Sicht -- ohne GL, unter offscreen testbar."""
import math

import pytest

pytest.importorskip("PySide6.QtGui")

from spotlab.gui.raumeditor import geometrie3d as g  # noqa: E402
from spotlab.welt.raum import Block, Raum, RaumTag  # noqa: E402


def test_ein_kasten_hat_36_vertices_mit_normalen_und_dreht_sich():
    daten = g.kasten(1.0, 2.0, 0.5, 1.0, 0.25, 0.5, yaw_grad=90.0)
    assert len(daten) == 36 * 6
    xs = daten[0::6]
    ys = daten[1::6]
    zs = daten[2::6]
    # 2 m lang entlang der eigenen x-Achse, die nach +y zeigt: y spannt 1..3, x nur 0.75..1.25
    assert min(ys) == pytest.approx(1.0) and max(ys) == pytest.approx(3.0)
    assert min(xs) == pytest.approx(0.75) and max(xs) == pytest.approx(1.25)
    assert min(zs) == pytest.approx(0.0) and max(zs) == pytest.approx(1.0)
    normalen = {tuple(round(v, 6) for v in daten[i + 3:i + 6]) for i in range(0, len(daten), 6)}
    assert len(normalen) == 6                       # sechs Flaechen, sechs Richtungen
    assert all(abs(math.hypot(*n) - 1.0) < 1e-6 for n in normalen)


def test_kaesten_aus_raum_nennen_ihre_schluessel():
    raum = Raum(name="T", beschreibung="", start=(1.0, 1.0, 0.0),
                waende=((0, 0, 4, 0),), bloecke=(Block("K", 2, 2, 1, 1),),
                tags=(RaumTag(1, 3, 3, 90.0),))
    kaesten = g.kaesten_aus_raum(raum, frozenset())
    schluessel = [s for s, _ in kaesten]
    assert schluessel == [("wand", 0), ("block", 0), ("tag", 0), ("start",)]
    wand = dict(kaesten)[("wand", 0)]
    assert max(wand[2::6]) == pytest.approx(raum.wand_hoehe)
    spot = dict(kaesten)[("start",)]
    assert max(spot[2::6]) == pytest.approx(0.6) and min(spot[2::6]) == pytest.approx(0.4)


def test_bodenraster_und_pfeil():
    linien = g.bodenraster((0.0, 0.0, 2.0, 1.0), schritt=1.0)
    assert len(linien) % 6 == 0
    assert len(linien) // 6 == 3 + 2                 # x = 0, 1, 2 und y = 0, 1
    pfeil = g.spot_pfeil((1.0, 1.0, 90.0))
    assert pfeil[:3] == [1.0, 1.0, 0.3] and pfeil[4] == pytest.approx(1.6)


def test_kamera_schaut_auf_das_ziel_und_rahmt_den_raum():
    kamera = g.Kamera()
    kamera.rahme((0.0, 0.0, 6.0, 4.0))
    assert kamera.ziel == (3.0, 2.0, 0.0)
    auge = kamera.auge()
    assert auge.z() > 0 and kamera.abstand > 6.0
    sicht = kamera.ansicht()
    mitte = sicht.map(g.QVector3D(3.0, 2.0, 0.0))
    assert abs(mitte.x()) < 1e-6 and abs(mitte.y()) < 1e-6 and mitte.z() < 0   # vor der Kamera, mittig
    kamera.orbit(10.0, 200.0)
    assert kamera.elevation == 89.0                   # Deckel
    kamera.zoom(0.001)
    assert kamera.abstand == 1.0


def test_der_mausstrahl_durch_die_bildmitte_trifft_das_ziel():
    kamera = g.Kamera(ziel=(3.0, 2.0, 0.0), abstand=8.0, azimut=30.0, elevation=40.0)
    punkt = kamera.bodenpunkt(400, 300, 800, 600)
    assert punkt == (pytest.approx(3.0, abs=1e-3), pytest.approx(2.0, abs=1e-3))
    kamera.schwenke(1.0, 0.0)
    assert kamera.ziel[0] != 3.0 or kamera.ziel[1] != 2.0


def test_farb_ids_sind_umkehrbar():
    for index in (1, 2, 255, 256, 65537):
        r, gg, b = g.farbe_fuer(index)
        assert g.index_aus(round(r * 255), round(gg * 255), round(b * 255)) == index
    assert g.index_aus(0, 0, 0) == 0


# ------------------------------------------------------------- Hoehe (Stufe 13)


def test_ein_kasten_mit_nick_hebt_bei_negativem_nick_sein_plus_x_ende():
    daten = g.kasten(0.0, 0.0, 0.0, 1.0, 0.5, 0.1, pitch_grad=-30.0)
    xs, zs = daten[0::6], daten[2::6]
    vorne = [z for x, z in zip(xs, zs) if x > 0.5]
    hinten = [z for x, z in zip(xs, zs) if x < -0.5]
    assert min(vorne) > max(hinten)
    normalen = {tuple(round(v, 6) for v in daten[i + 3:i + 6]) for i in range(0, len(daten), 6)}
    assert len(normalen) == 6


def test_boeden_kommen_als_dieselben_kaesten_wie_in_mujoco():
    from spotlab.welt.hoehe import kaesten_fuer
    from spotlab.welt.raum import Boden, Wand

    raum = Raum(name="H", beschreibung="", start=(5.0, 0.0, 0.0), waende=(Wand(0, 3, 6, 3, z=1.0),),
                boeden=(Boden("T", 3, 0, 2, 2, anstieg=1.0, stufen=5), Boden("P", 5, 0, 2, 2, z=1.0)))
    kaesten = g.kaesten_aus_raum(raum, frozenset())
    schluessel = [s for s, _ in kaesten]
    assert schluessel.count(("boden", 0)) == 5 and schluessel.count(("boden", 1)) == 1
    wand = next(v for s, v in kaesten if s == ("wand", 0))
    assert min(wand[2::6]) == pytest.approx(1.0) and max(wand[2::6]) == pytest.approx(2.0)
    spot = next(v for s, v in kaesten if s == ("start",))
    assert min(spot[2::6]) == pytest.approx(1.4) and max(spot[2::6]) == pytest.approx(1.6)   # auf dem Podest
    erwartet = kaesten_fuer(raum.boeden[1], 0.0)[0]
    podest = next(v for s, v in kaesten if s == ("boden", 1))
    assert (min(podest[2::6]), max(podest[2::6])) == (pytest.approx(0.0), pytest.approx(1.0))
    assert erwartet[3] == pytest.approx(0.5)


def test_bodenraster_liegt_auf_der_tiefsten_ebene():
    linien = g.bodenraster((0.0, 0.0, 2.0, 1.0), schritt=1.0, z=-1.0)
    assert set(linien[2::3]) == {-1.0}


# ------------------------------------------------------------- Gelaende


def test_zwei_dreiecke_je_voller_zelle_und_eins_bei_drei_knoten():
    from spotlab.gui.raumeditor.geometrie3d import gelaende_dreiecke
    from spotlab.welt import gelaende as g

    voll = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.0)
    assert sum(len(v) for _b, v in gelaende_dreiecke(voll)) == 2 * 3 * 6
    drei = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: None if (x, y) == (1.0, 1.0) else 0.0)
    assert sum(len(v) for _b, v in gelaende_dreiecke(drei)) == 1 * 3 * 6


def test_die_normale_zeigt_nach_oben_und_das_band_stimmt():
    from spotlab.gui.raumeditor.geometrie3d import gelaende_dreiecke
    from spotlab.welt import gelaende as g

    ge = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.6)
    ((band, v),) = gelaende_dreiecke(ge)
    assert band == 2 and v[5] > 0.99 and v[2] == pytest.approx(0.6)


def test_kaesten_aus_raum_beginnt_mit_dem_gelaende():
    from spotlab.gui.raumeditor.geometrie3d import kaesten_aus_raum
    from spotlab.welt import gelaende as g
    from spotlab.welt.raum import Raum

    raum = Raum("G", "", (0.5, 0.5, 0.0), gelaende=g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.0))
    kaesten = kaesten_aus_raum(raum, frozenset())
    assert kaesten[0][0] == ("gelaende", 0) and kaesten[-1][0] == ("start",)
