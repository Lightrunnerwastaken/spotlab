import shutil

import pytest

from spotlab.anbindung.manifest import DATEINAME
from spotlab.anbindung.speicher import binde_an
from spotlab.laufsuche import finde_lauf, lauf_verzeichnisse

MANIFEST = '[projekt]\nname = "fremd"\n\n[[skript]]\nname = "s"\ndatei = "scripts/s.py"\n'


def _werkstatt(tmp_path):
    arbeit = tmp_path / "werkstatt"
    (arbeit / "demo" / "runs" / "20260807T101010Z").mkdir(parents=True)
    return arbeit


def _fremdes_projekt(tmp_path):
    projekt = tmp_path / "fremd"
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")
    return projekt


def test_findet_laeufe_der_werkstatt(tmp_path):
    assert [p.name for p in lauf_verzeichnisse(_werkstatt(tmp_path))] == [
        "20260807T101010Z"
    ]


def test_findet_laeufe_eines_angebundenen_projekts(tmp_path):
    """Ohne das bliebe „Live-Lauf" bei fremden Projekten leer — der Fehler aus Stufe 3.

    Laeufe landen unter <skriptordner>/runs/, also AUSSERHALB des Arbeitsordners.
    """
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    (projekt / "scripts" / "runs" / "20260807T120000Z").mkdir(parents=True)

    assert {p.name for p in lauf_verzeichnisse(arbeit)} == {
        "20260807T101010Z",
        "20260807T120000Z",
    }


def test_kein_doppelter_eintrag(tmp_path):
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    binde_an(arbeit, projekt)
    (projekt / "scripts" / "runs" / "20260807T120000Z").mkdir(parents=True)
    pfade = lauf_verzeichnisse(arbeit)
    assert len(pfade) == len({str(p) for p in pfade})


def test_fehlendes_fremdprojekt_stoert_nicht(tmp_path):
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    shutil.rmtree(projekt)
    assert [p.name for p in lauf_verzeichnisse(arbeit)] == ["20260807T101010Z"]


def test_finde_lauf_ueber_beide_orte(tmp_path):
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    (projekt / "scripts" / "runs" / "20260807T120000Z").mkdir(parents=True)

    assert finde_lauf(arbeit, "20260807T101010Z").name == "20260807T101010Z"
    assert finde_lauf(arbeit, "20260807T120000Z").name == "20260807T120000Z"
    assert finde_lauf(arbeit, "gibtsnicht") is None


def test_laufsuche_ist_qt_frei():
    import pathlib
    import re

    import spotlab.laufsuche as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    assert re.search(r"^\s*(from|import)\s+PySide6", quelle, re.M) is None


def test_watcher_exportiert_dieselbe_funktion():
    # Der einzige Test in dieser Datei, der Qt braucht -- und der einzige im
    # ganzen Projekt, der ohne das Extra [gui] mit ModuleNotFoundError statt
    # mit einem Ueberspringen endete. Aufgefallen ist das erst bei einer
    # Installation, die NUR [dev] hatte; lokal ist PySide6 immer da.
    pytest.importorskip("PySide6.QtCore")
    from spotlab.gui.watcher import lauf_verzeichnisse as aus_watcher

    assert aus_watcher is lauf_verzeichnisse
