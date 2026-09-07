"""Sperrzonen: eine Regel auf dem Boden, kein Hindernis.

Anlass (07.09.2026): der Explorer fuhr am echten Spot dicht an eine Glasfront.
Glas loest kein Sensor des Roboters -- die Stereokameras schauen hindurch, das
Hindernisgitter meldet frei. Wer es weiss, ist der Mensch; er traegt es ein.
"""

import pytest

from spotlab.welt.kollision import ZONE_RAND_M, bewege_mit_hoehe, zone_bei
from spotlab.welt.raum import Raum, Sperrzone, raum_laden_pfad, raum_speichern


def _raum(*zonen, waende=()):
    return Raum(name="T", beschreibung="", start=(1.0, 1.0, 0.0), groesse=(10.0, 10.0),
                waende=waende, sperrzonen=zonen)


ZONE = Sperrzone(name="Glasfront", x=5.0, y=5.0, breite=4.0, tiefe=1.0, grund="Glas")


# ------------------------------------------------------------------ Geometrie


def test_die_zone_ist_ein_rechteck_wie_ein_block():
    ecken = ZONE.ecken()
    assert len(ecken) == 4
    xs = [x for x, _ in ecken]
    assert min(xs) == pytest.approx(3.0) and max(xs) == pytest.approx(7.0)
    assert ZONE.lokal(5.0, 5.0) == pytest.approx((0.0, 0.0))


def test_zone_bei_haelt_abstand_und_kennt_die_drehung():
    raum = _raum(ZONE)
    assert zone_bei(raum, 5.0, 5.0) == "Glasfront"
    # Der Rand: Zone bis y = 5.5, dazu Roboterradius und Sicherheitsabstand.
    assert zone_bei(raum, 5.0, 5.5 + ZONE_RAND_M + 0.4) is None
    assert zone_bei(raum, 5.0, 5.6) == "Glasfront", "der Rand gehoert dazu"
    assert zone_bei(raum, 9.5, 5.0) is None
    gedreht = _raum(Sperrzone(name="Quer", x=5.0, y=5.0, breite=4.0, tiefe=1.0, drehung=90.0))
    assert zone_bei(gedreht, 5.0, 6.5) == "Quer", "gedreht reicht die Zone in y"
    assert zone_bei(gedreht, 6.6, 5.0) is None


def test_ohne_zonen_kostet_es_nichts():
    assert zone_bei(_raum(), 5.0, 5.0) is None


# ------------------------------------------------------------------ Bewegung


def test_der_sim_bleibt_an_der_zonengrenze_stehen():
    """Wie an einer Wand -- nur heisst das Hindernis nach der Zone, damit im
    Protokoll steht, WARUM der Roboter nicht weiterfuhr."""
    raum = _raum(ZONE)
    pose, z, getroffen = bewege_mit_hoehe(raum, (5.0, 2.0, 0.0), (5.0, 5.0, 0.0), 0.0, ())
    assert getroffen == "Sperrzone Glasfront"
    assert pose[1] < 5.5 - ZONE_RAND_M, "vor der Zone stehengeblieben"
    assert pose[1] > 3.0, "nicht schon am Start blockiert"


def test_neben_der_zone_faehrt_er_weiter():
    raum = _raum(ZONE)
    pose, _z, getroffen = bewege_mit_hoehe(raum, (9.0, 2.0, 0.0), (9.0, 8.0, 0.0), 0.0, ())
    assert getroffen is None and pose[1] == pytest.approx(8.0)


def test_aus_der_zone_heraus_geht_immer():
    """Wer drinsteht (von Hand hingestellt, Drift), muss herauskommen."""
    raum = _raum(ZONE)
    pose, _z, getroffen = bewege_mit_hoehe(raum, (5.0, 5.0, 0.0), (5.0, 2.0, 0.0), 0.0, ())
    assert getroffen is None and pose[1] == pytest.approx(2.0)


# ------------------------------------------------- eine Regel, keine Geometrie


def test_die_zone_steht_in_keinem_hindernisgitter():
    """Der ganze Zweck: die Zone haelt dort, wo der SENSOR frei sagt. Taucht sie
    im Gitter auf, ist sie eine unsichtbare Wand -- und ein Programm, das der
    freien Strecke folgt, wuerde sie umfahren statt sie zu respektieren."""
    from spotlab.welt.wahrnehmung import abstandsgitter

    assert abstandsgitter(_raum(), (5.0, 3.0, 0.0)) == abstandsgitter(_raum(ZONE), (5.0, 3.0, 0.0))


def test_ein_start_in_der_zone_faellt_bei_der_pruefung_auf():
    from spotlab.welt.bearbeitung import pruefe

    drin = Raum(name="T", beschreibung="", start=(5.0, 5.0, 0.0), groesse=(10.0, 10.0),
                sperrzonen=(ZONE,))
    hinweise = " ".join(pruefe(drin))
    assert "Glasfront" in hinweise


# ---------------------------------------------------------------- Raumformat


