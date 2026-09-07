"""kamera.json im Lauf-Verzeichnis: der Kamerawunsch des Uebungsfensters fuer den Ansichtsthread."""

from spotlab.record import kamera


def test_schreiben_und_lesen(tmp_path):
    kamera.schreibe(tmp_path, "verfolgen", 2.5)
    assert (tmp_path / kamera.DATEI).is_file()
    assert kamera.lies(tmp_path) == ("verfolgen", 2.5)
    assert not list(tmp_path.glob("*.tmp"))


def test_ohne_datei_die_vorgabe(tmp_path):
    assert kamera.lies(tmp_path) == (kamera.VORGABE_MODUS, kamera.VORGABE_ZOOM) == ("raum", 1.0)


def test_kaputt_oder_unbekannt_heisst_vorgabe(tmp_path):
    (tmp_path / kamera.DATEI).write_text("{nicht json", encoding="utf-8")
    assert kamera.lies(tmp_path) == ("raum", 1.0)
    (tmp_path / kamera.DATEI).write_text('{"modus": "drohne", "zoom": "gross"}', encoding="utf-8")
    assert kamera.lies(tmp_path) == ("raum", 1.0)


def test_der_zoom_ist_begrenzt(tmp_path):
    kamera.schreibe(tmp_path, "raum", 100.0)
    assert kamera.lies(tmp_path) == ("raum", kamera.ZOOM_BEREICH[1])
    kamera.schreibe(tmp_path, "raum", 0.01)
    assert kamera.lies(tmp_path) == ("raum", kamera.ZOOM_BEREICH[0])


def test_stand_sagt_ob_sich_die_datei_geaendert_hat(tmp_path):
    assert kamera.stand(tmp_path) is None
    kamera.schreibe(tmp_path, "raum", 1.0)
    erster = kamera.stand(tmp_path)
    assert erster is not None
    kamera.schreibe(tmp_path, "verfolgen", 1.0)
    assert kamera.stand(tmp_path) != erster


def test_schreiben_uebersteht_einen_kurzen_lesekonflikt(tmp_path, monkeypatch):
    from spotlab.record import atomar

    def nie(quelle, ziel):
        raise PermissionError("Zugriff verweigert")

    monkeypatch.setattr(atomar, "_ersetze", nie)
    kamera.schreibe(tmp_path, "verfolgen", 2.0)             # gibt auf, wirft nicht
    assert kamera.lies(tmp_path) == ("raum", 1.0) and not list(tmp_path.glob("*.tmp"))
