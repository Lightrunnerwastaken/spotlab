import json

from spotlab.record.read import list_runs, read_jsonl, read_run
from spotlab.record.run import RunRecorder


def test_abgeschnittene_letzte_zeile_wird_uebersprungen(tmp_path):
    datei = tmp_path / "ereignisse.jsonl"
    datei.write_text(
        '{"t": 0.1, "art": "verbunden", "daten": {}}\n{"t": 0.2, "art": "komm',
        encoding="utf-8",
    )
    saetze = read_jsonl(datei)
    assert len(saetze) == 1
    assert saetze[0]["art"] == "verbunden"


def test_fehlende_datei_ergibt_leere_liste(tmp_path):
    assert read_jsonl(tmp_path / "gibtsnicht.jsonl") == []


def test_lauf_wird_zusammengefasst(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun", nickname="Spot")
    rec.event("verbunden")
    rec.sample({"battery": 90.0})
    rec.finish("ok")

    zusammenfassung = read_run(rec.dir)
    assert zusammenfassung.ergebnis == "ok"
    assert zusammenfassung.backend == "dryrun"
    assert zusammenfassung.ereignisse_n == 2  # verbunden + ende
    assert zusammenfassung.abtastungen_n == 1


def test_abgestuerzter_lauf_bleibt_lesbar(tmp_path):
    """lauf.json steht auf 'läuft', ereignisse.jsonl endet mitten in einer Zeile."""
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("verbunden")
    with (rec.dir / "ereignisse.jsonl").open("a", encoding="utf-8") as datei:
        datei.write('{"t": 1.0, "art": "komm')

    zusammenfassung = read_run(rec.dir)
    assert zusammenfassung.ergebnis == "läuft"
    assert zusammenfassung.ereignisse_n == 1


def test_laeufe_kommen_neueste_zuerst(tmp_path):
    """Bewusst nur synthetische IDs: ein echter Lauf träge das heutige Datum und
    machte die Sortierung vom Kalender abhängig."""
    for kennung in ("20260101T120000Z_aaaaaaaa", "20270101T120000Z_bbbbbbbb"):
        verzeichnis = tmp_path / kennung
        verzeichnis.mkdir()
        (verzeichnis / "lauf.json").write_text(
            json.dumps({"id": kennung, "ergebnis": "ok"}), encoding="utf-8"
        )

    ids = [z.id for z in list_runs(tmp_path)]
    assert ids == ["20270101T120000Z_bbbbbbbb", "20260101T120000Z_aaaaaaaa"]


def test_leeres_runs_verzeichnis(tmp_path):
    assert list_runs(tmp_path / "gibtsnicht") == []
