"""Haltung messen -- Abnahme A41, gedacht für den ECHTEN Spot.

Spot steht auf, hält acht Körperhaltungen je 3 s, setzt sich und schreibt danach noch 5 s
mit. Aus der Aufzeichnung werden zwei Annahmen des Physikmodus ersetzt: wie er sich
hinsetzt (bisher: das Aufstehen rückwärts) und wie schnell eine Haltung erreicht ist
(bisher: 1 s). Ausgewertet wird `zustand.jsonl` des Laufs (Höhe, Roll, Nick, Gelenke).

Vorher: Freifläche mit 1 m Platz um Spot, Aufsicht, Tablet mit Not-Aus in Reichweite,
Abnahmepunkt A1 erledigt. Im Übungsraum geht es nur im Physikmodus.
"""

import time

import spotlab

HALTEN_S = 3.0          # so lange je Haltung
NEUTRAL_S = 2.0         # dazwischen zurück in die neutrale Haltung
NACHLAUF_S = 5.0        # nach sit() weiter aufzeichnen -- bisher endete jeder Lauf zu früh
POSEN = (("roll", 15), ("roll", -15), ("pitch", 15), ("pitch", -15),
         ("yaw", 20), ("yaw", -20), ("height", 0.1), ("height", -0.1))


def messe(spot, schlaf=time.sleep):
    spot.power_on()
    spot.stand()
    schlaf(HALTEN_S)
    for achse, wert in POSEN:
        print(f"Haltung {achse} = {wert}")
        spot.pose(**{achse: wert})
        schlaf(HALTEN_S)
        spot.pose()
        schlaf(NEUTRAL_S)
    spot.sit()
    schlaf(NACHLAUF_S)


if __name__ == "__main__":
    with spotlab.connect() as spot:
        messe(spot)
