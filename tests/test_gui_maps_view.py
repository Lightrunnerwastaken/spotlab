import pytest

pytest.importorskip("PySide6.QtWidgets")

from bosdyn.api.graph_nav import map_pb2  # noqa: E402

from spotlab.gui.views.maps import MapsView  # noqa: E402
from spotlab.maps.store import karten_wurzel, speichere_metadaten  # noqa: E402


def _graph():
    graph = map_pb2.Graph()
    for kennung, name in (("wp0", "start"), ("wp1", "kueche")):
        wp = graph.waypoints.add()
        wp.id = kennung
        wp.annotations.name = name
    kante = graph.edges.add()
    kante.id.from_waypoint = "wp0"
    kante.id.to_waypoint = "wp1"
    for kennung, x in (("wp0", 0.0), ("wp1", 2.0)):
        anker = graph.anchoring.anchors.add()
        anker.id = kennung
        anker.seed_tform_waypoint.rotation.w = 1.0
        anker.seed_tform_waypoint.position.x = x
    return graph


def _karte(tmp_path, name="turnhalle"):
    ordner = karten_wurzel(tmp_path) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph().SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph())
    return ordner


def test_liste_zeigt_die_karten(qapp, tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 1
    assert "turnhalle" in ansicht.liste.item(0).text()


def test_ohne_karten_bleibt_die_liste_leer(qapp, tmp_path):
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 0


def test_auswahl_zeichnet_die_draufsicht(qapp, tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.liste.setCurrentRow(0)
    assert len(ansicht.plot.grundriss.punkte) == 2
    assert ansicht.plot.grundriss.quelle == "anker"


def test_als_aktiv_setzen_meldet_den_namen(qapp, tmp_path):
    _karte(tmp_path)
    gewaehlt = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.aktive_karte_gewaehlt.connect(gewaehlt.append)
    ansicht.liste.setCurrentRow(0)
    ansicht.aktiv_knopf.click()
    assert gewaehlt == ["turnhalle"]


def test_als_aktiv_ohne_auswahl_tut_nichts(qapp, tmp_path):
    gewaehlt = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.aktive_karte_gewaehlt.connect(gewaehlt.append)
    ansicht.aktiv_knopf.click()
    assert gewaehlt == []


def test_aufnahme_ohne_konfiguration_meldet_klartext(qapp, tmp_path):
    meldungen = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.meldung.connect(meldungen.append)
    ansicht.start_knopf.click()
    assert meldungen and "eingerichtet" in meldungen[0].lower()


def test_hinweis_auf_tablet_und_fiducial_steht_da(qapp):
    ansicht = MapsView()
    text = ansicht.hinweis.text().lower()
    assert "fiducial" in text
    assert "tablet" in text


def test_status_fuellt_die_anzeige(qapp, tmp_path):
    from spotlab.maps.session import RecordingStatus

    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht._zeige_status(RecordingStatus(True, 12, 11, "Aufnahme läuft"))
    assert "12" in ansicht.aufnahme_status.text()


def test_die_kartenansicht_reicht_die_palette_durch(qapp):
    """S2.13: auf der Windows-Vorgabe `hell` sind die Wegpunktnamen sonst
    praktisch unlesbar -- Kontrast rund 1.3:1 auf der Mehrheit der Schullaptops."""
    from spotlab.gui.theme import HELL
    from spotlab.gui.views.maps import MapsView

    ansicht = MapsView(HELL)
    assert ansicht.plot.palette_ is HELL


def test_das_fenster_gibt_beiden_diagrammen_seine_palette(qapp):
    from spotlab.gui.app import MainWindow

    fenster = MainWindow()
    assert fenster.ansichten["karten"].plot.palette_ is fenster._palette
    assert fenster.ansichten["laeufe"].kurve.palette_ is fenster._palette


# ----------------------------------------------------------- Navigation


def _mit_karte(tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.liste.setCurrentRow(0)
    return ansicht


def test_ein_klick_ohne_lauf_waehlt_nur(qapp, tmp_path):
    from spotlab.record import navigation

    ansicht = _mit_karte(tmp_path)
    assert ansicht.karte_fuer_navigation() == "turnhalle" and not ansicht.laeuft()
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    assert ansicht.plot.ziel == "wp1"
    assert "kueche" in ansicht.navigation_status.text() and "gewählt" in ansicht.navigation_status.text()
    assert not list(tmp_path.rglob(navigation.ZIEL_DATEI))


def test_im_lauf_schreibt_der_klick_das_ziel(qapp, tmp_path):
    from spotlab.record import navigation

    ansicht = _mit_karte(tmp_path)
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    ansicht.lauf_beginnt(lauf, "navigieren.py")
    assert ansicht.laeuft() and not ansicht.liste.isEnabled()
    assert "beenden" in ansicht.navigation_knopf.text() and ansicht.navigation_stopp.isEnabled()
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    assert navigation.lies_ziel(lauf) == ("wp1", 1)
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    assert navigation.lies_ziel(lauf) == ("wp1", 2), "noch einmal geklickt heisst noch einmal fahren"
    ansicht.lauf_beendet()
    assert not ansicht.laeuft() and ansicht.liste.isEnabled() and ansicht.plot.ziel is None
    assert "fahren" in ansicht.navigation_knopf.text() and not ansicht.navigation_stopp.isEnabled()


def test_der_stand_kommt_in_zeile_und_zeichnung(qapp, tmp_path):
    ansicht = _mit_karte(tmp_path)
    ansicht.lauf_beginnt(tmp_path, "navigieren.py")
    ansicht.zeige_navigation({"status": "verorte", "text": "kein Tag im Bild", "karte": "turnhalle",
                              "ziel": None, "standort": None, "versatz": None})
    assert "AprilTag" in ansicht.navigation_status.text() and "kein Tag" in ansicht.navigation_status.text()
    ansicht.zeige_navigation({"status": "bereit", "text": "", "karte": "turnhalle", "ziel": None,
                              "standort": "wp0", "versatz": [1.0, 0.0, 0.0]})
    assert "start" in ansicht.navigation_status.text()
    assert ansicht.plot.standort == "wp0"
    x, y, grad = ansicht.plot.roboter
    assert abs(x - 1.0) < 1e-9 and abs(y) < 1e-9 and grad == 0.0
    ansicht.zeige_navigation({"status": "unterwegs", "text": "", "karte": "turnhalle", "ziel": "wp1",
                              "standort": "wp0", "versatz": [1.5, 0.0, 0.0]})
    assert ansicht.plot.ziel == "wp1" and "kueche" in ansicht.navigation_status.text()
    ansicht.zeige_navigation({"status": "angekommen", "text": "", "karte": "turnhalle", "ziel": "wp1",
                              "standort": "wp1", "versatz": [0.0, 0.0, 0.0]})
    assert ansicht.plot.ziel is None and ansicht.plot.standort == "wp1"
    ansicht.zeige_navigation({"status": "gescheitert", "text": "verloren", "karte": "andere",
                              "ziel": "wp1", "standort": None, "versatz": None})
    text = ansicht.navigation_status.text()
    assert "verloren" in text and "andere" in text, "eine fremde Karte im Lauf wird gesagt"
    assert ansicht.plot.roboter is None


# ------------------------------------------------------------- Benennen


def test_ein_gewaehlter_wegpunkt_laesst_sich_benennen(qapp, tmp_path, monkeypatch):
    from spotlab.gui.views import maps as maps_modul
    from spotlab.maps.store import lade_graph, wegpunkt_name

    ansicht = _mit_karte(tmp_path)
    assert not ansicht.benennen_knopf.isEnabled()
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    assert ansicht.benennen_knopf.isEnabled() and "benennen" in ansicht.navigation_status.text()
    gefragt = []
    monkeypatch.setattr(maps_modul.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (gefragt.append(k.get("text")), ("Fenster", True))[1]))
    ansicht.benennen_knopf.click()
    assert gefragt == ["kueche"], "der bisherige Name steht im Dialog"
    assert wegpunkt_name(lade_graph(_karte_ordner(tmp_path)), "wp1") == "Fenster"
    assert {p.id: p.name for p in ansicht.plot.grundriss.punkte}["wp1"] == "Fenster", "neu gezeichnet"
    assert ansicht.plot.ziel == "wp1" and "Fenster" in ansicht.navigation_status.text()


def test_doppelklick_benennt_und_abbrechen_aendert_nichts(qapp, tmp_path, monkeypatch):
    from spotlab.gui.views import maps as maps_modul
    from spotlab.maps.store import lade_graph, wegpunkt_name

    ansicht = _mit_karte(tmp_path)
    monkeypatch.setattr(maps_modul.QInputDialog, "getText", staticmethod(lambda *a, **k: ("egal", False)))
    ansicht.plot.wegpunkt_doppelt.emit("wp0")
    assert wegpunkt_name(lade_graph(_karte_ordner(tmp_path)), "wp0") == "start"
    assert ansicht.plot.ziel == "wp0" and ansicht.benennen_knopf.isEnabled()


def test_ein_doppelter_name_wird_gemeldet_nicht_geschrieben(qapp, tmp_path, monkeypatch):
    from spotlab.gui.views import maps as maps_modul
    from spotlab.maps.store import lade_graph, wegpunkt_name

    ansicht = _mit_karte(tmp_path)
    meldungen = []
    ansicht.meldung.connect(meldungen.append)
    monkeypatch.setattr(maps_modul.QInputDialog, "getText", staticmethod(lambda *a, **k: ("start", True)))
    ansicht.plot.wegpunkt_doppelt.emit("wp1")
    assert meldungen and "anderer Wegpunkt" in meldungen[0]
    assert wegpunkt_name(lade_graph(_karte_ordner(tmp_path)), "wp1") == "kueche"


def test_waehrend_der_navigation_wird_nicht_umbenannt(qapp, tmp_path, monkeypatch):
    from spotlab.gui.views import maps as maps_modul

    ansicht = _mit_karte(tmp_path)
    ansicht.lauf_beginnt(tmp_path, "navigieren.py")
    gefragt = []
    monkeypatch.setattr(maps_modul.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (gefragt.append(1), ("x", True))[1]))
    ansicht.plot.wegpunkt_doppelt.emit("wp1")
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    assert gefragt == [] and not ansicht.benennen_knopf.isEnabled()


def _karte_ordner(tmp_path):
    return karten_wurzel(tmp_path) / "turnhalle"


# ------------------------------------------------ Auswahl nach einem Lauf (p14)


def test_nach_einem_lauf_bleibt_die_auswahl(qapp, tmp_path, monkeypatch):
    """Befund p14 (22.09.2026): `app.py::_lauf_beendet` ruft nach JEDEM Lauf `aktualisiere()`,
    und das leerte die Liste. Die Zeichnung blieb stehen, „Wegpunkt benennen" war aktiv und
    tat still nichts, „Zu Wegpunkten fahren" sagte „Waehle zuerst eine Karte"."""
    from spotlab.gui.views import maps as maps_modul

    ansicht = _mit_karte(tmp_path)
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    ansicht.aktualisiere()
    assert ansicht.karte_fuer_navigation() == "turnhalle"
    assert len(ansicht.plot.grundriss.punkte) == 2
    assert ansicht.plot.ziel == "wp1" and ansicht.benennen_knopf.isEnabled()
    gefragt = []
    monkeypatch.setattr(maps_modul.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (gefragt.append(1), ("", False))[1]))
    ansicht.benennen_knopf.click()
    assert gefragt == [1], "der Knopf tut, was er verspricht"


