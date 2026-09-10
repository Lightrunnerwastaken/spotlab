"""Gesichter in Spots Frontkameras -- und die Gegenprobe aus der Geometrie.

Der Erkenner findet Kaesten; ob einer ein Gesicht sein KANN, entscheidet die
Physik: aus Hoehenwinkel und gemessenem Abstand folgt die Hoehe ueber dem Boden.
Ueber die Aufzeichnung vom 12.08.2026 fand YuNet in 4 von 107 Takten etwas --
der beste Treffer war eine Stuhllehne, der zweitbeste ein SCHIENBEIN.
"""

import math

import numpy as np
import pytest

from spotlab.backends.real import gesicht
from spotlab.errors import SpotlabError

# ------------------------------------------------------- Abstand aus Tiefe


def _wolke(abstand, peilung_grad, hoehenwinkel_grad, anzahl=30):
    p, h = math.radians(peilung_grad), math.radians(hoehenwinkel_grad)
    eben = abstand
    x, y = eben * math.cos(p), eben * math.sin(p)
    z = eben * math.tan(h)
    return np.array([[x, y, z]] * anzahl, dtype=float)


def test_der_abstand_kommt_aus_den_punkten_in_dieser_richtung():
    punkte = np.vstack([_wolke(2.0, 0.0, 20.0), _wolke(5.0, 60.0, 0.0)])
    assert gesicht.abstand_in_richtung(punkte, 0.0, 20.0) == pytest.approx(2.0, abs=0.01)
    assert gesicht.abstand_in_richtung(punkte, 60.0, 0.0) == pytest.approx(5.0, abs=0.01)
    assert gesicht.abstand_in_richtung(punkte, -60.0, 0.0) is None


def test_der_median_gewinnt_gegen_einen_ausreisser():
    """Ein einzelner Punkt vor dem Gesicht waere sonst der gemeldete Abstand."""
    punkte = np.vstack([_wolke(3.0, 0.0, 15.0, anzahl=30), _wolke(0.4, 0.0, 15.0, anzahl=1)])
    assert gesicht.abstand_in_richtung(punkte, 0.0, 15.0) == pytest.approx(3.0, abs=0.01)


def test_zu_wenige_punkte_geben_keinen_abstand():
    assert gesicht.abstand_in_richtung(_wolke(2.0, 0.0, 0.0, anzahl=3), 0.0, 0.0) is None
    assert gesicht.abstand_in_richtung(None, 0.0, 0.0) is None
    assert gesicht.abstand_in_richtung(np.zeros((0, 3)), 0.0, 0.0) is None


# ------------------------------------------------------------ Gegenprobe


class _Pano:
    """Ein Panorama, das eine feste Richtung liefert."""

    def __init__(self, peilung, hoehenwinkel):
        self._winkel = (peilung, hoehenwinkel)

    def winkel(self, spalte, zeile):
        return self._winkel


def _mit_kaesten(monkeypatch, kaesten):
    monkeypatch.setattr(gesicht, "kaesten", lambda feld, erkenner_: kaesten)


def test_ein_schienbein_faellt_durch_die_gegenprobe(monkeypatch):
    """Der echte Fehltreffer vom 12.08.2026: ein Bein, einen Meter voraus."""
    _mit_kaesten(monkeypatch, [(320.0, 181.0, 104.0, 210.0, 0.66)])
    punkte = _wolke(1.0, 0.0, 0.0)
    assert gesicht.gesichter(None, _Pano(0.0, 0.0), None, punkte, 0.46) == []


def test_ein_kopf_auf_kopfhoehe_zaehlt(monkeypatch):
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.8)])
    # 3 m voraus, 20 Grad hinauf -> 0.46 + 3*tan(20) = 1.55 m
    punkte = _wolke(3.0, 0.0, 20.0)
    [kopf] = gesicht.gesichter(None, _Pano(0.0, 20.0), None, punkte, 0.46)
    assert kopf.height == pytest.approx(1.55, abs=0.02)
    assert kopf.distance == pytest.approx(3.0, abs=0.01)
    assert kopf.bearing == 0.0 and kopf.score == 0.8


def test_ohne_tiefenpunkte_zaehlt_kein_kasten(monkeypatch):
    """Ohne Entfernung gibt es keine Gegenprobe -- und ohne Gegenprobe ist ein
    Schienbein ein Gesicht."""
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.99)])
    assert gesicht.gesichter(None, _Pano(0.0, 20.0), None, np.zeros((0, 3)), 0.46) == []


def test_das_naechste_gesicht_steht_vorne(monkeypatch):
    _mit_kaesten(monkeypatch, [(0.0, 0.0, 40.0, 50.0, 0.8), (500.0, 0.0, 40.0, 50.0, 0.9)])

    class _Zwei:
        def __init__(self):
            self._folge = [(0.0, 20.0), (30.0, 20.0)]

        def winkel(self, spalte, zeile):
            return self._folge[0] if spalte < 100 else self._folge[1]

    punkte = np.vstack([_wolke(4.0, 0.0, 20.0), _wolke(2.5, 30.0, 20.0)])
    gefunden = gesicht.gesichter(None, _Zwei(), None, punkte, 0.46)
    assert [round(g.distance, 1) for g in gefunden] == [2.5, 4.0]


