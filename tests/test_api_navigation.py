import json

import pytest
from bosdyn.api.graph_nav import map_pb2

from spotlab.api.navigation import Map, load_map, localize, navigate_to
from spotlab.backends.base import Capability, NavStatus
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits
from spotlab.errors import NavigationError, SpotlabError, UnsupportedCapability
from spotlab.maps.store import karten_wurzel, speichere_metadaten


def _graph():
    graph = map_pb2.Graph()
    for kennung, name in (("wp0", "start"), ("wp1", "kueche")):
        wp = graph.waypoints.add()
        wp.id = kennung
        wp.annotations.name = name
    kante = graph.edges.add()
    kante.id.from_waypoint = "wp0"
    kante.id.to_waypoint = "wp1"
    return graph


def _karte_auf_platte(tmp_path, name="turnhalle"):
    ordner = karten_wurzel(tmp_path) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph().SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph())
    return ordner


class FakeBackend(DryRunBackend):
    """Trockenlauf plus GraphNav — das Attrappen-Gegenstück zu RealSpot."""

    def __init__(self, folge=None):
        super().__init__()
        self.power_on()
        self.protokoll = []
        self.letzte_params = None
        self._folge = list(folge or [])

    def capabilities(self):
        return super().capabilities() | Capability.GRAPH_NAV

    def upload_map(self, kartenordner):
        self.protokoll.append(f"upload:{kartenordner.name}")
        return _graph()

    def localize(self):
        self.protokoll.append("localize")
        return "wp0"

    def travel_params(self, limits):
        self.letzte_params = limits
        return f"params({limits.max_speed})"

    def navigate_step(self, waypoint_id, dauer_s, params, command_id=None):
        self.protokoll.append(f"nav:{waypoint_id}")
        return 7

    def navigation_status(self, command_id):
        if self._folge:
            return self._folge.pop(0)
        return NavStatus(fertig=True, status="Angekommen.", gescheitert=False)


