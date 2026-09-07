"""Ueberhaenge aus Tiefenbildern -- was das Hindernisgitter nicht sieht.

Die Fixtures sind ECHTE Aufnahmen vom Schul-Spot (12.08.2026, Herkunft in
`tests/daten/tiefe_real_20260812/HERKUNFT.md`), keine Attrappen: an ihnen
haengt die Aussage, dass die Rechnung stimmt. Der Boden muss auf der
gemessenen Standhoehe landen, ein freier Gang leer bleiben und die Tischreihe
auftauchen.
"""

import math
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("bosdyn.api")

from spotlab.backends.real import tiefe  # noqa: E402
from spotlab.errors import SpotlabError  # noqa: E402

DATEN = Path(__file__).parent / "daten" / "tiefe_real_20260812"
STANDHOEHE_M = 0.512            # gemessen am Schul-Spot (kalibrierung/gang.json)


def _echt(lage, kamera="frontleft"):
    from bosdyn.api import image_pb2

    antwort = image_pb2.ImageResponse()
    antwort.ParseFromString((DATEN / f"{lage}_{kamera}_depth.pb").read_bytes())
    return antwort


# ------------------------------------------------------------- Lochkamera


def test_die_punktwolke_folgt_dem_lochkameramodell():
    """z aus dem Rohwert durch die Skala, x und y aus der Bildlage."""
    bild = np.array([[0, 2000], [1000, 0]], dtype=np.uint16)
    punkte = tiefe.punktwolke(bild, fx=100.0, fy=200.0, cx=1.0, cy=0.5, skala=1000.0)

    assert punkte.shape == (2, 3), "die beiden Null-Pixel sind KEINE Messung"
    # Pixel (v=0, u=1): z = 2 m, x = (1-1)*2/100 = 0, y = (0-0.5)*2/200 = -0.005
    assert punkte[0] == pytest.approx([0.0, -0.005, 2.0])
    # Pixel (v=1, u=0): z = 1 m, x = (0-1)*1/100, y = (1-0.5)*1/200
    assert punkte[1] == pytest.approx([-0.01, 0.0025, 1.0])


def test_der_schritt_tastet_aus_und_behaelt_die_bildlage():
    """Jeder zweite Pixel -- aber mit seiner ECHTEN Spalte, sonst wandert alles."""
    bild = np.zeros((4, 4), dtype=np.uint16)
    bild[2, 2] = 1000
    punkte = tiefe.punktwolke(bild, fx=100.0, fy=100.0, cx=0.0, cy=0.0, skala=1000.0, schritt=2)
    assert punkte.shape == (1, 3)
    assert punkte[0] == pytest.approx([0.02, 0.02, 1.0])       # u = v = 2, nicht 1


def test_ohne_messung_bleibt_die_wolke_leer():
    leer = tiefe.punktwolke(np.zeros((3, 3), dtype=np.uint16), 1.0, 1.0, 0.0, 0.0, skala=1.0)
    assert leer.shape == (0, 3)


def test_umgerechnet_dreht_und_verschiebt():
    punkte = np.array([[1.0, 0.0, 0.0]])
    matrix = np.array([[0.0, -1.0, 0.0, 2.0],       # 90 Grad um z, dann +2 in x
                       [1.0, 0.0, 0.0, 0.0],
                       [0.0, 0.0, 1.0, 0.0],
                       [0.0, 0.0, 0.0, 1.0]])
    assert tiefe.umgerechnet(punkte, matrix)[0] == pytest.approx([2.0, 1.0, 0.0])


def test_aufgerichtet_dreht_nick_und_roll_heraus():
    """Das Hoehenband haengt an der Schwerkraft, nicht am Ruecken des Roboters:
    auf einer Rampe kippt der Koerperrahmen, das Band darf nicht mitkippen.
    Nase hoch ist NEGATIV -- dieselbe Konvention wie in `welt/hoehe.py`."""
    voraus = np.array([[1.0, 0.0, 0.0]])
    nase_runter = tiefe.aufgerichtet(voraus, roll=0.0, nick=math.radians(10.0))
    assert nase_runter[0][2] == pytest.approx(-math.sin(math.radians(10.0)))
    assert tiefe.aufgerichtet(voraus, roll=0.0, nick=0.0)[0] == pytest.approx([1.0, 0.0, 0.0])
    seite = tiefe.aufgerichtet(np.array([[0.0, 1.0, 0.0]]), roll=math.radians(10.0), nick=0.0)
    assert seite[0][2] == pytest.approx(math.sin(math.radians(10.0)))


# ---------------------------------------------------------------- Ueberhang