def test_die_auswahl_folgt_dem_namen_nicht_der_zeile(qapp, tmp_path):
    """Die Liste ist nach Aenderungszeit sortiert -- nach „Karte verbessern" rutscht eine
    Karte nach oben, und die Zeile von vorher waere eine andere Karte."""
    import os

    _karte(tmp_path, "flur")
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    zeile = next(i for i in range(ansicht.liste.count()) if "turnhalle" in ansicht.liste.item(i).text())
    ansicht.liste.setCurrentRow(zeile)
    flur = karten_wurzel(tmp_path) / "flur"
    spaeter = max(p.stat().st_mtime for p in karten_wurzel(tmp_path).iterdir()) + 100
    os.utime(flur, (spaeter, spaeter))
    ansicht.aktualisiere()
    assert ansicht.karte_fuer_navigation() == "turnhalle"
    assert "turnhalle" in ansicht.liste.currentItem().text()


def test_nach_dem_lauf_zeigt_die_zeichnung_den_neuen_stand(qapp, tmp_path):
    """Nach einer Kartenarbeit liegt eine andere Karte auf der Platte -- dafuer ruft die App
    `aktualisiere()` ueberhaupt."""
    from spotlab.maps.store import benenne_wegpunkt

    ansicht = _mit_karte(tmp_path)
    benenne_wegpunkt(_karte_ordner(tmp_path), "wp1", "Fenster")
    ansicht.aktualisiere()
    assert {p.id: p.name for p in ansicht.plot.grundriss.punkte}["wp1"] == "Fenster"


