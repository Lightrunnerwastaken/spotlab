"""Der Merkpunkt: Spot merkt sich den Menschen als Punkt im Raum, nicht als Winkel im Bild.

Befund aus zwei Folge-Aufnahmen (25.09.2026): von 74 Verlusten über einer Sekunde
stand der Mensch 70-mal VOR Spot und wurde nur ein, zwei Bilder lang übersehen; in
der Lücke ging er im Mittel 0.4 m weit. Der Punkt im Raum überbrückt das -- und weil
er im Raum liegt, stimmen Peilung und Abstand auch, wenn Spot inzwischen gefahren ist.
"""

import math

import pytest

from spotlab.workshop import merkpunkt
from spotlab.workshop.folgen import Ziel


def _ziel(peilung, abstand, ort=(0.0, 0.0), gier=0.0, name="Körper"):
    return Ziel(peilung, abstand, name, gier=gier, ort=ort)


def _bei(x, y, name="Körper"):
    """Ein Ziel, gesehen von Spot im Ursprung mit Nase nach +x."""
    return _ziel(math.degrees(math.atan2(y, x)), math.hypot(x, y), name=name)


# ------------------------------------------------------------ Umrechnung


def test_vom_bild_in_den_raum_und_zurueck():
    """Spot bei (1, 2), Nase nach +y: ein Mensch 2 m voraus steht bei (1, 4)."""
    x, y = merkpunkt.in_raum((1.0, 2.0), math.radians(90.0), 0.0, 2.0)
    assert (x, y) == pytest.approx((1.0, 4.0))
    peilung, abstand = merkpunkt.vom_roboter((1.0, 2.0), math.radians(90.0), (1.0, 4.0))
    assert peilung == pytest.approx(0.0, abs=1e-9) and abstand == pytest.approx(2.0)
    # links ist positiv: bei Spot mit Nase nach +x liegt (0, 1) links
    assert merkpunkt.vom_roboter((0.0, 0.0), 0.0, (0.0, 1.0))[0] == pytest.approx(90.0)


# ------------------------------------------------------------ Festhalten


def test_der_punkt_bleibt_im_raum_waehrend_spot_faehrt_und_dreht():
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _ziel(0.0, 3.0))
    ziel = m.ziel(0.5, (1.0, 0.0), 0.0, _ziel(0.0, 3.0))
    assert ziel.bearing == pytest.approx(0.0, abs=1e-6) and ziel.distance == pytest.approx(2.0)
    ziel = m.ziel(0.5, (0.0, 0.0), math.radians(90.0), _ziel(0.0, 3.0))
    assert ziel.bearing == pytest.approx(-90.0), "nach links gedreht: der Mensch liegt jetzt rechts"


def test_das_gemerkte_ziel_behaelt_name_und_oberkante_der_vorlage():
    m = merkpunkt.Merkpunkt()
    vorlage = Ziel(0.0, 3.0, "Körper, Hüfte auf 0.95 m", bild_oben=8.0, gier=0.0, ort=(0.0, 0.0))
    m.aufnehmen(0.0, vorlage)
    ziel = m.ziel(0.2, (0.0, 0.0), 0.0, vorlage)
    assert ziel.name == vorlage.name and ziel.bild_oben == 8.0
    assert ziel.gier is None, "schon auf JETZT gerechnet -- nicht noch einmal nachführen"


def test_ohne_neue_erkennung_gilt_der_punkt_die_haltezeit_lang():
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _ziel(0.0, 3.0))
    assert m.aktiv(merkpunkt.HALTEN_S - 0.01)
    assert not m.aktiv(merkpunkt.HALTEN_S + 0.01)
    assert m.ziel(merkpunkt.HALTEN_S + 0.01, (0.0, 0.0), 0.0, _ziel(0.0, 3.0)) is None
    assert m.alter(1.0) == pytest.approx(1.0)


def test_die_haltezeit_ist_einstellbar():
    m = merkpunkt.Merkpunkt(halten_s=0.5)
    m.aufnehmen(0.0, _ziel(0.0, 3.0))
    assert not m.aktiv(0.6)


def test_ein_leerer_merkpunkt_ist_nicht_aktiv():
    m = merkpunkt.Merkpunkt()
    assert not m.aktiv(0.0) and m.alter(0.0) is None
    assert m.ziel(0.0, (0.0, 0.0), 0.0, _ziel(0.0, 3.0)) is None
    assert m.bericht(0.0) is None


