"""`ansicht.json`: der Schalter der GUI fuer den Blick des Laufs.

Derselbe Weg wie `fahrt.json` -- die GUI schreibt, der Laufprozess liest, die
Platte ist der einzige Kanal. Mit EINEM bewusst anderen Verhalten: ein
Fahrbefehl VERFAELLT (losgelassene Taste, eingeschlafene GUI heissen Stopp),
ein Schalter darf das nicht. Wer eine halbe Stunde geradeaus faehrt, ohne eine
Taste zu bewegen, soll die Kaesten nicht verlieren.
"""

from spotlab.record import ansicht


def test_schreiben_und_lesen(tmp_path):
    ansicht.schreibe(tmp_path, gesicht=True)
    assert (tmp_path / ansicht.DATEI).is_file()
    assert ansicht.lies(tmp_path) is True
    assert not list(tmp_path.glob("*.tmp")), "atomar geschrieben, nichts bleibt liegen"

    ansicht.schreibe(tmp_path, gesicht=False)
    assert ansicht.lies(tmp_path) is False


def test_ohne_datei_ist_die_erkennung_aus(tmp_path):
    """Die Vorgabe. Ein Lauf ohne Schalter kostet keine Rechenzeit."""
    assert ansicht.lies(tmp_path) is False


def test_eine_kaputte_datei_heisst_aus(tmp_path):
    """Halb geschrieben oder von Hand verpfuscht: nicht werfen, nur nicht erkennen.
    Ein Blick, der an einer Schalterdatei stirbt, waere schlimmer als keine Kaesten."""
    (tmp_path / ansicht.DATEI).write_text("{kaputt", encoding="utf-8")
    assert ansicht.lies(tmp_path) is False
    (tmp_path / ansicht.DATEI).write_text('{"gesicht": "vielleicht"}', encoding="utf-8")
    assert ansicht.lies(tmp_path) is False
    (tmp_path / ansicht.DATEI).write_text("[]", encoding="utf-8")
    assert ansicht.lies(tmp_path) is False


def test_zwei_schalter_in_einer_datei(tmp_path):
    """Gesicht und Hand reisen zusammen: eine Datei, ein Lesen je Bild im Blick."""
    ansicht.schreibe(tmp_path, gesicht=False, hand=True)
    assert ansicht.schalter(tmp_path) == {"gesicht": False, "hand": True}
    assert ansicht.lies(tmp_path) is False, "`lies` bleibt der Gesichtsschalter"
    ansicht.schreibe(tmp_path, gesicht=True, hand=True)
    assert ansicht.schalter(tmp_path) == {"gesicht": True, "hand": True}


def test_eine_datei_ohne_handschalter_heisst_hand_aus(tmp_path):
    """Aeltere Dateien tragen nur `gesicht`; kaputte gar nichts -- beides heisst aus, nie werfen."""
    (tmp_path / ansicht.DATEI).write_text('{"gesicht": true}', encoding="utf-8")
    assert ansicht.schalter(tmp_path) == {"gesicht": True, "hand": False}
    (tmp_path / ansicht.DATEI).write_text("{kaputt", encoding="utf-8")
    assert ansicht.schalter(tmp_path) == {"gesicht": False, "hand": False}
    assert ansicht.schalter(tmp_path / "fehlt") == {"gesicht": False, "hand": False}
    (tmp_path / ansicht.DATEI).write_text('{"gesicht": true, "hand": "ja"}', encoding="utf-8")
    assert ansicht.schalter(tmp_path)["hand"] is False, "nur ein echtes true zaehlt"


def test_der_schalter_verfaellt_nicht(tmp_path):
    """Der Unterschied zu `fahrt.json`, und der Grund, warum es eine eigene Datei ist.

    `fahrt.lies` gibt nach TOTMANN_S Stillstand zurueck -- das ist dort richtig
    und rettet den Roboter. Hier waere es falsch: der Schalter traegt keine Zeit,
    also kann er auch nicht veralten.
    """
    ansicht.schreibe(tmp_path, gesicht=True)
    inhalt = (tmp_path / ansicht.DATEI).read_text(encoding="utf-8")
    assert "t" not in __import__("json").loads(inhalt), "keine Zeitmarke, kein Verfall"
    assert ansicht.lies(tmp_path) is True