def test_eine_verschwundene_karte_wird_auch_nicht_mehr_gezeichnet(qapp, tmp_path):
    import shutil

    ansicht = _mit_karte(tmp_path)
    ansicht.plot.wegpunkt_geklickt.emit("wp1")
    shutil.rmtree(_karte_ordner(tmp_path))
    ansicht.aktualisiere()
    assert ansicht.karte_fuer_navigation() is None
    assert ansicht.plot.grundriss.punkte == [] and ansicht.plot.ziel is None
    assert not ansicht.benennen_knopf.isEnabled()


def test_nach_einem_fehlgeschlagenen_verbinden_ist_der_reiter_wieder_benutzbar(qapp, tmp_path):
    """Befund 22.09.2026: `_aufnahme_fehler` meldete nur und setzte nichts zurueck.
    Der Knopf blieb fuer immer grau, und ein zweiter Versuch antwortete 'Es laeuft
    bereits eine Aufnahme' -- eine Ursache, die es nicht gab. Nur ein Neustart half.
    Das trifft jeden ohne Roboter beim ersten Klick."""
    from spotlab.config import Config, Limits

    ansicht = MapsView()
    ansicht.setze_arbeitsordner(str(tmp_path))
    ansicht.setze_config(Config(ip="10.0.0.9", username="u", limits=Limits()))
    meldungen = []
    ansicht.meldung.connect(meldungen.append)

    class _Gescheitert:
        """Ein Arbeiter, der gar nicht erst verbindet."""

        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

        def schliesse(self):
            pass

        def wait(self, _ms=0):
            return True

        status = fehler = abgebrochen = gespeichert = bereit = property(lambda self: None)

    ansicht._worker = _Gescheitert()
    ansicht.start_knopf.setEnabled(False)
    ansicht._aufnahme_fehler("Ich erreiche 10.0.0.9 nicht.")

    assert meldungen and "10.0.0.9" in meldungen[0]
    assert ansicht.start_knopf.isEnabled(), "der Reiter muss einen zweiten Versuch zulassen"
    assert ansicht._worker is None