def test_ein_ziel_ohne_ort_macht_den_merkpunkt_leer():
    """Ein Tag hat keinen Ort im Bild -- dann gibt es nichts zu merken."""
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _ziel(0.0, 3.0))
    m.aufnehmen(0.5, Ziel(0.0, 3.0, "Tag 3"))
    assert not m.aktiv(0.5)


# ------------------------------------------------------------ Vorhersage


def _seitwaerts(m, tempo=0.8, takte=4, takt_s=0.5):
    """Ein Mensch 3 m voraus, der nach links (+y) läuft; Spot steht im Ursprung."""
    for i in range(takte):
        m.aufnehmen(i * takt_s, _bei(3.0, tempo * i * takt_s))
    return (takte - 1) * takt_s, tempo * (takte - 1) * takt_s


def test_ein_laufender_mensch_wird_vorausgesagt_hoechstens_eine_sekunde():
    m = merkpunkt.Merkpunkt()
    t_letzt, y_letzt = _seitwaerts(m)
    vx, vy = m.tempo()
    assert vx == pytest.approx(0.0, abs=1e-6) and vy == pytest.approx(0.8)
    assert m.erwartet(t_letzt + 0.5) == pytest.approx((3.0, y_letzt + 0.4))
    x, y = m.erwartet(t_letzt + 2.5)
    assert y == pytest.approx(y_letzt + 0.8 * merkpunkt.VORHERSAGE_S), "weiter voraus wird nicht geraten"


def test_beim_umrunden_zeigt_das_gemerkte_ziel_in_die_laufrichtung():
    """Der Mensch läuft links an Spot vorbei und aus dem Bild: das Ziel wandert weiter
    nach links, Spot dreht also in dieselbe Richtung mit."""
    m = merkpunkt.Merkpunkt()
    t_letzt, y_letzt = _seitwaerts(m, tempo=1.0)
    zuletzt_gesehen = math.degrees(math.atan2(y_letzt, 3.0))
    ziel = m.ziel(t_letzt + 1.0, (0.0, 0.0), 0.0, _bei(3.0, y_letzt))
    assert ziel.bearing > zuletzt_gesehen + 5.0


def test_ein_einzelner_punkt_hat_kein_tempo():
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _ziel(0.0, 3.0))
    assert m.tempo() == (0.0, 0.0)
    assert m.erwartet(0.8) == pytest.approx((3.0, 0.0))


def test_ein_sprung_der_tiefe_macht_keinen_rennenden_menschen():
    """Fahrt 2 (25.09.2026): aus dem Abstand geschätzt lief der Mensch einmal 3.1 m/s --
    ein Messfehler, kein Sprint. Mehr als ein schnell gehender Mensch wird nicht angenommen."""
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _bei(3.0, 0.0))
    m.aufnehmen(0.5, _bei(5.0, 0.0))            # 4 m/s, noch im Fangkreis
    assert math.hypot(*m.tempo()) == pytest.approx(merkpunkt.MAX_MENSCH_M_S)


def test_alte_punkte_zaehlen_nicht_fuers_tempo():
    """Wer eben noch stand und jetzt geht, hat das Tempo von jetzt, nicht den Schnitt."""
    m = merkpunkt.Merkpunkt()
    for i in range(10):
        m.aufnehmen(i * 0.5, _bei(3.0, 0.0))                  # 4.5 s gestanden
    for i in range(1, 6):
        m.aufnehmen(4.5 + i * 0.5, _bei(3.0, 0.6 * i * 0.5))  # dann 0.6 m/s nach links
    assert m.tempo()[1] == pytest.approx(0.6, abs=0.1)


def test_das_weg_tempo_ist_der_anteil_vom_roboter_weg():
    m = merkpunkt.Merkpunkt()
    for i in range(4):
        m.aufnehmen(i * 0.5, _bei(3.0 + 0.8 * i * 0.5, 0.0))
    assert m.weg_tempo((0.0, 0.0)) == pytest.approx(0.8)
    m = merkpunkt.Merkpunkt()
    for i in range(4):
        m.aufnehmen(i * 0.5, _bei(3.0 - 0.5 * i * 0.5, 0.0))
    assert m.weg_tempo((0.0, 0.0)) == pytest.approx(-0.5)
    assert merkpunkt.Merkpunkt().weg_tempo((0.0, 0.0)) == 0.0


# ------------------------------------------------------------ Wählen


