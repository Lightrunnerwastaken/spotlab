import json
import shutil

import pytest

from spotlab.anbindung.manifest import DATEINAME, ManifestFehler
from spotlab.anbindung.speicher import (
    anbindungen,
    binde_an,
    finde,
    lauf_verzeichnisse_von,
    loese,
    panelordner,
    wurzel,
)

MANIFEST = """
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation"

[[skript]]
name = "Baseline"
datei = "scripts/experiment_baseline.py"
argumente = ["--episoden", "20"]

[[skript]]
name = "Zweites im selben Ordner"
datei = "scripts/explorer_demo.py"
"""


def _fremdes_projekt(tmp_path, name="matura-spot", inhalt=MANIFEST):
    projekt = tmp_path / name
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "experiment_baseline.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / "scripts" / "explorer_demo.py").write_text("y = 2\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(inhalt, encoding="utf-8")
    return projekt


def _arbeitsordner(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    return arbeit


def test_anbinden_legt_den_ordner_an(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    gebunden = binde_an(arbeit, _fremdes_projekt(tmp_path))
    assert gebunden.ordner == wurzel(arbeit) / "matura-spot"
    assert (gebunden.ordner / "anbindung.json").is_file()
    assert panelordner(gebunden).is_dir()
    assert gebunden.vorhanden is True


def test_anbindung_json_enthaelt_manifest_und_quelle(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    daten = json.loads((gebunden.ordner / "anbindung.json").read_text(encoding="utf-8"))
    assert daten["quelle"] == str(projekt.resolve())
    assert daten["manifest"]["name"] == "matura-spot"
    assert daten["angebunden"]


def test_auflisten_und_finden(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    binde_an(arbeit, _fremdes_projekt(tmp_path, "eins"))
    binde_an(
        arbeit, _fremdes_projekt(tmp_path, "zwei", MANIFEST.replace("matura-spot", "zwei"))
    )
    assert {a.name for a in anbindungen(arbeit)} == {"matura-spot", "zwei"}
    assert finde(arbeit, "zwei").name == "zwei"


def test_finden_ohne_treffer_wirft(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    with pytest.raises(Exception) as fehler:
        finde(arbeit, "gibtsnicht")
    assert "gibtsnicht" in str(fehler.value)


def test_erneutes_anbinden_laesst_panels_stehen(tmp_path):
    """Ein Agent, der nach jeder Manifestaenderung neu anbindet, darf nichts verlieren."""
    arbeit = _arbeitsordner(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    (panelordner(gebunden) / "test.json").write_text("{}", encoding="utf-8")
    wieder = binde_an(arbeit, projekt)
    assert (panelordner(wieder) / "test.json").is_file()


def test_verschwundenes_projekt_bleibt_lesbar(tmp_path):
    """Panels bleiben sichtbar, nur die Skripte gehen aus."""
    arbeit = _arbeitsordner(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    shutil.rmtree(projekt)
    gebunden = finde(arbeit, "matura-spot")
    assert gebunden.vorhanden is False
    assert gebunden.manifest.name == "matura-spot"      # aus der Kopie
    assert str(gebunden.quelle) == str(projekt.resolve())


def test_gefaehrlicher_projektname_bleibt_im_ordner(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    projekt = _fremdes_projekt(tmp_path, "boes", MANIFEST.replace("matura-spot", "../../weg"))
    gebunden = binde_an(arbeit, projekt)
    assert gebunden.ordner.parent == wurzel(arbeit)
    assert ".." not in gebunden.ordner.name


def test_ohne_manifest_wirft(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    leer = tmp_path / "leer"
    leer.mkdir()
    with pytest.raises(ManifestFehler):
        binde_an(arbeit, leer)


def test_loesen_entfernt_den_ordner(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    binde_an(arbeit, _fremdes_projekt(tmp_path))
    assert loese(arbeit, "matura-spot") is True
    assert anbindungen(arbeit) == []
    assert loese(arbeit, "matura-spot") is False


def test_lauf_verzeichnisse_kommen_aus_dem_manifest(tmp_path):
    """Ohne das bliebe „Live-Lauf" bei fremden Projekten leer — der Fehler aus Stufe 3."""
    arbeit = _arbeitsordner(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    assert lauf_verzeichnisse_von(gebunden) == [(projekt / "scripts" / "runs").resolve()]


def test_leerer_arbeitsordner_ergibt_leere_liste(tmp_path):
    assert anbindungen(tmp_path / "gibtsnicht") == []


def test_kaputte_anbindung_json_wird_uebersprungen(tmp_path):
    arbeit = _arbeitsordner(tmp_path)
    binde_an(arbeit, _fremdes_projekt(tmp_path))
    (wurzel(arbeit) / "muell").mkdir()
    (wurzel(arbeit) / "muell" / "anbindung.json").write_text("{", encoding="utf-8")
    assert [a.name for a in anbindungen(arbeit)] == ["matura-spot"]
