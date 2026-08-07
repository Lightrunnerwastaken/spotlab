import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QTextCursor                                 # noqa: E402

from spotlab.editor.verbs import Vorschlag                            # noqa: E402
from spotlab.gui.editor import completer as modul                     # noqa: E402
from spotlab.gui.editor.codeedit import CodeEdit                      # noqa: E402
from spotlab.gui.editor.completer import (                            # noqa: E402
    Vervollstaendigung,
    eigene_vorschlaege,
    zusammenfuehren,
)
from spotlab.gui.theme import DUNKEL                                  # noqa: E402


def test_eigener_eintrag_gewinnt_bei_namensgleichheit():
    # Nur der eigene traegt Signatur und deutsche Erklaerung.
    eigen = Vorschlag("move", "move(forward=0.0)", "Geht eine feste Strecke.")
    fremd = Vorschlag("move", "move", "Funktion")
    assert zusammenfuehren([eigen], [fremd]) == [eigen]


def test_fremde_ergaenzen_was_wir_nicht_kennen():
    eigen = Vorschlag("move", "move()", "Geht.")
    fremd = Vorschlag("sqrt", "sqrt", "Funktion")
    assert zusammenfuehren([eigen], [fremd]) == [eigen, fremd]


def test_reihenfolge_ist_stabil():
    eigene = [Vorschlag(n, n, "") for n in ("a", "b")]
    fremde = [Vorschlag(n, n, "") for n in ("c", "a", "d")]
    assert [v.name for v in zusammenfuehren(eigene, fremde)] == ["a", "b", "c", "d"]


def test_eigene_vorschlaege_nach_spot_punkt():
    namen = {v.name for v in eigene_vorschlaege("    spot.")}
    assert "navigate_to" in namen


def test_kein_vorschlag_fuer_fremde_namen():
    assert eigene_vorschlaege("roboter.") == []


def _hilfe_mit(feld, text):
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText(text)
    feld.moveCursor(QTextCursor.End)
    return hilfe


def test_ohne_jedi_kommen_trotzdem_vorschlaege(qapp, monkeypatch):
    """Der Rueckfall ist die Bedingung dafuer, dass die Suite ohne jedi gruen ist."""
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    assert hilfe.modell.rowCount() > 0


def test_veraltete_jedi_antwort_wird_verworfen(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    vorher = hilfe.modell.rowCount()
    hilfe._jedi_fertig(-1, [Vorschlag("veraltet", "veraltet", "")])
    assert hilfe.modell.rowCount() == vorher


def test_aktuelle_jedi_antwort_wird_ergaenzt(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    vorher = hilfe.modell.rowCount()
    hilfe._jedi_fertig(hilfe._nummer, [Vorschlag("etwas_neues", "etwas_neues", "Wert")])
    assert hilfe.modell.rowCount() == vorher + 1


def test_einfuegen_schreibt_den_blossen_namen(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.mo")
    hilfe.anfordern(erzwungen=True)
    hilfe._einfuegen("move")
    assert feld.toPlainText() == "spot.move"


def test_einfuegen_versteht_auch_den_anzeigetext(qapp, monkeypatch):
    # Absicherung gegen die Qt-Version: je nach Aufbau liefert
    # QCompleter.activated den completionRole ODER den Anzeigetext.
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    index = hilfe.modell.index(0, 0)
    anzeige = hilfe.modell.data(index)
    name = hilfe.modell.data(index, modul.NAME_ROLLE)
    hilfe._einfuegen(anzeige)
    assert feld.toPlainText() == f"spot.{name}"


def test_anzeigetext_enthaelt_signatur_und_deutsche_hilfe(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    texte = [
        hilfe.modell.data(hilfe.modell.index(z, 0))
        for z in range(hilfe.modell.rowCount())
    ]
    passend = [t for t in texte if t.startswith("move(")]
    assert passend and "Strecke" in passend[0]


def test_mit_jedi_werden_fremde_namen_ergaenzt(qapp):
    """Was jedi abdeckt und wir nicht: math., np., lokale Variablen."""
    pytest.importorskip("jedi")
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    fremde = hilfe.jedi_lesen(feld.toPlainText(), 2, 5, None)
    assert "sqrt" in {v.name for v in fremde}
