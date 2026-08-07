import pytest

from spotlab.cli import build_parser, main


def test_alle_kommandos_sind_erreichbar():
    parser = build_parser()
    for kommando in ("login", "doctor", "new", "open", "run", "runs", "lease"):
        argumente = [kommando] + (["x"] if kommando in ("new", "open", "run") else [])
        assert parser.parse_args(argumente)


def test_new_legt_projekt_an(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "mein-projekt"]) == 0
    assert (tmp_path / "mein-projekt" / "hallo_spot.py").exists()
    assert "mein-projekt" in capsys.readouterr().out


def test_new_meldet_bestehenden_ordner_als_fehler(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["new", "p"])
    assert main(["new", "p"]) == 1
    assert "gibt es schon" in capsys.readouterr().err


def test_runs_listet_laeufe(tmp_path, monkeypatch, capsys):
    from spotlab.record.run import RunRecorder

    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    rec = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    rec.finish("ok")
    assert main(["runs"]) == 0
    assert rec.id in capsys.readouterr().out


def test_runs_zeigt_details_eines_laufs(tmp_path, monkeypatch, capsys):
    from spotlab.record.run import RunRecorder

    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    rec = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    rec.event("verbunden", ip="1.2.3.4")
    rec.finish("ok")
    assert main(["runs", rec.id]) == 0
    ausgabe = capsys.readouterr().out
    assert "verbunden" in ausgabe and "Ereignisse" in ausgabe


def test_runs_ohne_laeufe_sagt_das_freundlich(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["runs"]) == 0
    assert "noch keine" in capsys.readouterr().out.lower()


def test_run_mit_dryrun_setzt_die_variable(tmp_path, monkeypatch):
    skript = tmp_path / "x.py"
    skript.write_text(
        "import spotlab\nwith spotlab.connect() as s:\n    pass\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["run", "x.py", "--dryrun"]) == 0


def test_doctor_gibt_stufen_aus(monkeypatch, capsys):
    from spotlab.workshop.doctor import Check

    monkeypatch.setattr(
        "spotlab.cli.diagnose",
        lambda *a, **k: [
            Check("Netz", True, "antwortet"),
            Check("Anmeldung", False, "falsch", "spotlab login"),
        ],
    )
    assert main(["doctor"]) == 1
    ausgabe = capsys.readouterr().out
    assert "Netz" in ausgabe and "spotlab login" in ausgabe


def test_unbekanntes_kommando_gibt_hilfe():
    with pytest.raises(SystemExit):
        main(["quatsch"])


def test_gui_kommando_existiert():
    assert build_parser().parse_args(["gui"])


def test_gui_ohne_pyside_nennt_den_befehl(monkeypatch, capsys):
    import builtins

    echt = builtins.__import__

    def ohne_pyside(name, *args, **kw):
        if name.startswith("spotlab.gui") or name.startswith("PySide6"):
            raise ImportError("No module named 'PySide6'")
        return echt(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", ohne_pyside)
    assert main(["gui"]) == 1
    assert "pip install" in capsys.readouterr().err
