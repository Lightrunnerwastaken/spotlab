"""Die Draufsicht der Steuerzentrale: zeichnen, verschieben, zoomen, Klick in Weltkoordinaten."""

import re
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from spotlab.backends.base import ObstacleGrid  # noqa: E402
from spotlab.gui import lagebild as lb  # noqa: E402
from spotlab.gui.theme import palette_fuer  # noqa: E402
from spotlab.workshop import skizze as sk  # noqa: E402


def _daten(spot=(2.0, 3.0, 0.0), **mehr):
    daten = {"t": 1.0, "rahmen": "vision", "zelle_m": 0.05, "ursprung": None, "breite": 0,
             "hoehe": 0, "spot": {"x": spot[0], "y": spot[1], "gier_grad": spot[2]},
             "tags": [], "klickfahrt": {"nummer": 0, "zustand": "keine", "grund": "",
                                        "ziel": None, "weg": []},
             "faehigkeiten": {"licht": False, "ton": False, "kamera": False},
             "menschen": [], "karte": None}
    daten.update(mehr)
    return daten


def _widget(qapp):
    w = lb.Lagebild(palette_fuer(False))
    w.resize(400, 400)
    w.show()
    qapp.processEvents()
    return w


def test_spot_steht_in_der_mitte(qapp):
    w = _widget(qapp)
    w.zeige(_daten(), None)
    p = w.welt_zu_schirm(2.0, 3.0)
    assert p.x() == pytest.approx(200, abs=1) and p.y() == pytest.approx(200, abs=1)
    x, y = w.schirm_zu_welt(p.x(), p.y())
    assert (x, y) == pytest.approx((2.0, 3.0))


def test_oben_ist_plus_y(qapp):
    w = _widget(qapp)
    w.zeige(_daten(), None)
    assert w.welt_zu_schirm(2.0, 4.0).y() < w.welt_zu_schirm(2.0, 3.0).y()
    assert w.welt_zu_schirm(3.0, 3.0).x() > w.welt_zu_schirm(2.0, 3.0).x()


def test_ein_klick_meldet_die_weltkoordinate(qapp):
    w = _widget(qapp)
    w.zeige(_daten(), None)
    gemeldet = []
    w.klick.connect(lambda x, y: gemeldet.append((x, y)))
    p = w.welt_zu_schirm(2.5, 3.0)
    QTest.mouseClick(w, Qt.LeftButton, pos=QPoint(round(p.x()), round(p.y())))
    [(x, y)] = gemeldet
    assert x == pytest.approx(2.5, abs=0.03) and y == pytest.approx(3.0, abs=0.03)


def test_ziehen_verschiebt_und_ist_kein_klick(qapp):
    w = _widget(qapp)
    w.zeige(_daten(), None)
    gemeldet = []
    w.klick.connect(lambda x, y: gemeldet.append((x, y)))
    vorher = w.schirm_zu_welt(200, 200)
    QTest.mousePress(w, Qt.LeftButton, pos=QPoint(200, 200))
    QTest.mouseMove(w, QPoint(260, 200))
    QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(260, 200))
    assert not gemeldet
    assert w.schirm_zu_welt(260, 200) == pytest.approx(vorher), "der Punkt wandert mit der Maus"
    assert not w.folgt
    w.zeige(_daten(spot=(5.0, 5.0, 0.0)), None)
    assert w.schirm_zu_welt(260, 200) == pytest.approx(vorher), "verschoben heisst: folgt nicht mehr"
    w.mitte()
    assert w.folgt and w.welt_zu_schirm(5.0, 5.0).x() == pytest.approx(200, abs=1)


