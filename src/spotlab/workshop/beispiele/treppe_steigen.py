"""Treppe steigen: Spot findet die Treppe, geht vorwärts hinauf, sieht oben den
Tag — und kommt rückwärts wieder herunter.

Vorher im Raumeditor den Raum „treppe" wählen. Spot hat einen neuen Sinn:

    spot.stairs()      die Treppen in Sicht — wie weit, in welche Richtung, wie
                       viele Stufen, und wo bergauf ist (axis_bearing)

Die Regel ist die von Boston Dynamics: auf einer Treppe zeigt die Nase IMMER
bergauf. Hinauf geht es also vorwärts — und hinunter RÜCKWÄRTS, ohne sich
umzudrehen. Nimmt ein Programm die Treppe falsch herum, bleibt Spot im
Übungsraum an der Kante stehen, und der Lauf sagt es (`treppe_verweigert`).
Am echten Spot läuft dasselbe Programm; dort erkennt die Firmware die Treppe
selbst (config.toml: `treppen = "auto"`).
"""

import time

import spotlab

TEMPO_M_S = 0.25                      # gemächlich, wie am echten Gerät auf Stufen
HOECHSTENS_S = 60.0                   # je Richtung; danach gibt er auf


def hoehe(spot):
    """Die Körperhöhe — steigt sie, ist Spot oben."""
    return spot.state.z


with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    unten = hoehe(spot)

    treppen = spot.stairs()
    if not treppen:
        print("Keine Treppe in Sicht — ich setze mich.")
        spot.sit()
        raise SystemExit

    treppe = treppen[0]
    print(f"Treppe: {treppe.steps} Stufen, {treppe.rise_m:.2f} m hoch, "
          f"{treppe.distance:.1f} m entfernt, ich stehe {treppe.direction}wärts.")

    # Nase bergauf: die Achse der Treppe ist die Richtung, in der es hinaufgeht.
    spot.move(turn=treppe.axis_bearing)

    # Vorwärts hinauf, bis der Körper um den Anstieg gestiegen ist.
    start = time.monotonic()
    while hoehe(spot) - unten < treppe.rise_m - 0.05 and time.monotonic() - start < HOECHSTENS_S:
        spot.walk(vx=TEMPO_M_S, stop=False)
    spot.walk(vx=TEMPO_M_S, duration=1.5)          # noch ein Stück auf das Podest
    spot.stop()
    print("Oben")
    for tag in spot.tags():
        print(f"Tag {tag.id}: {tag.distance:.1f} m")

    # NICHT umdrehen: die Nase bleibt bergauf, die Treppe liegt hinter Spot,
    # und rückwärts geht es hinunter.
    start = time.monotonic()
    while hoehe(spot) - unten > 0.05 and time.monotonic() - start < HOECHSTENS_S:
        spot.walk(vx=-TEMPO_M_S, stop=False)
    spot.walk(vx=-TEMPO_M_S, duration=1.0)         # weg von der Fusskante
    spot.stop()
    print("Unten")
    spot.sit()
