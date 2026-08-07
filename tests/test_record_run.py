import json
from datetime import UTC, datetime

import pytest

from spotlab.record.run import RunRecorder, run_id


def test_lauf_id_hat_zeitstempel_und_skript_hash(tmp_path):
    skript = tmp_path / "hallo.py"
    skript.write_text("print('hi')", encoding="utf-8")
    kennung = run_id(skript, datetime(2026, 8, 6, 14, 3, 27, tzinfo=UTC))
    zeit, _, kurz = kennung.partition("_")
    assert zeit == "20260806T140327Z"
    assert len(kurz) == 8 and all(c in "0123456789abcdef" for c in kurz)


def test_gleiches_skript_gleicher_hash(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1", encoding="utf-8")
    b.write_text("x = 1", encoding="utf-8")
    jetzt = datetime(2026, 8, 6, tzinfo=UTC)
    assert run_id(a, jetzt).split("_")[1] == run_id(b, jetzt).split("_")[1]


def test_ereignisse_landen_als_jsonl(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("verbunden", ip="1.2.3.4")
    rec.event("kommando", name="stand")
    rec.finish("ok")

    zeilen = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8").strip().split("\n")
    arten = [json.loads(z)["art"] for z in zeilen]
    assert arten == ["verbunden", "kommando", "ende"]
    assert json.loads(zeilen[0])["daten"] == {"ip": "1.2.3.4"}
    assert json.loads(zeilen[0])["t"] >= 0.0


def test_unbekannte_ereignisart_wird_abgelehnt(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    with pytest.raises(ValueError, match="Unbekannte Ereignisart"):
        rec.event("quatsch")


def test_lauf_json_traegt_ergebnis_und_dauer(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun", nickname="Spot der Kanti")
    rec.finish("fehler", "Akku leer")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["ergebnis"] == "fehler"
    assert daten["fehler"] == "Akku leer"
    assert daten["backend"] == "dryrun"
    assert daten["nickname"] == "Spot der Kanti"
    assert daten["dauer_s"] >= 0.0


def test_lauf_json_existiert_schon_waehrend_des_laufs(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["ergebnis"] == "läuft"


def test_skript_hash_und_pfad_stehen_in_lauf_json(tmp_path):
    skript = tmp_path / "hallo.py"
    skript.write_text("print('hi')", encoding="utf-8")
    rec = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    rec.finish("ok")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["skript"] == str(skript)
    assert len(daten["skript_sha256"]) == 64


def test_abtastungen_landen_in_zustand_jsonl(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 91.0})
    rec.sample({"battery": 90.5})
    rec.finish("ok")
    zeilen = (rec.dir / "zustand.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(zeilen) == 2
    assert json.loads(zeilen[1])["daten"]["battery"] == 90.5


def test_bild_wird_abgelegt_und_verzeichnet(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    ziel = rec.image("frontleft", b"\x89PNG-attrappe", {"source": "frontleft_fisheye_image"})
    rec.finish("ok")
    assert ziel.exists() and ziel.parent.name == "bilder"
    verzeichnis = json.loads((rec.dir / "bilder" / "bilder.json").read_text(encoding="utf-8"))
    assert verzeichnis[0]["source"] == "frontleft_fisheye_image"
    assert verzeichnis[0]["datei"] == ziel.name


def test_jede_zeile_wird_sofort_geschrieben(tmp_path):
    """Absturzfestigkeit: was geschrieben ist, ist auf der Platte."""
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("verbunden")
    inhalt = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert inhalt.endswith("\n")


def test_lauf_json_traegt_die_prozess_id(tmp_path):
    """Ohne die PID kann der Not-Aus keinen Lauf beenden, den er nicht selbst gestartet hat."""
    import os

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.finish("ok")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["pid"] == os.getpid()


def test_stopp_datei_ist_benannt():
    from spotlab.record.run import STOPP_DATEI

    assert STOPP_DATEI == "stopp"


def test_zwei_laeufe_in_derselben_sekunde_kollidieren_nicht(tmp_path):
    """Ohne Skript ist die Kurzkennung immer 'interakt' — ohne Auflösung
    schrieben beide Läufe in dasselbe Verzeichnis."""
    erster = RunRecorder(tmp_path, None, backend="dryrun")
    zweiter = RunRecorder(tmp_path, None, backend="dryrun")
    assert erster.dir != zweiter.dir
    assert zweiter.id.endswith("-2")


def test_gleiches_skript_zweimal_kollidiert_nicht(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    erster = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    zweiter = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    assert erster.dir != zweiter.dir
