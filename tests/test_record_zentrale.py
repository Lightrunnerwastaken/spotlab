"""Die Dateien zwischen dem Tab „Fahren“ (Steuerzentrale) und `workshop/zentrale.py`."""

from pathlib import Path

import pytest

from spotlab.record import atomar
from spotlab.record import zentrale as z


def test_das_klickziel_kommt_heil_an_und_lebt_eine_halbe_sekunde(tmp_path):
    z.schreibe_klickziel(tmp_path, 3, (1.5, -2.0), "langsam", jetzt=lambda: 100.0)
    kz = z.lies_klickziel(tmp_path)
    assert kz == z.Klickziel(3, (1.5, -2.0), "langsam", 100.0)
    assert z.lebt(kz, jetzt=lambda: 100.4)
    assert not z.lebt(kz, jetzt=lambda: 100.6)
    assert not z.lebt(None)


def test_ohne_ziel_heisst_abbrechen(tmp_path):
    z.schreibe_klickziel(tmp_path, 4, None, "normal", jetzt=lambda: 1.0)
    assert z.lies_klickziel(tmp_path).ziel is None


def test_kaputt_oder_fehlend_ist_nichts(tmp_path):
    assert z.lies_klickziel(tmp_path) is None
    (tmp_path / z.KLICKZIEL).write_text("{halb", encoding="utf-8")
    assert z.lies_klickziel(tmp_path) is None
    (tmp_path / z.KLICKZIEL).write_text('{"nummer": 1}', encoding="utf-8")
    assert z.lies_klickziel(tmp_path) is None


def test_aktionen_licht_und_ton(tmp_path):
    z.schreibe_aktion(tmp_path, 1, "licht", "gruen")
    assert z.lies_aktion(tmp_path) == {"nummer": 1, "art": "licht", "farbe": "gruen"}
    z.schreibe_aktion(tmp_path, 2, "ton")
    assert z.lies_aktion(tmp_path) == {"nummer": 2, "art": "ton", "farbe": None}
    with pytest.raises(ValueError):
        z.schreibe_aktion(tmp_path, 3, "tanz")
    with pytest.raises(ValueError):
        z.schreibe_aktion(tmp_path, 3, "licht", "pink")
    assert z.lies_aktion(tmp_path)["nummer"] == 2, "eine abgelehnte Aktion schreibt nichts"


def test_eine_kaputte_aktion_ist_keine(tmp_path):
    assert z.lies_aktion(tmp_path) is None
    (tmp_path / z.AKTION).write_text('{"nummer": "x"}', encoding="utf-8")
    assert z.lies_aktion(tmp_path) is None


def test_das_bild_liegt_vor_der_beschreibung(tmp_path, monkeypatch):
    """Wer ein neues `lagebild.json` sieht, findet das Bild dazu schon vor."""
    reihe = []
    echt = atomar.schreibe_atomar

    def merken(pfad, inhalt, **kw):
        reihe.append(Path(pfad).name)
        return echt(pfad, inhalt, **kw)

    monkeypatch.setattr(atomar, "schreibe_atomar", merken)
    assert z.schreibe_lagebild(tmp_path, {"t": 1.0}, b"PNG")
    assert reihe == [z.LAGEBILD_BILD, z.LAGEBILD]
    assert z.lies_lagebild(tmp_path) == {"t": 1.0}
    assert (tmp_path / z.LAGEBILD_BILD).read_bytes() == b"PNG"


def test_ein_lagebild_ohne_skizze_hat_kein_bild(tmp_path):
    z.schreibe_lagebild(tmp_path, {"t": 2.0, "breite": 0}, None)
    assert z.lies_lagebild(tmp_path)["breite"] == 0
    assert not (tmp_path / z.LAGEBILD_BILD).exists()


