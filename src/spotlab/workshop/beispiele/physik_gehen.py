"""Physikversuch auf ebenem Boden: Stand, Trab, Stopp. Kein Sitzbefehl."""
from spotlab import connect

if __name__ == '__main__':
    with connect(backend='physics') as spot:
        spot.power_on()
        spot.stand()
        with spot.messfenster('physik_geradeaus', hz=50):
            spot.walk(vx=0.15, duration=8)
        spot.stop()
        state = spot.state
        print(f'Position: {state.x:.3f}, {state.y:.3f} m; Tempo: {state.speed:.3f} m/s')
