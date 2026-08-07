import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtGui import QTextCursor                        # noqa: E402
from PySide6.QtTest import QTest                             # noqa: E402

from spotlab.editor.syntax import pruefe                     # noqa: E402
from spotlab.gui.editor.codeedit import CodeEdit             # noqa: E402
from spotlab.gui.theme import DUNKEL                         # noqa: E402


def test_tab_schreibt_vier_leerzeichen(qapp):
    feld = CodeEdit(DUNKEL)
    QTest.keyClick(feld, Qt.Key_Tab)
    assert feld.toPlainText() == "    "


def test_enter_behaelt_die_einrueckung(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("    x = 1")
    feld.moveCursor(QTextCursor.End)
    QTest.keyClick(feld, Qt.Key_Return)
    assert feld.toPlainText() == "    x = 1\n    "


def test_enter_nach_doppelpunkt_rueckt_ein(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("def f():")
    feld.moveCursor(QTextCursor.End)
    QTest.keyClick(feld, Qt.Key_Return)
    assert feld.toPlainText() == "def f():\n    "


def test_shift_tab_rueckt_aus(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("        x = 1")
    feld.moveCursor(QTextCursor.End)
    QTest.keyClick(feld, Qt.Key_Backtab)
    assert feld.toPlainText() == "    x = 1"


def test_ctrl_s_meldet_speicherwunsch(qapp):
    feld = CodeEdit(DUNKEL)
    gerufen = []
    feld.speichern_gewuenscht.connect(lambda: gerufen.append(True))
    QTest.keyClick(feld, Qt.Key_S, Qt.ControlModifier)
    assert gerufen == [True]
    assert feld.toPlainText() == ""      # das S darf nicht im Text landen


def test_ctrl_space_erzwingt_vorschlaege(qapp):
    feld = CodeEdit(DUNKEL)
    erzwungen = []
    feld.vervollstaendigung_gewuenscht.connect(erzwungen.append)
    QTest.keyClick(feld, Qt.Key_Space, Qt.ControlModifier)
    assert erzwungen == [True]


def test_fehler_wird_unterkringelt_und_als_hinweis_gezeigt(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("x = 1\n  y = 2\n")
    feld.zeige_fehler(pruefe(feld.toPlainText()))
    assert "eingerückt" in feld.toolTip()
    assert len(feld.extraSelections()) >= 2      # aktuelle Zeile + Kringel


def test_fehler_zuruecknehmen_leert_den_hinweis(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("x = 1\n")
    feld.zeige_fehler(pruefe("  kaputt"))
    feld.zeige_fehler(None)
    assert feld.toolTip() == ""


def test_zeilenleiste_waechst_mit_der_zeilenzahl(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("x = 1\n")
    schmal = feld.zeilenleiste_breite()
    feld.setPlainText("\n".join(f"x = {i}" for i in range(1200)))
    assert feld.zeilenleiste_breite() > schmal


def test_ruhe_kommt_erst_nach_der_pause(qapp):
    feld = CodeEdit(DUNKEL)
    ruhig = []
    feld.ruhe.connect(lambda: ruhig.append(True))
    feld.setPlainText("x = 1")
    assert ruhig == []                     # noch nicht
    QTest.qWait(400)
    assert ruhig == [True]                 # genau einmal


def test_alle_ersetzen_in_der_offenen_datei(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("a = 1\nb = a\nc = a\n")
    feld.suchleiste_umschalten()
    feld.suchleiste.suchfeld.setText("a")
    feld.suchleiste.ersatzfeld.setText("z")
    assert feld.suchleiste.ersetze_alle() == 3
    assert feld.toPlainText() == "z = 1\nb = z\nc = z\n"
