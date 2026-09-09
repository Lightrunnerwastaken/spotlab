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
    # Die Uhr ausdruecklich, an der Datei verankert: sonst entscheidet die
    # Maschinenlast zwischen dem Schreiben und dieser Zeile, ob der Lauf noch
    # als frisch gilt -- und der Test behauptete etwas ueber die Last statt
    # ueber `ist_aktiv`.
    lauf = _lauf(tmp_path)
    gerade_eben = (lauf / "zustand.jsonl").stat().st_mtime + 0.1
    assert ist_aktiv(lauf, jetzt=gerade_eben) is True


def test_alter_lauf_ist_nicht_aktiv(tmp_path):
    assert ist_aktiv(_lauf(tmp_path, alter_s=30.0)) is False


def test_lauf_ohne_zustandsdatei_ist_nicht_aktiv(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    assert ist_aktiv(rec.dir) is False


def test_aktive_laeufe_filtert(tmp_path):
    # `aktive_laeufe` nimmt keine Uhr, wohl aber die Grenze: eine Stunde gegen
    # eben geschrieben trennt sicher, auch wenn der Test unter Last ein paar
    # Sekunden braucht. Geprueft wird das Filtern, nicht die 2-Sekunden-Grenze
    # (die hat ihren eigenen Test).
    frisch = _lauf(tmp_path)
    _lauf(tmp_path, alter_s=3600.0)
    assert [p.name for p in aktive_laeufe(tmp_path, grenze_s=60.0)] == [frisch.name]


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

    def killer(pid):
        getroffen.append(pid)
        return True          # der Killer meldet jetzt, OB er getroffen hat

    assert beende_hart(verzeichnis, killer=killer) is True
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


# ------------------------------------- ehrlicher NOT-AUS (A9, S1.7)


def _im_abbau(tmp_path, alter_s=8.0):
    """Ein Lauf, dessen Abtaster schon schweigt, waehrend close() noch laeuft."""
    from spotlab.record.run import ABBAU_DATEI

    verzeichnis = _lauf(tmp_path, pid=4242, alter_s=alter_s)
    (verzeichnis / ABBAU_DATEI).touch()
    return verzeichnis


def test_beende_hart_meldet_misserfolg_wenn_das_toeten_scheitert(tmp_path):
    """Bisher gab beende_hart() True zurueck, sobald es den Killer aufgerufen
    hatte -- unabhaengig davon, ob taskkill den Prozess wirklich erwischt hat.
    Die GUI meldete dem Schueler dann "beendet", waehrend der Roboter weiterlief.
    """
    verzeichnis = _lauf(tmp_path, pid=1234)
    assert beende_hart(verzeichnis, killer=lambda pid: False) is False


def test_beende_hart_meldet_erfolg_wenn_der_killer_ihn_meldet(tmp_path):
    verzeichnis = _lauf(tmp_path, pid=1234)
    assert beende_hart(verzeichnis, killer=lambda pid: True) is True


def test_ein_lauf_im_abbau_gilt_weiter_als_aktiv(tmp_path):
    """DER Fall, der A9 unterlaeuft: bei Strg-C hoert der Abtaster sofort auf,
    aber close() laeuft noch bis zu 20 s (power_off timeout_sec=20). In genau
    diesem Fenster meldete ist_aktiv() False -- der NOT-AUS-Knopf traf also
    niemanden, waehrend der Spot noch unter Strom stand.
    """
    assert ist_aktiv(_im_abbau(tmp_path, alter_s=8.0)) is True


def test_der_notaus_trifft_einen_lauf_im_abbau(tmp_path):
    getroffen = []
    verzeichnis = _im_abbau(tmp_path, alter_s=8.0)
    assert beende_hart(verzeichnis, killer=lambda pid: getroffen.append(pid) or True)
    assert getroffen == [4242]


def test_ohne_abbau_markierung_bleibt_es_bei_der_alten_regel(tmp_path):
    """Ein abgestuerzter Prozess kommt nie dazu, die Markierung anzulegen --
    die Prozess-ID-Regel darf dadurch nicht aufgeweicht werden."""
    assert ist_aktiv(_lauf(tmp_path, alter_s=8.0)) is False


def test_auch_das_abbaufenster_ist_endlich(tmp_path):
    """Mitten im Abbau getoetet: die Markierung bleibt liegen. Danach greift
    wieder die Prozess-ID-Regel."""
    from spotlab.workshop.control import ABBAU_FRIST_S

    verzeichnis = _im_abbau(tmp_path, alter_s=10.0)
    spaeter = time.time() + ABBAU_FRIST_S + 1.0
    assert ist_aktiv(verzeichnis, jetzt=spaeter) is False


def test_finish_raeumt_die_abbau_markierung_weg(tmp_path):
    """Sonst gaelte jeder sauber beendete Lauf noch 30 s als aktiv."""
    from spotlab.record.run import ABBAU_DATEI

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    rec.abbau_beginnt()
    assert (rec.dir / ABBAU_DATEI).exists()
    rec.finish("ok")
    assert not (rec.dir / ABBAU_DATEI).exists()
