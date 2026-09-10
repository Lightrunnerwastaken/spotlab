"""Gehzeit: Spot steht im Gang und nimmt für jeden die Zeit.

Für den Versuch aus der Verhaltensbiologie — wie schnell gehen Leute, und hängt
das von der Gruppengrösse ab? Bisher steht ein Mensch mit der Stoppuhr da und
kann immer nur EINE Gruppe messen. Spot stoppt für jeden gleichzeitig.

AUFBAU

1. Zwei AprilTags an die Enden der Strecke hängen, auf Kniehöhe, flach an die
   Wand. Spot misst die Länge dazwischen selbst — nichts eintippen.
2. Spot seitlich hinstellen, so dass er BEIDE Tags gleichzeitig sieht und der
   Gang vor ihm liegt. Er bewegt sich nicht; das Tablet darf jemand in der Hand
   behalten.
3. Jede Person, deren Zeit zählen soll, trägt ein AprilTag sichtbar am Rucksack
   oder in der Hand (`gehzeit.tag_quelle`). Wenn dieser Spot Menschen von selbst
   verfolgt, geht es auch ohne — dann `gehzeit.personen_quelle()` als `quelle`
   übergeben. Was dieser Roboter kann, klärt Abnahmepunkt A34 Teil 1.

Der Lauf endet mit dem Stopp-Knopf oder nach der eingestellten Dauer:

    python gehzeit.py           # zehn Minuten
    python gehzeit.py 300       # fünf Minuten

DANACH, und das ist der Teil für einen Menschen: der Reiter **Gehzeit** im
spotlab-Fenster. Dort steht auch der Knopf, mit dem sich der Versuch starten
lässt, ohne dieses Programm zu öffnen. Wer lieber tippt:

    python -m spotlab.experiment.nachtrag <Lauf-Verzeichnis>

Dort stehen die Durchgänge mit Uhrzeit, Zeit und Tempo, dazu die Bilder des
Abschnitts. Spot schlägt vor, wie viele Leute gleichzeitig unterwegs waren —
ob das eine Gruppe war, entscheidest du. Klasse und Gruppengrösse kommen in
dieselbe Tabelle (`gehzeit/gehzeit.csv`, öffnet sich mit einem Doppelklick).
Am Ende fragt das Programm, ob die Bilder gelöscht werden sollen: es sind
Aufnahmen von Mitschülern, gemacht für genau diese eine Frage.

Wer stehen bleibt, umkehrt oder aus dem Bild verschwindet, wird VERWORFEN —
mit Grund in der Tabelle, nicht stillschweigend.

Spot bewegt sich in diesem Programm nicht. Es verbindet ohne Lease
(`nur_lesen=True`), nimmt dem Tablet also nichts weg und kann den Roboter nicht
fahren lassen.
"""

import sys

import spotlab
from spotlab.workshop import gehzeit

dauer_s = float(sys.argv[1]) if len(sys.argv) > 1 else gehzeit.DAUER_S

with spotlab.connect(nur_lesen=True) as spot:
    print('Gehzeit: Spot misst die Strecke und schaut dann zu. Stopp beendet.')
    mitschnitt = gehzeit.bildmitschnitt(spot)
    if mitschnitt is not None:
        mitschnitt.start()
    try:
        gehzeit.gehzeit(spot, dauer_s=dauer_s, lauf_dir=spot.recorder.dir,
                        mitschnitt=mitschnitt)
    finally:
        if mitschnitt is not None:
            mitschnitt.stop()
