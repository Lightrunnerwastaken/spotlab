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


# ================================== S2.12 Tabs und Kommentare in der Einrueckung


def test_tabs_zaehlen_als_einrueckung():
    """`lstrip(" ")` sah einen Tab nicht -- eine mit Tabs eingerueckte Datei
    (VS Code, fremder Code) verlor bei jedem Zeilenumbruch ihre Ebene."""
    assert einrueckung_von("\tx = 1") == "\t"
    assert einrueckung_von("\t\tx = 1") == "\t\t"
    assert einrueckung_von("  \tx = 1") == "  \t"


def test_naechste_einrueckung_haelt_die_tab_ebene():
    assert naechste_einrueckung("\tif x:") == "\t" + EINRUECKUNG
    assert naechste_einrueckung("\t\tx = 1") == "\t\t"


def test_ein_doppelpunkt_im_kommentar_rueckt_nicht_ein():
    """`# und dann:` endet auf einem Doppelpunkt und ist trotzdem kein Block."""
    assert naechste_einrueckung("x = 1  # und dann:") == ""
    assert naechste_einrueckung("    y = 2  # Achtung:") == "    "


def test_ein_doppelpunkt_in_einer_zeichenkette_rueckt_nicht_ein():
    assert naechste_einrueckung('s = "gilt hier:"') == ""


def test_echte_bloecke_ruecken_weiterhin_ein():
    assert naechste_einrueckung("if x:") == EINRUECKUNG
    assert naechste_einrueckung("def f():  # Kommentar") == EINRUECKUNG


def test_ausruecken_kennt_den_tab():
    assert ausruecken("\tx = 1") == 1
    assert ausruecken("        x = 1") == len(EINRUECKUNG)
