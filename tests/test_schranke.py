import os
import subprocess
import sys
from pathlib import Path

from spotlab import ENV_NUR_TROCKEN
from spotlab.workshop.launcher import start_script

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
    prozess.wait()
    assert "--episoden|20|--archiv" in ausgabe


def test_start_script_setzt_die_schranke(tmp_path):
    skript = tmp_path / "zeig.py"
    skript.write_text(
        f"import os\nprint(os.environ.get({ENV_NUR_TROCKEN!r}))\n", encoding="utf-8"
    )
    prozess = start_script(skript, nur_trocken=True)
    ausgabe = prozess.stdout.read()
    prozess.wait()
    assert "1" in ausgabe


def test_start_script_setzt_die_schranke_nicht_von_selbst(tmp_path):
    skript = tmp_path / "zeig.py"
    skript.write_text(
        f"import os\nprint(os.environ.get({ENV_NUR_TROCKEN!r}, 'nicht gesetzt'))\n",
        encoding="utf-8",
    )
    prozess = start_script(skript)
    ausgabe = prozess.stdout.read()
    prozess.wait()
    assert "nicht gesetzt" in ausgabe
