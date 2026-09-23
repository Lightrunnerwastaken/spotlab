import math

import pytest

from spotlab.welt.raum import Block, Raum, RaumTag
from spotlab.welt.wahrnehmung import (
    GITTER_ZELLE_M,
    GITTER_ZELLEN,
    TAG_REICHWEITE_M,
    abstandsgitter,
    sichtbare_tags,
)


def _raum(tags=(), bloecke=()):
    return Raum(
        name="T", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
        waende=(
            (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
            (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
        ),
        bloecke=tuple(bloecke), tags=tuple(tags),
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
        bloecke=(Block("Kiste", 6.2, 5.0, 0.4, 1.0),),
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
    """Der Fehler, der einen Roboter in eine Wand faehrt: unbekannt != frei.

    (Die Kiste steht seit dem 23.09.2026 1.2 m voraus statt 0.7: „davor“ muss
    ausserhalb des Koerperschattens liegen, sonst prueft der Test den Schatten.)"""
    raum = _raum(bloecke=(Block("Kiste", 6.2, 5.0, 0.4, 1.0),))
    _werte, bekannt, ursprung = abstandsgitter(raum, (5.0, 5.0, 0.0))
    zeile = int(round((5.0 - ursprung[1]) / GITTER_ZELLE_M))
    spalte_dahinter = int(round((6.8 - ursprung[0]) / GITTER_ZELLE_M))
    assert bekannt[zeile][spalte_dahinter] is False
    spalte_davor = int(round((5.7 - ursprung[0]) / GITTER_ZELLE_M))
    assert bekannt[zeile][spalte_davor] is True


def test_der_koerperschatten_ist_unbekannt_wie_am_roboter():
    """Beta-Prüfung 23.09.2026 (p10): der 2D-Sim sah direkt vor und unter dem
    Koerper -- `look()` meldete dort „clear“ und „blocked“, wo MuJoCo und der
    echte Spot nichts sehen. Gemessen am echten Gitter vom 12.08.2026: 91 %
    unbekannt bis 0.3 m, 65 % bis 0.5 m, dann 33 % und ab 0.7 m der Grund-
    anteil; MuJoCo: erste bekannte Zelle je Richtung bei 0.36 bis 0.8 m."""
    import math

    from spotlab.welt.wahrnehmung import KOERPERSCHATTEN_M

    werte, bekannt, ursprung = abstandsgitter(_raum(), (5.0, 5.0, 0.3))
    for zeile in range(GITTER_ZELLEN):
        for spalte in range(GITTER_ZELLEN):
            x = ursprung[0] + spalte * GITTER_ZELLE_M
            y = ursprung[1] + zeile * GITTER_ZELLE_M
            abstand = math.hypot(x - 5.0, y - 5.0)
            if abstand < KOERPERSCHATTEN_M:
                assert bekannt[zeile][spalte] is False, (x, y)
            elif abstand < 1.5:
                assert bekannt[zeile][spalte] is True, (x, y)   # freie Sicht im leeren Raum


def test_der_schatten_endet_bevor_free_distance_unbekanntes_fuer_zu_haelt():
    """`free_distance` ueberspringt Unbekanntes nur bis FREI_AB_M. Reichte der
    Schatten bis dorthin, endete JEDE freie Strecke am Schattenrand -- die
    naechste Zelle ab FREI_AB_M muss bekannt sein (eine Zelle Luft fuer das
    Runden auf die Zellmitte)."""
    from spotlab.backends.base import FREI_AB_M
    from spotlab.welt.wahrnehmung import KOERPERSCHATTEN_M

    assert KOERPERSCHATTEN_M <= FREI_AB_M - GITTER_ZELLE_M


def test_gitter_liefert_listen_keine_numpy_arrays():
    """welt/ gibt rohe Werte zurueck; sim.py macht daraus ein ObstacleGrid."""
    werte, bekannt, _ursprung = abstandsgitter(_raum(), (5.0, 5.0, 0.0))
    assert isinstance(werte, list) and isinstance(werte[0], list)
    assert isinstance(bekannt, list)


def test_gitter_ist_schnell_genug_fuer_zwei_hertz():
    """Bei 2 Hz darf ein Abruf nicht laenger als eine viertel Sekunde dauern."""
    import time

    raum = _raum(bloecke=tuple(
        Block(f"H{i}", i + 0.25, 2.25, 0.5, 0.5) for i in range(8)
    ))
    beginn = time.perf_counter()
    abstandsgitter(raum, (5.0, 5.0, 0.0))
    assert time.perf_counter() - beginn < 0.25


# ------------------------------------------------------- gedrehte Bloecke


def _wert_bei(raum, pose, x, y):
    from spotlab.welt.wahrnehmung import GITTER_ZELLE_M, abstandsgitter

    werte, _bekannt, ursprung = abstandsgitter(raum, pose)
    spalte = int(round((x - ursprung[0]) / GITTER_ZELLE_M))
    zeile = int(round((y - ursprung[1]) / GITTER_ZELLE_M))
    return werte[zeile][spalte]


def test_das_gitter_kennt_gedrehte_bloecke():
    raum = Raum(name="G", beschreibung="", start=(5.0, 5.0, 0.0),
                bloecke=(Block("Balken", 5.0, 5.0, 2.0, 0.5, drehung=45.0),))
    pose = (5.0, 5.0, 0.0)
    assert _wert_bei(raum, pose, 5.0 + 0.9 * 0.7071, 5.0 + 0.9 * 0.7071) == pytest.approx(0.0, abs=0.03)
    assert _wert_bei(raum, pose, 5.6, 5.0) == pytest.approx(0.174, abs=0.03)


def test_die_wanddicke_zaehlt_im_gitter():
    raum = Raum(name="W", beschreibung="", start=(5.0, 5.0, 0.0),
                waende=((0.0, 4.0, 10.0, 4.0),), wand_dicke=0.10)
    # 0.30 m vor der Wandlinie bleiben 0.25 m bis zur Wandflaeche.
    assert _wert_bei(raum, (5.0, 5.0, 0.0), 5.0, 4.30) == pytest.approx(0.25, abs=0.03)


# ------------------------------------------------------------- Hoehe


def _gitterwert(gitter, ursprung, x, y):
    spalte = int(round((x - ursprung[0]) / GITTER_ZELLE_M))
    zeile = int(round((y - ursprung[1]) / GITTER_ZELLE_M))
    return gitter[zeile][spalte]


def test_klippe_ist_belegt_treppe_frei_und_block_oben_unsichtbar_von_unten():
    from spotlab.welt.kollision import klippen_von
    from spotlab.welt.raum import Boden

    raum = _raum(bloecke=(Block("K", 7.0, 5.0, 0.5, 0.5, z=1.0),))
    raum = Raum(name=raum.name, beschreibung="", groesse=raum.groesse, start=raum.start,
                waende=raum.waende, bloecke=raum.bloecke,
                boeden=(Boden("T", 3.5, 5.0, 2.0, 2.0, anstieg=1.0, stufen=6),     # x 2.5..4.5
                        Boden("P", 6.0, 5.0, 3.0, 2.0, z=1.0)))                     # x 4.5..7.5
    kanten = klippen_von(raum)
    pose = (5.0, 3.0, 0.0)                                                          # unten, neben dem Podest
    werte, bekannt, ursprung = abstandsgitter(raum, pose, z=0.0, klippen_=kanten)
    assert _gitterwert(werte, ursprung, 5.0, 4.0) == pytest.approx(0.0, abs=GITTER_ZELLE_M)   # Podestkante y = 4
    assert _gitterwert(werte, ursprung, 3.5, 4.5) > 0.3                                # auf der Treppe frei
    assert _gitterwert(werte, ursprung, 5.0, 3.0) > 0.5                                # der Block oben zaehlt unten nicht
    oben = (6.0, 5.0, 0.0)
    werte, bekannt, ursprung = abstandsgitter(raum, oben, z=1.0, klippen_=kanten)
    assert _gitterwert(werte, ursprung, 6.75, 5.0) == pytest.approx(0.0, abs=GITTER_ZELLE_M)  # der Block, von oben


def test_ein_tag_auf_der_anderen_ebene_ist_unsichtbar():
    from spotlab.welt.raum import Boden

    raum = _raum(tags=(RaumTag(3, 3.0, 5.0, 180.0, z=2.0),))
    raum = Raum(name=raum.name, beschreibung="", groesse=raum.groesse, start=raum.start,
                waende=raum.waende, tags=raum.tags, boeden=(Boden("P", 3.0, 5.0, 2, 2, z=2.0),))
    assert sichtbare_tags(raum, (2.0, 5.0, 0.0), z=0.0) == []
    assert len(sichtbare_tags(raum, (2.0, 5.0, 0.0), z=2.0)) == 1
    assert len(sichtbare_tags(raum, (2.0, 5.0, 0.0))) == 0                          # ohne z: z = 0


def test_das_gitter_meldet_die_gelaendekante():
    from spotlab.welt import gelaende as g
    from spotlab.welt.kollision import klippen_von

    raum = Raum("G", "", (0.5, 1.0, 0.0),
                gelaende=g.gitter(0.0, 0.0, 0.2, 11, 31, lambda x, y: 0.0 if x < 3.0 else 0.6))
    werte, bekannt, ursprung = abstandsgitter(raum, (2.0, 1.0, 0.0), z=0.0, klippen_=klippen_von(raum))
    assert _gitterwert(werte, ursprung, 2.9, 1.0) < 0.15
    assert _gitterwert(werte, ursprung, 2.0, 1.0) > 0.5


def test_viele_klippen_rechnet_das_gitter_vektorisiert():
    """Ein Gelaende hat Hunderte Klippenstrecken; je Strecke einmal ueber alle Zellen zu
    rechnen kostete 0.57 s je Abruf (Katakomben, 07.09.2026)."""
    import random
    import time

    import numpy as np

    from spotlab.welt.wahrnehmung import _zur_strecke

    # 30 x 30 m wie eine Karte, 2000 Klippenstuecke ueberall -- das Gitter sieht nur 3.84 m.
    raum = Raum(name="K", beschreibung="", start=(15.0, 15.0, 0.0),
                waende=((0, 0, 30, 0), (30, 0, 30, 30), (30, 30, 0, 30), (0, 30, 0, 0)))
    zufall = random.Random(1)
    klippen = []
    for _ in range(2000):
        x, y = zufall.uniform(0.5, 29.5), zufall.uniform(0.5, 29.5)
        klippen.append((x, y, x + 0.2, y))
    beginn = time.perf_counter()
    werte, _bekannt, ursprung = abstandsgitter(raum, (15.0, 15.0, 0.0), z=0.0, klippen_=klippen)
    assert time.perf_counter() - beginn < 0.25
    # Nahe der Mitte ist der Wert der Abstand zur naechsten Klippe -- gegen alle gerechnet.
    for x, y in ((15.0, 15.0), (14.6, 15.4), (15.5, 14.4)):
        cx = ursprung[0] + round((x - ursprung[0]) / GITTER_ZELLE_M) * GITTER_ZELLE_M
        cy = ursprung[1] + round((y - ursprung[1]) / GITTER_ZELLE_M) * GITTER_ZELLE_M
        xs, ys = np.array([cx]), np.array([cy])
        erwartet = min(float(_zur_strecke(xs, ys, *k)[0]) for k in klippen)
        assert _gitterwert(werte, ursprung, cx, cy) == pytest.approx(erwartet, abs=1e-6)
