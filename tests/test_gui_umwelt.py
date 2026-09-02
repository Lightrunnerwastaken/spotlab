"""Die Ansicht „Umwelt" — liest Dateien, spricht nie mit einem Roboter."""

import io
import json
from pathlib import Path

import numpy as np
import pytest

QUELLE = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui" / "views" / "umwelt.py"

pytest.importorskip("PySide6.QtWidgets")


def _importierte_module(pfad):
    """Die tatsaechlich importierten Modulnamen — auch aus Funktionsrumpfen.

    Ueber `ast`, nicht ueber Textsuche: der Docstring dieser Ansicht ERWAEHNT
    bosdyn, um zu begruenden, warum es fehlt. Eine Substring-Pruefung schluege
    daran an und pruefte damit die Dokumentation statt des Codes.
    """
    import ast

    namen = set()
    for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Import):
            namen.update(teil.name for teil in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            namen.add(knoten.module)
    return namen


def test_ansicht_importiert_weder_bosdyn_noch_backends():
    """CLAUDE.md: kein bosdyn UND kein spotlab.backends unterhalb von gui/."""
    module = _importierte_module(QUELLE)
    verboten = [
        name for name in module
        if name.split(".")[0] == "bosdyn" or name.startswith("spotlab.backends")
    ]
    assert not verboten, f"Die Ansicht darf das nicht importieren: {verboten}"


def _lauf_mit_objekten(tmp_path, t=1.0):
    zeilen = [
        {"t": t, "art": "kommando",
         "daten": {"name": "tags", "treffer": 2, "ids": [1, 2],
                   "distanzen": [2.06, 4.27]}},
    ]
    (tmp_path / "ereignisse.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    return tmp_path


def _lege_vorschau(tmp_path):
    from PIL import Image

    ordner = tmp_path / "gitter"
    ordner.mkdir(exist_ok=True)
    (ordner / "000001_obstacle_distance.pb").write_bytes(b"fuer die GUI unlesbar")
    puffer = io.BytesIO()
    Image.fromarray(np.full((8, 8), 128, dtype=np.uint8), mode="L").save(
        puffer, format="PNG"
    )
    (ordner / "000001_obstacle_distance.png").write_bytes(puffer.getvalue())
    return tmp_path


def test_zeigt_gesehene_objekte_aus_dem_lauf(qapp, tmp_path):
    from spotlab.gui.views.umwelt import UmweltView

    ansicht = UmweltView()
    ansicht.lade(_lauf_mit_objekten(tmp_path))
    texte = ansicht.objekttexte()
    assert any("2.06" in t for t in texte)
    assert len(texte) == 2


def test_alter_der_beobachtung_wird_angezeigt():
    """Eine Objektliste ohne Alter suggeriert Gegenwart."""
    from spotlab.gui.views.umwelt import zeilen_aus

    saetze = [{"t": 100.0, "art": "kommando",
               "daten": {"name": "tags", "ids": [1], "distanzen": [2.0]}}]
    zeile = zeilen_aus(saetze, jetzt=142.0)[0]
    assert "vor 42 s" in zeile


def test_leeres_lauf_verzeichnis_meldet_nichts_statt_zu_stuerzen(qapp, tmp_path):
    from spotlab.gui.views.umwelt import UmweltView

    ansicht = UmweltView()
    ansicht.lade(tmp_path)
    assert ansicht.objekttexte() == []
    assert ansicht.gitterbild() is None


def test_halbe_letzte_zeile_bricht_die_ansicht_nicht(qapp, tmp_path):
    """Ein hart getoeteter Lauf hinterlaesst eine angeschnittene jsonl-Zeile."""
    from spotlab.gui.views.umwelt import UmweltView

    _lauf_mit_objekten(tmp_path)
    with (tmp_path / "ereignisse.jsonl").open("a", encoding="utf-8") as datei:
        datei.write('{"t": 2.0, "art": "komm')

    ansicht = UmweltView()
    ansicht.lade(tmp_path)
    assert len(ansicht.objekttexte()) == 2


def test_zeigt_die_vorschau_nicht_das_protobuf(qapp, tmp_path):
    """Die GUI kann kein Protobuf dekodieren — sie bekommt ein Bild."""
    from spotlab.gui.views.umwelt import UmweltView

    _lauf_mit_objekten(tmp_path)
    _lege_vorschau(tmp_path)

    ansicht = UmweltView()
    ansicht.lade(tmp_path)
    bild = ansicht.gitterbild()
    assert bild is not None
    assert not bild.isNull()


def test_sonde_ohne_arbeitsordner_meldet_klartext(qapp, tmp_path):
    from spotlab.gui.views.umwelt import UmweltView

    ansicht = UmweltView()
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    assert ansicht._starte_sonde() is None
    assert gemeldet and "Arbeitsordner" in gemeldet[0]
