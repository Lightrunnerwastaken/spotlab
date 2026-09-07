"""Der Korrigierer: Wandluecken finden, Vorschlaege aus Weg und Pauspapier, anwenden."""

import pytest

from spotlab.welt import korrektur as k
from spotlab.welt.raum import Boden, Raum, RaumTag, Wand


def _raum(*waende):
    return Raum("K", "", (0.5, 0.5, 0.0), waende=[Wand(*w) for w in waende])


# ------------------------------------------------------------- Kandidaten


def test_zwei_kollineare_waende_mit_luecke():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0))
    (lk,) = k.finde_luecken(raum)
    assert lk.art == "luecke" and lk.waende == (0, 1) and lk.enden == (2, 1)
    assert lk.ziel == pytest.approx((2.6, 0.0)) and lk.laenge == pytest.approx(0.6)
    assert lk.vorschlag == "unklar"


def test_eine_ecke_schliesst_auf_dem_schnittpunkt():
    raum = _raum((0, 0, 2.5, 0), (3, 0.5, 3, 3))
    (lk,) = k.finde_luecken(raum)
    assert lk.art == "ecke" and lk.ziel == pytest.approx((3.0, 0.0))
    assert len(lk.strecken) == 2 and lk.laenge == pytest.approx(1.0)
    assert lk.enden == (2, 1)


def test_ein_anschluss_an_die_wandmitte():
    raum = _raum((0, 0, 6, 0), (3, 0.7, 3, 3))
    (lk,) = k.finde_luecken(raum)
    assert lk.art == "anschluss" and lk.waende == (1, 0) and lk.ziel == pytest.approx((3.0, 0.0))
    assert lk.enden == (1,)


def test_zu_weit_oder_beruehrend_ist_kein_kandidat():
    assert k.finde_luecken(_raum((0, 0, 2, 0), (4, 0, 6, 0))) == []
    assert k.finde_luecken(_raum((0, 0, 2, 0), (2, 0, 4, 0))) == []


def test_kein_kandidat_durch_eine_dritte_wand():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0), (2.5, -1, 2.5, 1))
    assert all(lk.waende != (0, 1) for lk in k.finde_luecken(raum))


def test_je_ende_der_kuerzeste_und_jedes_paar_einmal():
    raum = _raum((0, 0, 2, 0), (2.4, 0, 4, 0), (2.8, 0.05, 5, 0.05))
    luecken = k.finde_luecken(raum)
    assert [lk.waende for lk in luecken].count((0, 1)) == 1
    assert all(sorted(lk.waende) != [0, 2] for lk in luecken)


# ------------------------------------------------------------- Vorschlaege


def _punkte_auf(x1, y1, x2, y2, n=40):
    return [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]


def test_der_weg_durch_die_luecke_macht_einen_durchgang():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0))
    (lk,) = k.finde_luecken(raum, weg=[(2.5, -1.0, 0.0), (2.5, 1.0, 0.0)])
    assert lk.vorschlag == "durchgang" and "lief hindurch" in lk.grund


def test_punkte_in_der_luecke_machen_eine_wand():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0))
    (lk,) = k.finde_luecken(raum, pauspapier=_punkte_auf(2.0, 0.0, 3.0, 0.0))
    assert lk.vorschlag == "wand" and "Punkte" in lk.grund


def test_ohne_beides_unklar():
    (lk,) = k.finde_luecken(_raum((0, 0, 2, 0), (3, 0, 5, 0)))
    assert lk.vorschlag == "unklar" and "entscheiden" in lk.grund


def test_eine_wand_quer_ueber_den_weg_soll_weg():
    raum = _raum((0, 0, 6, 0), (3, -1, 3, 1))
    luecken = k.finde_luecken(raum, weg=[(1.0, 0.5, 0.0), (5.0, 0.5, 0.0)])
    (kreuzt,) = [lk for lk in luecken if lk.art == "kreuzt"]
    assert kreuzt.waende == (1,) and kreuzt.vorschlag == "loeschen" and kreuzt.enden == ()
    assert kreuzt.strecken == ((3.0, -1.0, 3.0, 1.0),)


def test_das_u_mit_tuer():
    # U: unten 0..6, links in zwei Stuecken mit Bruch (Punkte), rechts mit Tuer (Weg hindurch).
    raum = _raum((0, 0, 6, 0), (0, 0, 0, 1.8), (0, 2.2, 0, 4), (6, 0.5, 6, 1.5), (6, 2.6, 6, 4))
    punkte = _punkte_auf(0, 1.8, 0, 2.2) + _punkte_auf(6, 0, 6, 0.5)
    weg = [(5.0, 2.0, 0.0), (7.0, 2.0, 0.0)]
    luecken = k.finde_luecken(raum, weg=weg, pauspapier=punkte)
    arten = {(tuple(sorted(lk.waende)), lk.art): lk.vorschlag for lk in luecken}
    assert arten[((1, 2), "luecke")] == "wand"
    assert arten[((3, 4), "luecke")] == "durchgang"
    assert arten[((0, 3), "ecke")] == "wand"


# ------------------------------------------------------------- Anwenden


def test_wende_an_rueckt_enden_und_loescht():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0), (3, -1, 3, 1))
    luecken = k.finde_luecken(raum, weg=[(1.0, 0.5, 0.0), (4.0, 0.5, 0.0)])
    entscheide = {i: {"luecke": "wand", "kreuzt": "loeschen"}.get(lk.art, "lassen")
                  for i, lk in enumerate(luecken)}
    neu = k.wende_an(raum, luecken, entscheide)
    assert len(neu.waende) == 2 and (neu.waende[0].x2, neu.waende[0].y2) == pytest.approx((2.6, 0.0))


def test_durchgang_und_lassen_aendern_nichts():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0))
    luecken = k.finde_luecken(raum)
    assert k.wende_an(raum, luecken, {0: "durchgang"}) == raum
    assert k.wende_an(raum, luecken, {0: "lassen"}) == raum
    assert k.wende_an(raum, luecken, {}) == raum


def test_eine_ecke_rueckt_beide_enden():
    raum = _raum((0, 0, 2.5, 0), (3, 0.5, 3, 3))
    neu = k.wende_an(raum, k.finde_luecken(raum), {0: "wand"})
    assert (neu.waende[0].x2, neu.waende[0].y2) == pytest.approx((3.0, 0.0))
    assert (neu.waende[1].x1, neu.waende[1].y1) == pytest.approx((3.0, 0.0))
    assert neu.waende[0].z == raum.waende[0].z


def test_uebernimm_gelaende_loest_rampen_auf_und_setzt_z():
    from spotlab.welt import gelaende as g

    ge = g.gitter(0.0, 0.0, 0.5, 5, 9, lambda x, y: 0.1 * x)
    raum = Raum("K", "", (0.5, 0.5, 0.0), waende=[Wand(0, 0, 4, 0)],
                boeden=(Boden("Rampe 1", 2, 1, 2, 1, anstieg=0.2), Boden("Podest 1", 3, 1, 1, 1, z=0.3),
                        Boden("Treppe", 1, 1, 1, 1, z=0.1, anstieg=0.5, stufen=3)),
                tags=(RaumTag(1, 4.0, 1.0, 0.0),))
    neu = k.uebernimm_gelaende(raum, ge, True)
    assert neu.gelaende is ge
    assert [b.name for b in neu.boeden] == ["Treppe"]
    assert neu.waende[0].z == pytest.approx(0.2) and neu.tags[0].z == pytest.approx(0.4)
    assert k.uebernimm_gelaende(raum, ge, False).boeden == raum.boeden