# --------------------------------------------------------------- Modell


def test_ein_fehlendes_modell_sagt_wo_es_herkommt(tmp_path):
    with pytest.raises(SpotlabError, match="OpenCV-Zoo"):
        gesicht.modellpfad(tmp_path / "gibtsnicht.onnx", umgebung={})


def test_ein_vorhandenes_modell_wird_genommen(tmp_path):
    pfad = tmp_path / "modell.onnx"
    pfad.write_bytes(b"x")
    assert gesicht.modellpfad(pfad, umgebung={}) == pfad


def test_die_umgebungsvariable_zaehlt_wenn_kein_pfad_kommt(tmp_path):
    """Damit eine schon vorhandene Kopie nicht kopiert werden muss."""
    pfad = tmp_path / "modell.onnx"
    pfad.write_bytes(b"x")
    assert gesicht.modellpfad(umgebung={gesicht.ENV_MODELL: str(pfad)}) == pfad


# ============ Mit echtem Erkenner, echtem Bild und echter Geometrie
#
# Braucht OpenCV und das YuNet-Modell (SPOTLAB_GESICHTSMODELL oder
# ~/.spotlab/modelle/). Fehlt eines, wird uebersprungen -- die Aussage oben
# steht auch ohne, weil sie Geometrie ist und kein Modell.


def _modell_da():
    try:
        gesicht.modellpfad()
        return True
    except SpotlabError:
        return False


@pytest.mark.skipif(not _modell_da(), reason="YuNet-Modell nicht abgelegt")
def test_das_echte_schienbein_faellt_durch_die_gegenprobe():
    """Takt 50 der Aufzeichnung: YuNet setzt einen Kasten mit 0.66 auf ein Bein.
    Mit Tiefenpunkten auf einem Meter ist der Kasten rund einen halben Meter
    ueber dem Boden -- und damit kein Gesicht."""
    pytest.importorskip("cv2")
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).parent))
    from test_backend_panorama import _paar

    from spotlab.backends.real import panorama

    kameras = panorama.kalibrierung_aus(_paar(90))
    pano = panorama.Panorama(kameras, zuschnitt=panorama.ALLES)
    feld = pano.zusammensetzen(panorama.bilder_aus(_paar(50)))
    erkenner_ = gesicht.erkenner(pano.breite, pano.hoehe, mindestscore=0.5)

    roh = gesicht.kaesten(feld, erkenner_)
    assert roh, "der Erkenner findet hier etwas -- genau das ist der Fehltreffer"

    # Die Person ging dicht vorbei: Tiefenpunkte auf einem Meter, rundum.
    punkte = np.vstack([_wolke(1.0, p, h, anzahl=40)
                        for p in range(-60, 61, 5) for h in (-20, 0, 20)])
    assert gesicht.gesichter(feld, pano, erkenner_, punkte, pano.kamerahoehe()) == []


# ============ Mit geneigtem Koerper
#
# Der Hoehenwinkel aus dem Panorama ist KOERPERFEST. Hebt Spot die Nase,
# erscheint derselbe Punkt weiter unten im Bild -- ohne Korrektur laege ein
# Gesicht auf drei Metern bei 15 Grad Neigung rund 80 cm zu tief.


def test_ohne_korrektur_faellt_ein_gesicht_bei_geneigtem_koerper_durch(monkeypatch):
    """Die Gegenprobe rechnet den Nick heraus -- sonst verwirft sie den Kopf."""
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.8)])
    # Der Kopf steht 3 m voraus auf 1.55 m, der Koerper ist 15 Grad geneigt.
    # Im Bild erscheint er deshalb bei 20 - 15 = 5 Grad.
    punkte = _wolke(3.0, 0.0, 20.0)
    pano = _Pano(0.0, 5.0)

    ohne = gesicht.gesichter(None, pano, None, punkte, 0.46)
    assert ohne == [], "ohne Korrektur passt weder Richtung noch Hoehe"

    [kopf] = gesicht.gesichter(None, pano, None, punkte, 0.56, blick_grad=15.0)
    assert kopf.elevation == pytest.approx(20.0)
    assert kopf.height == pytest.approx(0.56 + 3.0 * math.tan(math.radians(20.0)), abs=0.01)


def test_die_kamera_hebt_sich_mit_der_nase():
    """Sie sitzt 38 cm vor der Koerpermitte -- bei 15 Grad steigt sie gut 10 cm."""
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).parent))
    from test_backend_panorama import _paar

    from spotlab.backends.real import panorama

    pano = panorama.Panorama(panorama.kalibrierung_aus(_paar(90)))
    flach = pano.kamerahoehe()
    geneigt = pano.kamerahoehe(15.0)
    assert geneigt - flach == pytest.approx(0.10, abs=0.02)
    assert pano.kamerahoehe(0.0) == pytest.approx(flach)
