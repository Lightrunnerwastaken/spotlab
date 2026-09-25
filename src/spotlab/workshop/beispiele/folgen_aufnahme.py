"""Folgen MIT Aufnahme: dasselbe wie `folgen.py` — und hinterher siehst du, was Spot sah.

Spot folgt dir genau wie in `folgen.py` (Körper vor Gesicht, Handzeichen, LEDs,
alle Schranken). Zusätzlich schreibt er je Takt mit, was er gesehen und daraus
gemacht hat — das Panorama der Frontkameras, jeden erkannten Körper und jedes
Gesicht mit Urteil (genommen oder warum verworfen), das Ziel, den Fahrbefehl,
welche Schranke gebremst hat, und wie lange jeder Schritt dauerte. Das liegt im
Lauf unter `folgen/`, rund eine halbe Megabyte je Takt.

Danach das Video mit allen Markierungen, in Echtzeit:

    python -m spotlab.workshop.folgenfilm runs/<lauf>

Es landet als `folgen.mp4` im Lauf, daneben `folgen_bericht.txt` mit den Zahlen:
wohin die Zeit eines Takts geht, wie oft er folgte, suchte oder aus dem Nachlauf
fuhr, was die Gegenprobe verwarf und wo die Lücken waren. Die letzte Zeile des
Laufs nennt den Befehl mit dem richtigen Pfad.

EIN GUTER ABLAUF für eine Aufnahme, die etwas zeigt (3–5 Minuten):
  1. 1.6 m vor Spot stehen, bis die LEDs blau sind
  2. langsam geradeaus weggehen, dann stehen bleiben
  3. einen Bogen nach links, einen nach rechts
  4. nah herankommen (1 m), dann weit weg (3–4 m)
  5. seitlich aus dem Bild gehen und wieder hinein
  6. kurz in die Hocke gehen
Ein Handyvideo von hinten dazu hilft beim Vergleich.

Die Aufnahme bremst keinen Takt: Bilder schreibt ein eigener Faden, und kommt der
nicht nach, fällt ein Bild weg — nie ein Fahrbefehl.

Spot bewegt sich AUTONOM. Freifläche, Aufsicht, Tablet mit Not-Aus in
Reichweite — vor dem ersten Mal die Abnahmepunkte A1 und A34 lesen.
"""

import spotlab
from spotlab.workshop import folgen

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    print('Folgen mit Aufnahme: stell dich vor Spot und geh los. Offene Hand = Halt, Daumen hoch = Weiter. Stopp beendet.')
    staffel = folgen.zuerst(folgen.koerper_finder(), folgen.gesicht_finder())
    folgen.folge(
        spot,
        staffel,
        gesten=folgen.gesten_leser(staffel),
        lauf_dir=spot.recorder.dir,
        aufnahme=True,
    )
    spot.sit()
