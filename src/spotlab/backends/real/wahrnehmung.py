"""Objekte und Hindernisgitter vom echten Spot.

`WorldObjectClient` und `LocalGridClient` sind reine LESEDIENSTE: kein Lease,
kein Kommando, keine Möglichkeit, den Roboter zu bewegen. Deshalb darf die Sonde
(`workshop/sonde.py`) sie neben einem fremden Lease benutzen — dieselbe
Begründung wie bei `beobachtung/` und `maps/`.

Hier fällt die Protobuf-Grenze: nach oben gehen ausschliesslich die Datenklassen
aus `backends/base.py`.
"""

import math

import numpy as np
from bosdyn.client import frame_helpers as fh
from bosdyn.client.math_helpers import SE3Pose

from spotlab.backends.base import (
    ObstacleGrid,
    Staircase,
    Tag,
    TrackedEntity,
    WorldObject,
    richtung,
)

GITTERTYP = "obstacle_distance"

# Feldname im Protobuf -> unser Artname. AprilTags stehen ausserhalb, weil sie
# als einzige einen eigenen Rahmennamen und eine gefilterte Pose mitbringen.
# Nicht jede SDK-Fassung kennt jedes dieser Felder: `door_properties` gibt es in
# bosdyn-api 5.0.1.2 nicht (mehr). `HasField` WIRFT auf ein unbekanntes Feld —
# und weil diese Schleife fuer JEDES Objekt laeuft, riss ein einziger toter
# Eintrag die ganze Wahrnehmung mit, sobald ein Objekt kein Dock war. Deshalb
# wird gefragt, was das Protobuf hier wirklich hat (`_hat`), statt es zu glauben.
ARTEN = {
    "dock_properties": "dock",
    "door_properties": "door",
    "image_properties": "image_coordinates",
    "tracked_entity_properties": "tracked_entity",
}

# `TrackedEntityProperties.entity_type` -> unser Name.
ENTITAETSARTEN = {
    0: "unknown", 1: "3d_blob", 2: "person", 3: "forklift", 4: "spot",
}
# Derselbe Zahlenschluessel in `type_likelihoods` -- dort steht, fuer wie
# wahrscheinlich die Firmware jeden Typ haelt.
PERSON = 2


def _art_und_rahmen(obj):
    """(Art, Rahmenname, gefiltert) — oder (None, None, False), wenn unbekannt."""
    if _hat(obj, "apriltag_properties"):
        props = obj.apriltag_properties
        gefiltert = bool(props.frame_name_fiducial_filtered)
        # Die gefilterte Pose ist über die Zeit geglättet und ruhiger; die rohe
        # ist aktueller. Wir nehmen die gefilterte und SAGEN es im Feld —
        # verschweigen wäre eine stille Genauigkeitsaussage.
        rahmen = props.frame_name_fiducial_filtered or props.frame_name_fiducial
        return "apriltag", rahmen, gefiltert
    for feld, art in ARTEN.items():
        if _hat(obj, feld):
            return art, obj.name, False
    return None, None, False


def _hat(obj, feld):
    """Hat dieses Protobuf das Feld -- und ist es gesetzt?"""
    return feld in obj.DESCRIPTOR.fields_by_name and obj.HasField(feld)


def _pose(schnappschuss, rahmen, bezug):
    try:
        return fh.get_a_tform_b(schnappschuss, bezug, rahmen)
    except Exception:
        return None


def _treppe_aus(obj, jetzt):
    """Eine `Staircase` aus `staircase_properties` -- oder None ohne Rahmen.

    Der Treppenrahmen der Firmware sitzt am Fuss der Treppe, x zeigt bergauf
    (`stairs.proto`). Fuss und Kopf werden in den Koerper geholt; die naehere
    Kante gibt Peilung und Abstand, die Lage des Roboters die Richtung.
    """
    treppe = obj.staircase_properties.staircase
    rahmen = treppe.stair_tform.frame_name
    koerper_tform_rahmen = _pose(obj.transforms_snapshot, rahmen, fh.BODY_FRAME_NAME) if rahmen else None
    if koerper_tform_rahmen is None:
        return None
    koerper_tform_treppe = koerper_tform_rahmen * SE3Pose.from_proto(treppe.stair_tform.frame_tform_stairs)
    stufen = int(treppe.number_of_steps)
    laenge = stufen * float(treppe.average_run)
    achse = koerper_tform_treppe.rot.to_yaw()
    fuss = (float(koerper_tform_treppe.x), float(koerper_tform_treppe.y))
    kopf = (fuss[0] + laenge * math.cos(achse), fuss[1] + laenge * math.sin(achse))
    am_fuss = math.hypot(*fuss) <= math.hypot(*kopf)
    peilung, distanz = richtung(*(fuss if am_fuss else kopf))
    welt = _pose(obj.transforms_snapshot, rahmen, fh.VISION_FRAME_NAME)
    welt_xy = None
    if welt is not None:
        w = welt * SE3Pose.from_proto(treppe.stair_tform.frame_tform_stairs)
        welt_xy = (float(w.x), float(w.y))
    return Staircase(
        name=obj.name, kind="staircase", bearing=peilung, distance=distanz,
        world_xy=welt_xy, time=jetzt, direction="auf" if am_fuss else "ab",
        steps=stufen, rise_m=round(stufen * float(treppe.average_rise), 3),
        axis_bearing=math.degrees(achse),
    )


