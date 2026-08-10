import json

import pytest

from spotlab.mcp import werkzeuge


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    from spotlab.config import Config, Limits

    arbeit = tmp_path / "werkstatt"
    (arbeit / "demo").mkdir(parents=True)
    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(arbeit))
    monkeypatch.setattr(werkzeuge, "load_config", lambda: cfg)
    return arbeit


def _lauf(arbeit, ergebnis="ok"):
    """Legt einen echten Lauf an. Die Zustandsdatei schreiben die Tests selbst.

    RunRecorder.sample() setzt `t` aus seiner eigenen Uhr — Abtastluecken
    liessen sich darueber nicht gezielt erzeugen.
    """
    from spotlab.record.run import RunRecorder

    skript = arbeit / "demo" / "hallo.py"
    skript.write_text("print(1)\n", encoding="utf-8")
    recorder = RunRecorder(arbeit / "demo" / "runs", skript, backend="dryrun")
    recorder.finish(ergebnis)
    return recorder


def _schreibe_zustand(recorder, saetze):
    text = "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in saetze)
    (recorder.dir / "zustand.jsonl").write_text(text, encoding="utf-8")


def _satz(t, x=0.0, v=0.0, akku=90.0):
    return {
        "t": t,
        "daten": {
            "pose": [x, 0.0, 0.0],
            "velocity": [v, 0.0, 0.0],
            "battery": akku,
            "feet": [True, True, True, True],
        },
    }


def test_laeufe_auflisten(welt):
    _lauf(welt)
    liste = werkzeuge.laeufe_auflisten()
    assert len(liste) == 1
    assert liste[0]["ergebnis"] == "ok"
    assert liste[0]["id"]


def test_laeufe_auflisten_begrenzt(welt):
    for _ in range(3):
        _lauf(welt)
    assert len(werkzeuge.laeufe_auflisten(anzahl=2)) == 2


def test_lauf_lesen_gibt_pfade_und_keine_inhalte(welt):
    """Der wichtigste Entwurfspunkt: keine Massendaten ins Kontextfenster."""
    recorder = _lauf(welt)
    _schreibe_zustand(recorder, [_satz(0.0), _satz(0.1)])
    antwort = werkzeuge.lauf_lesen(recorder.id)
    assert antwort["ergebnis"] == "ok"
    assert antwort["abtastungen_n"] == 2
    assert antwort["pfade"]["zustand"].endswith("zustand.jsonl")
    assert antwort["pfade"]["ereignisse"].endswith("ereignisse.jsonl")
    assert "battery" not in json.dumps(antwort)     # keine Messwerte in der Antwort


def test_lauf_lesen_unbekannt(welt):
    assert "fehler" in werkzeuge.lauf_lesen("gibtsnicht")


def test_zustand_zusammenfassen_rechnet(welt):
    recorder = _lauf(welt)
    _schreibe_zustand(
        recorder, [_satz(i * 0.1, x=i * 0.05, v=0.5, akku=90 - i) for i in range(11)]
    )
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert antwort["abtastungen"] == 11
    assert antwort["dauer_s"] == pytest.approx(1.0, abs=0.01)
    assert antwort["strecke_m"] == pytest.approx(0.5, abs=0.01)
    assert antwort["tempo_max"] == pytest.approx(0.5, abs=0.01)
    assert antwort["akku_von"] == 90.0
    assert antwort["akku_bis"] == 80.0
    assert [a["hz_soll"] for a in antwort["abschnitte"]] == [10.0]
    assert antwort["luecken"] == []


