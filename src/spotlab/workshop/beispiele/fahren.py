"""Fahren: selbst mit der Tastatur durch den Übungsraum — der Knopf „🎮 Fahren".

Der Raumeditor startet diese Datei; du kannst sie auch selbst starten wie jedes
Beispiel. Die Tasten drückst du im Übungsfenster:

    W / S   vorwärts, rückwärts        A / D   seitwärts links, rechts
    Q / E   links, rechts drehen       Leertaste hält, „Stopp" beendet

Das Fenster schreibt die Tasten in eine kleine Datei im Lauf-Verzeichnis
(`fahrt.json`), dieses Programm liest sie zwanzigmal je Sekunde und ruft
`spot.walk(vx, vy, wz, stop=False)`. Ein Befehl, der älter ist als eine halbe
Sekunde, heisst Stopp — losgelassene Taste, eingeschlafenes Fenster. Die
Schleife selbst steht in `spotlab.workshop.fahren.fahre`; lies sie, wenn du
wissen willst, wie ein Programm laufend neu lenkt.
"""

import spotlab
from spotlab.workshop.fahren import fahre

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    print("Fahren: W/S vor und zurück · A/D seitwärts · Q/E drehen · Leertaste hält")
    fahre(spot, spot.recorder.dir)
    spot.sit()
