"""Folgen: Spot geht dir hinterher — mit Abstand.

Halte ein AprilTag in der Hand oder häng es dir an den Rucksack, starte dieses
Programm und geh los. Spot dreht sich zu dir und hält ungefähr anderthalb Meter
Abstand. Näher als einen Meter kommt er nie, und rückwärts fährt er nicht —
nach hinten sieht er nichts.

Wer statt des Tags Spots eigenen Personen-Tracker probieren will, tauscht eine
Zeile: `folgen.personen_finder()` statt `folgen.tag_finder()`. Ob dieser Spot
Menschen verfolgt, zeigt erst das Gerät; findet er niemanden, bleibt Spot
stehen. Genau das ist der Sinn der Trennung: der Regler bleibt, der Finder
wechselt.

Spot bewegt sich AUTONOM. Freifläche, Aufsicht, Tablet mit Not-Aus in
Reichweite — vor dem ersten Mal die Abnahmepunkte A1 und A34 lesen.
"""

import spotlab
from spotlab.workshop import folgen

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    print('Folgen: zeig Spot das Tag und geh los. „Stopp" beendet.')
    folgen.folge(spot, folgen.tag_finder(), lauf_dir=spot.recorder.dir)
    spot.sit()
