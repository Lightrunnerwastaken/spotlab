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


# ================== Nachbearbeitung: Schleifen schliessen, Anker optimieren
#
# Der Aufzeichnungsdienst legt Wegpunkte in einer KETTE an. Ohne diesen Schritt
# gibt es zwischen zwei Punkten immer nur den einen aufgezeichneten Weg, und die
# Anker stehen so da, wie die Odometrie sie sah -- eine Runde durch das
# Schulhaus schliesst sich sichtbar nicht.


class FakeProcessing:
    def __init__(self, neue_kanten=3, schritte=42, abgelaufen=False, fehler=None):
        from bosdyn.api.graph_nav import map_processing_pb2

        self.protokoll = []
        self.topologie_params = None
        self.anker_args = None
        self._mp = map_processing_pb2
        self._neue_kanten = neue_kanten
        self._schritte = schritte
        self._abgelaufen = abgelaufen
        self._fehler = fehler or {}

    def process_topology(self, params=None, modify_map_on_server=None, timeout=None):
        self.protokoll.append(f"topology:{modify_map_on_server}:{timeout}")
        self.topologie_params = params
        if "topology" in self._fehler:
            raise self._fehler["topology"]
        antwort = self._mp.ProcessTopologyResponse(timed_out=self._abgelaufen)
        for i in range(self._neue_kanten):
            kante = antwort.new_subgraph.edges.add()
            kante.id.from_waypoint, kante.id.to_waypoint = f"wp{i}", f"wp{i + 5}"
        return antwort

    def process_anchoring(self, params=None, modify_anchoring_on_server=None,
                          stream_intermediate_results=None, timeout=None):
        self.protokoll.append(f"anchoring:{modify_anchoring_on_server}:{timeout}")
        self.anker_args = (stream_intermediate_results,)
        if "anchoring" in self._fehler:
            raise self._fehler["anchoring"]
        return self._mp.ProcessAnchoringResponse(iteration=self._schritte)


def _sitzung_mit_prozessor(**kw):
    prozessor = FakeProcessing(**kw)
    sitzung = RecordingSession(
        robot=object(), recording_client=FakeRecording(), graph_client=FakeGraphNav(),
        processing_client=prozessor,
    )
    return sitzung, prozessor


def test_schleifen_werden_ueber_fiducials_und_odometrie_geschlossen():
    sitzung, prozessor = _sitzung_mit_prozessor(neue_kanten=3)
    neue_kanten, abgelaufen = sitzung.schliesse_schleifen()
    assert (neue_kanten, abgelaufen) == (3, False)
    assert prozessor.protokoll[0].startswith("topology:True:"), "die Karte auf dem Roboter"
    params = prozessor.topologie_params
    assert params.do_fiducial_loop_closure.value is True
    assert params.do_odometry_loop_closure.value is True
    assert params.timeout_seconds > 0, "der Dienst muss von selbst aufhoeren koennen"


def test_die_schleifensuche_laesst_sich_einschraenken():
    sitzung, prozessor = _sitzung_mit_prozessor()
    sitzung.schliesse_schleifen(fiducial=False, odometrie=True)
    assert prozessor.topologie_params.do_fiducial_loop_closure.value is False
    assert prozessor.topologie_params.do_odometry_loop_closure.value is True


def test_anker_werden_auf_dem_roboter_optimiert():
    sitzung, prozessor = _sitzung_mit_prozessor(schritte=42)
    assert sitzung.optimiere_anker() == 42
    assert prozessor.protokoll[0].startswith("anchoring:True:")
    assert prozessor.anker_args == (False,), "Zwischenergebnisse brauchen wir nicht"


def test_nachbearbeiten_macht_beides_in_dieser_reihenfolge():
    sitzung, prozessor = _sitzung_mit_prozessor(neue_kanten=2, schritte=7)
    gemeldet = []
    bericht = sitzung.nachbearbeiten(melde=gemeldet.append)
    assert [e.split(":")[0] for e in prozessor.protokoll] == ["topology", "anchoring"]
    assert (bericht.neue_kanten, bericht.schritte) == (2, 7) and bericht.gelaufen
    assert gemeldet == list(bericht.meldungen)
    assert "2 neue Verbindungen." in gemeldet
    assert "Anker optimiert (7 Rechenschritte)." in gemeldet


def test_ohne_neue_verbindung_sagt_es_das_auch():
    sitzung, _ = _sitzung_mit_prozessor(neue_kanten=0)
    assert "Keine neue Verbindung gefunden." in sitzung.nachbearbeiten().meldungen


def test_eine_abgelaufene_suche_wird_gesagt():
    sitzung, _ = _sitzung_mit_prozessor(neue_kanten=1, abgelaufen=True)
    bericht = sitzung.nachbearbeiten()
    assert bericht.neue_kanten == 1
    assert any("Frist" in m for m in bericht.meldungen)


def test_eine_gescheiterte_nachbearbeitung_kostet_die_aufnahme_nicht():
    """Wer eine Stunde durch das Schulhaus gefahren ist, bekommt seine Karte --
    notfalls unbearbeitet, aber mit dem Grund in der Meldung."""
    sitzung, prozessor = _sitzung_mit_prozessor(
        fehler={"topology": RuntimeError("Dienst antwortet nicht")}
    )
    bericht = sitzung.nachbearbeiten()                 # wirft nicht
    assert bericht.neue_kanten is None and bericht.schritte == 42
    assert any("Schleifen nicht geschlossen" in m for m in bericht.meldungen)
    assert any(e.startswith("anchoring") for e in prozessor.protokoll), "der Rest laeuft weiter"


def test_auch_die_ankeroptimierung_darf_scheitern():
    sitzung, _ = _sitzung_mit_prozessor(fehler={"anchoring": RuntimeError("zu gross")})
    bericht = sitzung.nachbearbeiten()
    assert bericht.neue_kanten == 3 and bericht.schritte is None
    assert any("Anker nicht optimiert" in m for m in bericht.meldungen)


def test_ohne_den_dienst_wird_es_gesagt_statt_zu_werfen():
    """Aeltere Roboter-Software hat den Dienst nicht -- eine Aufnahme ohne
    Nachbearbeitung ist besser als gar keine."""
    sitzung = _sitzung()                               # ohne processing_client
    bericht = sitzung.nachbearbeiten()
    assert not bericht.gelaufen
    assert any("map-processing-service" in m for m in bericht.meldungen)
    with pytest.raises(MapError, match="map-processing-service"):
        sitzung.schliesse_schleifen()
