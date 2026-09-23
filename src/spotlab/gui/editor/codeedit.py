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

# Solange die Vorschlagsliste offen ist, gehoeren diese Tasten ihr.
LISTENTASTEN = (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backtab)

ABSATZ = "\u2029"       # so trennt QTextDocument seine Bloecke


def rohtext(dokument):
    """Der Text, wie er in der Datei steht -- NICHT `toPlainText()`.

    `toPlainText()` macht aus U+00A0 (geschütztes Leerzeichen) ein Leerzeichen
    und aus U+2028 (Zeilentrenner) einen Zeilenumbruch. Beides steht in Code
    aus dem Netz oder aus Word; ein U+2028 in einer Zeichenkette wurde so beim
    blossen „Starten" zum Umbruch, und die Datei kompilierte danach nicht mehr
    (Prüfung 23.09.2026). Der Rohtext trägt beide unverändert; nur die
    Blockgrenzen sind U+2029 und werden hier zu dem, was sie in der Datei sind.
    """
    return dokument.toRawText().replace(ABSATZ, "\n")


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
        self._vorschlagsliste = None       # das Popup der Vervollstaendigung
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

    def rohtext(self):
        """Der Inhalt fuer Datei, Syntaxpruefung und jedi (siehe `rohtext`)."""
        return rohtext(self.document())

    def setze_vorschlagsliste(self, liste):
        """Das Popup der Vervollstaendigung: solange es offen ist, gehoeren ihm
        Enter, Tab und Shift+Tab (siehe `keyPressEvent`)."""
        self._vorschlagsliste = liste

    def _liste_offen(self):
        liste = self._vorschlagsliste
        try:
            return liste is not None and liste.isVisible()
        except RuntimeError:            # schon abgeraeumt
            return False

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
        self._platziere_suchleiste()

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
        if ereignis.key() in LISTENTASTEN and self._liste_offen():
            # Die offene Vorschlagsliste entscheidet: der QCompleter schickt die
            # Taste zuerst hierher und uebernimmt den Vorschlag nur, wenn das
            # Feld sie NICHT annimmt. Vorher fuegte Enter einen Umbruch und Tab
            # vier Leerzeichen ein, und der Vorschlag kam nie an (p02/p02b).
            ereignis.ignore()
            return
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
            self._einruecken()
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

    def _markierte_bloecke(self):
        """Erste und letzte Blocknummer, die die Markierung beruehrt.

        Endet sie am Anfang einer Zeile (ganze Zeilen mit Shift+Pfeil markiert),
        gehoert diese Zeile nicht dazu -- so machen es alle Editoren.
        """
        cursor = self.textCursor()
        dokument = self.document()
        erster = dokument.findBlock(cursor.selectionStart())
        letzter = dokument.findBlock(cursor.selectionEnd())
        if (letzter.blockNumber() > erster.blockNumber()
                and cursor.selectionEnd() == letzter.position()):
            letzter = letzter.previous()
        return erster.blockNumber(), letzter.blockNumber()

    def _je_block(self, arbeit):
        """`arbeit(block, bearbeiter)` fuer jeden markierten Block (ohne
        Markierung: die Zeile des Cursors) -- in EINEM Bearbeitungsschritt, damit
        ein Strg+Z alles zuruecknimmt."""
        if self.textCursor().hasSelection():
            erster, letzter = self._markierte_bloecke()
        else:
            erster = letzter = self.textCursor().blockNumber()
        bearbeiter = QTextCursor(self.document())
        bearbeiter.beginEditBlock()
        try:
            for nummer in range(erster, letzter + 1):
                block = self.document().findBlockByNumber(nummer)
                arbeit(block, bearbeiter, erster == letzter)
        finally:
            bearbeiter.endEditBlock()

    def _einruecken(self):
        """Tab: ohne Markierung vier Leerzeichen am Cursor, MIT Markierung eine
        Ebene fuer jede markierte Zeile.

        Bis zum 23.09.2026 ersetzte Tab die Markierung durch vier Leerzeichen --
        wer drei Zeilen einruecken wollte, hatte sie geloescht (p01).
        """
        if not self.textCursor().hasSelection():
            self.insertPlainText(EINRUECKUNG)
            return

        def eine_ebene(block, bearbeiter, nur_eine_zeile):
            if not block.text() and not nur_eine_zeile:
                return              # leere Zeilen bekommen keinen Leerraum am Ende
            bearbeiter.setPosition(block.position())
            bearbeiter.insertText(EINRUECKUNG)

        self._je_block(eine_ebene)

    def _ausruecken(self):
        """Shift+Tab: eine Ebene weniger -- fuer JEDE markierte Zeile, nicht nur
        fuer die mit dem Cursor."""

        def eine_ebene(block, bearbeiter, _nur_eine_zeile):
            weg = ausruecken(block.text())
            if weg <= 0:
                return
            # Leerraum ist ASCII: `weg` Zeichen sind `weg` Positionen.
            bearbeiter.setPosition(block.position())
            bearbeiter.setPosition(block.position() + weg, QTextCursor.KeepAnchor)
            bearbeiter.removeSelectedText()

        self._je_block(eine_ebene)

    # ------------------------------------------------------------ Suchen

    def suchleiste_umschalten(self):
        if self.suchleiste is None:
            self.suchleiste = Suchleiste(self)
        # isHidden() statt isVisible(): isVisible() ist falsch, solange ein
        # Vorfahre nicht gezeigt wird — das Umschalten haette dann nie wieder
        # zugemacht.
        zeigen = self.suchleiste.isHidden()
        self.suchleiste.setVisible(zeigen)
        self._platziere_suchleiste()
        if zeigen:
            self.suchleiste.suchfeld.setFocus()

    def _platziere_suchleiste(self):
        """Oben rechts ueber dem Text, wie in VS Code.

        Die Leiste ist ein Kind des Textfelds und liegt in keinem Layout —
        ohne diese Platzierung saesse sie in der linken oberen Ecke ueber den
        Zeilennummern.
        """
        if self.suchleiste is None or self.suchleiste.isHidden():
            return
        sicht = self.viewport().geometry()
        breite = min(self.suchleiste.sizeHint().width(), sicht.width())
        hoehe = self.suchleiste.sizeHint().height()
        self.suchleiste.setGeometry(sicht.right() - breite + 1, sicht.top(), breite, hoehe)
        self.suchleiste.raise_()


