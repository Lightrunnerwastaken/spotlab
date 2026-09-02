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
from tests_zeitgrenzen import TEST_TIMEOUT_S  # noqa: E402

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
            prozess.wait(timeout=TEST_TIMEOUT_S)


# ------------------------------------- abtaster.stop() vor spot.close() (S1.6)


@pytest.fixture
def klemmender_abtaster(monkeypatch):
    """`StateSampler.stop()` wirft -- und der Thread wird trotzdem angehalten.

    Die Aussage der beiden Tests darunter ist, dass der Abbau einen KAPUTTEN
    Abtaster ueberlebt. Waehrend des Tests muss `stop()` also wirklich werfen.

    Die Folge davon war ein Leck: der Abtaster-Thread wurde nie angehalten und
    lief als Daemon bis zum Prozessende weiter, mit 10 Hz gegen ein
    `tmp_path`, das pytest laengst geloescht hatte. Ab diesen beiden Tests
    meldete JEDER folgende Test zwei lebende `spotlab-sampler`.

    Das war nicht bloss unsauber: die Dauerlast hat
    `test_messfahrt_ende_zu_ende.py::test_die_messfahrt_meldet_keine_falschen_luecken`
    in einem von drei vollstaendigen Laeufen gekippt -- ein Test, der allein
    zuverlaessig gruen ist. Auf einem geteilten CI-Rechner ist das schlechter,
    nicht besser.

    Die Attrappe merkt sich, WELCHE Instanz getroffen wurde, und im Teardown
    laeuft das echte `stop()` darauf. `stop()` hat eine eigene Zeitgrenze
    (2 s Join), es kann hier also nicht haengen.
    """
    from spotlab.record.sampler import StateSampler

    echtes_stop = StateSampler.stop
    getroffen = []

    def kaputtes_stop(self, *args, **kwargs):
        getroffen.append(self)
        raise RuntimeError("Abtaster klemmt")

    monkeypatch.setattr(StateSampler, "stop", kaputtes_stop)
    yield
    for abtaster in dict.fromkeys(getroffen):      # jede Instanz genau einmal
        echtes_stop(abtaster)


def test_ein_kaputter_abtaster_verhindert_den_abbau_nicht(
    tmp_path, monkeypatch, klemmender_abtaster
):
    """`abtaster.stop()` stand ausserhalb jedes try/finally, direkt VOR
    `spot.close()`. Wirft es -- oder wird es unterbrochen -- baut die Sitzung
    nie ab: Motoren an, Lease gehalten, Not-Aus-Endpunkt registriert.
    """
    import spotlab

    geschlossen = []

    with pytest.raises(RuntimeError, match="Abtaster klemmt"):
        with spotlab.connect(backend="dryrun", runs_dir=tmp_path) as spot:
            monkeypatch.setattr(
                type(spot), "close", lambda self: geschlossen.append(True)
            )

    assert geschlossen == [True], "spot.close() wurde uebersprungen"


def test_der_lauf_wird_trotz_kaputtem_abtaster_abgeschlossen(
    tmp_path, klemmender_abtaster
):
    """recorder.finish() muss ebenfalls laufen -- sonst bleibt lauf.json auf
    'laeuft' stehen und die GUI zeigt den Lauf ewig als aktiv."""
    import json

    import spotlab

    with pytest.raises(RuntimeError):
        with spotlab.connect(backend="dryrun", runs_dir=tmp_path):
            pass

    lauf = next(tmp_path.glob("*/lauf.json"))
    assert json.loads(lauf.read_text(encoding="utf-8"))["ergebnis"] != "läuft"


def test_der_abtaster_ueberlebt_diese_tests_nicht(tmp_path, monkeypatch):
    """Die Gegenprobe zur Vorrichtung: nach dem Test lebt kein Abtaster mehr.

    Ohne sie waere `klemmender_abtaster` eine Behauptung -- und genau diese
    Sorte Leck faellt sonst erst auf, wenn ein ganz anderer Test kippt.
    """
    import threading

    import spotlab
    from spotlab.record.sampler import StateSampler

    vorher = {t for t in threading.enumerate() if t.name == "spotlab-sampler"}

    echtes_stop = StateSampler.stop
    getroffen = []

    def kaputtes_stop(self, *args, **kwargs):
        getroffen.append(self)
        raise RuntimeError("klemmt")

    monkeypatch.setattr(StateSampler, "stop", kaputtes_stop)
    with pytest.raises(RuntimeError):
        with spotlab.connect(backend="dryrun", runs_dir=tmp_path):
            pass
    assert getroffen, "der gepatchte stop() wurde gar nicht gerufen"

    # Vor dem Aufraeumen MUSS der Thread noch leben -- sonst pruefte der Test
    # nichts.
    assert getroffen[0]._thread is not None and getroffen[0]._thread.is_alive()

    for abtaster in dict.fromkeys(getroffen):
        echtes_stop(abtaster)

    nachher = {t for t in threading.enumerate()
               if t.name == "spotlab-sampler" and t.is_alive()}
    assert nachher <= vorher, f"Abtaster ueberlebt: {nachher - vorher}"


def test_connect_nimmt_den_raum_aus_dem_argument(tmp_path, monkeypatch):
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    with spotlab.connect(runs_dir=tmp_path, raum="leer") as spot:
        assert spot.backend._raum is not None
        assert spot.backend._raum.name == "Leer"


def test_verbunden_ereignis_nennt_den_raum(tmp_path, monkeypatch):
    """Die Ansicht liest daraus, welcher Raum gilt."""
    import json

    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    with spotlab.connect(runs_dir=tmp_path, raum="leer") as spot:
        verzeichnis = spot.recorder.dir
    zeilen = [json.loads(z) for z
              in (verzeichnis / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    verbunden = [z for z in zeilen if z["art"] == "verbunden"][0]
    assert verbunden["daten"]["raum"] == "leer"
