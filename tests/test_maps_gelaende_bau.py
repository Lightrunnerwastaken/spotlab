"""Der Gelaendebau: Sperren, Fluten, offene Raender, Membran ueber dem Weg."""

import math

import numpy as np
import pytest

pytest.importorskip("numpy")

from spotlab.errors import SpotlabError  # noqa: E402
from spotlab.maps import gelaende_bau as gb  # noqa: E402
from spotlab.welt.raum import Raum, Wand  # noqa: E402


def _l_gang():
    """Gang 2 m breit: Schenkel A entlang x (0..8, y 0..2), Schenkel B entlang y (x 6..8, y 2..8).
    Die Aussenwand rechts hat eine 1-m-Luecke bei y 4..5 (ohne Punkte)."""
    waende = [Wand(0, 0, 8, 0), Wand(0, 0, 0, 2), Wand(0, 2, 6, 2), Wand(6, 2, 6, 8),
              Wand(8, 0, 8, 4), Wand(8, 5, 8, 8), Wand(6, 8, 8, 8)]
    weg = [(1.0, 1.0, 0.0), (7.0, 1.0, 0.42), (7.0, 7.0, 0.42)]      # 4 Grad ueber 6 m in A
    return Raum("L", "", (1.0, 1.0, 0.0), waende=waende), weg


def test_das_gelaende_reicht_bis_an_die_waende():
    raum, weg = _l_gang()
    ge = gb.baue_gelaende(raum, weg, []).gelaende
    assert ge.hoehe_bei(0.3, 0.3) is not None and ge.hoehe_bei(7.7, 7.7) is not None
    assert ge.hoehe_bei(3.0, 5.0) is None              # ausserhalb des L
    assert ge.hoehe_bei(1.0, 1.0) == pytest.approx(0.0, abs=0.02)


def test_genau_ein_offener_rand_an_der_luecke():
    raum, weg = _l_gang()
    erg = gb.baue_gelaende(raum, weg, [])
    # Durch die Luecke fliesst der Boden hinaus, bis 2 m neben dem Weg (x = 7): der offene
    # Rand liegt draussen, in einem Lauf; im Gang selbst ist nichts offen.
    assert erg.bericht["offen"] == 1 and erg.offene_raender

    def im_gang(x, y):
        return (0 < x < 8 and 0 < y < 2) or (6 < x < 8 and 2 < y < 8)

    assert not any(im_gang(x, y) for x, y in erg.offene_raender)
    assert max(x for x, _y in erg.offene_raender) <= 9.0 + 0.3


def test_punkte_sperren_und_rauschen_nicht():
    raum, weg = _l_gang()
    dicht = [(8.0, 4.0 + 0.05 * i) for i in range(21)] * 6   # die Luecke voller Punkte: sperrt
    erg = gb.baue_gelaende(raum, weg, dicht)
    assert erg.bericht["offen"] == 0 and erg.gelaende.hoehe_bei(8.5, 4.5) is None
    rauschen = [(3.0, 1.0)] * 6 + [(3.2, 1.0)] * 6        # zwei Zellen mitten im Gang: Rauschen
    erg = gb.baue_gelaende(raum, weg, rauschen)
    assert erg.gelaende.hoehe_bei(3.0, 1.0) is not None


def test_der_weg_bleibt_frei_und_loecher_werden_gefuellt():
    raum, weg = _l_gang()
    quer = Raum("L", "", (1, 1, 0), waende=list(raum.waende) + [Wand(4, 0, 4, 2)])
    assert gb.baue_gelaende(quer, weg, []).gelaende.hoehe_bei(4.0, 1.0) is not None
    insel = Raum("L", "", (1, 1, 0), waende=list(raum.waende) + [
        Wand(2, 0.5, 3, 0.5), Wand(3, 0.5, 3, 1.5), Wand(3, 1.5, 2, 1.5), Wand(2, 1.5, 2, 0.5)])
    assert gb.baue_gelaende(insel, weg, []).gelaende.hoehe_bei(2.5, 1.0) is not None


def test_ohne_weg_ein_klarer_fehler():
    raum, _ = _l_gang()
    with pytest.raises(SpotlabError, match="Weg"):
        gb.baue_gelaende(raum, [(1.0, 1.0, 0.0)], [])


def test_quer_eben_laengs_das_gefaelle():
    raum, weg = _l_gang()
    ge = gb.baue_gelaende(raum, weg, []).gelaende
    # Bis 2 m vor der Ecke ist der Gang quer eben; naeher zieht die Membran zum Nordgang.
    for x in (2.0, 3.5, 5.0):
        quer = [ge.hoehe_bei(x, y) for y in np.arange(0.3, 1.8, 0.1)]
        assert max(quer) - min(quer) < 0.01, x
    steigung = (ge.hoehe_bei(6.0, 1.0) - ge.hoehe_bei(2.0, 1.0)) / 4.0
    assert math.degrees(math.atan(steigung)) == pytest.approx(4.0, abs=0.5)


def test_keine_klippe_entlang_des_wegs_und_der_tiefste_knoten_ist_null():
    from spotlab.welt.gelaende import klippen

    raum, weg = _l_gang()
    erg = gb.baue_gelaende(raum, weg, [])
    assert min(h for h in erg.gelaende.hoehen if h is not None) == pytest.approx(0.0, abs=1e-6)
    assert not [k for k in klippen(erg.gelaende) if 0.5 < k[0] < 7.5 and 0.5 < k[1] < 1.5]
    assert erg.bericht["iterationen"] < 3000 and erg.bericht["dauer_s"] < 5.0
    assert erg.bericht["knoten"] > 0 and erg.bericht["verschiebung"] == pytest.approx(0.0, abs=1e-6)
