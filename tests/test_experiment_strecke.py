"""Die Strecke wird GEMESSEN, nicht eingetippt.

Ein eingetippter Wert waere die bequemste Fehlerquelle des ganzen Versuchs: die
Zeiten stimmten auf die Hundertstel, und jedes Tempo waere um denselben Faktor
falsch. Zwei AprilTags an den Enden, Spot misst dazwischen — und sagt, wie stark
seine Einzelmessungen streuen.
"""

import math

import pytest

from spotlab.errors import SpotlabError
from spotlab.experiment.strecke import (
    Punkt,
    fortschritt,
    miss_strecke,
    punkt_aus,
    querabstand,
)


def _probe(*eintraege):
    """Eine Abtastung: (Tag-Nummer, Peilung in Grad, Abstand in Metern)."""
    return list(eintraege)


def test_ein_punkt_liegt_dort_wo_die_peilung_hinzeigt():
    """Links positiv, wie ueberall im Projekt (`move(left=…)`, `richtung`)."""
    p = punkt_aus(90.0, 2.0)
    assert p.x == pytest.approx(0.0, abs=1e-9)
    assert p.y == pytest.approx(2.0)
    q = punkt_aus(0.0, 3.0)
    assert (q.x, q.y) == pytest.approx((3.0, 0.0))


def test_die_laenge_kommt_aus_den_beiden_tags():
    """Zwei Tags, 4 m auseinander, quer vor Spot."""
    proben = [_probe((1, 90.0, 2.0), (2, -90.0, 2.0)) for _ in range(5)]
    strecke = miss_strecke(proben)
    assert strecke.laenge_m == pytest.approx(4.0)
    assert strecke.tag_start == 1 and strecke.tag_ziel == 2


def test_die_streuung_wird_gemeldet_statt_weggemittelt():
    """Der Median glaettet — aber wie stark er glaetten musste, gehoert in den
    Bericht. Sonst sieht eine wackelige Messung aus wie eine ruhige."""
    proben = [
        _probe((1, 90.0, 2.0), (2, -90.0, 2.0)),
        _probe((1, 90.0, 2.0), (2, -90.0, 2.3)),
        _probe((1, 90.0, 2.0), (2, -90.0, 1.7)),
    ]
    strecke = miss_strecke(proben)
    assert strecke.laenge_m == pytest.approx(4.0)
    assert strecke.streuung_m == pytest.approx(0.3, abs=0.01)


def test_ein_ausreisser_kippt_die_laenge_nicht():
    """Ein einzelner Fehltreffer der Tag-Erkennung ist der Normalfall, nicht die
    Ausnahme. Der Median haelt ihn heraus, die Streuung zeigt ihn an."""
    proben = [_probe((1, 90.0, 2.0), (2, -90.0, 2.0)) for _ in range(4)]
    proben.append(_probe((1, 90.0, 2.0), (2, -90.0, 9.0)))
    strecke = miss_strecke(proben)
    assert strecke.laenge_m == pytest.approx(4.0)
    assert strecke.streuung_m > 4.0


def test_ohne_zwei_tags_gibt_es_keine_strecke():
    """Lieber gar keine Messung als eine geratene Laenge."""
    with pytest.raises(SpotlabError, match="zwei"):
        miss_strecke([_probe((1, 90.0, 2.0)) for _ in range(5)])


def test_zu_wenige_proben_sind_keine_messung():
    proben = [_probe((1, 90.0, 2.0), (2, -90.0, 2.0))]
    with pytest.raises(SpotlabError, match="Abtastungen"):
        miss_strecke(proben, mindestproben=3)


def test_die_tags_lassen_sich_ausdruecklich_nennen():
    """Im Gang haengen mehr Tags als die zwei des Versuchs."""
    proben = [
        _probe((1, 90.0, 2.0), (2, -90.0, 2.0), (7, 0.0, 1.0)) for _ in range(5)
    ]
    strecke = miss_strecke(proben, tag_start=2, tag_ziel=1)
    assert (strecke.tag_start, strecke.tag_ziel) == (2, 1)
    assert strecke.laenge_m == pytest.approx(4.0)


def test_ein_genanntes_tag_das_fehlt_ist_ein_fehler():
    proben = [_probe((1, 90.0, 2.0), (2, -90.0, 2.0)) for _ in range(5)]
    with pytest.raises(SpotlabError, match="9"):
        miss_strecke(proben, tag_start=1, tag_ziel=9)


# ------------------------------------------------------- Lage auf der Strecke


def _quer_strecke():
    proben = [_probe((1, 90.0, 2.0), (2, -90.0, 2.0)) for _ in range(5)]
    return miss_strecke(proben)


def test_fortschritt_misst_meter_ab_dem_startpunkt():
    strecke = _quer_strecke()
    assert fortschritt(strecke, Punkt(0.0, 2.0)) == pytest.approx(0.0)
    assert fortschritt(strecke, Punkt(0.0, -2.0)) == pytest.approx(4.0)
    assert fortschritt(strecke, Punkt(0.0, 0.0)) == pytest.approx(2.0)


def test_fortschritt_darf_vor_dem_start_und_hinter_dem_ziel_liegen():
    """Sonst begaenne die Zeit erst beim ersten Bild NACH der Linie."""
    strecke = _quer_strecke()
    assert fortschritt(strecke, Punkt(0.0, 3.0)) == pytest.approx(-1.0)
    assert fortschritt(strecke, Punkt(0.0, -3.0)) == pytest.approx(5.0)


def test_querabstand_trennt_den_gang_vom_rest_des_raums():
    """Wer zwei Meter neben der Strecke steht, laeuft sie nicht."""
    strecke = _quer_strecke()
    assert querabstand(strecke, Punkt(0.0, 0.0)) == pytest.approx(0.0, abs=1e-9)
    assert querabstand(strecke, Punkt(1.5, 0.0)) == pytest.approx(1.5)
    assert querabstand(strecke, Punkt(-1.5, 0.0)) == pytest.approx(1.5)


def test_eine_schraege_strecke_rechnet_genauso():
    """Spot steht selten sauber quer zum Gang."""
    a, b = punkt_aus(45.0, math.sqrt(2)), punkt_aus(0.0, 5.0)
    proben = [_probe((1, 45.0, math.sqrt(2)), (2, 0.0, 5.0)) for _ in range(5)]
    strecke = miss_strecke(proben)
    assert strecke.laenge_m == pytest.approx(math.dist((a.x, a.y), (b.x, b.y)))
    assert fortschritt(strecke, a) == pytest.approx(0.0)
    assert fortschritt(strecke, b) == pytest.approx(strecke.laenge_m)
