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


# ------------------------------------------------------------- Vorschlaege


def _punkte_auf(x1, y1, x2, y2, n=40):
    return [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]


def test_der_weg_durch_die_luecke_macht_einen_durchgang():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0))
    (l,) = k.finde_luecken(raum, weg=[(2.5, -1.0, 0.0), (2.5, 1.0, 0.0)])
    assert l.vorschlag == "durchgang" and "lief hindurch" in l.grund


def test_punkte_in_der_luecke_machen_eine_wand():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0))
    (l,) = k.finde_luecken(raum, pauspapier=_punkte_auf(2.0, 0.0, 3.0, 0.0))
    assert l.vorschlag == "wand" and "Punkte" in l.grund


def test_ohne_beides_unklar():
    (l,) = k.finde_luecken(_raum((0, 0, 2, 0), (3, 0, 5, 0)))
    assert l.vorschlag == "unklar" and "entscheiden" in l.grund


def test_eine_wand_quer_ueber_den_weg_soll_weg():
    raum = _raum((0, 0, 6, 0), (3, -1, 3, 1))
    luecken = k.finde_luecken(raum, weg=[(1.0, 0.5, 0.0), (5.0, 0.5, 0.0)])
    (kreuzt,) = [l for l in luecken if l.art == "kreuzt"]
    assert kreuzt.waende == (1,) and kreuzt.vorschlag == "loeschen" and kreuzt.enden == ()
    assert kreuzt.strecken == ((3.0, -1.0, 3.0, 1.0),)


def test_das_u_mit_tuer():
    # U: unten 0..6, links in zwei Stuecken mit Bruch (Punkte), rechts mit Tuer (Weg hindurch).
    raum = _raum((0, 0, 6, 0), (0, 0, 0, 1.8), (0, 2.2, 0, 4), (6, 0.5, 6, 1.5), (6, 2.6, 6, 4))
    punkte = _punkte_auf(0, 1.8, 0, 2.2) + _punkte_auf(6, 0, 6, 0.5)
    weg = [(5.0, 2.0, 0.0), (7.0, 2.0, 0.0)]
    luecken = k.finde_luecken(raum, weg=weg, pauspapier=punkte)
    arten = {(tuple(sorted(l.waende)), l.art): l.vorschlag for l in luecken}
    assert arten[((1, 2), "luecke")] == "wand"
    assert arten[((3, 4), "luecke")] == "durchgang"
    assert arten[((0, 3), "ecke")] == "wand"
