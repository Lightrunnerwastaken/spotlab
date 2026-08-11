import os
import subprocess
import sys
from pathlib import Path

from spotlab import ENV_NUR_TROCKEN
from spotlab.workshop.launcher import start_script
from tests_zeitgrenzen import TEST_TIMEOUT_S

QUELLE = str(Path(__file__).resolve().parents[1] / "src")


def _umgebung(**extra):
    return {**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1", **extra}


def _lauf(tmp_path, quelltext, **extra):
    skript = tmp_path / "versuch.py"
    skript.write_text(quelltext, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(skript)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        env=_umgebung(**extra),
        timeout=TEST_TIMEOUT_S,
    )


def test_ohne_schranke_laeuft_der_trockenlauf(tmp_path):
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='dryrun') as spot:\n    print('ok')\n",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "ok" in ergebnis.stdout


def test_schranke_erlaubt_den_trockenlauf(tmp_path):
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='dryrun') as spot:\n    print('ok')\n",
        **{ENV_NUR_TROCKEN: "1"},
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "ok" in ergebnis.stdout


def test_schranke_weist_explizites_real_ab(tmp_path):
    """DER Test dieser Aufgabe.

    SPOTLAB_BACKEND allein genuegt nicht: connect() liest
    `backend or os.environ.get(...)`, ein explizites backend="real"
    ueberschreibt die Variable. Ein veraltetes Manifest darf den Roboter
    nicht bewegen koennen.
    """
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='real') as spot:\n    print('nie')\n",
        **{ENV_NUR_TROCKEN: "1"},
    )
    assert ergebnis.returncode != 0
    assert "nie" not in ergebnis.stdout
    assert "ohne Roboter" in (ergebnis.stdout + ergebnis.stderr)


def test_schranke_weist_auch_die_backend_variable_ab(tmp_path):
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect() as spot:\n    print('nie')\n",
        **{ENV_NUR_TROCKEN: "1", "SPOTLAB_BACKEND": "real"},
    )
    assert ergebnis.returncode != 0
    assert "nie" not in ergebnis.stdout


def test_schranke_legt_kein_leeres_lauf_verzeichnis_an(tmp_path):
    """Die Pruefung steht vor dem RunRecorder — sonst bleibt Muell liegen."""
    _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='real') as spot:\n    pass\n",
        **{ENV_NUR_TROCKEN: "1"},
    )
    runs = tmp_path / "runs"
    assert not runs.exists() or list(runs.iterdir()) == []


def test_start_script_reicht_argumente_durch(tmp_path):
    skript = tmp_path / "args.py"
    skript.write_text("import sys\nprint('|'.join(sys.argv[1:]))\n", encoding="utf-8")
    prozess = start_script(skript, argumente=("--episoden", "20", "--archiv"))
    ausgabe = prozess.stdout.read()
    prozess.wait(timeout=TEST_TIMEOUT_S)
    assert "--episoden|20|--archiv" in ausgabe


def test_start_script_setzt_die_schranke(tmp_path):
    skript = tmp_path / "zeig.py"
    skript.write_text(
        f"import os\nprint(os.environ.get({ENV_NUR_TROCKEN!r}))\n", encoding="utf-8"
    )
    prozess = start_script(skript, nur_trocken=True)
    ausgabe = prozess.stdout.read()
    prozess.wait(timeout=TEST_TIMEOUT_S)
    assert "1" in ausgabe


def test_start_script_setzt_die_schranke_nicht_von_selbst(tmp_path):
    skript = tmp_path / "zeig.py"
    skript.write_text(
        f"import os\nprint(os.environ.get({ENV_NUR_TROCKEN!r}, 'nicht gesetzt'))\n",
        encoding="utf-8",
    )
    prozess = start_script(skript)
    ausgabe = prozess.stdout.read()
    prozess.wait(timeout=TEST_TIMEOUT_S)
    assert "nicht gesetzt" in ausgabe


# ----------------------------------------------- der Weg an connect() vorbei
#
# `spotlab.connect()` ist nicht der einzige Weg zum echten Roboter. Wer direkt
# `verbinde()` oder `RealSpot.connect()` importiert, kam an der Obergrenze
# bisher vorbei -- und genau diesen Weg nimmt ein Agent, der ein fremdes
# Projekt startet. Die Kartenaufzeichnung nutzt dieselbe Funktion.

_DIREKT = """\
from pathlib import Path
from spotlab.config import Config
from spotlab.backends.real.verbindung import verbinde

def bauen(cfg):
    Path("ERREICHT").write_text("ja", encoding="utf-8")
    raise SystemExit("bis hierher haette es nie kommen duerfen")

try:
    verbinde(Config(ip="10.0.0.3", username="u"), robot_bauen=bauen,
             passwort_lesen=lambda u: "x")
except Exception as fehler:
    print("ABGEWIESEN:", type(fehler).__name__, fehler)
"""


def test_schranke_greift_auch_am_direkten_weg(tmp_path):
    ergebnis = _lauf(tmp_path, _DIREKT, SPOTLAB_NUR_TROCKEN="1")
    assert not (tmp_path / "ERREICHT").exists(), (
        "Der Roboter wurde trotz Schranke aufgebaut: " + ergebnis.stdout
    )
    assert "ABGEWIESEN" in ergebnis.stdout, ergebnis.stderr


def test_ohne_schranke_geht_der_direkte_weg_weiter(tmp_path):
    """Gegenprobe: sonst wuerde der Test oben auch bei kaputtem verbinde() gruen."""
    ergebnis = _lauf(tmp_path, _DIREKT)
    assert (tmp_path / "ERREICHT").exists(), ergebnis.stdout + ergebnis.stderr


_ENTFERNEN = """\
import os
from pathlib import Path
from spotlab.config import Config

os.environ.pop("SPOTLAB_NUR_TROCKEN", None)      # Skript raeumt die Schranke weg

from spotlab.backends.real.verbindung import verbinde

def bauen(cfg):
    Path("ERREICHT").write_text("ja", encoding="utf-8")
    raise SystemExit("bis hierher haette es nie kommen duerfen")

try:
    verbinde(Config(ip="10.0.0.3", username="u"), robot_bauen=bauen,
             passwort_lesen=lambda u: "x")
except Exception as fehler:
    print("ABGEWIESEN:", type(fehler).__name__)
"""


def test_skript_kann_die_schranke_nicht_selbst_entfernen(tmp_path):
    """Der Wert wird beim Import EINMAL eingefroren. Wuerde er bei jedem Aufruf
    frisch aus os.environ gelesen, genuegten zwei Zeilen, um ihn loszuwerden."""
    ergebnis = _lauf(tmp_path, _ENTFERNEN, SPOTLAB_NUR_TROCKEN="1")
    assert not (tmp_path / "ERREICHT").exists(), (
        "Die Schranke liess sich zur Laufzeit entfernen: " + ergebnis.stdout
    )
    assert "ABGEWIESEN" in ergebnis.stdout, ergebnis.stderr
