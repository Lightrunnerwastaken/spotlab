"""Was Spot gerade sieht: Objekte, AprilTags, Hindernisgitter.

Alles in Grad und Metern, damit `spot.move(turn=tag.bearing)` ohne Umrechnung
funktioniert — ein Schueler soll dafuer nicht `math.degrees` kennen muessen.

Die Datenklassen liegen in `backends/base.py` neben Feedback und NavStatus, wo
die backend-unabhaengigen Formen wohnen; hier werden sie re-exportiert, weil
`from spotlab.api.world import Tag` die Schuelertuer ist.
"""

from spotlab.backends.base import (  # noqa: F401  (Re-Export)
    Capability,
    ObstacleGrid,
    Tag,
    WorldObject,
    require,
    richtung,
)

__all__ = [
    "WorldObject", "Tag", "ObstacleGrid", "richtung",
    "world_objects", "tags", "obstacles",
]


def _protokolliere(recorder, name, **daten):
    if recorder is not None:
        recorder.event("kommando", name=name, **daten)


def world_objects(backend, recorder, kinds=None):
    """Alles, was Spots Firmware gerade als Objekt führt, nächstes zuerst."""
    require(backend, Capability.WORLD_OBJECTS, "Objekte in der Umgebung nennen")
    gefunden = sorted(backend.world_objects(kinds=kinds), key=lambda o: o.distance)
    _protokolliere(
        recorder, "world_objects",
        treffer=len(gefunden),
        arten=sorted({o.kind for o in gefunden}),
        distanzen=[round(o.distance, 2) for o in gefunden],
    )
    return gefunden


def tags(backend, recorder, id=None):
    """Die sichtbaren AprilTags, nächstes zuerst. Ohne `id` zählt jeder.

    `spot.tags()[0]` ist damit ohne Nachdenken das nächste Ziel.
    """
    require(backend, Capability.WORLD_OBJECTS, "Objekte in der Umgebung nennen")
    gefunden = [
        objekt for objekt in backend.world_objects(kinds=["apriltag"])
        if id is None or getattr(objekt, "id", None) == id
    ]
    gefunden.sort(key=lambda t: t.distance)
    # Auch die erfolglose Abfrage wird protokolliert: "vier Sekunden lang nichts
    # gesehen" ist eine Information, die man nachher braucht.
    _protokolliere(
        recorder, "tags",
        treffer=len(gefunden),
        ids=[t.id for t in gefunden],
        distanzen=[round(t.distance, 2) for t in gefunden],
    )
    return gefunden


def obstacles(backend, recorder):
    """Das Hindernisgitter: je Zelle der Abstand zum nächsten Hindernis."""
    require(backend, Capability.LOCAL_GRID, "das Hindernisgitter lesen")
    gitter = backend.local_grid()
    _protokolliere(recorder, "obstacles", zellengroesse=gitter.cell_size)
    return gitter
