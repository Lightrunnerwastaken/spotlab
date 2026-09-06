"""Bearbeitung eines Raums -- reine Funktionen, ohne Qt (Tasks 6-8 des Raumeditors)."""
import pytest

from spotlab.welt import bearbeitung as b
from spotlab.welt.raum import Block, Raum, RaumTag

RAUM = Raum(
    name="T", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 4, 0), (4, 0, 4, 3)),
    bloecke=(Block("Kiste", 2.0, 2.0, 1.0, 0.5),),
    tags=(RaumTag(1, 3.5, 1.5, 180.0),),
)


# ---------------------------------------------------------- Operationen


def test_lage_und_mitte():
    assert b.lage(RAUM, ("wand", 0)) == (2.0, 0.0)
    assert b.lage(RAUM, ("block", 0)) == (2.0, 2.0)
    assert b.lage(RAUM, ("tag", 0)) == (3.5, 1.5)
    assert b.lage(RAUM, ("start",)) == (1.0, 1.0)
    assert b.mitte(RAUM, frozenset({("wand", 0), ("block", 0)})) == (2.0, 1.0)


def test_verschieben_trifft_nur_die_auswahl():
    neu = b.verschiebe(RAUM, frozenset({("block", 0), ("start",)}), 1.0, -0.5)
    assert (neu.bloecke[0].x, neu.bloecke[0].y) == (3.0, 1.5)
    assert neu.start == (2.0, 0.5, 0.0)
    assert neu.waende == RAUM.waende and neu.tags == RAUM.tags


def test_eine_wand_dreht_um_ihre_mitte():
    neu = b.drehe(RAUM, frozenset({("wand", 0)}), 90.0)
    wand = neu.waende[0]
    assert (wand.x1, wand.y1) == (pytest.approx(2.0), pytest.approx(-2.0))
    assert (wand.x2, wand.y2) == (pytest.approx(2.0), pytest.approx(2.0))


def test_ein_block_dreht_um_einen_fremden_punkt_und_sich_selbst():
    neu = b.drehe(RAUM, frozenset({("block", 0)}), 90.0, um=(0.0, 0.0))
    kiste = neu.bloecke[0]
    assert (kiste.x, kiste.y) == (pytest.approx(-2.0), pytest.approx(2.0))
    assert kiste.drehung == 90.0


def test_tag_und_start_drehen_lage_und_blick():
    neu = b.drehe(RAUM, frozenset({("tag", 0), ("start",)}), 180.0, um=(2.0, 1.0))
    assert neu.tags[0].grad == pytest.approx(0.0)
    assert (neu.tags[0].x, neu.tags[0].y) == (pytest.approx(0.5), pytest.approx(0.5))
    assert neu.start[2] == pytest.approx(180.0)


def test_skalieren_mit_achse():
    neu = b.skaliere(RAUM, frozenset({("block", 0)}), 2.0, 1.0, 3.0, um=(2.0, 2.0))
    kiste = neu.bloecke[0]
    assert (kiste.breite, kiste.tiefe, kiste.hoehe) == (2.0, 0.5, 2.25)
    neu = b.skaliere(RAUM, frozenset({("wand", 0)}), 0.5, 0.5, 1.0, um=(0.0, 0.0))
    assert list(neu.waende[0]) == [0.0, 0.0, 2.0, 0.0]


def test_skalieren_haelt_die_mindestkante():
    neu = b.skaliere(RAUM, frozenset({("block", 0)}), 0.001, 0.001, 0.001)
    kiste = neu.bloecke[0]
    assert kiste.breite == kiste.tiefe == kiste.hoehe == b.MINDESTKANTE_M


def test_duplizieren_haengt_kopien_an_und_waehlt_sie():
    neu, auswahl = b.dupliziere(RAUM, frozenset({("block", 0), ("wand", 1)}))
    assert len(neu.bloecke) == 2 and len(neu.waende) == 3
    assert auswahl == frozenset({("block", 1), ("wand", 2)})
    assert (neu.bloecke[1].x, neu.bloecke[1].y) == (2.5, 2.5)
    assert neu.bloecke[1].name == "Kiste Kopie"
    assert list(neu.waende[2]) == [4.5, 0.5, 4.5, 3.5]


def test_loeschen_entfernt_und_leert_die_auswahl():
    neu, auswahl = b.loesche(RAUM, frozenset({("wand", 0), ("tag", 0), ("start",)}))
    assert len(neu.waende) == 1 and list(neu.waende[0]) == [4, 0, 4, 3]
    assert neu.tags == () and neu.start == RAUM.start        # der Start bleibt
    assert auswahl == frozenset()


