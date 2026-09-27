"""Kartenwände und Abgleich (Steuerzentrale Teil 3): was Spot von der Karte wiedererkennt.

Die Skizze wird hier direkt als Raster gebaut (5-cm-Zellen ab (0, 0)), die Karte als Liste von
Wandpunkten im Rahmen „vision“. Spot steht bei (2.5, 1.0); das Blickfeld reicht 4 m weit und
zählt nur, was höchstens 5 s alt ist.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from spotlab.backends.base import Verortung
from spotlab.record import zentrale as protokoll
from spotlab.workshop import kartenabgleich as ka
from spotlab.workshop import skizze as sk

T = 100.0
SPOT = (2.5, 1.0)
KATAKOMBEN = Path(r"D:\Users\janis\Documents\Spot Projects\maps\map_catacombs_01")


def _skizze(waende=(), frei_alles=True, alter_s=0.0, groesse=(120, 120)):
    """Eine Skizze 6 x 6 m ab (0, 0): alles frisch frei, dazu Wandzellen [(x, y), ...]."""
    s = sk.Skizze()
    s.ursprung = (0.0, 0.0)
    s.zustand = np.full(groesse, sk.FREI if frei_alles else sk.UNBEKANNT, np.uint8)
    s.zeit = np.full(groesse, T - alter_s, float)
    for x, y in waende:
        z, sp = s.zelle(x, y)
        s.zustand[z, sp] = sk.WAND
    return s


def _linie(x0, x1, y, schritt=0.05):
    return [(x, y) for x in np.arange(x0, x1 + 1e-9, schritt)]


def _code(a, x, y):
    spalte = int(math.floor((x - a.ursprung[0]) / ka.ZELLE_M + 1e-6))
    zeile = int(math.floor((y - a.ursprung[1]) / ka.ZELLE_M + 1e-6))
    return int(a.raster[zeile, spalte])


def test_eine_gesehene_wand_die_in_der_karte_steht_ist_erkannt():
    wand = _linie(1.0, 4.0, 2.02)
    a = ka.abgleich(_skizze(wand), np.array(wand), SPOT, T)
    assert a.neu == 0 and a.erkannt > 20 and a.anteil == pytest.approx(1.0)
    assert _code(a, 2.5, 2.02) == protokoll.KARTE_ERKANNT


def test_zehn_zentimeter_daneben_ist_noch_erkannt_dreissig_nicht():
    wand = _linie(1.0, 4.0, 2.02)
    assert ka.abgleich(_skizze(wand), np.array(_linie(1.0, 4.0, 2.12)), SPOT, T).anteil == 1.0
    assert ka.abgleich(_skizze(wand), np.array(_linie(1.0, 4.0, 2.32)), SPOT, T).anteil == 0.0


def test_eine_wand_ohne_kartenwand_ist_neu():
    wand = _linie(1.0, 4.0, 2.02)
    a = ka.abgleich(_skizze(wand), np.array(_linie(1.0, 4.0, 5.5)), SPOT, T)
    assert a.erkannt == 0 and a.neu > 20 and a.anteil == 0.0
    assert _code(a, 2.5, 2.02) == protokoll.KARTE_NEU
    assert _code(a, 2.5, 5.5) == protokoll.KARTE_UNGEPRUEFT, "5.5 m ist ausserhalb des Blickfelds"


def test_eine_kartenwand_wo_spot_freien_boden_sieht_fehlt():
    a = ka.abgleich(_skizze(), np.array(_linie(1.0, 4.0, 3.0)), SPOT, T)
    assert a.fehlt > 20 and _code(a, 2.5, 3.0) == protokoll.KARTE_FEHLT
    assert a.anteil is None, "keine Wand gesehen: keine Zahl"


def test_alte_und_ferne_beobachtungen_zaehlen_nicht():
    wand = _linie(1.0, 4.0, 2.02)
    alt = ka.abgleich(_skizze(wand, alter_s=sk.FRISCH_S + 1), np.array(wand), SPOT, T)
    assert alt.erkannt == alt.neu == alt.fehlt == 0
    assert _code(alt, 2.5, 2.02) == protokoll.KARTE_UNGEPRUEFT
    fern = ka.abgleich(_skizze(wand), np.array(wand), (2.5, -4.0), T)
    assert fern.erkannt == 0 and fern.anteil is None


def test_zu_wenig_wand_im_blick_gibt_keine_zahl():
    wand = _linie(2.0, 2.4, 2.02)          # 9 Zellen
    a = ka.abgleich(_skizze(wand), np.array(wand), SPOT, T)
    assert a.erkannt > 0 and a.anteil is None


def test_verloren_ist_alles_ungeprueft_und_ohne_zahl():
    wand = _linie(1.0, 4.0, 2.02)
    a = ka.abgleich(_skizze(wand + _linie(1.0, 4.0, 0.5)), np.array(wand), SPOT, T, verloren=True)
    assert (a.erkannt, a.neu, a.fehlt, a.anteil) == (0, 0, 0, None)
    assert set(np.unique(a.raster)) <= {0, protokoll.KARTE_UNGEPRUEFT}


def test_das_raster_liegt_im_zellgitter_der_skizze():
    a = ka.abgleich(_skizze(), np.array([(1.234, 2.345), (3.21, 0.77)]), SPOT, T)
    for wert in a.ursprung:
        assert abs(wert / ka.ZELLE_M - round(wert / ka.ZELLE_M)) < 1e-6
    assert a.raster.shape == (a.hoehe, a.breite)


def test_ohne_kartenwand_und_ohne_skizze_gibt_es_kein_raster():
    assert ka.abgleich(sk.Skizze(), np.zeros((0, 2)), SPOT, T) is None


def test_das_bild_ist_ein_indexbild_mit_oben_als_erster_zeile():
    from io import BytesIO

    from PIL import Image

    a = ka.abgleich(_skizze(), np.array(_linie(1.0, 4.0, 3.0)), SPOT, T)
    bild = Image.open(BytesIO(ka.png(a)))
    assert bild.mode == "P" and bild.size == (a.breite, a.hoehe)
    assert np.array_equal(np.array(bild), np.flipud(a.raster))


# ------------------------------------------------------------ Umrechnung


def test_vom_seed_in_die_skizze():
    """Spot steht im Seed bei (2, 1) mit Nase +y, in „vision“ bei (5, 6) mit Nase 0.3 rad."""
    v = Verortung("wp", (2.0, 1.0, math.radians(90.0)), (5.0, 6.0, 0.3), False, 0, 0)
    trafo = ka.vision_von_seed(v)
    koerper, voraus = ka.in_vision(np.array([[2.0, 1.0], [2.0, 2.0]]), trafo)
    assert koerper == pytest.approx((5.0, 6.0))
    assert voraus == pytest.approx((5.0 + math.cos(0.3), 6.0 + math.sin(0.3)))


def test_ohne_vision_gibt_es_keine_umrechnung():
    assert ka.vision_von_seed(Verortung("wp", (0, 0, 0), None, False, 0, 0)) is None


# ------------------------------------------------------------ an einer echten Karte


@pytest.mark.skipif(not KATAKOMBEN.is_dir(), reason="Katakomben-Karte fehlt auf diesem Rechner")
def test_die_kartenwaende_sind_die_der_rekonstruktion():
    from spotlab.maps import rekonstruktion

    w = ka.Kartenwaende.aus_ordner(KATAKOMBEN)
    graph, schnappschuesse, _ = rekonstruktion.lade_karte(KATAKOMBEN)
    posen_, _ = rekonstruktion.posen(graph)
    erwartet = rekonstruktion.wandzellen(graph, schnappschuesse, posen_).zellen
    assert len(w.zellen) == len(erwartet) > 1000
    assert len(w.wegpunkte) == len(graph.waypoints)
    assert all(0 <= i < len(w.wegpunkte) and 0 <= j < len(w.wegpunkte) for i, j in w.kanten)
    assert len(w.kanten) == len(graph.edges)
