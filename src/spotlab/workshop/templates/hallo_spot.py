"""Erstes Spot-Programm.

Starten:  spotlab run hallo_spot.py
Oder in VS Code einfach F5 drücken — aufgezeichnet wird beides.
"""

import spotlab

# connect() meldet sich an, synchronisiert die Uhr, registriert den Not-Aus und
# holt das Lease. Am Ende des with-Blocks setzt sich der Spot hin und schaltet
# die Motoren ab — auch wenn dein Programm mit einem Fehler abbricht.
with spotlab.connect() as spot:

    # Motoren einschalten ist bewusst eine eigene Zeile: ein 30-kg-Roboter steht
    # nicht auf, nur weil jemand ein Programm gestartet hat.
    spot.power_on()
    spot.stand()

    print("Akku:", spot.battery, "%")

    # Einen Meter vorwärts. move() wartet, bis der Spot wirklich angekommen ist.
    spot.move(forward=1.0)

    # Ein Bild der vorderen linken Kamera aufnehmen und speichern.
    # spot.cameras() sagt ehrlich, was DIESES Backend wirklich hat — im
    # Trockenlauf (--dryrun) gibt es keine Kameras, am echten Spot fünf.
    if "frontleft" in spot.cameras():
        bild = spot.camera("frontleft")
        bild.save("vorne.png")
        print("Bild gespeichert:", bild)
    else:
        print("Keine Kamera vorhanden — das ist im Trockenlauf normal.")

    # 90 Grad nach links drehen.
    spot.move(turn=90)

print("Fertig. Der Lauf liegt im Ordner runs/.")
