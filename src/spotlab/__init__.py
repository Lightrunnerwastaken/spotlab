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
# Raum und Startpose des Uebungsraums. Die GUI reicht damit durch, was auf
# dem BILDSCHIRM steht, statt sich auf die Konfiguration zu verlassen: die
# bekam den Raum erst beim Klick in die Zeichnung, und wer nur startete, fuhr
# in gar keinem Raum -- Start (0, 0), quer durch die Waende. Und ein Laptop
# ohne eingerichteten Spot hat ueberhaupt keine Konfiguration.
ENV_RAUM = "SPOTLAB_RAUM"
ENV_RAUM_START = "SPOTLAB_RAUM_START"

# EINMAL beim Import eingefroren, nicht bei jedem Aufruf frisch gelesen.
# `os.environ.pop("SPOTLAB_NUR_TROCKEN")` in Zeile eins eines Skripts hätte die
# Obergrenze sonst aufgehoben — und genau solche Skripte schreibt der Agent,
# für den die Schranke gedacht ist.
NUR_TROCKEN = os.environ.get(ENV_NUR_TROCKEN) == "1"

NUR_TROCKEN_MELDUNG = (
    "Dieser Lauf wurde ohne Roboter gestartet und darf keinen anfordern. "
    "Starte das Programm selbst im Fenster, wenn der Spot fahren soll."
)

# Backends, die gar keinen Roboter erreichen können: kein Netzclient, kein
# Lease, kein Not-Aus-Endpunkt. Nur diese laufen unter `SPOTLAB_NUR_TROCKEN`.
#
# ERLAUBNISLISTE, keine Sperrliste. Ein neues Backend ist gesperrt, bis jemand
# es hier einträgt — und wer es einträgt, hat die Frage beantwortet, ob es den
# Spot bewegen kann. Andersherum wäre jedes künftige Backend versehentlich frei.
OHNE_ROBOTER = ("dryrun", "sim", "mujoco")


