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


# --------------------------------- ein Aufbau, der scheitert, sagt warum


def _lauf_json(runs):
    (lauf,) = _laeufe(runs)
    return json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("art", ["sim", "mujoco", "physics"])
def test_ein_raum_tippfehler_beendet_den_lauf_mit_grund(tmp_path, kein_roboter, art):
    """Beta-Prüfung 23.09.2026 (p01): `raum="moebeliert"` warf zwar eine gute
    Meldung, aber `lauf.json` blieb für immer auf „läuft“ -- ohne Fehler, und
    das Protokollziel zeigte weiter in den toten Lauf."""
    from spotlab import protokoll

    runs = tmp_path / "runs"
    with pytest.raises(SpotlabError, match="moebeliert"):
        with spotlab.connect(backend=art, raum="moebeliert", runs_dir=runs,
                             config_path=_konfiguration(tmp_path)):
            pass
    meta = _lauf_json(runs)
    assert meta["ergebnis"] == "fehler"
    assert "moebeliert" in meta["fehler"]
    assert protokoll.ziel() is None


def test_fehlt_die_simulation_steht_das_im_lauf(tmp_path, kein_roboter, monkeypatch):
    from spotlab.backends import mujoco

    def fehlt():
        raise SpotlabError("Die Simulation fehlt. einrichten.cmd erneut ausführen.")

    monkeypatch.setattr(mujoco, "_puppe_laden", fehlt)
    runs = tmp_path / "runs"
    with pytest.raises(SpotlabError):
        with spotlab.connect(backend="mujoco", runs_dir=runs, config_path=_konfiguration(tmp_path)):
            pass
    meta = _lauf_json(runs)
    assert meta["ergebnis"] == "fehler" and "Simulation fehlt" in meta["fehler"]


def test_strg_c_beim_laden_heisst_abgebrochen(tmp_path, kein_roboter, monkeypatch):
    from spotlab.backends import sim

    def unterbrochen(self, *argumente, **benannt):
        raise KeyboardInterrupt

    monkeypatch.setattr(sim.SimBackend, "__init__", unterbrochen)
    runs = tmp_path / "runs"
    with pytest.raises(KeyboardInterrupt):
        with spotlab.connect(backend="sim", runs_dir=runs, config_path=_konfiguration(tmp_path)):
            pass
    assert _lauf_json(runs)["ergebnis"] == "abgebrochen"


# ------------------------------------------ sys.exit ist kein Absturz


@pytest.mark.parametrize("code", [0, None])
def test_sys_exit_mit_null_ist_ein_ordentliches_ende(tmp_path, kein_roboter, code):
    """p08: ein Schüler beendet sein Programm mit `sys.exit(0)`, weil der Akku
    nicht voll ist -- und der Lauf stand als „fehler: SystemExit: 0“ da."""
    runs = tmp_path / "runs"
    with pytest.raises(SystemExit):
        with spotlab.connect(backend="dryrun", runs_dir=runs):
            raise SystemExit(code)
    meta = _lauf_json(runs)
    assert meta["ergebnis"] == "ok" and meta["fehler"] is None


def test_sys_exit_mit_fehlercode_bleibt_ein_fehler(tmp_path, kein_roboter):
    runs = tmp_path / "runs"
    with pytest.raises(SystemExit):
        with spotlab.connect(backend="dryrun", runs_dir=runs):
            raise SystemExit(2)
    meta = _lauf_json(runs)
    assert meta["ergebnis"] == "fehler" and "sys.exit(2)" in meta["fehler"]
