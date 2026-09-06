"""Der Ordner „Beispiele" im Arbeitsordner -- und das Beispiel, das durch die Tuer geht.

Die GUI legt den Ordner beim Start an und zeigt ihn wie jedes Projekt. Kopiert
wird nur, was fehlt: aendert ein Schueler ein Beispiel, bleibt seine Fassung.
"""

import json
import os
import subprocess
import sys

import pytest

from spotlab.workshop.beispiele import ORDNER, bereitstellen
from tests_zeitgrenzen import TEST_TIMEOUT_S


def test_der_ordner_ist_ein_projekt_mit_allen_beispielen(tmp_path):
    ziel, neu = bereitstellen(tmp_path)
    assert ziel == tmp_path / ORDNER
    assert (ziel / "runs").is_dir(), "ohne runs/ erkennt die GUI kein Projekt"
    assert (ziel / ".vscode" / "settings.json").is_file()
    for name in ("hallo_spot.py", "uebungsraum.py", "durchgang_finden.py", "README.md"):
        assert (ziel / name).is_file(), name
        assert name in neu


def test_ein_geaendertes_beispiel_wird_nicht_ueberschrieben(tmp_path):
    ziel, _ = bereitstellen(tmp_path)
    (ziel / "durchgang_finden.py").write_text("# meins\n", encoding="utf-8")
    _, neu = bereitstellen(tmp_path)
    assert neu == []
    assert (ziel / "durchgang_finden.py").read_text(encoding="utf-8") == "# meins\n"


def test_ein_geloeschtes_beispiel_kommt_wieder(tmp_path):
    ziel, _ = bereitstellen(tmp_path)
    (ziel / "hallo_spot.py").unlink()
    _, neu = bereitstellen(tmp_path)
    assert neu == ["hallo_spot.py"]


def test_die_gui_findet_den_ordner_als_projekt(tmp_path):
    from spotlab.gui.views.projects import projekte_in

    bereitstellen(tmp_path)
    assert [p.name for p in projekte_in(tmp_path)] == [ORDNER]


# ------------------------------------------------------- Das Beispiel selbst


def _lauf_des_beispiels(tmp_path, backend="sim", raum="durchgang"):
    """`durchgang_finden.py` als echter Kindprozess im Uebungsraum."""
    ziel, _ = bereitstellen(tmp_path)
    umgebung = dict(os.environ, SPOTLAB_BACKEND=backend, SPOTLAB_RAUM=raum,
                    SPOTLAB_RAUM_START="1.00,2.00,0.0", PYTHONUTF8="1",
                    PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    ergebnis = subprocess.run(
        [sys.executable, "-u", str(ziel / "durchgang_finden.py")],
        cwd=str(ziel), env=umgebung, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TEST_TIMEOUT_S * 4,
    )
    laeufe = sorted((ziel / "runs").glob("*"))
    return ergebnis, laeufe[-1] if laeufe else None


def test_das_beispiel_findet_die_tuer_und_setzt_sich_im_2d_raum(tmp_path):
    """Start (1, 2) im Raum „durchgang": die Tuer liegt bei x = 4.5, der Tag
    drueben bei x = 8.9. Spot darf den Plan nicht kennen -- er soll ihn mit
    dem Gitter finden und den Tag als Beweis nehmen, dass er drueben ist."""
    ergebnis, lauf = _lauf_des_beispiels(tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Tag gesehen" in ergebnis.stdout, ergebnis.stdout
    assert lauf is not None
    meta = json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))
    assert meta["backend"] == "sim" and meta["ergebnis"] == "ok"
    ereignisse = [json.loads(z) for z in (lauf / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines() if z.strip()]
    kommandos = [e["daten"].get("name") for e in ereignisse if e["art"] == "kommando"]
    assert kommandos[-1] == "sit", kommandos
    assert "angestossen" not in [e["art"] for e in ereignisse], "gegen eine Wand gelaufen"
    letzte = json.loads((lauf / "zustand.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    x, y, _yaw = letzte["daten"]["pose"]
    assert x > 4.5, f"nicht durch die Tuer: x = {x:.2f}"
    assert 1.5 < y < 2.4 or x > 5.0, f"neben der Tuer: y = {y:.2f}"


@pytest.mark.skipif(not __import__("importlib").util.find_spec("spotsim"),
                    reason="3D braucht spotsim")
def test_das_beispiel_findet_die_tuer_auch_in_3d(tmp_path):
    """Dasselbe Programm, unveraendert, mit Kameras und Tiefengitter."""
    import spotsim

    if not spotsim.spot_asset_available():
        pytest.skip("Menagerie-Asset fehlt")
    ergebnis, lauf = _lauf_des_beispiels(tmp_path, backend="mujoco")
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Tag gesehen" in ergebnis.stdout, ergebnis.stdout
    letzte = json.loads((lauf / "zustand.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert letzte["daten"]["pose"][0] > 4.5
