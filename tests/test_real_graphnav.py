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


# ================================= S2.6 GraphNav-Fehler in deutschem Klartext


class _KaputterRobot:
    def __init__(self, fehler):
        self._fehler = fehler

    def ensure_client(self, name):
        return self

    def upload_graph(self, **kw):
        raise self._fehler

    def set_localization(self, **kw):
        raise self._fehler

    def clear_graph(self, **kw):
        raise self._fehler

    def get_localization_state(self):
        raise self._fehler


def test_aufnahme_laeuft_noch_wird_erklaert(tmp_path):
    from bosdyn.api.graph_nav import map_pb2
    from bosdyn.client.graph_nav import CannotModifyMapDuringRecordingError

    from spotlab.backends.real import graphnav
    from spotlab.errors import MapError

    (tmp_path / "graph").write_bytes(map_pb2.Graph().SerializeToString())
    robot = _KaputterRobot(CannotModifyMapDuringRecordingError(response=None))
    with pytest.raises(MapError) as fehler:
        graphnav.upload_map(robot, tmp_path)
    assert "Kartenaufnahme" in str(fehler.value)


def test_netzfehler_beim_verorten_meldet_das_netz():
    from bosdyn.client.exceptions import RetryableUnavailableError

    from spotlab.backends.real import graphnav
    from spotlab.errors import NotReachable

    robot = _KaputterRobot(RetryableUnavailableError(OSError("weg")))
    with pytest.raises(NotReachable):
        graphnav.localize(robot)


def test_die_ortung_ist_relativ_zum_eigenen_wegpunkt():
    """Fuer die Zeichnung im Karten-Tab: Wegpunkt plus Versatz des Koerpers in
    dessen Rahmen -- nicht der Seed-Rahmen, der bei einem Grundriss ohne Anker
    nicht der Rahmen der Zeichnung ist."""
    import math

    from spotlab.backends.real.graphnav import localization

    class MitLage(FakeGraphNav):
        def get_localization_state(self, **kw):
            antwort = graph_nav_pb2.GetLocalizationStateResponse()
            antwort.localization.waypoint_id = "wp-hier"
            lage = antwort.localization.waypoint_tform_body
            lage.position.x, lage.position.y = 1.5, -0.5
            lage.rotation.w = math.cos(math.radians(90) / 2)
            lage.rotation.z = math.sin(math.radians(90) / 2)
            return antwort

    kennung, (dx, dy, grad) = localization(FakeRobot(MitLage()))
    assert kennung == "wp-hier" and (dx, dy) == (1.5, -0.5) and abs(grad - 90.0) < 1e-6

    class Ohne(FakeGraphNav):
        def get_localization_state(self, **kw):
            return graph_nav_pb2.GetLocalizationStateResponse()

    assert localization(FakeRobot(Ohne())) is None, "nicht verortet ist keine Lage"


# ============ Eine gespeicherte Karte nachtraeglich nachbearbeiten
#
# Hochladen braucht ein Lease (`UploadGraphRequest.lease`) -- deshalb laeuft das
# hier am RealSpot und nicht in der GUI. Das Nachbearbeiten und das
# Herunterladen brauchen keines.


class FakeProcessingClient:
    def __init__(self, neue_kanten=2, schritte=5):
        from bosdyn.api.graph_nav import map_processing_pb2

        self._mp = map_processing_pb2
        self._neue_kanten = neue_kanten
        self._schritte = schritte
        self.protokoll = []

    def process_topology(self, params=None, modify_map_on_server=None, timeout=None):
        self.protokoll.append("topology")
        antwort = self._mp.ProcessTopologyResponse()
        for i in range(self._neue_kanten):
            antwort.new_subgraph.edges.add().id.from_waypoint = f"wp{i}"
        return antwort

    def process_anchoring(self, **kw):
        self.protokoll.append("anchoring")
        return self._mp.ProcessAnchoringResponse(iteration=self._schritte)


