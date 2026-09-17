"""Lage: Batteriewechsel-Haltung und Aufrichten — der Kern hinter den Knöpfen im Tab „Fahren".

Zwei Rollkommandos kennt das SDK, und nur diese zwei: die
BATTERIEWECHSEL-HALTUNG (`battery_change_pose_command`, nach links oder rechts —
Spot setzt sich, rollt auf die Seite, der Akku wird zugänglich) und SELF-RIGHT
(`selfright_command`, zurück auf die Füsse). Ein „ganz auf den Rücken" gibt es
nicht; die Akku-Haltung ist das Weiteste, was die API rollt (Endlage etwa 130°),
von dort kippt ein Mensch ihn von Hand. Beides geht über `spot.send()`, weil die
Schülerfassade kein „umlegen" kennt — und das ist Absicht: ein Roboter, der sich
auf Knopfdruck auf die Seite legt, gehört nicht in die erste Programmierstunde.

GEMESSEN am 16.09.2026 (Software 5.1.3, Akku 18 %): Spot rollt in ~5 s auf die
Seite und schaltet die Motoren SELBST ab, sobald er kippt (Rollwinkel ≈ −113°,
Endlage ≈ −131° nach links). Die Rückmeldung des Kommandos
(`battery_change_pose_feedback.status`) blieb dabei die ganze Zeit
STATUS_UNKNOWN — deshalb zählt hier der KÖRPER (`state.roll`, `state.powered`),
nie die Meldung. Self-right brachte ihn in ~3.5 s von −134° auf 0°; erst
`RUHE_S` ruhig heisst oben, denn unterwegs geht der Winkel durch null.

Voraussetzung: die Motoren müssen VOR dem Verbinden aus sein. Der Roboter
verweigert `SetEstopConfig` bei laufenden Motoren (`MotorsOnError`), und
spotlab trägt seinen Not-Aus-Endpunkt genau dort ein. Und das Lease: hält es
das Tablet, geht es nur mit Übernahme (`--uebernehmen`, `connect(take=True)`)
— eine bewusste, protokollierte Handlung, nie die Vorgabe.

Das Hauptprogramm unten ist PAKETCODE, wie bei der Gehzeit: der Knopf im Tab
startet diese Datei, nicht die Kopie im Arbeitsordner — ein Knopf, der „rollt
auf die Seite" verspricht, darf nicht etwas anderes tun, weil jemand das
Beispiel bearbeitet hat. `Beispiele/batteriewechsel.py` und
`Beispiele/aufrichten.py` bleiben daneben zum Lesen und rufen denselben Kern.
"""

import math
import time
from pathlib import Path

from spotlab.errors import SpotlabError

SKRIPT = Path(__file__)              # das startet der Knopf im Tab „Fahren"
AKTIONEN = ("akku", "aufrichten")
SEITEN = ("links", "rechts")
WARTE_S = 40.0                       # so lange darf das Rollen dauern (gemessen: 5 s)
AUF_DER_SEITE_GRAD = 80.0            # ab hier liegt er auf der Seite
AUFRECHT_GRAD = 15.0                 # darunter ist er aufrecht
RUHE_S = 1.5                         # so lange muss er aufrecht BLEIBEN
TAKT_S = 0.25
STUFE_GRAD = 15.0                    # der Verlauf wird in diesen Schritten gesagt


def rollwinkel(zustand):
    """Der Rollwinkel des Körpers in Grad — links liegen ist negativ."""
    return math.degrees(zustand.roll)


def _richtung(seite):
    if seite not in SEITEN:
        raise SpotlabError(f"Unbekannte Seite „{seite}“ — „links“ oder „rechts“.")
    from bosdyn.api.basic_command_pb2 import BatteryChangePoseCommand

    return {"links": BatteryChangePoseCommand.Request.HINT_LEFT,
            "rechts": BatteryChangePoseCommand.Request.HINT_RIGHT}[seite]


def _echt(spot):
    """Nur der echte Roboter hat eine Lage; Trockenlauf und Sims kennen das Kommando nicht."""
    return getattr(spot, "robot", None) is not None


def _stufe(melde, winkel, gemeldet):
    """Den Verlauf in Stufen sagen, nicht jede Abtastung."""
    stufe = round(winkel / STUFE_GRAD) * STUFE_GRAD
    if stufe != gemeldet:
        melde(f"  Rollwinkel {winkel:.0f}°")
    return stufe


def umlegen(spot, seite="links", melde=print, jetzt=time.monotonic, schlaf=time.sleep,
            warte_s=WARTE_S):
    """In die Batteriewechsel-Haltung: Motoren an, rollen, warten, bis er liegt.

    Gibt den Befund als Text zurück; wirft `SpotlabError`, wenn Spot nach
    `warte_s` nicht auf der Seite liegt — und lässt ihn dann unter Strom, denn
    aufrecht und unter Strom ist der Zustand, in dem ein Mensch nachsehen soll.
    """
    richtung = _richtung(seite)
    from bosdyn.client.robot_command import RobotCommandBuilder

    lage = "linken" if seite == "links" else "rechten"
    spot.power_on()
    melde(f"Rolle nach {seite} …")
    spot.send(RobotCommandBuilder.battery_change_pose_command(dir_hint=richtung))
    if not _echt(spot):
        return ("kein echter Roboter (Trockenlauf und Sims kennen keine Lage) — "
                "das Kommando ist geschickt.")
    ende = jetzt() + warte_s
    gemeldet = None
    winkel = 0.0
    while jetzt() < ende:
        zustand = spot.state
        winkel = rollwinkel(zustand)
        gemeldet = _stufe(melde, winkel, gemeldet)
        if not zustand.powered:
            return (f"Motoren von selbst aus bei Rollwinkel {winkel:.0f}° — Spot liegt auf der "
                    f"{lage} Seite. Akku wechseln.")
        schlaf(TAKT_S)
    if abs(winkel) >= AUF_DER_SEITE_GRAD:
        melde("Motoren aus (sicher) …")
        spot.power_off(safe=True)
        return (f"Spot liegt auf der {lage} Seite (Rollwinkel {winkel:.0f}°), Motoren aus. "
                f"Akku wechseln.")
    raise SpotlabError(
        f"Spot liegt nach {warte_s:.0f} s nicht auf der Seite (Rollwinkel {winkel:.0f}°). "
        f"Sitzt er auf ebenem Boden, mit Platz auf der {lage} Seite? Am Tablet nachsehen — "
        f"die Motoren sind noch an."
    )


