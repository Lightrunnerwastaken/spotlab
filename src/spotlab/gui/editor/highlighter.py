"""Syntaxhervorhebung ueber pygments.

Bewusst NICHT zeilenweise: dreifach zitierte Zeichenketten laufen ueber
mehrere Zeilen, und ein zeilenweiser Hervorheber faerbt ab dem ersten
Docstring den halben Rest der Datei gruen. Deshalb lext dieses Modul das ganze
Dokument und legt eine Karte Blocknummer -> Spannen an; highlightBlock
schlaegt darin nur nach. Ein Schuelerskript hat 50-300 Zeilen; das kostet nichts.
"""

import bisect

from pygments.lexers import PythonLexer
from pygments.token import Comment, Keyword, Name, Number, String
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


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
        for spalte, laenge, fmt in self._karte.get(self.currentBlock().blockNumber(), ()):
            self.setFormat(spalte, laenge, fmt)
