import pytest

from spotlab.pfade import sicherer_name


@pytest.mark.parametrize(
    "roh, erwartet",
    [
        ("turnhalle", "turnhalle"),
        ("Turnhalle 2", "Turnhalle-2"),
        ("matura-spot", "matura-spot"),
        ("a/b", "a-b"),
        ("../../etc", "etc"),
        ("  rand  ", "rand"),
        ("...", "ordner"),
        ("", "ordner"),
    ],
)
def test_sicherer_name(roh, erwartet):
    assert sicherer_name(roh) == erwartet


def test_ersatz_ist_einstellbar():
    assert sicherer_name("", ersatz="karte") == "karte"


def test_maps_store_exportiert_dieselbe_funktion():
    """Der bestehende Import-Pfad muss weiter tragen."""
    from spotlab.maps.store import sicherer_name as aus_maps

    assert aus_maps is sicherer_name


def test_pfade_ist_frei_von_fremden_importen():
    """Auf IMPORTE geprüft, nicht auf Vorkommen — der Docstring nennt bosdyn."""
    import pathlib
    import re

    import spotlab.pfade as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    muster = re.compile(
        r"^\s*(from|import)\s+(bosdyn|PySide6|spotlab\.maps|spotlab\.api)", re.M
    )
    assert muster.search(quelle) is None
