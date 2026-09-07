"""Das gemeinsame Zeichnen von Raeumen -- fuer Raumeditor und Uebungsfenster."""
import ast
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QImage, QPainter  # noqa: E402

from spotlab.gui.raumzeichnung import (  # noqa: E402
    wand_polygon,
    zeichne_raum,
    zeichne_spot,
    zeichne_spur,
)
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import Block, Raum, RaumTag, Wand  # noqa: E402


def test_das_wandpolygon_hat_die_dicke():
    ecken = wand_polygon(Wand(0.0, 0.0, 4.0, 0.0), 0.2)
    ys = sorted(round(y, 6) for _x, y in ecken)
    assert ys == [-0.1, -0.1, 0.1, 0.1]
    assert sorted(round(x, 6) for x, _y in ecken) == [0.0, 0.0, 4.0, 4.0]


def test_zeichnen_mit_allem_und_auswahl_stuerzt_nicht(qapp):
    raum = Raum(name="T", beschreibung="", start=(1.0, 1.0, 30.0),
                waende=((0, 0, 5, 0), (5, 0, 5, 4)),
                bloecke=(Block("Regal", 2.0, 2.0, 1.0, 0.4, drehung=30.0),),
                tags=(RaumTag(1, 4.5, 2.0, 180.0),))
    bild = QImage(400, 300, QImage.Format_RGB32)
    bild.fill(0)
    maler = QPainter(bild)
    skala = 50.0
    zeichne_raum(maler, raum, lambda x, y: (20 + x * skala, 280 - y * skala), skala, DUNKEL,
                 auswahl=frozenset({("block", 0), ("wand", 1)}))
    zeichne_spur(maler, [(1, 1), (2, 1.5)], lambda x, y: (20 + x * skala, 280 - y * skala), DUNKEL)
    zeichne_spot(maler, 70.0, 230.0, 30.0, skala, DUNKEL)
    maler.end()
    assert bild.pixel(70 + 13, 230) != bild.pixel(1, 1)      # der Kreis ist gezeichnet


def test_kein_farbliteral():
    quelle = Path("src/spotlab/gui/raumzeichnung.py").read_text(encoding="utf-8")
    for knoten in ast.walk(ast.parse(quelle)):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            assert not knoten.value.startswith("#"), knoten.value


# ------------------------------------------------------------- Hoehe (Stufe 13)


def _bild_mit(raum, ebene=None, klippen_=(), skala=100.0):
    bild = QImage(800, 600, QImage.Format_RGB32)
    bild.fill(0)
    maler = QPainter(bild)
    zeichne_raum(maler, raum, lambda x, y: (20 + x * skala, 580 - y * skala), skala, DUNKEL,
                 ebene=ebene, klippen_=klippen_)
    maler.end()
    return bild, (lambda x, y: (int(20 + x * skala), int(580 - y * skala)))


def test_andere_ebenen_werden_blass_gezeichnet(qapp):
    from PySide6.QtGui import QColor

    from spotlab.welt.raum import Boden

    raum = Raum(name="T", beschreibung="", start=(1, 1, 0), waende=(Wand(0, 3, 5, 3),),
                boeden=(Boden("P", 3, 1, 2, 1, z=1.2),))
    bild, px = _bild_mit(raum, ebene=None)
    assert bild.pixelColor(*px(2.5, 3.0)) == QColor(DUNKEL.text)          # alle Ebenen: voll
    bild, px = _bild_mit(raum, ebene=1.2)
    assert bild.pixelColor(*px(2.5, 3.0)) == QColor(DUNKEL.blass)         # die Wand liegt bei 0
    bild, px = _bild_mit(raum, ebene=0.0)
    assert bild.pixelColor(*px(2.5, 3.0)) == QColor(DUNKEL.text)


