"""Der Weg vom Doppelklick zum Fenster.

Hier laufen die PowerShell-Skripte WIRKLICH (CLAUDE.md: wo ein externer Prozess
im Spiel ist, braucht es einen Test, der ihn startet). Attrappen pruefen nur,
dass die richtigen Argumente gebaut werden -- nicht, dass Windows damit etwas
anfangen kann.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests_zeitgrenzen import TEST_TIMEOUT_S

WURZEL = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell fehlt")


def _ps(skript, *argumente, cwd=None, pfad=None):
    umgebung = None
    if pfad is not None:
        umgebung = dict(os.environ, PATH=str(pfad))
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(skript), *argumente],
        capture_output=True, text=True, timeout=TEST_TIMEOUT_S,
        cwd=str(cwd or WURZEL), encoding="utf-8", errors="replace", env=umgebung,
    )


# ------------------------------------------------------------ Verknuepfung


def test_verknuepfung_wird_wirklich_angelegt(tmp_path):
    ergebnis = _ps(
        WURZEL / "verknuepfung.ps1",
        "-Ordner", str(tmp_path), "-Name", "spotlab",
    )
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert (tmp_path / "spotlab.lnk").is_file()


def _lies_lnk(lnk):
    """Die Verknuepfung zurueckgelesen -- ueber dieselbe COM-Schnittstelle, die
    sie angelegt hat. Ein Blick in die rohen Bytes taeuscht: Windows legt die
    Pfade als UTF-16 ab, eine Textsuche findet sie nie."""
    befehl = (
        "$s = New-Object -ComObject WScript.Shell; "
        f"$v = $s.CreateShortcut('{lnk}'); "
        "Write-Output $v.TargetPath; Write-Output $v.Arguments; "
        "Write-Output $v.IconLocation"
    )
    ergebnis = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", befehl],
        capture_output=True, text=True, timeout=TEST_TIMEOUT_S,
        encoding="utf-8", errors="replace",
    )
    ziel, argumente, icon = ergebnis.stdout.splitlines()[:3]
    return ziel, argumente, icon


def test_verknuepfung_zeigt_auf_starten_ps1(tmp_path):
    _ps(WURZEL / "verknuepfung.ps1", "-Ordner", str(tmp_path), "-Name", "spotlab")
    ziel, argumente, _icon = _lies_lnk(tmp_path / "spotlab.lnk")
    # Ziel ist PowerShell, nicht das Skript: ein doppelgeklicktes .ps1 wuerde
    # von Windows im Editor GEOEFFNET statt ausgefuehrt.
    assert ziel.lower().endswith("powershell.exe")
    assert "starten.ps1" in argumente
    assert "-ExecutionPolicy Bypass" in argumente


def test_verknuepfung_traegt_das_icon(tmp_path):
    _ps(WURZEL / "verknuepfung.ps1", "-Ordner", str(tmp_path), "-Name", "spotlab")
    _ziel, _argumente, icon = _lies_lnk(tmp_path / "spotlab.lnk")
    assert "spotlab.ico" in icon


def test_verknuepfung_ist_wiederholbar(tmp_path):
    """Wie einrichten.ps1 selbst: zweimal ausgefuehrt aendert nichts."""
    for _ in range(2):
        ergebnis = _ps(
            WURZEL / "verknuepfung.ps1", "-Ordner", str(tmp_path), "-Name", "spotlab"
        )
        assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert len(list(tmp_path.glob("*.lnk"))) == 1


# ----------------------------------------------------------------- Starten


def _falsches_repo(tmp_path, mit_venv):
    """Ein Repo-Abbild mit starten.ps1 und wahlweise einer .venv-Attrappe."""
    shutil.copy(WURZEL / "starten.ps1", tmp_path / "starten.ps1")
    (tmp_path / "einrichten.ps1").write_text("Write-Host 'eingerichtet'\n",
                                             encoding="utf-8")
    if mit_venv:
        skripte = tmp_path / ".venv" / "Scripts"
        skripte.mkdir(parents=True)
        (skripte / "pythonw.exe").write_bytes(b"nicht wirklich Python")
    return tmp_path


def test_mit_umgebung_wird_die_gui_gestartet(tmp_path):
    repo = _falsches_repo(tmp_path, mit_venv=True)
    ergebnis = _ps(repo / "starten.ps1", "-NurPruefen", cwd=repo)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "pythonw.exe" in ergebnis.stdout
    assert "spotlab.cli" in ergebnis.stdout
    assert "einrichten" not in ergebnis.stdout.lower()


def test_ohne_umgebung_wird_zuerst_eingerichtet(tmp_path):
    """Der selbstheilende Teil: ein frischer Laptop kommt mit einem Klick hin.

    Der PATH muss dafuer LEER sein. Ohne das fand der Test auf dem Rechner des
    Autors dessen eigenes spotlab in miniconda -- und pruefte dann etwas ganz
    anderes, als sein Name behauptet.
    """
    repo = _falsches_repo(tmp_path, mit_venv=False)
    leer = tmp_path / "leer"
    leer.mkdir()
    ergebnis = _ps(repo / "starten.ps1", "-NurPruefen", cwd=repo, pfad=leer)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "einrichten.ps1" in ergebnis.stdout


def test_starten_haengt_nicht_am_arbeitsverzeichnis(tmp_path):
    """Eine Verknuepfung startet irgendwo -- das Skript muss sein Repo selbst finden."""
    repo = _falsches_repo(tmp_path, mit_venv=True)
    anderswo = tmp_path / "woanders"
    anderswo.mkdir()
    ergebnis = _ps(repo / "starten.ps1", "-NurPruefen", cwd=anderswo)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert str(repo) in ergebnis.stdout


# ------------------------------------------------------------- Icon und GUI


def test_es_gibt_ein_icon():
    """Ohne .ico traegt die Verknuepfung das PowerShell-Logo."""
    icon = WURZEL / "spotlab.ico"
    assert icon.is_file()
    assert icon.stat().st_size > 0


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") is None, reason="ohne Qt")
def test_ohne_konfiguration_fuehrt_die_gui_zu_den_zugangsdaten(qapp, monkeypatch):
    """Vorhandenes Verhalten, bisher ungetestet: wer zum ersten Mal startet,
    soll nicht vor einer leeren Projektansicht sitzen."""
    pytest.importorskip("PySide6.QtWidgets")
    from spotlab.errors import ConfigMissing
    from spotlab.gui import app as modul

    def keine(*_a, **_k):
        raise ConfigMissing("keine Konfiguration")

    monkeypatch.setattr(modul, "load_config", keine)
    fenster = modul.MainWindow()
    assert fenster.stapel.currentWidget() is fenster.ansichten["spot"]


# --------------------------------- vorhandene Installation statt Neubau
#
# Der Autor selbst hat spotlab in einer Conda-Umgebung, nicht in .venv. Ohne
# diese Suche wuerde ein Doppelklick bei ihm ein ZWEITES Environment anlegen --
# 642 MB PySide6, obwohl alles laengst da ist. Ein Werkzeug, das der Autor
# umgehen muss, wird selten gut.


def _falsche_installation(tmp_path, conda_layout):
    """Ein spotlab im PATH. `pythonw.exe` liegt bei conda EINE Ebene ueber
    dem Scripts-Ordner, bei einem venv darin -- beide Faelle kommen vor."""
    umgebung = tmp_path / ("conda" if conda_layout else "venv")
    skripte = umgebung / "Scripts"
    skripte.mkdir(parents=True)
    (skripte / "spotlab.exe").write_bytes(b"nicht wirklich spotlab")
    ziel = umgebung if conda_layout else skripte
    (ziel / "pythonw.exe").write_bytes(b"nicht wirklich Python")
    return skripte, ziel / "pythonw.exe"


def test_vorhandenes_spotlab_wird_genutzt_conda(tmp_path):
    repo = _falsches_repo(tmp_path, mit_venv=False)
    skripte, pythonw = _falsche_installation(tmp_path, conda_layout=True)
    ergebnis = _ps(repo / "starten.ps1", "-NurPruefen", cwd=repo, pfad=skripte)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert str(pythonw) in ergebnis.stdout
    assert "einrichten" not in ergebnis.stdout.lower()


def test_vorhandenes_spotlab_wird_genutzt_venv(tmp_path):
    repo = _falsches_repo(tmp_path, mit_venv=False)
    skripte, pythonw = _falsche_installation(tmp_path, conda_layout=False)
    ergebnis = _ps(repo / "starten.ps1", "-NurPruefen", cwd=repo, pfad=skripte)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert str(pythonw) in ergebnis.stdout


def test_eigene_umgebung_geht_vor(tmp_path):
    """Auf einem Schul-Laptop soll .venv gelten, auch wenn zufaellig noch
    irgendein spotlab im PATH steht."""
    repo = _falsches_repo(tmp_path, mit_venv=True)
    skripte, fremdes = _falsche_installation(tmp_path, conda_layout=True)
    ergebnis = _ps(repo / "starten.ps1", "-NurPruefen", cwd=repo, pfad=skripte)
    assert ".venv" in ergebnis.stdout
    assert str(fremdes) not in ergebnis.stdout
