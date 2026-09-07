"""Der Korrigierer: Wandluecken finden, Vorschlaege aus Weg und Pauspapier, anwenden."""

import pytest

from spotlab.welt import korrektur as k
from spotlab.welt.raum import Boden, Raum, RaumTag, Wand


def _raum(*waende):
    return Raum("K", "", (0.5, 0.5, 0.0), waende=[Wand(*w) for w in waende])


# ------------------------------------------------------------- Kandidaten


def test_zwei_kollineare_waende_mit_luecke():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0))
    (l,) = k.finde_luecken(raum)
    assert l.art == "luecke" and l.waende == (0, 1) and l.enden == (2, 1)
    assert l.ziel == pytest.approx((2.6, 0.0)) and l.laenge == pytest.approx(0.6)
    assert l.vorschlag == "unklar"


def test_eine_ecke_schliesst_auf_dem_schnittpunkt():
    raum = _raum((0, 0, 2.5, 0), (3, 0.5, 3, 3))
    (l,) = k.finde_luecken(raum)
    assert l.art == "ecke" and l.ziel == pytest.approx((3.0, 0.0))
    assert len(l.strecken) == 2 and l.laenge == pytest.approx(1.0)
    assert l.enden == (2, 1)


def test_ein_anschluss_an_die_wandmitte():
    raum = _raum((0, 0, 6, 0), (3, 0.7, 3, 3))
    (l,) = k.finde_luecken(raum)
    assert l.art == "anschluss" and l.waende == (1, 0) and l.ziel == pytest.approx((3.0, 0.0))
    assert l.enden == (1,)


def test_zu_weit_oder_beruehrend_ist_kein_kandidat():
    assert k.finde_luecken(_raum((0, 0, 2, 0), (4, 0, 6, 0))) == []
    assert k.finde_luecken(_raum((0, 0, 2, 0), (2, 0, 4, 0))) == []


def test_kein_kandidat_durch_eine_dritte_wand():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0), (2.5, -1, 2.5, 1))
    assert all(l.waende != (0, 1) for l in k.finde_luecken(raum))


def test_je_ende_der_kuerzeste_und_jedes_paar_einmal():
    raum = _raum((0, 0, 2, 0), (2.4, 0, 4, 0), (2.8, 0.05, 5, 0.05))
    luecken = k.finde_luecken(raum)
    assert [l.waende for l in luecken].count((0, 1)) == 1
    assert all(sorted(l.waende) != [0, 2] for l in luecken)
