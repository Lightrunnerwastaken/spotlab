"""Das Symbol: freigestellt, quadratisch, in allen Fenstern.

Ein Symbol mit eigenem Hintergrund saesse in der Taskleiste in einem grauen
Kasten -- deshalb pruefen die Tests die Transparenz aussen, nicht bloss, dass
eine Datei da ist.
"""

from pathlib import Path

import pytest

from spotlab.gui.symbol import DATEI, symbol

WURZEL = Path(__file__).resolve().parents[1]
ICO = WURZEL / "spotlab.ico"


def test_das_symbol_liegt_im_paket():
    """Neben dem Modul, nicht neben der Wurzel: nur so ueberlebt es ein
    `pip install .` (package-data in pyproject.toml)."""
    assert DATEI.is_file() and DATEI.parent.name == "gui"
    inhalt = (WURZEL / "pyproject.toml").read_text(encoding="utf-8")
    assert '"spotlab.gui" = ["spotlab.png"]' in inhalt


def test_das_symbol_ist_quadratisch_und_freigestellt():
    bild = pytest.importorskip("PIL.Image").open(DATEI)
    assert bild.mode == "RGBA" and bild.width == bild.height >= 256
    breite = bild.width
    ecken = [(2, 2), (breite - 3, 2), (2, breite - 3), (breite - 3, breite - 3)]
    for x, y in ecken:
        assert bild.getpixel((x, y))[3] == 0, f"Ecke ({x}, {y}) ist nicht durchsichtig"
    assert bild.getpixel((breite // 2, breite // 2))[3] == 255, "die Mitte muss decken"
    # Die Kachel fuellt das Bild: am Rand der Mitte ist sie da, in den Ecken nicht.
    assert bild.getpixel((breite // 2, 4))[3] > 200


def test_die_verknuepfung_bekommt_dieselbe_vorlage():
    """`verknuepfung.ps1` traegt `spotlab.ico`; es muss die ueblichen Groessen
    haben, sonst skaliert Windows die grosse herunter und es wird matschig."""
    bild = pytest.importorskip("PIL.Image").open(ICO)
    groessen = {g for g in bild.info["sizes"]}
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= groessen


def test_die_fenster_tragen_das_symbol(qapp):
    from spotlab.gui.app import MainWindow
    from spotlab.gui.theme import DUNKEL
    from spotlab.gui.uebungsfenster import Uebungsfenster

    assert not symbol().isNull()
    fenster = MainWindow()
    assert not fenster.windowIcon().isNull()
    uebung = Uebungsfenster(DUNKEL)
    assert not uebung.windowIcon().isNull()
    uebung.close()


def test_ohne_datei_stuerzt_nichts_ab(qapp, monkeypatch):
    """Ein fehlendes Bild darf die GUI nie anhalten -- sie ist das Fenster mit
    dem NOT-AUS-Knopf."""
    from spotlab.gui import symbol as modul

    monkeypatch.setattr(modul, "DATEI", DATEI.with_name("gibtsnicht.png"))
    assert modul.symbol().isNull()
