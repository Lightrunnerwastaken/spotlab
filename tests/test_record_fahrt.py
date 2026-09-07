"""fahrt.json: der Fahrbefehl des Uebungsfensters fuer das Programm `fahren.py`."""

import pytest

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


def test_die_tastenbelegung():
    assert fahrt.befehl_aus_tasten(set()) == (0.0, 0.0, 0.0)
    assert fahrt.befehl_aus_tasten({"w"}) == (fahrt.TEMPO_M_S, 0.0, 0.0)
    assert fahrt.befehl_aus_tasten({"s", "d"}) == (-fahrt.TEMPO_M_S, -fahrt.QUER_M_S, 0.0)
    assert fahrt.befehl_aus_tasten({"a", "e"}) == (0.0, fahrt.QUER_M_S, -fahrt.DREH_RAD_S)
    assert fahrt.befehl_aus_tasten({"w", "s"}) == (0.0, 0.0, 0.0)          # hebt sich auf
    assert fahrt.befehl_aus_tasten({"q", "x"}) == (0.0, 0.0, fahrt.DREH_RAD_S)
    # Der Faktor drosselt alle drei Achsen -- „Langsam" in der Ansicht „Fahren".
    assert fahrt.befehl_aus_tasten({"w", "a", "q"}, faktor=0.5) == (
        pytest.approx(fahrt.TEMPO_M_S / 2), pytest.approx(fahrt.QUER_M_S / 2),
        pytest.approx(fahrt.DREH_RAD_S / 2))


def test_die_tempostufen():
    """Drei Stufen als Faktor auf alle Achsen; der Deckel aus config.toml gilt zusaetzlich."""
    assert [name for name, _ in fahrt.STUFEN] == ["langsam", "normal", "schnell"]
    assert fahrt.faktor_der_stufe("langsam") == 0.5
    assert fahrt.faktor_der_stufe("normal") == 1.0
    assert fahrt.faktor_der_stufe("schnell") == 2.0
    with pytest.raises(ValueError):
        fahrt.faktor_der_stufe("rasend")


def test_schreiben_uebersteht_einen_kurzen_lesekonflikt(tmp_path, monkeypatch):
    """Windows: os.replace scheitert mit PermissionError, solange der Leser die Datei
    offen hat (gesehen in der Gesamtsuite am 07.09.2026). Kurz wiederholen, dann
    aufgeben -- der naechste Takt schreibt ohnehin; nie werfen."""
    from spotlab.record import atomar

    echt = atomar._ersetze
    versuche = {"n": 0}

    def zickig(quelle, ziel):
        versuche["n"] += 1
        if versuche["n"] < 3:
            raise PermissionError("Zugriff verweigert")
        return echt(quelle, ziel)

    monkeypatch.setattr(atomar, "_ersetze", zickig)
    fahrt.schreibe(tmp_path, 0.1, 0.0, 0.0)
    assert fahrt.lies(tmp_path)[0] == 0.1 and versuche["n"] == 3

    def nie(quelle, ziel):
        raise PermissionError("Zugriff verweigert")

    monkeypatch.setattr(atomar, "_ersetze", nie)
    fahrt.schreibe(tmp_path, 0.2, 0.0, 0.0)                 # gibt auf, wirft nicht
    assert fahrt.lies(tmp_path)[0] == 0.1 and not list(tmp_path.glob("*.tmp"))
