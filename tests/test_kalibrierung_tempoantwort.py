"""Die Antwort auf walk(): Latenz, Anlauf, Zeitkonstanten, Drehschwelle, Tempoanteil.

Gemessen aus kommandierten Laeufen am Schul-Spot (Fahren und Folgen, 07.-21.09.2026).
Bis dahin galt im Sim: kommandiert IST erreicht, sofort.
"""

import json
import math

import pytest

from spotlab.kalibrierung import tempoantwort

KENNLINIE = {
    "fassung": 1,
    "spruenge": (
        [{"art": "anfahren", "gruppe": "gehen", "soll": 0.4, "totzeit_s": 0.24, "tau_s": 0.2,
          "endwert": 0.95}] * 3
        + [{"art": "anfahren", "gruppe": "drehen", "soll": 0.8, "totzeit_s": 0.24, "tau_s": 0.05,
            "endwert": 0.95}] * 3
        + [{"art": "anhalten", "gruppe": "gehen", "soll": 0.4, "totzeit_s": 0.10, "tau_s": 0.13,
            "endwert": 0.95}] * 3
        + [{"art": "anhalten", "gruppe": "drehen", "soll": 0.8, "totzeit_s": 0.10, "tau_s": 0.07,
            "endwert": 0.95}] * 3
    ),
    "drehschwelle": [
        {"soll_rad_s": 0.06, "proben": 200, "anteil": 0.02},
        {"soll_rad_s": 0.12, "proben": 300, "anteil": 0.01},
        {"soll_rad_s": 0.13, "proben": 30, "anteil": 0.94},
        {"soll_rad_s": 0.2, "proben": 5, "anteil": 0.03},       # zu wenige Proben: zaehlt nicht
        {"soll_rad_s": 0.3, "proben": 70, "anteil": 0.97},
    ],
    "tempo": (
        [{"gruppe": "gehen", "soll": 0.2, "anteil": 0.85}] * 6
        + [{"gruppe": "gehen", "soll": 0.4, "anteil": 0.95}] * 6
        + [{"gruppe": "gehen", "soll": 0.8, "anteil": 1.0}] * 6
        + [{"gruppe": "drehen", "soll": 0.8, "anteil": 1.0}] * 6
    ),
}


@pytest.fixture
def modell():
    return tempoantwort.Tempoantwort(KENNLINIE)


# ------------------------------------------------------------------ Modell


def test_die_parameter_kommen_aus_den_spruengen(modell):
    assert modell.latenz_s == pytest.approx(0.10)
    assert modell.anlauf_s == pytest.approx(0.14)          # 0.24 - 0.10
    assert modell.tau["gehen"] == pytest.approx((0.2, 0.13))
    assert modell.tau["drehen"] == pytest.approx((0.05, 0.07))


def test_die_drehschwelle_liegt_zwischen_den_gut_belegten_stufen(modell):
    assert modell.drehschwelle_rad_s == pytest.approx(0.125)


def test_reines_drehen_unter_der_schwelle_laesst_spot_stehen(modell):
    assert modell.ziel(0.0, 0.0, 0.1) == ((0.0, 0.0, 0.0), True)
    assert modell.ziel(0.0, 0.0, -0.1) == ((0.0, 0.0, 0.0), True)
    ziel, unter = modell.ziel(0.0, 0.0, 0.3)
    assert not unter and ziel[2] == pytest.approx(0.3)


def test_beim_gehen_gilt_die_schwelle_nicht(modell):
    """Gemessen: kleine Drehraten werden beim Gehen umgesetzt (0.86-0.96)."""
    ziel, unter = modell.ziel(0.4, 0.0, 0.05)
    assert not unter and ziel[2] == pytest.approx(0.05)


def test_der_tempoanteil_wird_interpoliert_und_am_rand_gehalten(modell):
    assert modell.ziel(0.2, 0.0, 0.0)[0][0] == pytest.approx(0.2 * 0.85)
    assert modell.ziel(0.3, 0.0, 0.0)[0][0] == pytest.approx(0.3 * 0.90)
    assert modell.ziel(0.1, 0.0, 0.0)[0][0] == pytest.approx(0.1 * 0.85)   # darunter: nicht gemessen
    assert modell.ziel(1.2, 0.0, 0.0)[0][0] == pytest.approx(1.2 * 1.0)
    vx, vy, _ = modell.ziel(0.0, -0.4, 0.0)[0]
    assert (vx, vy) == pytest.approx((0.0, -0.4 * 0.95))


def test_gemessen_sagt_wo_die_tabelle_endet(modell):
    assert modell.gemessen(0.4, 0.0, 0.0)
    assert not modell.gemessen(0.1, 0.0, 0.0)
    assert modell.gemessen(0.0, 0.0, 0.0)


# ------------------------------------------------------------------ Folger