def test_neue_elemente_bekommen_freie_namen_und_nummern():
    neu, s = b.neue_wand(RAUM, 0, 3, 4, 3)
    assert s == ("wand", 2) and list(neu.waende[2]) == [0, 3, 4, 3]
    neu, s = b.neuer_block(neu, 1.0, 1.0, 0.5, 0.5)
    assert s == ("block", 1) and neu.bloecke[1].name == "Block 1"
    assert neu.bloecke[1].hoehe == 0.75
    neu, s = b.neuer_tag(neu, 0.5, 0.5)
    assert s == ("tag", 1) and neu.tags[1].id == 2                # 1 ist belegt
    neu = b.setze_start(neu, 3.0, 2.0, 45.0)
    assert neu.start == (3.0, 2.0, 45.0)


def test_setze_feld_je_art():
    neu = b.setze_feld(RAUM, ("block", 0), "drehung", 30.0)
    assert neu.bloecke[0].drehung == 30.0
    neu = b.setze_feld(neu, ("block", 0), "name", "Regal")
    assert neu.bloecke[0].name == "Regal"
    neu = b.setze_feld(neu, ("wand", 0), "x2", 5.0)
    assert neu.waende[0].x2 == 5.0
    neu = b.setze_feld(neu, ("tag", 0), "hoehe", 0.5)
    assert neu.tags[0].hoehe == 0.5
    neu = b.setze_feld(neu, ("start",), "grad", 90.0)
    assert neu.start[2] == 90.0
    neu = b.setze_feld(neu, ("raum",), "wand_dicke", 0.1)
    assert neu.wand_dicke == 0.1
    assert b.setze_feld(neu, ("block", 0), "breite", 0.0).bloecke[0].breite == b.MINDESTKANTE_M
    with pytest.raises(ValueError):
        b.setze_feld(neu, ("block", 0), "farbe", 1)
    assert b.FELDER["block"] == ("name", "x", "y", "breite", "tiefe", "hoehe", "drehung")


# ------------------------------------------- Rasten, Fang, Treffer, Griffe


def test_rasten():
    assert b.raste(1.234) == pytest.approx(1.25)
    assert b.raste(37.0, b.RASTER_GRAD) == 35.0


def test_wandenden_fangen_sich():
    assert b.fange_ende(RAUM, 4.05, 0.08) == (4.0, 0.0)
    assert b.fange_ende(RAUM, 4.05, 0.08, ausser=("wand", 0)) == (4.0, 0.0)
    assert b.fange_ende(RAUM, 2.0, 2.0) == (2.0, 2.0)


def test_treffer_mit_vorrang():
    assert b.treffer(RAUM, 2.0, 0.02) == ("wand", 0)
    assert b.treffer(RAUM, 2.1, 2.1) == ("block", 0)
    assert b.treffer(RAUM, 3.55, 1.5) == ("tag", 0)
    assert b.treffer(RAUM, 1.05, 1.0) == ("start",)
    assert b.treffer(RAUM, 2.0, 1.0) is None
    raum = Raum(name="T", beschreibung="", start=(9, 9, 0),
                bloecke=(Block("K", 2, 2, 2, 2),), tags=(RaumTag(1, 2, 2, 0),))
    assert b.treffer(raum, 2.0, 2.0) == ("tag", 0)          # das Kleinere liegt oben


def test_rahmenauswahl_nimmt_die_mitten():
    assert b.im_rahmen(RAUM, 1.5, -0.5, 2.5, 2.5) == frozenset({("wand", 0), ("block", 0)})
    assert b.im_rahmen(RAUM, 0, 0, 5, 5) == frozenset(
        {("wand", 0), ("wand", 1), ("block", 0), ("tag", 0), ("start",)})


def test_griffe_je_art():
    griffe = b.griffe(RAUM, frozenset({("wand", 0), ("block", 0), ("tag", 0), ("start",)}))
    arten = {(s, art): (x, y) for s, art, x, y in griffe}
    assert arten[(("wand", 0), "ende_a")] == (0.0, 0.0)
    assert arten[(("wand", 0), "ende_b")] == (4.0, 0.0)
    assert arten[(("block", 0), "ecke0")] == (pytest.approx(1.5), pytest.approx(1.75))
    assert arten[(("block", 0), "drehring")] == (
        pytest.approx(2.5 + b.RING_ABSTAND_M), pytest.approx(2.0))
    assert arten[(("tag", 0), "richtung")] == (pytest.approx(3.5 - b.PFEIL_M), pytest.approx(1.5))
    assert arten[(("start",), "richtung")] == (pytest.approx(1.0 + b.PFEIL_M), pytest.approx(1.0))


def test_eine_ecke_ziehen_laesst_die_gegenecke_stehen():
    neu = b.ziehe_ecke(RAUM, ("block", 0), 2, 3.0, 3.0)      # Ecke 2 = rechts oben
    kiste = neu.bloecke[0]
    assert kiste.ecken()[0] == (pytest.approx(1.5), pytest.approx(1.75))
    assert (kiste.breite, kiste.tiefe) == (pytest.approx(1.5), pytest.approx(1.25))
    assert (kiste.x, kiste.y) == (pytest.approx(2.25), pytest.approx(2.375))


