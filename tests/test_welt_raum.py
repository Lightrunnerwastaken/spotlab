import pytest

from spotlab.errors import SpotlabError
from spotlab.welt.raum import (
    Block,
    Raum,
    RaumTag,
    Wand,
    eigene_raeume,
    huelle,
    raum_laden,
    raum_laden_pfad,
    raum_pfad,
    raum_speichern,
    vorlagen,
)

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
    assert raum.bloecke[0].name == "Kiste"
    assert (raum.bloecke[0].x, raum.bloecke[0].y) == (1.25, 1.25)   # Mitte des Rechtecks
    assert (raum.bloecke[0].breite, raum.bloecke[0].tiefe) == (0.5, 0.5)
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
    # `groesse` ist seit Fassung 2 optional (Huelle); `start` bleibt Pflicht.
    ohne = BEISPIEL.replace("start        = [0.5, 0.5, 90.0]\n", "")
    with pytest.raises(SpotlabError) as fehler:
        raum_laden("kaputt", workspace=_schreibe(tmp_path, "kaputt", ohne))
    assert "start" in str(fehler.value)


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


def test_vorlagen_nennt_die_vier():
    assert sorted(vorlagen()) == ["durchgang", "leer", "moebliert", "physik_einzelstufe", "physik_treppe_3stufen", "treppe"]


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


# ------------------------------------------------------------- Fassung 2


def test_alte_hindernisse_werden_zu_bloecken():
    raum = raum_laden("moebliert")
    tisch = next(b for b in raum.bloecke if b.name == "Tisch")
    # rechteck = [2.5, 1.4, 1.2, 0.8]: Mitte = Ecke + halbe Kante, tischhoch, ungedreht
    assert (tisch.x, tisch.y) == (pytest.approx(3.1), pytest.approx(1.8))
    assert (tisch.breite, tisch.tiefe, tisch.hoehe, tisch.drehung) == (1.2, 0.8, 0.75, 0.0)
    assert not hasattr(raum, "hindernisse")


def test_waende_sind_waende_auch_aus_tupeln():
    raum = Raum(name="T", beschreibung="", start=(0, 0, 0), waende=((0, 0, 2, 0),))
    wand = raum.waende[0]
    assert isinstance(wand, Wand)
    assert list(wand) == [0.0, 0.0, 2.0, 0.0]          # entpackbar wie bisher
    assert wand.laenge == pytest.approx(2.0)
    assert wand.mitte == (1.0, 0.0)
    assert wand.winkel == pytest.approx(0.0)


def test_block_ecken_drehen_mit():
    block = Block("K", 1.0, 1.0, 2.0, 1.0, drehung=90.0)
    ecken = block.ecken()
    # 2 m breit entlang der eigenen x-Achse, die jetzt nach +y zeigt
    assert ecken[0] == (pytest.approx(1.5), pytest.approx(0.0))
    assert ecken[2] == (pytest.approx(0.5), pytest.approx(2.0))
    assert block.lokal(1.0, 2.0) == (pytest.approx(1.0), pytest.approx(0.0))


def test_groesse_ist_optional_und_die_huelle_folgt_der_geometrie():
    raum = Raum(name="T", beschreibung="", start=(0.5, 0.5, 0.0),
                waende=((0, 0, 4, 0),), bloecke=(Block("K", 2, 3, 1, 1),))
    assert raum.groesse is None
    assert huelle(raum) == (-0.5, -0.5, 4.5, 4.0)          # Huelle + RAND_M
    mit = raum_laden("leer")
    assert huelle(mit) == (0.0, 0.0, mit.groesse[0], mit.groesse[1])


def test_neue_schreibweise_laedt_bloecke_und_taghoehe(tmp_path):
    (tmp_path / "raeume").mkdir()
    (tmp_path / "raeume" / "neu.toml").write_text(
        '[raum]\nname = "Neu"\nstart = [1.0, 1.0, 0.0]\nwand_dicke = 0.1\n'
        'waende = [[0.0, 0.0, 3.0, 0.0]]\n'
        '[[block]]\nname = "Regal"\nmitte = [2.0, 1.0]\ngroesse = [1.0, 0.4, 1.8]\ndrehung = 30\n'
        '[[tag]]\nid = 7\npose = [2.5, 0.2, 90.0]\nhoehe = 0.5\n',
        encoding="utf-8",
    )
    raum = raum_laden("neu", workspace=tmp_path)
    assert raum.wand_dicke == 0.1 and raum.wand_hoehe == 1.0
    assert raum.bloecke == (Block("Regal", 2.0, 1.0, 1.0, 0.4, 1.8, 30.0),)
    assert raum.tags == (RaumTag(7, 2.5, 0.2, 90.0, 0.5),)
    assert raum.groesse is None