class _RobotMitDiensten:
    def __init__(self, graphnav, processing=None):
        self._dienste = {"graph-nav-service": graphnav}
        if processing is not None:
            self._dienste["map-processing-service"] = processing

    def ensure_client(self, name):
        if name not in self._dienste:
            raise RuntimeError(f"Dienst {name} fehlt")
        return self._dienste[name]


def test_nachbearbeiten_geht_ueber_dieselbe_formulierung():
    from spotlab.backends.real.graphnav import process_map

    prozessor = FakeProcessingClient(neue_kanten=2, schritte=5)
    bericht = process_map(_RobotMitDiensten(FakeGraphNav(), prozessor))
    assert prozessor.protokoll == ["topology", "anchoring"]
    assert (bericht.neue_kanten, bericht.schritte) == (2, 5)


def test_ohne_den_dienst_wird_es_gesagt_statt_zu_werfen():
    from spotlab.backends.real.graphnav import process_map

    bericht = process_map(_RobotMitDiensten(FakeGraphNav()))       # kein Prozessor
    assert not bericht.gelaufen
    assert any("map-processing-service" in m for m in bericht.meldungen)


class _GraphNavMitDownload(FakeGraphNav):
    def __init__(self, wegpunkte=3, kaputt=False):
        super().__init__()
        self._wegpunkte = wegpunkte
        self._kaputt = kaputt

    def write_graph_and_snapshots(self, verzeichnis):
        from pathlib import Path

        self.protokoll.append(f"write:{Path(verzeichnis).name}")
        graph = map_pb2.Graph()
        for i in range(self._wegpunkte):
            graph.waypoints.add().id = f"wp{i}"
        daten = b"kaputt" if self._kaputt else graph.SerializeToString()
        (Path(verzeichnis) / "graph").write_bytes(daten)


def _gespeicherte_karte(tmp_path):
    from spotlab.maps.store import karten_wurzel, speichere_metadaten

    graph = map_pb2.Graph()
    graph.waypoints.add().id = "alt0"
    ordner = karten_wurzel(tmp_path) / "flur"
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    speichere_metadaten(ordner, "flur", "SN-1", graph)
    return ordner


def test_herunterladen_ersetzt_die_karte_und_zieht_die_zahlen_nach(tmp_path):
    import json

    from spotlab.backends.real.graphnav import download_map
    from spotlab.maps.store import METADATEN

    ordner = _gespeicherte_karte(tmp_path)
    dienst = _GraphNavMitDownload(wegpunkte=4)
    graph = download_map(_RobotMitDiensten(dienst), ordner)
    assert len(graph.waypoints) == 4
    assert dienst.protokoll == ["write:flur.neu"], "geschrieben wird NEBENAN"
    assert [wp.id for wp in map_pb2.Graph.FromString((ordner / "graph").read_bytes()).waypoints] \
        == ["wp0", "wp1", "wp2", "wp3"]
    assert not (ordner.parent / "flur.neu").exists() and not (ordner.parent / "flur.alt").exists()
    assert json.loads((ordner / METADATEN).read_text(encoding="utf-8"))["wegpunkte"] == 4


def test_eine_unlesbare_antwort_laesst_die_gespeicherte_karte_in_ruhe(tmp_path):
    from spotlab.backends.real.graphnav import download_map
    from spotlab.errors import MapError

    ordner = _gespeicherte_karte(tmp_path)
    vorher = (ordner / "graph").read_bytes()
    with pytest.raises(MapError, match="unlesbar|keine Wegpunkte"):
        download_map(_RobotMitDiensten(_GraphNavMitDownload(kaputt=True)), ordner)
    assert (ordner / "graph").read_bytes() == vorher
    assert not (ordner.parent / "flur.neu").exists()


def test_eine_leere_antwort_ebenso(tmp_path):
    from spotlab.backends.real.graphnav import download_map
    from spotlab.errors import MapError

    ordner = _gespeicherte_karte(tmp_path)
    vorher = (ordner / "graph").read_bytes()
    with pytest.raises(MapError, match="keine Wegpunkte"):
        download_map(_RobotMitDiensten(_GraphNavMitDownload(wegpunkte=0)), ordner)
    assert (ordner / "graph").read_bytes() == vorher