# ------------------------------------------------ Aufnahme mit echtem Arbeiter (p04, p05)


class _Sitzung:
    """Die Robotersitzung der Aufnahme -- Attrappe, kein Netz. Der erste Wegpunkt scheitert."""

    def __init__(self, start_scheitert=False):
        from spotlab.errors import MapError

        self.fehler = MapError
        self.robot_zeichnet = False
        self.aufrufe = []
        self.start_scheitert = start_scheitert

    def start(self, graph_leeren=False):
        self.aufrufe.append("start")
        if self.start_scheitert:
            self.start_scheitert = False
            raise self.fehler("Kein Fiducial im Bild -- die Aufnahme laesst sich nicht starten.")
        self.robot_zeichnet = True

    def waypoint(self, name):
        self.aufrufe.append(f"waypoint:{name}")
        if self.aufrufe.count("waypoint:kueche") == 1 and name == "kueche":
            raise self.fehler("Der Wegpunkt liess sich nicht setzen (Zeitueberschreitung).")
        return "wp-neu"

    def stop(self):
        self.aufrufe.append("stop")
        self.robot_zeichnet = False

    def nachbearbeiten(self, melde=None):
        self.aufrufe.append("nachbearbeiten")

    def download(self, wurzel, name, roboter=None):
        self.aufrufe.append(f"download:{name}")
        return wurzel / name

    def status(self):
        from spotlab.maps.session import RecordingStatus

        return RecordingStatus(self.robot_zeichnet, 3, 2,
                               "Aufnahme läuft" if self.robot_zeichnet else "Keine Aufnahme")

    def close(self):
        self.aufrufe.append("close")