def test_zustand_zusammenfassen_findet_luecken(welt):
    """Eine unbemerkte Luecke macht den Real->Sim-Vergleich still ungueltig."""
    recorder = _lauf(welt)
    _schreibe_zustand(recorder, [_satz(0.0), _satz(0.1), _satz(1.4), _satz(1.5)])
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert len(antwort["luecken"]) == 1
    assert antwort["luecken"][0]["ab_start_s"] == pytest.approx(0.1)
    # Beide Auswertungen muessen sagen, auf welcher Uhr sie zaehlen -- sonst
    # liefern sie fuer denselben Lauf verschiedene Lueckenlisten und niemand
    # sieht, warum.
    assert antwort["zeitquelle"] == "empfang"
    assert antwort["luecken"][0]["laenge_s"] == pytest.approx(1.3)


def test_zustand_zusammenfassen_ohne_abtastungen(welt):
    recorder = _lauf(welt)
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert antwort["abtastungen"] == 0
    assert antwort["luecken"] == []


def test_karten_auflisten_ohne_karten(welt):
    assert werkzeuge.karten_auflisten() == []


def test_karte_lesen_unbekannt(welt):
    assert "fehler" in werkzeuge.karte_lesen("gibtsnicht")


def test_spot_pruefen_reicht_die_pruefungen_durch(welt, monkeypatch):
    from spotlab.workshop.doctor import Check

    monkeypatch.setattr(
        werkzeuge, "diagnose", lambda: [Check("Netz", True, "erreichbar", "")]
    )
    assert werkzeuge.spot_pruefen() == [
        {"name": "Netz", "ok": True, "detail": "erreichbar", "rat": ""}
    ]


def test_alle_lese_antworten_sind_json_faehig(welt):
    recorder = _lauf(welt)
    _schreibe_zustand(recorder, [_satz(0.0)])
    for antwort in (
        werkzeuge.laeufe_auflisten(),
        werkzeuge.lauf_lesen(recorder.id),
        werkzeuge.zustand_zusammenfassen(recorder.id),
        werkzeuge.karten_auflisten(),
    ):
        json.dumps(antwort)


# ------------------------------------------------ abschnittsweiser Lueckenmelder


def _ereignisse(recorder, eintraege):
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eintraege)
    (recorder.dir / "ereignisse.jsonl").write_text(text, encoding="utf-8")


def _fenster_marken(von, bis, hz):
    return [
        {"t": von, "art": "messfenster",
         "daten": {"phase": "start", "name": "G3", "hz_soll": hz}},
        {"t": bis, "art": "messfenster", "daten": {"phase": "ende", "name": "G3"}},
    ]


def test_ratenwechsel_ist_keine_luecke(welt):
    """Ein Alarm, der bei jeder Messfahrt kommt, wird ignoriert."""
    recorder = _lauf(welt)
    saetze = [_satz(i * 0.1) for i in range(11)]
    saetze += [_satz(1.0 + i * 0.02) for i in range(1, 51)]
    saetze += [_satz(2.0 + i * 0.1) for i in range(1, 11)]
    _schreibe_zustand(recorder, saetze)
    _ereignisse(recorder, _fenster_marken(1.0, 2.0, 50))

    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert antwort["luecken"] == []
    assert [a["hz_soll"] for a in antwort["abschnitte"]] == [10.0, 50.0, 10.0]


def test_echte_luecke_im_fenster_wird_gefunden(welt):
    recorder = _lauf(welt)
    saetze = [_satz(1.0 + i * 0.02) for i in range(11)]
    saetze += [_satz(1.5 + i * 0.02) for i in range(11)]
    _schreibe_zustand(recorder, saetze)
    _ereignisse(recorder, _fenster_marken(1.0, 2.0, 50))

    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert len(antwort["luecken"]) == 1
    assert antwort["luecken"][0]["laenge_s"] == pytest.approx(0.3, abs=0.01)


def test_ohne_fenster_bleibt_es_bei_zehn_hertz(welt):
    recorder = _lauf(welt)
    _schreibe_zustand(recorder, [_satz(0.0), _satz(0.1), _satz(1.4), _satz(1.5)])
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert len(antwort["luecken"]) == 1
    assert [a["hz_soll"] for a in antwort["abschnitte"]] == [10.0]
