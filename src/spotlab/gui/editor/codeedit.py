"""Das Textfeld: Zeilennummern, Einrueckung, Fehlerkringel, ein Zeitgeber.

Der Zeitgeber ist der einzige Taktgeber im Editor: 150 ms nach dem letzten
Tastendruck meldet er `ruhe`. Daran haengen Hervorhebung UND Syntaxpruefung —
ein Zeitgeber, zwei Verbraucher.
"""

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from spotlab.editor.indent import EINRUECKUNG, ausruecken, naechste_einrueckung

RUHE_MS = 150


class Zeilenleiste(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.zeilenleiste_breite(), 0)

    def paintEvent(self, ereignis):
        self._editor.zeichne_zeilenleiste(ereignis)


class CodeEdit(QPlainTextEdit):
    ruhe = Signal()
    speichern_gewuenscht = Signal()
    vervollstaendigung_gewuenscht = Signal(bool)   # True = erzwungen (Ctrl+Space)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._fehlerzeile = None
        self.suchleiste = None
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

        self.leiste = Zeilenleiste(self)
        self.blockCountChanged.connect(lambda _: self._setze_rand())
        self.updateRequest.connect(self._leiste_scrollen)
        self.cursorPositionChanged.connect(self._markiere)

        self._zeitgeber = QTimer(self)
        self._zeitgeber.setSingleShot(True)
        self._zeitgeber.setInterval(RUHE_MS)
        self._zeitgeber.timeout.connect(self.ruhe.emit)
        self.textChanged.connect(self._zeitgeber.start)

        self._setze_rand()
        self._markiere()

    # ------------------------------------------------------------ Zeilenleiste

    def zeilenleiste_breite(self):
        stellen = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * stellen

    def _setze_rand(self):
        self.setViewportMargins(self.zeilenleiste_breite(), 0, 0, 0)

    def _leiste_scrollen(self, rechteck, dy):
        if dy:
            self.leiste.scroll(0, dy)
        else:
            self.leiste.update(0, rechteck.y(), self.leiste.width(), rechteck.height())
        if rechteck.contains(self.viewport().rect()):
            self._setze_rand()

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        innen = self.contentsRect()
        self.leiste.setGeometry(
            QRect(innen.left(), innen.top(), self.zeilenleiste_breite(), innen.height())
        )

    def zeichne_zeilenleiste(self, ereignis):
        maler = QPainter(self.leiste)
        maler.fillRect(ereignis.rect(), QColor(self._palette.hintergrund))
        block = self.firstVisibleBlock()
        oben = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        hoehe = self.fontMetrics().height()
        while block.isValid() and oben <= ereignis.rect().bottom():
            unten = oben + self.blockBoundingRect(block).height()
            if block.isVisible() and unten >= ereignis.rect().top():
                nummer = block.blockNumber() + 1
                ist_fehler = nummer == self._fehlerzeile
                maler.setPen(
                    QColor(self._palette.gefahr if ist_fehler else self._palette.gedaempft)
                )
                maler.drawText(
                    0, int(oben), self.leiste.width() - 6, hoehe, Qt.AlignRight, str(nummer)
                )
            oben = unten
            block = block.next()

    # ------------------------------------------------------------ Markierungen

    def zeige_fehler(self, stelle):
        """`stelle` ist eine editor.syntax.Fehlerstelle oder None."""
        self._fehlerzeile = stelle.zeile if stelle else None
        self.setToolTip(stelle.text if stelle else "")
        self._markiere()
        self.leiste.update()

    def _markiere(self):
        auswahlen = []
        aktuell = QTextEdit.ExtraSelection()
        aktuell.format.setBackground(QColor(self._palette.flaeche))
        aktuell.format.setProperty(QTextFormat.FullWidthSelection, True)
        aktuell.cursor = self.textCursor()
        aktuell.cursor.clearSelection()
        auswahlen.append(aktuell)

        if self._fehlerzeile is not None:
            block = self.document().findBlockByNumber(self._fehlerzeile - 1)
            if block.isValid():
                kringel = QTextEdit.ExtraSelection()
                kringel.format.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
                kringel.format.setUnderlineColor(QColor(self._palette.gefahr))
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                kringel.cursor = cursor
                auswahlen.append(kringel)

        self.setExtraSelections(auswahlen)

    # ------------------------------------------------------------ Tasten

    def keyPressEvent(self, ereignis):
        if ereignis.matches(QKeySequence.Save):
            self.speichern_gewuenscht.emit()
            return
        if ereignis.matches(QKeySequence.Find):
            self.suchleiste_umschalten()
            return
        if ereignis.key() == Qt.Key_Space and ereignis.modifiers() & Qt.ControlModifier:
            self.vervollstaendigung_gewuenscht.emit(True)
            return
        if ereignis.key() == Qt.Key_Tab and not ereignis.modifiers():
            self.insertPlainText(EINRUECKUNG)
            return
        if ereignis.key() == Qt.Key_Backtab:
            self._ausruecken()
            return
        if ereignis.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._neue_zeile()
            return
        super().keyPressEvent(ereignis)
        zeichen = ereignis.text()
        if zeichen and (zeichen.isalnum() or zeichen in "._"):
            self.vervollstaendigung_gewuenscht.emit(False)

    def _neue_zeile(self):
        cursor = self.textCursor()
        vor_dem_cursor = cursor.block().text()[: cursor.positionInBlock()]
        cursor.insertText("\n" + naechste_einrueckung(vor_dem_cursor))
        self.setTextCursor(cursor)

    def _ausruecken(self):
        block = self.textCursor().block()
        weg = ausruecken(block.text())
        if weg <= 0:
            return
        loeschen = QTextCursor(block)
        loeschen.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, weg)
        loeschen.removeSelectedText()

    # ------------------------------------------------------------ Suchen

    def suchleiste_umschalten(self):
        if self.suchleiste is None:
            self.suchleiste = Suchleiste(self)
        self.suchleiste.setVisible(not self.suchleiste.isVisible())
        if self.suchleiste.isVisible():
            self.suchleiste.suchfeld.setFocus()


