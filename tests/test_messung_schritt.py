import math

import pytest

from spotlab.messung.schritt import dreh_matrix, flanken, fuss_in_odom, kennzahlen

TAKT = 0.02          # 50 Hz


def _satz(t, fuesse, x=0.0, yaw=0.0, z=0.42, roll=0.0, pitch=0.0):
    """fuesse: Liste aus (kontakt, (fx, fy, fz)) im Koerperframe."""
    return {
        "t": t,
        "daten": {
            "pose": [x, 0.0, yaw], "z": z, "roll": roll, "pitch": pitch,
            "velocity": [0.0, 0.0, 0.0], "joints": {}, "t_robot": t,
            "feet": [k for k, _p in fuesse],
            "feet_detail": [
                {"kontakt": k, "pos": list(p)} for k, p in fuesse
            ],
        },
    }


def _zweitakt(zyklus=0.8, schritt=0.30, hoehe=0.06, zyklen=4, tempo=None):
    """Ein sauberer Zweitakt: Fuesse 0+3 zusammen, 1+2 eine halbe Phase versetzt.

    Der Rumpf faehrt mit v = schritt / zyklus; ein stehender Fuss wandert im
    Koerperframe entsprechend nach hinten — genau das, was die Drehung nach odom
    wieder herausrechnen muss.
    """
    v = tempo if tempo is not None else schritt / zyklus
    saetze, t = [], 0.0
    ruhe_x = (0.33, 0.33, -0.33, -0.33)
    # Weltposition des jeweils letzten Aufsetzpunktes je Fuss
    stand_welt = [0.33, 0.33, -0.33, -0.33]
    while t < zyklus * zyklen:
        x = v * t
        fuesse = []
        for i in range(4):
            phase = (t / zyklus + (0.5 if i in (1, 2) else 0.0)) % 1.0
            im_stand = phase < 0.5
            if im_stand:
                if phase < TAKT / zyklus:          # gerade aufgesetzt
                    stand_welt[i] = x + ruhe_x[i] + schritt / 2
                fz = 0.0
                fx_welt = stand_welt[i]
            else:
                s = (phase - 0.5) / 0.5
                start = stand_welt[i]
                ziel = start + schritt
                fx_welt = start + s * (ziel - start)
                fz = hoehe * math.sin(math.pi * s)
            fuesse.append((im_stand, (fx_welt - x, 0.2 if i in (0, 1) else -0.2, fz - z_boden())))
        saetze.append(_satz(t, fuesse, x=x))
        t += TAKT
    return saetze


def z_boden():
    return 0.42          # Koerperhoehe: Fuss auf dem Boden ist -0.42 im Koerperframe


def _zeiten(saetze):
    return [s["t"] for s in saetze]


# ----------------------------------------------------------------- Bausteine


def test_drehmatrix_ist_orthonormal():
    r = dreh_matrix(0.1, -0.2, 1.3)
    for i in range(3):
        assert sum(r[i][j] ** 2 for j in range(3)) == pytest.approx(1.0)
    assert sum(r[0][j] * r[1][j] for j in range(3)) == pytest.approx(0.0, abs=1e-12)


def test_fuss_in_odom_dreht_und_verschiebt():
    daten = {"pose": [1.0, 2.0, math.pi / 2], "z": 0.5, "roll": 0.0, "pitch": 0.0,
             "feet_detail": [{"kontakt": True, "pos": [0.3, 0.0, -0.5]}]}
    x, y, z = fuss_in_odom(daten, 0)
    assert (x, y, z) == pytest.approx((1.0, 2.3, 0.0), abs=1e-9)   # 90° gedreht


def test_fuss_in_odom_ohne_detail_ist_none():
    assert fuss_in_odom({"pose": [0, 0, 0], "z": 0.4}, 0) is None


def test_flanken():
    auf, ab = flanken([False, True, True, False, True])
    assert auf == [1, 4]
    assert ab == [3]


# ----------------------------------------------------------------- Kennzahlen


