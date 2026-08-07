import pytest
from bosdyn.api.graph_nav import graph_nav_pb2, map_pb2

from spotlab.backends.base import Capability
from spotlab.backends.real.graphnav import (
    localize,
    navigate_step,
    navigation_status,
    travel_params,
    upload_map,
)
from spotlab.config import Limits
from spotlab.errors import NotLocalized


class FakeGraphNav:
    def __init__(self, unbekannte_snapshots=()):
        self.protokoll = []
        self._unbekannt = list(unbekannte_snapshots)
        self.letzte_params = None

    def clear_graph(self, **kw):
        self.protokoll.append("clear")

    def upload_graph(self, graph=None, generate_new_anchoring=False, **kw):
        self.protokoll.append(f"upload_graph:{len(graph.waypoints)}")
        antwort = graph_nav_pb2.UploadGraphResponse()
        for kennung in self._unbekannt:
            antwort.unknown_waypoint_snapshot_ids.append(kennung)
        return antwort

    def upload_waypoint_snapshot(self, waypoint_snapshot, **kw):
        self.protokoll.append(f"upload_wp:{waypoint_snapshot.id}")

    def upload_edge_snapshot(self, edge_snapshot, **kw):
        self.protokoll.append(f"upload_edge:{edge_snapshot.id}")

    def set_localization(self, initial_guess_localization, fiducial_init=None, **kw):
        self.protokoll.append(f"localize:{fiducial_init}")

    def get_localization_state(self, **kw):
        antwort = graph_nav_pb2.GetLocalizationStateResponse()
        antwort.localization.waypoint_id = "wp-hier"
        return antwort

    def navigate_to(self, destination_waypoint_id, cmd_duration, travel_params=None,
                    command_id=None, **kw):
        self.letzte_params = travel_params
        self.protokoll.append(f"nav:{destination_waypoint_id}:{cmd_duration}")
        return 42

    def navigation_feedback(self, command_id=0, **kw):
        antwort = graph_nav_pb2.NavigationFeedbackResponse()
        antwort.status = graph_nav_pb2.NavigationFeedbackResponse.STATUS_REACHED_GOAL
        return antwort


class FakeRobot:
    def __init__(self, graphnav):
        self._graphnav = graphnav

    def ensure_client(self, name):
        return self._graphnav


def _karte(tmp_path, snapshots=()):
    graph = map_pb2.Graph()
    wp = graph.waypoints.add()
    wp.id = "wp0"
    wp.snapshot_id = "snap0"
    ordner = tmp_path / "turnhalle"
    (ordner / "waypoint_snapshots").mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    for kennung in snapshots:
        schnappschuss = map_pb2.WaypointSnapshot()
        schnappschuss.id = kennung
        (ordner / "waypoint_snapshots" / kennung).write_bytes(
            schnappschuss.SerializeToString()
        )
    return ordner


def test_hochladen_leert_zuerst_und_laedt_dann(tmp_path):
    fake = FakeGraphNav()
    upload_map(FakeRobot(fake), _karte(tmp_path))
    assert fake.protokoll[0] == "clear"
    assert "upload_graph:1" in fake.protokoll


def test_fehlende_schnappschuesse_werden_nachgeladen(tmp_path):
    fake = FakeGraphNav(unbekannte_snapshots=["snap0"])
    upload_map(FakeRobot(fake), _karte(tmp_path, snapshots=["snap0"]))
    assert "upload_wp:snap0" in fake.protokoll


def test_lokalisieren_nutzt_das_naechste_fiducial():
    fake = FakeGraphNav()
    kennung = localize(FakeRobot(fake))
    assert kennung == "wp-hier"
    erwartet = graph_nav_pb2.SetLocalizationRequest.FIDUCIAL_INIT_NEAREST
    assert f"localize:{erwartet}" in fake.protokoll


def test_lokalisieren_ohne_ergebnis_wirft_klartext():
    class OhneVerortung(FakeGraphNav):
        def get_localization_state(self, **kw):
            return graph_nav_pb2.GetLocalizationStateResponse()

    with pytest.raises(NotLocalized) as info:
        localize(FakeRobot(OhneVerortung()))
    assert "Fiducial" in str(info.value)


def test_travel_params_tragen_den_geschwindigkeitsdeckel():
    params = travel_params(Limits(max_speed=0.35, max_turn_rate=0.5))
    assert abs(params.velocity_limit.max_vel.linear.x - 0.35) < 1e-9
    assert abs(params.velocity_limit.max_vel.angular - 0.5) < 1e-9


def test_travel_params_setzen_auch_die_untergrenze():
    """Ohne min_vel bremst der Roboter nur vorwärts, nicht rückwärts."""
    params = travel_params(Limits(max_speed=0.35, max_turn_rate=0.5))
    assert abs(params.velocity_limit.min_vel.linear.x + 0.35) < 1e-9


def test_navigationsschritt_reicht_params_durch():
    fake = FakeGraphNav()
    params = travel_params(Limits())
    kennung = navigate_step(FakeRobot(fake), "wp1", 1.0, params)
    assert kennung == 42
    assert fake.letzte_params is params
    assert "nav:wp1:1.0" in fake.protokoll


def test_rueckmeldung_wird_uebersetzt():
    zustand = navigation_status(FakeRobot(FakeGraphNav()), 42)
    assert zustand.fertig is True
    assert "Angekommen" in zustand.status


def test_realspot_kann_graph_nav():
    from spotlab.backends.real.session import RealSpot

    koennen = RealSpot.capabilities(None)
    assert koennen & Capability.GRAPH_NAV