class Suchleiste(QWidget):
    """Suchen und Ersetzen in der offenen Datei — mehr braucht es hier nicht.

    Projektweite Suche ist Nicht-Ziel; wer sie braucht, hat VS Code.
    """

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
        self.setAutoFillBackground(True)
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

        # Ausdruecklich verstecken: ein frisch angelegtes Kindwidget gilt in Qt
        # bereits als sichtbar (isHidden() == False), auch wenn der Vorfahre
        # noch nicht gezeigt wurde. Ohne das haette der erste Ctrl+F die Leiste
        # zugemacht statt aufgemacht.
        self.hide()

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

    # Suchen, Ersetzen und Alle ersetzen fragen ALLE `document().find()` mit
    # denselben Flags. Bis zum 23.09.2026 fand die Suche ohne Haekchen Spot, spot
    # und SPOT, „Ersetzen" verglich die Markierung aber exakt und tat nichts, und
    # „Alle ersetzen" zaehlte mit str.count nur die genaue Schreibweise (p01).

    def _markierung_ist_treffer(self):
        """Ist die Markierung genau ein Treffer -- nach den Regeln der Suche?"""
        cursor = self._editor.textCursor()
        text = self.suchfeld.text()
        if not text or not cursor.hasSelection():
            return False
        treffer = self._editor.document().find(text, cursor.selectionStart(),
                                               self._flags(False))
        return (not treffer.isNull()
                and treffer.selectionStart() == cursor.selectionStart()
                and treffer.selectionEnd() == cursor.selectionEnd())

    def ersetze(self):
        if self._markierung_ist_treffer():
            self._editor.textCursor().insertText(self.ersatzfeld.text())
        return self.suche(rueckwaerts=False)

    def ersetze_alle(self):
        """Ersetzt jeden Treffer der Suche. EIN Bearbeitungsschritt: ein Strg+Z
        nimmt alle zurueck. Rueckgabe: die Zahl der Ersetzungen."""
        suchen, ersetzen = self.suchfeld.text(), self.ersatzfeld.text()
        if not suchen:
            return 0
        dokument = self._editor.document()
        flags = self._flags(False)
        bearbeiter = QTextCursor(dokument)
        anzahl = 0
        bearbeiter.beginEditBlock()
        try:
            while True:
                # Weiter HINTER der letzten Ersetzung: ein Ersatz, der den
                # Suchtext enthaelt („a" -> „aa"), wird nie erneut getroffen.
                treffer = dokument.find(suchen, bearbeiter, flags)
                if treffer.isNull():
                    break
                bearbeiter.setPosition(treffer.selectionStart())
                bearbeiter.setPosition(treffer.selectionEnd(), QTextCursor.KeepAnchor)
                bearbeiter.insertText(ersetzen)
                anzahl += 1
        finally:
            bearbeiter.endEditBlock()
        return anzahl
