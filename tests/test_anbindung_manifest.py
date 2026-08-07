import pytest

from spotlab.anbindung.manifest import (
    DATEINAME,
    ManifestFehler,
    als_json,
    aus_json,
    lies,
    skript_von,
)

VOLLSTAENDIG = """
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation des Spot"

[[skript]]
name = "Baseline, 20 Episoden"
datei = "scripts/experiment_baseline.py"
argumente = ["--episoden", "20", "--archiv"]
roboter = false
beschreibung = "Frontier-Exploration"

[[skript]]
name = "Fahrt auf dem echten Spot"
datei = "scripts/sdk_drive.py"
roboter = true
"""


def _projekt(tmp_path, inhalt=VOLLSTAENDIG):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "experiment_baseline.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / DATEINAME).write_text(inhalt, encoding="utf-8")
    return tmp_path


def test_liest_projekt_und_skripte(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert manifest.name == "matura-spot"
    assert manifest.beschreibung.startswith("MuJoCo")
    assert manifest.projekt == tmp_path.resolve()
    assert [s.name for s in manifest.skripte] == [
        "Baseline, 20 Episoden",
        "Fahrt auf dem echten Spot",
    ]


def test_pfade_werden_gegen_das_projekt_aufgeloest(tmp_path):
    manifest = lies(_projekt(tmp_path))
    erwartet = (tmp_path / "scripts" / "experiment_baseline.py").resolve()
    assert manifest.skripte[0].datei == erwartet
    assert manifest.skripte[0].datei.is_absolute()


def test_argumente_sind_ein_tupel(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert manifest.skripte[0].argumente == ("--episoden", "20", "--archiv")


def test_standardwerte(tmp_path):
    manifest = lies(_projekt(tmp_path))
    zweites = manifest.skripte[1]
    assert zweites.argumente == ()
    assert zweites.beschreibung == ""
    assert zweites.roboter is True
    assert manifest.skripte[0].roboter is False


def test_fehlende_datei(tmp_path):
    with pytest.raises(ManifestFehler) as fehler:
        lies(tmp_path)
    assert DATEINAME in str(fehler.value)
    assert str(tmp_path.resolve()) in str(fehler.value)


def test_kaputtes_toml_nennt_die_datei(tmp_path):
    (tmp_path / DATEINAME).write_text("[projekt\nname =", encoding="utf-8")
    with pytest.raises(ManifestFehler) as fehler:
        lies(tmp_path)
    assert DATEINAME in str(fehler.value)


def test_fehlender_projektname(tmp_path):
    with pytest.raises(ManifestFehler) as fehler:
        lies(_projekt(tmp_path, '[projekt]\nbeschreibung = "x"\n'))
    assert "name" in str(fehler.value)


def test_skript_ohne_datei_nennt_die_nummer(tmp_path):
    inhalt = '[projekt]\nname = "p"\n\n[[skript]]\nname = "eins"\n'
    with pytest.raises(ManifestFehler) as fehler:
        lies(_projekt(tmp_path, inhalt))
    text = str(fehler.value)
    assert "datei" in text and "1" in text


def test_argumente_muessen_texte_sein(tmp_path):
    inhalt = (
        '[projekt]\nname = "p"\n\n[[skript]]\nname = "eins"\n'
        'datei = "a.py"\nargumente = [1, 2]\n'
    )
    with pytest.raises(ManifestFehler) as fehler:
        lies(_projekt(tmp_path, inhalt))
    assert "argumente" in str(fehler.value)


def test_json_hin_und_zurueck(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert aus_json(als_json(manifest)) == manifest


def test_skript_von_findet_und_gibt_sonst_none(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert skript_von(manifest, "Baseline, 20 Episoden").roboter is False
    assert skript_von(manifest, "gibtsnicht") is None


def test_anbindung_ist_frei_von_sdk_und_qt():
    """Die Schichtregel als Test — auf IMPORTE geprüft, nicht auf Vorkommen.

    spotlab.errors ist erlaubt und erwünscht: SpotlabError ist der Fehlertyp,
    den CLI und GUI bereits abfangen.
    """
    import pathlib
    import re

    import spotlab.anbindung as paket

    wurzel = pathlib.Path(paket.__file__).parent
    muster = re.compile(
        r"^\s*(from|import)\s+"
        r"(bosdyn|PySide6|spotlab\.backends|spotlab\.api|spotlab\.maps|spotlab\.gui)",
        re.M,
    )
    verstoesse = [
        str(p) for p in wurzel.rglob("*.py") if muster.search(p.read_text(encoding="utf-8"))
    ]
    assert verstoesse == []
