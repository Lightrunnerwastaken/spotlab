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
    zahlen = [
        (spalte, laenge)
        for spalte, laenge, fmt in karte[0]
        if fmt.foreground().color().name() == DUNKEL.zahl
    ]
    assert zahlen == [(4, 1)]


def test_leerer_text_ergibt_leere_karte(qapp):
    assert spannen("", DUNKEL) == {}
