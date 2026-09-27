"""A*-Wegsuche auf der Skizze: nur über bekannten freien Boden, mit Randabstand."""

import math

import numpy as np

from spotlab.workshop import skizze as sk
from spotlab.workshop import wegsuche


def _raum(wand_bis_y=3.5, groesse=100):
    """5 x 5 m freier Boden, Ursprung (0, 0), eine Wand bei x = 2.5 von y = 0 bis `wand_bis_y`."""
    s = sk.Skizze()
    s.ursprung = (0.0, 0.0)
    s.zustand = np.full((groesse, groesse), sk.FREI, np.uint8)
    s.zeit = np.zeros((groesse, groesse))
    zeilen = int(round(wand_bis_y / s.zelle_m))
    s.zustand[:zeilen, 50] = sk.WAND
    return s


def _wandabstand(s, x, y):
    zeilen, spalten = np.nonzero(s.zustand == sk.WAND)
    if not len(zeilen):
        return math.inf
    wx = s.ursprung[0] + (spalten + 0.5) * s.zelle_m
    wy = s.ursprung[1] + (zeilen + 0.5) * s.zelle_m
    return float(np.min(np.hypot(wx - x, wy - y)))


def _abgetastet(start, weg, schritt=0.02):
    punkte, a = [], start
    for b in weg:
        n = max(1, int(math.dist(a, b) / schritt))
        punkte += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]
        a = b
    return punkte


def test_um_die_wand_herum_mit_randabstand():
    s = _raum()
    weg = wegsuche.weg(s, (1.0, 1.0), (4.0, 1.0))
    assert weg is not None
    assert weg[-1] == (4.0, 1.0), "der letzte Punkt ist genau das Ziel"
    assert max(y for _, y in weg) > 3.5, "über das Ende der Wand"
    naechster = min(_wandabstand(s, x, y) for x, y in _abgetastet((1.0, 1.0), weg))
    assert naechster >= 0.3 - 0.05, naechster


def test_eine_geschlossene_wand_hat_keinen_weg():
    s = _raum(wand_bis_y=5.0)
    assert wegsuche.weg(s, (1.0, 1.0), (4.0, 1.0)) is None


def test_auf_freier_gerade_bleibt_nur_das_ziel():
    s = _raum()
    assert wegsuche.weg(s, (1.0, 1.0), (2.0, 1.2)) == [(2.0, 1.2)]


def test_der_koerperschatten_am_start_haelt_nicht_auf():
    """Unter und dicht um Spot sieht er nichts -- dort ist die Skizze unbekannt."""
    s = _raum()
    z, sp = s.zelle(1.0, 1.0)
    s.zustand[z - 8:z + 9, sp - 8:sp + 9] = sk.UNBEKANNT
    assert wegsuche.weg(s, (1.0, 1.0), (1.8, 2.5)) is not None


def test_unbekanntes_ausserhalb_des_koerpers_ist_zu():
    s = _raum()
    s.zustand[:, 70:74] = sk.UNBEKANNT            # ein unbekannter Streifen bei x = 3.5
    assert wegsuche.weg(s, (1.0, 1.0), (4.0, 4.5)) is None


def test_die_zielpruefung_sagt_warum():
    s = _raum()
    s.zustand[10:20, 80:90] = sk.UNBEKANNT
    assert wegsuche.pruefe_ziel(s, (1.0, 1.0), (4.0, 1.0), 0.3, 5.0) == ""
    assert "zu weit" in wegsuche.pruefe_ziel(s, (1.0, 1.0), (4.5, 4.9), 0.3, 5.0)
    assert "unbekannt" in wegsuche.pruefe_ziel(s, (1.0, 1.0), (4.25, 0.75), 0.3, 5.0)
    assert "unbekannt" in wegsuche.pruefe_ziel(s, (1.0, 1.0), (5.5, 1.0), 0.3, 5.0), "ausserhalb"
    assert "Wand" in wegsuche.pruefe_ziel(s, (1.0, 1.0), (2.52, 1.0), 0.3, 5.0)
    assert "Wand" in wegsuche.pruefe_ziel(s, (1.0, 1.0), (2.35, 1.0), 0.3, 5.0), "zu nah daran"


def test_eine_leere_skizze_hat_keinen_weg():
    s = sk.Skizze()
    assert wegsuche.weg(s, (0.0, 0.0), (1.0, 0.0)) is None
    assert "unbekannt" in wegsuche.pruefe_ziel(s, (0.0, 0.0), (1.0, 0.0), 0.3, 5.0)


def test_aufdicken_macht_eine_scheibe_ohne_umlauf():
    maske = np.zeros((9, 9), bool)
    maske[4, 4] = True
    dick = wegsuche.aufdicken(maske, 2)
    assert dick[4, 2] and dick[2, 4] and dick[5, 5] and not dick[2, 2]
    rand = np.zeros((5, 5), bool)
    rand[0, 0] = True
    assert not wegsuche.aufdicken(rand, 1)[4, 4], "keine Verschiebung über den Rand"
