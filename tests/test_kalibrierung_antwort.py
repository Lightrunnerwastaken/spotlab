"""Die Koerperantwort auf Kommandos: aus kommandierten Laeufen, als Trapez.

Die Gangkennlinie kennt kein Anfahren und kein Bremsen. Seit dem 02.09.2026
gibt es kommandierte Laeufe am Schul-Spot -- wenige, aber gemessen.
"""

import json
import math
from pathlib import Path

import pytest

from spotlab.kalibrierung import antwort

ECHTE_LAEUFE = Path("C:/Users/janis/Documents/Matura/spotProjects/run/runs")


def _trapez(t, a, v_reise, b, strecke):
    """Tempo zur Zeit t fuer ein Trapezprofil ueber `strecke`."""
    t_an = v_reise / a
    s_an = 0.5 * a * t_an ** 2
    t_ab = v_reise / b
    s_ab = 0.5 * b * t_ab ** 2
    s_reise = max(0.0, strecke - s_an - s_ab)
    t_reise = s_reise / v_reise
    if t < 0:
        return 0.0
    if t < t_an:
        return a * t
    if t < t_an + t_reise:
        return v_reise
    if t < t_an + t_reise + t_ab:
        return max(0.0, v_reise - b * (t - t_an - t_reise))
    return 0.0