def test_zyklus_und_takt():
    saetze = _zweitakt(zyklus=0.8, zyklen=5)
    k = kennzahlen(saetze, _zeiten(saetze))
    assert k["zyklusdauer_s"] == pytest.approx(0.8, abs=0.03)
    assert k["schwungdauer_s"] == pytest.approx(0.4, abs=0.03)
    assert k["standdauer_s"] == pytest.approx(0.4, abs=0.03)
    assert k["muster"] == "zweitakt"


def test_phasen_zeigen_die_paare():
    saetze = _zweitakt(zyklus=0.8, zyklen=5)
    phasen = kennzahlen(saetze, _zeiten(saetze))["phasen"]
    assert phasen[0] == pytest.approx(phasen[3], abs=0.05)
    assert abs(phasen[1] - phasen[0]) == pytest.approx(0.5, abs=0.05)


def test_schrittlaenge_wird_in_der_welt_gemessen():
    """Im Koerperframe waere die Schrittlaenge um den Rumpfweg falsch."""
    saetze = _zweitakt(zyklus=0.8, schritt=0.30, zyklen=5)
    k = kennzahlen(saetze, _zeiten(saetze))
    assert k["schrittlaenge_m"] == pytest.approx(0.30, abs=0.02)
    assert k["schritte"] >= 4


def test_schwunghoehe():
    saetze = _zweitakt(hoehe=0.06, zyklen=5)
    assert kennzahlen(saetze, _zeiten(saetze))["schwunghoehe_m"] == pytest.approx(
        0.06, abs=0.01
    )


def test_kurzer_schritt_bei_gleicher_kadenz_ist_unterscheidbar():
    """DIE Frage: kommt langsame Fahrt aus kurzen Schritten oder aus der Kadenz?"""
    kurz = kennzahlen(*_mit_zeiten(_zweitakt(zyklus=0.7, schritt=0.10, zyklen=6)))
    lang = kennzahlen(*_mit_zeiten(_zweitakt(zyklus=0.7, schritt=0.30, zyklen=6)))
    assert kurz["zyklusdauer_s"] == pytest.approx(lang["zyklusdauer_s"], abs=0.03)
    assert kurz["schrittlaenge_m"] < 0.5 * lang["schrittlaenge_m"]


def test_langsame_kadenz_bei_gleicher_schrittlaenge_ist_unterscheidbar():
    schnell = kennzahlen(*_mit_zeiten(_zweitakt(zyklus=0.5, schritt=0.20, zyklen=8)))
    langsam = kennzahlen(*_mit_zeiten(_zweitakt(zyklus=1.0, schritt=0.20, zyklen=5)))
    assert schnell["schrittlaenge_m"] == pytest.approx(
        langsam["schrittlaenge_m"], abs=0.03
    )
    assert langsam["zyklusdauer_s"] > 1.7 * schnell["zyklusdauer_s"]


def _mit_zeiten(saetze):
    return saetze, _zeiten(saetze)


def test_weg_je_zyklus_ist_die_entsprechung_der_bias_kappe():
    saetze = _zweitakt(zyklus=0.8, schritt=0.30, zyklen=5)
    versatz = saetze[-1]["daten"]["pose"][0] - saetze[0]["daten"]["pose"][0]
    k = kennzahlen(saetze, _zeiten(saetze), versatz_m=versatz)
    assert k["weg_je_zyklus_m"] == pytest.approx(0.30, abs=0.03)


