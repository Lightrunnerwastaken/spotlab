"""Batteriewechsel-Haltung: Spot setzt sich, rollt auf die Seite, Motoren aus.

Aufruf:
    python batteriewechsel.py                  # rollt nach links
    python batteriewechsel.py rechts           # rollt nach rechts
    python batteriewechsel.py links --uebernehmen
        # nimmt das Lease dem Tablet ab (bewusste Handlung, wird protokolliert)

Die Schülerfassade kennt kein „umlegen" — darum geht das rohe SDK-Kommando
über `spot.send()`. Danach liegt Spot auf der Seite, und die Motoren sind aus:
so lässt sich der Akku wechseln. Aufrichten danach über das Tablet
(Motoren ein, Self-right/Aufstehen) oder mit `spot.stand()`.

Voraussetzung: Die Motoren müssen VOR dem Start aus sein (am Tablet
ausschalten). Der Roboter lässt spotlab seinen Not-Aus-Endpunkt nicht
eintragen, solange die Motoren laufen (MotorsOnError).

Gemessen am 16.09.2026 (Software 5.1.3): Spot rollt in ~5 s auf die Seite
und schaltet die Motoren SELBST ab, sobald er kippt (Rollwinkel ≈ −113°,
Endlage ≈ −131°). Die Rückmeldung des Kommandos
(`battery_change_pose_feedback.status`) blieb dabei die ganze Zeit
STATUS_UNKNOWN — deshalb zählt hier der Körper, nicht die Meldung.
"""

import math
import sys
import time

import spotlab
from bosdyn.api.basic_command_pb2 import BatteryChangePoseCommand
from bosdyn.client.robot_command import RobotCommandBuilder

RICHTUNG = {
    "links": BatteryChangePoseCommand.Request.HINT_LEFT,
    "rechts": BatteryChangePoseCommand.Request.HINT_RIGHT,
}
WARTE_S = 40.0
AUF_DER_SEITE_GRAD = 80.0


def warte_bis_auf_der_seite(spot):
    """Wartet, bis Spot die Motoren selbst abgeschaltet hat; meldet den Rollwinkel."""
    if spot.robot is None:
        return "kein echter Roboter (Trockenlauf/Sim kennt das Kommando nicht)"
    ende = time.monotonic() + WARTE_S
    gemeldet = None
    while time.monotonic() < ende:
        zustand = spot.state
        winkel = math.degrees(zustand.roll)
        stufe = round(winkel / 15) * 15
        if stufe != gemeldet:
            print(f"  Rollwinkel {winkel:.0f}°")
            gemeldet = stufe
        if not zustand.powered:
            return f"Motoren von selbst aus bei Rollwinkel {winkel:.0f}°"
        time.sleep(0.25)
    zustand = spot.state
    winkel = math.degrees(zustand.roll)
    if abs(winkel) >= AUF_DER_SEITE_GRAD:
        return f"liegt auf der Seite (Rollwinkel {winkel:.0f}°), Motoren noch an"
    raise SystemExit(
        f"Spot liegt nach {WARTE_S:.0f} s nicht auf der Seite (Rollwinkel {winkel:.0f}°)."
    )


def main(argv):
    seite = next((a for a in argv if a in RICHTUNG), "links")
    uebernehmen = "--uebernehmen" in argv

    with spotlab.connect(take=uebernehmen) as spot:
        print(f"Akku: {spot.battery:.0f} %")
        spot.power_on()
        print(f"Rolle nach {seite} ...")
        spot.send(RobotCommandBuilder.battery_change_pose_command(dir_hint=RICHTUNG[seite]))
        print("  " + warte_bis_auf_der_seite(spot))
        if spot.is_powered:
            print("Motoren aus (sicher) ...")
            spot.power_off(safe=True)
        lage = "linken" if seite == "links" else "rechten"
        print(f"Fertig: Spot liegt auf der {lage} Seite, Motoren aus. Akku wechseln.")


if __name__ == "__main__":
    main(sys.argv[1:])
