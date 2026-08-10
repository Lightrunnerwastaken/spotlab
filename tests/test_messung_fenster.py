import json
import math
import re
from pathlib import Path

import pytest

from spotlab.messung.fenster import als_json, fenster, schreibe


def _lauf(tmp_path, ereignisse, saetze):
    ordner = tmp_path / "20260808T120000Z"
    ordner.mkdir(parents=True)
    (ordner / "ereignisse.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ereignisse),
        encoding="utf-8",
    )
    (ordner / "zustand.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in saetze),
        encoding="utf-8",
    )
    return ordner


def _start(t, name, hz=50, **felder):
    return {"t": t, "art": "messfenster",
            "daten": {"phase": "start", "name": name, "hz_soll": hz, **felder}}


def _ende(t, name, **felder):
    return {"t": t, "art": "messfenster", "daten": {"phase": "ende", "name": name, **felder}}


def _satz(t, t_robot=None, **daten):
    voll = {"pose": [0.0, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0],
            "z": 0.42, "roll": 0.0, "pitch": 0.0, "feet": [True] * 4,
            "joints": {}, "battery": 87.0, "powered": True,
            "t_robot": t if t_robot is None else t_robot}
    voll.update(daten)
    return {"t": t, "daten": voll}


def test_ein_fenster_wird_erkannt(tmp_path):
    ordner = _lauf(
        tmp_path,
        [_start(1.0, "G3", stuetzstelle="0.30"), _ende(3.0, "G3")],
        [_satz(t / 10) for t in range(0, 50)],
    )
    liste = fenster(ordner)
    assert len(liste) == 1
    f = liste[0]
    assert f.name == "G3"
    assert f.felder == {"stuetzstelle": "0.30"}
    assert f.hz_soll == 50
    assert f.von_s == 1.0 and f.bis_s == 3.0
    assert f.unvollstaendig is False


def test_nur_abtastungen_im_fenster_zaehlen(tmp_path):
    ordner = _lauf(
        tmp_path,
        [_start(1.0, "G1"), _ende(2.0, "G1")],
        [_satz(t / 10) for t in range(0, 40)],
    )
    assert fenster(ordner)[0].abtastungen == 11          # 1.0 … 2.0 einschliesslich


def test_hz_ist_wird_aus_den_abtastungen_gerechnet(tmp_path):
    """Nicht aus den Marken — deren Abstand zaehlt die Wartezeit auf den ersten Tick mit."""
    ordner = _lauf(
        tmp_path,
        [_start(0.9, "G1", hz=10), _ende(2.2, "G1")],
        [_satz(1.0 + i / 10) for i in range(11)],
    )
    assert fenster(ordner)[0].hz_ist == pytest.approx(10.0, abs=0.01)


def test_zwei_fenster_nacheinander(tmp_path):
    ordner = _lauf(
        tmp_path,
        [_start(1.0, "G2"), _ende(2.0, "G2"), _start(3.0, "G3"), _ende(4.0, "G3")],
        [_satz(t / 10) for t in range(0, 50)],
    )
    assert [f.name for f in fenster(ordner)] == ["G2", "G3"]


def test_fenster_ohne_ende_gilt_als_unvollstaendig(tmp_path):
    """Prozess gestorben — die letzte Abtastung ist das Ende, und das steht dran."""
    ordner = _lauf(tmp_path, [_start(1.0, "G6")], [_satz(t / 10) for t in range(0, 30)])
    f = fenster(ordner)[0]
    assert f.unvollstaendig is True
    assert f.bis_s == pytest.approx(2.9)


def test_zeitquelle_robot_wenn_alle_stempel_da_sind(tmp_path):
    ordner = _lauf(tmp_path, [_start(1.0, "G1"), _ende(2.0, "G1")],
                   [_satz(t / 10, t_robot=1000.0 + t / 10) for t in range(0, 30)])
    assert fenster(ordner)[0].zeitquelle == "robot"


