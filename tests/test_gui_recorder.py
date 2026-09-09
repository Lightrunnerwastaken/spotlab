import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.errors import MapError  # noqa: E402
from spotlab.gui.recorder import Auftrag, verarbeite  # noqa: E402
from spotlab.maps.session import RecordingStatus  # noqa: E402


class FakeSession:
    def __init__(self, fehler=None):
        self.protokoll = []
        self._fehler = fehler

    def start(self, graph_leeren=False):
        if self._fehler:
            raise self._fehler
        self.protokoll.append(f"start:{graph_leeren}")

    def waypoint(self, name):
        if self._fehler:
            raise self._fehler
        self.protokoll.append(f"waypoint:{name}")
        return "wp-neu"

    def stop(self):
        self.protokoll.append("stop")

    def nachbearbeiten(self, melde=None, fiducial=True, odometrie=True):
        from spotlab.maps.session import Nachbearbeitung

        self.protokoll.append("nachbearbeiten")
        if melde is not None:
            melde("Schleifen werden gesucht…")
        return Nachbearbeitung(2, 7, ("Schleifen werden gesucht…",))

    def download(self, wurzel, name, roboter=None):
        self.protokoll.append(f"download:{name}")
        return wurzel / name

    def status(self):
        return RecordingStatus(True, 3, 2, "Aufnahme läuft")


def test_start_wird_durchgereicht():
    sitzung = FakeSession()
    art, _ = verarbeite(sitzung, Auftrag("start", {"graph_leeren": True}))
    assert art == "status"
    assert sitzung.protokoll == ["start:True"]


def test_wegpunkt_wird_durchgereicht():
    sitzung = FakeSession()
    verarbeite(sitzung, Auftrag("waypoint", {"name": "kueche"}))
    assert sitzung.protokoll == ["waypoint:kueche"]


def test_stoppen_und_speichern(tmp_path):
    sitzung = FakeSession()
    art, nutzlast = verarbeite(
        sitzung, Auftrag("speichern", {"wurzel": tmp_path, "name": "turnhalle"})
    )
    assert art == "gespeichert"
    assert "download:turnhalle" in sitzung.protokoll
    assert str(nutzlast).endswith("turnhalle")


def test_fehler_wird_als_fehler_gemeldet_nicht_geworfen():
    sitzung = FakeSession(fehler=MapError("Kein Fiducial."))
    art, nutzlast = verarbeite(sitzung, Auftrag("start", {"graph_leeren": False}))
    assert art == "fehler"
    assert "Fiducial" in nutzlast


def test_unerwarteter_fehler_wird_ebenfalls_gemeldet():
    sitzung = FakeSession(fehler=RuntimeError("Netz weg"))
    art, nutzlast = verarbeite(sitzung, Auftrag("start", {"graph_leeren": False}))
    assert art == "fehler"
    assert "Netz weg" in nutzlast


def test_unbekannter_auftrag_meldet_das():
    art, nutzlast = verarbeite(FakeSession(), Auftrag("quatsch", {}))
    assert art == "fehler"
    assert "quatsch" in nutzlast


def test_worker_ist_ein_qthread(qapp):
    from PySide6.QtCore import QThread

    from spotlab.gui.recorder import RecordingWorker

    assert issubclass(RecordingWorker, QThread)


# ================== S1.13 Nachbearbeitung vor dem Herunterladen
#
# Ohne Schleifenschluss ist die Aufnahme eine Kette: wer zweimal durch denselben
# Gang faehrt, bekommt zwei Straenge nebeneinander, und Spot faehrt „wie auf
# Schienen" die aufgezeichnete Strecke ab, statt den kurzen Weg zu nehmen.


def test_vor_dem_herunterladen_wird_nachbearbeitet(tmp_path):
    """Die Reihenfolge ist der Punkt: `nachbearbeiten` aendert die Karte AUF DEM
    ROBOTER, und genau die wird danach heruntergeladen."""
    sitzung = FakeSession()
    art, _ = verarbeite(
        sitzung, Auftrag("speichern", {"wurzel": tmp_path, "name": "turnhalle"})
    )
    assert art == "gespeichert"
    assert sitzung.protokoll == ["stop", "nachbearbeiten", "download:turnhalle"]


def test_der_zwischenstand_wird_gemeldet(tmp_path):
    """Die Nachbearbeitung dauert Sekunden; ohne Zeichen saehe es aus, als haenge es."""
    meldungen = []
    verarbeite(
        FakeSession(),
        Auftrag("speichern", {"wurzel": tmp_path, "name": "turnhalle"}),
        melde=meldungen.append,
    )
    assert meldungen == ["Schleifen werden gesucht…"]


def test_die_nachbearbeitung_laesst_sich_abwaehlen(tmp_path):
    sitzung = FakeSession()
    verarbeite(
        sitzung,
        Auftrag("speichern", {"wurzel": tmp_path, "name": "turnhalle",
                              "nachbearbeiten": False}),
    )
    assert sitzung.protokoll == ["stop", "download:turnhalle"]
