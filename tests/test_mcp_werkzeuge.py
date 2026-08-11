import json
from pathlib import Path

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


# ==================================== S4.5 die Werkzeuge muessen alles abfangen
#
# Der Kopf dieser Datei verspricht: „Fehler kommen als {"fehler": ...} zurueck
# statt als Ausnahme". Gefangen wurden aber nur SpotlabError und OSError. Alles
# andere flog durch und riss den Protokollaufruf mit -- der Agent bekam dann
# keine Meldung, sondern gar nichts, und wiederholte denselben Aufruf.


def test_ein_unerwarteter_fehler_kommt_als_meldung_zurueck(welt, monkeypatch):
    def wirf(*a, **kw):
        raise ValueError("etwas ganz anderes")

    monkeypatch.setattr(werkzeuge.speicher, "finde", wirf)
    antwort = werkzeuge.panel_entfernen("matura-spot", "x")
    assert "ValueError" in antwort["fehler"]
    assert "Programmfehler" in antwort["fehler"]


def test_ein_unerwarteter_fehler_bricht_auch_eine_liste_nicht_ab(welt, monkeypatch):
    def wirf(*a, **kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(werkzeuge, "lauf_verzeichnisse", wirf)
    antwort = werkzeuge.laeufe_auflisten()
    assert isinstance(antwort, list) and "RuntimeError" in antwort[0]["fehler"]


def test_eine_unsinnige_anzahl_wird_benannt_statt_zu_werfen(welt):
    antwort = werkzeuge.laeufe_auflisten(anzahl="viele")
    assert "anzahl" in antwort[0]["fehler"]


def test_die_anzahl_ist_nach_oben_begrenzt(welt, monkeypatch):
    """anzahl kam ungeprueft aus dem Protokoll.

    laeufe_auflisten(anzahl=1000000) las jedes gefundene Lauf-Verzeichnis von
    der Platte, waehrend im Fenster jemand auf NOT-AUS wartete. Geprueft wird,
    wie oft wirklich GELESEN wird — nicht, was die Konstante sagt.
    """
    from pathlib import Path

    gelesen = []
    monkeypatch.setattr(
        werkzeuge, "lauf_verzeichnisse", lambda w: [Path(f"lauf{i:04d}") for i in range(500)]
    )
    monkeypatch.setattr(werkzeuge, "read_run", lambda v: gelesen.append(v) or _leer(v))

    antwort = werkzeuge.laeufe_auflisten(anzahl=10**6)
    assert len(gelesen) == werkzeuge.MAX_LAEUFE == 200
    assert len(antwort) == 200


def _leer(verzeichnis):
    from spotlab.record.read import RunSummary

    return RunSummary(
        id=verzeichnis.name, dir=verzeichnis, gestartet=None, dauer_s=0.0,
        backend="dryrun", nickname="", ergebnis="ok", fehler=None, skript=None,
        benutzer=None, ereignisse_n=0, abtastungen_n=0,
    )


def test_mehr_als_drei_gleichzeitige_laeufe_werden_abgelehnt(welt, monkeypatch):
    """Jeder Start ist ein echter Prozess. Ein Agent in einer Schleife hat auf
    einem Schul-Laptop sonst die Lektion beendet."""
    from pathlib import Path

    werkzeuge.projekt_anbinden(str(welt[1]))
    monkeypatch.setattr(
        werkzeuge, "lauf_verzeichnisse", lambda w: [Path(f"lauf{i}") for i in range(3)]
    )
    monkeypatch.setattr(werkzeuge, "ist_aktiv", lambda v: True)
    gestartet = []
    monkeypatch.setattr(werkzeuge, "start_script", lambda *a, **kw: gestartet.append(a))

    antwort = werkzeuge.skript_starten("matura-spot", "Baseline")
    assert "laufen bereits 3" in antwort["fehler"]
    assert gestartet == [], "Trotz Grenze gestartet"


def test_unter_der_grenze_wird_gestartet(welt, monkeypatch):
    from pathlib import Path

    werkzeuge.projekt_anbinden(str(welt[1]))
    monkeypatch.setattr(
        werkzeuge, "lauf_verzeichnisse", lambda w: [Path(f"lauf{i}") for i in range(2)]
    )
    monkeypatch.setattr(werkzeuge, "ist_aktiv", lambda v: True)
    gestartet = []
    monkeypatch.setattr(werkzeuge, "start_script", lambda *a, **kw: gestartet.append(a))

    antwort = werkzeuge.skript_starten("matura-spot", "Baseline")
    assert antwort["gestartet"] is True
    assert len(gestartet) == 1


def test_ein_geschwaetziges_skript_bleibt_nicht_stehen(welt, tmp_path):
    """S4.5 -- der Server liest die Pipe nirgends leer.

    start_script() gibt dem Kind eine Pipe fuer stdout. Wer sie nicht leert,
    laesst das Skript beim vollen Puffer (unter Windows rund 64 KB) fuer immer
    stehen: ohne Fehler, ohne Ende, mitten in einer Bewegung. Der MCP-Server
    warf den Prozess-Handle weg und las nie.

    Das Skript hier schreibt rund 400 KB -- ein Vielfaches des Puffers.
    """
    import time

    arbeit, projekt = welt
    (projekt / "scripts" / "laut.py").write_text(
        "for i in range(8000):\n    print('x' * 50)\n", encoding="utf-8"
    )
    (projekt / DATEINAME).write_text(
        MANIFEST + '\n[[skript]]\nname = "Laut"\ndatei = "scripts/laut.py"\nroboter = false\n',
        encoding="utf-8",
    )
    werkzeuge.projekt_anbinden(str(projekt))

    antwort = werkzeuge.skript_starten("matura-spot", "Laut")
    assert antwort["gestartet"] is True

    ausgabe = Path(antwort["ausgabe"])
    ende = time.monotonic() + 60
    while time.monotonic() < ende:
        if ausgabe.exists() and ausgabe.read_text(encoding="utf-8").count("\n") >= 8000:
            break
        time.sleep(0.1)
    else:
        gelesen = ausgabe.read_text(encoding="utf-8").count("\n") if ausgabe.exists() else 0
        raise AssertionError(
            f"Das Skript kam nicht durch: {gelesen} von 8000 Zeilen. "
            "Der volle Pipe-Puffer haelt es an."
        )
