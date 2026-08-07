import pytest
from bosdyn.api.graph_nav import map_pb2, recording_pb2

from spotlab.errors import MapError
from spotlab.maps.session import RecordingSession, RecordingStatus


class FakeRecording:
    def __init__(self, start_status=None, wegpunkt_status=None):
        self.protokoll = []
        self._start_status = (
            recording_pb2.StartRecordingResponse.STATUS_OK
            if start_status is None
            else start_status
        )
        self._wegpunkt_status = (
            recording_pb2.CreateWaypointResponse.STATUS_OK
            if wegpunkt_status is None
            else wegpunkt_status
        )
        self.laeuft = False

    def start_recording_full(self, **kw):
        self.protokoll.append("start")
        antwort = recording_pb2.StartRecordingResponse(status=self._start_status)
        if self._start_status == recording_pb2.StartRecordingResponse.STATUS_OK:
            self.laeuft = True
        return antwort

    def stop_recording(self, **kw):
        self.protokoll.append("stop")
        self.laeuft = False

    def create_waypoint(self, waypoint_name=None, **kw):
        self.protokoll.append(f"waypoint:{waypoint_name}")
        antwort = recording_pb2.CreateWaypointResponse(status=self._wegpunkt_status)
        antwort.created_waypoint.id = "wp-neu"
        return antwort

    def get_record_status(self, **kw):
        antwort = recording_pb2.GetRecordStatusResponse(is_recording=self.laeuft)
        antwort.map_stats.waypoints.count = 7
        antwort.map_stats.edges.count = 6
        return antwort


class FakeGraphNav:
    def __init__(self):
        self.protokoll = []

    def clear_graph(self, **kw):
        self.protokoll.append("clear")

    def download_graph(self, **kw):
        graph = map_pb2.Graph()
        graph.waypoints.add().id = "wp0"
        return graph

    def write_graph_and_snapshots(self, verzeichnis):
        self.protokoll.append(f"write:{verzeichnis}")


def _sitzung(**kw):
    return RecordingSession(
        robot=object(), recording_client=FakeRecording(**kw), graph_client=FakeGraphNav()
    )


def test_start_stop_reihenfolge():
    sitzung = _sitzung()
    sitzung.start()
    sitzung.stop()
    assert sitzung._recording.protokoll == ["start", "stop"]


def test_graph_leeren_vor_dem_start():
    sitzung = _sitzung()
    sitzung.start(graph_leeren=True)
    assert sitzung._graph.protokoll == ["clear"]
    assert sitzung._recording.protokoll == ["start"]


def test_ohne_leeren_wird_nichts_geloescht():
    sitzung = _sitzung()
    sitzung.start()
    assert sitzung._graph.protokoll == []


def test_fehlendes_fiducial_wird_zu_klartext():
    sitzung = _sitzung(
        start_status=recording_pb2.StartRecordingResponse.STATUS_MISSING_FIDUCIALS
    )
    with pytest.raises(MapError) as info:
        sitzung.start()
    assert "Fiducial" in str(info.value)


def test_alte_karte_nennt_den_ausweg():
    sitzung = _sitzung(
        start_status=recording_pb2.StartRecordingResponse.STATUS_NOT_LOCALIZED_TO_EXISTING_MAP
    )
    with pytest.raises(MapError) as info:
        sitzung.start()
    assert "leeren" in str(info.value)


def test_wegpunkt_gibt_die_id_zurueck():
    sitzung = _sitzung()
    sitzung.start()
    assert sitzung.waypoint("kueche") == "wp-neu"
    assert "waypoint:kueche" in sitzung._recording.protokoll


def test_wegpunkt_ohne_aufnahme_wird_zu_klartext():
    sitzung = _sitzung(
        wegpunkt_status=recording_pb2.CreateWaypointResponse.STATUS_NOT_RECORDING
    )
    with pytest.raises(MapError) as info:
        sitzung.waypoint("kueche")
    assert "Aufnahme" in str(info.value)


def test_status_kommt_aus_map_stats():
    sitzung = _sitzung()
    sitzung.start()
    zustand = sitzung.status()
    assert isinstance(zustand, RecordingStatus)
    assert zustand.laeuft is True
    assert zustand.wegpunkte == 7 and zustand.kanten == 6


def test_status_vor_dem_start():
    assert _sitzung().status().laeuft is False


def test_download_schreibt_und_legt_metadaten_an(tmp_path):
    sitzung = _sitzung()
    ziel = sitzung.download(tmp_path, name="turnhalle", roboter="SN-1")
    assert f"write:{ziel}" in sitzung._graph.protokoll
    assert (ziel / "karte.json").exists()


def test_session_ist_leaselos():
    """Grundsatzentscheidung N2: maps/ nimmt keine Kontrolle an sich."""
    import pathlib

    import spotlab.maps.session as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    assert "LeaseClient" not in quelle
    assert "EstopClient" not in quelle
    assert "EstopEndpoint" not in quelle


def test_kein_lease_im_ganzen_maps_paket():
    """Die Regel gilt fürs Paket, nicht nur für diese Datei."""
    import pathlib

    import spotlab.maps

    wurzel = pathlib.Path(spotlab.maps.__file__).parent
    for pfad in wurzel.rglob("*.py"):
        quelle = pfad.read_text(encoding="utf-8")
        assert "LeaseClient" not in quelle, pfad
        assert "EstopClient" not in quelle, pfad
