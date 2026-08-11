import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QTextCursor  # noqa: E402

from spotlab.editor.verbs import Vorschlag  # noqa: E402
from spotlab.gui.editor import completer as modul  # noqa: E402
from spotlab.gui.editor.codeedit import CodeEdit  # noqa: E402
from spotlab.gui.editor.completer import (  # noqa: E402
    Vervollstaendigung,
    eigene_vorschlaege,
    zusammenfuehren,
)
from spotlab.gui.theme import DUNKEL  # noqa: E402


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


def _feld():
    from spotlab.gui.editor.codeedit import CodeEdit
    from spotlab.gui.theme import palette_fuer

    return CodeEdit(palette_fuer(False))


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


# ======================== S1.10 Reiter schliessen waehrend jedi noch laeuft
#
# `feld.deleteLater()` zerstoert das CodeEdit; der Vervollstaendiger haengt
# darunter, der JediWorker-QThread wieder darunter. Laeuft der noch, wird ein
# QThread destruiert, waehrend er arbeitet -- das reisst das GANZE Fenster mit,
# inklusive NOT-AUS-Knopf, und ein laufendes Roboterprogramm im Kindprozess
# bleibt fuehrerlos zurueck.


class _LangsamerWorker:
    """Ein Arbeiter, der noch laeuft, wenn der Reiter geschlossen wird."""

    def __init__(self):
        self.getrennt = False
        self.gewartet = False
        self._laeuft = True

    def isRunning(self):
        return self._laeuft

    @property
    def fertig(self):
        arbeiter = self

        class Signalattrappe:
            def disconnect(self, *a, **kw):
                arbeiter.getrennt = True

        return Signalattrappe()

    def wait(self, ms=None):
        self.gewartet = True
        self._laeuft = False
        return True

    def requestInterruption(self):
        pass


def test_schliesse_trennt_und_wartet_auf_den_arbeiter(qapp):
    feld = _feld()
    v = Vervollstaendigung(feld)
    arbeiter = _LangsamerWorker()
    v._worker = arbeiter
    v.schliesse()
    assert arbeiter.getrennt, "die Antwort haette in ein zerstoertes Widget gezeigt"
    assert arbeiter.gewartet, "der Thread wurde nicht abgewartet"
    assert v._worker is None


def test_schliesse_ohne_arbeiter_ist_harmlos(qapp):
    Vervollstaendigung(_feld()).schliesse()   # darf nicht werfen


def test_eine_verspaetete_antwort_nach_dem_schliessen_wird_ignoriert(qapp):
    """Der Kern: die Antwort darf das zerstoerte Widget nicht mehr anfassen."""
    feld = _feld()
    v = Vervollstaendigung(feld)
    v._nummer = 5
    v.schliesse()
    v._jedi_fertig(5, [("os.path", "os.path")])       # darf nicht werfen
