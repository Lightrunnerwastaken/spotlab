import os
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.views.live import LiveView  # noqa: E402
from spotlab.record.run import STOPP_DATEI, RunRecorder  # noqa: E402


def _lauf(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0})
    return rec


def test_leerer_zustand_sagt_was_zu_tun_ist(qapp):
    # Referenz festhalten, sonst räumt Python das Widget sofort ab.
    ansicht = LiveView()
    text = ansicht.leer.text().lower()
    assert "starten" in text or "programm" in text


def test_zustand_fuellt_die_kacheln(qapp, tmp_path):
    ansicht = LiveView()
    ansicht.setze_lauf(_lauf(tmp_path).dir, "hallo_spot.py")
    ansicht.zeige_zustand(
        {"daten": {"battery": 61.0, "pose": [1.02, 0.0, 0.0],
                   "velocity": [0.30, 0.0, 0.0], "feet": [True, True, False, True]}}
    )
    assert "1.02" in ansicht.kachel_pose.text()
    assert "0.30" in ansicht.kachel_tempo.text()
    assert "61" in ansicht.kachel_akku.text()


def test_ereignisse_landen_in_der_liste(qapp, tmp_path):
    ansicht = LiveView()
    ansicht.setze_lauf(_lauf(tmp_path).dir, "x.py")
    ansicht.zeige_ereignis({"t": 0.28, "art": "kommando", "daten": {"name": "stand"}})
    assert ansicht.ereignisliste.count() == 1
    assert "stand" in ansicht.ereignisliste.item(0).text()


def test_ausgabe_wird_angehaengt(qapp, tmp_path):
    ansicht = LiveView()
    ansicht.setze_lauf(_lauf(tmp_path).dir, "x.py")
    ansicht.zeige_ausgabe("Akku: 87 %")
    assert "Akku: 87 %" in ansicht.ausgabe.toPlainText()


def test_stopp_legt_die_markierung_an(qapp, tmp_path):
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.stopp_knopf.click()
    assert (rec.dir / STOPP_DATEI).exists()


def test_eskalation_erscheint_erst_wenn_es_haengt(qapp, tmp_path):
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.stopp_knopf.click()
    assert not ansicht.hart_knopf.isVisible()

    ansicht._pruefe_eskalation()  # Zeitgeber von Hand auslösen
    assert not ansicht.hart_knopf.isHidden()


def test_keine_eskalation_wenn_der_lauf_endete(qapp, tmp_path):
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.stopp_knopf.click()

    alt = time.time() - 60
    os.utime(rec.dir / "zustand.jsonl", (alt, alt))
    ansicht._pruefe_eskalation()
    assert ansicht.hart_knopf.isHidden()


def test_notaus_ruft_hartes_beenden(qapp, tmp_path, monkeypatch):
    gerufen = []
    monkeypatch.setattr(
        "spotlab.gui.views.live.beende_hart", lambda p, **kw: gerufen.append(p) or True
    )
    rec = _lauf(tmp_path)
    ansicht = LiveView()
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.notaus()
    assert gerufen == [rec.dir]


def test_notaus_ohne_lauf_meldet_das(qapp):
    meldungen = []
    ansicht = LiveView()
    ansicht.meldung.connect(meldungen.append)
    ansicht.notaus()
    assert meldungen and "läuft" in meldungen[0].lower()


def test_gescheitertes_notaus_schickt_zum_physischen_knopf(qapp, tmp_path, monkeypatch):
    """Der gefaehrlichste Fall im ganzen Fenster.

    Wenn taskkill den Prozess NICHT erwischt (Rechte, haengender Prozess), meldete
    die Ansicht bisher "Der Lauf laeuft nicht mehr" -- eine Entwarnung, waehrend
    der Roboter weiterfaehrt. Der Schueler muss stattdessen zum physischen
    Not-Aus geschickt werden.
    """
    monkeypatch.setattr("spotlab.gui.views.live.beende_hart", lambda p, **kw: False)
    monkeypatch.setattr("spotlab.gui.views.live.ist_aktiv", lambda p, **kw: True)
    rec = _lauf(tmp_path)
    meldungen = []
    ansicht = LiveView()
    ansicht.meldung.connect(meldungen.append)
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.notaus()

    assert meldungen, "keine Rueckmeldung nach gescheitertem NOT-AUS"
    text = meldungen[-1]
    assert "nicht" in text.lower()
    assert "not-aus" in text.lower() or "tablet" in text.lower(), text
    assert "läuft nicht mehr" not in text.lower(), "faelschliche Entwarnung: " + text


def test_notaus_auf_totem_lauf_meldet_das_weiterhin(qapp, tmp_path, monkeypatch):
    """Gegenprobe: der harmlose Fall darf nicht zur Alarmmeldung werden."""
    monkeypatch.setattr("spotlab.gui.views.live.beende_hart", lambda p, **kw: False)
    monkeypatch.setattr("spotlab.gui.views.live.ist_aktiv", lambda p, **kw: False)
    rec = _lauf(tmp_path)
    meldungen = []
    ansicht = LiveView()
    ansicht.meldung.connect(meldungen.append)
    ansicht.setze_lauf(rec.dir, "x.py")
    ansicht.notaus()
    assert meldungen and "läuft nicht mehr" in meldungen[-1].lower()
