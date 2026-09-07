"""Die Hoehenfunktion: der Boden unter einem Punkt, Klippen, Treppenregel, Kaesten."""
import math

import pytest

from spotlab.welt import hoehe as h
from spotlab.welt.raum import MAX_STUFE_M, Block, Boden, Raum, RaumTag, Wand

RAUM = Raum(name="H", beschreibung="", start=(0.5, 0.5, 0),
            boeden=(Boden("Rampe", 3, 1, 2, 1, anstieg=1.0),          # x 2..4, y 0.5..1.5, 0 -> 1
                    Boden("Podest", 6, 1, 4, 3, z=1.0),               # x 4..8, y -0.5..2.5
                    Boden("Bruecke", 6, 5, 4, 1, z=2.0)))             # x 4..8, y 4.5..5.5, ueber dem Grund


def test_boden_bei_nimmt_den_boden_der_eigenen_hoehe_am_naechsten():
    assert h.boden_bei(RAUM, 1, 1) == (0.0, None)
    assert h.boden_bei(RAUM, 3, 1)[0] == pytest.approx(0.5)
    assert h.boden_bei(RAUM, 3, 1)[1].name == "Rampe"
    assert h.boden_bei(RAUM, 6, 1)[0] == pytest.approx(1.0)
    assert h.boden_bei(RAUM, 6, 5, z_nahe=0.0)[0] == 0.0          # unter der Bruecke
    assert h.boden_bei(RAUM, 6, 5, z_nahe=1.9)[0] == 2.0          # auf der Bruecke
    assert h.boden_bei(RAUM, 6, 5, z_nahe=1.9, ohne=RAUM.boeden[2])[0] == 0.0


def test_neigung_und_nick_folgen_der_gedrehten_rampe():
    raum = Raum(name="H", beschreibung="", start=(0, 0, 0),
                boeden=(Boden("R", 0, 0, 2, 1, anstieg=1.0, drehung=90.0),))   # steigt nach +y
    dzdx, dzdy = h.neigung_bei(raum, 0, 0)
    assert dzdx == pytest.approx(0.0, abs=1e-9) and dzdy == pytest.approx(0.5)
    steil = math.degrees(math.atan(0.5))
    # Rechte-Hand-Regel um y: bergauf fahren ist Nase hoch, also NEGATIVER Nick.
    assert h.nick_grad(raum, 0, 0, math.radians(90)) == pytest.approx(-steil)
    assert h.nick_grad(raum, 0, 0, math.radians(-90)) == pytest.approx(steil)
    assert h.nick_grad(raum, 0, 0, 0.0) == pytest.approx(0.0, abs=1e-9)      # quer zur Rampe
    assert h.nick_grad(RAUM, 6, 1, 0.0) == 0.0                                # Podest


def test_ebenen_sind_die_gerundeten_bodenhoehen():
    assert h.ebenen(RAUM) == [0.0, 1.0, 2.0]
    assert h.ebenen(Raum(name="L", beschreibung="", start=(0, 0, 0))) == [0.0]
    assert h.boden_z(RAUM) == 0.0
    tief = Raum(name="T", beschreibung="", start=(0, 0, 0), boeden=(Boden("G", 0, 0, 2, 2, z=-1.8),))
    assert h.boden_z(tief) == -1.8


def test_hoehenband_und_ebene():
    raum = Raum(name="H", beschreibung="", start=(0, 0, 0), wand_hoehe=1.0,
                waende=(Wand(0, 0, 4, 0), Wand(0, 3, 4, 3, z=1.2)),
                bloecke=(Block("K", 2, 2, 1, 1, hoehe=0.5, z=1.2),),
                tags=(RaumTag(3, 3, 3, 90.0, hoehe=0.3, z=1.2),),
                boeden=(Boden("T", 2, 1, 2, 1, anstieg=1.2, stufen=7),))
    assert h.hoehenband(raum.waende[0], raum) == (0.0, 1.0)
    assert h.hoehenband(raum.bloecke[0], raum) == (1.2, 1.7)
    assert h.hoehenband(raum.tags[0], raum) == (1.5, 1.5)
    assert h.hoehenband(raum.boeden[0], raum) == (0.0, 1.2)
    assert h.auf_ebene(raum.waende[0], raum, 0.0) and not h.auf_ebene(raum.waende[0], raum, 1.2)
    assert h.auf_ebene(raum.waende[1], raum, 1.2) and not h.auf_ebene(raum.waende[1], raum, 0.0)
    assert h.auf_ebene(raum.boeden[0], raum, 0.0) and h.auf_ebene(raum.boeden[0], raum, 1.2)
    assert h.auf_ebene(raum.tags[0], raum, 1.2)


