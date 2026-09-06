"""Die Steuerung des Raumeditors -- Maus in Metern, Tasten als Namen, ohne Qt."""
import pytest

from spotlab.gui.raumeditor.steuerung import TOLERANZ_M, Steuerung
from spotlab.welt.raum import Block, Raum, RaumTag

RAUM = Raum(
    name="T", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 4, 0), (4, 0, 4, 3)),
    bloecke=(Block("Kiste", 2.0, 2.0, 1.0, 0.5),),
    tags=(RaumTag(1, 3.5, 1.5, 180.0),),
)


def klick(st, x, y, **k):
    st.druecke(x, y, **k)
    st.lasse_los(x, y, shift=k.get("shift", False))


def test_klick_waehlt_und_shift_ergaenzt():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    assert st.auswahl == {("block", 0)}
    klick(st, 2.0, 0.0, shift=True)
    assert st.auswahl == {("block", 0), ("wand", 0)}
    klick(st, 2.0, 0.0, shift=True)                       # nochmal: abwaehlen
    assert st.auswahl == {("block", 0)}
    klick(st, 2.0, 1.0)                                   # ins Leere
    assert st.auswahl == frozenset() and not st.geaendert


def test_ziehen_verschiebt_gerastet_und_merkt_sich_das():
    st = Steuerung(RAUM)
    st.druecke(2.0, 2.0)
    st.bewege(2.52, 2.03)
    assert (st.raum.bloecke[0].x, st.raum.bloecke[0].y) == (pytest.approx(2.5), pytest.approx(2.05))
    st.lasse_los(2.52, 2.03)
    assert st.geaendert and st.verlauf.kann_zurueck
    assert st.rueckgaengig() and st.raum.bloecke[0].x == 2.0


def test_rahmen_waehlt_mehrere():
    st = Steuerung(RAUM)
    st.druecke(1.5, -0.5)
    st.bewege(2.5, 2.5)
    assert st.rahmen == (1.5, -0.5, 2.5, 2.5)
    st.lasse_los(2.5, 2.5)
    assert st.auswahl == {("wand", 0), ("block", 0)} and st.rahmen is None


def test_wandwerkzeug_zeichnet_eine_kette_mit_fang():
    st = Steuerung(RAUM)
    st.setze_werkzeug("wand")
    klick(st, 4.04, 3.03)                                 # faengt (4, 3)
    assert st.kette == (4.0, 3.0) and len(st.raum.waende) == 2
    klick(st, 0.02, 3.01)
    assert len(st.raum.waende) == 3 and list(st.raum.waende[2]) == [4.0, 3.0, 0.0, 3.0]
    assert st.auswahl == {("wand", 2)} and st.kette == (0.0, 3.0)
    st.taste("escape")
    assert st.kette is None
    klick(st, 1.0, 1.0)
    st.druecke(1.0, 1.0, taste="rechts")                  # rechts beendet auch
    assert st.kette is None


def test_blockwerkzeug_zieht_ein_rechteck():
    st = Steuerung(RAUM)
    st.setze_werkzeug("block")
    st.druecke(0.5, 1.5)
    st.bewege(1.52, 2.48)                                 # rastet auf (1.5, 2.5)
    st.lasse_los(1.52, 2.48)
    kiste = st.raum.bloecke[1]
    assert kiste.name == "Block 1"
    assert (kiste.x, kiste.y, kiste.breite, kiste.tiefe) == (
        pytest.approx(1.0), pytest.approx(2.0), pytest.approx(1.0), pytest.approx(1.0))
    assert st.auswahl == {("block", 1)}


def test_tag_und_start_werkzeug():
    st = Steuerung(RAUM)
    st.setze_werkzeug("tag")
    klick(st, 0.5, 0.5)
    assert st.raum.tags[1].id == 2 and st.auswahl == {("tag", 1)}
    st.setze_werkzeug("start")
    st.druecke(3.0, 2.0)
    st.bewege(3.0, 2.5)                                   # nach oben ziehen: Blick 90 Grad
    st.lasse_los(3.0, 2.5)
    assert st.raum.start == (3.0, 2.0, 90.0) and st.geaendert


def test_griffe_ziehen_ende_ecke_ring_und_richtung():
    st = Steuerung(RAUM)
    klick(st, 2.0, 0.0)                                   # Wand 0
    st.druecke(4.0, 0.0)                                  # Griff ende_b
    st.bewege(4.5, 0.02)
    st.lasse_los(4.5, 0.02)
    assert list(st.raum.waende[0]) == [0.0, 0.0, 4.5, 0.0]
    klick(st, 2.0, 2.0)                                   # Kiste
    st.druecke(2.5, 2.25)                                 # Ecke 2
    st.bewege(3.0, 3.0)
    st.lasse_los(3.0, 3.0)
    assert (st.raum.bloecke[0].breite, st.raum.bloecke[0].tiefe) == (
        pytest.approx(1.5), pytest.approx(1.25))
    klick(st, st.raum.bloecke[0].x, st.raum.bloecke[0].y)
    ring = next(g for g in st.griffe() if g[1] == "drehring")
    st.druecke(ring[2], ring[3])
    st.bewege(st.raum.bloecke[0].x, st.raum.bloecke[0].y + 2.0)
    st.lasse_los(st.raum.bloecke[0].x, st.raum.bloecke[0].y + 2.0)
    assert st.raum.bloecke[0].drehung == 90.0
    klick(st, 1.0, 1.0)                                   # Start
    st.druecke(1.4, 1.0)                                  # Richtungsgriff
    st.bewege(1.0, 1.6)
    st.lasse_los(1.0, 1.6)
    assert st.raum.start[2] == 90.0


