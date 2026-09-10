"""Folgen: Spot geht dir hinterher — mit Abstand.

Halte ein AprilTag in der Hand oder häng es dir an den Rucksack, starte dieses
Programm und geh los. Spot dreht sich zu dir und hält ungefähr anderthalb Meter
Abstand. Näher als einen Meter kommt er nie, und rückwärts fährt er nicht —
nach hinten sieht er nichts.

Gesucht wird in einer STAFFEL: zuerst ein Gesicht, dann das Tag. Das hat einen
gemessenen Grund. Spots Frontkameras schauen rund 20 Grad nach unten, und ein
stehender Mensch hat erst ab gut zweieinhalb Metern ein Gesicht im Bild —
näher sieht Spot Beine. Das Tag übernimmt genau dort. Fehlt OpenCV oder das
Gesichtsmodell, fällt der erste Finder aus und das Tag trägt allein; warum,
steht im Protokoll.

Mit `blick_grad` hebt Spot beim Gehen die Nase, damit die Kameras höher
schauen — zwölf Grad holen das Gesicht von zweieinhalb Metern auf gut einen
Meter herunter. Dafür sieht er den Boden dicht vor den Füssen nicht mehr, und
genau dort prüft die Hindernisschranke. Deshalb ist die Vorgabe null:

    folgen.folge(spot, finder, lauf_dir=…, blick_grad=12)

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
        folgen.zuerst(folgen.gesicht_finder(), folgen.tag_finder()),
        lauf_dir=spot.recorder.dir,
    )
    spot.sit()