def test_streuung_zeigt_einen_doppelt_aufsetzenden_fuss():
    """Setzt ein Fuss pro Gangzyklus zweimal auf, sinkt der Mittelwert und die
    Kadenz sieht schneller aus als sie ist. Die Streuung ist die Warnlampe davor.

    Gefunden am Sim-Kriechgang (matura-spot, notes/REALISMUS_GATES.md Runde 3);
    real erzeugt ein schleifender Fuss dasselbe Bild.
    """
    sauber = _zweitakt(zyklus=0.8, zyklen=6)
    kaputt = _zweitakt(zyklus=0.8, zyklen=6)
    for s in kaputt:
        if 0.20 <= (s["t"] / 0.8) % 1.0 < 0.28:      # mitten in der Standphase
            s["daten"]["feet"][0] = False
            s["daten"]["feet_detail"][0]["kontakt"] = False
    k_sauber = kennzahlen(sauber, _zeiten(sauber))
    k_kaputt = kennzahlen(kaputt, _zeiten(kaputt))
    # Beim sauberen Gang bleibt die Streuung UNTER einer Abtastperiode — mehr
    # als die Flankenquantisierung ist da nicht drin.
    assert k_sauber["zyklusdauer_streuung_s"] < TAKT
    assert k_kaputt["zyklusdauer_streuung_s"] > 0.1
    assert k_kaputt["zyklusdauer_s"] < k_sauber["zyklusdauer_s"]


def test_streuung_braucht_zwei_intervalle():
    from spotlab.messung.schritt import _streuung

    assert _streuung([]) is None
    assert _streuung([1.0]) is None
    assert _streuung([1.0, 3.0]) == pytest.approx(1.0)


def test_ohne_versatz_bleibt_weg_je_zyklus_leer():
    saetze = _zweitakt(zyklen=4)
    assert kennzahlen(saetze, _zeiten(saetze))["weg_je_zyklus_m"] is None


def test_schlankes_fenster_liefert_takt_aber_keine_geometrie():
    """`feet` reicht für Takt und Phasen, Schrittlänge braucht Fusspositionen."""
    saetze = _zweitakt(zyklen=5)
    for s in saetze:
        del s["daten"]["feet_detail"]
    k = kennzahlen(saetze, _zeiten(saetze))
    assert k["zyklusdauer_s"] == pytest.approx(0.8, abs=0.03)
    assert k["muster"] == "zweitakt"
    assert k["schrittlaenge_m"] is None
    assert k["schwunghoehe_m"] is None


def test_stehender_roboter_hat_keinen_takt():
    saetze = [
        _satz(i * TAKT, [(True, (0.33, 0.2, -0.42))] * 4) for i in range(50)
    ]
    k = kennzahlen(saetze, _zeiten(saetze))
    assert k["zyklusdauer_s"] is None
    assert k["schrittlaenge_m"] is None
    assert k["muster"] == "unklar"


def test_zu_wenige_abtastungen():
    assert kennzahlen([], []) == {}
    assert kennzahlen([_satz(0.0, [(True, (0, 0, -0.42))])], [0.0]) == {}


def test_viertakt_wird_erkannt():
    """Kriechgang: die vier Fuesse setzen nacheinander auf."""
    zyklus, saetze, t = 1.2, [], 0.0
    while t < zyklus * 4:
        fuesse = []
        for i in range(4):
            phase = (t / zyklus - i * 0.25) % 1.0
            im_stand = phase > 0.25          # nur ein Fuss gleichzeitig in der Luft
            fuesse.append((im_stand, (0.33, 0.2, -0.42 if im_stand else -0.36)))
        saetze.append(_satz(t, fuesse))
        t += TAKT
    k = kennzahlen(saetze, _zeiten(saetze))
    assert k["muster"] == "viertakt"
    assert k["zyklusdauer_s"] == pytest.approx(1.2, abs=0.05)


def test_schritt_block_haengt_in_den_fensterkennzahlen():
    from spotlab.messung.fenster import kennzahlen as fenster_kennzahlen

    saetze = _zweitakt(zyklus=0.8, schritt=0.30, zyklen=5)
    k = fenster_kennzahlen(saetze, [], "robot", 50.0)
    assert k["schritt"]["muster"] == "zweitakt"
    assert k["schritt"]["schrittlaenge_m"] == pytest.approx(0.30, abs=0.02)
    assert k["schritt"]["weg_je_zyklus_m"] is not None