def test_block_ohne_mitte_nennt_das_feld(tmp_path):
    (tmp_path / "raeume").mkdir()
    (tmp_path / "raeume" / "kaputt.toml").write_text(
        '[raum]\nname = "K"\nstart = [1.0, 1.0, 0.0]\n[[block]]\nname = "R"\ngroesse = [1, 1, 1]\n',
        encoding="utf-8",
    )
    with pytest.raises(SpotlabError, match="mitte"):
        raum_laden("kaputt", workspace=tmp_path)


@pytest.mark.parametrize("name", vorlagen())
def test_speichern_und_laden_ist_eine_rundreise(name, tmp_path):
    raum = raum_laden(name)
    pfad = raum_pfad(tmp_path, name)
    raum_speichern(raum, pfad)
    assert pfad == tmp_path / "raeume" / f"{name}.toml"
    wieder = raum_laden(name, workspace=tmp_path)
    assert wieder == raum
    text = pfad.read_text(encoding="utf-8")
    assert "[[block]]" in text or not raum.bloecke
    assert "hindernisse" not in text                      # immer die neue Form


def test_eigene_raeume_listet_den_arbeitsordner(tmp_path):
    assert eigene_raeume(tmp_path) == []
    raum_speichern(raum_laden("leer"), raum_pfad(tmp_path, "mein zimmer"))
    assert eigene_raeume(tmp_path) == ["mein zimmer"]
    assert eigene_raeume(None) == []


def test_speichern_schreibt_lf_und_utf8(tmp_path):
    raum = Raum(name="Ä", beschreibung='sagt "hallo"', start=(0, 0, 0))
    pfad = raum_pfad(tmp_path, "ae")
    raum_speichern(raum, pfad)
    roh = pfad.read_bytes()
    assert b"\r\n" not in roh
    assert raum_laden("ae", workspace=tmp_path).beschreibung == 'sagt "hallo"'


# ------------------------------------------------------------- Fassung 3: Hoehe


def test_ein_boden_ist_podest_rampe_oder_treppe_und_kennt_seine_hoehe():
    import math

    from spotlab.welt.raum import Boden

    podest = Boden("P", 2, 2, 2, 1, z=1.2)
    rampe = Boden("R", 2, 2, 2, 1, z=0.0, anstieg=1.0)
    treppe = Boden("T", 2, 2, 2, 1, z=0.0, anstieg=1.0, stufen=5)
    assert (podest.art, rampe.art, treppe.art) == ("podest", "rampe", "treppe")
    assert rampe.hoehe_lokal(-1.0) == pytest.approx(0.0)
    assert rampe.hoehe_lokal(0.0) == pytest.approx(0.5)
    assert rampe.hoehe_lokal(1.0) == pytest.approx(1.0)
    assert treppe.stufe_lokal(-0.99) == pytest.approx(0.2)      # erste Trittflaeche
    assert treppe.stufe_lokal(0.99) == pytest.approx(1.0)
    assert podest.stufe_lokal(0.3) == pytest.approx(1.2)         # ohne Stufen: die Flaeche
    assert rampe.neigung_grad == pytest.approx(math.degrees(math.atan(0.5)))
    assert podest.neigung_grad == 0.0
    assert treppe.z_oben == pytest.approx(1.0)
    gedreht = Boden("G", 0, 0, 2, 1, drehung=90.0)
    assert gedreht.lokal(0.0, 1.0)[0] == pytest.approx(1.0)      # +y der Welt ist +x des Bodens


