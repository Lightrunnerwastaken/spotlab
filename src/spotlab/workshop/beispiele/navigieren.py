"""Navigieren: Wegpunkte auf der Karte anklicken, Spot fährt hin — der Knopf „🧭 Zu Wegpunkten fahren".

Der Tab „Karten" startet diese Datei; du kannst sie auch selbst starten wie
jedes Beispiel. Sie lädt die Karte, die im Tab gewählt ist (oder die aktive
Karte), verortet den Spot über ein AprilTag und wartet dann auf Klicks: der Tab
schreibt den angeklickten Wegpunkt als `ziel.json` ins Lauf-Verzeichnis, dieses
Programm fährt hin (`spot.navigate_to`) und meldet in `navigation.json`, wo Spot
steht. „Stopp" im Tab beendet den Lauf. Die Schleife selbst steht in
`spotlab.workshop.navigieren.navigiere`; lies sie, wenn du wissen willst, wie
ein Programm auf Ziele von aussen wartet.

Spot fährt dabei AUTONOM. Freifläche, Aufsicht, Tablet mit Not-Aus in Reichweite.
"""

import spotlab
from spotlab.workshop.navigieren import karte_aus_umgebung, navigiere

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    print('Navigation: im Tab „Karten" einen Wegpunkt anklicken · „Stopp" beendet')
    navigiere(spot, spot.recorder.dir, karte=karte_aus_umgebung())
    spot.sit()
