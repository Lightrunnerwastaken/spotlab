"""fahrt.json: der Fahrbefehl des Uebungsfensters fuer das Programm `fahren.py`."""

from spotlab.record import fahrt


def test_schreiben_und_lesen(tmp_path):
    fahrt.schreibe(tmp_path, 0.4, -0.3, 0.8, jetzt=lambda: 100.0)
    assert (tmp_path / fahrt.DATEI).is_file()
    assert fahrt.lies(tmp_path, jetzt=lambda: 100.2) == (0.4, -0.3, 0.8)
    assert not list(tmp_path.glob("*.tmp"))


def test_ein_alter_befehl_heisst_stopp(tmp_path):
    fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: 100.0)
    assert fahrt.lies(tmp_path, jetzt=lambda: 100.0 + fahrt.TOTMANN_S + 0.01) == (0.0, 0.0, 0.0)


def test_ohne_oder_mit_kaputter_datei_stopp(tmp_path):
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0)
    (tmp_path / fahrt.DATEI).write_text("{kaputt", encoding="utf-8")
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0)
    (tmp_path / fahrt.DATEI).write_text('{"vx": "schnell", "t": 1e12}', encoding="utf-8")
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0)
