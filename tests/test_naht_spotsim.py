"""Die Naht zu matura-spot: genau EINE Datei importiert `spotsim`.

Zwei Repos, zwei Regeln: `spotsim` importiert nie `spotlab` (matura-spot,
CLAUDE.md), und spotlab holt sich die Puppe nur in `backends/mujoco.py`
hinter dem Extra `[sim]`. Ein zweiter Import anderswo waere der Anfang einer
Kopplung, die niemand entschieden hat -- und er fiele erst auf, wenn ein
Laptop ohne matura-spot beim Start stirbt.
"""

import ast
from pathlib import Path

QUELLEN = Path(__file__).resolve().parents[1] / "src" / "spotlab"
ERLAUBT = QUELLEN / "backends" / "mujoco.py"


def _importiert_spotsim(pfad):
    for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Import):
            if any(a.name.split(".")[0] == "spotsim" for a in knoten.names):
                return True
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            if knoten.module.split(".")[0] == "spotsim":
                return True
    return False


def test_nur_das_mujoco_backend_importiert_spotsim():
    taeter = [p.relative_to(QUELLEN) for p in QUELLEN.rglob("*.py")
              if p != ERLAUBT and _importiert_spotsim(p)]
    assert taeter == [], f"spotsim ausserhalb von backends/mujoco.py importiert: {taeter}"
    assert _importiert_spotsim(ERLAUBT)


def test_die_gui_bleibt_frei_von_mujoco():
    """Dieselbe Regel wie bei bosdyn: die GUI rendert nichts selbst, sie liest
    ein Bild aus dem Lauf-Verzeichnis."""
    for pfad in (QUELLEN / "gui").rglob("*.py"):
        for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            namen = ()
            if isinstance(knoten, ast.Import):
                namen = tuple(a.name.split(".")[0] for a in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen = (knoten.module.split(".")[0],)
            assert not set(namen) & {"mujoco", "spotsim"}, f"{pfad.name} importiert {namen}"