def test_karte_wird_geladen_und_beschrieben(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = FakeBackend()
    karte = load_map(backend, None, tmp_path, "turnhalle")
    assert isinstance(karte, Map)
    assert karte.name == "turnhalle"
    assert sorted(karte.waypoints) == ["kueche", "start"]
    assert "upload:turnhalle" in backend.protokoll


def test_ohne_argument_wird_die_aktive_karte_genommen(tmp_path):
    _karte_auf_platte(tmp_path, "aula")
    karte = load_map(FakeBackend(), None, tmp_path, None, active="aula")
    assert karte.name == "aula"


def test_ohne_argument_und_ohne_aktive_karte_klarer_fehler(tmp_path):
    _karte_auf_platte(tmp_path, "aula")
    with pytest.raises(SpotlabError) as info:
        load_map(FakeBackend(), None, tmp_path, None, active="")
    assert "aula" in str(info.value)


def test_ohne_arbeitsordner_klarer_fehler():
    with pytest.raises(SpotlabError) as info:
        load_map(FakeBackend(), None, None, "turnhalle")
    assert "Arbeitsordner" in str(info.value)


def test_namen_werden_zu_wegpunkt_ids(tmp_path):
    _karte_auf_platte(tmp_path)
    karte = load_map(FakeBackend(), None, tmp_path, "turnhalle")
    assert karte.id_fuer("kueche") == "wp1"


def test_unbekannter_wegpunkt_zaehlt_die_vorhandenen_auf(tmp_path):
    _karte_auf_platte(tmp_path)
    karte = load_map(FakeBackend(), None, tmp_path, "turnhalle")
    with pytest.raises(SpotlabError) as info:
        karte.id_fuer("keller")
    assert "start" in str(info.value) and "kueche" in str(info.value)


def test_lokalisieren_reicht_durch():
    backend = FakeBackend()
    assert localize(backend, None) == "wp0"
    assert "localize" in backend.protokoll


def test_fahrt_erreicht_das_ziel(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = FakeBackend()
    karte = load_map(backend, None, tmp_path, "turnhalle")
    navigate_to(backend, None, karte, "kueche", Limits(),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert "nav:wp1" in backend.protokoll


def test_der_geschwindigkeitsdeckel_landet_in_den_params(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = FakeBackend()
    karte = load_map(backend, None, tmp_path, "turnhalle")
    navigate_to(backend, None, karte, "kueche", Limits(max_speed=0.25),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert backend.letzte_params.max_speed == 0.25


def test_kommando_wird_nachgesendet(tmp_path):
    """Navigationskommandos verfallen — wie Geschwindigkeitskommandos."""
    _karte_auf_platte(tmp_path)
    unterwegs = NavStatus(fertig=False, status="Unterwegs.", gescheitert=False)
    backend = FakeBackend(folge=[unterwegs, unterwegs])
    karte = load_map(backend, None, tmp_path, "turnhalle")
    navigate_to(backend, None, karte, "kueche", Limits(),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert backend.protokoll.count("nav:wp1") >= 3


def test_verloren_bricht_mit_klartext_ab(tmp_path):
    _karte_auf_platte(tmp_path)
    verloren = NavStatus(fertig=False, status="Der Spot hat sich verloren.",
                         gescheitert=True)
    backend = FakeBackend(folge=[verloren])
    karte = load_map(backend, None, tmp_path, "turnhalle")
    with pytest.raises(NavigationError) as info:
        navigate_to(backend, None, karte, "kueche", Limits(),
                    schlaf=lambda _: None, jetzt=lambda: 0.0)
    assert "verloren" in str(info.value)


def test_zeitueberschreitung_meldet_klartext(tmp_path):
    _karte_auf_platte(tmp_path)
    unterwegs = NavStatus(fertig=False, status="Unterwegs.", gescheitert=False)
    backend = FakeBackend(folge=[unterwegs] * 50)
    karte = load_map(backend, None, tmp_path, "turnhalle")
    uhr = iter([0.0, 0.0, 5.0, 500.0, 900.0])
    with pytest.raises(NavigationError) as info:
        navigate_to(backend, None, karte, "kueche", Limits(), timeout=10.0,
                    schlaf=lambda _: None, jetzt=lambda: next(uhr))
    assert "10" in str(info.value)


def test_ohne_graph_nav_klare_verweigerung(tmp_path):
    _karte_auf_platte(tmp_path)
    backend = DryRunBackend()
    backend.power_on()
    with pytest.raises(UnsupportedCapability):
        load_map(backend, None, tmp_path, "turnhalle")


def test_ereignisse_werden_aufgezeichnet(tmp_path):
    from spotlab.record.run import RunRecorder

    _karte_auf_platte(tmp_path)
    rec = RunRecorder(tmp_path / "runs", None, backend="test")
    backend = FakeBackend()
    karte = load_map(backend, rec, tmp_path, "turnhalle")
    navigate_to(backend, rec, karte, "kueche", Limits(),
                schlaf=lambda _: None, jetzt=lambda: 0.0)
    rec.finish("ok")
    text = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert "load_map" in text and "navigate_to" in text


def test_abbruch_haelt_an_und_meldet_nicht_angekommen(tmp_path):
    """Der Karten-Tab wechselt das Ziel waehrend der Fahrt: `abbruch()` wird je
    Takt gefragt, sagt es ja, haelt Spot an und die Fahrt gilt nicht als Ankunft."""
    unterwegs = NavStatus(fertig=False, status="Unterwegs.", gescheitert=False)
    backend = FakeBackend(folge=[unterwegs] * 5)
    karte = Map("turnhalle", _karte_auf_platte(tmp_path), _graph())
    fragen = []

    def abbruch():
        fragen.append(1)
        return len(fragen) >= 2

    angekommen = navigate_to(backend, None, karte, "kueche", Limits(),
                             schlaf=lambda _s: None, abbruch=abbruch)
    assert angekommen is False and len(fragen) == 2
    assert backend.protokoll.count("nav:wp1") == 2, "nach dem Abbruch wird nicht nachgesendet"


def test_ohne_abbruch_gilt_die_ankunft(tmp_path):
    backend = FakeBackend()
    karte = Map("turnhalle", _karte_auf_platte(tmp_path), _graph())
    assert navigate_to(backend, None, karte, "kueche", Limits(), schlaf=lambda _s: None) is True


# ============ Eine gespeicherte Karte nachtraeglich nachbearbeiten


class _BackendMitNachbearbeitung(FakeBackend):
    def __init__(self, bericht=None, **kw):
        super().__init__(**kw)
        from spotlab.maps.nachbearbeitung import Nachbearbeitung

        self.bericht = bericht if bericht is not None else Nachbearbeitung(2, 5, ("gemacht",))
        self.heruntergeladen = []

    def process_map(self, melde=None, fiducial=True, odometrie=True):
        self.protokoll.append(f"process:{fiducial}:{odometrie}")
        if melde is not None:
            for text in self.bericht.meldungen:
                melde(text)
        return self.bericht

    def download_map(self, kartenordner):
        from bosdyn.api.graph_nav import map_pb2

        self.heruntergeladen.append(kartenordner)
        graph = map_pb2.Graph()
        graph.waypoints.add().id = "wp0"
        return graph


def test_eine_karte_wird_nachbearbeitet_und_zurueckgeschrieben(tmp_path):
    from spotlab.api.navigation import process_map

    backend = _BackendMitNachbearbeitung()
    karte = Map("turnhalle", _karte_auf_platte(tmp_path), _graph())
    gemeldet = []
    bericht = process_map(backend, None, karte, melde=gemeldet.append)
    assert bericht.neue_kanten == 2
    assert "process:True:True" in backend.protokoll
    assert backend.heruntergeladen == [karte.dir]
    assert "gemacht" in gemeldet and any("gespeichert" in m for m in gemeldet)


def test_ohne_ergebnis_wird_die_gespeicherte_karte_nicht_angefasst(tmp_path):
    """Eine gescheiterte Nachbearbeitung darf die Karte auf der Platte nicht kosten."""
    from spotlab.api.navigation import process_map
    from spotlab.maps.nachbearbeitung import Nachbearbeitung

    backend = _BackendMitNachbearbeitung(bericht=Nachbearbeitung(None, None, ("nichts",)))
    karte = Map("turnhalle", _karte_auf_platte(tmp_path), _graph())
    assert not process_map(backend, None, karte).gelaufen
    assert backend.heruntergeladen == []


def test_das_nachbearbeiten_steht_in_der_aufzeichnung(tmp_path):
    from spotlab.api.navigation import process_map
    from spotlab.record.run import RunRecorder

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    karte = Map("turnhalle", _karte_auf_platte(tmp_path), _graph())
    process_map(_BackendMitNachbearbeitung(), rec, karte)
    rec.finish("ok")
    zeilen = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    arten = [json.loads(z)["daten"].get("name") for z in zeilen if z.strip()]
    assert arten.count("process_map") == 2, "Kommando und Rueckmeldung"


def test_ohne_graph_nav_wird_gar_nicht_erst_gerechnet(tmp_path):
    from spotlab.api.navigation import process_map

    class _Ohne(_BackendMitNachbearbeitung):
        def capabilities(self):
            return DryRunBackend.capabilities(self)

    backend = _Ohne()
    karte = Map("turnhalle", _karte_auf_platte(tmp_path), _graph())
    with pytest.raises(UnsupportedCapability):
        process_map(backend, None, karte)
    assert not any(e.startswith("process:") for e in backend.protokoll)