def test_ein_halb_geschriebenes_lagebild_ist_keins(tmp_path):
    (tmp_path / z.LAGEBILD).write_text('{"t": 1', encoding="utf-8")
    assert z.lies_lagebild(tmp_path) is None
    (tmp_path / z.LAGEBILD).write_text("[1, 2]", encoding="utf-8")
    assert z.lies_lagebild(tmp_path) is None


# ------------------------------------------------ Teil 2: Menschen (27.09.2026)


def test_ein_klickziel_kennt_seine_art(tmp_path):
    z.schreibe_klickziel(tmp_path, 5, (1.0, 2.0), "normal", jetzt=lambda: 1.0, art="mensch")
    assert z.lies_klickziel(tmp_path).art == "mensch"
    z.schreibe_klickziel(tmp_path, 6, (1.0, 2.0), "normal", jetzt=lambda: 1.0)
    assert z.lies_klickziel(tmp_path).art == "ort"
    with pytest.raises(ValueError):
        z.schreibe_klickziel(tmp_path, 7, (1.0, 2.0), "normal", art="hund")


def test_ein_altes_klickziel_ohne_art_ist_ein_ort(tmp_path):
    (tmp_path / z.KLICKZIEL).write_text(
        '{"nummer": 1, "ziel": [1, 2], "stufe": "normal", "lebt": 1.0}', encoding="utf-8")
    assert z.lies_klickziel(tmp_path).art == "ort"


def test_die_suchstufe_ist_eine_aktion(tmp_path):
    assert z.SUCHSTUFEN == ("aus", "sparsam", "normal", "rundum")
    z.schreibe_aktion(tmp_path, 3, "suche", stufe="rundum")
    assert z.lies_aktion(tmp_path) == {"nummer": 3, "art": "suche", "farbe": None, "stufe": "rundum"}
    with pytest.raises(ValueError):
        z.schreibe_aktion(tmp_path, 4, "suche", stufe="turbo")


def test_folgen_ist_ein_zustand():
    assert "folgt" in z.ZUSTAENDE


# ------------------------------------------------------------ Karten (Teil 3)


def test_ein_kartenauftrag_hin_und_zurueck(tmp_path):
    z.schreibe_kartenauftrag(tmp_path, 3, "aufnahme_start", name="flur-2")
    assert z.lies_kartenauftrag(tmp_path) == {"nummer": 3, "was": "aufnahme_start",
                                                      "name": "flur-2"}
    z.schreibe_kartenauftrag(tmp_path, 4, "aufnahme_stopp")
    assert z.lies_kartenauftrag(tmp_path)["name"] is None


def test_ein_unbekannter_kartenauftrag_wird_nicht_geschrieben(tmp_path):
    with pytest.raises(ValueError):
        z.schreibe_kartenauftrag(tmp_path, 1, "loeschen")
    assert z.lies_kartenauftrag(tmp_path) is None


def test_ein_kaputter_kartenauftrag_ist_keiner(tmp_path):
    (tmp_path / z.KARTENAUFTRAG).write_text('{"nummer": 1, "was": "sprengen"}',
                                                    encoding="utf-8")
    assert z.lies_kartenauftrag(tmp_path) is None
    (tmp_path / z.KARTENAUFTRAG).write_text("{halb", encoding="utf-8")
    assert z.lies_kartenauftrag(tmp_path) is None


def test_das_kartenbild_liegt_vor_der_beschreibung(tmp_path):
    z.schreibe_lagebild(tmp_path, {"t": 1.0}, b"skizze", kartenbild=b"karte")
    assert (tmp_path / z.LAGEBILD_KARTE).read_bytes() == b"karte"
    assert (tmp_path / z.LAGEBILD_BILD).read_bytes() == b"skizze"
    assert z.lies_lagebild(tmp_path) == {"t": 1.0}


def test_die_kartennummern_sind_verschieden_und_nicht_null():
    nummern = {z.KARTE_UNGEPRUEFT, z.KARTE_ERKANNT, z.KARTE_FEHLT,
               z.KARTE_NEU}
    assert len(nummern) == 4 and 0 not in nummern
