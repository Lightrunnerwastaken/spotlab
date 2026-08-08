import json
import os
import subprocess
import sys
from pathlib import Path

from spotlab.messung.fenster import fenster, schreibe

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
    assert antwort["luecken"] == [], antwort["luecken"]
