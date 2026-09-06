"""Durch die Tür: Spot sucht den Durchgang, geht in den nächsten Raum und setzt sich.

Vorher in der Ansicht „Übungsraum" den Raum „durchgang" wählen (Start links,
der Tag hängt drüben). Spot kennt den Plan des Zimmers NICHT. Er hat zwei Sinne:

    spot.obstacles()   das Hindernisgitter — wie weit ist es in jede Richtung frei?
    spot.tags()        AprilTags. Der Tag hängt im Nachbarraum: sieht Spot ihn,
                       ist er drüben.

Jede Runde schaut Spot sich um, dreht sich in die offenste Richtung und geht
ein Stück. Das ist kein Plan, das ist ein Reflex — und er reicht für eine Tür.
Am echten Spot läuft dasselbe Programm: Tag 3 im Nachbarraum aufhängen.
"""

import math

import spotlab

SCHRITT_M = 0.8                       # so weit geht Spot je Runde
ABSTAND_M = 0.5                       # so viel Platz lässt er vor Hindernissen
RICHTUNGEN = range(-150, 181, 30)     # Grad, links positiv — wie spot.move(turn=…)
RUNDEN = 12                           # danach gibt er auf


def umsehen(spot):
    """{Drehung in Grad: freie Meter in dieser Richtung}"""
    gitter = spot.obstacles()
    x, y, yaw = spot.state.pose
    blick = math.degrees(yaw)
    return {d: gitter.free_distance(x, y, blick + d) for d in RICHTUNGEN}


with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()

    for runde in range(1, RUNDEN + 1):
        if spot.tags():
            print("Tag gesehen — ich bin im nächsten Raum.")
            break

        frei = umsehen(spot)
        # Die offenste Richtung; bei Gleichstand die kleinste Drehung.
        drehung = min(frei, key=lambda d: (-frei[d], abs(d)))
        print(f"Runde {runde}: am weitesten frei bei {drehung:+d}° ({frei[drehung]:.1f} m)")
        if frei[drehung] < ABSTAND_M:
            print("Überall zu eng — ich bleibe stehen.")
            break

        spot.move(turn=drehung)
        spot.move(forward=min(SCHRITT_M, frei[drehung] - ABSTAND_M))
    else:
        print("Keinen Tag gefunden — ich setze mich trotzdem.")

    spot.sit()
