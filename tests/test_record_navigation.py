"""`ziel.json` und `navigation.json`: der Draht zwischen Karten-Tab und Navigationslauf."""

import pytest

from spotlab.record import navigation


def test_ziel_hin_und_zurueck(tmp_path):
    assert navigation.schreibe_ziel(tmp_path, "wp1", 3, jetzt=lambda: 10.0)
    assert navigation.lies_ziel(tmp_path) == ("wp1", 3)
    assert not list(tmp_path.glob("*.tmp")), "atomar geschrieben"


def test_ohne_oder_mit_kaputtem_ziel_kommt_none(tmp_path):
    assert navigation.lies_ziel(tmp_path) is None
    (tmp_path / navigation.ZIEL_DATEI).write_text('{"wegpunkt": "wp1"', encoding="utf-8")
    assert navigation.lies_ziel(tmp_path) is None
    (tmp_path / navigation.ZIEL_DATEI).write_text('{"wegpunkt": "wp1"}', encoding="utf-8")
    assert navigation.lies_ziel(tmp_path) is None, "ohne Nummer ist es kein Ziel"


def test_stand_hin_und_zurueck(tmp_path):
    assert navigation.schreibe_stand(
        tmp_path, "unterwegs", text="", karte="flur", ziel="wp3",
        standort="wp1", versatz=(0.5, -0.25, 90), jetzt=lambda: 5.0)
    stand = navigation.lies_stand(tmp_path)
    assert stand["status"] == "unterwegs" and stand["karte"] == "flur" and stand["ziel"] == "wp3"
    assert stand["standort"] == "wp1" and stand["versatz"] == [0.5, -0.25, 90.0] and stand["t"] == 5.0


def test_ein_unbekannter_stand_wird_abgewiesen(tmp_path):
    with pytest.raises(ValueError, match="Unbekannter Navigationsstand"):
        navigation.schreibe_stand(tmp_path, "fliegt")


def test_halb_geschriebener_stand_liest_sich_als_none(tmp_path):
    assert navigation.lies_stand(tmp_path) is None
    (tmp_path / navigation.STAND_DATEI).write_text('{"status": "bere', encoding="utf-8")
    assert navigation.lies_stand(tmp_path) is None
    (tmp_path / navigation.STAND_DATEI).write_text(
        '{"status": "bereit", "versatz": [1, 2]}', encoding="utf-8")
    stand = navigation.lies_stand(tmp_path)
    assert stand["status"] == "bereit" and stand["versatz"] is None, "ein kaputter Versatz ist keiner"
