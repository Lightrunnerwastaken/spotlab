"""Die Sonde: was sie sammelt — und vor allem, was sie NICHT tut."""

import ast
import os
import subprocess
import sys
from pathlib import Path

from spotlab.api.spot import Spot
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import UnsupportedCapability
from spotlab.workshop.sonde import sonde

QUELLE = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "workshop" / "sonde.py"

BEWEGUNGSVERBEN = {
    "walk", "move", "stand", "sit", "power_on", "power_off",
    "navigate_to", "send_command", "send",
}


def test_sonde_ruft_keine_bewegungsfunktion_auf():
    """Das Gate hinter der Leaselosigkeit.

    Eine Naht ist erst eine Naht, wenn sie reisst, sobald jemand durchgreift.
    Dieser Test reisst — dieselbe Methode wie test_editor_verbs.py.
    """
    baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
    gerufen = {
        knoten.func.attr
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
    }
    verboten = gerufen & BEWEGUNGSVERBEN
    assert not verboten, f"Die Sonde darf nichts bewegen, ruft aber: {sorted(verboten)}"


def test_sonde_importiert_kein_bewegungsmodul():
    quelle = QUELLE.read_text(encoding="utf-8")
    assert "api.motion" not in quelle
    assert "api.posture" not in quelle


def test_sonde_sammelt_objekte_und_gitter():
    takte = iter([0.0, 0.5, 1.0, 1.5, 2.0, 99.0])
    ergebnis = sonde(
        Spot(DryRunBackend()), dauer_s=2.0, hz=2.0,
        schlaf=lambda _s: None, jetzt=lambda: next(takte),
    )
    assert ergebnis["abtastungen"] >= 1
    assert ergebnis["objekte_gesehen"] >= 1
    assert ergebnis["gitter"] is not None


def test_sonde_behaelt_die_naechste_sichtung():
    """Wer wissen will, ob ein Tag in Reichweite kommt, will den besten Moment."""
    takte = iter([0.0, 0.5, 99.0])
    ergebnis = sonde(
        Spot(DryRunBackend()), dauer_s=1.0, hz=2.0,
        schlaf=lambda _s: None, jetzt=lambda: next(takte),
    )
    abstaende = [o.distance for o in ergebnis["objekte"]]
    assert abstaende == sorted(abstaende)


def test_sonde_ueberlebt_ein_backend_ohne_gitter():
    """Die Sim kann kein Gitter — die Sonde soll trotzdem Objekte melden."""

    class OhneGitter(DryRunBackend):
        def local_grid(self):
            raise UnsupportedCapability("kein Gitter")

    takte = iter([0.0, 0.5, 99.0])
    ergebnis = sonde(
        Spot(OhneGitter()), dauer_s=1.0, hz=2.0,
        schlaf=lambda _s: None, jetzt=lambda: next(takte),
    )
    assert ergebnis["objekte_gesehen"] >= 1
    assert ergebnis["gitter"] is None


def test_sonde_laeuft_wirklich_als_prozess(tmp_path):
    """Attrappen pruefen nur, dass die Argumente stimmen.

    CLAUDE.md: wo ein externer Prozess im Spiel ist, braucht es einen Test, der
    ihn wirklich startet — genau daran ist "In VS Code oeffnen" durch die ganze
    Suite gegangen.
    """
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    umgebung = dict(
        os.environ,
        SPOTLAB_NUR_TROCKEN="1",
        SPOTLAB_BACKEND="dryrun",
        SPOTLAB_RUNS_DIR=str(tmp_path),
    )
    ergebnis = subprocess.run(
        [sys.executable, "-m", "spotlab.workshop.sonde"],
        capture_output=True, text=True, timeout=TEST_TIMEOUT_S, env=umgebung,
        cwd=str(tmp_path),
    )
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Objekte gesehen" in ergebnis.stdout
