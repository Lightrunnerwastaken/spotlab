import pytest

from spotlab.errors import SpotlabError
from spotlab.welt.raum import Raum, raum_laden, vorlagen

BEISPIEL = '''
[raum]
name         = "Prüfraum"
beschreibung = "Nur zum Testen."
groesse      = [4.0, 3.0]
start        = [0.5, 0.5, 90.0]
waende = [
    [0.0, 0.0, 4.0, 0.0],
    [4.0, 0.0, 4.0, 3.0],
]
hindernisse = [
    { name = "Kiste", rechteck = [1.0, 1.0, 0.5, 0.5] },
]

[[tag]]
id = 7
pose = [3.9, 1.5, 180.0]
'''


def _schreibe(ordner, name, inhalt=BEISPIEL):
    raeume = ordner / "raeume"
    raeume.mkdir(parents=True, exist_ok=True)
    (raeume / f"{name}.toml").write_text(inhalt, encoding="utf-8")
    return ordner


def test_laedt_alle_felder(tmp_path):
    raum = raum_laden("pruefraum", workspace=_schreibe(tmp_path, "pruefraum"))
    assert isinstance(raum, Raum)
    assert raum.name == "Prüfraum"
    assert raum.groesse == (4.0, 3.0)
    assert raum.start == (0.5, 0.5, 90.0)
    assert len(raum.waende) == 2
    assert raum.hindernisse[0].name == "Kiste"
    assert raum.hindernisse[0].rechteck == (1.0, 1.0, 0.5, 0.5)
    assert raum.tags[0].id == 7
    assert raum.tags[0].grad == 180.0


def test_arbeitsordner_geht_vor_paket(tmp_path):
    """Eigene Raeume sollen die mitgelieferten ueberschreiben koennen."""
    eigen = BEISPIEL.replace('name         = "Prüfraum"', 'name         = "Eigener"')
    raum = raum_laden("leer", workspace=_schreibe(tmp_path, "leer", eigen))
    assert raum.name == "Eigener"


def test_ohne_arbeitsordner_kommt_die_vorlage():
    raum = raum_laden("leer")
    assert raum.name
    assert len(raum.waende) >= 4


def test_unbekannter_raum_nennt_die_vorhandenen():
    with pytest.raises(SpotlabError) as fehler:
        raum_laden("gibtsnicht")
    text = str(fehler.value)
    assert "gibtsnicht" in text
    assert "leer" in text and "moebliert" in text and "durchgang" in text


def test_fehlendes_feld_nennt_das_feld(tmp_path):
    ohne = BEISPIEL.replace("groesse      = [4.0, 3.0]\n", "")
    with pytest.raises(SpotlabError) as fehler:
        raum_laden("kaputt", workspace=_schreibe(tmp_path, "kaputt", ohne))
    assert "groesse" in str(fehler.value)


def test_kaputtes_toml_wird_uebersetzt(tmp_path):
    with pytest.raises(SpotlabError):
        raum_laden("murks", workspace=_schreibe(tmp_path, "murks", "das ist kein toml ["))


@pytest.mark.parametrize("name", ["leer", "moebliert", "durchgang"])
def test_jede_vorlage_ist_geometrisch_stimmig(name):
    """Was ohne kollision.py pruefbar ist. Die Frage, ob die Startpose FREI
    liegt, kommt in Task 2 dazu -- sie braucht den Roboterradius."""
    raum = raum_laden(name)
    breite, hoehe = raum.groesse
    x, y, _grad = raum.start
    assert 0 < x < breite and 0 < y < hoehe, "Start liegt ausserhalb"
    assert raum.tags, "jede Vorlage soll mindestens einen Tag haben"
    for tag in raum.tags:
        assert 0 <= tag.x <= breite and 0 <= tag.y <= hoehe


def test_vorlagen_nennt_die_drei():
    assert sorted(vorlagen()) == ["durchgang", "leer", "moebliert"]


# ------------------------------------------------------- die Schichtregel


def test_welt_importiert_nichts_verbotenes():
    """welt/ ist reine Geometrie. Ein Import aus backends/ oder api/ waere der
    Anfang eines Kreises, und Qt oder bosdyn machten es untestbar."""
    import ast
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "welt"
    verboten = ("bosdyn", "PySide6", "spotlab.backends", "spotlab.api", "spotlab.gui")
    for datei in wurzel.rglob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        namen = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                namen.update(t.name for t in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen.add(knoten.module)
        schlimm = [n for n in namen if any(n.startswith(v) for v in verboten)]
        assert not schlimm, f"{datei.name} importiert {schlimm}"


def test_nur_wahrnehmung_darf_numpy():
    """raum.py wird von der GUI importiert und bleibt deshalb leichtgewichtig.

    Ueber `ast`, nicht als Textsuche: der Docstring von raum.py ERWAEHNT numpy,
    um zu begruenden, warum es dort fehlt. Eine Substring-Pruefung schluege
    daran an und pruefte die Dokumentation statt des Codes.
    """
    import ast
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "welt"
    for datei in ("raum.py", "kollision.py"):
        pfad = wurzel / datei
        if not pfad.is_file():
            continue          # kollision.py kommt in Task 2 dazu
        namen = set()
        for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.Import):
                namen.update(t.name for t in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen.add(knoten.module)
        assert not [n for n in namen if n.split(".")[0] == "numpy"],             f"{datei} soll ohne numpy auskommen"
