import re
from dataclasses import fields

from spotlab.gui.theme import DUNKEL, HELL, palette_fuer, stylesheet

# Aus der Dataclass abgeleitet statt abgeschrieben: eine neue Farbe soll nicht
# stillschweigend an der Vollstaendigkeitspruefung vorbeikommen.
FELDER = tuple(f.name for f in fields(DUNKEL))
SYNTAXFELDER = ("schluesselwort", "zeichenkette", "kommentar", "zahl", "funktion")


def test_beide_paletten_sind_vollstaendig():
    for palette in (DUNKEL, HELL):
        for feld in FELDER:
            wert = getattr(palette, feld)
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", wert), f"{feld}={wert!r}"


def test_auswahl_folgt_dem_schalter():
    assert palette_fuer(True) is DUNKEL
    assert palette_fuer(False) is HELL


def test_paletten_unterscheiden_sich():
    assert DUNKEL.hintergrund != HELL.hintergrund
    assert DUNKEL.text != HELL.text


def test_stylesheet_enthaelt_nur_farben_der_palette():
    """Keine Farbliterale im Widget-Code — sonst bricht der zweite Modus."""
    text = stylesheet(DUNKEL)
    erlaubt = {getattr(DUNKEL, f).lower() for f in FELDER}
    gefunden = {t.lower() for t in re.findall(r"#[0-9a-fA-F]{6}", text)}
    assert gefunden <= erlaubt, f"fremde Farben: {gefunden - erlaubt}"


def test_stylesheet_ist_fuer_beide_paletten_baubar():
    assert len(stylesheet(HELL)) > 100
    assert stylesheet(HELL) != stylesheet(DUNKEL)


def test_beide_paletten_haben_die_syntaxfarben():
    for palette in (DUNKEL, HELL):
        for feld in SYNTAXFELDER:
            assert feld in FELDER
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", getattr(palette, feld))


def test_syntaxfarben_sind_unterscheidbar():
    for palette in (DUNKEL, HELL):
        farben = {getattr(palette, feld) for feld in SYNTAXFELDER}
        assert len(farben) == 5              # keine zwei Token sehen gleich aus
        assert palette.text not in farben    # und keine faellt mit dem Fliesstext zusammen


def test_theme_ist_qt_frei():
    """Die Palettenwahl muss ohne Fenster prüfbar bleiben."""
    import pathlib

    import spotlab.gui.theme as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in quelle
