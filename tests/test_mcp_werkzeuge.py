import json

import pytest

from spotlab.anbindung.manifest import DATEINAME
from spotlab.mcp import werkzeuge

MANIFEST = """
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation"

[[skript]]
name = "Baseline"
datei = "scripts/experiment_baseline.py"
argumente = ["--kurz"]
roboter = false

[[skript]]
name = "Echte Fahrt"
datei = "scripts/sdk_drive.py"
roboter = true
"""


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Arbeitsordner und fremdes Projekt, mit umgebogener Konfiguration."""
    from spotlab.config import Config, Limits

    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "matura-spot"
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "experiment_baseline.py").write_text(
        "import sys\nprint('args:', ' '.join(sys.argv[1:]))\n", encoding="utf-8"
    )
    (projekt / "scripts" / "sdk_drive.py").write_text("print('faehrt')\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")

    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(arbeit))
    monkeypatch.setattr(werkzeuge, "load_config", lambda: cfg)
    return arbeit, projekt


def test_arbeitsordner_kommt_aus_der_konfiguration(welt):
    arbeit, _ = welt
    assert werkzeuge.arbeitsordner() == arbeit


def test_ohne_arbeitsordner_kommt_ein_fehler_statt_absturz(monkeypatch):
    from spotlab.config import Config, Limits

    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), workspace="")
    monkeypatch.setattr(werkzeuge, "load_config", lambda: cfg)
    antwort = werkzeuge.anbindungen_auflisten()
    assert "fehler" in antwort[0]


def test_ohne_konfiguration_kommt_ein_fehler_statt_absturz(monkeypatch):
    from spotlab.errors import ConfigMissing

    def wirf():
        raise ConfigMissing("Keine Konfiguration. Einrichten mit `spotlab login`.")

    monkeypatch.setattr(werkzeuge, "load_config", wirf)
    assert "fehler" in werkzeuge.anbindungen_auflisten()[0]
    assert "fehler" in werkzeuge.lauf_lesen("egal")


def test_projekt_anbinden(welt):
    _, projekt = welt
    antwort = werkzeuge.projekt_anbinden(str(projekt))
    assert antwort["name"] == "matura-spot"
    assert [s["name"] for s in antwort["skripte"]] == ["Baseline", "Echte Fahrt"]
    assert antwort["skripte"][1]["roboter"] is True


def test_anbinden_ohne_manifest_meldet_es(welt, tmp_path):
    leer = tmp_path / "leer"
    leer.mkdir()
    antwort = werkzeuge.projekt_anbinden(str(leer))
    assert "fehler" in antwort
    assert DATEINAME in antwort["fehler"]


def test_anbindungen_auflisten(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    liste = werkzeuge.anbindungen_auflisten()
    assert [a["name"] for a in liste] == ["matura-spot"]
    assert liste[0]["vorhanden"] is True
    assert liste[0]["panels"] == []


def test_panel_setzen_und_entfernen(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.panel_setzen(
        "matura-spot", "baseline", "kennzahlen", "Baseline",
        [{"name": "success", "wert": "95 %"}],
    )
    assert antwort["ok"] is True
    assert werkzeuge.anbindungen_auflisten()[0]["panels"] == ["baseline"]
    assert werkzeuge.panel_entfernen("matura-spot", "baseline")["ok"] is True
    assert werkzeuge.panel_entfernen("matura-spot", "baseline")["ok"] is False


def test_panel_mit_ungueltigem_inhalt_wird_benannt(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.panel_setzen("matura-spot", "x", "tabelle", "X", {"spalten": ["a"]})
    assert "fehler" in antwort
    assert "zeilen" in antwort["fehler"]


def test_panel_fuer_unbekanntes_projekt(welt):
    antwort = werkzeuge.panel_setzen("gibtsnicht", "x", "text", "X", {"absaetze": []})
    assert "fehler" in antwort


def test_skript_starten(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.skript_starten("matura-spot", "Baseline")
    assert "fehler" not in antwort, antwort
    assert antwort["gestartet"] is True
    assert antwort["skript"].endswith("experiment_baseline.py")
    assert antwort["argumente"] == ["--kurz"]


def test_skript_mit_roboter_wird_verweigert(welt):
    """Erste Lage der Schranke: gar nicht erst starten, mit guter Meldung."""
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.skript_starten("matura-spot", "Echte Fahrt")
    assert "fehler" in antwort
    assert "Fenster" in antwort["fehler"]


def test_unbekanntes_skript_nennt_die_bekannten(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.skript_starten("matura-spot", "gibtsnicht")
    assert "fehler" in antwort
    assert "Baseline" in antwort["fehler"]


def test_fehlende_skriptdatei(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    (projekt / "scripts" / "experiment_baseline.py").unlink()
    assert "fehler" in werkzeuge.skript_starten("matura-spot", "Baseline")


def test_lauf_stoppen_ohne_lauf(welt):
    assert "fehler" in werkzeuge.lauf_stoppen("gibtsnicht")


def test_alle_antworten_sind_json_faehig(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    for antwort in (
        werkzeuge.projekt_anbinden(str(projekt)),
        werkzeuge.anbindungen_auflisten(),
        werkzeuge.panel_setzen("matura-spot", "p", "text", "T", {"absaetze": ["a"]}),
        werkzeuge.lauf_stoppen("gibtsnicht"),
    ):
        json.dumps(antwort)
