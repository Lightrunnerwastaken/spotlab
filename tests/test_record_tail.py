import json

from spotlab.record.tail import JsonlTail


def _schreibe(pfad, *saetze, unvollstaendig=None):
    with pfad.open("a", encoding="utf-8") as datei:
        for satz in saetze:
            datei.write(json.dumps(satz, ensure_ascii=False) + "\n")
        if unvollstaendig is not None:
            datei.write(unvollstaendig)


def test_fehlende_datei_ergibt_leere_liste(tmp_path):
    assert JsonlTail(tmp_path / "gibtsnicht.jsonl").neue_saetze() == []


def test_liest_nur_neues(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, {"t": 2})
    tail = JsonlTail(pfad)
    assert [s["t"] for s in tail.neue_saetze()] == [1, 2]
    assert tail.neue_saetze() == []

    _schreibe(pfad, {"t": 3})
    assert [s["t"] for s in tail.neue_saetze()] == [3]


def test_halbe_letzte_zeile_wird_nicht_verschluckt(tmp_path):
    """Der wichtigste Fall: der Abtaster schreibt gerade, wir lesen mitten hinein."""
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, unvollstaendig='{"t": 2, "dat')
    tail = JsonlTail(pfad)
    assert [s["t"] for s in tail.neue_saetze()] == [1]

    with pfad.open("a", encoding="utf-8") as datei:  # Zeile fertigschreiben
        datei.write('en": {}}\n')
    assert [s["t"] for s in tail.neue_saetze()] == [2]


def test_verkuerzte_datei_setzt_den_stand_zurueck(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, {"t": 2})
    tail = JsonlTail(pfad)
    tail.neue_saetze()

    pfad.write_text("", encoding="utf-8")
    _schreibe(pfad, {"t": 9})
    assert [s["t"] for s in tail.neue_saetze()] == [9]


def test_unlesbare_zeile_wird_uebersprungen(tmp_path):
    pfad = tmp_path / "z.jsonl"
    pfad.write_text('{"t": 1}\nkein json\n{"t": 2}\n', encoding="utf-8")
    assert [s["t"] for s in JsonlTail(pfad).neue_saetze()] == [1, 2]


def test_umlaute_ueberleben(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"art": "rückmeldung", "daten": {"status": "steht"}})
    assert JsonlTail(pfad).neue_saetze()[0]["art"] == "rückmeldung"


def test_stand_waechst_nur_bis_zum_zeilenumbruch(tmp_path):
    pfad = tmp_path / "z.jsonl"
    _schreibe(pfad, {"t": 1}, unvollstaendig="halb")
    tail = JsonlTail(pfad)
    tail.neue_saetze()
    # Nicht gegen eine gezählte Zeichenkette prüfen: Windows schreibt im
    # Textmodus \r\n, die Zeile ist dort ein Byte länger.
    assert tail.stand == pfad.stat().st_size - len("halb")