def objekte_aus(antwort, jetzt):
    """Protobuf-Antwort in Datenklassen, nächstes Objekt zuerst.

    Überspringt, was sich nicht verorten lässt: ein Objekt mit erfundener
    Distanz 0 wäre schlimmer als ein fehlendes.
    """
    gefunden = []
    for obj in antwort.world_objects:
        if _hat(obj, "staircase_properties"):
            treppe = _treppe_aus(obj, jetzt)
            if treppe is not None:
                gefunden.append(treppe)
            continue
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
        elif art == "tracked_entity":
            gefunden.append(_verfolgtes(obj, gemeinsam))
        else:
            gefunden.append(WorldObject(**gemeinsam))
    return sorted(gefunden, key=lambda o: o.distance)


def _verfolgtes(obj, gemeinsam):
    """Ein `TrackedEntity` aus `tracked_entity_properties`."""
    props = obj.tracked_entity_properties
    geschwindigkeit = math.hypot(float(props.velocity.x), float(props.velocity.y))
    return TrackedEntity(
        **gemeinsam,
        entity_id=int(props.entity_id),
        entity_type=ENTITAETSARTEN.get(int(props.entity_type), "unknown"),
        likelihood=float(props.likelihood_exists),
        person_likelihood=float(props.type_likelihoods.get(PERSON, 0.0)),
        speed=geschwindigkeit,
        observations=int(props.num_observations),
    )


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
    # (ny, nx): local_grid.proto legt Zelle (i, j) bei i * num_cells_x + j ab --
    # x laeuft am schnellsten, das Array ist [zeile = y, spalte = x]. Genau so
    # indiziert `ObstacleGrid._zelle`. Bei 128x128 faellt der Unterschied nicht
    # auf; er faellt auf, sobald ein Gitter nicht quadratisch ist.
    n = (g.extent.num_cells_y, g.extent.num_cells_x)
    roh = np.frombuffer(g.data, dtype=_dtypen()[g.cell_format])
    if g.encoding == lg.LocalGrid.ENCODING_RLE:
        roh = np.repeat(roh, np.asarray(g.rle_counts, dtype=np.int64))
    zellen = roh.reshape(n).astype(np.float64) * g.cell_value_scale + g.cell_value_offset

    bekannt = None
    if g.unknown_cells:
        # EIN BYTE je Zelle (0 = bekannt, 1 = unbekannt) -- GEMESSEN an der
        # Aufzeichnung vom 12.08.2026 (tests/daten/gitter_real_20260812), 16384
        # Bytes fuer 128x128. Bis zum 06.09.2026 wurde hier bitweise entpackt:
        # die ersten 2048 Bytes als Bits, der Rest ignoriert -- am echten Spot
        # eine falsche Maske, und `is_free()` hielt Unbekanntes fuer frei.
        # Bitgepackt waren nur alte Sim-Aufzeichnungen aus matura-spot; die
        # bleiben an der Laenge erkennbar und lesbar.
        roh = np.frombuffer(g.unknown_cells, dtype=np.uint8)
        anzahl = n[0] * n[1]
        if roh.size == anzahl:
            unbekannt = roh.reshape(n).astype(bool)
        else:
            unbekannt = np.unpackbits(roh, count=anzahl, bitorder="little").reshape(n).astype(bool)
        bekannt = ~unbekannt

    ecke = _pose(g.transforms_snapshot, g.frame_name_local_grid_data,
                 fh.VISION_FRAME_NAME)
    # `origin` ist die MITTE der Zelle [0, 0] -- so rechnet `ObstacleGrid._zelle`
    # (round), und so liegt der Ursprung auch im 2D-Uebungsraum. Der Rahmen des
    # Dienstes zeigt auf die ECKE des Gitters; die halbe Zelle dazu, sonst
    # kippt jede Anfrage im zweiten Drittel einer Zelle in die Nachbarzelle.
    halb = float(g.extent.cell_size) / 2.0
    return ObstacleGrid(
        cells=zellen,
        cell_size=g.extent.cell_size,
        origin=(float(ecke.x) + halb, float(ecke.y) + halb) if ecke else (halb, halb),
        time=g.acquisition_time.seconds + g.acquisition_time.nanos / 1e9,
        known=bekannt,
    )


def objekte_holen(client, jetzt, kinds=None):
    """Reiner Lesedienst — nie ein Kommando."""
    from bosdyn.api import world_object_pb2 as wo

    typen = None
    if kinds is not None and set(kinds) == {"apriltag"}:
        typen = [wo.WORLD_OBJECT_APRILTAG]
    elif kinds is not None and set(kinds) == {"staircase"}:
        typen = [wo.WORLD_OBJECT_STAIRCASE]
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
