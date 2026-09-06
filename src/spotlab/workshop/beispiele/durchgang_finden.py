"""Durch die Tür: Spot fährt laufend, sieht sich dabei um, findet den Durchgang,
geht in den nächsten Raum und setzt sich.

Vorher in der Ansicht „Übungsraum" den Raum „durchgang" wählen (Start links,
der Tag hängt drüben). Spot kennt den Plan des Zimmers NICHT. Er hat zwei Sinne:

    spot.obstacles()   das Hindernisgitter — wie weit ist es in jede Richtung frei?
    spot.tags()        AprilTags. Der Tag hängt im Nachbarraum: sieht Spot ihn,
                       ist er drüben.

Fünfmal je Sekunde liest Spot das Gitter neu und lenkt in die offenste
Richtung — ohne anzuhalten. Je weiter seitlich sie liegt, desto stärker dreht
er und desto langsamer geht er vorwärts. Kein Plan, ein Reflex: für eine Tür
reicht das. Am echten Spot läuft dasselbe Programm (Tag 3 im Nachbarraum).
"""

import math
import time

import spotlab

TEMPO_M_S = 0.4                       # Reisetempo
TAKT_S = 0.2                          # so oft schaut Spot neu
ABSTAND_M = 0.5                       # so viel Platz lässt er vor Hindernissen
RICHTUNGEN = range(-165, 181, 15)     # Grad, links positiv — wie spot.move(turn=…)
LENKUNG = 2.0                         # Grad/s Drehrate je Grad Abweichung
MAX_DREHRATE = 60.0                   # Grad/s
HOECHSTENS_S = 60.0                   # danach gibt er auf


def umsehen(spot):
    """{Richtung in Grad: freie Meter dorthin}"""
    gitter = spot.obstacles()
    x, y, yaw = spot.state.pose
    blick = math.degrees(yaw)
    return {d: gitter.free_distance(x, y, blick + d) for d in RICHTUNGEN}


with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()

    start = time.monotonic()
    gefunden = False
    letzte_richtung = None
    while time.monotonic() - start < HOECHSTENS_S:
        if spot.tags():
            gefunden = True
            break

        frei = umsehen(spot)
        # Die offenste Richtung; bei Gleichstand die kleinste Drehung.
        richtung = min(frei, key=lambda d: (-frei[d], abs(d)))
        if frei[richtung] < ABSTAND_M:
            print("Überall zu eng — ich bleibe stehen.")
            break
        if richtung != letzte_richtung:
            print(f"{time.monotonic() - start:4.1f} s: offenste Richtung {richtung:+d}° "
                  f"({frei[richtung]:.1f} m frei)")
            letzte_richtung = richtung

        # Lenken statt anhalten: Drehrate proportional zur Abweichung, Tempo
        # nach vorn nur, soweit die Richtung vor Spot liegt — und nie schneller,
        # als die freie Strecke erlaubt.
        drehrate = max(-MAX_DREHRATE, min(MAX_DREHRATE, LENKUNG * richtung))
        tempo = TEMPO_M_S * max(0.0, math.cos(math.radians(richtung)))
        tempo = min(tempo, frei[richtung] - ABSTAND_M)
        spot.walk(vx=tempo, wz=math.radians(drehrate), duration=TAKT_S)   # wz in rad/s

    spot.stop()
    if gefunden:
        print("Tag gesehen — ich bin im nächsten Raum.")
    else:
        print("Keinen Tag gefunden — ich setze mich trotzdem.")
    spot.sit()
