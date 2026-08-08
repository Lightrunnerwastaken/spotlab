import math

import pytest

from spotlab.messung.fenster import kennzahlen


def _satz(t, x=0.0, y=0.0, yaw=0.0, z=0.42, roll=0.0, pitch=0.0,
          vx=0.0, vy=0.0, wz=0.0, feet=(True, True, True, True), **extra):
    daten = {
        "pose": [x, y, yaw], "velocity": [vx, vy, wz],
        "z": z, "roll": roll, "pitch": pitch, "feet": list(feet),
        "joints": {}, "t_robot": t,
    }
    daten.update(extra)
    return {"t": t, "daten": daten}


def _reihe(n, dt=0.02, **fest):
    return [_satz(i * dt, **fest) for i in range(n)]


def test_messguete_zuerst():
    k = kennzahlen(_reihe(51), [], "robot", 50.0)
    assert k["abtastungen"] == 51
    assert k["dauer_s"] == pytest.approx(1.0)
    assert k["hz_ist"] == pytest.approx(50.0, abs=0.1)
    assert k["zeitquelle"] == "robot"
    assert k["luecken"] == []


def test_luecke_wird_gegen_hz_soll_gemessen():
    saetze = _reihe(10)
    saetze += [_satz(1.0 + i * 0.02) for i in range(10)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert len(k["luecken"]) == 1
    assert k["luecken"][0]["laenge_s"] == pytest.approx(0.82, abs=0.01)


def test_hoehe_drift_und_absacken():
    saetze = [_satz(i * 0.02, z=0.42 - i * 0.0001) for i in range(51)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["hoehe_mittel"] == pytest.approx(0.4175, abs=1e-3)
    assert k["hoehe_max"] == pytest.approx(0.42)
    assert k["hoehe_min"] == pytest.approx(0.415)
    assert k["hoehe_drift"] == pytest.approx(-0.005, abs=1e-4)


def test_neigung_in_grad():
    saetze = [_satz(i * 0.02, roll=math.radians(3), pitch=math.radians(-5))
              for i in range(10)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["roll_max_grad"] == pytest.approx(3.0, abs=1e-3)
    assert k["pitch_max_grad"] == pytest.approx(5.0, abs=1e-3)


def test_strecke_und_netto_versatz():
    """Hin und zurueck: Strecke 2 m, Netto 0."""
    hin = [_satz(i * 0.1, x=i * 0.1) for i in range(11)]
    zurueck = [_satz(1.1 + i * 0.1, x=1.0 - i * 0.1) for i in range(11)]
    k = kennzahlen(hin + zurueck, [], "robot", 10.0)
    assert k["strecke_m"] == pytest.approx(2.0, abs=1e-3)
    assert k["netto_versatz_m"] == pytest.approx(0.0, abs=1e-6)


def test_gierwinkel_wird_fortlaufend_aufsummiert():
    """G4 verlangt das ausdruecklich: eine Drehung ueber 180 Grad wechselt sonst das Zeichen."""
    winkel = [
        ((math.radians(g) + math.pi) % (2 * math.pi)) - math.pi for g in range(0, 300, 10)
    ]
    saetze = [_satz(i * 0.1, yaw=w) for i, w in enumerate(winkel)]
    assert kennzahlen(saetze, [], "robot", 10.0)["gierwinkel_grad"] == pytest.approx(
        290.0, abs=0.5
    )


def test_tempo_kennzahlen():
    k = kennzahlen(_reihe(51, vx=0.30, wz=0.05), [], "robot", 50.0)
    assert k["tempo_x_mittel"] == pytest.approx(0.30)
    assert k["drehrate_mittel"] == pytest.approx(0.05)
    assert k["tempo_max"] == pytest.approx(0.30)


def test_tracking_aus_kommando_und_messung():
    k = kennzahlen(_reihe(51, vx=0.24),
                   [{"name": "walk", "vx": 0.30, "vy": 0.0, "wz": 0.0}], "robot", 50.0)
    assert k["kommandiert"] == {"vx": 0.30, "vy": 0.0, "wz": 0.0}
    assert k["tracking_prozent"] == pytest.approx(80.0, abs=0.1)


def test_widerspruechliche_kommandos_ergeben_keine_zahl():
    """Lieber keine Zahl als eine ueber zwei Bedingungen gemittelte."""
    k = kennzahlen(_reihe(51, vx=0.24),
                   [{"name": "walk", "vx": 0.30}, {"name": "walk", "vx": 0.50}],
                   "robot", 50.0)
    assert k["kommandiert"] == {}
    assert k["tracking_prozent"] is None


def test_gleiches_kommando_zweimal_ist_kein_widerspruch():
    k = kennzahlen(_reihe(51, vx=0.24),
                   [{"name": "walk", "vx": 0.30}, {"name": "walk", "vx": 0.30}],
                   "robot", 50.0)
    assert k["tracking_prozent"] == pytest.approx(80.0, abs=0.1)


def test_kein_kommando_kein_tracking():
    assert kennzahlen(_reihe(10), [], "robot", 50.0)["tracking_prozent"] is None


def test_gelenkkennzahlen():
    saetze = [
        _satz(i * 0.02, joints={"fl.hx": {"position": 0.1, "velocity": 0.4, "load": 20.0},
                                "fl.hy": {"position": 0.2, "velocity": -0.9, "load": -5.0}})
        for i in range(10)
    ]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["gelenk_rate_max"] == pytest.approx(0.9)
    assert k["gelenk_last_max"] == pytest.approx(20.0)
    assert k["gelenke"]["fl.hy"]["rate_max"] == pytest.approx(0.9)
    assert k["gelenke"]["fl.hx"]["last_max"] == pytest.approx(20.0)


def test_fuss_duty_und_schrittfrequenz_aus_schlanken_daten():
    """Kontakte stehen schon in `feet` — dafuer braucht es kein reiches Fenster."""
    muster = [(True, True, True, True), (False, True, True, True)]
    saetze = [_satz(i * 0.05, feet=muster[i % 2]) for i in range(41)]
    k = kennzahlen(saetze, [], "robot", 20.0)
    assert k["fuss_duty"][1] == pytest.approx(1.0)
    assert k["fuss_duty"][0] == pytest.approx(0.51, abs=0.02)
    assert k["schrittfrequenz_hz"] > 0


def test_reibwert_und_schlupf_nur_aus_reichen_daten():
    saetze = [
        _satz(i * 0.02, feet_detail=[
            {"kontakt": True, "mu": 0.60, "slip_weg": [0.002, 0.0, 0.0],
             "slip_tempo": [0.03, 0.0, 0.0]},
            {"kontakt": True, "mu": 0.64, "slip_weg": [0.001, 0.0, 0.0],
             "slip_tempo": [0.01, 0.0, 0.0]},
        ])
        for i in range(10)
    ]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["mu_mittel"] == pytest.approx(0.62)
    assert k["schlupf_weg_max_m"] == pytest.approx(0.002)
    assert k["schlupf_tempo_max"] == pytest.approx(0.03)


def test_schlanke_daten_ergeben_none_statt_null():
    """Der Unterschied zwischen 'gemessen und null' und 'nicht gemessen' entscheidet,
    ob eine Kalibrierung gueltig ist."""
    k = kennzahlen(_reihe(10), [], "robot", 50.0)
    assert k["mu_mittel"] is None
    assert k["schlupf_weg_max_m"] is None
    assert k["schlupf_tempo_max"] is None


def test_leere_reihe_ergibt_leere_kennzahlen():
    assert kennzahlen([], [], "empfang", 50.0) == {}