def test_zeitquelle_empfang_wenn_ein_stempel_fehlt(tmp_path):
    saetze = [_satz(t / 10, t_robot=1000.0 + t / 10) for t in range(0, 30)]
    saetze[15]["daten"]["t_robot"] = 0.0
    ordner = _lauf(tmp_path, [_start(1.0, "G1"), _ende(2.0, "G1")], saetze)
    assert fenster(ordner)[0].zeitquelle == "empfang"


def test_reich_wird_erkannt(tmp_path):
    schlank = _lauf(tmp_path / "a", [_start(1.0, "G1"), _ende(2.0, "G1")],
                    [_satz(t / 10) for t in range(0, 30)])
    assert fenster(schlank)[0].reich is False

    reich = _lauf(tmp_path / "b", [_start(1.0, "G1"), _ende(2.0, "G1")],
                  [_satz(t / 10, feet_detail=[{"kontakt": True, "mu": 0.6}])
                   for t in range(0, 30)])
    assert fenster(reich)[0].reich is True


def test_kommandos_im_fenster_werden_mitgenommen(tmp_path):
    ordner = _lauf(
        tmp_path,
        [
            {"t": 0.5, "art": "kommando", "daten": {"name": "walk", "vx": 0.9}},
            _start(1.0, "G3"),
            {"t": 1.2, "art": "kommando", "daten": {"name": "walk", "vx": 0.30}},
            _ende(2.0, "G3"),
        ],
        [_satz(t / 10) for t in range(0, 30)],
    )
    assert [k["vx"] for k in fenster(ordner)[0].kommandos] == [0.30]


def test_fenster_ohne_abtastungen_stuerzt_nicht(tmp_path):
    ordner = _lauf(tmp_path, [_start(9.0, "G1"), _ende(9.5, "G1")],
                   [_satz(t / 10) for t in range(0, 30)])
    f = fenster(ordner)[0]
    assert f.abtastungen == 0
    assert f.hz_ist == 0.0
    assert f.messwerte == {}


def test_lauf_ohne_fenster(tmp_path):
    assert fenster(_lauf(tmp_path, [], [_satz(0.1)])) == []


def test_schreibe_legt_messfenster_json_an(tmp_path):
    ordner = _lauf(tmp_path, [_start(1.0, "G1"), _ende(2.0, "G1")],
                   [_satz(t / 10) for t in range(0, 30)])
    pfad = schreibe(ordner)
    assert pfad.name == "messfenster.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    assert daten["lauf"] == ordner.name
    assert [f["name"] for f in daten["fenster"]] == ["G1"]
    json.dumps(als_json(fenster(ordner)))


def test_messung_ist_frei_von_sdk_und_qt():
    import spotlab.messung as paket

    wurzel = Path(paket.__file__).parent
    muster = re.compile(
        r"^\s*(from|import)\s+"
        r"(bosdyn|PySide6|spotlab\.api|spotlab\.backends|spotlab\.gui)",
        re.M,
    )
    verstoesse = [
        str(p) for p in wurzel.rglob("*.py") if muster.search(p.read_text(encoding="utf-8"))
    ]
    assert verstoesse == []


def test_luecke_ueber_einen_ratenwechsel_wird_nachsichtig_gemessen():
    """Direkt nach dem Herunterschalten von 50 auf 10 Hz ist 0.1 s kein Loch."""
    from spotlab.messung.fenster import hz_soll_zwischen

    stuecke = [
        {"von_s": 0.0, "bis_s": 1.0, "hz_soll": 10.0},
        {"von_s": 1.0, "bis_s": 2.0, "hz_soll": 50.0},
        {"von_s": 2.0, "bis_s": 3.0, "hz_soll": 10.0},
    ]
    assert hz_soll_zwischen(stuecke, 1.5, 1.52) == 50.0        # mitten im Fenster
    assert hz_soll_zwischen(stuecke, 2.0, 2.1) == 10.0         # ueber die Grenze
    assert hz_soll_zwischen(stuecke, 0.9, 1.1) == 10.0         # ueber die andere
    assert hz_soll_zwischen(stuecke, 9.0, 9.1) == 10.0         # ausserhalb