def _fahre(folger, bis, dt=0.005, t=0.0):
    while t < bis - 1e-12:
        folger.schritt(t, dt)
        t += dt
    return t


def test_aus_dem_stand_erst_latenz_und_anlauf_dann_erste_ordnung(modell):
    f = tempoantwort.Folger(modell)
    f.befehl(0.0, (0.4, 0.0, 0.0))
    t = _fahre(f, 0.235)
    assert f.ist == (0.0, 0.0, 0.0)
    _fahre(f, 0.24 + 0.2, t=t)
    assert f.ist[0] == pytest.approx(0.4 * (1 - math.exp(-1)), abs=0.01)


def test_anhalten_nach_der_latenz_ohne_anlauf_und_schneller(modell):
    f = tempoantwort.Folger(modell, ist=(0.4, 0.0, 0.0))
    f.befehl(0.0, (0.4, 0.0, 0.0))
    t = _fahre(f, 1.0)
    f.befehl(t, (0.0, 0.0, 0.0))
    t2 = _fahre(f, t + 0.095, t=t)
    assert f.ist[0] == pytest.approx(0.4, abs=1e-6)
    _fahre(f, t + 0.10 + 0.13, t=t2)
    assert f.ist[0] == pytest.approx(0.4 * math.exp(-1), abs=0.01)


def test_ein_neuer_befehl_im_gehen_hat_nur_die_latenz(modell):
    f = tempoantwort.Folger(modell, ist=(0.4, 0.0, 0.0))
    f.befehl(0.0, (0.4, 0.0, 0.0))
    t = _fahre(f, 1.0)
    f.befehl(t, (0.8, 0.0, 0.0))
    _fahre(f, t + 0.10 + 0.2, t=t)
    assert f.ist[0] == pytest.approx(0.8 - 0.4 * math.exp(-1), abs=0.01)


def test_befehle_wirken_in_sendereihenfolge(modell):
    """Ein Stopp nach einem walk darf nicht vom walk ueberholt werden."""
    f = tempoantwort.Folger(modell)
    f.befehl(0.0, (0.4, 0.0, 0.0))
    f.befehl(0.01, (0.0, 0.0, 0.0))
    _fahre(f, 2.0)
    assert f.ist == (0.0, 0.0, 0.0)
    assert f.ruht


def test_ein_stopp_im_anlauf_bricht_ihn_ab(modell):
    f = tempoantwort.Folger(modell)
    f.befehl(0.0, (0.4, 0.0, 0.0))
    t = _fahre(f, 0.15)
    f.befehl(t, (0.0, 0.0, 0.0))
    _fahre(f, 2.0, t=t)
    assert f.ist == (0.0, 0.0, 0.0)


def test_drehen_und_gehen_haben_eigene_zeitkonstanten(modell):
    f = tempoantwort.Folger(modell)
    f.befehl(0.0, (0.4, 0.0, 0.8))
    _fahre(f, 0.24 + 0.05)
    assert f.ist[2] == pytest.approx(0.8 * (1 - math.exp(-1)), abs=0.02)
    assert f.ist[0] == pytest.approx(0.4 * (1 - math.exp(-0.05 / 0.2)), abs=0.01)


# ------------------------------------------------------------------ Messen


def _pt1(t, totzeit, tau, steigend):
    x = max(0.0, t - totzeit)
    f = 1.0 - math.exp(-x / tau)
    return f if steigend else 1.0 - f


