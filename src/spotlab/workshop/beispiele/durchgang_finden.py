"""Durch die Tür: Spot fährt laufend, sieht sich dabei um, findet den Durchgang,
geht in den nächsten Raum und setzt sich.

Vorher in der Ansicht „Übungsraum" den Raum „durchgang" wählen (Start links,
der Tag hängt drüben). Spot kennt den Plan des Zimmers NICHT. Er hat zwei Sinne:

    spot.obstacles()   das Hindernisgitter — wie weit ist es in jede Richtung frei?
    spot.tags()        AprilTags. Der Tag hängt im Nachbarraum: sieht Spot ihn,
                       ist er drüben.

Immer wieder liest Spot das Gitter neu und hält auf die Richtung zu, in der es
am weitesten frei ist — ohne anzuhalten: `spot.walk(…, stop=False)` setzt nur
das Tempo und kehrt sofort zurück. Den Kurs wechselt er erst, wenn eine andere
Richtung DEUTLICH freier ist; sonst flatterte er bei jedem Messrauschen. Und
durch eine Lücke geht er in der Mitte, nicht an der Kante.
Kein Plan, ein Reflex: für eine Tür reicht das.
Am echten Spot läuft dasselbe Programm (Tag 3 im Nachbarraum aufhängen).
"""

import math
import time

import spotlab

TEMPO_M_S = 0.4                       # Reisetempo
ABSTAND_M = 0.5                       # so viel Platz lässt er vor Hindernissen
SCHRITT_GRAD = 5                      # so fein tastet er die Richtungen ab
RICHTUNGEN = range(-180, 180, SCHRITT_GRAD)   # Grad rundum, links positiv — wie spot.move(turn=…)
DEUTLICH_M = 0.3                      # so viel freier muss eine neue Richtung sein
LUECKE_GRAD = 20                      # so weit sucht er um den besten Strahl die Mitte der Lücke
LENKUNG = 1.5                         # Grad/s Drehrate je Grad Kursabweichung
MAX_DREHRATE = 40.0                   # Grad/s
HOECHSTENS_S = 60.0                   # danach gibt er auf


def umsehen(spot):
    """(Blickrichtung in Grad, {Richtung relativ dazu: freie Meter dorthin})"""
    gitter = spot.obstacles()
    x, y, yaw = spot.state.pose
    blick = math.degrees(yaw)
    return blick, {d: gitter.free_distance(x, y, blick + d) for d in RICHTUNGEN}


def relativ(kurs_welt, blick):
    """Ein Kurs im Weltframe als Richtung relativ zum Blick, auf das Raster gerundet."""
    grad = (kurs_welt - blick + 180) % 360 - 180
    return min(RICHTUNGEN, key=lambda d: abs(d - grad))


def kurs(frei, bisher):
    """Die Richtung, in der es am weitesten frei ist — mit Beharrlichkeit.

    Bei Gleichstand die kleinste Drehung. Nach hinten schaut Spot erst, wenn
    es dort DEUTLICH weiter geht als vorne. Der bisherige Kurs bleibt, solange
    keine andere Richtung um DEUTLICH_M freier ist: ein einzelner verrauschter
    Strahl darf Spot nicht umdrehen lassen.
    """
    vorne = {d: m for d, m in frei.items() if abs(d) <= 90}
    zur_wahl = vorne if max(vorne.values()) >= max(frei.values()) - DEUTLICH_M else frei
    beste = min(zur_wahl, key=lambda d: (-zur_wahl[d], abs(d)))
    if bisher is not None and frei[beste] - frei[bisher] < DEUTLICH_M:
        return bisher
    return beste


def mitte(frei, richtung):
    """Die Mitte der Lücke, in der `richtung` liegt.

    Nachbarstrahlen, die (fast) genauso weit reichen, gehören zur selben Lücke
    — höchstens LUECKE_GRAD nach jeder Seite. Durch eine Tür geht Spot so in
    der Mitte statt an der Kante; im offenen Raum ist die Mitte der Strahl selbst.
    """
    weit = frei[richtung] - 0.05
    links = rechts = richtung
    while links - richtung < LUECKE_GRAD and frei.get(links + SCHRITT_GRAD, 0.0) >= weit:
        links += SCHRITT_GRAD
    while richtung - rechts < LUECKE_GRAD and frei.get(rechts - SCHRITT_GRAD, 0.0) >= weit:
        rechts -= SCHRITT_GRAD
    return (links + rechts) / 2


with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()

    start = time.monotonic()
    gefunden = False
    kurs_welt = None                  # der Kurs bleibt im Weltframe, Spot dreht sich ja
    while time.monotonic() - start < HOECHSTENS_S:
        if spot.tags():
            gefunden = True
            break

        blick, frei = umsehen(spot)
        bisher = None if kurs_welt is None else relativ(kurs_welt, blick)
        richtung = kurs(frei, bisher)
        if richtung != bisher:
            print(f"{time.monotonic() - start:4.1f} s: Kurs {richtung:+d}° ({frei[richtung]:.1f} m frei)")
        kurs_welt = blick + richtung
        if frei[richtung] < ABSTAND_M:
            print("Überall zu eng — ich bleibe stehen.")
            break

        # Lenken statt anhalten: Drehrate proportional zur Abweichung von der
        # Lückenmitte, Tempo nach vorn nur, soweit die vor Spot liegt — und nie
        # schneller, als der Platz erlaubt. stop=False: nur das Tempo setzen,
        # sofort weiter umsehen; Spot fährt derweil.
        ziel = mitte(frei, richtung)
        drehrate = max(-MAX_DREHRATE, min(MAX_DREHRATE, LENKUNG * ziel))
        tempo = TEMPO_M_S * max(0.0, math.cos(math.radians(ziel)))
        tempo = min(tempo, frei[richtung] - ABSTAND_M)
        spot.walk(vx=tempo, wz=math.radians(drehrate), stop=False)       # wz in rad/s

    spot.stop()
    if gefunden:
        print("Tag gesehen — ich bin im nächsten Raum.")
    else:
        print("Keinen Tag gefunden — ich setze mich trotzdem.")
    spot.sit()