def test_abschnitte_decken_den_ganzen_lauf(tmp_path):
    from spotlab.messung.fenster import abschnitte

    ordner = _lauf(tmp_path, [_start(1.0, "G3", hz=50), _ende(2.0, "G3")],
                   [_satz(t / 10) for t in range(0, 30)])
    stuecke = abschnitte(ordner)
    assert [s["hz_soll"] for s in stuecke] == [10.0, 50.0, 10.0]
    assert stuecke[0]["von_s"] == 0.0
    assert stuecke[-1]["bis_s"] == pytest.approx(2.9)


# =========================================================== S3.3 bis S3.6
#
# Vier Definitionsfehler aus docs/HAERTUNG.md, alle vor der ersten echten
# Messkampagne zu beheben: sonst werden sie erst nach dem teuren Robotertermin
# sichtbar.


def _satz_mit(t, **daten):
    grund = {"pose": [0.0, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0], "joints": {},
             "feet": [True] * 4, "z": 0.42, "roll": 0.0, "pitch": 0.0, "t_robot": t}
    grund.update(daten)
    return {"t": t, "daten": grund}


def test_gierwinkel_bei_fensterstart_wird_mitgeschrieben():
    """S3.3: erreichte Geschwindigkeit und Querdrift sind reine odom-x/y-
    Differenzen. Ohne den Startwinkel laesst sich nicht nachrechnen, wie viel
    davon nur Gierdrift war."""
    from spotlab.messung.fenster import kennzahlen

    saetze = [_satz_mit(i * 0.02, pose=[0.0, 0.0, 0.6]) for i in range(20)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["gier_start_grad"] == pytest.approx(math.degrees(0.6), abs=0.01)


def test_luecken_sind_im_fenster_verortbar():
    """S3.4: `von_s` war bei Zeitquelle `robot` ein absoluter Epochenstempel
    (1.78e9), waehrend das Fenster selbst laufrelativ zaehlt. Eine Luecke liess
    sich damit nicht mehr im Fenster verorten."""
    from spotlab.messung.fenster import kennzahlen

    t0 = 1_786_000_000.0
    zeiten = [t0 + i * 0.02 for i in range(10)] + [t0 + 1.0]
    saetze = [_satz_mit(t) for t in zeiten]
    luecken = kennzahlen(saetze, [], "robot", 50.0)["luecken"]
    assert len(luecken) == 1
    luecke = luecken[0]
    assert "von_s" not in luecke, "der zweideutige Schluessel ist noch da"
    assert luecke["ab_start_s"] == pytest.approx(0.18, abs=0.01)
    assert luecke["laenge_s"] == pytest.approx(0.82, abs=0.01)
    # Der rohe Stempel bleibt erhalten -- in der Uhr, die `zeitquelle` nennt.
    assert luecke["t_roh_s"] == pytest.approx(t0 + 0.18, abs=0.01)


def test_reich_prueft_alle_saetze_nicht_nur_den_ersten(tmp_path):
    """S3.6: der Ratenwechsel wirkt erst ab dem naechsten Takt, der ERSTE Satz
    im Fenster ist also oft noch schlank. `reich` meldete dann False -- genau
    dort, wo man als Erstes nachsieht, ob Terrain-Daten vorliegen."""
    saetze = [_satz_mit(0.01)]                       # schlank, kein feet_detail
    saetze += [
        _satz_mit(0.02 + i * 0.02,
                  feet_detail=[{"kontakt": True, "pos": [0.3, 0.2, -0.42]}] * 4)
        for i in range(10)
    ]
    ordner = _lauf(tmp_path, [_start(0.0, "G3"), _ende(0.5, "G3")], saetze)
    assert fenster(ordner)[0].reich is True


def test_reich_bleibt_falsch_wenn_kein_satz_reich_ist(tmp_path):
    """Gegenprobe: sonst meldete jedes Fenster `reich`."""
    saetze = [_satz_mit(0.02 + i * 0.02) for i in range(10)]
    ordner = _lauf(tmp_path, [_start(0.0, "G3"), _ende(0.5, "G3")], saetze)
    assert fenster(ordner)[0].reich is False