def _aufnahme(tmp_path, monkeypatch, verbinde, namen=("kueche",)):
    from spotlab.config import Config, Limits
    from spotlab.gui.views import maps as maps_modul
    from spotlab.maps import session as sessionmodul

    monkeypatch.setattr(sessionmodul.RecordingSession, "connect", classmethod(verbinde))
    antworten = iter(namen)
    monkeypatch.setattr(maps_modul.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (next(antworten, "x"), True)))
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(str(tmp_path))
    ansicht.setze_config(Config(ip="10.0.0.9", username="u", limits=Limits()))
    meldungen = []
    ansicht.meldung.connect(meldungen.append)
    return ansicht, meldungen


def _bis(qapp, bedingung, worauf):
    from tests_zeitgrenzen import warte_bis

    warte_bis(bedingung, worauf, zwischendurch=qapp.processEvents)


def _abraeumen(qapp, arbeiter):
    """Den Faden sicher beenden, bevor der Test endet -- ein Leck faellt nie dort auf, wo es entsteht."""
    from PySide6.QtCore import QCoreApplication, QEvent

    from tests_zeitgrenzen import TEST_TIMEOUT_S

    if arbeiter is not None:
        arbeiter.schliesse()
        assert arbeiter.wait(TEST_TIMEOUT_S * 1000)
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_ein_gescheiterter_wegpunkt_beendet_die_aufnahme_nicht(qapp, tmp_path, monkeypatch):
    """Befund p04 (22.09.2026): ein einzelner Fehlschlag beim Wegpunkt schloss den Arbeiter,
    die Anzeige sagte „Nicht aufgenommen.", „Beenden und speichern" war grau -- und der
    Roboter zeichnete weiter auf, denn ein Stopp ging nie hinaus."""
    sitzung = _Sitzung()
    ansicht, meldungen = _aufnahme(tmp_path, monkeypatch, lambda cls, cfg, verbinder=None: sitzung,
                                   namen=("kueche", "turnhalle"))
    arbeiter = None
    try:
        ansicht.start_knopf.click()
        arbeiter = ansicht._worker
        _bis(qapp, lambda: sitzung.robot_zeichnet, "die Aufnahme laeuft")
        ansicht.wegpunkt_knopf.click()
        _bis(qapp, lambda: any("Wegpunkt" in m for m in meldungen), "der Fehler ist gemeldet")
        assert ansicht._worker is arbeiter and arbeiter.isRunning(), "der Arbeiter lebt weiter"
        assert ansicht.speichern_knopf.isEnabled() and ansicht.wegpunkt_knopf.isEnabled()
        assert "close" not in sitzung.aufrufe
        ansicht.speichern_knopf.click()
        _bis(qapp, lambda: any("gespeichert" in m for m in meldungen), "die Karte ist gespeichert")
        assert sitzung.aufrufe[-4:] == ["stop", "nachbearbeiten", "download:turnhalle", "close"]
        assert ansicht._worker is None and ansicht.start_knopf.isEnabled()
    finally:
        _abraeumen(qapp, arbeiter)
    assert "stop" in sitzung.aufrufe, "die Aufnahme am Roboter ist beendet"


