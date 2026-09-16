"""Aufrichten nach dem Batteriewechsel: Spot rollt sich zurück und setzt sich hin.

Aufruf:
    python aufrichten.py                 # Lease holen (muss frei sein)
    python aufrichten.py --uebernehmen   # Lease dem Tablet abnehmen (wird protokolliert)

Gegenstück zu `batteriewechsel.py`: rohes SDK-Kommando `selfright_command()`
über `spot.send()`. Danach sitzt Spot aufrecht; die Motoren gehen beim
Beenden des Laufs aus (spotlab-Abbau). Weiter geht es am Tablet oder mit
einem eigenen Programm (`spot.power_on()`, `spot.stand()`).

Voraussetzung: Motoren aus beim Start (siehe batteriewechsel.py, MotorsOnError).
Der Erfolg wird am Körper gemessen (Rollwinkel), nicht an der Rückmeldung.
"""

import math
import sys
import time

import spotlab
from bosdyn.client.robot_command import RobotCommandBuilder

WARTE_S = 40.0
AUFRECHT_GRAD = 15.0
RUHE_S = 1.5


def rollwinkel(spot):
    return math.degrees(spot.state.roll)


def warte_bis_aufrecht(spot):
    """Wartet, bis der Rollwinkel klein ist und so bleibt; meldet den Verlauf."""
    if spot.robot is None:
        return "kein echter Roboter (Trockenlauf/Sim kennt das Kommando nicht)"
    ende = time.monotonic() + WARTE_S
    gemeldet = None
    ruhig_seit = None
    winkel = rollwinkel(spot)
    while time.monotonic() < ende:
        winkel = rollwinkel(spot)
        stufe = round(winkel / 15) * 15
        if stufe != gemeldet:
            print(f"  Rollwinkel {winkel:.0f}°")
            gemeldet = stufe
        if abs(winkel) < AUFRECHT_GRAD:
            if ruhig_seit is None:
                ruhig_seit = time.monotonic()
            elif time.monotonic() - ruhig_seit >= RUHE_S:
                return f"aufrecht (Rollwinkel {winkel:.0f}°)"
        else:
            ruhig_seit = None
        time.sleep(0.25)
    raise SystemExit(
        f"Spot ist nach {WARTE_S:.0f} s nicht aufrecht (Rollwinkel {winkel:.0f}°)."
    )


def main(argv):
    uebernehmen = "--uebernehmen" in argv

    with spotlab.connect(take=uebernehmen) as spot:
        print(f"Akku: {spot.battery:.0f} %")
        vorher = rollwinkel(spot)
        print(f"Rollwinkel jetzt {vorher:.0f}°")
        spot.power_on()
        if abs(vorher) >= AUFRECHT_GRAD:
            print("Richte auf ...")
            spot.send(RobotCommandBuilder.selfright_command())
            print("  " + warte_bis_aufrecht(spot))
        else:
            print("Spot liegt schon aufrecht.")
        print("Setze hin ...")
        spot.sit()
        print("Fertig: Spot sitzt aufrecht. Die Motoren gehen beim Beenden aus.")


if __name__ == "__main__":
    main(sys.argv[1:])
