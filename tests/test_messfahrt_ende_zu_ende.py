import json
import os
import subprocess
import sys
from pathlib import Path

from spotlab.messung.fenster import fenster, schreibe
from tests_zeitgrenzen import TEST_TIMEOUT_S

QUELLE = str(Path(__file__).resolve().parents[1] / "src")

SKRIPT = '''
import spotlab

with spotlab.connect(backend="dryrun") as spot:
    spot.power_on()
    spot.stand()
    with spot.messfenster("G1", hz=50):
        spot.walk(vx=0.0, duration=0.4)
    spot.walk(vx=0.0, duration=0.3)
    with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
        spot.walk(vx=0.30, duration=0.4)
'''


def _messfahrt(tmp_path):
    """Ein echter Lauf in einem echten Projekt: <arbeitsordner>/demo/runs/<id>."""
    projekt = tmp_path / "demo"
    projekt.mkdir()
    skript = projekt / "messfahrt.py"
    skript.write_text(SKRIPT, encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(skript)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(projekt),
        env={**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1"},
        timeout=TEST_TIMEOUT_S,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    laeufe = list((projekt / "runs").iterdir())
    assert len(laeufe) == 1
    return laeufe[0]


def test_messfahrt_im_trockenlauf_ergibt_zwei_auswertbare_fenster(tmp_path):
    """Ein echter Prozess — Attrappen pruefen nur, dass die Argumente stimmen."""
    lauf = _messfahrt(tmp_path)

    gefunden = fenster(lauf)
    assert [f.name for f in gefunden] == ["G1", "G3"]
    for f in gefunden:
        assert f.abtastungen > 0, f.name
        assert f.reich is True, f.name
        assert f.zeitquelle == "robot", f.name
        assert f.unvollstaendig is False, f.name
        assert f.messwerte["hoehe_mittel"] > 0.3
        assert f.messwerte["mu_mittel"] is not None

    g3 = gefunden[1]
    assert g3.felder == {"stuetzstelle": "0.30"}
    assert g3.messwerte["kommandiert"]["vx"] == 0.30

    pfad = schreibe(lauf)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    assert [f["name"] for f in daten["fenster"]] == ["G1", "G3"]


def test_ausserhalb_der_fenster_bleibt_es_schlank(tmp_path):
    lauf = _messfahrt(tmp_path)
    saetze = [
        json.loads(z)
        for z in (lauf / "zustand.jsonl").read_text(encoding="utf-8").splitlines()
        if z.strip()
    ]
    schlanke = [s for s in saetze if "feet_detail" not in s["daten"]]
    assert schlanke, "kein einziger schlanker Satz — die Rate wird nicht zurückgestellt"
    # Und die Immer-Felder fehlen nirgends.
    assert all({"z", "roll", "pitch", "t_robot"} <= set(s["daten"]) for s in saetze)


def test_die_messfahrt_meldet_keine_falschen_luecken(tmp_path, monkeypatch):
    """Der Ratenwechsel darf keinen Alarm ausloesen, den man wegzuklicken lernt."""
    from spotlab.config import Config, Limits
    from spotlab.mcp import werkzeuge

    lauf = _messfahrt(tmp_path)
    monkeypatch.setattr(
        werkzeuge, "load_config",
        lambda: Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path)),
    )
    antwort = werkzeuge.zustand_zusammenfassen(lauf.name)
    assert "fehler" not in antwort, antwort
    # Ob nach dem letzten Fenster noch eine Abtastung liegt, haengt am Timing des
    # Abbaus — geprueft wird der Wechsel, nicht der Schwanz.
    raten = [a["hz_soll"] for a in antwort["abschnitte"]]
    assert raten[:4] == [10.0, 50.0, 10.0, 50.0], raten
    assert all(r in (10.0, 50.0) for r in raten)

    # Geprueft wird die ART der Luecke, nicht ihre Abwesenheit.
    #
    # `luecken == []` stand hier und war auf diesem Rechner meistens wahr. In
    # einer frischen Umgebung unter Last kamen vier Luecken von je 46 bis 47 ms
    # heraus — kein Fehler im Detektor, sondern Windows: die Zeitgeberaufloesung
    # ist rund 15.6 ms, ein 20-ms-Takt (50 Hz) rutscht damit regelmaessig auf
    # 31 ms, gelegentlich auf 47. In der CI, wo der Rechner geteilt ist, waere
    # der Test rot gewesen, ohne dass irgendetwas kaputt war — und ein Test, den
    # man wegzuklicken lernt, ist schlimmer als keiner.
    #
    # Der EIGENTLICHE Fehler, gegen den dieser Test steht, sieht anders aus:
    # rechnet der Detektor am Ratenwechsel mit der falschen Erwartung, meldet er
    # den ganzen 10-Hz-Takt als Luecke — also 100 ms, nicht 47. Deshalb die
    # Grenze bei einem 10-Hz-Takt. Genau so sah der Wettlauf im Abtaster aus
    # (Periode vor dem Stempel gelesen, Startereignis vor dem Umschalten
    # geschrieben): "Luecke 0.101 s", einmal in fuenf Laeufen, 06.09.2026 --
    # siehe test_sampler.py und test_record_messfenster.py.
    laengen = [luecke["laenge_s"] for luecke in antwort["luecken"]]
    assert all(laenge < 0.1 for laenge in laengen), (
        f"Luecke in Groesse eines ganzen 10-Hz-Takts: {antwort['luecken']}"
    )
    # Und Jitter bleibt Jitter: reisst wirklich der Abtaster ab, sind es viele.
    assert len(laengen) <= max(3, antwort["abtastungen"] // 10), antwort["luecken"]


# ====================== S4.4 die Auswertung muss ohne das SDK importierbar sein
#
# spotlab.messung ist die Schicht, die matura-spot Zeile fuer Zeile spiegelt
# (src/spotsim/schritt.py ist eine woertliche Kopie). Dort ist bosdyn NICHT
# installiert. Zoege ein Import von spotlab.messung das SDK herein, waere der
# Zwilling nicht mehr gegen das Original testbar -- und das ist der einzige
# Grund, weshalb wir behaupten duerfen, dass Sim und Realroboter dieselbe
# Groesse berechnen.
#
# Der Umkehrschluss steht bewusst NICHT hier: dass record/sampler.py ueber
# api/state.py bosdyn hereinzieht, ist kein Versehen. backends/dryrun.py baut
# echte RobotState-Protos, damit die Attrappe sich verhaelt wie der Roboter.
# Genau das hat den end_time_secs-Fehler ueberhaupt erst sichtbar gemacht.
# Ein Trockenlauf ohne SDK waere billiger und wertloser.


def test_die_auswertung_zieht_weder_sdk_noch_qt_herein():
    code = (
        "import sys\n"
        "import spotlab.messung.schritt\n"
        "import spotlab.messung.fenster\n"
        "import spotlab.record.read\n"
        "verboten = [m for m in ('bosdyn', 'PySide6', 'keyring') if m in sys.modules]\n"
        "print(','.join(verboten))\n"
    )
    ergebnis = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1"},
        timeout=TEST_TIMEOUT_S,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ergebnis.stdout.strip() == "", f"mitgeschleppt: {ergebnis.stdout.strip()}"
