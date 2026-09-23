import pytest

pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("pygments")

from spotlab.gui.editor.highlighter import spannen  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402


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
    zahlen = [
        (spalte, laenge)
        for spalte, laenge, fmt in karte[0]
        if fmt.foreground().color().name() == DUNKEL.zahl
    ]
    assert zahlen == [(4, 1)]


def test_leerer_text_ergibt_leere_karte(qapp):
    assert spannen("", DUNKEL) == {}


def test_ein_zeilentrenner_verschiebt_die_zeilen_nicht(qapp):
    """toPlainText() macht aus U+2028 einen Zeilenumbruch -- die Karte zaehlte
    dann eine Zeile mehr als das Dokument Bloecke, und ab dort sass jede Farbe
    eine Zeile zu tief."""
    from PySide6.QtGui import QTextDocument

    from spotlab.gui.editor.highlighter import Hervorheber

    dokument = QTextDocument()
    dokument.setPlainText('s = "a\u2028b"\nx = 1\n')
    hervorheber = Hervorheber(dokument, DUNKEL)
    hervorheber.neu_lexen()
    assert DUNKEL.zahl in _farben(hervorheber._karte, 1)


# ================= Emojis ausserhalb der BMP (Pruefung 23.09.2026, p15)
#
# pygments zaehlt Python-Zeichen, QSyntaxHighlighter.setFormat UTF-16-Einheiten.
# Nach drei Robotern in einer Zeichenkette sass die Kommentarfarbe drei
# Positionen zu frueh -- mitten im Code davor.

ROBOTER = chr(0x1F916)


def test_spalten_nach_einem_emoji_zaehlen_utf16(qapp):
    zeile = f'print("{ROBOTER * 3}")  # Kommentar\n'
    karte = spannen(zeile, DUNKEL)
    def spannen_in(farbe):
        return [(s, n) for s, n, fmt in karte[0] if fmt.foreground().color().name() == farbe]

    assert spannen_in(DUNKEL.kommentar) == [(17, 11)]            # Python zaehlt hier 14
    # pygments liefert die Zeichenkette in drei Teilen: ", drei Emojis (6), "
    assert spannen_in(DUNKEL.zeichenkette) == [(6, 1), (7, 6), (13, 1)]


def test_im_dokument_sitzt_die_kommentarfarbe_auf_dem_kommentar(qapp):
    from PySide6.QtGui import QColor, QTextDocument

    from spotlab.gui.editor.highlighter import Hervorheber

    dokument = QTextDocument()
    dokument.setPlainText(f'print("{ROBOTER * 3}")  # Kommentar\n')
    hervorheber = Hervorheber(dokument, DUNKEL)
    hervorheber.neu_lexen()
    block = dokument.firstBlock()
    u16 = block.text().encode("utf-16-le")
    gefaerbt = [u16[2 * f.start:2 * (f.start + f.length)].decode("utf-16-le")
                for f in block.layout().formats()
                if f.format.foreground().color() == QColor(DUNKEL.kommentar)]
    assert gefaerbt == ["# Kommentar"]
