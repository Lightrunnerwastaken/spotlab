"""Karte verbessern: Schleifen schliessen und Anker optimieren — der Knopf „✨ Karte verbessern".

Eine Karte, die aufgezeichnet wurde, ohne dass Schleifen geschlossen wurden, ist
eine KETTE: der Aufzeichnungsdienst weiss nicht, dass der Gang, durch den Spot
zum zweiten Mal fährt, derselbe ist, und legt einen zweiten Strang daneben.
Zwischen zwei Punkten gibt es dann nur den einen aufgezeichneten Weg — Spot
fährt wie auf Schienen.

Dieses Programm holt das nach: Karte auf den Spot laden, dort Schleifen suchen
und die Anker optimieren, dann die verbesserte Karte zurückschreiben. Es dauert
Sekunden bis Minuten, je nach Grösse der Karte.

**Spot bewegt sich dabei nicht.** Er braucht trotzdem das Lease, denn das
Hochladen einer Karte gehört ihm; halte das Tablet bereit.
"""

import spotlab
from spotlab.workshop.karte import karte_aus_umgebung, verbessere

with spotlab.connect() as spot:
    bericht = verbessere(spot, karte_aus_umgebung())
    print("Fertig." if bericht.gelaufen else "Fertig, ohne Änderung.")
