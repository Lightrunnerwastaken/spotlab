"""Aufrichten nach dem Batteriewechsel: Spot rollt sich zurück und setzt sich hin.

Aufruf:
    python aufrichten.py                 # Lease holen (muss frei sein)
    python aufrichten.py --uebernehmen   # Lease dem Tablet abnehmen (wird protokolliert)

Dasselbe tut der Knopf „⬆ Aufrichten" im Reiter „Fahren" — der startet aber den
Kern im Paket (`spotlab.workshop.lage`), nicht diese Datei. Diese Datei ist zum
Lesen und Ändern da; sie ruft denselben Kern.

Gegenstück zu `batteriewechsel.py`: das rohe SDK-Kommando `selfright_command()`
über `spot.send()`, dann `spot.sit()`. Es ist auch der Weg aus der Rückenlage,
etwa nach dem Auspacken aus dem Koffer. Danach sitzt Spot aufrecht; die
Motoren gehen beim Beenden des Laufs aus (spotlab-Abbau). Weiter geht es am
Tablet oder mit einem eigenen Programm (`spot.power_on()`, `spot.stand()`).

Voraussetzung: Motoren aus beim Start (siehe batteriewechsel.py, MotorsOnError).
Der Erfolg wird am Körper gemessen (Rollwinkel), nicht an der Rückmeldung.
"""

import sys

import spotlab
from spotlab.workshop import lage

with spotlab.connect(take="--uebernehmen" in sys.argv) as spot:
    print(f"Akku: {spot.battery:.0f} %" if spot.battery is not None else "Akku: unbekannt")
    print("Fertig: " + lage.aufrichten(spot))