def test_ein_gescheiterter_start_laesst_sich_ohne_neues_verbinden_wiederholen(
        qapp, tmp_path, monkeypatch):
    """Scheitert der Start (kein Fiducial im Bild), steht die Verbindung trotzdem: derselbe
    Knopf versucht es noch einmal -- vorher hiess es „Es laeuft bereits eine Aufnahme"."""
    sitzung = _Sitzung(start_scheitert=True)
    verbunden = []

    def verbinde(cls, cfg, verbinder=None):
        verbunden.append(1)
        return sitzung

    ansicht, meldungen = _aufnahme(tmp_path, monkeypatch, verbinde)
    arbeiter = None
    try:
        ansicht.start_knopf.click()
        arbeiter = ansicht._worker
        _bis(qapp, lambda: any("Fiducial" in m for m in meldungen), "der Fehlstart ist gemeldet")
        assert ansicht._worker is arbeiter and ansicht.start_knopf.isEnabled()
        ansicht.start_knopf.click()
        _bis(qapp, lambda: sitzung.robot_zeichnet, "der zweite Start laeuft")
        assert verbunden == [1], "kein zweites Verbinden"
        assert not any("bereits" in m for m in meldungen), meldungen
        assert not ansicht.start_knopf.isEnabled()
    finally:
        _abraeumen(qapp, arbeiter)


def test_schliessen_waehrend_des_verbindens_vergisst_den_arbeiter_nicht(
        qapp, tmp_path, monkeypatch):
    """Befund p05 (22.09.2026): `_beende_worker` wartete 3 s und vergass den Arbeiter dann,
    auch wenn er noch lief. Das Widget wurde zerstoert, der QThread darunter mit -- Qt
    brach den Prozess ab („QThread: Destroyed while thread is still running"), samt
    NOT-AUS-Knopf. Jetzt: die Rueckgabe sagt, dass er noch laeuft, und der Arbeiter
    ueberlebt das Widget, bis er fertig ist."""
    import threading

    import shiboken6

    from spotlab.gui.views import maps as maps_modul
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    los = threading.Event()

    def haengt(cls, cfg, verbinder=None):
        los.wait(TEST_TIMEOUT_S)
        raise RuntimeError("Zeitueberschreitung beim Verbinden")

    ansicht, _ = _aufnahme(tmp_path, monkeypatch, haengt)
    ansicht.start_knopf.click()
    arbeiter = ansicht._worker
    try:
        _bis(qapp, arbeiter.isRunning, "der Arbeiter verbindet")
        assert ansicht._beende_worker(warte_ms=20) is True, "er laeuft noch -- und das wird gesagt"
        assert ansicht._worker is None and ansicht.start_knopf.isEnabled()
        assert arbeiter.parent() is None, "vom Widget geloest"
        assert maps_modul.aufnahme_laeuft_noch()
        shiboken6.delete(ansicht)          # was beim Beenden passiert -- kein Absturz
    finally:
        los.set()
        assert arbeiter.wait(TEST_TIMEOUT_S * 1000)
    _abraeumen(qapp, None)
    assert not maps_modul.aufnahme_laeuft_noch()


def test_ein_arbeiter_der_rechtzeitig_endet_meldet_nichts_laufendes(qapp, tmp_path, monkeypatch):
    sitzung = _Sitzung()
    ansicht, _ = _aufnahme(tmp_path, monkeypatch, lambda cls, cfg, verbinder=None: sitzung)
    ansicht.start_knopf.click()
    arbeiter = ansicht._worker
    try:
        _bis(qapp, lambda: sitzung.robot_zeichnet, "die Aufnahme laeuft")
        assert ansicht._beende_worker() is False
        assert not arbeiter.isRunning() and sitzung.aufrufe[-1] == "close"
    finally:
        _abraeumen(qapp, arbeiter if arbeiter.isRunning() else None)
