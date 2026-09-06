import shutil
import subprocess

import pytest

from spotlab.errors import SpotlabError
from spotlab.workshop.editor import finde_editor, open_in_editor
from spotlab.workshop.launcher import run_script, start_script


class FakeProzess:
    """Verhält sich wie ein Popen: hat wait() und returncode."""

    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = None

    def wait(self):
        return self.returncode


FAKE_CODE = r"C:\fake\Microsoft VS Code\bin\code.CMD"


def test_editor_wird_mit_pfad_aufgerufen(tmp_path):
    aufrufe = []
    open_in_editor(
        tmp_path,
        command="code",
        starter=lambda *a, **k: aufrufe.append(a),
        sucher=lambda _: FAKE_CODE,
    )
    assert str(tmp_path) in aufrufe[0][0]


def test_befehl_wird_vor_dem_start_aufgeloest(tmp_path):
    """Der Kern des Windows-Fehlers: subprocess bekommt nie den nackten Namen.

    CreateProcess wertet PATHEXT nicht aus und findet `code.cmd` im PATH
    deshalb nicht — obwohl `code` in jeder Shell funktioniert.
    """
    aufrufe = []
    open_in_editor(
        tmp_path,
        command="code",
        starter=lambda *a, **k: aufrufe.append(a),
        sucher=lambda _: FAKE_CODE,
    )
    assert aufrufe[0][0][0] == FAKE_CODE
    assert aufrufe[0][0][0] != "code"


def test_nicht_gefunden_gibt_klartext(tmp_path):
    with pytest.raises(SpotlabError) as info:
        open_in_editor(tmp_path, command="code", sucher=lambda _: None)
    text = str(info.value)
    assert "installiert" in text
    assert str(tmp_path) in text


def test_start_schlaegt_fehl_gibt_klartext(tmp_path):
    def fehlt(*a, **k):
        raise FileNotFoundError("weg")

    with pytest.raises(SpotlabError) as info:
        open_in_editor(tmp_path, command="code", starter=fehlt, sucher=lambda _: FAKE_CODE)
    assert "starten" in str(info.value)


def test_voller_pfad_wird_durchgereicht(tmp_path):
    """Damit man in config.toml ein Programm ausserhalb des PATH eintragen kann."""
    programm = tmp_path / "meineditor.exe"
    programm.write_text("", encoding="utf-8")
    assert finde_editor(str(programm), sucher=lambda _: None) == str(programm)


def test_voller_pfad_der_nicht_existiert_ergibt_none(tmp_path):
    assert finde_editor(str(tmp_path / "gibtsnicht.exe"), sucher=lambda _: None) is None


@pytest.mark.skipif(shutil.which("code") is None, reason="VS Code ist hier nicht installiert")
def test_aufgeloester_editor_ist_wirklich_startbar():
    """Regressionstest mit ECHTEM Prozess.

    Genau hier lag die Lücke: beide alten Editor-Tests reichten eine Attrappe
    herein und starteten nie etwas. Der nackte Name scheitert unter Windows an
    CreateProcess, der aufgelöste Pfad läuft.
    """
    aufgeloest = finde_editor("code")
    assert aufgeloest is not None
    ergebnis = subprocess.run(
        [aufgeloest, "--version"], capture_output=True, text=True, timeout=60
    )
    assert ergebnis.returncode == 0, ergebnis.stderr


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


def _umgebung_von(tmp_path, **kw):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    def starter(argumente, **gesehen):
        aufrufe.append(gesehen)
        return FakeProzess()

    start_script(skript, starter=starter, **kw)
    return aufrufe[0]["env"]


def test_backend_name_wird_durchgereicht(tmp_path):
    """Der Uebungsraum braucht `sim` -- ueber `dryrun=True` allein ist das
    Backend gar nicht erreichbar, und ein Trockenlauf hat keine Position."""
    assert _umgebung_von(tmp_path, backend="sim")["SPOTLAB_BACKEND"] == "sim"


def test_ohne_angabe_bleibt_die_variable_weg(tmp_path):
    """Sonst uebersteuerte die GUI stillschweigend `default_backend`."""
    assert "SPOTLAB_BACKEND" not in _umgebung_von(tmp_path)


def test_backend_schlaegt_dryrun(tmp_path):
    umgebung = _umgebung_von(tmp_path, backend="sim", dryrun=True)
    assert umgebung["SPOTLAB_BACKEND"] == "sim"


def test_zusatzumgebung_wird_mitgegeben(tmp_path):
    """Damit die GUI Raum und Startpose durchreichen kann, ohne den Umweg ueber
    die Konfigurationsdatei."""
    umgebung = _umgebung_von(tmp_path, umgebung={"SPOTLAB_RAUM": "durchgang"})
    assert umgebung["SPOTLAB_RAUM"] == "durchgang"
    assert umgebung["PYTHONUTF8"] == "1"        # das Uebrige bleibt stehen