def test_klippen_liegen_an_den_seiten_der_rampe_nicht_an_fuss_und_kopf():
    kanten = h.klippen(RAUM)
    assert kanten
    # Seiten der Rampe (y = 0.5 und 1.5) werden Klippe, sobald sie 0.25 m ueber dem Grund liegen.
    seiten = [k for k in kanten if abs(k[1] - k[3]) < 1e-6 and 2.0 <= min(k[0], k[2]) and max(k[0], k[2]) <= 4.0]
    assert {round(k[1], 2) for k in seiten} == {0.5, 1.5}
    assert all(min(k[0], k[2]) >= 2.4 for k in seiten)            # unterhalb 0.25 m keine Klippe
    # Fusskante (x = 2) und Kopfkante zum Podest (x = 4, y 0.5..1.5) sind frei.
    senkrecht = [k for k in kanten if abs(k[0] - k[2]) < 1e-6]
    assert not any(abs(k[0] - 2.0) < 1e-6 for k in senkrecht)
    assert not any(abs(k[0] - 4.0) < 1e-6 and 0.5 <= min(k[1], k[3]) and max(k[1], k[3]) <= 1.5
                   for k in senkrecht)
    # Die Podestkante bei x = 8 ist eine Klippe; die Bruecke hat rundum Klippen.
    assert any(abs(k[0] - 8.0) < 1e-6 for k in senkrecht)
    assert any(abs(k[1] - 4.5) < 1e-6 and abs(k[3] - 4.5) < 1e-6 for k in kanten)


def test_mit_alles_sind_auch_rampen_und_treppen_klippen():
    kanten = h.klippen(RAUM, alles=True)
    senkrecht = [k for k in kanten if abs(k[0] - k[2]) < 1e-6]
    assert any(abs(k[0] - 2.0) < 1e-6 for k in senkrecht)         # jetzt auch der Rampenfuss


TREPPE = Raum(name="H", beschreibung="", start=(0, 0, 0),
              boeden=(Boden("T", 3, 0, 2, 1, anstieg=1.0, stufen=5),    # x 2..4
                      Boden("P", 5, 0, 2, 1, z=1.0)))                    # x 4..6


def test_treppe_vor_kennt_richtung_und_achse():
    lage = h.treppe_vor(TREPPE, 1.0, 0.0, 0.0)
    assert lage.boden.name == "T" and lage.richtung == "auf"
    assert lage.abstand == pytest.approx(1.0) and lage.achsenwinkel_grad == pytest.approx(0.0)
    assert lage.peilung_grad == pytest.approx(0.0)
    lage = h.treppe_vor(TREPPE, 4.5, 0.0, 180.0, z_nahe=1.0)
    assert lage.richtung == "ab" and lage.achsenwinkel_grad == pytest.approx(180.0)
    assert lage.abstand == pytest.approx(0.5)
    # Rueckwaerts an die Kopfkante: die Nase zeigt bergauf, die Treppe liegt hinten.
    lage = h.treppe_vor(TREPPE, 4.5, 0.0, 0.0, z_nahe=1.0)
    assert lage.richtung == "ab" and lage.achsenwinkel_grad == pytest.approx(0.0)
    assert lage.peilung_grad == pytest.approx(180.0)
    assert h.treppe_vor(TREPPE, 1.0, 0.0, 90.0) is None            # quer: keine Treppe im Weg
    assert h.treppe_vor(TREPPE, 0.0, 0.0, 0.0) is None             # zu weit (2 m > 1.5 m)


def test_die_treppenregel():
    assert h.treppe_erlaubt("auf", 0.2, 10.0) == (True, "vorwärts hoch")
    assert h.treppe_erlaubt("auf", -0.2, 170.0) == (False, "vorwärts hoch")
    assert h.treppe_erlaubt("auf", 0.2, 80.0) == (False, "vorwärts hoch")     # schraeg
    assert h.treppe_erlaubt("ab", -0.2, 20.0) == (True, "rückwärts runter")
    assert h.treppe_erlaubt("ab", 0.2, 170.0) == (False, "rückwärts runter")
    assert h.treppe_erlaubt("ab", 0.0, 0.0) == (True, "rückwärts runter")      # stehen darf man


