import pytest

from spotlab.errors import SpotlabError
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import run_script


class Ergebnis:
    returncode = 0


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
        return Ergebnis()

    assert run_script(skript, starter=starter) == 0
    argumente, kw = aufrufe[0]
    assert argumente[1] == str(skript)
    assert kw["cwd"] == str(tmp_path)


def test_dryrun_setzt_umgebungsvariable(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    def starter(argumente, **kw):
        aufrufe.append(kw)
        return Ergebnis()

    run_script(skript, dryrun=True, starter=starter)
    assert aufrufe[0]["env"]["SPOTLAB_BACKEND"] == "dryrun"


def test_kindprozess_bekommt_utf8_und_importpfad(tmp_path):
    """Deutsche Meldungen dürfen auf einer cp1252-Konsole nicht zerfallen."""
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    def starter(argumente, **kw):
        aufrufe.append(kw)
        return Ergebnis()

    run_script(skript, starter=starter)
    umgebung = aufrufe[0]["env"]
    assert umgebung["PYTHONUTF8"] == "1"
    assert umgebung["PYTHONPATH"]


def test_fehlendes_skript_gibt_klartext(tmp_path):
    with pytest.raises(SpotlabError) as info:
        run_script(tmp_path / "gibtsnicht.py")
    assert "gibtsnicht.py" in str(info.value)


def test_connect_beachtet_umgebungsvariable(tmp_path, monkeypatch):
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "dryrun")
    with spotlab.connect(runs_dir=tmp_path) as spot:
        assert spot.backend.__class__.__name__ == "DryRunBackend"