def test_ohne_merkpunkt_nimmt_er_den_naechsten():
    m = merkpunkt.Merkpunkt()
    nah, fern = _bei(2.0, 1.0, "nah"), _bei(4.0, 0.0, "fern")
    assert m.waehle(0.0, [fern, nah]) is nah


def _bestaetigt(x=3.0, y=0.0):
    """Ein Merkpunkt mit zwei passenden Erkennungen bei (x, y), die letzte bei t = 0.5."""
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _bei(x, y))
    m.aufnehmen(0.5, _bei(x, y))
    return m


def test_mit_merkpunkt_nimmt_er_den_bei_der_erwartung_nicht_den_naechsten():
    """Ein zweiter Mensch tritt näher vor Spot: er bleibt bei dem, dem er folgte."""
    m = _bestaetigt()
    fremd, er = _bei(1.6, 1.2, "fremd"), _bei(3.2, 0.1, "er")
    assert m.waehle(1.1, [fremd, er]) is er


def test_eine_erkennung_weit_neben_der_erwartung_ist_nicht_er():
    m = _bestaetigt()
    anderer = _bei(3.0, 3.5)
    assert m.waehle(1.1, [anderer]) is None
    assert "Merkpunkt" in m.befund and "daneben" in m.befund


def test_nach_der_haltezeit_nimmt_er_wieder_den_naechsten():
    m = _bestaetigt()
    anderer = _bei(3.0, 3.5)
    assert m.waehle(0.5 + merkpunkt.HALTEN_S + 0.1, [anderer]) is anderer


def test_ein_einzelner_ausreisser_haelt_den_echten_nicht_fern():
    """Fahrt 2, 25.6 s: eine Messung in 7.9 m, dann der Mensch in 4.4 m -- 3.5 m daneben.
    Ein Punkt aus EINER Erkennung ist noch keiner: er schützt vor niemandem, und die
    nächste Erkennung, die nicht passt, fängt neu an, statt ein Tempo zu erfinden."""
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _bei(7.9, 0.0))
    echt = _bei(4.4, 0.0)
    assert m.waehle(0.8, [echt]) is echt
    m.aufnehmen(0.8, echt)
    assert m.tempo() == (0.0, 0.0), "kein Sprint aus dem Ausreisser"
    assert m.erwartet(1.0) == pytest.approx((4.4, 0.0))


def test_nahe_am_zuletzt_gesehenen_ort_ist_er_auch_wenn_die_vorhersage_danebenliegt():
    """Fahrt 2, 52.3 s: aus zwei Punkten 1.5 m/s geschätzt, die Vorhersage schoss 1.9 m
    hinaus -- der Mensch stand 1.2 m neben dem Ort, an dem er zuletzt war."""
    m = merkpunkt.Merkpunkt()
    m.aufnehmen(0.0, _bei(3.0, 0.0))
    m.aufnehmen(0.8, _bei(3.0, 1.2))            # 1.5 m/s nach links
    zurueck = _bei(3.0, 0.3)                    # ... und wieder zurück
    assert m.waehle(1.6, [zurueck]) is zurueck


def test_der_fangkreis_waechst_mit_abstand_und_alter():
    """Die Tiefe streut weit weg mehr, und wer länger nicht gesehen wurde, kann weiter sein."""
    m = merkpunkt.Merkpunkt()
    assert m.fang_m(0.0, 5.0) > m.fang_m(0.0, 2.0)
    m.aufnehmen(0.0, _bei(3.0, 0.0))
    assert m.fang_m(2.0, 3.0) - m.fang_m(1.0, 3.0) == pytest.approx(merkpunkt.FANG_JE_S)
    assert merkpunkt.FANG_JE_S >= 1.0, "ein gehender Mensch ist nach einer Sekunde 1 m weiter"


def test_kandidaten_ohne_ort_werden_wie_bisher_nach_abstand_gewaehlt():
    m = _bestaetigt()
    nah, fern = Ziel(0.0, 2.0, "nah"), Ziel(0.0, 4.0, "fern")
    assert m.waehle(1.0, [fern, nah]) is nah


# ------------------------------------------------------------ Bericht


def test_der_bericht_sagt_wo_der_punkt_liegt_und_wie_alt_er_ist():
    m = merkpunkt.Merkpunkt()
    _seitwaerts(m)
    bericht = m.bericht(2.0)
    assert bericht["x"] == pytest.approx(3.0) and bericht["vy"] == pytest.approx(0.8)
    assert bericht["alter_s"] == pytest.approx(0.5)