def test_das_mausrad_zoomt_um_den_zeiger(qapp):
    from PySide6.QtCore import QPoint as P
    from PySide6.QtGui import QWheelEvent

    w = _widget(qapp)
    w.zeige(_daten(), None)
    zeiger = QPointF(300, 120)
    vorher = w.schirm_zu_welt(zeiger.x(), zeiger.y())
    massstab = w.px_je_m
    ereignis = QWheelEvent(zeiger, w.mapToGlobal(zeiger), P(0, 0), P(0, 120), Qt.NoButton,
                           Qt.NoModifier, Qt.NoScrollPhase, False)
    w.wheelEvent(ereignis)
    assert w.px_je_m > massstab
    assert w.schirm_zu_welt(zeiger.x(), zeiger.y()) == pytest.approx(vorher, abs=1e-6)


def _skizze_mit_wand():
    s = sk.Skizze()
    werte = np.full((40, 40), 1.0)
    werte[20, :] = 0.0
    s.aufnehmen(ObstacleGrid(werte, 0.03, (1.4, 2.4), 0.0, known=np.ones((40, 40), bool)), t=1.0)
    return s


def test_die_skizze_wird_mit_den_themenfarben_gezeichnet(qapp):
    from PySide6.QtGui import QColor

    s = _skizze_mit_wand()
    w = _widget(qapp)
    daten = _daten(ursprung=list(s.ursprung), breite=s.zustand.shape[1], hoehe=s.zustand.shape[0])
    w.zeige(daten, s.png(t=1.0))
    bild = w.grab().toImage()
    p = w.welt_zu_schirm(1.6, 3.0 + 0.012)      # die Wandzeile bei y = 3.0, neben Spot
    wand = QColor(bild.pixel(round(p.x()), round(p.y())))
    q = w.welt_zu_schirm(1.6, 2.7)
    boden = QColor(bild.pixel(round(q.x()), round(q.y())))
    ecke = QColor(bild.pixel(5, 5))
    palette = palette_fuer(False)
    assert wand != boden != ecke
    assert abs(wand.lightness() - QColor(palette.text).lightness()) < 40


def test_leeren_vergisst_bild_und_lage(qapp):
    s = _skizze_mit_wand()
    w = _widget(qapp)
    w.zeige(_daten(ursprung=list(s.ursprung), breite=s.zustand.shape[1],
                   hoehe=s.zustand.shape[0]), s.png(t=1.0))
    w.leeren()
    assert not w.hat_bild()
    w.grab()                                   # zeichnet ohne Daten, ohne zu werfen


def test_ein_kaputtes_bild_laesst_das_letzte_stehen(qapp):
    s = _skizze_mit_wand()
    w = _widget(qapp)
    daten = _daten(ursprung=list(s.ursprung), breite=s.zustand.shape[1], hoehe=s.zustand.shape[0])
    w.zeige(daten, s.png(t=1.0))
    w.zeige(daten, b"halb")
    assert w.hat_bild()


def test_weg_ziel_und_tags_zeichnen_ohne_fehler(qapp):
    w = _widget(qapp)
    w.zeige(_daten(tags=[{"id": 3, "x": 3.0, "y": 3.0}],
                   klickfahrt={"nummer": 2, "zustand": "abgelehnt", "grund": "unbekannt",
                               "ziel": [3.0, 4.0], "weg": [[2.5, 3.5], [3.0, 4.0]]}), None)
    w.grab()


def test_keine_farbliterale_im_widget():
    quelle = Path(lb.__file__).read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{6}\b", quelle)
    assert not re.search(r"QColor\(\s*\d", quelle)


def test_unbekanntes_hebt_sich_von_der_seite_ab(qapp):
    """Ein Bild vom 27.09.2026: Unbekanntes hatte die Farbe des Seitenhintergrunds, man sah
    nicht, wo die Draufsicht aufhört. Das Feld ist die Fläche, nicht der Hintergrund."""
    from PySide6.QtGui import QColor

    for dunkel in (False, True):
        palette = palette_fuer(dunkel)
        w = lb.Lagebild(palette)
        w.resize(400, 400)
        w.zeige(_daten(), None)
        ecke = QColor(w.grab().toImage().pixel(20, 20))
        assert ecke == QColor(palette.flaeche)
        assert ecke != QColor(palette.hintergrund)
