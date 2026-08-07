import subprocess

import pytest

from spotlab.errors import SpotlabError
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import run_script, start_script


class FakeProzess:
    """Verhält sich wie ein Popen: hat wait() und returncode."""

    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = None

    def wait(self):
        return self.returncode


def test_editor_wird_mit_pfad_aufgerufen(tmp_path):
    aufrufe = []
    open_in_editor(tmp_path, command="code", starter=lambda *a, **k: aufrufe.append(a))
    assert str(tmp_path) in aufrufe[0][0]


def test_fehlender_editor_gibt_klartext(tmp_path):
    def fehlt(*a, **k):
        raise FileNotFoundError

    with pytest.raises(SpotlabError) as info:
        open_in_editor(tmp_path, command="code", starter=fehlt)
    assert "PATH" in str(info.value) or "gefunden" in str(info.value)


def test_skript_wird_mit_python_gestartet(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    def starter(argumente, **kw):
        aufrufe.append((argumente, kw))
        return FakeProzess()

    assert run_script(skript, starter=starter) == 0
    argumente, kw = aufrufe[0]
    assert argumente[-1] == str(skript)
    assert kw["cwd"] == str(tmp_path)


def test_dryrun_setzt_umgebungsvariable(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    def starter(argumente, **kw):
        aufrufe.append(kw)
        return FakeProzess()

    run_script(skript, dryrun=True, starter=starter)
    assert aufrufe[0]["env"]["SPOTLAB_BACKEND"] == "dryrun"


def test_fehlendes_skript_gibt_klartext(tmp_path):
    with pytest.raises(SpotlabError) as info:
        run_script(tmp_path / "gibtsnicht.py")
    assert "gibtsnicht.py" in str(info.value)


def test_kindprozess_bekommt_utf8_und_importpfad(tmp_path):
    """Deutsche Meldungen dürfen auf einer cp1252-Konsole nicht zerfallen."""
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    def starter(argumente, **kw):
        aufrufe.append(kw)
        return FakeProzess()

    run_script(skript, starter=starter)
    umgebung = aufrufe[0]["env"]
    assert umgebung["PYTHONUTF8"] == "1"
    assert umgebung["PYTHONPATH"]


def test_connect_beachtet_umgebungsvariable(tmp_path, monkeypatch):
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "dryrun")
    with spotlab.connect(runs_dir=tmp_path) as spot:
        assert spot.backend.__class__.__name__ == "DryRunBackend"


def test_start_script_kehrt_sofort_zurueck(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    gebaut = []

    def starter(argumente, **kw):
        gebaut.append((argumente, kw))
        return FakeProzess()

    prozess = start_script(skript, starter=starter)
    assert prozess.returncode == 0
    argumente, kw = gebaut[0]
    assert argumente[-1] == str(skript)
    assert kw["cwd"] == str(tmp_path)


def test_start_script_fuehrt_ausgabe_zusammen(tmp_path):
    """Ein Leser statt zwei: sonst muss die GUI zwei Pipes gleichzeitig bedienen."""
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    gebaut = []

    def starter(argumente, **kw):
        gebaut.append(kw)
        return FakeProzess()

    start_script(skript, starter=starter)
    kw = gebaut[0]
    assert kw["stdout"] is subprocess.PIPE
    assert kw["stderr"] is subprocess.STDOUT
    assert kw["text"] is True


def test_run_script_wartet_und_gibt_code_zurueck(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    assert run_script(skript, starter=lambda *a, **k: FakeProzess(returncode=3)) == 3
