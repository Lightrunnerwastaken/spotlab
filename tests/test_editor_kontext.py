"""Wo steht der Cursor? Ohne Fenster geprueft -- `editor/` ist Qt-frei.

Der Editor fragt jedi bei jedem Tastendruck. Ohne diese Unterscheidung schlaegt
er auch im Kommentar (158 globale Namen) und in einer offenen Zeichenkette
(Verzeichnisse des Laptops) vor -- beides am 09.09.2026 gemessen.
"""

import pytest

from spotlab.editor.kontext import CODE, KOMMENTAR, ZEICHENKETTE, im_code, ort, stelle_passt


@pytest.mark.parametrize("text, erwartet", [
    ("spot.mo", CODE),
    ("", CODE),
    ("x = 1\ny = ", CODE),
    ("# ein Kommentar mit spot.", KOMMENTAR),
    ("x = 1  # Notiz", KOMMENTAR),
    ("# Kommentar\nspot.", CODE),                     # der Kommentar endet an der Zeile
    ('pfad = "C:/Users/', ZEICHENKETTE),
    ("name = 'Kue", ZEICHENKETTE),
    ('x = "fertig"\nspot.', CODE),                    # geschlossen, dann Code
    ('x = f"{wert}"\nspot.', CODE),
    ('x = "mit \\" drin', ZEICHENKETTE),              # maskiertes Anfuehrungszeichen
    ('x = "C:\\\\"\nspot.', CODE),                    # Backslash am Ende, dann geschlossen
])
def test_ort_erkennt_code_kommentar_und_zeichenkette(text, erwartet):
    assert ort(text) == erwartet


def test_ein_docstring_zaehlt_bis_zu_seinem_ende():
    """Die Stelle, an der ein Schueler am laengsten Prosa schreibt."""
    assert ort('"""Fahre zum Fenster und ') == ZEICHENKETTE
    assert ort('"""Fahre zum Fenster."""\nimport ma') == CODE
    assert ort("'''noch offen\nueber zwei Zeilen") == ZEICHENKETTE


def test_ein_rautenzeichen_in_einer_zeichenkette_ist_kein_kommentar():
    """Hier ist der Automat genauer als die grobe Regel in `verbs.praefix`."""
    assert ort('print("# kein Kommentar")\nspot.') == CODE
    assert ort('print("# kein Kommentar') == ZEICHENKETTE


def test_ein_anfuehrungszeichen_in_einem_kommentar_oeffnet_nichts():
    assert ort('# er sagte "hallo\nspot.') == CODE


def test_eine_einzeilige_zeichenkette_endet_an_der_zeile():
    """Fuer Python ein Fehler; wer den Rest der Datei als Zeichenkette naehme,
    schaltete die Vorschlaege bis zum Dateiende ab."""
    assert ort('x = "vergessen\nspot.') == CODE


def test_im_code_ist_die_kurzform():
    assert im_code("spot.") is True
    assert im_code("# nein") is False


@pytest.mark.parametrize("zeile, erwartet", [
    ("spot.", True),                 # nach dem Punkt: gerade dort will man sie
    ("math.sq", True),
    ("zahlen.", True),
    ("pri", True),
    ("pr", True),
    ("p", False),                    # ein Buchstabe oeffnet keine Liste
    ("", False),
    ("    ", False),
    ("x = ", False),
    ("x = 1 + ", False),
])
def test_stelle_passt_wiegt_punkt_gegen_wortlaenge(zeile, erwartet):
    assert stelle_passt(zeile) is erwartet


def test_die_mindestlaenge_ist_einstellbar():
    assert stelle_passt("p", mindestzeichen=1) is True
    assert stelle_passt("prin", mindestzeichen=5) is False
    assert stelle_passt("spot.", mindestzeichen=5) is True, "der Punkt schlaegt die Laenge"


def test_nur_die_letzte_zeile_zaehlt_fuer_die_stelle():
    assert stelle_passt("import math\nmath.") is True
    assert stelle_passt("import math\np") is False
