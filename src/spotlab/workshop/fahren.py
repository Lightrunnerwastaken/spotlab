"""Fahren: mit W A S D Q E durch den Übungsraum — der Fahrmodus des Raumeditors.

Das Programm läuft wie jedes Schülerprogramm über `spotlab.connect()` und wird
vom Knopf „Fahren" im Raumeditor gestartet. Die Tasten drückt man im
Übungsfenster; es schreibt sie als `fahrt.json` ins Lauf-Verzeichnis
(`record/fahrt.py`), hier wird die Datei mit 20 Hz gelesen und gefahren:

    W / S   vorwärts, rückwärts        A / D   seitwärts links, rechts
    Q / E   links, rechts drehen       Leertaste hält

Ein Befehl, der älter ist als eine halbe Sekunde, heisst Stopp — losgelassene
Taste, eingeschlafene GUI. Die Geschwindigkeitsgrenzen aus `config.toml`
gelten wie überall. „Stopp" im Fenster beendet den Lauf.
"""

import time
from pathlib import Path

from spotlab.record import fahrt
from spotlab.record.run import STOPP_DATEI

SKRIPT = Path(__file__)
TAKT_S = 0.05                     # 20 Hz: schneller als das Fenster schreibt


def fahre(spot, lauf_dir, jetzt=time.time, schlaf=time.sleep, takt_s=TAKT_S, laeuft=None):
    """Die Schleife: `fahrt.json` lesen, fahren oder einmal anhalten, bis `laeuft()` falsch ist.

    Testbar ohne Roboter: `spot` braucht nur `walk` und `stop`, `jetzt` und
    `schlaf` sind die Uhr. Am Ende hält Spot immer.
    """
    lauf_dir = Path(lauf_dir)
    if laeuft is None:
        def laeuft():
            return not (lauf_dir / STOPP_DATEI).exists()

    faehrt = False
    while laeuft():
        vx, vy, wz = fahrt.lies(lauf_dir, jetzt=jetzt)
        if (vx, vy, wz) != fahrt.STILL:
            spot.walk(vx=vx, vy=vy, wz=wz, stop=False)
            faehrt = True
        elif faehrt:
            spot.stop()
            faehrt = False
        schlaf(takt_s)
    spot.stop()


if __name__ == "__main__":
    import spotlab

    with spotlab.connect() as spot:
        spot.power_on()
        spot.stand()
        print("Fahren: W/S vor und zurück · A/D seitwärts · Q/E drehen · Leertaste hält")
        fahre(spot, spot.recorder.dir)
        spot.sit()
