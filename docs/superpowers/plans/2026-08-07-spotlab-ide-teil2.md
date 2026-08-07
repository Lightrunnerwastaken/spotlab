# spotlab IDE Implementierungsplan — Teil 2 (Aufgaben 7–14)

> **Für agentische Arbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`. Schritte sind Checkboxen (`- [ ]`).

**Fortsetzung von** `docs/superpowers/plans/2026-08-07-spotlab-ide.md`.
**Die „Globalen Vorgaben" aus Teil 1 gelten unverändert für jede Aufgabe hier.**

**Voraussetzungen aus Teil 1** (Aufgaben 1–6 abgeschlossen):

| Modul | Was daraus benutzt wird |
|---|---|
| `spotlab.editor.syntax` | `pruefe(quelltext) -> Fehlerstelle \| None`, `Fehlerstelle(zeile, spalte, text)` |
| `spotlab.editor.traceback` | `finde_stellen(text, wurzel) -> list[Stelle]`, `Stelle(pfad, zeile, von, bis)` |
| `spotlab.editor.verbs` | `Vorschlag(name, signatur, hilfe)`, `spot_verben()`, `spotlab_verben()`, `praefix(text)`, `teilwort(text)` |
| `spotlab.editor.indent` | `EINRUECKUNG`, `einrueckung_von`, `naechste_einrueckung`, `ausruecken` |
| `spotlab.gui.theme` | `Palette` mit `schluesselwort`, `zeichenkette`, `kommentar`, `zahl`, `funktion` |

**Vorhandenes, das wiederverwendet und nicht nachgebaut wird:**

| Baustein | Wo | Wofür |
|---|---|---|
| `start_script(pfad, dryrun=False)` | `spotlab.workshop.launcher` | der **einzige** Startweg |
| `OutputReader(prozess)` | `spotlab.gui.workers` | der **einzige** Leser der Ausgabe-Pipe |
| `LiveView.stoppe()` | `spotlab.gui.views.live` | der **einzige** freundliche Stopp |
| `projekte_in(ordner)` | `spotlab.gui.views.projects` | Projekterkennung |
| `SpotlabError` | `spotlab.errors` | Meldungen an den Nutzer |

---

## Aufgabe 7: `gui/editor/highlighter.py` — Syntaxhervorhebung

**Dateien:**
- Anlegen: `src/spotlab/gui/editor/__init__.py`
- Anlegen: `src/spotlab/gui/editor/highlighter.py`
- Ändern: `pyproject.toml` (`pygments` ins Extra `gui`)
- Test: `tests/test_gui_highlighter.py`

**Schnittstellen:**
- Verbraucht: `Palette` aus `spotlab.gui.theme`.
- Liefert: `spannen(text: str, palette: Palette, lexer=None) -> dict[int, list[tuple[int, int, QTextCharFormat]]]`
  (Blocknummer → Spannen) und `Hervorheber(dokument, palette)` mit `neu_lexen()`.
  Aufgabe 8 hängt `neu_lexen` an das `ruhe`-Signal von `CodeEdit`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_gui_highlighter.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("pygments")

from spotlab.gui.editor.highlighter import spannen          # noqa: E402
from spotlab.gui.theme import DUNKEL                        # noqa: E402


def _farben(karte, zeile):
    return {fmt.foreground().color().name() for _, _, fmt in karte.get(zeile, ())}


def test_schluesselwort_bekommt_die_schluesselwortfarbe(qapp):
    karte = spannen("import spotlab\n", DUNKEL)
    assert DUNKEL.schluesselwort in _farben(karte, 0)


def test_zahl_und_zeichenkette(qapp):
    karte = spannen("x = 42\ns = 'hallo'\n", DUNKEL)
    assert DUNKEL.zahl in _farben(karte, 0)
    assert DUNKEL.zeichenkette in _farben(karte, 1)


def test_kommentar(qapp):
    karte = spannen("# eine Notiz\n", DUNKEL)
    assert DUNKEL.kommentar in _farben(karte, 0)


def test_mehrzeilige_zeichenkette_faerbt_nur_ihre_zeilen(qapp):
    # Der Fehler, den zeilenweise Hervorheber machen: ab dem Docstring wird
    # der halbe Rest der Datei gruen.
    text = 'a = """eins\nzwei"""\nb = 1\n'
    karte = spannen(text, DUNKEL)
    assert DUNKEL.zeichenkette in _farben(karte, 0)
    assert DUNKEL.zeichenkette in _farben(karte, 1)
    assert DUNKEL.zeichenkette not in _farben(karte, 2)
    assert DUNKEL.zahl in _farben(karte, 2)


def test_spalten_stimmen(qapp):
    karte = spannen("x = 1\n", DUNKEL)
    zahlen = [(spalte, laenge) for spalte, laenge, fmt in karte[0]
              if fmt.foreground().color().name() == DUNKEL.zahl]
    assert zahlen == [(4, 1)]


def test_leerer_text_ergibt_leere_karte(qapp):
    assert spannen("", DUNKEL) == {}
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_highlighter.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.gui.editor'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/editor/__init__.py`:

```python
"""Die Widgets des eingebauten Editors.

Was nicht Widget ist, liegt in spotlab.editor — Qt-frei und SDK-frei.
Hier gilt weiterhin: kein import bosdyn und kein import spotlab.backends.
"""
```

`src/spotlab/gui/editor/highlighter.py`:

```python
"""Syntaxhervorhebung ueber pygments.

Bewusst NICHT zeilenweise: dreifach zitierte Zeichenketten laufen ueber
mehrere Zeilen, und ein zeilenweiser Hervorheber faerbt ab dem ersten
Docstring den halben Rest der Datei gruen. Deshalb lext dieses Modul das ganze
Dokument und legt eine Karte Blocknummer -> Spannen an; highlightBlock
schlaegt darin nur nach. Ein Schuelerskript hat 50-300 Zeilen; das kostet nichts.
"""

import bisect

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from pygments.lexers import PythonLexer
from pygments.token import Comment, Keyword, Name, Number, String


def _formate(palette):
    def format_mit(farbe):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(farbe))
        return fmt

    # Geordnet: das erste passende Token gewinnt. `art in token` prueft in
    # pygments auch Untertypen (Keyword.Constant liegt in Keyword).
    return (
        (Keyword, format_mit(palette.schluesselwort)),
        (String, format_mit(palette.zeichenkette)),
        (Comment, format_mit(palette.kommentar)),
        (Number, format_mit(palette.zahl)),
        (Name.Function, format_mit(palette.funktion)),
        (Name.Class, format_mit(palette.funktion)),
        (Name.Builtin, format_mit(palette.funktion)),
    )


def _passendes(art, formate):
    for token, fmt in formate:
        if art in token:
            return fmt
    return None


def _zeilenanfaenge(text):
    anfaenge = [0]
    pos = text.find("\n")
    while pos != -1:
        anfaenge.append(pos + 1)
        pos = text.find("\n", pos + 1)
    return anfaenge


def _nach_zeilen(index, wert):
    """Zerlegt einen Token, der ueber Zeilen laeuft, in ein Stueck je Zeile."""
    pos = index
    for stueck in wert.split("\n"):
        if stueck:
            yield pos, stueck
        pos += len(stueck) + 1


def spannen(text, palette, lexer=None):
    """Blocknummer -> [(spalte, laenge, QTextCharFormat)]. Ohne Widget prüfbar."""
    if not text:
        return {}
    lexer = lexer or PythonLexer()
    formate = _formate(palette)
    anfaenge = _zeilenanfaenge(text)
    karte = {}
    for index, art, wert in lexer.get_tokens_unprocessed(text):
        fmt = _passendes(art, formate)
        if fmt is None or not wert:
            continue
        for teil_index, teil in _nach_zeilen(index, wert):
            nummer = bisect.bisect_right(anfaenge, teil_index) - 1
            karte.setdefault(nummer, []).append(
                (teil_index - anfaenge[nummer], len(teil), fmt)
            )
    return karte


class Hervorheber(QSyntaxHighlighter):
    def __init__(self, dokument, palette):
        super().__init__(dokument)
        self._palette = palette
        self._karte = {}

    def neu_lexen(self):
        """Aus dem `ruhe`-Signal von CodeEdit aufgerufen, nie aus textChanged.

        Ein rehighlight() direkt im Aenderungssignal loeste sich selbst wieder aus.
        """
        self._karte = spannen(self.document().toPlainText(), self._palette)
        self.rehighlight()

    def highlightBlock(self, text):
        nummer = self.currentBlock().blockNumber()
        for spalte, laenge, fmt in self._karte.get(nummer, ()):
            self.setFormat(spalte, laenge, fmt)
```

In `pyproject.toml` das Extra ergänzen:

