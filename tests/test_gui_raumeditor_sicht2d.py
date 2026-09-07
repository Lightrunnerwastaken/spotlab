"""Die 2D-Sicht des Raumeditors: Umrechnung, Ereignisse in Metern, Zeichnen."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from spotlab.gui.raumeditor.sicht2d import Sicht2D  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import Block, Raum  # noqa: E402

RAUM = Raum(name="T", beschreibung="", start=(1, 1, 0), waende=((0, 0, 4, 0),),
            bloecke=(Block("K", 2, 2, 1, 1),))


def _sicht():
    sicht = Sicht2D(DUNKEL)
    sicht.resize(400, 300)
    sicht.zeige(RAUM, griffe=[(("block", 0), "ecke0", 1.5, 1.5)], rahmen=(0, 0, 1, 1), kette=(0, 0))
    sicht.alles_zeigen()
    return sicht


def test_umrechnung_ist_umkehrbar_und_y_zeigt_nach_oben(qapp):
    sicht = _sicht()
    px, py = sicht.meter_zu_schirm(2.0, 1.0)
    assert sicht.schirm_zu_meter(px, py) == (pytest.approx(2.0), pytest.approx(1.0))
    assert sicht.meter_zu_schirm(2.0, 2.0)[1] < py


def test_klick_kommt_in_metern_mit_umschalttasten(qapp):
    sicht = _sicht()
    empfangen = []
    sicht.gedrueckt.connect(lambda *a: empfangen.append(a))
    sicht.losgelassen.connect(lambda *a: empfangen.append(("los", *a)))
    px, py = sicht.meter_zu_schirm(2.0, 2.0)
    QTest.mouseClick(sicht, Qt.LeftButton, Qt.ShiftModifier, QPoint(int(px), int(py)))
    x, y, taste, shift, ctrl = empfangen[0]
    assert (x, y) == (pytest.approx(2.0, abs=0.02), pytest.approx(2.0, abs=0.02))
    assert taste == "links" and shift and not ctrl
    assert empfangen[1][0] == "los"


def test_tasten_kommen_als_namen(qapp):
    sicht = _sicht()
    empfangen = []
    sicht.taste_gedrueckt.connect(lambda *a: empfangen.append(a))
    QTest.keyClick(sicht, Qt.Key_G)
    QTest.keyClick(sicht, Qt.Key_Z, Qt.ControlModifier)
    QTest.keyClick(sicht, Qt.Key_Return)
    QTest.keyClick(sicht, Qt.Key_Period)
    assert empfangen == [("g", False, False, False), ("z", False, True, False),
                         ("return", False, False, False), (".", False, False, False)]


def test_rad_zoomt_und_home_zeigt_alles(qapp):
    sicht = _sicht()
    vorher = sicht.skala
    sicht.zoome(1.5, sicht.width() / 2, sicht.height() / 2)
    assert sicht.skala == pytest.approx(vorher * 1.5)
    QTest.keyClick(sicht, Qt.Key_Home)
    assert sicht.skala == pytest.approx(vorher)


def test_zeichnen_mit_allem_stuerzt_nicht(qapp):
    sicht = _sicht()
    sicht.setze_spur([(1, 1), (2, 1)])
    sicht.setze_anstoesse([(2.5, 1.0)])
    sicht.setze_pauspapier([(0.1 * i, 0.2) for i in range(50)])
    sicht.grab()          # rendert offscreen
    assert sicht.toleranz_m() > 0


def test_ebene_und_klippen_zeichnen_stuerzt_nicht(qapp):
    sicht = _sicht()
    sicht.zeige(RAUM, ebene=1.2, klippen_=[(0.0, 0.0, 1.0, 0.0)])
    sicht.grab()


def test_das_gelaende_wird_gezeichnet_und_einmal_je_raum_gerendert(qapp):
    from spotlab.welt import gelaende as g

    ge = g.gitter(0.0, 0.0, 0.5, 5, 9, lambda x, y: 0.2 * x)
    raum = Raum(name="G", beschreibung="", start=(1, 1, 0), gelaende=ge)
    sicht = Sicht2D(DUNKEL)
    sicht.resize(400, 300)
    sicht.zeige(raum)
    sicht.alles_zeigen()
    bild = sicht.grab().toImage()
    px, py = sicht.meter_zu_schirm(2.25, 1.25)
    assert bild.pixelColor(int(px), int(py)).name() != DUNKEL.hintergrund
    schluessel = sicht._gelaende_schluessel
    sicht.grab()
    assert sicht._gelaende_schluessel == schluessel          # nicht neu gerechnet
    sicht.zeige(raum, ebene=0.0)
    sicht.grab()
    assert sicht._gelaende_schluessel != schluessel          # die Ebene aendert das Bild


def test_markierung_kandidaten_und_offene_raender_zeichnen(qapp):
    sicht = _sicht()
    sicht.setze_kandidaten([(0, 0, 1, 1), (1, 0, 2, 0)])
    sicht.setze_markierung([(0, 0, 1, 1)])
    sicht.setze_offen([(0.5, 0.5)])
    sicht.grab()
    assert sicht._markierung == [(0, 0, 1, 1)] and sicht._offen == [(0.5, 0.5)]
    assert len(sicht._kandidaten) == 2
