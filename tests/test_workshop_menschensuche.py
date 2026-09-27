"""Die Menschensuche der Steuerzentrale: dieselbe Kette wie beim Folgen, Ergebnis in der Draufsicht."""

import math

import numpy as np
import pytest
from test_backend_koerper import _Pano, _wolke

from spotlab.backends.real.koerper import Koerper
from spotlab.workshop import menschensuche as ms
from spotlab.workshop.folgen import Gesichtsaufnahme


def _koerper(spalte=620.0, huefte_zeile=300.0):
    return Koerper(huefte=(spalte, huefte_zeile), schulter=(spalte, 250.0), conf=0.95,
                   kasten=(spalte - 60.0, 100.0, spalte + 60.0, 700.0))


class _Erkenner:
    def __init__(self, koerper):
        self.koerper = koerper
        self.bilder = 0

    def finde(self, feld):
        self.bilder += 1
        return list(self.koerper)


class _Seite:
    """Eine Einzelsicht-Attrappe: Spalte 620 blickt nach `gier` Grad (Körperrahmen)."""

    def __init__(self, gier):
        self.gier = gier

    def winkel(self, spalte, zeile):
        return self.gier + (620.0 - spalte) / 7.0, (400.0 - zeile) / 10.0

    def kamerahoehe(self, blick_grad=0.0):
        return 0.46


def _suche(vorne=None, seiten=None, lage=(0.0, 0.0, 0.0), koerper=None):
    erkenner = {}

    def bauen(quelle):
        erkenner[quelle] = _Erkenner(koerper.get(quelle, []) if koerper else [_koerper()])
        return erkenner[quelle]

    def vorne_holen(spot, gemerkt):
        if vorne == "fehlt":
            return None
        feld = np.zeros((782, 1239), np.uint8)
        return Gesichtsaufnahme(feld, _Pano(), None, vorne if vorne is not None else _wolke(3.0, 0.0, 10.0),
                                0.0)

    def seite_holen(spot, gemerkt):
        return seiten or {}

    suche = ms.Menschensuche(object(), erkenner_bauen=bauen, vorne_holen=vorne_holen,
                             seite_holen=seite_holen, lage_holen=lambda spot: lage)
    return suche, erkenner


def test_aus_heisst_gar_nicht_suchen():
    suche, erkenner = _suche()
    assert suche.runde("aus", t=1.0) == ([], {})
    assert not erkenner


def test_vorne_landet_der_mensch_in_der_welt():
    """Spot bei (1, 2) mit Nase nach +y, der Mensch 3 m voraus: er steht bei (1, 5)."""
    suche, _ = _suche(lage=(1.0, 2.0, math.radians(90.0)))
    menschen, gruende = suche.runde("normal", t=7.0)
    [m] = menschen
    assert (m.x, m.y) == pytest.approx((1.0, 5.0), abs=0.05)
    assert m.abstand == pytest.approx(3.0, abs=0.05) and m.quelle == "vorne" and m.t == 7.0
    assert gruende == {}


def test_ein_verworfener_koerper_ist_kein_mensch():
    """Hüfte auf Kistenhöhe: die Höhenprobe verwirft ihn wie beim Folgen."""
    suche, _ = _suche(vorne=_wolke(2.0, 0.0, -5.0), koerper={"vorne": [_koerper(huefte_zeile=450.0)]})
    assert suche.runde("normal", t=1.0)[0] == []


def test_rundum_fragt_die_seiten_und_jede_quelle_hat_ihren_erkenner():
    seiten = {
        "links": (np.zeros((10, 10), np.uint8), _Seite(90.0), _wolke(2.0, 90.0, 10.0)),
        "hinten": (np.zeros((10, 10), np.uint8), _Seite(180.0), _wolke(2.5, 180.0, 10.0)),
    }
    suche, erkenner = _suche(seiten=seiten)
    menschen, _ = suche.runde("rundum", t=1.0)
    orte = {m.quelle: (round(m.x, 1), round(m.y, 1)) for m in menschen}
    assert orte["links"] == (0.0, 2.0) and orte["hinten"] == (-2.5, 0.0)
    assert set(erkenner) == {"vorne", "links", "hinten"}, "je Quelle eine eigene Spur"
    suche.runde("normal", t=2.0)
    assert erkenner["links"].bilder == 1, "normal fragt die Seiten nicht"


def test_eine_scheiternde_quelle_haelt_die_anderen_nicht_auf():
    seiten = {"links": RuntimeError("Kamera weg"),
              "hinten": (np.zeros((10, 10), np.uint8), _Seite(180.0), _wolke(2.5, 180.0, 10.0))}
    suche, _ = _suche(seiten=seiten)
    menschen, gruende = suche.runde("rundum", t=1.0)
    assert {m.quelle for m in menschen} == {"vorne", "hinten"}
    assert "Kamera weg" in gruende["links"]


def test_ohne_bilder_vorne_sagt_die_runde_warum():
    suche, _ = _suche(vorne="fehlt")
    menschen, gruende = suche.runde("normal", t=1.0)
    assert menschen == [] and "vorne" in gruende


def test_ohne_lage_gibt_es_keinen_ort():
    suche, _ = _suche(lage=None)
    menschen, gruende = suche.runde("normal", t=1.0)
    assert menschen == [] and "Lage" in gruende["vorne"]


def test_die_pause_je_stufe():
    assert ms.pause_s("sparsam") == ms.SPARSAM_PAUSE_S
    assert ms.pause_s("normal") == 0.0 and ms.pause_s("rundum") == 0.0
    with pytest.raises(ValueError):
        ms.pause_s("turbo")


def test_hinten_ueber_die_180_grad_findet_die_tiefenprobe_ihre_punkte():
    """Der Mensch bei +178 Grad, seine Tiefenpunkte bei -179: ohne Wickeln 357 Grad daneben --
    die Rückkamera hätte nie einen Abstand gehabt."""
    from spotlab.backends.real import gesicht

    punkte = _wolke(2.5, -179.0, 10.0)
    assert gesicht.abstand_in_richtung(punkte, 178.0, 10.0) == pytest.approx(2.5)
    assert gesicht.abstand_in_richtung(_wolke(2.5, 10.0, 10.0), 12.0, 10.0) == pytest.approx(2.5)