def test_tasten_g_x_zahl_enter_und_rueckgaengig():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    assert st.taste("g") and st.modus.aktiv
    for name in "x 1 . 5".split():
        assert st.taste(name)
    assert st.raum.bloecke[0].x == 2.0                    # Vorschau erst nach bewege()
    st.bewege(2.0, 2.0)
    assert st.raum.bloecke[0].x == 3.5
    assert st.taste("return") and not st.modus.aktiv and st.raum.bloecke[0].x == 3.5
    assert st.taste("z", ctrl=True) and st.raum.bloecke[0].x == 2.0
    assert st.taste("y", ctrl=True) and st.raum.bloecke[0].x == 3.5


def test_modus_abbruch_klick_und_escape():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    st.taste("g")
    st.bewege(3.0, 2.0)
    st.taste("escape")
    assert st.raum.bloecke[0].x == 2.0 and not st.geaendert
    st.taste("r")
    st.bewege(2.0, 3.0)
    st.druecke(2.0, 3.0)                                  # Linksklick bestaetigt
    assert not st.modus.aktiv and st.raum.bloecke[0].drehung == 90.0 and st.geaendert


def test_loeschen_duplizieren_alles():
    st = Steuerung(RAUM)
    assert st.taste("a") and st.auswahl == st.alle() and len(st.auswahl) == 5
    assert st.taste("a", alt=True) and st.auswahl == frozenset()
    klick(st, 2.0, 2.0)
    assert st.taste("d", shift=True)
    assert len(st.raum.bloecke) == 2 and st.auswahl == {("block", 1)} and st.modus.aktiv
    st.taste("escape")
    assert st.taste("delete") and len(st.raum.bloecke) == 1 and st.auswahl == frozenset()


def test_setze_feld_und_hinweise():
    st = Steuerung(RAUM)
    st.setze_feld(("start",), "x", 2.0)
    st.setze_feld(("start",), "y", 2.0)
    assert any("Start" in h for h in st.hinweise()) and st.geaendert
    with pytest.raises(ValueError):
        st.setze_feld(("block", 0), "farbe", 1)


def test_setze_raum_setzt_alles_zurueck():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    st.taste("delete")
    st.setze_raum(RAUM)
    assert st.raum is RAUM and st.auswahl == frozenset() and not st.geaendert
    assert not st.verlauf.kann_zurueck
    assert TOLERANZ_M == 0.12


def test_ein_uebergebener_treffer_geht_vor_dem_bodenpunkt():
    """Aus 3D: der Farb-ID-Treffer nennt den Block, obwohl der Bodenpunkt dahinter liegt."""
    st = Steuerung(RAUM)
    st.druecke(3.9, 2.9, treffer=("block", 0))
    st.lasse_los(3.9, 2.9)
    assert st.auswahl == {("block", 0)}


# ---------------------------------------------------------------- Hoehe (Stufe 13)


def test_werkzeug_boden_zieht_ein_rechteck_auf_der_ebene():
    st = Steuerung(RAUM)
    st.setze_ebene(1.2)
    st.setze_werkzeug("boden")
    st.druecke(1.0, 1.0)
    st.bewege(3.0, 2.0)
    st.lasse_los(3.0, 2.0)
    boden = st.raum.boeden[0]
    assert (boden.x, boden.y, boden.breite, boden.tiefe, boden.z) == (2.0, 1.5, 2.0, 1.0, 1.2)
    assert st.auswahl == {("boden", 0)} and st.geaendert
    st.setze_werkzeug("block")
    st.druecke(1.0, 2.5)
    st.bewege(2.0, 3.0)
    st.lasse_los(2.0, 3.0)
    assert st.raum.bloecke[-1].z == 1.2
    st.setze_werkzeug("tag")
    klick(st, 3.5, 2.5)
    assert st.raum.tags[-1].z == 1.2
    st.setze_ebene(None)
    st.setze_werkzeug("block")
    st.druecke(0.5, 2.5)
    st.bewege(0.9, 2.9)
    st.lasse_los(0.9, 2.9)
    assert st.raum.bloecke[-1].z == 0.0


def test_g_dann_z_hebt_die_auswahl():
    st = Steuerung(RAUM)
    st.auswahl = frozenset({("block", 0)})
    st.zeiger = (2.0, 2.0)
    assert st.taste("g") and st.taste("z")
    st.bewege(2.0, 2.5)                                    # nach oben auf dem Schirm = hoeher
    assert st.modus.vorschau().bloecke[0].z == 0.5
    assert st.modus.vorschau().bloecke[0].x == 2.0         # in der Ebene rührt sich nichts
    st.taste("return")
    assert st.raum.bloecke[0].z == 0.5 and st.geaendert


def test_hinweise_nennen_die_kante_und_alle_kennt_boeden():
    from spotlab.welt.raum import Boden, Raum

    raum = Raum(name="H", beschreibung="", start=(2.9, 0.0, 0.0), boeden=(Boden("P", 2, 0, 2, 2, z=1.0),))
    st = Steuerung(raum)
    assert any("Kante" in h for h in st.hinweise())
    assert ("boden", 0) in st.alle()