def test_ueberhang_nimmt_nur_das_hoehenband():
    """Boden und Zimmerdecke sind kein Ueberhang -- eine Tischplatte schon."""
    punkte = np.array([
        [1.0, 0.0, -0.51],        # Boden
        [1.0, 0.0, 0.20],         # Tischplatte, 0.7 m ueber dem Boden
        [1.0, 0.0, 2.00],         # Zimmerdecke
        [1.0, 0.0, -0.05],        # unter der Koerpermitte: Sache des Gitters
    ])
    band = tiefe.ueberhang(punkte)
    assert band.shape == (1, 3) and band[0][2] == pytest.approx(0.20)


def test_der_eigene_rumpf_zaehlt_nicht_als_ueberhang():
    """Die Kameras sehen den eigenen Ruecken und die eigenen Beine. Wer das
    mitzaehlt, meldet dauernd Ueberhang und der Roboter faehrt nie wieder."""
    punkte = np.array([
        [0.2, 0.0, 0.15],         # auf dem eigenen Ruecken
        [1.0, 0.0, 0.15],         # davor: echter Ueberhang
    ])
    band = tiefe.ueberhang(punkte)
    assert band.shape == (1, 3) and band[0][0] == pytest.approx(1.0)


def test_kopfraum_meldet_den_naechsten_punkt_im_korridor():
    punkte = np.array([[1.5, 0.0, 0.2]] * 30 + [[0.8, 0.0, 0.2]] * 30)
    assert tiefe.kopfraum(punkte) == pytest.approx(0.8)


def test_neben_dem_korridor_und_zu_weit_weg_zaehlt_nicht():
    daneben = np.array([[1.0, 1.2, 0.2]] * 30)          # 1.2 m seitlich
    zu_weit = np.array([[5.0, 0.0, 0.2]] * 30)
    assert tiefe.kopfraum(daneben) is None
    assert tiefe.kopfraum(zu_weit) is None
    assert tiefe.kopfraum(np.zeros((0, 3))) is None


def test_ein_paar_pixel_sind_noch_kein_tisch():
    """Ein einzelner Ausreisser darf den Roboter nicht anhalten -- erst eine
    Flaeche zaehlt. Dieselbe Regel wie beim Gitter: Freiraum ist billig,
    ein Hindernis braucht Belege."""
    rauschen = np.array([[1.0, 0.0, 0.2]] * (tiefe.MIN_PUNKTE - 1))
    assert tiefe.kopfraum(rauschen) is None
    assert tiefe.kopfraum(np.array([[1.0, 0.0, 0.2]] * tiefe.MIN_PUNKTE)) == pytest.approx(1.0)


# ------------------------------------------------- gegen die echte Aufnahme


def test_das_echte_tiefenbild_legt_den_boden_auf_die_standhoehe():
    """Die Probe aufs Exempel fuer Intrinsik UND Extrinsik: der Boden muss im
    Koerperrahmen bei minus der Standhoehe liegen. Ein Vorzeichenfehler oder
    eine verdrehte Achse faellt hier sofort auf."""
    punkte = tiefe.punkte_aus_bild(_echt("freier_gang"))
    assert len(punkte) > 10_000
    boden = np.median(punkte[:, 2])
    assert boden == pytest.approx(-STANDHOEHE_M, abs=0.05), f"Boden bei {boden:.3f} m"


def test_der_freie_gang_meldet_keinen_ueberhang():
    """Kein Fehlalarm auf freier Flaeche -- sonst ist das Tor im Betrieb wertlos."""
    bilder = [_echt("freier_gang", k) for k in ("frontleft", "frontright")]
    punkte = tiefe.ueberhang_aus_bildern(bilder)
    assert tiefe.kopfraum(punkte) is None


def test_die_tischreihe_wird_erkannt():
    """Takt 428 derselben Fahrt: etwas haengt 0.72 m voraus, rund 0.7 m ueber
    dem Boden. Genau diese Bauart hat den Explorer am 07.09.2026 gefangen."""
    bilder = [_echt("tischreihe", k) for k in ("frontleft", "frontright")]
    punkte = tiefe.ueberhang_aus_bildern(bilder)
    abstand = tiefe.kopfraum(punkte)
    assert abstand is not None and 0.6 < abstand < 0.9, abstand
    hoehen = punkte[:, 2]
    assert 0.05 < np.median(hoehen) < 0.4, "Tischhoehe, nicht Zimmerdecke"


def test_ohne_tiefenbild_wird_es_laut():
    """Fehlende Daten sind kein freier Weg. Der Aufrufer muss den Unterschied
    zwischen „nichts da" und „nichts im Weg" sehen koennen."""
    from bosdyn.api import image_pb2

    grau = image_pb2.ImageResponse()
    grau.source.name = "frontleft_fisheye_image"
    grau.source.image_type = image_pb2.ImageSource.IMAGE_TYPE_VISUAL
    with pytest.raises(SpotlabError):
        tiefe.ueberhang_aus_bildern([grau])
    with pytest.raises(SpotlabError):
        tiefe.ueberhang_aus_bildern([])
