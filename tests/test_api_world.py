import math

import pytest

from spotlab.api import world
from spotlab.api.world import ObstacleGrid, Tag, WorldObject, richtung
from spotlab.backends.dryrun import DryRunBackend


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


class Mitschreiber:
    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))


def test_tags_sind_nach_distanz_sortiert():
    assert [t.id for t in world.tags(DryRunBackend(), None)] == [1, 2]


def test_tags_filtert_auf_eine_nummer():
    assert [t.id for t in world.tags(DryRunBackend(), None, id=2)] == [2]


def test_tags_ohne_treffer_liefert_leere_liste_keinen_fehler():
    assert world.tags(DryRunBackend(), None, id=99) == []


def test_jede_abfrage_wird_protokolliert_auch_die_erfolglose():
    schreiber = Mitschreiber()
    world.tags(DryRunBackend(), schreiber, id=99)
    _art, daten = schreiber.ereignisse[-1]
    assert daten["name"] == "tags"
    assert daten["treffer"] == 0


def test_protokoll_nennt_ids_und_distanzen():
    schreiber = Mitschreiber()
    world.tags(DryRunBackend(), schreiber)
    _art, daten = schreiber.ereignisse[-1]
    assert daten["ids"] == [1, 2]
    assert len(daten["distanzen"]) == 2


def test_world_objects_liefert_auch_nicht_tags():
    arten = {o.kind for o in world.world_objects(DryRunBackend(), None)}
    assert "dock" in arten


def test_obstacles_liefert_ein_gitter():
    assert world.obstacles(DryRunBackend(), None).cell_size > 0


def test_backend_ohne_faehigkeit_wird_deutlich_abgewiesen():
    from spotlab.backends.base import Capability
    from spotlab.errors import UnsupportedCapability

    class Ohne:
        def capabilities(self):
            return Capability.LOCOMOTION

    with pytest.raises(UnsupportedCapability) as fehler:
        world.tags(Ohne(), None)
    assert "Objekte" in str(fehler.value)


# ------------------------------------------------------------ free_distance


def _raum_mit_wand(wand_x=1.5):
    """5x5 m bekannt, eine Wand bei x = wand_x (Abstandsgitter, 0.05 m Zellen)."""
    import numpy as np

    n, c = 100, 0.05
    xs = np.arange(n) * c
    ys = np.arange(n) * c
    X, Y = np.meshgrid(xs, ys)                        # [zeile=y, spalte=x]
    abstand = np.abs(X - wand_x)
    return ObstacleGrid(cells=abstand, cell_size=c, origin=(0.0, 0.0), time=0.0,
                        known=np.ones((n, n), dtype=bool))


def test_free_distance_misst_bis_zur_wand():
    gitter = _raum_mit_wand(wand_x=2.0)
    # Von (0.5, 2.5) nach Osten: die Wand steht 1.5 m entfernt, der Rand von
    # 0.3 m gilt -- frei sind rund 1.2 m.
    frei = gitter.free_distance(0.5, 2.5, 0.0)
    assert 1.05 <= frei <= 1.25, frei


def test_free_distance_ist_nach_hinten_offen():
    gitter = _raum_mit_wand(wand_x=4.5)
    assert gitter.free_distance(2.5, 2.5, 180.0) == pytest.approx(1.8)      # FREI_BIS_M


def test_free_distance_faengt_erst_vor_dem_koerper_an():
    """Unter und dicht vor Spot ist das Gitter unbekannt (Koerperschatten) --
    die Messung beginnt deshalb FREI_AB_M vor dem Punkt und meldet nicht
    faelschlich 0."""

    gitter = _raum_mit_wand(wand_x=4.5)
    bekannt = gitter.known.copy()
    bekannt[45:55, 45:55] = False                     # Schatten um (2.5, 2.5)
    gitter = ObstacleGrid(cells=gitter.cells, cell_size=gitter.cell_size,
                          origin=gitter.origin, time=0.0, known=bekannt)
    assert gitter.free_distance(2.5, 2.5, 0.0) > 1.0


def test_free_distance_null_wenn_direkt_davor_zu():
    gitter = _raum_mit_wand(wand_x=0.6)
    assert gitter.free_distance(0.5, 2.5, 0.0) == 0.0


def test_free_distance_sieht_ein_bekanntes_hindernis_auch_dicht_vor_der_nase():
    """Nach einer Drehung auf der Stelle steht die Wand, die eben noch seitlich
    war, 0.4 m vor der Nase -- BEKANNT, im Gitter. Ab FREI_AB_M zu messen und
    sie zu uebersehen, hiesse hineinzulaufen (2D-Uebungsraum, 06.09.2026)."""
    gitter = _raum_mit_wand(wand_x=0.9)                # 0.4 m voraus, weit vor FREI_AB_M
    assert gitter.free_distance(0.5, 2.5, 0.0) < 0.2


def test_free_distance_ignoriert_unbekanntes_nur_im_koerperschatten():
    """Dicht am Koerper zaehlt Unbekanntes nicht (dort sieht Spot nie etwas),
    weiter draussen sehr wohl: hinter der Sichtgrenze ist nicht frei."""
    gitter = _raum_mit_wand(wand_x=4.5)
    bekannt = gitter.known.copy()
    bekannt[:, 30:] = False                            # ab x = 1.5 m nichts mehr bekannt
    gitter = ObstacleGrid(cells=gitter.cells, cell_size=gitter.cell_size,
                          origin=gitter.origin, time=0.0, known=bekannt)
    frei = gitter.free_distance(0.5, 2.5, 0.0)
    assert 0.9 <= frei <= 1.05, frei                   # bis zur Sichtgrenze, nicht weiter
