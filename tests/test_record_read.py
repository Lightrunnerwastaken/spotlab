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
    # Der Kern dieses Tests: die halbe Zeile macht die Datei nicht unlesbar.
    assert zusammenfassung.ereignisse_n == 1
    # Und er heisst nicht umsonst „abgestuerzt": lauf.json steht zwar auf
    # „läuft", aber es laeuft nichts mehr. Frueher zeigte jede Ansicht so einen
    # Lauf dauerhaft als aktiv an, mit 0.0 s Dauer (S2.9).
    assert zusammenfassung.ergebnis == "abgebrochen"


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


# ===================================== S2.9 / S2.15 abgestuerzte Laeufe, Version
#
# `ergebnis` bleibt auf "läuft", wenn finish() nie lief -- nach einem harten
# Abbruch, einem Stromausfall, einem Absturz. Die GUI zeigt solche Laeufe
# dauerhaft als laufend mit "0.0 s", obwohl sie es nicht sind. Der MCP-Pfad
# loest das bereits ueber ist_aktiv(); read_run() ist die Stelle, an der es
# EINMAL stehen muss, damit GUI und CLI es gemeinsam bekommen.


def _lauf(tmp_path, ergebnis="läuft", alter_s=None):
    import json
    import os
    import time

    ordner = tmp_path / "lauf"
    ordner.mkdir(exist_ok=True)
    (ordner / "lauf.json").write_text(
        json.dumps({"id": "x", "ergebnis": ergebnis, "dauer_s": 0.0,
                    "spotlab_version": "0.1.0"}),
        encoding="utf-8",
    )
    zustand = ordner / "zustand.jsonl"
    zustand.write_text("{}\n", encoding="utf-8")
    if alter_s:
        alt = time.time() - alter_s
        os.utime(zustand, (alt, alt))
    return ordner


def test_ein_abgestuerzter_lauf_gilt_nicht_mehr_als_laufend(tmp_path):
    from spotlab.record.read import read_run

    zusammenfassung = read_run(_lauf(tmp_path, "läuft", alter_s=600))
    assert zusammenfassung.ergebnis == "abgebrochen"


def test_ein_wirklich_laufender_lauf_bleibt_laufend(tmp_path):
    from spotlab.record.read import read_run

    assert read_run(_lauf(tmp_path, "läuft")).ergebnis == "läuft"


def test_ein_abgeschlossener_lauf_wird_nicht_umgedeutet(tmp_path):
    from spotlab.record.read import read_run

    assert read_run(_lauf(tmp_path, "ok", alter_s=600)).ergebnis == "ok"


def test_die_version_steht_in_der_zusammenfassung(tmp_path):
    """S2.15: steht in jeder lauf.json, war aber ueber keinen Leseweg sichtbar --
    fuer Versionsvergleiche im Unterricht und in der Maturaarbeit noetig."""
    from spotlab.record.read import read_run

    assert read_run(_lauf(tmp_path)).spotlab_version == "0.1.0"


def test_eine_alte_aufzeichnung_ohne_version_bleibt_lesbar(tmp_path):
    import json

    from spotlab.record.read import read_run

    ordner = tmp_path / "alt"
    ordner.mkdir()
    (ordner / "lauf.json").write_text(json.dumps({"id": "y"}), encoding="utf-8")
    assert read_run(ordner).spotlab_version is None
