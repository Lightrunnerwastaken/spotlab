"""Die Protobuf-Grenze: echte world_object-Protobufs hinein, Datenklassen heraus.

Laeuft ohne Roboter — gebaut wird gegen die SDK-Schemata, wie in test_dryrun.py.
"""

import pytest
from bosdyn.api import world_object_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME

from spotlab.backends.base import Tag, WorldObject
from spotlab.backends.real.wahrnehmung import objekte_aus


def _kante(obj, rahmen, x, y, eltern=BODY_FRAME_NAME):
    kante = obj.transforms_snapshot.child_to_parent_edge_map[rahmen]
    kante.parent_frame_name = eltern
    kante.parent_tform_child.position.x = x
    kante.parent_tform_child.position.y = y
    kante.parent_tform_child.rotation.w = 1.0


def _apriltag(nummer, x, y):
    obj = world_object_pb2.WorldObject()
    obj.name = f"world_obj_apriltag_{nummer:03d}"
    obj.apriltag_properties.tag_id = nummer
    rahmen = f"fiducial_{nummer}"
    obj.apriltag_properties.frame_name_fiducial = rahmen
    _kante(obj, rahmen, x, y)
    obj.transforms_snapshot.child_to_parent_edge_map[BODY_FRAME_NAME].SetInParent()
    return obj


class Antwort:
    def __init__(self, objekte):
        self.world_objects = objekte


def test_apriltag_wird_zu_einem_tag_in_grad():
    gefunden = objekte_aus(Antwort([_apriltag(1, 3.0, 4.0)]), jetzt=100.0)
    assert len(gefunden) == 1
    tag = gefunden[0]
    assert isinstance(tag, Tag)
    assert tag.id == 1
    assert tag.distance == pytest.approx(5.0)
    assert tag.bearing == pytest.approx(53.13, abs=0.1)


def test_objekt_ohne_transformation_wird_uebersprungen_nicht_genullt():
    """Eine falsche Zahl ist schlimmer als eine fehlende."""
    kaputt = world_object_pb2.WorldObject()
    kaputt.name = "world_obj_apriltag_009"
    kaputt.apriltag_properties.tag_id = 9
    kaputt.apriltag_properties.frame_name_fiducial = "gibt_es_nicht"
    assert objekte_aus(Antwort([kaputt]), jetzt=100.0) == []


def test_gefilterte_pose_wird_bevorzugt_und_ausgewiesen():
    obj = _apriltag(1, 3.0, 4.0)
    obj.apriltag_properties.frame_name_fiducial_filtered = "filtered_1"
    _kante(obj, "filtered_1", 1.0, 0.0)

    tag = objekte_aus(Antwort([obj]), jetzt=100.0)[0]
    assert tag.filtered is True
    assert tag.distance == pytest.approx(1.0)


def test_nicht_tag_objekt_wird_zu_worldobject():
    obj = world_object_pb2.WorldObject()
    obj.name = "world_obj_dock_003"
    obj.dock_properties.dock_id = 3
    _kante(obj, obj.name, 1.0, 0.0)
    obj.transforms_snapshot.child_to_parent_edge_map[BODY_FRAME_NAME].SetInParent()

    gefunden = objekte_aus(Antwort([obj]), jetzt=100.0)
    assert len(gefunden) == 1
    assert type(gefunden[0]) is WorldObject
    assert gefunden[0].kind == "dock"


def test_naechstes_objekt_steht_vorne():
    antwort = Antwort([_apriltag(2, 9.0, 0.0), _apriltag(1, 2.0, 0.0)])
    assert [t.id for t in objekte_aus(antwort, jetzt=100.0)] == [1, 2]


# ------------------------------------------------------------- Treppen (Stufe 13)


def _treppe(bottom_x, koerper_x, stufen=6, rise=0.17, run=0.3):
    """Eine Treppe im odom-Rahmen bei x = bottom_x, bergauf nach +x; der Koerper bei koerper_x."""
    obj = world_object_pb2.WorldObject()
    obj.name = "world_obj_staircase_1"
    st = obj.staircase_properties.staircase
    st.stair_tform.frame_name = "odom"
    st.stair_tform.frame_tform_stairs.position.x = bottom_x
    st.stair_tform.frame_tform_stairs.rotation.w = 1.0
    st.number_of_steps = stufen
    st.average_rise = rise
    st.average_run = run
    baum = obj.transforms_snapshot.child_to_parent_edge_map
    baum["odom"].SetInParent()
    baum[BODY_FRAME_NAME].parent_frame_name = "odom"
    baum[BODY_FRAME_NAME].parent_tform_child.position.x = koerper_x
    baum[BODY_FRAME_NAME].parent_tform_child.rotation.w = 1.0
    return obj


