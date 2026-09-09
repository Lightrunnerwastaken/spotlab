"""Drei 4-cm-Stufen im Physikmodus. Etwa 7–12 Minuten einplanen."""
import time

from spotlab import connect


def drive_until(spot, target, direction, timeout=360):
    begun = time.monotonic()
    next_message = begun
    while True:
        state = spot.state
        if direction*(state.x-target) >= 0:
            break
        now = time.monotonic()
        if now-begun >= timeout:
            spot.stop()
            raise RuntimeError("Zeitlimit erreicht; Laufbericht pruefen.")
        if now >= next_message:
            print(f"{now-begun:.0f} s: x={state.x:.2f} m, Ziel {target:.2f} m", flush=True)
            next_message = now+5
        spot.walk(vx=direction*.02, stop=False)
        time.sleep(.15)
    spot.stand(timeout=20)


if __name__ == '__main__':
    with connect(backend='physics', raum='physik_treppe_3stufen') as spot:
        state = spot.state
        if abs(state.x) > .1 or abs(state.y) > .1 or abs(state.heading) > 3:
            raise RuntimeError("Vorlage physik_treppe_3stufen und Start (0,0,0) waehlen.")
        spot.power_on()
        spot.stand()
        print("Vorwaerts drei niedrige Stufen hinauf; langsamer Versuch.", flush=True)
        drive_until(spot, 1.75, 1)
        print("Rueckwaerts herunter.", flush=True)
        drive_until(spot, -.03, -1)
        spot.stop()
        spot.stand(timeout=20)
        print("Versuch beendet. Kontakt-Diagnostik steht im Laufbericht.", flush=True)