def aufrichten(spot, melde=print, jetzt=time.monotonic, schlaf=time.sleep, warte_s=WARTE_S):
    """Self-right, dann hinsetzen. Aus der Seiten- oder Rückenlage — oder aus dem Sitzen.

    Gibt den Befund als Text zurück; wirft `SpotlabError`, wenn er nach
    `warte_s` nicht aufrecht ist. Aufrecht heisst: `AUFRECHT_GRAD` unterschritten
    und `RUHE_S` lang geblieben — der Winkel geht beim Rollen durch null.
    """
    from bosdyn.client.robot_command import RobotCommandBuilder

    if not _echt(spot):
        spot.power_on()
        spot.send(RobotCommandBuilder.selfright_command())
        spot.sit()
        return ("kein echter Roboter (Trockenlauf und Sims kennen keine Lage) — "
                "Self-right geschickt, hingesetzt.")
    vorher = rollwinkel(spot.state)
    melde(f"Rollwinkel jetzt {vorher:.0f}°")
    spot.power_on()
    if abs(vorher) >= AUFRECHT_GRAD:
        melde("Richte auf …")
        spot.send(RobotCommandBuilder.selfright_command())
        ende = jetzt() + warte_s
        gemeldet = None
        ruhig_seit = None
        winkel = vorher
        while True:
            nun = jetzt()
            if nun >= ende:
                raise SpotlabError(
                    f"Spot ist nach {warte_s:.0f} s nicht aufrecht (Rollwinkel {winkel:.0f}°). "
                    f"Liegt etwas im Weg? Am Tablet nachsehen — die Motoren sind noch an."
                )
            winkel = rollwinkel(spot.state)
            gemeldet = _stufe(melde, winkel, gemeldet)
            if abs(winkel) < AUFRECHT_GRAD:
                ruhig_seit = nun if ruhig_seit is None else ruhig_seit
                if nun - ruhig_seit >= RUHE_S:
                    melde(f"  aufrecht (Rollwinkel {winkel:.0f}°)")
                    break
            else:
                ruhig_seit = None
            schlaf(TAKT_S)
    else:
        melde("Spot liegt schon aufrecht.")
    melde("Setze hin …")
    spot.sit()
    return "Spot sitzt aufrecht. Die Motoren gehen beim Beenden des Laufs aus."


# ------------------------------------------------------------ Hauptprogramm


def argumente(argv):
    """(aktion, seite, runs, uebernehmen) aus der Kommandozeile — oder ein Fehler, der sagt, was fehlt.

        lage.py akku [links|rechts] [--runs ORDNER] [--uebernehmen]
        lage.py aufrichten            [--runs ORDNER] [--uebernehmen]
    """
    argv = list(argv)
    if not argv or argv[0] not in AKTIONEN:
        raise SpotlabError("Die Aktion fehlt: „akku“ (auf die Seite rollen) oder „aufrichten“.")
    aktion = argv[0]
    seite, runs, uebernehmen = "links", None, False
    rest = argv[1:]
    while rest:
        wort = rest.pop(0)
        if wort == "--runs":
            if not rest:
                raise SpotlabError("Nach --runs fehlt der Ordner.")
            runs = rest.pop(0)
        elif wort == "--uebernehmen":
            uebernehmen = True
        elif wort.startswith("--"):
            raise SpotlabError(f"Unbekannte Option {wort}.")
        elif wort in SEITEN:
            seite = wort
        else:
            raise SpotlabError(f"Unbekannte Seite „{wort}“ — „links“ oder „rechts“.")
    return aktion, seite, runs, uebernehmen


def _hauptprogramm(argv=None):
    """Das Programm hinter den Knöpfen — PAKETCODE, siehe oben.

    Das Lauf-Verzeichnis wird AUSDRÜCKLICH gesetzt (`--runs`, sonst
    `SPOTLAB_RUNS_DIR`, sonst `./runs`): diese Datei liegt im installierten
    Paket, und `start_script` setzt `cwd` auf den Skriptordner — ohne die
    Angabe schriebe der Lauf zwischen den Quelltext.
    """
    import os
    import sys

    import spotlab

    aktion, seite, runs, uebernehmen = argumente(sys.argv[1:] if argv is None else argv)
    runs = runs or os.environ.get("SPOTLAB_RUNS_DIR") or str(Path.cwd() / "runs")
    with spotlab.connect(runs_dir=runs, script=__file__, take=uebernehmen) as spot:
        print(f"Akku: {spot.battery:.0f} %")
        if aktion == "akku":
            print("Fertig: " + umlegen(spot, seite))
        else:
            print("Fertig: " + aufrichten(spot))


if __name__ == "__main__":
    _hauptprogramm()