```toml
gui = ["PySide6>=6.6", "pygments>=2.17"]
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_highlighter.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/editor/__init__.py src/spotlab/gui/editor/highlighter.py pyproject.toml tests/test_gui_highlighter.py
git commit -m "feat(gui): Syntaxhervorhebung ueber pygments, dokumentweit gelext"
```

---

## Aufgabe 8: `gui/editor/codeedit.py` — das Textfeld

**Dateien:**
- Anlegen: `src/spotlab/gui/editor/codeedit.py`
- Test: `tests/test_gui_codeedit.py`

**Schnittstellen:**
- Verbraucht: `EINRUECKUNG`, `naechste_einrueckung`, `ausruecken` (Aufgabe 4);
  `Fehlerstelle` (Aufgabe 1); `Hervorheber` (Aufgabe 7).
- Liefert: `CodeEdit(palette, parent=None)` mit Signalen `ruhe`, `speichern_gewuenscht`,
  `vervollstaendigung_gewuenscht` und Methoden `zeige_fehler(stelle)`,
  `zeilenleiste_breite()`, `suchleiste_umschalten()`; ausserdem `Suchleiste(editor)`.
  Aufgaben 9 und 11 hängen daran.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_gui_codeedit.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt                                # noqa: E402
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
    feld.moveCursor(feld.textCursor().End)
    QTest.keyClick(feld, Qt.Key_Return)
    assert feld.toPlainText() == "    x = 1\n    "


