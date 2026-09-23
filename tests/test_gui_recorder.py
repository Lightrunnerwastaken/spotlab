import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.errors import MapError  # noqa: E402
from spotlab.gui.recorder import Auftrag, verarbeite  # noqa: E402
from spotlab.maps.session import RecordingStatus  # noqa: E402
from tests_zeitgrenzen import TEST_TIMEOUT_S  # noqa: E402


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


class _Wechselhaft(FakeSession):
    """Eine Sitzung, deren ERSTER Wegpunkt scheitert -- und die mitschreibt, wann sie schliesst."""

    def __init__(self):
        super().__init__()
        self.wegpunkt_gescheitert = False

    def waypoint(self, name):
        if not self.wegpunkt_gescheitert:
            self.wegpunkt_gescheitert = True
            raise MapError("Der Wegpunkt liess sich nicht setzen (Zeitueberschreitung).")
        return super().waypoint(name)

    def close(self):
        self.protokoll.append("close")


def _arbeiter(monkeypatch, verbinde):
    from spotlab.gui.recorder import RecordingWorker
    from spotlab.maps import session as sessionmodul

    monkeypatch.setattr(sessionmodul.RecordingSession, "connect", classmethod(verbinde))
    arbeiter = RecordingWorker(cfg=None)
    gesehen = {"fehler": [], "abgebrochen": [], "bereit": []}
    arbeiter.fehler.connect(lambda art, text: gesehen["fehler"].append((art, text)))
    arbeiter.abgebrochen.connect(gesehen["abgebrochen"].append)
    arbeiter.bereit.connect(lambda: gesehen["bereit"].append(True))
    return arbeiter, gesehen


def test_ein_gescheiterter_auftrag_beendet_den_arbeiter_nicht(qapp, monkeypatch):
    """Befund p04 (22.09.2026): EIN gescheiterter Wegpunkt beendete die ganze Aufnahme im
    Fenster, waehrend der Roboter weiter aufzeichnete -- „Beenden und speichern" war grau,
    und ein Stopp wurde nie geschickt. Nur ein Verbindungsfehler beendet den Arbeiter."""
    from tests_zeitgrenzen import warte_bis

    sitzung = _Wechselhaft()
    arbeiter, gesehen = _arbeiter(monkeypatch, lambda cls, cfg, verbinder=None: sitzung)
    arbeiter.start()
    try:
        arbeiter.starte()
        arbeiter.setze_wegpunkt("kueche")
        arbeiter.setze_wegpunkt("flur")
        warte_bis(lambda: "waypoint:flur" in sitzung.protokoll, "der zweite Wegpunkt kam an",
                  zwischendurch=qapp.processEvents)
        assert arbeiter.isRunning(), "der Arbeiter lebt nach dem Fehlschlag weiter"
        warte_bis(lambda: gesehen["fehler"], "der Fehler wurde gemeldet", zwischendurch=qapp.processEvents)
        assert gesehen["fehler"] == [("waypoint", "Der Wegpunkt liess sich nicht setzen "
                                                  "(Zeitueberschreitung).")]
        assert gesehen["abgebrochen"] == [] and "close" not in sitzung.protokoll
    finally:
        arbeiter.schliesse()
        assert arbeiter.wait(TEST_TIMEOUT_S * 1000)
    assert sitzung.protokoll[-1] == "close"


def test_ein_verbindungsfehler_bricht_ab(qapp, monkeypatch):
    from tests_zeitgrenzen import warte_bis

    def kaputt(cls, cfg, verbinder=None):
        raise RuntimeError("Ich erreiche 10.0.0.9 nicht")

    arbeiter, gesehen = _arbeiter(monkeypatch, kaputt)
    arbeiter.start()
    assert arbeiter.wait(TEST_TIMEOUT_S * 1000), "ohne Verbindung endet der Arbeiter"
    warte_bis(lambda: gesehen["abgebrochen"], "der Abbruch wurde gemeldet",
              zwischendurch=qapp.processEvents)
    assert "10.0.0.9" in gesehen["abgebrochen"][0] and gesehen["fehler"] == []
    assert gesehen["bereit"] == []


def test_die_nachbearbeitung_laesst_sich_abwaehlen(tmp_path):
    sitzung = FakeSession()
    verarbeite(
        sitzung,
        Auftrag("speichern", {"wurzel": tmp_path, "name": "turnhalle",
                              "nachbearbeiten": False}),
    )
    assert sitzung.protokoll == ["stop", "download:turnhalle"]
