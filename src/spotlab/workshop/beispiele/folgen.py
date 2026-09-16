"""Folgen: Spot geht dir hinterher — mit Abstand.

Halte ein AprilTag in der Hand oder häng es dir an den Rucksack, starte dieses
Programm und geh los. Spot dreht sich zu dir und hält ungefähr anderthalb Meter
Abstand. Näher als einen Meter kommt er nie, und rückwärts fährt er nicht —
nach hinten sieht er nichts.

Gesucht wird in einer STAFFEL: zuerst der Körper, dann ein Gesicht, dann das Tag.
Das hat einen gemessenen Grund. Spots Frontkameras schauen rund 20 Grad nach
unten; nah und genau voraus ist ein Gesicht über dem Bild oder in der Naht der
beiden Kameras — die Hüfte nicht. Weit weg ist der Körper für den Erkenner zu
klein, das Gesicht nicht. Das Tag geht immer. Fehlt ein Modell oder OpenCV,
fällt der betroffene Finder aus und die nächste Stufe trägt; warum, steht im
Protokoll und in der Zeile „Noch kein Ziel".

Mit `blick_grad` hebt Spot beim Gehen die Nase, damit die Kameras höher
schauen — fünfzehn Grad holen das Gesicht von zweieinhalb Metern auf gut einen
Meter herunter. Das ist seit dem 16.09.2026 die Vorgabe: mit flacher Nase sah
Spot einen aufrecht stehenden Menschen auf Folgeabstand nie, nur Beine. Der
Preis: er sieht den Boden dicht vor den Füssen nicht mehr, und genau dort prüft
die Hindernisschranke. Wer das braucht, fährt flach:

    folgen.folge(spot, finder, lauf_dir=…, blick_grad=0)

Nur ein Weg, wenn du vergleichen willst:

    folgen.folge(spot, folgen.tag_finder(), lauf_dir=…)        # nur das Tag
    folgen.folge(spot, folgen.personen_finder(), lauf_dir=…)   # Spots Tracker
    folgen.folge(spot, folgen.gesicht_finder(), lauf_dir=…)    # nur Gesichter

Spot bewegt sich AUTONOM. Freifläche, Aufsicht, Tablet mit Not-Aus in
Reichweite — vor dem ersten Mal die Abnahmepunkte A1 und A34 lesen.
"""

import spotlab
from spotlab.workshop import folgen

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    print('Folgen: zeig Spot das Tag und geh los. Stopp beendet.')
    folgen.folge(
        spot,
        folgen.zuerst(folgen.koerper_finder(), folgen.gesicht_finder(), folgen.tag_finder()),
        lauf_dir=spot.recorder.dir,
    )
    spot.sit()