def test_zonen_ueberstehen_speichern_und_laden(tmp_path):
    pfad = tmp_path / "zone.toml"
    raum_speichern(_raum(ZONE, Sperrzone(name="Treppenabgang", x=1.0, y=8.0, breite=2.0,
                                         tiefe=2.0, drehung=30.0, grund="Absturz")), pfad)
    text = pfad.read_text(encoding="utf-8")
    assert "fassung      = 5" in text and "[[sperrzone]]" in text and "Glas" in text

    wieder = raum_laden_pfad(pfad)
    assert [z.name for z in wieder.sperrzonen] == ["Glasfront", "Treppenabgang"]
    assert wieder.sperrzonen[0].grund == "Glas"
    assert wieder.sperrzonen[1].drehung == pytest.approx(30.0)


def test_ein_raum_ohne_zonen_bleibt_die_alte_datei(tmp_path):
    """Fassung 5 nur, wo sie noetig ist -- sonst muesste jeder aeltere Leser
    aufgeben, obwohl sich nichts geaendert hat."""
    pfad = tmp_path / "leer.toml"
    raum_speichern(Raum(name="T", beschreibung="", start=(1.0, 1.0, 0.0),
                        groesse=(4.0, 4.0)), pfad)
    text = pfad.read_text(encoding="utf-8")
    assert "fassung" not in text and "sperrzone" not in text


def test_alte_raeume_laden_weiter(tmp_path):
    pfad = tmp_path / "alt.toml"
    pfad.write_text('[raum]\nname = "A"\nbeschreibung = ""\nstart = [1.0, 1.0, 0.0]\n'
                    'groesse = [5.0, 5.0]\nwaende = []\n', encoding="utf-8")
    assert raum_laden_pfad(pfad).sperrzonen == ()


# ----------------------------------------------- die Bruecke zur Karte


def test_aus_karte_und_nach_karte_sind_umkehrbar():
    """Der rekonstruierte Raum ist gegen die GraphNav-Karte GEDREHT und
    VERSCHOBEN (`ausrichten`). Ohne diese Beziehung weiss ein Lauf am echten
    Roboter nicht, wo im Raum er steht -- und eine Zone waere wertlos."""
    from spotlab.welt.raum import Kartenbezug, aus_karte, nach_karte

    raum = Raum(name="T", beschreibung="", start=(0.0, 0.0, 0.0),
                karte=Kartenbezug(name="k", dreh=90.0, versatz_x=2.0, versatz_y=-1.0, z_min=1.5))
    # 90 Grad drehen: (1, 0) -> (0, 1), dann der Versatz.
    assert aus_karte(raum, 1.0, 0.0) == pytest.approx((2.0, 0.0))
    assert nach_karte(raum, 2.0, 0.0) == pytest.approx((1.0, 0.0))
    hin = aus_karte(raum, -3.5, 7.25, grad=10.0)
    assert nach_karte(raum, *hin) == pytest.approx((-3.5, 7.25, 10.0))


def test_ohne_kartenbezug_wird_nicht_geraten():
    """Eine Zone an der falschen Stelle ist schlimmer als keine."""
    from spotlab.welt.raum import aus_karte, nach_karte

    assert aus_karte(_raum(), 1.0, 2.0) is None
    assert nach_karte(_raum(), 1.0, 2.0) is None


def test_der_kartenbezug_ueberlebt_speichern_und_laden(tmp_path):
    from spotlab.welt.raum import Kartenbezug

    pfad = tmp_path / "mitkarte.toml"
    raum_speichern(Raum(name="T", beschreibung="", start=(1.0, 1.0, 0.0),
                        karte=Kartenbezug(name="map_catacombs_01", dreh=-3.0,
                                          versatz_x=16.4, versatz_y=27.6, z_min=1.83)), pfad)
    k = raum_laden_pfad(pfad).karte
    assert k.name == "map_catacombs_01" and k.dreh == pytest.approx(-3.0)
    assert (k.versatz_x, k.versatz_y, k.z_min) == pytest.approx((16.4, 27.6, 1.83))


def test_zone_voraus_schaut_nach_vorn_nicht_nach_hinten():
    """Der Weg aus der Falle darf nicht zugehen: hinter dem Roboter zaehlt die
    Zone nicht, sonst koennte er sich nie herausfahren."""
    from spotlab.welt.kollision import zone_voraus

    raum = _raum(ZONE)                       # Zone um (5, 5), 4 x 1 m
    assert zone_voraus(raum, (5.0, 3.0, 90.0), strecke=2.0) == "Glasfront"
    assert zone_voraus(raum, (5.0, 3.0, 270.0), strecke=2.0) is None, "rueckwaerts frei"
    assert zone_voraus(raum, (5.0, 3.0, 90.0), strecke=0.5) is None, "noch weit genug weg"
    assert zone_voraus(raum, (5.0, 3.0, 0.0), strecke=2.0) is None, "quer daran vorbei"
    assert zone_voraus(_raum(), (5.0, 3.0, 90.0)) is None
