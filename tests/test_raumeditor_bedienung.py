"""Bedienung des Raumeditors (UX-Pruefung vom 23.09.2026): was der Editor sagt,
zeigt und wo seine Tasten wirken.

Der Text der Zustandszeile, die gesperrte Achse, die Hervorhebung und der
Mauszeiger kommen aus der Steuerung -- ohne Fenster pruefbar. Die Qt-Tests
pruefen nur die Haut: Knoepfe, Kuerzel, Felder, Groessen.
"""
import pytest

from spotlab.gui.raumeditor.steuerung import Steuerung
from spotlab.welt import bearbeitung as b
from spotlab.welt.raum import Block, Raum, RaumTag

RAUM = Raum(
    name="T", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 4, 0), (4, 0, 4, 3)),
    bloecke=(Block("Kiste", 2.0, 2.0, 1.0, 0.5),),
    tags=(RaumTag(1, 3.5, 1.5, 180.0),),
)


# ------------------------------------------------------------- Zustandszeile


def test_die_zustandszeile_nennt_werkzeug_zeiger_und_raster():
    st = Steuerung(RAUM)
    st.bewege(1.234, 2.5)
    text = st.beschreibung()
    assert text.startswith("Auswählen")
    assert "x 1.23 m  y 2.50 m" in text and "Raster 5 cm (Strg: frei)" in text
    st.auswahl = frozenset({("block", 0)})
    assert "1 gewählt" in st.beschreibung() and "Entf löscht" in st.beschreibung()


def test_die_zustandszeile_zeigt_die_geste_mit_achse_und_getippter_zahl():
    st = Steuerung(RAUM)
    st.auswahl = frozenset({("block", 0)})
    st.zeiger = (2.0, 2.0)
    st.taste("g")
    st.bewege(2.5, 2.2)
    text = st.beschreibung()
    assert text.startswith("G bewegen") and "Δx +0.50 m  Δy +0.20 m" in text
    assert "Enter bestätigt · Esc bricht ab" in text
    st.taste("x")
    st.taste("1")
    st.taste(".")
    st.taste("5")
    text = st.beschreibung()
    assert "nur X" in text and "getippt 1.5 m" in text
    st.taste("escape")
    st.taste("r")
    for t in "30":
        st.taste(t)
    assert "R drehen" in st.beschreibung() and "getippt 30°" in st.beschreibung()
    st.taste("escape")
    st.taste("s")
    st.taste("2")
    assert "S skalieren" in st.beschreibung() and "getippt ×2" in st.beschreibung()


def test_die_zustandszeile_zeigt_laenge_und_winkel_der_naechsten_wand():
    st = Steuerung(RAUM)
    st.setze_werkzeug("wand")
    assert "Klick setzt den ersten Punkt" in st.beschreibung()
    st.druecke(0.0, 3.0)
    st.lasse_los(0.0, 3.0)
    st.bewege(3.0, 7.0)
    text = st.beschreibung()
    assert text.startswith("Wand") and "Länge 5.00 m · Winkel 53°" in text
    assert "Esc beendet" in text


def test_die_zustandszeile_zeigt_die_groesse_beim_aufziehen():
    st = Steuerung(RAUM)
    st.setze_werkzeug("block")
    st.druecke(0.5, 0.5)
    st.bewege(1.5, 1.0)
    assert "Block" in st.beschreibung() and "1.00 × 0.50 m" in st.beschreibung()


def test_die_gesperrte_achse_ist_eine_linie_durch_die_mitte():
    st = Steuerung(RAUM)
    st.auswahl = frozenset({("block", 0)})
    st.taste("g")
    assert st.achslinie() is None
    st.taste("x")
    assert st.achslinie() == ("x", (2.0, 2.0))
    st.taste("z")
    assert st.achslinie() is None                           # Hoehe: keine Linie in 2D
    st.taste("escape")
    st.taste("r")
    st.taste("x")
    assert st.achslinie() is None                           # Drehen kennt keine Achse


# ------------------------------------------------ Hervorhebung und Zeiger


def test_ueberfahren_hebt_hervor_und_waehlt_den_zeiger():
    st = Steuerung(RAUM)
    st.bewege(2.0, 2.0)
    assert st.ueber == ("block", 0) and st.zeigerart() == "element"
    st.bewege(1.0, 2.8)
    assert st.ueber is None and st.zeigerart() is None
    st.auswahl = frozenset({("block", 0)})
    ecke = next(g for g in st.griffe() if g[1] == "ecke0")
    st.bewege(ecke[2], ecke[3])
    assert st.ueber_griff and st.zeigerart() == "bewegen"
    st.setze_werkzeug("wand")
    st.bewege(2.0, 2.0)
    assert st.ueber is None and st.zeigerart() == "zeichnen"


def test_f_rahmt_die_auswahl():
    st = Steuerung(RAUM)
    assert st.auswahl_huelle() is None
    st.auswahl = frozenset({("block", 0), ("wand", 0)})
    x0, y0, x1, y1 = st.auswahl_huelle()
    assert x0 < 0.0 and y0 < 0.0 and x1 > 4.0 and 2.25 < y1 < 3.0


# -------------------------------------------------------------------- Hinweise


def test_gleiche_befunde_haben_eine_gruppe_und_ihr_element():
    raum = Raum(name="H", beschreibung="", start=(2.0, 2.0, 0.0),
                waende=((0, 0, 0, 0), (1, 1, 1, 1), (0, 0, 4, 0)))
    befunde = b.befunde(raum)
    assert [f.schluessel for f in befunde] == [("wand", 0), ("wand", 1)]
    assert {f.gruppe for f in befunde} == {"Wände ohne Länge"}
    assert [f.text for f in befunde] == b.pruefe(raum) == ["Wand 1 hat keine Länge.",
                                                          "Wand 2 hat keine Länge."]
    im_tisch = b.befunde(Raum(name="S", beschreibung="", start=(2.0, 2.0, 0.0),
                              bloecke=(Block("Tisch", 2.0, 2.0, 1.0, 1.0),)))
    assert im_tisch[0].schluessel == b.START and im_tisch[0].gruppe is None
    assert im_tisch[0].text.startswith("Der Start steht")


# ---------------------------------------------------------------- Aufbau (Qt)


@pytest.fixture
def tab(qapp):
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    ansicht = RaumeditorView(DUNKEL)
    yield ansicht
    ansicht.close()


def _leer():
    from spotlab.welt.raum import raum_laden

    return raum_laden("leer")


