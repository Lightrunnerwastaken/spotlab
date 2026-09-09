"""6-cm-Podest im Physikmodus. Langsamer Versuch: mehrere Minuten einplanen."""
import time

from spotlab import connect


def drive_until(spot, target, direction, timeout=180):
    deadline = time.monotonic()+timeout
    while direction*(spot.state.x-target) < 0:
        if time.monotonic() >= deadline:
            spot.stop()
            raise RuntimeError("Ziel nicht rechtzeitig erreicht; Lauf auswerten.")
        spot.walk(vx=direction*.02, duration=.8, stop=False)
        time.sleep(.15)
    spot.stand(timeout=20)  # laufenden Einzelfussschritt beenden und ruhig halten


if __name__ == '__main__':
    with connect(backend='physics', raum='physik_einzelstufe') as spot:
        state = spot.state
        if abs(state.x) > .15 or abs(state.y) > .1 or abs(state.heading) > 3:
            raise RuntimeError("Im Raumeditor Physik-Einzelstufe und Start (0, 0, 0) waehlen.")
        spot.power_on()
        spot.stand()
        print("Vorwaerts auf das Podest; der Kriechgang ist bewusst langsam.")
        drive_until(spot, .90, 1)
        print("Rueckwaerts herunter.")
        drive_until(spot, -.03, -1)
        spot.stop()
        spot.stand(timeout=20)
        print("Versuch beendet; Messdaten im Laufordner.")