def _lauf(tmp_path, art, backend="real", a=1.2, reise=0.7, b=1.0, soll=1.0, hz=10.0):
    """Ein synthetischer Lauf: Kommando bei t=1.0, Trapezprofil, Rueckmeldung."""
    ordner = tmp_path / f"lauf_{art}"
    ordner.mkdir()
    (ordner / "lauf.json").write_text(json.dumps({
        "id": ordner.name, "gestartet": "2026-09-02T15:21:10+00:00", "backend": backend,
    }), encoding="utf-8")
    strecke = soll if art == "fahrt" else math.radians(soll)
    t_an, t_ab = reise / a, reise / b
    dauer = t_an + max(0.0, strecke - 0.5 * a * t_an ** 2 - 0.5 * b * t_ab ** 2) / reise + t_ab
    t0 = 1.0
    felder = ({"forward": soll, "left": 0.0, "turn_grad": 0.0} if art == "fahrt"
              else {"forward": 0.0, "left": 0.0, "turn_grad": soll})
    ereignisse = [
        {"t": 0.5, "art": "kommando", "daten": {"name": "stand", "height": 0.0}},
        {"t": t0, "art": "kommando", "daten": {"name": "move", **felder}},
        {"t": t0 + dauer + 0.05, "art": "rückmeldung", "daten": {"name": "move", "status": "angekommen"}},
    ]
    zustand = []
    t = 0.0
    while t < t0 + dauer + 1.0:
        v = _trapez(t - t0, a, reise, b, strecke)
        geschwindigkeit = [v, 0.0, 0.0] if art == "fahrt" else [0.0, 0.0, v]
        zustand.append({"t": round(t, 3), "daten": {"pose": [0.0, 0.0, 0.0],
                                                   "velocity": geschwindigkeit}})
        t += 1.0 / hz
    (ordner / "ereignisse.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ereignisse), encoding="utf-8")
    (ordner / "zustand.jsonl").write_text(
        "".join(json.dumps(z) + "\n" for z in zustand), encoding="utf-8")
    return ordner


# ----------------------------------------------------------------- Messen


def test_eine_fahrt_liefert_spitze_rampen_und_dauer(tmp_path):
    punkte, verworfen = antwort.punkte_aus_lauf(_lauf(tmp_path, "fahrt"))
    assert verworfen == []
    assert len(punkte) == 1
    p = punkte[0]
    assert p.art == "fahrt" and p.soll == 1.0
    assert p.spitze == pytest.approx(0.7, abs=0.05)
    assert p.beschleunigung == pytest.approx(1.2, rel=0.3)
    assert p.verzoegerung == pytest.approx(1.0, rel=0.3)
    assert p.erreicht == pytest.approx(1.0, abs=0.08)
    assert 1.5 < p.dauer_s < 3.0
    assert p.herkunft["kommando"] == 1


def test_eine_drehung_wird_in_grad_gefuehrt(tmp_path):
    punkte, _ = antwort.punkte_aus_lauf(_lauf(tmp_path, "drehung", a=2.0, reise=1.0, b=2.0, soll=90.0))
    assert len(punkte) == 1
    p = punkte[0]
    assert p.art == "drehung" and p.soll == 90.0
    assert p.spitze == pytest.approx(1.0, abs=0.07)
    assert p.erreicht == pytest.approx(90.0, abs=6.0)


def test_ein_kombiniertes_kommando_wird_verworfen(tmp_path):
    """Fahrt UND Drehung zugleich wurde nie gemessen -- und wird nicht erraten."""
    ordner = _lauf(tmp_path, "fahrt")
    zeilen = (ordner / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    kommando = json.loads(zeilen[1])
    kommando["daten"]["turn_grad"] = 45.0
    zeilen[1] = json.dumps(kommando, ensure_ascii=False)
    (ordner / "ereignisse.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    punkte, verworfen = antwort.punkte_aus_lauf(ordner)
    assert punkte == []
    assert verworfen and "kombiniert" in verworfen[0][1]


def test_ein_trockenlauf_zaehlt_nicht(tmp_path):
    """Erlaubnisliste: nur `real`. Ein Trockenlauf hat erfundene Geschwindigkeiten."""
    _lauf(tmp_path, "fahrt", backend="dryrun")
    punkte, bericht = antwort.sammle(tmp_path)
    assert punkte == []
    assert "übersprungen" in bericht[0]


@pytest.mark.skipif(not ECHTE_LAEUFE.is_dir(), reason="die echten Laeufe liegen nur auf dem Autorenlaptop")
def test_die_echten_laeufe_vom_september_liefern_fahrt_und_drehung():
    punkte, _ = antwort.sammle(ECHTE_LAEUFE)
    # Nur die Messfahrten: im selben Ordner landen seither auch die echten Laeufe des
    # Alltags (Fahren, Navigation, 09.09.2026), und die sind keine Messung mit 1 m / 90 Grad.
    punkte = [p for p in punkte if p.herkunft.get("gestartet", "") < "2026-09-09"]
    fahrten = [p for p in punkte if p.art == "fahrt"]
    drehungen = [p for p in punkte if p.art == "drehung"]
    # Zwei Fahrten, nicht drei: der erste Lauf des Tages hatte nur `stand`.
    assert len(fahrten) >= 2 and all(p.soll == 1.0 for p in fahrten)
    assert len(drehungen) >= 1 and drehungen[0].soll == 90.0
    # Plausibel: Reisetempo unter dem konfigurierten Deckel 0.8, Dauer um 2 s.
    for p in fahrten:
        assert 0.4 < p.spitze < 0.95 and 1.5 < p.dauer_s < 3.5
        assert p.erreicht == pytest.approx(1.0, abs=0.15)


# ----------------------------------------------------------------- Modell


def _kennlinie():
    return {"punkte": [
        {"art": "fahrt", "soll": 1.0, "dauer_s": 2.2, "spitze": 0.7,
         "beschleunigung": 1.2, "verzoegerung": 1.0, "erreicht": 1.0, "proben": 25, "herkunft": {}},
        {"art": "fahrt", "soll": 1.0, "dauer_s": 2.3, "spitze": 0.65,
         "beschleunigung": 1.0, "verzoegerung": 1.1, "erreicht": 0.98, "proben": 25, "herkunft": {}},
        {"art": "drehung", "soll": 90.0, "dauer_s": 2.6, "spitze": 1.05,
         "beschleunigung": 2.0, "verzoegerung": 2.0, "erreicht": 90.0, "proben": 27, "herkunft": {}},
    ]}


def test_das_tempo_steigt_mit_der_gemessenen_beschleunigung():
    m = antwort.Antwortmodell(_kennlinie())
    assert m.tempo(0.0, rest_m=5.0, dt=0.1) == pytest.approx(0.11)      # Median(1.2, 1.0) * 0.1


def test_das_reisetempo_ist_das_gemessene_nicht_der_deckel():
    """Der echte Spot waehlte 0.65 m/s, obwohl 0.8 erlaubt war."""
    m = antwort.Antwortmodell(_kennlinie())
    assert m.tempo(0.9, rest_m=5.0, dt=0.1, deckel=0.8) == pytest.approx(0.675)


def test_der_deckel_gilt_wenn_er_tiefer_liegt():
    m = antwort.Antwortmodell(_kennlinie())
    assert m.tempo(0.9, rest_m=5.0, dt=0.1, deckel=0.3) == pytest.approx(0.3)


def test_vor_dem_ziel_wird_gebremst():
    m = antwort.Antwortmodell(_kennlinie())
    # v <= sqrt(2 * b * rest), b = Median(1.0, 1.1) = 1.05
    assert m.tempo(0.7, rest_m=0.02, dt=0.1) == pytest.approx(math.sqrt(2 * 1.05 * 0.02))
    assert m.tempo(0.7, rest_m=0.0, dt=0.1) == 0.0


def test_die_drehrate_folgt_derselben_regel():
    m = antwort.Antwortmodell(_kennlinie())
    assert m.drehrate(0.0, rest_rad=1.0, dt=0.1) == pytest.approx(0.2)
    assert m.drehrate(2.0, rest_rad=1.0, dt=0.1, deckel=1.1) == pytest.approx(1.05)


def test_gemessen_kennt_nur_seine_sollwerte():
    m = antwort.Antwortmodell(_kennlinie())
    assert m.gemessen(1.0, 0.0) and m.gemessen(1.05, 0.0)
    assert m.gemessen(0.0, 90.0) and m.gemessen(0.0, -90.0)
    assert not m.gemessen(2.0, 0.0)
    assert not m.gemessen(1.0, 90.0), "kombiniert wurde nie gemessen"


def test_ohne_drehpunkte_gibt_es_kein_modell():
    kennlinie = {"punkte": [p for p in _kennlinie()["punkte"] if p["art"] == "fahrt"]}
    with pytest.raises(ValueError):
        antwort.Antwortmodell(kennlinie)


# ------------------------------------------------------------ Datei/CLI


def test_die_mitgelieferte_kennlinie_traegt_beides():
    m = antwort.lade_modell()
    assert m.gemessene_strecken_m == [1.0]
    assert m.gemessene_winkel_grad == [90.0]
    assert 0.5 < m.a_fahrt < 3.0 and 0.5 < m.b_fahrt < 3.0
    assert 0.4 < m.v_fahrt < 0.95


def test_die_cli_schreibt_eine_datei(tmp_path, capsys):
    _lauf(tmp_path, "fahrt")
    _lauf(tmp_path, "drehung", a=2.0, reise=1.0, b=2.0, soll=90.0)
    ziel = tmp_path / "antwort.json"
    assert antwort.main([str(tmp_path), "--ziel", str(ziel), "--bemerkung", "Test"]) == 0
    inhalt = json.loads(ziel.read_text(encoding="utf-8"))
    assert {p["art"] for p in inhalt["punkte"]} == {"fahrt", "drehung"}
    assert inhalt["bemerkung"] == "Test"
    assert "2 Antwortpunkte" in capsys.readouterr().out
