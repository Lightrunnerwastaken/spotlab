"""spotlab — den Spot programmieren, ohne vorher SDK-Betriebsmechanik zu lernen."""

import contextlib
import os
import sys
from pathlib import Path

__version__ = "0.1.0"

ENV_BACKEND = "SPOTLAB_BACKEND"

# Obergrenze, nicht Vorgabe. Gesetzt von allem, was ohne Aufsicht startet —
# heute vom MCP-Server, wenn ein Agent ein Skript startet.
ENV_NUR_TROCKEN = "SPOTLAB_NUR_TROCKEN"


@contextlib.contextmanager
def connect(
    backend=None, runs_dir=None, script=None, take=False, config_path=None, nickname=None
):
    """Verbindet, zeichnet auf und baut am Ende garantiert sauber ab.

    Die Motoren gehen dabei NICHT an — `spot.power_on()` ist eine eigene Zeile,
    die jemand geschrieben haben muss.
    """
    from spotlab.api.spot import Spot
    from spotlab.config import Limits, load_config
    from spotlab.errors import ConfigMissing, LeaseLost, SpotlabError
    from spotlab.record.run import RunRecorder
    from spotlab.record.sampler import StateSampler

    try:
        cfg = load_config(config_path) if config_path else load_config()
    except ConfigMissing:
        cfg = None

    art = backend or os.environ.get(ENV_BACKEND) or (cfg.default_backend if cfg else "dryrun")

    # Die Schranke steht VOR dem RunRecorder: sonst entstünde ein leeres
    # Lauf-Verzeichnis für einen Lauf, den es nie gab.
    #
    # SPOTLAB_BACKEND allein genügt hier nicht — die Zeile darüber liest
    # `backend or os.environ.get(...)`, ein explizites backend="real" im Skript
    # überschreibt die Variable also. Abgewiesen statt stillschweigend
    # heruntergestuft: ein Skript, das glaubt, es fahre den echten Spot,
    # meldet sonst Unsinn und niemand merkt es.
    if os.environ.get(ENV_NUR_TROCKEN) == "1" and art != "dryrun":
        raise SpotlabError(
            "Dieser Lauf wurde ohne Roboter gestartet und darf keinen anfordern. "
            "Starte das Programm selbst im Fenster, wenn der Spot fahren soll."
        )

    grenzen = cfg.limits if cfg else Limits()
    spitzname = nickname or (cfg.nickname if cfg else "")

    skript = Path(script) if script else _skript_pfad()
    ziel = Path(runs_dir) if runs_dir else _runs_verzeichnis(skript)
    recorder = RunRecorder(ziel, skript, backend=art, nickname=spitzname)

    if art == "dryrun":
        from spotlab.backends.dryrun import DryRunBackend

        roher_roboter, unten = None, DryRunBackend(recorder)
        recorder.event("verbunden", backend="dryrun")
    else:
        from spotlab.backends.real import RealSpot

        if cfg is None:
            recorder.finish("fehler", "Keine Konfiguration")
            raise ConfigMissing("Keine Konfiguration. Einrichten mit `spotlab login`.")
        try:
            unten = RealSpot.connect(cfg, recorder=recorder, take=take)
        except BaseException as fehler:
            recorder.finish("fehler", f"{type(fehler).__name__}: {fehler}")
            raise
        roher_roboter = unten.robot

    # Abtaster vor dem Spot: die Fassade braucht ihn, um im Messfenster die Rate
    # zu heben.
    abtaster = StateSampler(unten, recorder)
    spot = Spot(
        unten,
        recorder=recorder,
        limits=grenzen,
        robot=roher_roboter,
        workspace=(cfg.workspace if cfg else None),
        active_map=(cfg.active_map if cfg else None),
        sampler=abtaster,
    )
    abtaster.start()

    ergebnis, fehlertext = "ok", None
    try:
        yield spot
    except KeyboardInterrupt:
        ergebnis, fehlertext = "abgebrochen", "Vom Benutzer abgebrochen (Ctrl-C)"
        raise
    except LeaseLost as fehler:
        ergebnis, fehlertext = "lease_verloren", str(fehler)
        raise
    except SpotlabError as fehler:
        ergebnis, fehlertext = "fehler", str(fehler)
        raise
    except BaseException as fehler:
        ergebnis, fehlertext = "fehler", f"{type(fehler).__name__}: {fehler}"
        raise
    finally:
        abtaster.stop()
        try:
            spot.close()
        finally:
            recorder.finish(ergebnis, fehlertext)


def _skript_pfad():
    haupt = sys.argv[0] if sys.argv else ""
    pfad = Path(haupt).resolve() if haupt else None
    return pfad if pfad and pfad.suffix == ".py" and pfad.exists() else None


def _runs_verzeichnis(skript):
    wurzel = skript.parent if skript else Path.cwd()
    return wurzel / "runs"