def test_enter_nach_doppelpunkt_rueckt_ein(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("def f():")
    feld.moveCursor(feld.textCursor().End)
    QTest.keyClick(feld, Qt.Key_Return)
    assert feld.toPlainText() == "def f():\n    "


def test_shift_tab_rueckt_aus(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("        x = 1")
    feld.moveCursor(feld.textCursor().End)
    QTest.keyClick(feld, Qt.Key_Backtab)
    assert feld.toPlainText() == "    x = 1"


def test_ctrl_s_meldet_speicherwunsch(qapp):
    feld = CodeEdit(DUNKEL)
    gerufen = []
    feld.speichern_gewuenscht.connect(lambda: gerufen.append(True))
    QTest.keyClick(feld, Qt.Key_S, Qt.ControlModifier)
    assert gerufen == [True]
    assert feld.toPlainText() == ""      # das S darf nicht im Text landen


def test_fehler_wird_unterkringelt_und_als_hinweis_gezeigt(qapp):
    feld = CodeEdit(DUNKEL)
    feld.setPlainText("x = 1\n  y = 2\n")
    feld.zeige_fehler(pruefe(feld.toPlainText()))
    assert "eingerückt" in feld.toolTip()
    assert len(feld.extraSelections()) >= 1


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
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_codeedit.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.gui.editor.codeedit'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/editor/codeedit.py`:

```python
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
                farbe = self._palette.gefahr if nummer == self._fehlerzeile else self._palette.gedaempft
                maler.setPen(QColor(farbe))
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
        if ereignis.text() and (ereignis.text().isalnum() or ereignis.text() in "._"):
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
        if getattr(self, "suchleiste", None) is None:
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
        weiter = QPushButton("Weiter")
        zurueck = QPushButton("Zurück")
        ersetzen = QPushButton("Ersetzen")
        alle = QPushButton("Alle ersetzen")
        schliessen = QPushButton("Schliessen")

        weiter.clicked.connect(lambda: self._suche(rueckwaerts=False))
        zurueck.clicked.connect(lambda: self._suche(rueckwaerts=True))
        ersetzen.clicked.connect(self._ersetze)
        alle.clicked.connect(self._ersetze_alle)
        schliessen.clicked.connect(lambda: self.setVisible(False))
        self.suchfeld.returnPressed.connect(lambda: self._suche(rueckwaerts=False))

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

    def _suche(self, rueckwaerts):
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

    def _ersetze(self):
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == self.suchfeld.text():
            cursor.insertText(self.ersatzfeld.text())
        self._suche(rueckwaerts=False)

    def _ersetze_alle(self):
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
```

Der Import `QTextDocument` fehlt oben noch — er kommt aus `PySide6.QtGui` und gehört in die
bestehende `from PySide6.QtGui import (...)`-Zeile.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_codeedit.py -q
```

Erwartet: PASS. Falls `test_ctrl_s_meldet_speicherwunsch` fehlschlägt, weil das `S` im Text
landet: `ereignis.matches(QKeySequence.Save)` muss **vor** `super().keyPressEvent` stehen und
mit `return` enden.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/editor/codeedit.py tests/test_gui_codeedit.py
git commit -m "feat(gui): Textfeld mit Zeilenleiste, Einrueckung, Fehlerkringel, Suche"
```

---

## Aufgabe 9: `gui/editor/completer.py` — Vorschläge

**Dateien:**
- Anlegen: `src/spotlab/gui/editor/completer.py`
- Ändern: `pyproject.toml` (`jedi` ins Extra `gui`)
- Test: `tests/test_gui_completer.py`

**Schnittstellen:**
- Verbraucht: `Vorschlag`, `praefix`, `teilwort`, `spot_verben`, `spotlab_verben` (Aufgabe 3);
  `CodeEdit` (Aufgabe 8).
- Liefert: `zusammenfuehren(eigene, fremde) -> list[Vorschlag]`,
  `eigene_vorschlaege(text_vor_cursor) -> list[Vorschlag]`,
  `Vervollstaendigung(editor, parent=None)` mit `setze_pfad(pfad)` und `anfordern(erzwungen)`.
  Aufgabe 11 hängt sie an jeden neuen Reiter.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_gui_completer.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

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
    fremd = Vorschlag("move", "move", "function")
    zusammen = zusammenfuehren([eigen], [fremd])
    assert zusammen == [eigen]


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


def test_ohne_jedi_kommen_trotzdem_vorschlaege(qapp, monkeypatch):
    """Der Rueckfall ist die Bedingung dafuer, dass die Suite ohne jedi gruen ist."""
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText("spot.")
    feld.moveCursor(feld.textCursor().End)
    hilfe.anfordern(erzwungen=True)
    assert hilfe.modell.rowCount() > 0


def test_veraltete_jedi_antwort_wird_verworfen(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText("spot.")
    feld.moveCursor(feld.textCursor().End)
    hilfe.anfordern(erzwungen=True)
    vorher = hilfe.modell.rowCount()
    hilfe._jedi_fertig(-1, [Vorschlag("veraltet", "veraltet", "")])
    assert hilfe.modell.rowCount() == vorher


def test_einfuegen_schreibt_den_blossen_namen(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText("spot.mo")
    feld.moveCursor(feld.textCursor().End)
    hilfe.anfordern(erzwungen=True)
    hilfe._einfuegen("move")
    assert feld.toPlainText() == "spot.move"


def test_einfuegen_versteht_auch_den_anzeigetext(qapp, monkeypatch):
    # Absicherung gegen die Qt-Version: je nach Aufbau liefert
    # QCompleter.activated den completionRole ODER den Anzeigetext.
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText("spot.")
    feld.moveCursor(feld.textCursor().End)
    hilfe.anfordern(erzwungen=True)
    anzeige = hilfe.modell.data(hilfe.modell.index(0, 0))
    name = hilfe.modell.data(hilfe.modell.index(0, 0), modul.NAME_ROLLE)
    hilfe._einfuegen(anzeige)
    assert feld.toPlainText() == f"spot.{name}"


def test_mit_jedi_werden_fremde_namen_ergaenzt(qapp):
    """Was jedi abdeckt und wir nicht: math., np., lokale Variablen."""
    pytest.importorskip("jedi")
    feld = CodeEdit(DUNKEL)
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText("import math\nmath.")
    feld.moveCursor(feld.textCursor().End)
    fremde = hilfe._jedi_lesen(feld.toPlainText(), 2, 5, None)
    assert "sqrt" in {v.name for v in fremde}
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_completer.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.gui.editor.completer'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/editor/completer.py`:

```python
"""Vorschlaege: die eigene Liste sofort, jedi wenn es rechtzeitig antwortet.

Die eigene Liste ist geprueft und garantiert — "nach spot. muss navigate_to
vorkommen" ist eine Aussage ueber unseren eigenen Code. Ob jedi durch
`with spotlab.connect() as spot:` hindurch auf Spot schliesst, haengt an
fremder Inferenz durch einen @contextmanager. jedi deckt dafuer ab, was wir
nicht wissen koennen: lokale Variablen, math., np., Importnamen.

Fehlt jedi oder wirft es, bleibt es bei der eigenen Liste — ohne Hinweis und
ohne Fehler. Ein Editor, der sich ueber eine fehlende Vervollstaendigung
beschwert, ist laestiger als einer, der leise weniger kann.
"""

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QCompleter

from spotlab.editor.verbs import Vorschlag, praefix, spot_verben, spotlab_verben, teilwort

try:
    import jedi
except Exception:       # pragma: no cover - haengt an der Installation
    jedi = None

NAME_ROLLE = Qt.UserRole + 1

# jedis Typnamen auf Deutsch — t.type ist billig, t.description loest aus.
ARTEN = {
    "function": "Funktion",
    "class": "Klasse",
    "module": "Modul",
    "instance": "Wert",
    "keyword": "Schlüsselwort",
    "statement": "Variable",
    "param": "Parameter",
    "path": "Pfad",
}


def zusammenfuehren(eigene, fremde):
    """Erst die eigenen, dann der Rest. Bei Namensgleichheit gewinnt der eigene."""
    ergebnis = list(eigene)
    bekannt = {v.name for v in ergebnis}
    for vorschlag in fremde:
        if vorschlag.name in bekannt:
            continue
        bekannt.add(vorschlag.name)
        ergebnis.append(vorschlag)
    return ergebnis


def eigene_vorschlaege(text_vor_cursor):
    ziel = praefix(text_vor_cursor)
    if ziel == "spot":
        return list(spot_verben())
    if ziel == "spotlab":
        return list(spotlab_verben())
    return []


class VorschlagModell(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._zeilen = []

    def setze(self, vorschlaege):
        self.beginResetModel()
        self._zeilen = list(vorschlaege)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._zeilen)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._zeilen):
            return None
        eintrag = self._zeilen[index.row()]
        if role == Qt.DisplayRole:
            return f"{eintrag.signatur}   {eintrag.hilfe}".rstrip()
        if role == NAME_ROLLE:
            return eintrag.name
        return None


class JediWorker(QThread):
    fertig = Signal(int, list)

    def __init__(self, nummer, quelltext, zeile, spalte, pfad, parent=None):
        super().__init__(parent)
        self._nummer = nummer
        self._quelltext = quelltext
        self._zeile = zeile
        self._spalte = spalte
        self._pfad = pfad

    def run(self):
        self.fertig.emit(
            self._nummer, _jedi_lesen(self._quelltext, self._zeile, self._spalte, self._pfad)
        )


def _jedi_lesen(quelltext, zeile, spalte, pfad):
    """Blockierend — laeuft nur im JediWorker oder im Test."""
    if jedi is None:
        return []
    try:
        skript = jedi.Script(code=quelltext, path=pfad)
        return [
            Vorschlag(t.name, t.name, ARTEN.get(t.type, ""))
            for t in skript.complete(zeile, spalte)
        ]
    except Exception:
        # Fremder Code: was hier schiefgeht, darf den Editor nicht mitreissen.
        return []


class Vervollstaendigung(QObject):
    def __init__(self, editor, parent=None):
        super().__init__(parent or editor)
        self._editor = editor
        self._pfad = None
        self._nummer = 0
        self._eigene = []
        self._anzeige_zu_name = {}
        self._worker = None

        self.modell = VorschlagModell(self)
        self.completer = QCompleter(self.modell, self)
        self.completer.setWidget(editor)
        self.completer.setCompletionRole(NAME_ROLLE)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.activated.connect(self._einfuegen)

        editor.vervollstaendigung_gewuenscht.connect(self.anfordern)

    def setze_pfad(self, pfad):
        self._pfad = str(pfad) if pfad else None

    # Der eigene Teil ist sofort da; jedi ergaenzt, wenn es antwortet.
    def anfordern(self, erzwungen=False):
        vor = self._vor_dem_cursor()
        self._eigene = eigene_vorschlaege(vor)
        if not self._eigene and not erzwungen:
            self.completer.popup().hide()
            return
        self._nummer += 1
        self._zeige(self._eigene, teilwort(vor))
        self._frage_jedi(self._nummer)

    def _vor_dem_cursor(self):
        cursor = self._editor.textCursor()
        return cursor.block().text()[: cursor.positionInBlock()]

    def _zeige(self, vorschlaege, praefixwort):
        self.modell.setze(vorschlaege)
        self._anzeige_zu_name = {}
        for zeile in range(self.modell.rowCount()):
            index = self.modell.index(zeile, 0)
            self._anzeige_zu_name[self.modell.data(index)] = self.modell.data(
                index, NAME_ROLLE
            )
        if not vorschlaege:
            self.completer.popup().hide()
            return
        self.completer.setCompletionPrefix(praefixwort)
        if self.completer.completionCount() == 0:
            self.completer.popup().hide()
            return
        rechteck = self._editor.cursorRect()
        rechteck.setWidth(
            self.completer.popup().sizeHintForColumn(0)
            + self.completer.popup().verticalScrollBar().sizeHint().width()
        )
        self.completer.complete(rechteck)

    def _frage_jedi(self, nummer):
        if jedi is None:
            return
        cursor = self._editor.textCursor()
        self._worker = JediWorker(
            nummer,
            self._editor.toPlainText(),
            cursor.blockNumber() + 1,
            cursor.positionInBlock(),
            self._pfad,
            self,
        )
        self._worker.fertig.connect(self._jedi_fertig)
        self._worker.start()

    def _jedi_fertig(self, nummer, fremde):
        if nummer != self._nummer:
            # Veraltet: eine langsame alte Antwort darf eine schnelle neue
            # nicht ueberschreiben.
            return
        self._zeige(zusammenfuehren(self._eigene, fremde), teilwort(self._vor_dem_cursor()))

    def _einfuegen(self, text):
        """QCompleter.activated liefert je nach Qt-Aufbau den completionRole
        (= den Namen) oder den Anzeigetext. Beides fuehrt hier zum Namen."""
        name = self._anzeige_zu_name.get(text, text)
        cursor = self._editor.textCursor()
        offen = len(teilwort(self._vor_dem_cursor()))
        if offen:
            cursor.movePosition(cursor.Left, cursor.KeepAnchor, offen)
            cursor.removeSelectedText()
        cursor.insertText(name)
        self._editor.setTextCursor(cursor)
```

Die Testdatei ruft `hilfe._jedi_lesen(...)`; damit das geht, im `Vervollstaendigung`-Körper
ergänzen:

```python
    _jedi_lesen = staticmethod(_jedi_lesen)
```

In `pyproject.toml`:

```toml
gui = ["PySide6>=6.6", "pygments>=2.17", "jedi>=0.19"]
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_completer.py -q
python -m pytest -q
```

Erwartet: PASS. Der jedi-Test wird übersprungen, solange `jedi` nicht installiert ist — das
ist richtig so. Zum Gegenprüfen einmal `python -m pip install jedi` und erneut laufen lassen;
**beide Läufe müssen grün sein.**

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/editor/completer.py pyproject.toml tests/test_gui_completer.py
git commit -m "feat(gui): Vervollstaendigung mit eigener Verbliste, jedi optional obendrauf"
```

---

## Aufgabe 10: `gui/editor/tree.py` — der Dateibaum

**Dateien:**
- Anlegen: `src/spotlab/gui/editor/tree.py`
- Test: `tests/test_gui_tree.py`

**Schnittstellen:**
- Verbraucht: nichts aus den vorigen Aufgaben.
- Liefert: `Dateibaum(parent=None)` mit `setze_projekt(pfad)`, Signal `datei_gewaehlt(object)`
  (ein `Path`), Attribut `.modell` (`QFileSystemModel`) und `.ansicht` (`QTreeView`);
  ausserdem `KeineLaeufe(wurzel)`. Aufgabe 11 setzt es links in die Ansicht.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_gui_tree.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer                 # noqa: E402

from spotlab.gui.editor.tree import Dateibaum                 # noqa: E402


def _warte_aufs_laden(baum, sekunden=5.0):
    """QFileSystemModel laedt Verzeichnisse in einem eigenen Thread."""
    schleife = QEventLoop()
    baum.modell.directoryLoaded.connect(lambda _pfad: schleife.quit())
    QTimer.singleShot(int(sekunden * 1000), schleife.quit)
    schleife.exec()


def _projekt(tmp_path):
    projekt = tmp_path / "demo"
    (projekt / "runs" / "20260807T101010Z").mkdir(parents=True)
    (projekt / "runs" / "20260807T101010Z" / "zustand.jsonl").write_text("{}\n", encoding="utf-8")
    (projekt / "hallo_spot.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / "notiz.md").write_text("# Notiz\n", encoding="utf-8")
    (projekt / "bild.png").write_bytes(b"\x89PNG")
    return projekt


def _sichtbare_namen(baum):
    proxy = baum.ansicht.model()
    wurzel = baum.ansicht.rootIndex()
    return {proxy.data(proxy.index(z, 0, wurzel)) for z in range(proxy.rowCount(wurzel))}


def test_zeigt_python_und_text_dateien(qapp, tmp_path):
    baum = Dateibaum()
    baum.setze_projekt(_projekt(tmp_path))
    _warte_aufs_laden(baum)
    namen = _sichtbare_namen(baum)
    assert "hallo_spot.py" in namen
    assert "notiz.md" in namen


def test_runs_wird_ausgeblendet(qapp, tmp_path):
    # Sonst horcht QFileSystemModel auf zustand.jsonl, in die der Sampler mit
    # 10 Hz schreibt — Aenderungssignale im Zehntelsekundentakt.
    baum = Dateibaum()
    baum.setze_projekt(_projekt(tmp_path))
    _warte_aufs_laden(baum)
    assert "runs" not in _sichtbare_namen(baum)


def test_bilder_werden_nicht_gezeigt(qapp, tmp_path):
    baum = Dateibaum()
    baum.setze_projekt(_projekt(tmp_path))
    _warte_aufs_laden(baum)
    assert "bild.png" not in _sichtbare_namen(baum)


def test_ohne_projekt_bleibt_der_baum_leer(qapp):
    baum = Dateibaum()
    baum.setze_projekt(None)
    assert not baum.ansicht.rootIndex().isValid()
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_tree.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.gui.editor.tree'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/editor/tree.py`:

```python
"""Der Dateibaum eines Projekts.

Ein Projekt auf einmal, nicht die ganze Werkstatt: der Baum bleibt kurz genug,
um ihn zu ueberblicken.
"""

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Signal
from PySide6.QtWidgets import QFileSystemModel, QTreeView, QVBoxLayout, QWidget

ENDUNGEN = ("*.py", "*.md", "*.txt", "*.json")


class KeineLaeufe(QSortFilterProxyModel):
    """Blendet runs/ auf oberster Ebene aus.

    Namensfilter greifen in Qt nur auf Dateien, nicht auf Verzeichnisse. Und
    ein QFileSystemModel ueber runs/ horcht auf zustand.jsonl, in die der
    Sampler mit 10 Hz schreibt — Aenderungssignale im Zehntelsekundentakt fuer
    Dateien, die im Editor ohnehin niemand oeffnet.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wurzel = None

    def setze_wurzel(self, pfad):
        self._wurzel = Path(pfad) if pfad else None
        self.invalidateFilter()

    def filterAcceptsRow(self, zeile, eltern):
        quelle = self.sourceModel()
        if quelle is None or self._wurzel is None:
            return True
        index = quelle.index(zeile, 0, eltern)
        if not index.isValid() or not quelle.isDir(index):
            return True
        pfad = Path(quelle.filePath(index))
        return not (pfad.name == "runs" and pfad.parent == self._wurzel)


class Dateibaum(QWidget):
    datei_gewaehlt = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modell = QFileSystemModel(self)
        self.modell.setNameFilters(list(ENDUNGEN))
        self.modell.setNameFilterDisables(False)

        self.filter = KeineLaeufe(self)
        self.filter.setSourceModel(self.modell)

        self.ansicht = QTreeView()
        self.ansicht.setModel(self.filter)
        self.ansicht.setHeaderHidden(True)
        for spalte in (1, 2, 3):
            self.ansicht.hideColumn(spalte)
        self.ansicht.doubleClicked.connect(self._gewaehlt)

        anordnung = QVBoxLayout(self)
        anordnung.setContentsMargins(0, 0, 0, 0)
        anordnung.addWidget(self.ansicht)

    def setze_projekt(self, pfad):
        if not pfad:
            self.ansicht.setRootIndex(self.filter.index(-1, -1))
            self.filter.setze_wurzel(None)
            return
        wurzel = Path(pfad)
        self.filter.setze_wurzel(wurzel)
        quelle = self.modell.setRootPath(str(wurzel))
        self.ansicht.setRootIndex(self.filter.mapFromSource(quelle))

    def _gewaehlt(self, index):
        quelle = self.filter.mapToSource(index)
        if self.modell.isDir(quelle):
            return
        self.datei_gewaehlt.emit(Path(self.modell.filePath(quelle)))
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_tree.py -q
```

Erwartet: PASS. Hängt ein Test, ist `_warte_aufs_laden` nicht gelaufen — `directoryLoaded`
kann bereits gefeuert haben; dann den Timeout im Test greifen lassen und die Namen trotzdem
prüfen.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/editor/tree.py tests/test_gui_tree.py
git commit -m "feat(gui): Dateibaum je Projekt, runs/ ausgeblendet"
```

---

## Aufgabe 11: Ansicht „Code" — Reiter, Laden, Speichern

**Dateien:**
- Anlegen: `src/spotlab/gui/editor/view.py`
- Test: `tests/test_gui_editorview.py`

**Schnittstellen:**
- Verbraucht: `CodeEdit` (8), `Hervorheber` (7), `Vervollstaendigung` (9), `Dateibaum` (10),
  `pruefe` (1), `projekte_in` aus `spotlab.gui.views.projects`.
- Liefert: `EditorView(palette, parent=None)` mit `setze_arbeitsordner(pfad)`,
  `setze_projekt(pfad)`, `oeffne(pfad)`, `speichere_aktuellen() -> bool`,
  `springe_zu(pfad, zeile)`, Signal `meldung(str)`, Attribute `.reiter` (QTabWidget),
  `.projektwahl` (QComboBox), `.baum`; ausserdem `Reiter`, `lade_text`, `schreibe_text`,
  `stempel`. Aufgabe 12 ergänzt Starten und Ausgabe **in derselben Datei**.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_gui_editorview.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.errors import SpotlabError                        # noqa: E402
from spotlab.gui.editor.view import EditorView                 # noqa: E402
from spotlab.gui.theme import DUNKEL                           # noqa: E402


def _werkstatt(tmp_path):
    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    (projekt / "hallo_spot.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path, projekt


def test_datei_oeffnen_legt_einen_reiter_an(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.setze_projekt(projekt)
    ansicht.oeffne(projekt / "hallo_spot.py")
    assert ansicht.reiter.count() == 1
    assert ansicht.reiter.currentWidget().toPlainText() == "x = 1\n"


def test_dieselbe_datei_zweimal_oeffnen_gibt_denselben_reiter(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.oeffne(projekt / "hallo_spot.py")
    assert ansicht.reiter.count() == 1


def test_aenderung_markiert_den_reiter(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.reiter.currentWidget().setPlainText("x = 2\n")
    assert ansicht.reiter.tabText(0).startswith("●")


def test_speichern_schreibt_lf_und_utf8(qapp, tmp_path):
    # Ohne newline="\n" schreibt Python auf Windows CRLF, und jede Datei sieht
    # danach in git vollstaendig geaendert aus.
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ziel = projekt / "hallo_spot.py"
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("s = 'grün'\n")
    assert ansicht.speichere_aktuellen() is True
    roh = ziel.read_bytes()
    assert b"\r\n" not in roh
    assert roh.decode("utf-8") == "s = 'grün'\n"
    assert not ansicht.reiter.tabText(0).startswith("●")


def test_nicht_utf8_wird_abgelehnt(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    kaputt = projekt / "latin.py"
    kaputt.write_bytes(b"s = '\xe4\xf6\xfc'\n")
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.oeffne(kaputt)
    assert ansicht.reiter.count() == 0          # kein halb geladener Reiter
    assert gemeldet and "UTF-8" in gemeldet[0]


def test_fremde_aenderung_wird_erkannt(qapp, tmp_path):
    # Folgt direkt daraus, dass VS Code eine Option bleibt: beide Editoren
    # haben regelmaessig dieselbe Datei offen.
    ordner, projekt = _werkstatt(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(ziel)
    eintrag = ansicht.aktueller_reiter()
    ziel.write_text("von VS Code geschrieben\n", encoding="utf-8")
    assert ansicht.fremd_geaendert(eintrag) is True


def test_abbrechen_bei_fremder_aenderung_schreibt_nicht(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("meins\n")
    ziel.write_text("fremd\n", encoding="utf-8")
    ansicht.frage_bei_konflikt = lambda pfad: "abbrechen"
    assert ansicht.speichere_aktuellen() is False
    assert ziel.read_text(encoding="utf-8") == "fremd\n"


def test_neu_laden_bei_fremder_aenderung(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("meins\n")
    ziel.write_text("fremd\n", encoding="utf-8")
    ansicht.frage_bei_konflikt = lambda pfad: "neu_laden"
    assert ansicht.speichere_aktuellen() is False
    assert ansicht.reiter.currentWidget().toPlainText() == "fremd\n"


def test_projektwahl_listet_die_projekte(qapp, tmp_path):
    ordner, _ = _werkstatt(tmp_path)
    (ordner / "zweites" / "runs").mkdir(parents=True)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    eintraege = {ansicht.projektwahl.itemText(i) for i in range(ansicht.projektwahl.count())}
    assert {"demo", "zweites"} <= eintraege


def test_syntaxfehler_erscheint_nach_der_ruhepause(qapp, tmp_path):
    from PySide6.QtTest import QTest

    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.reiter.currentWidget().setPlainText("def f()\n    return 1\n")
    QTest.qWait(400)
    assert "Doppelpunkt" in ansicht.reiter.currentWidget().toolTip()
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_editorview.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.gui.editor.view'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/editor/view.py`:

```python
"""Die Ansicht „Code": Dateibaum, Reiter, Ausgabe.

Leitsatz der Aufteilung: „Code" zeigt, was das Programm sagt; „Live-Lauf"
zeigt, was der Roboter tut. Deshalb steht hier keine Telemetrie.
"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from spotlab.editor.syntax import pruefe
from spotlab.errors import SpotlabError
from spotlab.gui.editor.codeedit import CodeEdit
from spotlab.gui.editor.completer import Vervollstaendigung
from spotlab.gui.editor.highlighter import Hervorheber
from spotlab.gui.editor.tree import Dateibaum
from spotlab.gui.views.projects import projekte_in


def lade_text(pfad):
    try:
        return Path(pfad).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise SpotlabError(
            f"{Path(pfad).name} ist nicht UTF-8 kodiert und lässt sich hier nicht "
            "öffnen. Speichere die Datei in VS Code als UTF-8."
        )


def schreibe_text(pfad, text):
    # newline="\n": sonst schreibt Python auf Windows CRLF und jede Datei sieht
    # nach dem ersten Speichern in git vollstaendig geaendert aus.
    Path(pfad).write_text(text, encoding="utf-8", newline="\n")


def stempel(pfad):
    zustand = Path(pfad).stat()
    return zustand.st_mtime, zustand.st_size


@dataclass
class Reiter:
    pfad: Path
    feld: CodeEdit
    hervorheber: object
    hilfe: object
    mtime: float
    groesse: int
    verschmutzt: bool = False


class EditorView(QWidget):
    meldung = Signal(str)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._ordner = None
        self._projekt = None
        self._reiter = {}          # CodeEdit -> Reiter

        self.projektwahl = QComboBox()
        self.projektwahl.currentTextChanged.connect(self._projekt_gewechselt)
        self.baum = Dateibaum()
        self.baum.datei_gewaehlt.connect(self.oeffne)

        links = QWidget()
        links_anordnung = QVBoxLayout(links)
        links_anordnung.setContentsMargins(0, 0, 0, 0)
        links_anordnung.addWidget(self.projektwahl)
        links_anordnung.addWidget(self.baum, 1)

        self.reiter = QTabWidget()
        self.reiter.setTabsClosable(True)
        self.reiter.setDocumentMode(True)
        self.reiter.tabCloseRequested.connect(self._schliesse)

        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(self.reiter)
        self.teiler.setStretchFactor(1, 1)

        aussen = QVBoxLayout(self)
        aussen.addWidget(self.teiler, 1)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.projektwahl.blockSignals(True)
        self.projektwahl.clear()
        if self._ordner is not None:
            for projekt in projekte_in(self._ordner):
                self.projektwahl.addItem(projekt.name)
        self.projektwahl.blockSignals(False)
        if self.projektwahl.count():
            self.projektwahl.setCurrentIndex(0)
            self._projekt_gewechselt(self.projektwahl.currentText())
        else:
            self.setze_projekt(None)

    def setze_projekt(self, pfad):
        self._projekt = Path(pfad) if pfad else None
        self.baum.setze_projekt(self._projekt)
        if self._projekt is not None:
            name = self._projekt.name
            if self.projektwahl.currentText() != name:
                index = self.projektwahl.findText(name)
                if index >= 0:
                    self.projektwahl.setCurrentIndex(index)

    def _projekt_gewechselt(self, name):
        if self._ordner is None or not name:
            return
        self.setze_projekt(self._ordner / name)

    def aktueller_reiter(self):
        feld = self.reiter.currentWidget()
        return self._reiter.get(feld)

    # ------------------------------------------------------------- Dateien

    def oeffne(self, pfad):
        pfad = Path(pfad)
        for feld, eintrag in self._reiter.items():
            if eintrag.pfad == pfad:
                self.reiter.setCurrentWidget(feld)
                return
        try:
            text = lade_text(pfad)
        except (SpotlabError, OSError) as fehler:
            self.meldung.emit(str(fehler))
            return

        feld = CodeEdit(self._palette)
        feld.setPlainText(text)
        hervorheber = Hervorheber(feld.document(), self._palette)
        hilfe = Vervollstaendigung(feld)
        hilfe.setze_pfad(pfad)
        feld.ruhe.connect(hervorheber.neu_lexen)
        feld.ruhe.connect(lambda f=feld: self._pruefe(f))
        feld.textChanged.connect(lambda f=feld: self._verschmutzt(f))
        feld.speichern_gewuenscht.connect(self.speichere_aktuellen)

        zeit, groesse = stempel(pfad)
        self._reiter[feld] = Reiter(pfad, feld, hervorheber, hilfe, zeit, groesse)
        self.reiter.addTab(feld, pfad.name)
        self.reiter.setCurrentWidget(feld)
        hervorheber.neu_lexen()

    def _pruefe(self, feld):
        feld.zeige_fehler(pruefe(feld.toPlainText(), name=str(self._reiter[feld].pfad)))

    def _verschmutzt(self, feld):
        eintrag = self._reiter.get(feld)
        if eintrag is None or eintrag.verschmutzt:
            return
        eintrag.verschmutzt = True
        self._titel(eintrag)

    def _titel(self, eintrag):
        index = self.reiter.indexOf(eintrag.feld)
        if index >= 0:
            marke = "● " if eintrag.verschmutzt else ""
            self.reiter.setTabText(index, f"{marke}{eintrag.pfad.name}")

    def fremd_geaendert(self, eintrag):
        try:
            return stempel(eintrag.pfad) != (eintrag.mtime, eintrag.groesse)
        except OSError:
            return False

    def frage_bei_konflikt(self, pfad):
        """Gibt 'ueberschreiben', 'neu_laden' oder 'abbrechen' zurück.

        Als Methode und nicht als Dialog mitten im Speichern: Tests ersetzen sie.
        """
        antwort = QMessageBox.question(
            self,
            "spotlab",
            f"{pfad.name} wurde ausserhalb von spotlab geändert.\n\n"
            "Überschreiben verwirft die fremde Änderung, Neu laden verwirft deine.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if antwort == QMessageBox.Save:
            return "ueberschreiben"
        if antwort == QMessageBox.Discard:
            return "neu_laden"
        return "abbrechen"

    def speichere_aktuellen(self):
        eintrag = self.aktueller_reiter()
        if eintrag is None:
            return False
        if self.fremd_geaendert(eintrag):
            wahl = self.frage_bei_konflikt(eintrag.pfad)
            if wahl == "abbrechen":
                return False
            if wahl == "neu_laden":
                self._neu_laden(eintrag)
                return False
        try:
            schreibe_text(eintrag.pfad, eintrag.feld.toPlainText())
        except OSError as fehler:
            self.meldung.emit(f"{eintrag.pfad.name} liess sich nicht speichern: {fehler}")
            return False
        eintrag.mtime, eintrag.groesse = stempel(eintrag.pfad)
        eintrag.verschmutzt = False
        self._titel(eintrag)
        return True

    def _neu_laden(self, eintrag):
        try:
            text = lade_text(eintrag.pfad)
        except (SpotlabError, OSError) as fehler:
            self.meldung.emit(str(fehler))
            return
        eintrag.feld.setPlainText(text)
        eintrag.mtime, eintrag.groesse = stempel(eintrag.pfad)
        eintrag.verschmutzt = False
        self._titel(eintrag)

    def _schliesse(self, index):
        feld = self.reiter.widget(index)
        eintrag = self._reiter.get(feld)
        if eintrag is not None and eintrag.verschmutzt:
            antwort = QMessageBox.question(
                self,
                "spotlab",
                f"{eintrag.pfad.name} hat ungespeicherte Änderungen. Trotzdem schliessen?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if antwort != QMessageBox.Yes:
                return
        self.reiter.removeTab(index)
        self._reiter.pop(feld, None)
        feld.deleteLater()

    def springe_zu(self, pfad, zeile):
        from PySide6.QtGui import QTextCursor

        self.oeffne(pfad)
        feld = self.reiter.currentWidget()
        if feld is None:
            return
        block = feld.document().findBlockByNumber(max(0, zeile - 1))
        if not block.isValid():
            return
        feld.setTextCursor(QTextCursor(block))
        feld.centerCursor()
        feld.setFocus()
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_editorview.py -q
```

Erwartet: PASS. Schlägt `test_speichern_schreibt_lf_und_utf8` fehl, prüfen, dass
`schreibe_text` wirklich `newline="\n"` übergibt.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/editor/view.py tests/test_gui_editorview.py
git commit -m "feat(gui): Ansicht Code mit Reitern, UTF-8/LF und Schutz vor Fremdaenderung"
```

---

## Aufgabe 12: Ansicht „Code" — Starten, Stoppen, anklickbare Ausgabe

**Dateien:**
- Ändern: `src/spotlab/gui/editor/view.py`
- Test: `tests/test_gui_editorview.py` (ergänzen)

**Schnittstellen:**
- Verbraucht: `finde_stellen` (Aufgabe 2), `start_script` aus `spotlab.workshop.launcher`.
- Liefert zusätzlich an `EditorView`: Signale `lauf_gestartet(object, str)` und
  `stopp_gewuenscht()`, Methoden `zeige_ausgabe(zeile)`, `lauf_beendet()`, Attribute
  `.ausgabe` (`Ausgabefeld`), `.start_knopf`, `.trockenlauf`; ausserdem Klasse `Ausgabefeld`.
  Aufgabe 13 verdrahtet alles im Hauptfenster.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_gui_editorview.py` anhängen:

```python
def test_ausgabe_macht_eigene_zeilen_anklickbar(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ziel = projekt / "hallo_spot.py"
    ansicht.zeige_ausgabe("Traceback (most recent call last):")
    ansicht.zeige_ausgabe(f'  File "{ziel}", line 1, in <module>')
    assert len(ansicht.ausgabe.stellen()) == 1
    von, bis, pfad, zeile = ansicht.ausgabe.stellen()[0]
    assert pfad == ziel.resolve() and zeile == 1
    assert ansicht.ausgabe.toPlainText()[von:bis].startswith('File "')


def test_ausgabe_laesst_fremde_zeilen_in_ruhe(qapp, tmp_path):
    ordner, _ = _werkstatt(tmp_path)
    fremd = tmp_path.parent / "fremd.py"
    fremd.write_text("x = 1\n", encoding="utf-8")
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.zeige_ausgabe(f'  File "{fremd}", line 3, in send')
    assert ansicht.ausgabe.stellen() == []


def test_klick_auf_eine_stelle_oeffnet_die_datei(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ziel.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.zeige_ausgabe(f'  File "{ziel}", line 3, in <module>')
    _von, _bis, pfad, zeile = ansicht.ausgabe.stellen()[0]
    ansicht.springe_zu(pfad, zeile)
    assert ansicht.reiter.count() == 1
    assert ansicht.reiter.currentWidget().textCursor().blockNumber() == 2


def test_starten_startet_wirklich_einen_prozess(qapp, tmp_path):
    """Attrappen pruefen nur, dass die richtigen Argumente gebaut werden — nicht,
    dass das Betriebssystem damit etwas anfangen kann. Genau daran ging
    „In VS Code öffnen" durch die ganze Suite."""
    ordner, projekt = _werkstatt(tmp_path)
    skript = projekt / "hallo_spot.py"
    skript.write_text("raise ValueError('kaputt')\n", encoding="utf-8")

    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(skript)
    ansicht.trockenlauf.setChecked(True)

    gestartet = []
    ansicht.lauf_gestartet.connect(lambda p, s: gestartet.append((p, s)))
    ansicht.start_knopf.click()
    assert gestartet, "kein Prozess gestartet"

    prozess, _skript = gestartet[0]
    for zeile in prozess.stdout:
        ansicht.zeige_ausgabe(zeile.rstrip("\n"))
    prozess.wait()

    # Ein echter Python-Traceback, echt erzeugt, echt zerlegt.
    assert "ValueError" in ansicht.ausgabe.toPlainText()
    assert [p for _v, _b, p, _z in ansicht.ausgabe.stellen()] == [skript.resolve()]


def test_starten_speichert_vorher(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    skript = projekt / "hallo_spot.py"
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(skript)
    ansicht.reiter.currentWidget().setPlainText("print('neu')\n")
    ansicht.trockenlauf.setChecked(True)
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    assert skript.read_text(encoding="utf-8") == "print('neu')\n"
    for p in prozesse:
        p.wait()


def test_knopf_wird_zu_stopp_und_meldet_den_wunsch(qapp, tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.trockenlauf.setChecked(True)
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    assert "Stopp" in ansicht.start_knopf.text()
    gewuenscht = []
    ansicht.stopp_gewuenscht.connect(lambda: gewuenscht.append(True))
    ansicht.start_knopf.click()
    assert gewuenscht == [True]
    ansicht.lauf_beendet()
    assert "Starten" in ansicht.start_knopf.text()
    for p in prozesse:
        p.wait()


def test_starten_ohne_offene_datei_meldet_es(qapp, tmp_path):
    ordner, _ = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.start_knopf.click()
    assert gemeldet and "Datei" in gemeldet[0]
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_editorview.py -q
```

Erwartet: FAIL mit `AttributeError: 'EditorView' object has no attribute 'ausgabe'`.

- [ ] **Schritt 3: Umsetzen**

In `src/spotlab/gui/editor/view.py` die Importe ergänzen:

```python
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    # ... die bisherigen
)

from spotlab.editor.traceback import finde_stellen
from spotlab.workshop.launcher import start_script
```

Vor `EditorView` die Klasse `Ausgabefeld` einfügen:

```python
class Ausgabefeld(QPlainTextEdit):
    """Die Ausgabe des Laufs, mit anklickbaren Stellen aus dem Traceback.

    Anklickbar wird nur, was in der Werkstatt liegt: sonst landet ein Schueler
    mit einem Klick in bosdyn/client/... und aendert fremden Bibliothekscode.
    """

    stelle_geklickt = Signal(object, int)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._palette = palette
        self._wurzel = None
        self._stellen = []          # (von, bis, pfad, zeile), absolut im Dokument

    def setze_wurzel(self, pfad):
        self._wurzel = Path(pfad) if pfad else None

    def stellen(self):
        return list(self._stellen)

    def leere(self):
        self.clear()
        self._stellen = []

    def haenge_an(self, zeile):
        vorher = self.toPlainText()
        basis = len(vorher) + (1 if vorher else 0)   # appendPlainText setzt ein \n davor
        self.appendPlainText(zeile)
        if self._wurzel is None:
            return
        for stelle in finde_stellen(zeile, self._wurzel):
            von, bis = basis + stelle.von, basis + stelle.bis
            self._stellen.append((von, bis, stelle.pfad, stelle.zeile))
            self._male_link(von, bis)

    def _male_link(self, von, bis):
        cursor = self.textCursor()
        cursor.setPosition(von)
        cursor.setPosition(bis, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._palette.akzent))
        fmt.setFontUnderline(True)
        cursor.mergeCharFormat(fmt)

    def mousePressEvent(self, ereignis):
        pos = self.cursorForPosition(ereignis.position().toPoint()).position()
        for von, bis, pfad, zeile in self._stellen:
            if von <= pos < bis:
                self.stelle_geklickt.emit(pfad, zeile)
                return
        super().mousePressEvent(ereignis)
```

In `EditorView` die Signale ergänzen und in `__init__` — **nach** dem Anlegen von
`self.reiter`, **vor** dem Splitter — die Werkzeugleiste und die Ausgabe aufbauen:

```python
class EditorView(QWidget):
    meldung = Signal(str)
    lauf_gestartet = Signal(object, str)
    stopp_gewuenscht = Signal()
```

```python
        self._laeuft = False
        self.trockenlauf = QCheckBox("Trockenlauf (ohne Roboter)")
        self.start_knopf = QPushButton("▶ Starten")
        self.start_knopf.clicked.connect(self._starten_oder_stoppen)

        werkzeuge = QHBoxLayout()
        werkzeuge.addWidget(self.trockenlauf)
        werkzeuge.addStretch(1)
        werkzeuge.addWidget(self.start_knopf)

        mitte = QWidget()
        mitte_anordnung = QVBoxLayout(mitte)
        mitte_anordnung.setContentsMargins(0, 0, 0, 0)
        mitte_anordnung.addLayout(werkzeuge)
        mitte_anordnung.addWidget(self.reiter, 1)

        self.ausgabe = Ausgabefeld(self._palette)
        self.ausgabe.stelle_geklickt.connect(self.springe_zu)
        self.hinweis = QLabel("Pose, Tempo und Kamerabild zeigt die Ansicht „Live-Lauf".")
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        rechts = QWidget()
        rechts_anordnung = QVBoxLayout(rechts)
        rechts_anordnung.setContentsMargins(0, 0, 0, 0)
        rechts_anordnung.addWidget(QLabel("Ausgabe"))
        rechts_anordnung.addWidget(self.ausgabe, 1)
        rechts_anordnung.addWidget(self.hinweis)
```

Der Splitter bekommt drei Spalten statt zwei:

```python
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(mitte)
        self.teiler.addWidget(rechts)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setSizes([220, 620, 300])
```

In `setze_arbeitsordner` die Wurzel der Ausgabe mitsetzen — **direkt nach**
`self._ordner = Path(pfad) if pfad else None`:

```python
        self.ausgabe.setze_wurzel(self._ordner)
```

Und die Start-/Stopp-Logik ans Ende der Klasse:

```python
    # ------------------------------------------------------------- Lauf

    def _starten_oder_stoppen(self):
        if self._laeuft:
            # Delegation ans Hauptfenster, das LiveView.stoppe() ruft: dasselbe
            # Objekt mit demselben Zustand, nicht eine zweite Kopie der Logik.
            self.stopp_gewuenscht.emit()
            return
        eintrag = self.aktueller_reiter()
        if eintrag is None:
            self.meldung.emit("Öffne zuerst eine Datei, die du starten möchtest.")
            return
        if not self.speichere_aktuellen():
            return          # wer auf Starten drückt, meint den Code, den er sieht
        try:
            prozess = start_script(eintrag.pfad, dryrun=self.trockenlauf.isChecked())
        except SpotlabError as fehler:
            self.meldung.emit(str(fehler))
            return
        self.ausgabe.leere()
        self._setze_laeuft(True)
        self.lauf_gestartet.emit(prozess, str(eintrag.pfad))

    def _setze_laeuft(self, laeuft):
        self._laeuft = laeuft
        self.start_knopf.setText("■ Stopp" if laeuft else "▶ Starten")

    def zeige_ausgabe(self, zeile):
        self.ausgabe.haenge_an(zeile)

    def lauf_beendet(self):
        self._setze_laeuft(False)
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_editorview.py -q
python -m pytest -q
```

Erwartet: PASS. `test_starten_startet_wirklich_einen_prozess` startet einen echten
Python-Prozess; er läuft im Trockenlauf und braucht weder Roboter noch Netz.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/editor/view.py tests/test_gui_editorview.py
git commit -m "feat(gui): Starten aus dem Editor und anklickbare Tracebacks"
```

---

## Aufgabe 13: Verdrahtung im Hauptfenster

**Dateien:**
- Ändern: `src/spotlab/gui/sidebar.py`
- Ändern: `src/spotlab/gui/app.py`
- Ändern: `src/spotlab/gui/views/projects.py`
- Test: `tests/test_gui_app.py` (ergänzen; falls die Datei anders heisst, in die bestehende
  MainWindow-Testdatei)

**Schnittstellen:**
- Verbraucht: `EditorView` (11, 12), `LiveView.stoppe` (vorhanden), `OutputReader` (vorhanden).
- Liefert: `MainWindow.ansichten["code"]`, `MainWindow._start_aus`,
  `ProjectsView.projekt_oeffnen(object)`.

**Die zwei Befunde, die hier umgesetzt werden:**
1. Es gibt genau **eine** Ausgabe-Pipe und darf genau **einen** Leser geben — ein zweiter
   teilte sich die Zeilen zufällig mit dem ersten.
2. `_lauf_begonnen` schaltet heute bedingungslos auf „Live-Lauf". Für F5-Läufe aus VS Code war
   das Absicht und bleibt. Für einen Start aus dem Editor wäre es falsch.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An die MainWindow-Testdatei anhängen:

```python
def test_seitenleiste_hat_die_ansicht_code(qapp):
    from spotlab.gui.sidebar import EINTRAEGE

    assert ("code", "Code") in EINTRAEGE


def test_ein_leser_speist_beide_ansichten(qapp):
    """Zwei OutputReader auf derselben Pipe teilten sich die Zeilen zufaellig auf."""
    fenster = MainWindow()
    fenster._starte_leser(_FakeProzess())
    fenster._leser.zeile.emit('  File "irgendwo.py", line 1')
    assert "irgendwo.py" in fenster.ansichten["code"].ausgabe.toPlainText()
    assert "irgendwo.py" in fenster.ansichten["live"].ausgabe.toPlainText()


def test_lauf_aus_dem_editor_schaltet_nicht_um(qapp, tmp_path):
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_aus_code(_FakeProzess(), "egal.py")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["code"]


def test_lauf_von_aussen_schaltet_weiterhin_um(qapp, tmp_path):
    """F5 in VS Code: der Schueler soll sehen, dass sein Programm laeuft."""
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_stopp_aus_dem_editor_geht_an_die_live_ansicht(qapp):
    fenster = MainWindow()
    gerufen = []
    fenster.ansichten["live"].stoppe = lambda: gerufen.append(True)
    fenster._verdrahte_code_stopp()          # erneut verdrahten, jetzt auf die Attrappe
    fenster.ansichten["code"].stopp_gewuenscht.emit()
    assert gerufen == [True]


def test_projekt_in_spotlab_oeffnen_wechselt_zur_code_ansicht(qapp, tmp_path):
    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._oeffne_in_code(projekt)
    assert fenster.stapel.currentWidget() is fenster.ansichten["code"]
    assert fenster.ansichten["code"].projektwahl.currentText() == "demo"
```

Und die zwei Helfer am Kopf derselben Datei:

```python
class _FakeProzess:
    """Eine Pipe, die sofort endet — der Leser darf nicht hängen bleiben."""

    stdout = iter(())

    def wait(self):
        return 0


def _lauf_verzeichnis(tmp_path):
    from spotlab.record.run import RunRecorder

    recorder = RunRecorder(tmp_path / "runs", tmp_path / "demo.py", backend="dryrun")
    recorder.finish("ok")
    return str(recorder.dir)
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_app.py -q
```

Erwartet: FAIL mit `AssertionError` bei `test_seitenleiste_hat_die_ansicht_code` und
`AttributeError: 'MainWindow' object has no attribute '_starte_leser'`.

- [ ] **Schritt 3: Umsetzen**

**`src/spotlab/gui/sidebar.py`** — der neue Eintrag steht direkt hinter „Projekte", weil der
Weg vom Projekt zum Code führt:

```python
EINTRAEGE = (
    ("projekte", "Projekte"),
    ("code", "Code"),
    ("live", "Live-Lauf"),
    ("laeufe", "Läufe"),
    ("karten", "Karten"),
    ("spot", "Spot"),
)
```

**`src/spotlab/gui/views/projects.py`** — Signal und Knopf:

```python
class ProjectsView(QWidget):
    lauf_gestartet = Signal(object, str)
    arbeitsordner_geaendert = Signal(str)
    projekt_oeffnen = Signal(object)
```

Im `__init__` neben `self.oeffnen_knopf`:

```python
        self.spotlab_knopf = QPushButton("In spotlab öffnen")
        self.spotlab_knopf.clicked.connect(self._oeffne_in_spotlab)
```

und in die Zeile `projektknoepfe`, **vor** `addStretch`:

```python
        projektknoepfe.addWidget(self.spotlab_knopf)
```

Dazu die Methode:

```python
    def _oeffne_in_spotlab(self):
        projekt = self._gewaehltes_projekt()
        if projekt is not None:
            self.projekt_oeffnen.emit(projekt)
```

**`src/spotlab/gui/app.py`** — Import ergänzen:

```python
from spotlab.gui.editor.view import EditorView
from spotlab.gui.theme import palette_fuer, stylesheet
```

Im `MainWindow.__init__` vor `self.ansichten`:

```python
        self._palette = palette_fuer(system_ist_dunkel())
        self._start_aus = None
```

Die Ansicht eintragen und in den Stapel legen:

```python
        self.ansichten = {
            "projekte": ProjectsView(
                editor_command=self._config.editor_command if self._config else "code"
            ),
            "code": EditorView(self._palette),
            "live": LiveView(),
            "laeufe": RunsView(),
            "karten": MapsView(),
            "spot": CheckupView(),
        }
        self.stapel = QStackedWidget()
        for schluessel in ("projekte", "code", "live", "laeufe", "karten", "spot"):
            self.stapel.addWidget(self.ansichten[schluessel])
```

In `_verdrahte` ergänzen:

```python
        self.ansichten["code"].lauf_gestartet.connect(self._lauf_aus_code)
        self.ansichten["code"].meldung.connect(self._melde)
        self.ansichten["projekte"].projekt_oeffnen.connect(self._oeffne_in_code)
        self._verdrahte_code_stopp()
```

Und die neuen Methoden:

```python
    def _verdrahte_code_stopp(self):
        """Eigene Methode, damit Tests nach dem Austausch von stoppe() neu verdrahten.

        Der Stopp-Knopf im Editor ruft NICHT eine zweite Kopie der Logik: der
        freundliche Stopp haengt am Lauf-Verzeichnis, das die Live-Ansicht vom
        Watcher bekommt. Delegation heisst dasselbe Objekt mit demselben Zustand.
        """
        self.ansichten["code"].stopp_gewuenscht.connect(
            lambda: self.ansichten["live"].stoppe()
        )

    def _starte_leser(self, prozess):
        """EIN Leser, zwei Senken.

        Ein zweiter OutputReader auf derselben Pipe teilte sich die Zeilen
        zufaellig mit dem ersten.
        """
        self._leser = OutputReader(prozess, self)
        self._leser.zeile.connect(self.ansichten["live"].zeige_ausgabe)
        self._leser.zeile.connect(self.ansichten["code"].zeige_ausgabe)
        self._leser.start()

    def _oeffne_in_code(self, projekt):
        self.ansichten["code"].setze_projekt(projekt)
        self._wechsle("code")
        self.leiste.waehle("code")

    def _lauf_aus_code(self, prozess, skript):
        # Kein Ansichtswechsel: wer aus „Code" startet, will dort bleiben.
        self._start_aus = "code"
        self._starte_leser(prozess)
```

`_lauf_gestartet` umbauen:

```python
    def _lauf_gestartet(self, prozess, skript):
        self._start_aus = "projekte"
        self._wechsle("live")
        self.leiste.waehle("live")
        self._starte_leser(prozess)
```

`_lauf_begonnen` bekommt die Bedingung:

```python
    def _lauf_begonnen(self, verzeichnis):
        skript = read_run(verzeichnis).skript
        name = Path(skript).name if skript else Path(verzeichnis).name
        self.ansichten["live"].setze_lauf(verzeichnis, name)
        # Auch bei einem von aussen gestarteten Lauf (F5 in VS Code) hinschalten —
        # sonst sieht der Schueler nicht, dass sein Programm laeuft. Wer aber
        # gerade selbst aus „Code" gestartet hat, wird nicht aus seiner Ansicht
        # geworfen.
        if self._start_aus == "code":
            return
        self._wechsle("live")
        self.leiste.waehle("live")
```

`_lauf_beendet` ergänzen:

```python
    def _lauf_beendet(self, verzeichnis):
        self.ansichten["live"].lauf_beendet()
        self.ansichten["code"].lauf_beendet()
        self.ansichten["laeufe"].aktualisiere()
        self.kopf.zeige_getrennt()
        self._start_aus = None
```

Und `_setze_arbeitsordner` ergänzen — direkt bei den anderen Ansichten:

```python
        self.ansichten["code"].setze_arbeitsordner(pfad or None)
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_app.py -q
python -m pytest -q
```

Erwartet: beide grün.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/sidebar.py src/spotlab/gui/app.py src/spotlab/gui/views/projects.py tests/test_gui_app.py
git commit -m "feat(gui): Ansicht Code verdrahtet, ein Leser mit zwei Senken"
```

---

## Aufgabe 14: Dokumentation und Abnahme

**Dateien:**
- Ändern: `CLAUDE.md`
- Ändern: `docs/ABNAHME.md`
- Test: keiner (Dokumentation)

- [ ] **Schritt 1: `CLAUDE.md` ergänzen**

Unter „Nicht verhandelbar" anhängen:

```markdown
- **`editor/` darf nichts aus `api/`, `backends/` oder `maps/` importieren und nichts
  ausserhalb der Standardbibliothek.** `api/spot.py` zieht über `motion`/`posture`/`state`/
  `perception` bosdyn, numpy und Pillow herein; für `editor/verbs.py` ist `api/spot.py`
  **Text, keine Schnittstelle**. Ein Import wäre der bequeme Weg zur Introspektion und
  ketten den Editor an das SDK. `tests/test_editor_verbs.py` hält das im Unterprozess fest.
- **Es gibt genau einen `OutputReader` pro Lauf.** Die Ausgabe-Pipe hat genau einen Leser;
  ein zweiter teilte sich die Zeilen zufällig mit dem ersten. Neue Ansichten hängen sich als
  weitere Senke an `_starte_leser`, nie mit einem eigenen Leser an den Prozess.
- **Der Stopp-Knopf im Editor delegiert an `LiveView.stoppe()`.** Dieselbe Funktion
  aufzurufen genügt nicht — der freundliche Stopp hängt am Lauf-Verzeichnis, das die
  Live-Ansicht vom Watcher bekommt.
```

Unter „Regeln" anhängen:

```markdown
- Der eingebaute Editor ist eine **Ergänzung**, kein Ersatz: `spotlab open` und „In VS Code
  öffnen" bleiben. Deshalb haben regelmässig beide Editoren dieselbe Datei offen — jeder
  Reiter merkt sich Änderungszeit und Grösse und fragt vor dem Überschreiben.
- Dateien schreibt der Editor mit `encoding="utf-8", newline="\n"`. Ohne das schreibt Python
  auf Windows CRLF, und jede Datei sieht nach dem ersten Speichern in git vollständig
  geändert aus.
```

Unter „Umsetzungsstand" den letzten Absatz ersetzen:

```markdown
Fundament (Stufe 1+2), GUI (Stufe 3), GraphNav (Stufe 4) und der eingebaute Editor
(Stufe 5) sind vollständig. Offen und bewusst nicht gebaut: MCP-Server, Sim-Adapter,
NN-Anbindung, Mehrbenutzer-Dienst, Arm und Docking. Im Editor bewusst nicht gebaut:
Debugger mit Haltepunkten, git-Integration, Erweiterungen, projektweite Suche.
```

- [ ] **Schritt 2: `docs/ABNAHME.md` ergänzen**

Vor dem Abschnitt „## Nach der Abnahme" einfügen:

```markdown
## A17 — Ein aus dem Editor gestarteter Lauf lässt sich genauso stoppen

**Prozedur** Ein Programm aus der Ansicht „Code" starten. Im ersten Durchgang „Stopp"
drücken, im zweiten den NOT-AUS in der Kopfleiste.

**Erwartung** „Stopp" setzt Spot hin wie bei einem Lauf aus „Projekte". Der NOT-AUS schaltet
die Motoren ab. Der Lauf erscheint danach in „Läufe", und die Ansicht springt beim Starten
**nicht** weg von „Code".

**Warum das trotz Delegation am Gerät geprüft wird:** ein zweiter Startweg, der beim
Anhalten anders reagiert, wäre die gefährlichste Art, diese Stufe falsch zu bauen. Dass der
Knopf dieselbe Methode desselben Objekts ruft, steht im Code — dass die Kette aus Watcher,
Lauf-Verzeichnis und Stopp-Markierung auch bei diesem Startweg vollständig geschlossen ist,
zeigt erst der Roboter.

**Ergebnis** _(offen)_

---
```

- [ ] **Schritt 3: Ganze Suite laufen lassen**

```bash
python -m pytest -q
```

Erwartet: alles grün.

- [ ] **Schritt 4: Aussehen auf einem echten Desktop prüfen**

```bash
python -m spotlab.gui.app
```

Falls das nicht als Modul startet: `spotlab gui`. **Im Offscreen-Modus gibt es keine
Schriften** — die Hervorhebung lässt sich nur hier beurteilen. Prüfen: Syntaxfarben in hell
und dunkel, Zeilenleiste, Fehlerkringel, Vorschlagsliste nach `spot.`, Klick auf eine
Traceback-Zeile.

- [ ] **Schritt 5: Committen**

```bash
git add CLAUDE.md docs/ABNAHME.md
git commit -m "docs: Editor-Regeln in CLAUDE.md, Abnahmepunkt A17"
```

---

## Selbstprüfung des Plans

**Abdeckung der Spec** — jeder Abschnitt hat eine Aufgabe:

| Spec | Aufgabe |
|---|---|
| §4.1 `editor/syntax.py` | 1 |
| §4.2 `editor/traceback.py` | 2 |
| §4.3 `editor/verbs.py` | 3, Docstrings in 5 |
| §4.4 Hervorhebung | 7 |
| §4.5 Palette | 6 |
| §4.6 Textfeld, Einrückung, Suche | 4, 8 |
| §4.7 Vervollständigung | 9 |
| §4.8 Dateibaum | 10 |
| §4.9 Ansicht „Code" | 11, 12 |
| §4.10 Anpassungen am Fenster | 13 |
| §6 Fehlerbehandlung | in 11 und 12 als Tests |
| §7 Prüfung | in jeder Aufgabe |
| §8 Abnahme A17 | 14 |
| §11 Abhängigkeiten | 7 (`pygments`), 9 (`jedi`) |

**Namen, die über Aufgaben hinweg gleich bleiben müssen:** `pruefe`, `Fehlerstelle`,
`finde_stellen`, `Stelle`, `Vorschlag`, `spot_verben`, `praefix`, `teilwort`,
`naechste_einrueckung`, `ausruecken`, `EINRUECKUNG`, `spannen`, `Hervorheber.neu_lexen`,
`CodeEdit.ruhe`, `CodeEdit.zeige_fehler`, `Vervollstaendigung.anfordern`,
`Dateibaum.datei_gewaehlt`, `EditorView.zeige_ausgabe`, `EditorView.lauf_beendet`,
`MainWindow._starte_leser`, `MainWindow._start_aus`.
