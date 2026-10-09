"""Fahrbausteine für Agentenbefehle -- ohne Roboter, ohne Zentrale."""

import math

import numpy as np
import pytest

from spotlab.backends.base import ObstacleGrid
from spotlab.workshop import agentfahrt as af


def _gitter(frei=True, x=0.0, y=0.0, halb=2.0, zelle=0.05, wand_x=None):
    """Ein Gitter um (x, y); mit `wand_x` steht quer bei x = wand_x eine dünne Wand."""
    n = int(round(2 * halb / zelle))
    zellen = np.full((n, n), 2.0 if frei else 0.0)
    if wand_x is not None:
        xs = x - halb + np.arange(n) * zelle
        for spalte, wx in enumerate(xs):
            zellen[:, spalte] = min(abs(wx - wand_x), 2.0)
    return ObstacleGrid(cells=zellen, cell_size=zelle, origin=(x - halb, y - halb), time=0.0,
                        known=np.ones((n, n), bool))


def test_relativ_vor_und_links_im_eigenen_blick():
    x, y = af.relativ_ziel((1.0, 2.0, math.radians(90)), 1.0, 0.5)   # Blick nach +y
    assert (x, y) == pytest.approx((0.5, 3.0))


def test_die_drehung_kommt_an_und_haelt_die_drehschwelle():
    d = af.Drehung(math.radians(90), t0=0.0)
    wz, zustand, _ = d.schritt(0.0, 0.0)
    assert zustand == "unterwegs" and wz > 0
    wz, zustand, _ = d.schritt(math.radians(86), 1.0)                 # 4° daneben
    assert zustand == "unterwegs" and wz >= af.DREH_MIN_RAD_S
    wz, zustand, _ = d.schritt(math.radians(88), 2.0)
    assert (wz, zustand) == (0.0, "angekommen")


def test_die_drehung_gibt_nach_der_frist_auf():
    d = af.Drehung(math.radians(-90), t0=0.0)
    wz, zustand, grund = d.schritt(0.0, af.DREH_FRIST_S + 0.1)
    assert (wz, zustand) == (0.0, "abgebrochen") and "s" in grund


def test_ein_stoss_wird_gekappt_und_vorwaerts_geprueft():
    lage = (0.0, 0.0, 0.0)
    vx, vy, wz, dauer, grund = af.stoss_pruefen(2.0, 0.0, 3.0, 5.0, lage, _gitter(), 3.0,
                                                True, "", max_v=0.5, max_w=0.8)
    assert grund is None
    assert (vx, wz, dauer) == pytest.approx((0.5, 0.8, af.STOSS_MAX_S))


def test_vorwaerts_ohne_platz_oder_kopfraum_faehrt_nicht():
    lage = (0.0, 0.0, 0.0)
    *_, grund = af.stoss_pruefen(0.5, 0.0, 0.0, 2.0, lage, _gitter(), 0.6, True, "",
                                 max_v=0.5, max_w=0.8)
    assert grund and "frei" in grund
    *_, grund = af.stoss_pruefen(0.3, 0.0, 0.0, 1.0, lage, _gitter(), 3.0, False, "Tischplatte",
                                 max_v=0.5, max_w=0.8)
    assert grund == "Tischplatte"


def test_seitwaerts_und_rueckwaerts_langsam_und_nur_wenn_das_gitter_frei_ist():
    lage = (0.0, 0.0, 0.0)
    vx, vy, _wz, _d, grund = af.stoss_pruefen(-0.6, 0.6, 0.0, 1.0, lage, _gitter(), 3.0, True,
                                              "", max_v=0.5, max_w=0.8)
    assert grund is None and abs(vx) <= af.STOSS_SEITE_MAX_M_S and abs(vy) <= af.STOSS_SEITE_MAX_M_S
    *_, grund = af.stoss_pruefen(-0.2, 0.0, 0.0, 2.0, lage, _gitter(wand_x=-0.3), 3.0, True, "",
                                 max_v=0.5, max_w=0.8)
    assert grund and "hinten" in grund


def test_ohne_lesbares_gitter_kein_stoss():
    *_, grund = af.stoss_pruefen(0.0, 0.2, 0.0, 1.0, (0.0, 0.0, 0.0), None, None, True, "",
                                 max_v=0.5, max_w=0.8)
    assert grund and "Gitter" in grund


def test_die_tiefe_je_sektor_nimmt_das_fuenfte_perzentil():
    rng = np.random.default_rng(1)
    mitte = np.column_stack([rng.uniform(1.0, 3.0, 200), rng.uniform(-0.1, 0.1, 200),
                             np.zeros(200)])
    links = np.column_stack([np.full(30, 2.0), np.full(30, 1.0), np.zeros(30)])   # +26°
    boden = np.column_stack([np.full(50, 0.6), np.zeros(50), np.full(50, -0.5)])   # zählt nicht
    ergebnis = af.tiefe_sektoren(np.vstack([mitte, links, boden]))
    assert ergebnis["mitte"]["abstand_m"] == pytest.approx(np.percentile(mitte[:, 0], 5), abs=0.01)
    assert ergebnis["links"]["abstand_m"] == pytest.approx(math.hypot(2.0, 1.0), abs=0.01)
    assert ergebnis["rechts"]["abstand_m"] is None and "wenig" in ergebnis["rechts"]["grund"]
