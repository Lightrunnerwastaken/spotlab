"""Batteriewechsel-Haltung: Spot setzt sich, rollt auf die Seite, Motoren aus.

Aufruf:
    python batteriewechsel.py                  # rollt nach links
    python batteriewechsel.py rechts           # rollt nach rechts
    python batteriewechsel.py links --uebernehmen
        # nimmt das Lease dem Tablet ab (bewusste Handlung, wird protokolliert)

Dasselbe tut der Knopf „🔋 Akku wechseln" im Reiter „Fahren" — der startet aber
den Kern im Paket (`spotlab.workshop.lage`), nicht diese Datei. Diese Datei ist
zum Lesen und Ändern da; sie ruft denselben Kern.

Die Schülerfassade kennt kein „umlegen" — der Kern schickt das rohe
SDK-Kommando über `spot.send()`. Danach liegt Spot auf der Seite, und die
Motoren sind aus: so lässt sich der Akku wechseln. Aufrichten danach mit
`aufrichten.py` (oder dem Knopf „⬆ Aufrichten").

Voraussetzung: Die Motoren müssen VOR dem Start aus sein (am Tablet
ausschalten). Der Roboter lässt spotlab seinen Not-Aus-Endpunkt nicht
eintragen, solange die Motoren laufen (MotorsOnError).

Gemessen am 16.09.2026 (Software 5.1.3): Spot rollt in ~5 s auf die Seite
und schaltet die Motoren SELBST ab, sobald er kippt (Rollwinkel ≈ −113°,
Endlage ≈ −131°). Die Rückmeldung des Kommandos blieb dabei STATUS_UNKNOWN —
deshalb zählt der Körper, nicht die Meldung.
"""

import sys

import spotlab
from spotlab.workshop import lage

seite = next((a for a in sys.argv[1:] if a in lage.SEITEN), "links")

with spotlab.connect(take="--uebernehmen" in sys.argv) as spot:
    print(f"Akku: {spot.battery:.0f} %")
    print("Fertig: " + lage.umlegen(spot, seite))
