import pytest

from spotlab.editor.indent import (
    EINRUECKUNG,
    ausruecken,
    einrueckung_von,
    naechste_einrueckung,
)


def test_einrueckung_ist_vier_leerzeichen():
    assert EINRUECKUNG == "    "


@pytest.mark.parametrize(
    "zeile, erwartet",
    [("x = 1", ""), ("    x = 1", "    "), ("        x = 1", "        "), ("", "")],
)
def test_einrueckung_von(zeile, erwartet):
    assert einrueckung_von(zeile) == erwartet


@pytest.mark.parametrize(
    "zeile, erwartet",
    [
        ("x = 1", ""),
        ("    x = 1", "    "),
        ("def f():", "    "),
        ("    if True:", "        "),
        ("    if True:   ", "        "),   # Leerzeichen hinter dem Doppelpunkt
        ("d = {'a': 1}", ""),              # Doppelpunkt nicht am Zeilenende
    ],
)
def test_naechste_einrueckung(zeile, erwartet):
    assert naechste_einrueckung(zeile) == erwartet


@pytest.mark.parametrize(
    "zeile, erwartet",
    [("        x", 4), ("    x", 4), ("  x", 2), ("x", 0), ("", 0)],
)
def test_ausruecken(zeile, erwartet):
    assert ausruecken(zeile) == erwartet