def _lauf(tmp_path, name, backend="real", soll=(0.4, 0.0, 0.0), an=(0.3, 0.2), ab=(0.1, 0.12),
          dauer=4.0, hz=10.0, faktor=1.0):
    """Ein kommandierter Lauf: walk alle 0.1 s ab t=1, stop nach `dauer`, PT1-Antwort."""
    ordner = tmp_path / name
    ordner.mkdir()
    (ordner / "lauf.json").write_text(json.dumps({"id": name, "backend": backend}), encoding="utf-8")
    t0, t1 = 1.0, 1.0 + dauer
    ereignisse = [{"t": 0.5, "art": "kommando", "daten": {"name": "stand", "height": 0.0}}]
    t = t0
    while t < t1 - 1e-9:
        ereignisse.append({"t": round(t, 3), "art": "kommando", "daten": {
            "name": "walk", "vx": soll[0], "vy": soll[1], "wz": soll[2], "duration": 1.0,
            "stop": False, "nick_grad": 0.0}})
        t += 0.1
    ereignisse.append({"t": t1, "art": "kommando", "daten": {"name": "stop"}})
    zustand = []
    t = 0.0
    while t < t1 + 3.0:
        if t < t1:
            anteil = _pt1(t - t0, *an, True)
        else:
            anteil = _pt1(t - t0, *an, True) * _pt1(t - t1, *ab, False)
        v = [s * anteil * faktor for s in soll]
        zustand.append({"t": round(t, 3), "daten": {"pose": [0.0, 0.0, 0.0], "velocity": v}})
        t += 1.0 / hz
    (ordner / "ereignisse.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in ereignisse), encoding="utf-8")
    (ordner / "zustand.jsonl").write_text(
        "".join(json.dumps(z) + "\n" for z in zustand), encoding="utf-8")
    return ordner


def test_ein_sprung_liefert_totzeit_und_zeitkonstante(tmp_path):
    spruenge, _ = tempoantwort.spruenge_aus_lauf(_lauf(tmp_path, "a"))
    an = [s for s in spruenge if s["art"] == "anfahren"]
    ab = [s for s in spruenge if s["art"] == "anhalten"]
    assert len(an) == 1 and len(ab) == 1
    assert an[0]["gruppe"] == "gehen"
    assert an[0]["totzeit_s"] == pytest.approx(0.3, abs=0.03)
    assert an[0]["tau_s"] == pytest.approx(0.2, abs=0.04)
    assert ab[0]["totzeit_s"] == pytest.approx(0.1, abs=0.03)
    assert ab[0]["tau_s"] == pytest.approx(0.12, abs=0.04)


def test_ein_drehsprung_zaehlt_zur_gruppe_drehen(tmp_path):
    spruenge, _ = tempoantwort.spruenge_aus_lauf(_lauf(tmp_path, "d", soll=(0.0, 0.0, 0.79)))
    assert {s["gruppe"] for s in spruenge} == {"drehen"}


def test_die_geschwindigkeit_wird_in_den_koerperrahmen_gedreht(tmp_path):
    """`velocity` steht im odom-Rahmen. Bei Gier 90 Grad ist vorwaerts odom-y."""
    ordner = _lauf(tmp_path, "g")
    zeilen = [json.loads(z) for z in (ordner / "zustand.jsonl").read_text().splitlines()]
    for z in zeilen:
        vx = z["daten"]["velocity"][0]
        z["daten"]["pose"] = [0.0, 0.0, math.pi / 2]
        z["daten"]["velocity"] = [0.0, vx, 0.0]
    (ordner / "zustand.jsonl").write_text("".join(json.dumps(z) + "\n" for z in zeilen))
    spruenge, _ = tempoantwort.spruenge_aus_lauf(ordner)
    assert [s["gruppe"] for s in spruenge] == ["gehen", "gehen"]
    assert spruenge[0]["endwert"] == pytest.approx(1.0, abs=0.05)


def test_haltephasen_liefern_den_tempoanteil(tmp_path):
    ordner = _lauf(tmp_path, "h", dauer=6.0)
    proben = tempoantwort.tempo_aus_lauf(ordner)
    assert proben and proben[0]["gruppe"] == "gehen" and proben[0]["soll"] == pytest.approx(0.4)
    assert proben[0]["anteil"] == pytest.approx(1.0, abs=0.02)


def test_reines_drehen_liefert_drehproben(tmp_path):
    """Spot dreht nicht (Anteil 0) -- genau das muss als Probe ankommen."""
    proben = tempoantwort.drehproben_aus_lauf(
        _lauf(tmp_path, "s", soll=(0.0, 0.0, 0.08), faktor=0.0, dauer=5.0))
    assert len(proben) >= 20
    assert {p[0] for p in proben} == {0.08}
    assert max(abs(p[1]) for p in proben) < 1e-9


def test_nur_kommandierte_laeufe_am_echten_spot(tmp_path):
    _lauf(tmp_path, "echt")
    _lauf(tmp_path, "sim", backend="mujoco")
    kennlinie, bericht = tempoantwort.sammle(tmp_path)
    assert {s["herkunft"]["lauf"] for s in kennlinie["spruenge"]} == {"echt"}
    assert any("sim" in zeile and "übersprungen" in zeile for zeile in bericht)


def test_die_gueltigkeit_ist_dieselbe_wie_in_walk():
    from spotlab.api import motion

    assert tempoantwort.GUELTIG_S == motion.KOMMANDO_GUELTIGKEIT_S


# ---------------------------------------------------- mitgelieferte Kennlinie


def test_die_mitgelieferte_kennlinie_traegt_die_messung():
    """Regressionsschutz fuer daten/tempoantwort.json (gemessen am Schul-Spot)."""
    m = tempoantwort.lade_modell()
    assert 0.05 <= m.latenz_s <= 0.2
    assert 0.05 <= m.anlauf_s <= 0.3
    assert 0.10 <= m.drehschwelle_rad_s <= 0.15
    assert 0.1 <= m.tau["gehen"][0] <= 0.4
    kennlinie = tempoantwort.lade()
    assert len(kennlinie["spruenge"]) >= 50
