"""Die wachsende Skizze der Steuerzentrale: was Spot gesehen hat, als Raster im Rahmen „vision“."""

import io

import numpy as np
import pytest

from spotlab.backends.base import ObstacleGrid
from spotlab.record.zentrale import ALTERSSTUFEN
from spotlab.workshop import skizze as sk


def _gitter(ursprung=(0.0, 0.0), n=40, wand_y=None, unbekannt_ecke=False, frei=1.0):
    """Ein Hindernisgitter wie Spots: 3-cm-Zellen, je Zelle der Abstand zum nächsten Hindernis.
    `wand_y`: eine Zeile mit Abstand 0 bei dieser Höhe (Weltkoordinate)."""
    werte = np.full((n, n), frei)
    bekannt = np.ones((n, n), bool)
    if wand_y is not None:
        zeile = int(round((wand_y - ursprung[1]) / 0.03))
        werte[zeile, :] = 0.0
    if unbekannt_ecke:
        bekannt[:5, :5] = False
    return ObstacleGrid(cells=werte, cell_size=0.03, origin=ursprung, time=0.0, known=bekannt)


def _zustand(s, x, y):
    z = s.zelle(x, y)
    assert z is not None, (x, y)
    return int(s.zustand[z])


def test_eine_leere_skizze_kennt_keine_zelle():
    s = sk.Skizze()
    assert s.leer and s.zelle(0.0, 0.0) is None


def test_boden_wand_und_unbekanntes_aus_einem_gitter():
    s = sk.Skizze()
    s.aufnehmen(_gitter(wand_y=0.6, unbekannt_ecke=True), t=10.0)
    assert not s.leer
    assert _zustand(s, 0.5, 0.3) == sk.FREI
    assert _zustand(s, 0.5, 0.61) == sk.WAND
    assert _zustand(s, 0.04, 0.04) == sk.UNBEKANNT
    assert s.zeit[s.zelle(0.5, 0.3)] == 10.0


def test_die_skizze_waechst_und_vergisst_nichts():
    s = sk.Skizze()
    s.aufnehmen(_gitter(wand_y=0.6), t=1.0)
    s.aufnehmen(_gitter(ursprung=(10.0, 10.0)), t=2.0)
    assert _zustand(s, 10.5, 10.5) == sk.FREI
    assert _zustand(s, 0.5, 0.61) == sk.WAND, "was vorher gesehen wurde, bleibt"
    assert s.zeit[s.zelle(0.5, 0.3)] == 1.0


def test_die_neueste_beobachtung_gewinnt():
    """Ein Mensch, der weggeht, hinterlässt keine Wand."""
    s = sk.Skizze()
    s.aufnehmen(_gitter(wand_y=0.6), t=1.0)
    s.aufnehmen(_gitter(), t=5.0)
    assert _zustand(s, 0.5, 0.61) == sk.FREI


def test_unbeobachtetes_aendert_nichts():
    s = sk.Skizze()
    s.aufnehmen(_gitter(wand_y=0.6), t=1.0)
    blind = _gitter()
    blind = ObstacleGrid(blind.cells, 0.03, (0.0, 0.0), 0.0, known=np.zeros((40, 40), bool))
    s.aufnehmen(blind, t=9.0)
    assert _zustand(s, 0.5, 0.61) == sk.WAND


def test_der_deckel_behaelt_das_neue():
    s = sk.Skizze()
    s.aufnehmen(_gitter(), t=1.0)
    s.aufnehmen(_gitter(ursprung=(70.0, 0.0)), t=2.0)
    h, b = s.zustand.shape
    assert b * s.zelle_m <= sk.MAX_M + 1e-9 and h * s.zelle_m <= sk.MAX_M + 1e-9
    assert _zustand(s, 70.5, 0.5) == sk.FREI
    assert s.zelle(0.5, 0.5) is None, "das Alte, 70 m weg, fällt heraus"


def test_welt_und_zelle_passen_zusammen():
    s = sk.Skizze()
    s.aufnehmen(_gitter(), t=1.0)
    z = s.zelle(0.52, 0.31)
    x, y = s.welt(*z)
    assert abs(x - 0.52) <= s.zelle_m / 2 + 1e-9 and abs(y - 0.31) <= s.zelle_m / 2 + 1e-9


def test_das_bild_zeigt_zustand_und_alter_und_oben_ist_norden():
    s = sk.Skizze()
    s.aufnehmen(_gitter(wand_y=0.6), t=0.0)
    s.aufnehmen(_gitter(ursprung=(0.0, 3.0)), t=sk.ALT_S)
    index = s.bild_index(t=sk.ALT_S)
    h, _ = index.shape

    def code(x, y):
        zeile, spalte = s.zelle(x, y)
        return int(index[h - 1 - zeile, spalte])

    assert code(0.5, 3.5) == 1, "frisch frei"
    assert code(0.5, 0.3) == ALTERSSTUFEN, "60 s alt frei: blassste Stufe"
    assert code(0.5, 0.61) == 2 * ALTERSSTUFEN, "alte Wand"
    assert index.max() <= 2 * ALTERSSTUFEN
    ecke = s.zelle(0.5, 2.5)
    assert ecke is None or int(index[h - 1 - ecke[0], ecke[1]]) == 0, "dazwischen unbekannt"


def test_das_png_hat_eine_palette_und_die_groesse_der_skizze():
    from PIL import Image

    s = sk.Skizze()
    s.aufnehmen(_gitter(wand_y=0.6), t=0.0)
    bild = Image.open(io.BytesIO(s.png(t=0.0)))
    h, b = s.zustand.shape
    assert bild.mode == "P" and bild.size == (b, h)


def test_ohne_skizze_gibt_es_kein_bild():
    with pytest.raises(ValueError):
        sk.Skizze().png(t=0.0)
