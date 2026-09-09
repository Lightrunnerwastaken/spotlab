"""Der Watcher meldet `navigation.json`, wenn sie sich geaendert hat -- und nur dann."""

from spotlab.gui.watcher import RunScanner, _Lauf
from spotlab.record import navigation


def test_stand_wird_einmal_je_aenderung_gemeldet(tmp_path):
    lauf = _Lauf(tmp_path)
    assert RunScanner._neuer_navigationsstand(lauf) == []
    navigation.schreibe_stand(tmp_path, "bereit", standort="wp0", versatz=(0, 0, 0), jetzt=lambda: 1.0)
    [(art, daten)] = RunScanner._neuer_navigationsstand(lauf)
    assert art == "navigation" and daten["status"] == "bereit"
    assert RunScanner._neuer_navigationsstand(lauf) == [], "unveraendert: nicht noch einmal"
    navigation.schreibe_stand(tmp_path, "unterwegs", ziel="wp1", jetzt=lambda: 2.0)
    [(_, daten)] = RunScanner._neuer_navigationsstand(lauf)
    assert daten["status"] == "unterwegs" and daten["ziel"] == "wp1"


def test_ein_halb_geschriebener_stand_wird_beim_naechsten_takt_nachgelesen(tmp_path):
    lauf = _Lauf(tmp_path)
    (tmp_path / navigation.STAND_DATEI).write_text('{"status": "ber', encoding="utf-8")
    assert RunScanner._neuer_navigationsstand(lauf) == []
    navigation.schreibe_stand(tmp_path, "bereit", jetzt=lambda: 3.0)
    assert len(RunScanner._neuer_navigationsstand(lauf)) == 1


def test_der_letzte_stand_kommt_vor_dem_ende_auch_wenn_der_lauf_schon_tot_ist(tmp_path):
    """Beginn und Ende im selben Takt (der Lauf starb, bevor der Watcher ihn fand):
    der Stand muss trotzdem VOR `lauf_beendet` gemeldet werden -- sonst sieht der
    Tab nie, woran es lag."""
    scanner = RunScanner(tmp_path)
    lauf = _Lauf(tmp_path / "lauf")
    lauf.dir.mkdir()
    navigation.schreibe_stand(lauf.dir, "gescheitert", text="kein GraphNav", jetzt=lambda: 1.0)
    scanner._offen[str(lauf.dir)] = lauf
    arten = [art for art, _ in scanner._neuigkeiten(str(lauf.dir))]
    assert arten.index("navigation") < arten.index("lauf_beendet")
