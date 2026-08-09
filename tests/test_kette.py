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


# ------------------------------------- abtaster.stop() vor spot.close() (S1.6)


def test_ein_kaputter_abtaster_verhindert_den_abbau_nicht(tmp_path, monkeypatch):
    """`abtaster.stop()` stand ausserhalb jedes try/finally, direkt VOR
    `spot.close()`. Wirft es -- oder wird es unterbrochen -- baut die Sitzung
    nie ab: Motoren an, Lease gehalten, Not-Aus-Endpunkt registriert.
    """
    import spotlab
    from spotlab.record.sampler import StateSampler

    geschlossen = []

    def kaputtes_stop(self):
        raise RuntimeError("Abtaster klemmt")

    monkeypatch.setattr(StateSampler, "stop", kaputtes_stop)

    with pytest.raises(RuntimeError, match="Abtaster klemmt"):
        with spotlab.connect(backend="dryrun", runs_dir=tmp_path) as spot:
            monkeypatch.setattr(
                type(spot), "close", lambda self: geschlossen.append(True)
            )

    assert geschlossen == [True], "spot.close() wurde uebersprungen"


def test_der_lauf_wird_trotz_kaputtem_abtaster_abgeschlossen(tmp_path, monkeypatch):
    """recorder.finish() muss ebenfalls laufen -- sonst bleibt lauf.json auf
    'laeuft' stehen und die GUI zeigt den Lauf ewig als aktiv."""
    import json

    import spotlab
    from spotlab.record.sampler import StateSampler

    monkeypatch.setattr(
        StateSampler, "stop", lambda self: (_ for _ in ()).throw(RuntimeError("klemmt"))
    )
    with pytest.raises(RuntimeError):
        with spotlab.connect(backend="dryrun", runs_dir=tmp_path):
            pass

    lauf = next(tmp_path.glob("*/lauf.json"))
    assert json.loads(lauf.read_text(encoding="utf-8"))["ergebnis"] != "läuft"
