"""Fahren: mit W A S D Q E durch den Übungsraum — der Kern des Fahrmodus.

Das Programm dazu ist `Beispiele/fahren.py` im Arbeitsordner (Vorlage in
`workshop/beispiele/`), gestartet vom Knopf „Fahren" im Raumeditor. Es muss dort
liegen und NICHT hier im Paket: Läufe landen neben dem Skript, und der Watcher
der GUI sucht nur unter `<Arbeitsordner>/<Projekt>/runs/` — ein Skript im Paket
legte seine Läufe unter `src/spotlab/workshop/runs/` an, wo sie niemand fand,
und das Übungsfenster erfuhr das Lauf-Verzeichnis nie (07.09.2026).
Die Tasten drückt man im Übungsfenster; es schreibt sie als `fahrt.json` ins
Lauf-Verzeichnis (`record/fahrt.py`), hier wird die Datei mit 20 Hz gelesen:

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
from spotlab.workshop import blick
from spotlab.workshop.beispiele import ORDNER

DATEINAME = "fahren.py"
TAKT_S = 0.05                     # 20 Hz: schneller als das Fenster schreibt


def skript_in(arbeitsordner):
    """Das Fahrprogramm im Projekt Beispiele des Arbeitsordners (`bereitstellen` legt es an)."""
    return Path(arbeitsordner) / ORDNER / DATEINAME


def fahre(spot, lauf_dir, jetzt=time.time, schlaf=time.sleep, takt_s=TAKT_S, laeuft=None,
          mit_blick=True):
    """Die Schleife: `fahrt.json` lesen, fahren oder einmal anhalten, bis `laeuft()` falsch ist.

    Testbar ohne Roboter: `spot` braucht nur `walk` und `stop`, `jetzt` und
    `schlaf` sind die Uhr. Am Ende hält Spot immer.

    `mit_blick`: nebenher schreibt ein eigener Thread `ansicht.jpg` aus den
    Frontkameras, damit man beim Fahren SIEHT, wohin (`workshop/blick.py`).
    Im Übungsraum rendert MuJoCo die Ansicht selbst; dann hält der Blick sich
    heraus. Ein Bildabruf dauert länger als ein Fahrtakt -- deshalb ein Thread
    und nicht diese Schleife.
    """
    lauf_dir = Path(lauf_dir)
    if laeuft is None:
        def laeuft():
            return not (lauf_dir / STOPP_DATEI).exists()

    seher = blick.starte(spot, lauf_dir) if mit_blick else None
    faehrt = False
    try:
        while laeuft():
            vx, vy, wz = fahrt.lies(lauf_dir, jetzt=jetzt)
            if (vx, vy, wz) != fahrt.STILL:
                spot.walk(vx=vx, vy=vy, wz=wz, stop=False)
                faehrt = True
            elif faehrt:
                spot.stop()
                faehrt = False
            schlaf(takt_s)
    finally:
        # Erst anhalten, dann den Blick abbauen: ein haengender Bildabruf darf
        # den Stopp nicht verzoegern.
        spot.stop()
        if seher is not None:
            seher.beenden()

