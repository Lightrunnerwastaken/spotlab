import pytest

from spotlab.anbindung.manifest import DATEINAME
from spotlab.anbindung.panel import (
    ARTEN,
    bild_erlaubt,
    entferne,
    lies,
    panels,
    pruefe_inhalt,
    schreibe,
)
from spotlab.anbindung.speicher import binde_an, panelordner
from spotlab.errors import SpotlabError

MANIFEST = '[projekt]\nname = "p"\n\n[[skript]]\nname = "s"\ndatei = "s.py"\n'
KENNZAHLEN = [{"name": "success", "wert": "95 %", "hinweis": "19 von 20"}]


@pytest.fixture()
def gebunden(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "fremd"
    projekt.mkdir()
    (projekt / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")
    return binde_an(arbeit, projekt)


def test_alle_fuenf_arten_sind_bekannt():
    assert ARTEN == ("kennzahlen", "tabelle", "reihe", "bild", "text")


def test_schreiben_und_lesen_im_kreis(gebunden):
    pfad = schreibe(gebunden, "baseline", "kennzahlen", "Baseline", KENNZAHLEN)
    panel = lies(pfad)
    assert panel.fehler is None
    assert panel.name == "baseline"
    assert panel.titel == "Baseline"
    assert panel.art == "kennzahlen"
    assert panel.inhalt == KENNZAHLEN
    assert panel.stand


def test_ueberschreiben_ersetzt(gebunden):
    schreibe(gebunden, "baseline", "kennzahlen", "Alt", KENNZAHLEN)
    schreibe(gebunden, "baseline", "kennzahlen", "Neu", KENNZAHLEN)
    assert [p.titel for p in panels(gebunden)] == ["Neu"]


def test_atomares_schreiben_laesst_keine_reste(gebunden):
    schreibe(gebunden, "baseline", "kennzahlen", "Baseline", KENNZAHLEN)
    assert list(panelordner(gebunden).glob("*.neu")) == []


def test_kaputtes_json_ergibt_ein_panel_mit_fehler(gebunden):
    """Ein halb geschriebenes Panel darf die Ansicht nicht leeren."""
    pfad = panelordner(gebunden) / "halb.json"
    pfad.write_text('{"titel": "abgeschnit', encoding="utf-8")
    panel = lies(pfad)
    assert panel.fehler is not None
    assert panel.name == "halb"


def test_ein_kaputtes_panel_laesst_die_anderen_stehen(gebunden):
    schreibe(gebunden, "gut", "kennzahlen", "Gut", KENNZAHLEN)
    (panelordner(gebunden) / "kaputt.json").write_text("{", encoding="utf-8")
    assert {p.name: p.fehler is None for p in panels(gebunden)} == {
        "gut": True,
        "kaputt": False,
    }


def test_unbekannte_art_nennt_die_bekannten(gebunden):
    pfad = panelordner(gebunden) / "fremd.json"
    pfad.write_text('{"art": "torte", "titel": "x", "inhalt": []}', encoding="utf-8")
    panel = lies(pfad)
    assert panel.fehler is not None
    assert "kennzahlen" in panel.fehler


@pytest.mark.parametrize(
    "art, inhalt",
    [
        ("kennzahlen", [{"name": "a", "wert": "1"}]),
        ("tabelle", {"spalten": ["a"], "zeilen": [["1"]]}),
        ("reihe", {"x": [0, 1], "y": [1.0, 2.0], "x_name": "t", "y_name": "v"}),
        ("bild", {"pfad": "out/bild.png"}),
        ("text", {"absaetze": ["hallo"]}),
    ],
)
def test_gueltige_inhalte(art, inhalt):
    assert pruefe_inhalt(art, inhalt) is None


@pytest.mark.parametrize(
    "art, inhalt",
    [
        ("kennzahlen", {"name": "a"}),
        ("kennzahlen", [{"wert": "1"}]),
        ("tabelle", {"spalten": ["a"]}),
        ("tabelle", {"spalten": ["a", "b"], "zeilen": [["1"]]}),
        ("reihe", {"x": [0, 1], "y": [1.0]}),
        ("bild", {}),
        ("text", {"absaetze": "kein Liste"}),
    ],
)
def test_ungueltige_inhalte_werden_benannt(art, inhalt):
    grund = pruefe_inhalt(art, inhalt)
    assert grund and isinstance(grund, str)


def test_schreiben_mit_ungueltigem_inhalt_wirft(gebunden):
    with pytest.raises(SpotlabError):
        schreibe(gebunden, "x", "tabelle", "X", {"spalten": ["a"]})


def test_bild_aus_dem_projekt_ist_erlaubt(gebunden):
    ziel = gebunden.quelle / "out" / "bild.png"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(b"\x89PNG")
    assert bild_erlaubt(ziel, gebunden) is True


def test_bild_aus_dem_anbindungsordner_ist_erlaubt(gebunden):
    ziel = gebunden.ordner / "eigen.png"
    ziel.write_bytes(b"\x89PNG")
    assert bild_erlaubt(ziel, gebunden) is True


def test_bild_von_ausserhalb_ist_verboten(gebunden, tmp_path):
    """Eine Datei, die sagt „zeig das hier", darf nicht auf Beliebiges deuten."""
    fremd = tmp_path / "geheim.png"
    fremd.write_bytes(b"\x89PNG")
    assert bild_erlaubt(fremd, gebunden) is False


def test_entfernen(gebunden):
    schreibe(gebunden, "weg", "kennzahlen", "Weg", KENNZAHLEN)
    assert entferne(gebunden, "weg") is True
    assert entferne(gebunden, "weg") is False


def test_panelname_kann_nicht_ausbrechen(gebunden):
    pfad = schreibe(gebunden, "../../weg", "kennzahlen", "X", KENNZAHLEN)
    assert pfad.parent == panelordner(gebunden)


# ============ S4.6 die Wegpruefung gehoert an den Schreiber, nicht nur an die Anzeige


def test_ein_bild_von_ausserhalb_wird_gar_nicht_erst_geschrieben(gebunden, tmp_path):
    """Vorher: schreibe() nahm jeden Pfad an und meldete „ok".

    Erst die GUI zeigte Tage spaeter eine Warnung statt des Bildes -- ohne zu
    sagen, welches Werkzeug den Pfad geschrieben hatte. Der Schreiber ist die
    einzige Stelle, an der jemand den Fehler noch beheben kann.
    """
    fremd = tmp_path / "geheim.png"
    fremd.write_bytes(b"\x89PNG")
    with pytest.raises(SpotlabError) as fehler:
        schreibe(gebunden, "b", "bild", "B", {"pfad": str(fremd)})
    assert "ausserhalb" in str(fehler.value)
    assert not (panelordner(gebunden) / "b.json").exists()


def test_ein_bild_aus_dem_projekt_wird_geschrieben(gebunden):
    ziel = gebunden.quelle / "out" / "bild.png"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(b"\x89PNG")
    pfad = schreibe(gebunden, "b", "bild", "B", {"pfad": str(ziel)})
    assert pfad.exists()
