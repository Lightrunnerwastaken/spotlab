"""Die Einzelsicht: eine Seiten- oder Rückkamera als Zylinderbild, Peilung im KÖRPERrahmen.

Für die Stufe „Rundum“ der Menschensuche (Steuerzentrale Teil 2, 27.09.2026). Das Frontpanorama
bleibt, wie es ist; die Einzelsicht nimmt dieselbe Projektion für EINE Kamera.
"""

import math

import numpy as np
import pytest

from spotlab.backends.real import panorama


def _kamera(name, vorn, rechts, ort=(0.0, 0.0, 0.05)):
    """Eine Lochkamera 640 x 480, waagerecht, Blick `vorn`, Bild-rechts `rechts` (Körperachsen)."""
    vorn, rechts = np.asarray(vorn, float), np.asarray(rechts, float)
    unten = np.array([0.0, 0.0, -1.0])
    lage = np.eye(4)
    lage[:3, 0], lage[:3, 1], lage[:3, 2] = rechts, unten, vorn
    lage[:3, 3] = ort
    return panorama.Kamera(name, 640, 480, 330.0, 330.0, 320.0, 240.0, lage)


def _links():
    # Blick nach links (+y); wer nach links schaut, hat vorn (+x) zur Rechten.
    return panorama.Einzelsicht(_kamera("left_fisheye_image", (0, 1, 0), (1, 0, 0), (0.0, 0.11, 0.05)))


def _hinten():
    return panorama.Einzelsicht(_kamera("back_fisheye_image", (-1, 0, 0), (0, 1, 0), (-0.42, 0.0, 0.05)))


def test_die_blickrichtung_ist_die_peilung_der_mitte():
    links, hinten = _links(), _hinten()
    assert links.gier_grad == pytest.approx(90.0)
    assert abs(hinten.gier_grad) == pytest.approx(180.0)
    peilung, hoehe = links.winkel(links.spalte(90.0), 0)
    assert peilung == pytest.approx(90.0, abs=0.01)


def test_nach_rechts_im_bild_der_linken_kamera_liegt_vorn():
    s = _links()
    mitte = s.spalte(90.0)
    assert s.winkel(mitte + 80, 100)[0] < 90.0 - 5.0
    assert s.winkel(mitte - 80, 100)[0] > 90.0 + 5.0


def test_die_peilung_der_rueckkamera_bleibt_zwischen_minus_und_plus_180():
    s = _hinten()
    for spalte in (s.spalte(170.0), s.spalte(-170.0), s.spalte(180.0)):
        peilung, _ = s.winkel(spalte, 50)
        assert -180.0 < peilung <= 180.0
    assert s.winkel(s.spalte(-170.0), 50)[0] == pytest.approx(-170.0, abs=0.01)


def test_aus_der_peilung_wird_wieder_die_spalte():
    s = _links()
    for spalte in (50.0, 200.0, s.breite - 60.0):
        assert s.spalte(s.winkel(spalte, 10)[0]) == pytest.approx(spalte, abs=1e-6)


def test_oben_im_bild_ist_ein_positiver_hoehenwinkel():
    s = _links()
    assert s.winkel(s.spalte(90.0), 0)[1] > 0.0 > s.winkel(s.spalte(90.0), s.hoehe - 1)[1]


def test_die_bildmitte_der_kamera_landet_bei_ihrer_blickrichtung():
    s = _links()
    bild = np.zeros((480, 640), np.uint8)
    bild[235:246, 315:326] = 255
    feld = s.zusammensetzen([bild])
    assert feld.shape == (s.hoehe, s.breite)
    zeilen, spalten = np.nonzero(feld > 128)
    assert len(spalten) and abs(float(np.mean(spalten)) - s.spalte(90.0)) < 3.0
    peilung, hoehe = s.winkel(float(np.mean(spalten)), float(np.mean(zeilen)))
    assert abs(hoehe) < 1.5, "waagerechte Kamera: die Mitte liegt auf dem Horizont"


def test_farbe_bleibt_farbe():
    s = _links()
    feld = s.zusammensetzen([np.zeros((480, 640, 3), np.uint8)])
    assert feld.shape == (s.hoehe, s.breite, 3)


def test_eine_fremde_bildgroesse_wird_abgewiesen():
    from spotlab.errors import SpotlabError

    with pytest.raises(SpotlabError):
        _links().zusammensetzen([np.zeros((100, 100), np.uint8)])


def test_die_kamerahoehe_kommt_aus_der_lage():
    s = _links()
    assert s.kamerahoehe(0.0) == pytest.approx(panorama.STANDHOEHE_M + 0.05)


def test_das_frontpanorama_verlangt_weiter_zwei_kameras():
    from spotlab.errors import SpotlabError

    with pytest.raises(SpotlabError):
        panorama.Panorama([_kamera("x", (1, 0, 0), (0, -1, 0))])
    assert math.isfinite(_links().brennweite)
