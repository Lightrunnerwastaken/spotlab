import math

import pytest

from spotlab.welt.raum import Hindernis, Raum, RaumTag
from spotlab.welt.wahrnehmung import (
    GITTER_ZELLE_M,
    GITTER_ZELLEN,
    TAG_REICHWEITE_M,
    abstandsgitter,
    sichtbare_tags,
)


def _raum(tags=(), hindernisse=()):
    return Raum(
        name="T", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
        waende=(
            (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
            (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
        ),
        hindernisse=tuple(hindernisse), tags=tuple(tags),
    )


def test_tag_in_reichweite_wird_gemeldet():
    raum = _raum(tags=(RaumTag(1, 6.0, 5.0, 180.0),))
    gefunden = sichtbare_tags(raum, (5.0, 5.0, 0.0))
    assert len(gefunden) == 1
    tag, dx, dy = gefunden[0]
    assert tag.id == 1
    assert dx == pytest.approx(1.0)
    assert dy == pytest.approx(0.0, abs=1e-9)


def test_koerperframe_dreht_mit():
    """Derselbe Tag, Spot um 90 Grad gedreht: aus 'voraus' wird 'rechts'."""
    raum = _raum(tags=(RaumTag(1, 6.0, 5.0, 180.0),))
    _tag, dx, dy = sichtbare_tags(raum, (5.0, 5.0, math.pi / 2))[0]
    assert dx == pytest.approx(0.0, abs=1e-9)
    assert dy == pytest.approx(-1.0)


def test_tag_ausser_reichweite_wird_nicht_gemeldet():
    zu_weit = 5.0 + TAG_REICHWEITE_M + 0.1
    raum = _raum(tags=(RaumTag(1, zu_weit, 5.0, 180.0),))
    assert sichtbare_tags(raum, (5.0, 5.0, 0.0)) == []


def test_tag_hinter_einem_hindernis_wird_nicht_gemeldet():
    raum = _raum(
        tags=(RaumTag(1, 7.0, 5.0, 180.0),),
        hindernisse=(Hindernis("Kiste", (6.0, 4.5, 0.4, 1.0)),),
    )
    assert sichtbare_tags(raum, (5.0, 5.0, 0.0)) == []


def test_naechster_tag_steht_vorne():
    raum = _raum(tags=(
        RaumTag(2, 7.5, 5.0, 180.0),
        RaumTag(1, 6.0, 5.0, 180.0),
    ))
    assert [t.id for t, _dx, _dy in sichtbare_tags(raum, (5.0, 5.0, 0.0))] == [1, 2]


def test_gitter_hat_die_masse_des_echten_localgrid():
    werte, bekannt, ursprung = abstandsgitter(_raum(), (5.0, 5.0, 0.0))
    assert len(werte) == GITTER_ZELLEN and len(werte[0]) == GITTER_ZELLEN
    assert len(bekannt) == GITTER_ZELLEN
    kante = GITTER_ZELLEN * GITTER_ZELLE_M
    assert ursprung == pytest.approx((5.0 - kante / 2, 5.0 - kante / 2))


def test_gitter_kennt_die_wand():
    """Nahe der Wand muss der Abstand klein werden."""
    werte, _bekannt, ursprung = abstandsgitter(_raum(), (1.0, 5.0, 0.0))
    spalte = int(round((0.0 - ursprung[0]) / GITTER_ZELLE_M))
    zeile = int(round((5.0 - ursprung[1]) / GITTER_ZELLE_M))
    assert werte[zeile][spalte] < 0.1


def test_verdeckte_zellen_sind_unbekannt_nicht_frei():
    """Der Fehler, der einen Roboter in eine Wand faehrt: unbekannt != frei."""
    raum = _raum(hindernisse=(Hindernis("Kiste", (5.5, 4.5, 0.4, 1.0)),))
    _werte, bekannt, ursprung = abstandsgitter(raum, (5.0, 5.0, 0.0))
    zeile = int(round((5.0 - ursprung[1]) / GITTER_ZELLE_M))
    spalte_dahinter = int(round((6.8 - ursprung[0]) / GITTER_ZELLE_M))
    assert bekannt[zeile][spalte_dahinter] is False
    spalte_davor = int(round((5.2 - ursprung[0]) / GITTER_ZELLE_M))
    assert bekannt[zeile][spalte_davor] is True


def test_gitter_liefert_listen_keine_numpy_arrays():
    """welt/ gibt rohe Werte zurueck; sim.py macht daraus ein ObstacleGrid."""
    werte, bekannt, _ursprung = abstandsgitter(_raum(), (5.0, 5.0, 0.0))
    assert isinstance(werte, list) and isinstance(werte[0], list)
    assert isinstance(bekannt, list)


def test_gitter_ist_schnell_genug_fuer_zwei_hertz():
    """Bei 2 Hz darf ein Abruf nicht laenger als eine viertel Sekunde dauern."""
    import time

    raum = _raum(hindernisse=tuple(
        Hindernis(f"H{i}", (float(i), 2.0, 0.5, 0.5)) for i in range(8)
    ))
    beginn = time.perf_counter()
    abstandsgitter(raum, (5.0, 5.0, 0.0))
    assert time.perf_counter() - beginn < 0.25
