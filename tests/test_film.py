"""Das Video eines Laufs -- nachtraeglich aus der Aufzeichnung gerendert.

Nicht waehrend des Laufs: aus `zustand.jsonl` (Pose + zwoelf Gelenke, 10 Hz)
wird auf `fps` interpoliert und auf der Puppe abgespielt. Das kostet den Lauf
nichts, ist fluessig, und es funktioniert fuer alte, fuer 2D- und fuer ECHTE
Laeufe -- die aufgezeichneten Gelenkwinkel des Schul-Spot im Menagerie-Modell.

Uebersprungen ohne spotsim oder Asset.
"""

import json
import math

import pytest

spotsim = pytest.importorskip("spotsim")

pytestmark = pytest.mark.skipif(
    not spotsim.spot_asset_available(),
    reason="Menagerie-Asset fehlt -- python scripts/fetch_menagerie.py in matura-spot",
)


def _lauf(tmp_path, raum="leer", mit_gelenken=True, dauer_s=1.5, hz=10.0, backend="mujoco"):
    """Ein synthetischer Lauf: 1 m vorwaerts und eine Vierteldrehung."""
    from spotlab.kalibrierung.modell import lade_modell

    modell = lade_modell()
    ordner = tmp_path / "runs" / "20260906T150000Z_abcdef12"
    ordner.mkdir(parents=True)
    (ordner / "lauf.json").write_text(json.dumps({
        "id": ordner.name, "backend": backend, "ergebnis": "ok", "dauer_s": dauer_s,
        "gestartet": "2026-09-06T15:00:00+00:00",
    }), encoding="utf-8")
    ereignisse = [{"t": 0.0, "art": "verbunden", "daten": {"backend": backend, "raum": raum}}]
    (ordner / "ereignisse.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ereignisse), encoding="utf-8")
    zeilen = []
    n = int(dauer_s * hz) + 1
    for i in range(n):
        t = i / hz
        anteil = i / max(n - 1, 1)
        daten = {"pose": [1.0 + anteil, 1.0, anteil * math.pi / 2], "battery": 88.0}
        if mit_gelenken:
            winkel = modell.gelenke(0.3, 0.0, anteil * 2.0)
            daten["joints"] = {name: {"position": w, "velocity": 0.0, "load": 0.0}
                               for name, w in winkel.items()}
        zeilen.append(json.dumps({"t": t, "daten": daten}))
    (ordner / "zustand.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return ordner


# ---------------------------------------------------------------- Renderer


def test_ein_lauf_wird_zum_video(tmp_path):
    from spotlab.backends.mujoco import film_aus_lauf

    lauf = _lauf(tmp_path)
    ergebnis = film_aus_lauf(lauf, fps=10)
    pfad = ergebnis["pfad"]
    assert pfad == lauf / "film.mp4" and pfad.is_file()
    assert pfad.stat().st_size > 5_000, "kein brauchbares Video"
    # 1.5 s bei 10 fps: 15 Bilder (+1 fuer den letzten Zeitpunkt)
    assert 15 <= ergebnis["bilder"] <= 16
    assert ergebnis["raum"] == "leer"


def test_zwischen_den_proben_wird_interpoliert(tmp_path):
    """Die Aufzeichnung hat 10 Hz; bei 30 fps liegen zwei von drei Bildern
    ZWISCHEN den Proben. Ohne Interpolation ruckelte das Video genau so wie
    die Live-Ansicht."""
    from spotlab.backends.mujoco import _bilder_aus_lauf

    lauf = _lauf(tmp_path, dauer_s=1.0)
    bilder = list(_bilder_aus_lauf(lauf, fps=30))
    assert 30 <= len(bilder) <= 31
    t, (x, _y, yaw), _gelenke = bilder[15]                 # t = 0.5 s, mitten drin
    assert t == pytest.approx(0.5)
    assert x == pytest.approx(1.5, abs=0.02)
    assert yaw == pytest.approx(math.pi / 4, abs=0.03)


def test_das_gieren_laeuft_sauber_ueber_die_grenze(tmp_path):
    """Von +170 nach -170 Grad sind 20 Grad Weg, nicht 340."""
    from spotlab.backends.mujoco import _interpoliere_pose

    x, y, yaw = _interpoliere_pose((0.0, 0.0, math.radians(170)),
                                   (0.0, 0.0, math.radians(-170)), 0.5)
    assert yaw == pytest.approx(math.pi, abs=1e-6) or yaw == pytest.approx(-math.pi, abs=1e-6)


def test_ohne_gelenke_und_ohne_raum_gibt_es_trotzdem_ein_video(tmp_path):
    """Ein Trockenlauf hat keinen Raum, ein alter Lauf vielleicht keine Gelenke.
    Dann steht Spot in der Standhaltung der Gangkennlinie auf leerem Boden."""
    from spotlab.backends.mujoco import film_aus_lauf

    lauf = _lauf(tmp_path, raum=None, mit_gelenken=False, dauer_s=0.5, backend="dryrun")
    ergebnis = film_aus_lauf(lauf, fps=10)
    assert ergebnis["pfad"].is_file()
    assert ergebnis["raum"] is None


def test_ein_leerer_lauf_sagt_was_fehlt(tmp_path):
    from spotlab.backends.mujoco import film_aus_lauf
    from spotlab.errors import SpotlabError

    lauf = _lauf(tmp_path)
    (lauf / "zustand.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(SpotlabError, match="zustand.jsonl"):
        film_aus_lauf(lauf)


# --------------------------------------------------------------------- CLI


def test_die_kommandozeile_rendert_einen_lauf(tmp_path, capsys):
    from spotlab.cli import main

    lauf = _lauf(tmp_path, dauer_s=0.5)
    assert main(["film", str(lauf), "--fps", "10"]) == 0
    ausgabe = capsys.readouterr().out
    assert "film.mp4" in ausgabe
    assert (lauf / "film.mp4").is_file()