def test_eine_treppe_wird_zu_einer_staircase_mit_richtung():
    from spotlab.backends.base import Staircase

    unten = objekte_aus(Antwort([_treppe(2.0, 0.0)]), jetzt=5.0)
    assert len(unten) == 1 and isinstance(unten[0], Staircase)
    t = unten[0]
    assert t.kind == "staircase" and t.direction == "auf" and t.steps == 6
    assert t.rise_m == pytest.approx(1.02) and t.distance == pytest.approx(2.0)
    assert t.bearing == pytest.approx(0.0) and t.axis_bearing == pytest.approx(0.0)
    oben = objekte_aus(Antwort([_treppe(2.0, 5.0)]), jetzt=5.0)[0]
    assert oben.direction == "ab" and oben.distance == pytest.approx(5.0 - 2.0 - 6 * 0.3)
    assert abs(oben.bearing) == pytest.approx(180.0)


def test_eine_treppe_ohne_rahmen_wird_uebersprungen():
    obj = _treppe(2.0, 0.0)
    obj.staircase_properties.staircase.stair_tform.frame_name = "gibt_es_nicht"
    assert objekte_aus(Antwort([obj]), jetzt=5.0) == []


# ================== Spots eigener Personen-Tracker (tracked_entity)
#
# Der Tracker steckt in der Firmware: er vergibt eine Nummer, haelt sie ueber
# die Zeit und sagt, fuer wie sicher er das Ding und seinen Typ haelt. Ob ein
# Roboter das liefert, zeigt erst das Geraet (A34).


def _verfolgt(name, x, y, art=2, sicher=0.9, person=0.8, vx=0.0, vy=0.0, gesehen=12):
    obj = world_object_pb2.WorldObject()
    obj.name = name
    props = obj.tracked_entity_properties
    props.entity_id = 7
    props.entity_type = art
    props.likelihood_exists = sicher
    props.type_likelihoods[2] = person
    props.velocity.x, props.velocity.y = vx, vy
    props.num_observations = gesehen
    _kante(obj, name, x, y)
    obj.transforms_snapshot.child_to_parent_edge_map[BODY_FRAME_NAME].SetInParent()
    return obj


def test_ein_verfolgter_mensch_wird_zu_einer_trackedentity():
    from spotlab.backends.base import TrackedEntity

    [gefunden] = objekte_aus(Antwort([_verfolgt("entity_7", 3.0, 4.0, vx=0.3, vy=0.4)]),
                             jetzt=100.0)
    assert isinstance(gefunden, TrackedEntity) and gefunden.kind == "tracked_entity"
    assert gefunden.entity_id == 7 and gefunden.entity_type == "person"
    assert gefunden.distance == pytest.approx(5.0)
    assert gefunden.bearing == pytest.approx(53.13, abs=0.1)
    assert gefunden.likelihood == pytest.approx(0.9)
    assert gefunden.person_likelihood == pytest.approx(0.8)
    assert gefunden.speed == pytest.approx(0.5), "Betrag aus vx und vy"
    assert gefunden.observations == 12


def test_andere_entitaetsarten_behalten_ihren_namen():
    [blob] = objekte_aus(Antwort([_verfolgt("entity_1", 1.0, 0.0, art=1)]), jetzt=100.0)
    assert blob.entity_type == "3d_blob"
    [unbekannt] = objekte_aus(Antwort([_verfolgt("entity_2", 1.0, 0.0, art=99)]), jetzt=100.0)
    assert unbekannt.entity_type == "unknown"


def test_ein_verfolgtes_ohne_rahmen_wird_uebersprungen():
    """Wie bei jedem Objekt: keine erfundene Position (`bearing` 0 waere eine)."""
    obj = world_object_pb2.WorldObject()
    obj.name = "entity_7"
    obj.tracked_entity_properties.entity_id = 7
    assert objekte_aus(Antwort([obj]), jetzt=100.0) == []


def test_ein_feld_das_diese_sdk_fassung_nicht_kennt_reisst_nichts_mit():
    """`door_properties` gibt es in bosdyn-api 5.0.1.2 nicht, steht aber in
    ARTEN. `HasField` wirft darauf -- und riss die ganze Wahrnehmung mit,
    sobald ein Objekt kein Dock war (gefunden am 09.09.2026)."""
    from spotlab.backends.real.wahrnehmung import ARTEN, _hat

    obj = world_object_pb2.WorldObject()
    assert "door_properties" in ARTEN
    assert "door_properties" not in obj.DESCRIPTOR.fields_by_name
    assert _hat(obj, "door_properties") is False
    # Und der ganze Weg darueber: ein verfolgtes Objekt kommt trotzdem an.
    assert len(objekte_aus(Antwort([_verfolgt("entity_7", 1.0, 0.0)]), jetzt=1.0)) == 1