class Suchleiste(QWidget):
    """Suchen und Ersetzen in der offenen Datei — mehr braucht es hier nicht.

    Projektweite Suche ist Nicht-Ziel; wer sie braucht, hat VS Code.
    """

    def __init__(self, editor):
        super().__init__(editor.parentWidget() or editor)
        self._editor = editor
        self.suchfeld = QLineEdit()
        self.suchfeld.setPlaceholderText("Suchen")
        self.ersatzfeld = QLineEdit()
        self.ersatzfeld.setPlaceholderText("Ersetzen durch")
        self.gross_klein = QCheckBox("Gross-/Kleinschreibung")
        zurueck = QPushButton("Zurück")
        weiter = QPushButton("Weiter")
        ersetzen = QPushButton("Ersetzen")
        alle = QPushButton("Alle ersetzen")
        schliessen = QPushButton("Schliessen")

        zurueck.clicked.connect(lambda: self.suche(rueckwaerts=True))
        weiter.clicked.connect(lambda: self.suche(rueckwaerts=False))
        ersetzen.clicked.connect(self.ersetze)
        alle.clicked.connect(self.ersetze_alle)
        schliessen.clicked.connect(lambda: self.setVisible(False))
        self.suchfeld.returnPressed.connect(lambda: self.suche(rueckwaerts=False))

        anordnung = QHBoxLayout(self)
        anordnung.setContentsMargins(0, 0, 0, 0)
        for widget in (self.suchfeld, self.ersatzfeld, self.gross_klein,
                       zurueck, weiter, ersetzen, alle, schliessen):
            anordnung.addWidget(widget)

    def _flags(self, rueckwaerts):
        flags = QTextDocument.FindFlags()
        if rueckwaerts:
            flags |= QTextDocument.FindBackward
        if self.gross_klein.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def suche(self, rueckwaerts=False):
        text = self.suchfeld.text()
        if not text:
            return False
        if self._editor.find(text, self._flags(rueckwaerts)):
            return True
        # Vom Anfang (bzw. Ende) noch einmal — sonst endet die Suche stumm.
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End if rueckwaerts else QTextCursor.Start)
        self._editor.setTextCursor(cursor)
        return self._editor.find(text, self._flags(rueckwaerts))

    def ersetze(self):
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == self.suchfeld.text():
            cursor.insertText(self.ersatzfeld.text())
        return self.suche(rueckwaerts=False)

    def ersetze_alle(self):
        suchen, ersetzen = self.suchfeld.text(), self.ersatzfeld.text()
        if not suchen:
            return 0
        text = self._editor.toPlainText()
        anzahl = text.count(suchen)
        if anzahl:
            cursor = self._editor.textCursor()
            cursor.beginEditBlock()
            cursor.select(QTextCursor.Document)
            cursor.insertText(text.replace(suchen, ersetzen))
            cursor.endEditBlock()
        return anzahl
