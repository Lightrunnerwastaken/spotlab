"""Das gemeinsame Zeichnen von Raeumen -- fuer Raumeditor und Uebungsfenster."""
import ast
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QImage, QPainter  # noqa: E402

from spotlab.gui.raumzeichnung import wand_polygon, zeichne_raum, zeichne_spot, zeichne_spur  # noqa: E402
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
