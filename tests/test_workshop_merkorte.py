"""Merkorte: benannte Punkte im Rahmen „vision“ (Agenten am Spot, Teil 2)."""

import math

import pytest

from spotlab.workshop import merkorte as mo


def test_setzen_holen_verschieben_loeschen():
    m = mo.Merkorte()
    assert m.setze("  Tür ", 1.0, 2.0) == "Tür"
    assert m.hole("Tür") == (1.0, 2.0)
    m.setze("Tür", 3.0, 4.0)
    assert m.namen() == ["Tür"] and m.hole("Tür") == (3.0, 4.0), "gleicher Name heisst verschieben"
    assert m.als_daten() == [{"name": "Tür", "x": 3.0, "y": 4.0}]
    assert m.loesche("Tür") and not m.loesche("Tür")
    assert m.hole("Tür") is None


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_ein_name_hat_ein_bis_vierzig_zeichen(name):
    with pytest.raises(ValueError):
        mo.Merkorte().setze(name, 0.0, 0.0)


def test_ein_ort_braucht_endliche_zahlen():
    with pytest.raises(ValueError):
        mo.Merkorte().setze("Tür", math.nan, 0.0)


def test_mit_datei_bleiben_sie_ueber_den_lauf_hinaus(tmp_path):
    pfad = mo.pfad_fuer(tmp_path, "durchgang")
    assert pfad == tmp_path / "raeume" / "durchgang.merkorte.json"
    m = mo.Merkorte(pfad)
    m.setze("start", 1.0, 2.0)
    assert mo.Merkorte(pfad).hole("start") == (1.0, 2.0)
    m.loesche("start")
    assert mo.Merkorte(pfad).namen() == []


def test_eine_kaputte_datei_ist_leer(tmp_path):
    pfad = tmp_path / "x.merkorte.json"
    pfad.write_text("{halb", encoding="utf-8")
    assert mo.Merkorte(pfad).namen() == []