def test_v3_geht_rund_und_ein_raum_ohne_hoehe_sieht_aus_wie_v2(tmp_path):
    from spotlab.welt.raum import Boden, raum_laden_pfad

    raum = Raum(name="H", beschreibung="", start=(1, 1, 0),
                waende=(Wand(0, 0, 4, 0), Wand(0, 3, 4, 3, z=1.2)),
                bloecke=(Block("K", 2, 2, 1, 1, z=1.2),),
                tags=(RaumTag(3, 3, 3, 90.0, z=1.2),),
                boeden=(Boden("T", 2, 1, 2, 1, anstieg=1.2, stufen=7),))
    raum_speichern(raum, tmp_path / "h.toml")
    assert raum_laden_pfad(tmp_path / "h.toml") == raum
    flach = Raum(name="F", beschreibung="", start=(1, 1, 0), waende=((0, 0, 4, 0),))
    raum_speichern(flach, tmp_path / "f.toml")
    text = (tmp_path / "f.toml").read_text(encoding="utf-8")
    assert "boden" not in text and "\nz " not in text and "[0.0, 0.0, 4.0, 0.0]" in text


def test_alte_dateien_bekommen_z_null():
    raum = raum_laden("moebliert")
    assert all(w.z == 0.0 for w in raum.waende) and all(b.z == 0.0 for b in raum.bloecke)
    assert raum.boeden == () and all(t.z == 0.0 for t in raum.tags)


def test_die_huelle_nimmt_boeden_mit():
    from spotlab.welt.raum import Boden

    raum = Raum(name="H", beschreibung="", start=(0, 0, 0), boeden=(Boden("P", 5, 5, 2, 2),))
    assert huelle(raum)[2] == pytest.approx(6.5) and huelle(raum)[3] == pytest.approx(6.5)


def test_die_stufenkonstanten_passen_zusammen():
    from spotlab.welt.raum import MAX_STUFE_M, STUFE_VORGABE_M

    assert 0.0 < STUFE_VORGABE_M < MAX_STUFE_M


# ------------------------------------------------------------- Fassung 4: Gelaende


def test_raum_mit_gelaende_speichert_fassung_4_und_datei(tmp_path):
    from spotlab.welt import gelaende as g
    ge = g.gitter(0.0, 0.0, 0.5, 3, 3, lambda x, y: 0.3)
    raum = Raum("G", "", (1.0, 1.0, 0.0), waende=[(0, 0, 3, 0)], gelaende=ge)
    pfad = tmp_path / "g.toml"
    raum_speichern(raum, pfad)
    text = pfad.read_text(encoding="utf-8")
    assert "fassung      = 4" in text and '[gelaende]\ndatei = "g.gelaende"' in text
    assert (tmp_path / "g.gelaende").is_file()
    zurueck = raum_laden_pfad(pfad)
    assert zurueck.gelaende.knoten(1, 1) == pytest.approx(0.3)


def test_ohne_gelaende_keine_spur_und_alte_datei_weg(tmp_path):
    (tmp_path / "g.gelaende").write_bytes(b"x")
    raum_speichern(Raum("G", "", (1.0, 1.0, 0.0), waende=[(0, 0, 3, 0)]), tmp_path / "g.toml")
    assert "gelaende" not in (tmp_path / "g.toml").read_text(encoding="utf-8")
    assert not (tmp_path / "g.gelaende").exists()


def test_fehlende_gelaende_datei_ist_ein_klarer_fehler(tmp_path):
    (tmp_path / "g.toml").write_text(
        '[raum]\nname = "G"\nstart = [1.0, 1.0, 0.0]\nwaende = []\n\n[gelaende]\ndatei = "g.gelaende"\n',
        encoding="utf-8")
    with pytest.raises(SpotlabError, match="Gelände-Datei"):
        raum_laden_pfad(tmp_path / "g.toml")


def test_die_huelle_nimmt_das_gelaende_mit():
    from spotlab.welt import gelaende as g
    from spotlab.welt.raum import RAND_M
    ge = g.gitter(5.0, 5.0, 1.0, 2, 2, lambda x, y: 0.0)
    raum = Raum("G", "", (1.0, 1.0, 0.0), gelaende=ge)
    assert huelle(raum)[2] >= 6.0 + RAND_M - 1e-9 and huelle(raum)[3] >= 6.0 + RAND_M - 1e-9