def test_kaesten_fuer_treppe_rampe_und_podest():
    stufen = h.kaesten_fuer(Boden("T", 3, 0, 2, 1, anstieg=1.0, stufen=5), boden_z=0.0)
    assert len(stufen) == 5 and [k[0] for k in stufen][0] == "stufe_T_0"
    assert stufen[0][3] == pytest.approx(0.1) and stufen[0][6] == pytest.approx(0.1)     # 0..0.2
    assert stufen[-1][3] == pytest.approx(0.5) and stufen[-1][6] == pytest.approx(0.5)   # 0..1.0
    assert stufen[0][1] == pytest.approx(2.2) and stufen[-1][1] == pytest.approx(3.8)
    rampe = h.kaesten_fuer(Boden("R", 3, 0, 2, 1, anstieg=1.0), boden_z=0.0)
    geneigt = [k for k in rampe if k[8] != 0.0]
    assert len(geneigt) == 1 and geneigt[0][8] == pytest.approx(-math.degrees(math.atan(0.5)))
    assert geneigt[0][0] == "rampe_R" and geneigt[0][4] == pytest.approx(math.hypot(2.0, 1.0) / 2)
    assert h.kaesten_fuer(Boden("P", 3, 0, 2, 1, z=0.0), boden_z=0.0) == []
    podest = h.kaesten_fuer(Boden("P", 3, 0, 2, 1, z=1.2), boden_z=-0.5)
    assert len(podest) == 1 and podest[0][3] == pytest.approx(0.35) and podest[0][6] == pytest.approx(0.85)


def test_max_stufe_ist_die_regel():
    assert h.MAX_STUFE_M == MAX_STUFE_M == 0.25


# ------------------------------------------------------------- Gelaende


def _mit_gelaende(f, boeden=()):
    from spotlab.welt import gelaende as g
    return Raum("G", "", (0.5, 0.5, 0.0), boeden=boeden,
                gelaende=g.gitter(0.0, 0.0, 0.2, 11, 31, f))     # 6 x 2 m


def test_der_grund_ist_das_gelaende():
    raum = _mit_gelaende(lambda x, y: 0.1 * x)
    z, boden = h.boden_bei(raum, 3.0, 1.0)
    assert z == pytest.approx(0.3) and boden is None


def test_ausserhalb_des_gelaendes_ist_der_grund_null():
    assert h.boden_bei(_mit_gelaende(lambda x, y: 0.5), 9.0, 9.0) == (0.0, None)


def test_eine_treppe_auf_dem_gelaende_gewinnt():
    treppe = Boden("T", 3.0, 1.0, 2.0, 1.0, z=0.3, anstieg=1.0, stufen=6)
    raum = _mit_gelaende(lambda x, y: 0.3, boeden=(treppe,))
    assert h.boden_bei(raum, 3.0, 1.0)[1] is treppe


def test_nick_auf_dem_gefaelle():
    raum = _mit_gelaende(lambda x, y: 0.1 * x)
    assert h.nick_grad(raum, 3.0, 1.0, 0.0) == pytest.approx(-math.degrees(math.atan(0.1)), abs=0.3)


def test_ebenen_mit_plateaus():
    raum = _mit_gelaende(lambda x, y: 0.0 if x < 2.0 else (1.0 if x > 4.0 else (x - 2.0) * 0.5))
    assert h.ebenen(raum) == [0.0, 1.0]


def test_klippen_des_gelaendes_gehoeren_zum_raum():
    raum = _mit_gelaende(lambda x, y: 0.0 if x < 3.0 else 0.6)
    assert any(abs(k[0] - 2.9) < 1e-6 or abs(k[0] - 3.1) < 1e-6 for k in h.klippen(raum))


def test_boden_z_ist_der_tiefste_knoten():
    assert h.boden_z(_mit_gelaende(lambda x, y: -0.4 + 0.1 * x)) == pytest.approx(-0.4)


def test_gelaendeklippen_unter_einem_boden_zaehlen_nicht():
    sprung = lambda x, y: 0.0 if x < 3.0 else 0.6                       # noqa: E731
    ohne = _mit_gelaende(sprung)
    treppe = Boden("T", 3.0, 1.0, 2.0, 2.2, z=0.0, anstieg=0.6, stufen=4)   # deckt x 2..4, y -0.1..2.1
    mit = _mit_gelaende(sprung, boeden=(treppe,))
    # Die senkrechte Klippe des Gelaendes bei x = 2.9 (Sprung 0 -> 0.6) faellt unter der
    # Treppe weg; die Kanten der Treppe selbst (waagrecht, an ihren Seiten) bleiben.
    def senkrecht_bei_29(klippen_):
        return [k for k in klippen_ if abs(k[0] - k[2]) < 1e-9 and abs(k[0] - 2.9) < 1e-6]

    assert senkrecht_bei_29(h.klippen(ohne))
    assert not senkrecht_bei_29(h.klippen(mit))
