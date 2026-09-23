"""Das Ausgabefeld des Editors: anklickbare Tracebacks und die Kosten je Zeile."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.theme import DUNKEL  # noqa: E402

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


# ================= Emojis ausserhalb der BMP (Pruefung 23.09.2026, p12)
#
# Python zaehlt ein Emoji wie den Roboter als EIN Zeichen, Qt als ZWEI
# UTF-16-Einheiten. Der laufende Offset rechnete in Python-Zeichen: nach zwoelf
# Zeilen mit zwei Emojis sass jede anklickbare Stelle 24 Positionen zu frueh --
# unterstrichen war das Falsche, und ein Klick auf das Ende des Links ging ins Leere.

ROBOTER, SPIEL = chr(0x1F916), chr(0x1F3AE)


def test_emojis_verschieben_die_anklickbaren_stellen_nicht(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    skript = tmp_path / "fehler.py"
    skript.write_text("x = 1\ny = 2\nraise ValueError\n", encoding="utf-8")
    feld = _ausgabefeld()
    feld.resize(900, 400)
    feld.show()
    feld.setze_wurzel(tmp_path)
    geklickt = []
    feld.stelle_geklickt.connect(lambda pfad, zeile: geklickt.append(zeile))
    for i in range(12):
        feld.haenge_an(f"{ROBOTER} Schritt {i} {SPIEL}")
    feld.haenge_an(f'  File "{skript}", line 3, in <module>')

    assert feld._laenge == feld.document().characterCount() - 1
    von, bis, _pfad, zeile = feld.stellen()[0]
    auswahl = QTextCursor(feld.document())
    auswahl.setPosition(von)
    auswahl.setPosition(bis, QTextCursor.KeepAnchor)
    assert auswahl.selectedText() == f'File "{skript}", line 3'

    ende = QTextCursor(feld.document())
    ende.setPosition(bis - 1)                     # das letzte Zeichen des Links
    QTest.mouseClick(feld.viewport(), Qt.LeftButton, Qt.NoModifier,
                     feld.cursorRect(ende).center())
    assert geklickt == [3]
    feld.close()
