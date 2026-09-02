"""Was Spot gerade sieht: Objekte, AprilTags, Hindernisgitter.

Alles in Grad und Metern, damit `spot.move(turn=tag.bearing)` ohne Umrechnung
funktioniert — ein Schueler soll dafuer nicht `math.degrees` kennen muessen.

Die Datenklassen liegen in `backends/base.py` neben Feedback und NavStatus, wo
die backend-unabhaengigen Formen wohnen; hier werden sie re-exportiert, weil
`from spotlab.api.world import Tag` die Schuelertuer ist.
"""

from spotlab.backends.base import (  # noqa: F401  (Re-Export)
    ObstacleGrid,
    Tag,
    WorldObject,
    richtung,
)

__all__ = ["WorldObject", "Tag", "ObstacleGrid", "richtung"]