def test_pruefe_nennt_die_probleme():
    raum = Raum(name="P", beschreibung="", start=(2.0, 2.0, 0.0),
                waende=((0, 0, 0, 0),),
                bloecke=(Block("Kiste", 2, 2, 1, 1), Block("Nadel", 5, 5, 0.01, 1)),
                tags=(RaumTag(1, 2, 2, 0), RaumTag(1, 8, 8, 0)))
    hinweise = b.pruefe(raum)
    assert any("Start" in h and "Kiste" in h for h in hinweise)
    assert any("Wand 1" in h for h in hinweise)
    assert any("Nadel" in h for h in hinweise)
    assert any("Tag 1" in h and "doppelt" in h for h in hinweise)
    assert any("Tag 1" in h and "Kiste" in h for h in hinweise)
    assert b.pruefe(RAUM) == []


# ------------------------------------------------------- Verlauf, Modus


def test_verlauf_merkt_geht_zurueck_und_vor():
    v = b.Verlauf(grenze=3)
    r1 = RAUM
    r2 = b.verschiebe(r1, frozenset({("start",)}), 1, 0)
    r3 = b.verschiebe(r2, frozenset({("start",)}), 1, 0)
    v.merke(r1)
    v.merke(r2)
    v.merke(r3)
    assert v.aktuell is r3 and v.kann_zurueck and not v.kann_vor
    assert v.zurueck() is r2 and v.zurueck() is r1 and v.zurueck() is None
    assert v.vor() is r2
    v.merke(RAUM)                       # verwirft r3
    assert not v.kann_vor and v.zurueck() is r2
    for _ in range(5):
        v.merke(RAUM)
    assert len(v._schnappschuesse) == 3


def _tasten(modus, folge):
    for name in folge.split():
        modus.taste(name)


def test_g_x_zahl_enter_bewegt_genau():
    m = b.Modus()
    m.beginne(b.Modus.BEWEGEN, RAUM, frozenset({("block", 0)}), zeiger=(2.0, 2.0))
    assert m.aktiv and m.art == b.Modus.BEWEGEN
    _tasten(m, "x 1 . 5")
    assert m.achse == "x" and m.zahl == "1.5"
    assert (m.vorschau().bloecke[0].x, m.vorschau().bloecke[0].y) == (3.5, 2.0)
    fertig = m.bestaetige()
    assert not m.aktiv and fertig.bloecke[0].x == 3.5


def test_bewegen_folgt_dem_zeiger_gerastet_und_frei():
    m = b.Modus()
    m.beginne(b.Modus.BEWEGEN, RAUM, frozenset({("block", 0)}), zeiger=(2.0, 2.0))
    m.zeiger(2.33, 2.08)
    assert (m.vorschau().bloecke[0].x, m.vorschau().bloecke[0].y) == (
        pytest.approx(2.35), pytest.approx(2.1))
    m.zeiger(2.33, 2.08, frei=True)
    assert m.vorschau().bloecke[0].x == pytest.approx(2.33)
    m.taste("y")                                            # Achssperre: nur y
    assert m.vorschau().bloecke[0].x == 2.0
    m.taste("y")                                            # zweite Achstaste hebt auf
    assert m.achse is None
    assert m.abbruch() is RAUM and not m.aktiv


def test_r_zahl_dreht_um_die_mitte_der_auswahl():
    m = b.Modus()
    m.beginne(b.Modus.DREHEN, RAUM, frozenset({("wand", 0)}), zeiger=(3.0, 0.0))
    _tasten(m, "9 0")
    wand = m.vorschau().waende[0]
    assert (wand.x1, wand.y1) == (pytest.approx(2.0), pytest.approx(-2.0))
    m.taste("Backspace")
    m.taste("Backspace")
    m.zeiger(2.0, 1.0)                                      # 90 Grad vom Startzeiger aus
    assert m.vorschau().waende[0].y2 == pytest.approx(2.0)


def test_s_z_zahl_skaliert_die_hoehe():
    m = b.Modus()
    m.beginne(b.Modus.SKALIEREN, RAUM, frozenset({("block", 0)}), zeiger=(3.0, 2.0))
    _tasten(m, "z 2")
    kiste = m.vorschau().bloecke[0]
    assert (kiste.breite, kiste.tiefe, kiste.hoehe) == (1.0, 0.5, 1.5)
    m2 = b.Modus()
    m2.beginne(b.Modus.SKALIEREN, RAUM, frozenset({("block", 0)}), zeiger=(3.0, 2.0))
    m2.zeiger(4.0, 2.0)                                     # doppelter Abstand zur Mitte
    assert m2.vorschau().bloecke[0].breite == pytest.approx(2.0)
    assert m2.vorschau().bloecke[0].tiefe == pytest.approx(1.0)


def test_ohne_auswahl_beginnt_kein_modus():
    m = b.Modus()
    m.beginne(b.Modus.BEWEGEN, RAUM, frozenset(), zeiger=(0.0, 0.0))
    assert not m.aktiv and m.taste("x") is False
