"""Die Dateien zwischen Agent, GUI und Steuerzentrale (Agenten am Spot, Teil 1)."""

import pytest

from spotlab.record import agent as a
from spotlab.record import zentrale as z
from spotlab.record.events import ARTEN


def test_ein_befehl_kommt_heil_an_und_lebt_eine_halbe_sekunde(tmp_path):
    a.schreibe_befehl(tmp_path, 4, "ziel", {"x": 1.5, "y": -2.0}, "zur Tür", "claude",
                      jetzt=lambda: 100.0)
    befehl = a.lies_befehl(tmp_path)
    assert befehl == a.Befehl(4, "ziel", {"x": 1.5, "y": -2.0}, "zur Tür", "claude", 100.0)
    assert a.befehl_lebt(befehl, jetzt=lambda: 100.0 + a.AGENT_TOTMANN_S)
    assert not a.befehl_lebt(befehl, jetzt=lambda: 100.01 + a.AGENT_TOTMANN_S)
    assert not a.befehl_lebt(None)


def test_unbekannte_art_wird_nicht_geschrieben(tmp_path):
    with pytest.raises(ValueError):
        a.schreibe_befehl(tmp_path, 1, "tanzen", {}, "", "claude")


@pytest.mark.parametrize("inhalt", ["{halb", '{"nummer": 1}',
                                     '{"nummer": 1, "art": "tanzen", "werte": {}, "warum": "",'
                                     ' "agent": "x", "lebt": 1.0}'])
def test_kaputt_fehlend_oder_unbekannt_ist_nichts(tmp_path, inhalt):
    assert a.lies_befehl(tmp_path) is None
    (tmp_path / a.BEFEHL).write_text(inhalt, encoding="utf-8")
    assert a.lies_befehl(tmp_path) is None


def test_die_freigabe_gilt_nur_mit_frischem_gui_puls(tmp_path):
    assert not a.freigabe_gilt(tmp_path, jetzt=lambda: 50.0)            # nichts da
    a.schreibe_freigabe(tmp_path, True, 1, jetzt=lambda: 50.0)
    assert a.lies_freigabe(tmp_path) == {"an": True, "nummer": 1, "t": 50.0}
    assert not a.freigabe_gilt(tmp_path, jetzt=lambda: 50.0), "ohne Puls gilt sie nicht"
    z.schreibe_gui_puls(tmp_path, jetzt=lambda: 50.0)
    assert a.freigabe_gilt(tmp_path, jetzt=lambda: 50.0 + a.FREIGABE_PULS_S)
    assert not a.freigabe_gilt(tmp_path, jetzt=lambda: 50.01 + a.FREIGABE_PULS_S)
    a.schreibe_freigabe(tmp_path, False, 2, jetzt=lambda: 51.0)
    assert not a.freigabe_gilt(tmp_path, jetzt=lambda: 51.0)


def test_der_besitz_nennt_agent_und_prozess(tmp_path):
    assert a.lies_besitz(tmp_path) is None
    a.schreibe_besitz(tmp_path, "codex", 4711, jetzt=lambda: 7.0)
    assert a.lies_besitz(tmp_path) == {"agent": "codex", "pid": 4711, "seit": 7.0}


def test_die_neuen_ereignisse_sind_erlaubt():
    assert {"agent_befehl", "agent_ergebnis", "freigabe"} <= ARTEN


@pytest.mark.parametrize("art", ["karte_laden", "aufnahme_start", "aufnahme_stopp",
                                 "wegpunkt_setzen", "zum_wegpunkt", "merkort_setzen",
                                 "merkort_loeschen", "zum_merkort"])
def test_die_kartenbefehle_aus_teil_2(tmp_path, art):
    a.schreibe_befehl(tmp_path, 7, art, {"name": "Tür"}, "", "claude", jetzt=lambda: 1.0)
    assert a.lies_befehl(tmp_path).art == art