@contextlib.contextmanager
def connect(
    backend=None, runs_dir=None, script=None, take=False, config_path=None,
    nickname=None, raum=None,
):
    """Verbindet, zeichnet auf und baut am Ende garantiert sauber ab.

    Die Motoren gehen dabei NICHT an — `spot.power_on()` ist eine eigene Zeile,
    die jemand geschrieben haben muss.
    """
    from spotlab import protokoll
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
    # `sim` steht hier neben `dryrun`, weil die Schranke „darf den echten Spot
    # nicht bewegen" heisst — nicht „darf sich nicht bewegen". Beide haben
    # keinen Netzclient und kein Lease; sie können gar keinen Roboter erreichen.
    # Eine ERLAUBNISLISTE, keine Sperrliste: ein künftiges Backend ist gesperrt,
    # bis jemand es hier ausdrücklich einträgt.
    if NUR_TROCKEN and art not in OHNE_ROBOTER:
        raise SpotlabError(NUR_TROCKEN_MELDUNG)

    grenzen = cfg.limits if cfg else Limits()
    spitzname = nickname or (cfg.nickname if cfg else "")

    skript = Path(script) if script else _skript_pfad()
    ziel = Path(runs_dir) if runs_dir else _runs_verzeichnis(skript)
    recorder = RunRecorder(ziel, skript, backend=art, nickname=spitzname)
    # Ab hier landen Diagnosezeilen neben der Aufzeichnung. Ohne Ziel schreibt
    # protokoll.notiere() nichts — ein Import von spotlab legt keine Datei an.
    protokoll.setze_ziel(recorder.dir)

    if art == "dryrun":
        from spotlab.backends.dryrun import DryRunBackend

        roher_roboter, unten = None, DryRunBackend(recorder)
        recorder.event("verbunden", backend="dryrun")
    elif art in ("sim", "mujoco"):
        # `mujoco` ist der 2D-Sim mit einem 3D-Koerper (backends/mujoco.py):
        # dieselben Kommandos, dieselbe Gangkennlinie, dieselbe Antwort — dazu
        # Kameras, Tiefengitter und Kollision an der Mesh-Geometrie. Er braucht
        # das Extra `spotlab[sim]` und `spotsim` aus matura-spot; fehlt eines,
        # sagt der Fehler, was zu tun ist.
        from spotlab.backends.sim import SimBackend
        from spotlab.config import startpose_aus
        from spotlab.welt.raum import raum_laden

        # Reihenfolge: Argument vor Umgebung vor Konfiguration. Ein Skript, das
        # seinen Raum nennt, soll nicht davon abhaengen, was zuletzt in der GUI
        # stand; die GUI wiederum soll nicht davon abhaengen, was zuletzt in der
        # Konfiguration gelandet ist.
        name = raum or os.environ.get(ENV_RAUM) or (cfg.raum if cfg else "")
        gewaehlt = (raum_laden(name, workspace=cfg.workspace if cfg else None)
                    if name else None)
        roher_start = os.environ.get(ENV_RAUM_START) or (cfg.raum_start if cfg else "")
        start = startpose_aus(roher_start)
        if gewaehlt is not None and start is None:
            start = gewaehlt.start

        if art == "mujoco":
            from spotlab.backends.mujoco import MujocoBackend

            unten = MujocoBackend(
                recorder, raum=gewaehlt, start=start,
                ansicht_ziel=recorder.dir / "ansicht.jpg",
            )
        else:
            unten = SimBackend(recorder, raum=gewaehlt, start=start, treppen=grenzen.treppen)
        roher_roboter = None
        # Der Hinweis gehört in die Aufzeichnung, nicht nur in den Docstring:
        # wer den Lauf später ansieht, muss sehen, dass hier nichts erprobt ist.
        # Dasselbe fuer den Treppengang: die Puppe spielt auf Stufen den ebenen
        # Gang, und der Lauf sagt es (Stufe 13, Wahl C des Autors).
        zusatz = {"treppengang": unten.treppengang()} if unten.treppengang() else {}
        recorder.event(
            "verbunden", backend=art, raum=name or None,
            hinweis=unten.hinweis_zur_gueltigkeit(), **zusatz,
        )
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
        # Verschachtelt, nicht hintereinander: `abtaster.stop()` stand hier
        # ungeschützt VOR `spot.close()`. Wirft es — oder unterbricht Strg-C es
        # genau dort —, baute die Sitzung nie ab: Motoren an, Lease gehalten,
        # Not-Aus-Endpunkt registriert, und der Lauf blieb in lauf.json auf
        # „läuft" stehen. Der Abtaster ist der unwichtigste der drei Schritte
        # und stand am gefährlichsten Platz.
        # Zuerst die Markierung: ab hier schweigt der Abtaster, und ohne sie
        # gälte der Lauf für den NOT-AUS-Knopf schon als tot, obwohl der Spot
        # noch unter Strom steht.
        recorder.abbau_beginnt()
        try:
            abtaster.stop()
        finally:
            try:
                spot.close()
            finally:
                # Vor `finish()`: der Bericht gehört in dasselbe `lauf.json`,
                # und `finish()` schreibt es zum letzten Mal.
                #
                # Eigener try-Block, weil er im Abbaupfad steht: eine kaputte
                # Kennlinie darf einen Lauf nicht offen lassen. Lieber ein
                # Lauf ohne Bericht als einer, der für immer auf „läuft" steht.
                try:
                    if hasattr(unten, "bericht"):
                        recorder.set_robot_info(sim=unten.bericht())
                except Exception as fehler:
                    protokoll.notiere("Sim-Bericht nicht geschrieben", fehler)
                recorder.finish(ergebnis, fehlertext)
                protokoll.setze_ziel(None)


def _skript_pfad():
    haupt = sys.argv[0] if sys.argv else ""
    pfad = Path(haupt).resolve() if haupt else None
    return pfad if pfad and pfad.suffix == ".py" and pfad.exists() else None


def _runs_verzeichnis(skript):
    wurzel = skript.parent if skript else Path.cwd()
    return wurzel / "runs"
