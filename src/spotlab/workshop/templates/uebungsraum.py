"""Ohne Roboter üben: Spot fährt durch ein gezeichnetes Zimmer.

Starten: über dem Editor „Wo läuft es?" auf „Übungsraum (virtuell)" stellen
und auf ▶ Starten drücken — dann geht das Fenster mit der Draufsicht auf.
Derselbe Knopf steht in der Ansicht „Übungsraum" unten rechts.
Raum und Startposition wählst du in derselben Ansicht; du kannst den Raum aber
auch hier nennen: spotlab.connect(backend="sim", raum="durchgang").

Der Sim fährt nach GEMESSENEN Gangarten. Ein Meter dauert hier so lange wie am
echten Spot — und ein Programm, das hier ankommt, kommt auch dort an.
"""

import spotlab

with spotlab.connect(backend="sim") as spot:
    spot.power_on()
    spot.stand()

    spot.move(forward=1.5)
    spot.move(turn=90)

    for tag in spot.tags():
        print(f"Tag {tag.id}: {tag.distance:.1f} m, {tag.bearing:+.0f} Grad")

    gitter = spot.obstacles()
    print("Einen halben Meter voraus frei:", gitter.is_free(0.5, 0.0))
