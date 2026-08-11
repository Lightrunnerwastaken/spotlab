"""Das Ausgabefeld des Editors: anklickbare Tracebacks und die Kosten je Zeile."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.editor.view import Ausgabefeld                # noqa: E402
from spotlab.gui.theme import DUNKEL                           # noqa: E402


# ======================= S1.12 Ausgabeflut friert die Ereignisschleife ein
#
# `haenge_an` rief bei JEDER Zeile `toPlainText()` -- das kopiert den ganzen
# Puffer. Gemessen: 0.070 ms/Zeile bei 500 Zeilen, 0.402 bei 4000. Auf 50 000
# Zeilen hochgerechnet sind das Minuten, in denen die Qt-Ereignisschleife
# besetzt ist -- und ein Klick auf NOT-AUS steht in derselben Warteschlange.


def _ausgabefeld():
    from spotlab.gui.editor.view import Ausgabefeld

    return Ausgabefeld(DUNKEL)


def test_der_laufende_offset_stimmt_mit_dem_dokument_ueberein(qapp):
    """Die Rechnung ersetzt toPlainText() -- sie muss dasselbe ergeben."""
    feld = _ausgabefeld()
    for i in range(50):
        feld.haenge_an(f"Zeile {i} mit Umlauten: äöü")
    assert feld._laenge == len(feld.toPlainText())


def test_der_offset_ueberlebt_das_leeren(qapp):
    feld = _ausgabefeld()
    feld.haenge_an("erst")
    feld.leere()
    assert feld._laenge == 0
    feld.haenge_an("danach")
    assert feld._laenge == len(feld.toPlainText())


def test_traceback_stellen_zeigen_weiterhin_richtig(qapp, tmp_path):
    """Der Grund, warum der Offset stimmen MUSS: die anklickbaren Stellen
    haengen an Zeichenpositionen im Dokument. Ein Fehler dort schickt den
    Schueler in die falsche Datei."""
    skript = tmp_path / "hallo_spot.py"
    skript.write_text("x = 1\n", encoding="utf-8")
    feld = _ausgabefeld()
    feld.setze_wurzel(tmp_path)
    feld.haenge_an("Vorlauf ohne Treffer")
    feld.haenge_an(f'  File "{skript}", line 3, in <module>')
    assert feld.stellen(), "keine anklickbare Stelle gefunden"
    von, bis, pfad, zeile = feld.stellen()[-1]
    ausschnitt = feld.toPlainText()[von:bis]
    assert ausschnitt.startswith('File "'), ausschnitt
    assert str(skript) in ausschnitt
    assert pfad == skript.resolve() and zeile == 3
