import math

import pytest

from spotlab.api.world import ObstacleGrid, Tag, WorldObject, richtung


def test_richtung_rechnet_in_grad_und_meter():
    bearing, distance = richtung(3.0, 4.0)
    assert distance == pytest.approx(5.0)
    assert bearing == pytest.approx(math.degrees(math.atan2(4.0, 3.0)))


def test_richtung_links_ist_positiv():
    links, _ = richtung(1.0, 1.0)
    rechts, _ = richtung(1.0, -1.0)
    assert links > 0
    assert rechts < 0


def test_richtung_geradeaus_ist_null_grad():
    bearing, distance = richtung(2.0, 0.0)
    assert bearing == pytest.approx(0.0)
    assert distance == pytest.approx(2.0)


def test_tag_erbt_die_felder_des_objekts():
    tag = Tag(
        name="world_obj_apriltag_001", kind="apriltag", bearing=-23.4,
        distance=2.7, world_xy=(1.0, 2.0), time=100.0, id=1, filtered=True,
    )
    assert isinstance(tag, WorldObject)
    assert tag.id == 1
    assert tag.kind == "apriltag"


def test_gitter_meldet_abstand_und_freiheit():
    import numpy as np

    zellen = np.full((10, 10), 2.0)
    zellen[5, 5] = 0.1
    gitter = ObstacleGrid(cells=zellen, cell_size=0.03, origin=(0.0, 0.0), time=100.0)
    assert gitter.distance_at(5 * 0.03, 5 * 0.03) == pytest.approx(0.1)
    assert not gitter.is_free(5 * 0.03, 5 * 0.03, margin=0.3)
    assert gitter.is_free(1 * 0.03, 1 * 0.03, margin=0.3)


def test_gitter_ausserhalb_gilt_als_unbekannt_nicht_als_frei():
    import numpy as np

    gitter = ObstacleGrid(
        cells=np.full((10, 10), 2.0), cell_size=0.03, origin=(0.0, 0.0), time=100.0
    )
    assert gitter.distance_at(99.0, 99.0) is None
    assert not gitter.is_free(99.0, 99.0)


def test_unbeobachtete_zelle_ist_nicht_frei_obwohl_der_wert_gross_ist():
    """Der Fehler, der einen Roboter in eine Wand faehrt: Unbekannt != frei."""
    import numpy as np

    bekannt = np.ones((10, 10), dtype=bool)
    bekannt[3, 3] = False
    gitter = ObstacleGrid(
        cells=np.full((10, 10), 5.0), cell_size=0.03, origin=(0.0, 0.0),
        time=100.0, known=bekannt,
    )
    assert gitter.distance_at(3 * 0.03, 3 * 0.03) is None
    assert not gitter.is_free(3 * 0.03, 3 * 0.03)
    assert gitter.is_free(4 * 0.03, 4 * 0.03)
