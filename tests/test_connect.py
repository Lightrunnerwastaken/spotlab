"""`spotlab.connect()` selbst: welcher Name welches Backend baut, und was ein Lauf
über sich sagt, wenn er nicht zustande kommt oder ordentlich endet.

Kein Test hier erreicht den echten Roboter: `kein_roboter` ersetzt beide
Einstiege von `RealSpot` durch eine Attrappe, die laut scheitert.
"""

import json

import pytest

import spotlab
from spotlab.errors import SpotlabError

UMGEBUNG = ("SPOTLAB_BACKEND", "SPOTLAB_RAUM", "SPOTLAB_RAUM_START")


@pytest.fixture
def kein_roboter(monkeypatch):
    """Zählt jeden Versuch, den echten Spot anzufordern -- und lässt ihn scheitern."""
    from spotlab.backends import real

    versuche = []

    def attrappe(*argumente, **benannt):
        versuche.append(argumente)
        raise AssertionError("der ECHTE Spot wäre angefordert worden")

    monkeypatch.setattr(real.RealSpot, "connect", staticmethod(attrappe))
    monkeypatch.setattr(real.RealSpot, "nur_lesen", staticmethod(attrappe))
    for name in UMGEBUNG:
        monkeypatch.delenv(name, raising=False)
    return versuche


def _konfiguration(tmp_path, defaults=True):
    pfad = tmp_path / "config.toml"
    text = '[robot]\nip = "192.0.2.1"\nusername = "u"\n'
    if defaults:
        text += '[defaults]\nbackend = "dryrun"\n'
    pfad.write_text(text, encoding="utf-8")
    return pfad


def _laeufe(runs):
    return sorted(runs.iterdir()) if runs.exists() else []


# ------------------------------------------------ unbekannte Backend-Namen


@pytest.mark.parametrize("name", ["Sim", "mujoko", "trocken", "REAL", " real", "dry-run"])
def test_ein_unbekannter_backend_name_faehrt_nicht_den_echten_spot(tmp_path, kein_roboter, name):
    """Beta-Prüfung 23.09.2026: jeder Name, der nicht genau stimmte, landete im
    else-Zweig -- bei `RealSpot.connect`. Ein Tippfehler in `backend="Sim"`
    forderte den echten Roboter an."""
    runs = tmp_path / "runs"
    with pytest.raises(SpotlabError) as fehler:
        with spotlab.connect(backend=name, runs_dir=runs, config_path=_konfiguration(tmp_path)):
            pass
    assert kein_roboter == []
    meldung = str(fehler.value)
    assert repr(name) in meldung or f"„{name}“" in meldung
    for gueltig in ("dryrun", "sim", "mujoco", "physics", "real"):
        assert gueltig in meldung
    # Abgewiesen VOR dem RunRecorder: kein leeres Lauf-Verzeichnis.
    assert _laeufe(runs) == []


def test_auch_ein_unbekannter_name_aus_der_umgebung_wird_abgewiesen(
        tmp_path, kein_roboter, monkeypatch):
    monkeypatch.setenv("SPOTLAB_BACKEND", "Mujoco")
    runs = tmp_path / "runs"
    with pytest.raises(SpotlabError) as fehler:
        with spotlab.connect(runs_dir=runs, config_path=_konfiguration(tmp_path)):
            pass
    assert "SPOTLAB_BACKEND" in str(fehler.value)
    assert kein_roboter == [] and _laeufe(runs) == []


def test_eine_konfiguration_ohne_defaults_faehrt_nicht_den_echten_spot(
        tmp_path, kein_roboter, monkeypatch):
    """Wer nichts einstellt, fährt NICHT den echten Spot (CLAUDE.md). Eine
    Konfiguration ohne [defaults] -- von Hand angelegt oder aus einer alten
    Fassung -- lieferte bis zum 23.09.2026 `default_backend = "real"`."""
    from spotlab.backends import mujoco
    from spotlab.backends.sim import SimBackend

    class OhnePuppe(SimBackend):
        """Der Übungsraum ohne 3D-Körper: hier zählt nur, WELCHES Backend gebaut wird."""

        def __init__(self, recorder=None, ansicht_ziel=None, **benannt):
            super().__init__(recorder=recorder, **benannt)

    monkeypatch.setattr(mujoco, "MujocoBackend", OhnePuppe)
    runs = tmp_path / "runs"
    with spotlab.connect(runs_dir=runs, config_path=_konfiguration(tmp_path, defaults=False)) as spot:
        assert isinstance(spot.backend, OhnePuppe)
    assert kein_roboter == []
    (lauf,) = _laeufe(runs)
    assert json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))["backend"] == "mujoco"
