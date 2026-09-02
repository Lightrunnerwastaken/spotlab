"""Objekte und Hindernisgitter vom echten Spot.

`WorldObjectClient` und `LocalGridClient` sind reine LESEDIENSTE: kein Lease,
kein Kommando, keine Möglichkeit, den Roboter zu bewegen. Deshalb darf die Sonde
(`workshop/sonde.py`) sie neben einem fremden Lease benutzen — dieselbe
Begründung wie bei `beobachtung/` und `maps/`.

Hier fällt die Protobuf-Grenze: nach oben gehen ausschliesslich die Datenklassen
aus `backends/base.py`.
"""

import numpy as np
from bosdyn.client import frame_helpers as fh

from spotlab.backends.base import ObstacleGrid, Tag, WorldObject, richtung

GITTERTYP = "obstacle_distance"

# Feldname im Protobuf -> unser Artname. AprilTags stehen ausserhalb, weil sie
# als einzige einen eigenen Rahmennamen und eine gefilterte Pose mitbringen.
ARTEN = {
    "dock_properties": "dock",
    "door_properties": "door",
    "image_properties": "image_coordinates",
}


def _art_und_rahmen(obj):
    """(Art, Rahmenname, gefiltert) — oder (None, None, False), wenn unbekannt."""
    if obj.HasField("apriltag_properties"):
        props = obj.apriltag_properties
        gefiltert = bool(props.frame_name_fiducial_filtered)
        # Die gefilterte Pose ist über die Zeit geglättet und ruhiger; die rohe
        # ist aktueller. Wir nehmen die gefilterte und SAGEN es im Feld —
        # verschweigen wäre eine stille Genauigkeitsaussage.
        rahmen = props.frame_name_fiducial_filtered or props.frame_name_fiducial
        return "apriltag", rahmen, gefiltert
    for feld, art in ARTEN.items():
        if obj.HasField(feld):
            return art, obj.name, False
    return None, None, False


def _pose(schnappschuss, rahmen, bezug):
    try:
        return fh.get_a_tform_b(schnappschuss, bezug, rahmen)
    except Exception:
        return None


def objekte_aus(antwort, jetzt):
    """Protobuf-Antwort in Datenklassen, nächstes Objekt zuerst.

    Überspringt, was sich nicht verorten lässt: ein Objekt mit erfundener
    Distanz 0 wäre schlimmer als ein fehlendes.
    """
    gefunden = []
    for obj in antwort.world_objects:
        art, rahmen, gefiltert = _art_und_rahmen(obj)
        if art is None or not rahmen:
            continue
        koerper = _pose(obj.transforms_snapshot, rahmen, fh.BODY_FRAME_NAME)
        if koerper is None:
            continue
        peilung, distanz = richtung(float(koerper.x), float(koerper.y))
        welt = _pose(obj.transforms_snapshot, rahmen, fh.VISION_FRAME_NAME)
        gemeinsam = dict(
            name=obj.name, kind=art, bearing=peilung, distance=distanz,
            world_xy=(float(welt.x), float(welt.y)) if welt is not None else None,
            time=jetzt,
        )
        if art == "apriltag":
            gefunden.append(
                Tag(**gemeinsam, id=int(obj.apriltag_properties.tag_id),
                    filtered=gefiltert)
            )
        else:
            gefunden.append(WorldObject(**gemeinsam))
    return sorted(gefunden, key=lambda o: o.distance)


def _dtypen():
    """Zellformat-Enum -> numpy-dtype. Lazy, damit der Import billig bleibt."""
    from bosdyn.api import local_grid_pb2 as lg

    return {
        lg.LocalGrid.CELL_FORMAT_FLOAT32: np.float32,
        lg.LocalGrid.CELL_FORMAT_FLOAT64: np.float64,
        lg.LocalGrid.CELL_FORMAT_INT16: "<i2",
        lg.LocalGrid.CELL_FORMAT_UINT16: "<u2",
        lg.LocalGrid.CELL_FORMAT_INT8: np.int8,
        lg.LocalGrid.CELL_FORMAT_UINT8: np.uint8,
    }


def gitter_aus(antwort):
    """Eine `LocalGridResponse` in ein `ObstacleGrid`.

    Portiert aus `matura-spot: spotsim/local_grid.py::grid_aus_proto`. Das SDK
    bringt KEINEN Entpacker mit — `expand_data_by_rle_count` und `unpack_grid`
    liegen nur im Beispiel `examples/visualizer/`, nicht im installierten Paket.
    Die portierte Fassung ist ohnehin besser: sie entpackt RLE vektorisiert
    (`np.repeat` statt Python-Doppelschleife) und wertet `unknown_cells` aus,
    was das Beispiel gar nicht tut.
    """
    from bosdyn.api import local_grid_pb2 as lg

    g = antwort.local_grid
    n = (g.extent.num_cells_x, g.extent.num_cells_y)
    roh = np.frombuffer(g.data, dtype=_dtypen()[g.cell_format])
    if g.encoding == lg.LocalGrid.ENCODING_RLE:
        roh = np.repeat(roh, np.asarray(g.rle_counts, dtype=np.int64))
    zellen = roh.reshape(n).astype(np.float64) * g.cell_value_scale + g.cell_value_offset

    bekannt = None
    if g.unknown_cells:
        unbekannt = np.unpackbits(
            np.frombuffer(g.unknown_cells, dtype=np.uint8),
            count=n[0] * n[1], bitorder="little",
        ).reshape(n).astype(bool)
        bekannt = ~unbekannt

    ursprung = _pose(g.transforms_snapshot, g.frame_name_local_grid_data,
                     fh.VISION_FRAME_NAME)
    return ObstacleGrid(
        cells=zellen,
        cell_size=g.extent.cell_size,
        origin=(float(ursprung.x), float(ursprung.y)) if ursprung else (0.0, 0.0),
        time=g.acquisition_time.seconds + g.acquisition_time.nanos / 1e9,
        known=bekannt,
    )


def objekte_holen(client, jetzt, kinds=None):
    """Reiner Lesedienst — nie ein Kommando."""
    from bosdyn.api import world_object_pb2 as wo

    typen = None
    if kinds is not None and set(kinds) == {"apriltag"}:
        typen = [wo.WORLD_OBJECT_APRILTAG]
    antwort = (client.list_world_objects(object_type=typen) if typen
               else client.list_world_objects())
    gefunden = objekte_aus(antwort, jetzt)
    if kinds is None:
        return gefunden
    return [objekt for objekt in gefunden if objekt.kind in kinds]


def gitter_holen(client):
    """Reiner Lesedienst — nie ein Kommando."""
    antworten = client.get_local_grids([GITTERTYP])
    if not antworten:
        raise RuntimeError("Der LocalGrid-Dienst hat nichts geliefert.")
    return gitter_aus(antworten[0])
