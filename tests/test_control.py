import json
import os
import time

from spotlab.record.run import STOPP_DATEI, RunRecorder
from spotlab.workshop.control import (
    aktive_laeufe,
    beende_hart,
    ist_aktiv,
    pid_von,
    stoppe_freundlich,
)


def _lauf(tmp_path, pid=4711, alter_s=0.0):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.set_robot_info(pid=pid)
    rec.sample({"battery": 90.0})
    if alter_s:
        alt = time.time() - alter_s
        os.utime(rec.dir / "zustand.jsonl", (alt, alt))
    return rec.dir


def test_frischer_lauf_ist_aktiv(tmp_path):
    assert ist_aktiv(_lauf(tmp_path)) is True


def test_alter_lauf_ist_nicht_aktiv(tmp_path):
    assert ist_aktiv(_lauf(tmp_path, alter_s=30.0)) is False


def test_lauf_ohne_zustandsdatei_ist_nicht_aktiv(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    assert ist_aktiv(rec.dir) is False


def test_aktive_laeufe_filtert(tmp_path):
    frisch = _lauf(tmp_path)
    _lauf(tmp_path, alter_s=30.0)
    assert [p.name for p in aktive_laeufe(tmp_path)] == [frisch.name]


def test_aktive_laeufe_bei_fehlendem_ordner(tmp_path):
    assert aktive_laeufe(tmp_path / "gibtsnicht") == []


def test_pid_wird_gelesen(tmp_path):
    assert pid_von(_lauf(tmp_path, pid=1234)) == 1234


def test_pid_fehlt_ergibt_none(tmp_path):
    verzeichnis = tmp_path / "leer"
    verzeichnis.mkdir()
    (verzeichnis / "lauf.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    assert pid_von(verzeichnis) is None


def test_stopp_legt_die_markierung_an(tmp_path):
    verzeichnis = _lauf(tmp_path)
    stoppe_freundlich(verzeichnis)
    assert (verzeichnis / STOPP_DATEI).exists()


def test_stopp_ist_idempotent(tmp_path):
    verzeichnis = _lauf(tmp_path)
    stoppe_freundlich(verzeichnis)
    stoppe_freundlich(verzeichnis)  # darf nicht werfen


def test_hartes_beenden_ruft_den_killer(tmp_path):
    verzeichnis = _lauf(tmp_path, pid=1234)
    getroffen = []
    assert beende_hart(verzeichnis, killer=getroffen.append) is True
    assert getroffen == [1234]


def test_toter_lauf_wird_nicht_getoetet(tmp_path):
    """Prozess-IDs werden wiederverwendet — ein toter Lauf darf niemanden treffen."""
    verzeichnis = _lauf(tmp_path, pid=1234, alter_s=30.0)
    getroffen = []
    assert beende_hart(verzeichnis, killer=getroffen.append) is False
    assert getroffen == []


def test_lauf_ohne_pid_wird_nicht_getoetet(tmp_path):
    verzeichnis = _lauf(tmp_path)
    (verzeichnis / "lauf.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    getroffen = []
    assert beende_hart(verzeichnis, killer=getroffen.append) is False
    assert getroffen == []
