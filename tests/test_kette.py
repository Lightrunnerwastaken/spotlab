"""Die ganze Kette ohne Roboter: starten → beobachten → stoppen.

Der wichtigste Test des GUI-Plans: er deckt die Naht ab, an der Oberfläche und
Fundament zusammenstossen — echtes Skript, echter Unterprozess, echter
Beobachter, echter Stopp.
"""

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.gui.watcher import RunScanner  # noqa: E402
from spotlab.workshop.control import ist_aktiv, stoppe_freundlich  # noqa: E402
from spotlab.workshop.launcher import start_script  # noqa: E402
from spotlab.workshop.project import create_project  # noqa: E402

SKRIPT = """
import spotlab

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    for _ in range(200):
        spot.walk(vx=0.1, duration=0.2)
"""


def _warte_bis(bedingung, grenze_s=15.0, takt_s=0.1):
    ende = time.monotonic() + grenze_s
    while time.monotonic() < ende:
        wert = bedingung()
        if wert:
            return wert
        time.sleep(takt_s)
    return None


def test_starten_beobachten_stoppen(tmp_path):
    projekt = create_project("kette", tmp_path)
    (projekt / "lang.py").write_text(SKRIPT, encoding="utf-8")

    prozess = start_script(projekt / "lang.py", dryrun=True)
    try:
        scanner = RunScanner(tmp_path)          # Arbeitsordner, nicht runs/

        gefunden = _warte_bis(
            lambda: [p for art, p in scanner.tick() if art == "lauf_begonnen"]
        )
        assert gefunden, "Der Beobachter hat den Lauf nicht aufgegriffen"
        lauf = Path(gefunden[0])

        zustaende = _warte_bis(lambda: [d for art, d in scanner.tick() if art == "zustand"])
        assert zustaende, "Keine Telemetrie angekommen"
        assert "battery" in zustaende[0]["daten"]

        stoppe_freundlich(lauf)
        assert _warte_bis(lambda: prozess.poll() is not None), \
            "Der freundliche Stopp hat den Lauf nicht beendet"

        _warte_bis(lambda: not ist_aktiv(lauf))
        daten = json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))
        assert daten["ergebnis"] == "abgebrochen"
    finally:
        if prozess.poll() is None:
            prozess.kill()
            prozess.wait()
