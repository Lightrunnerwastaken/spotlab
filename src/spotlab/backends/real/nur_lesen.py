"""Der Platzhalter für Lease und Not-Aus in einer Sitzung, die beides nicht hat.

`RealSpot` fragt an fünf Stellen `self._lease.raise_if_lost()`, bevor etwas an
den Roboter geht, und baut am Ende `self._lease.stop()` und `self._estop.stop()`
ab. Eine Nur-Lesen-Sitzung hat weder das eine noch das andere — und statt an
diesen Stellen überall `if self._lease is None` zu schreiben, steht hier ein
Objekt, das die Frage beantwortet: **nein, und zwar dauerhaft**.

Das ist der Unterschied zwischen „bewegt nichts" und „kann nichts bewegen".
`workshop/sonde.py` ruft ohnehin keine Bewegungsfunktion auf (ein Test hält das
fest), aber wer die Sonde kopiert und `spot.walk()` dazuschreibt, bekommt hier
eine Absage statt eines Lease-Fehlers vom Roboter — oder schlimmer, statt einer
Bewegung neben einem führenden Tablet.

`level()` gibt `None`: der Not-Aus des Roboters existiert weiter (das Tablet hält
ihn), diese Sitzung KENNT ihn nur nicht. `SafetyStatus` unterscheidet damit
sauber zwischen „frei" und „nicht gefragt" — dieselbe Regel wie überall:
fehlende Messwerte sind None, nie ein erfundener Wert.
"""

from spotlab.errors import ReadOnlySession

MELDUNG = (
    "Diese Sitzung liest nur (nur_lesen=True) und hält kein Lease — sie kann den "
    "Spot nicht bewegen. Starte das Programm ohne nur_lesen, wenn der Roboter "
    "fahren soll; dann darf aber niemand sonst die Kontrolle halten."
)


class NurLesen:
    """Steht für BEIDES: das fehlende Lease und den fehlenden Not-Aus-Endpunkt.

    Eine Klasse statt zwei, weil es hier nur eine Aussage gibt — diese Sitzung
    hat nichts genommen, also gibt sie am Ende auch nichts zurück.
    """

    # Wie beim echten `LeaseGuard`: `RealSpot` und die Aufzeichnung lesen beides.
    lost = False
    previous_holder = None

    def raise_if_lost(self):
        raise ReadOnlySession(MELDUNG)

    def level(self):
        return None

    def stop(self):
        """Nichts abzubauen. Kein Fehler, sondern der ganze Sinn der Sitzung."""