def test_boeden_treppen_und_klippen_werden_gezeichnet(qapp):
    from PySide6.QtGui import QColor

    from spotlab.welt.hoehe import klippen
    from spotlab.welt.raum import Boden

    raum = Raum(name="T", beschreibung="", start=(1, 1, 0),
                boeden=(Boden("T", 3, 1, 2, 1, anstieg=1.0, stufen=5), Boden("P", 5, 1, 2, 3, z=1.0)))
    bild, px = _bild_mit(raum, klippen_=klippen(raum))
    assert bild.pixelColor(*px(5.0, 1.0)) != QColor(0, 0, 0)              # das Podest ist gefuellt
    assert bild.pixelColor(*px(2.4, 1.0)) != QColor(0, 0, 0)              # die Treppe auch


# ------------------------------------------------------------- Gelaende


def _gelaende(f):
    from spotlab.welt import gelaende as g
    return g.gitter(0.0, 0.0, 0.2, 4, 6, f)


def test_das_bild_hat_die_knotenmasse_und_zeile_0_oben():
    from PySide6.QtGui import QColor

    from spotlab.gui.raumzeichnung import gelaende_bild

    bild = gelaende_bild(_gelaende(lambda x, y: y), DUNKEL)        # steigt nach +y
    assert (bild.width(), bild.height()) == (6, 4)
    oben, unten = QColor(bild.pixel(0, 0)), QColor(bild.pixel(0, 3))
    assert oben.lightness() > unten.lightness()                    # hoch = heller, oben im Bild


def test_ohne_boden_durchsichtig_und_hoehenlinie_gedaempft():
    from PySide6.QtGui import QColor

    from spotlab.gui.raumzeichnung import gelaende_bild

    bild = gelaende_bild(_gelaende(lambda x, y: None if x < 0.3 else (0.0 if x < 0.7 else 0.3)), DUNKEL)
    assert bild.pixelColor(0, 0).alpha() == 0
    # Spalte 3 (x = 0.6, Hoehe 0.0) grenzt rechts an 0.3: floor(0/0.25) != floor(0.3/0.25)
    assert QColor(bild.pixel(3, 0)).name() == DUNKEL.gedaempft
    assert QColor(bild.pixel(2, 0)).name() != DUNKEL.gedaempft


def test_ausserhalb_der_ebene_blass():
    from PySide6.QtGui import QColor

    from spotlab.gui.raumzeichnung import gelaende_bild

    bild = gelaende_bild(_gelaende(lambda x, y: 0.0 if x < 0.5 else 1.0), DUNKEL, ebene=0.0)
    assert QColor(bild.pixel(5, 0)).name() == DUNKEL.blass
    assert QColor(bild.pixel(0, 0)).name() != DUNKEL.blass


def test_das_rechteck_reicht_eine_halbe_zelle_ueber_die_knoten():
    from spotlab.gui.raumzeichnung import gelaende_rechteck

    assert gelaende_rechteck(_gelaende(lambda x, y: 0.0)) == pytest.approx((-0.1, -0.1, 1.1, 0.7))


# ------------------------------------------------------------- Pauspapier


def test_das_pauspapier_wird_ein_bild_mit_punkten_und_durchsichtigem_rest():
    from spotlab.gui.raumzeichnung import pauspapier_bild

    bild, rechteck = pauspapier_bild([(1.0, 2.0), (3.0, 4.0)], DUNKEL, zelle=0.5)
    x0, y0, x1, y1 = rechteck
    assert x0 <= 1.0 and y0 <= 2.0 and x1 >= 3.0 and y1 >= 4.0
    assert bild.width() >= 5 and bild.height() >= 5
    # Der Punkt (1, 2) liegt links unten: Spalte 0 .. 1, Zeile unten (Bild zeigt y nach oben).
    getroffen = [(x, y) for x in range(bild.width()) for y in range(bild.height())
                 if bild.pixelColor(x, y).alpha() > 0]
    assert len(getroffen) == 2
    assert all(bild.pixelColor(x, y).name() == DUNKEL.gedaempft for x, y in getroffen)


def test_ein_leeres_pauspapier_gibt_kein_bild():
    from spotlab.gui.raumzeichnung import pauspapier_bild

    assert pauspapier_bild([], DUNKEL) == (None, None)
