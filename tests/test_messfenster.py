import pytest

from spotlab.api.spot import Spot
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import SpotlabError
from spotlab.record.events import ARTEN


class _Recorder:
    def __init__(self):
        self.ereignisse = []
        self.dir = None

    def event(self, art, **daten):
        assert art in ARTEN, f"unbekannte Ereignisart: {art}"
        self.ereignisse.append((art, daten))


class _Abtaster:
    def __init__(self):
        self._takt = (10.0, False)
        self.verlauf = []

    def setze_takt(self, hz, reich):
        self._takt = (hz, reich)
        self.verlauf.append((hz, reich))

    def takt(self):
        return self._takt


def _spot(recorder=None, abtaster=None):
    return Spot(DryRunBackend(), recorder=recorder, sampler=abtaster)


def test_messfenster_ist_eine_erlaubte_ereignisart():
    assert "messfenster" in ARTEN


def test_marken_werden_geschrieben():
    recorder = _Recorder()
    with _spot(recorder).messfenster("G3", stuetzstelle="0.30", hz=50):
        pass
    assert [a for a, _ in recorder.ereignisse] == ["messfenster", "messfenster"]
    start, ende = (d for _a, d in recorder.ereignisse)
    assert start["phase"] == "start"
    assert start["name"] == "G3"
    assert start["hz_soll"] == 50
    assert start["stuetzstelle"] == "0.30"
    assert ende["phase"] == "ende"
    assert ende["name"] == "G3"


def test_takt_wird_gehoben_und_zurueckgestellt():
    abtaster = _Abtaster()
    with _spot(_Recorder(), abtaster).messfenster("G1", hz=50):
        assert abtaster.takt() == (50, True)
    assert abtaster.takt() == (10.0, False)


def test_ausnahme_schliesst_das_fenster_trotzdem():
    """Sonst bliebe der Lauf fuer immer auf 50 Hz und das Fenster ohne Ende."""
    recorder, abtaster = _Recorder(), _Abtaster()
    spot = _spot(recorder, abtaster)
    with pytest.raises(ValueError):
        with spot.messfenster("G6", hz=50):
            raise ValueError("Stoss danebengegangen")
    assert abtaster.takt() == (10.0, False)
    assert [d["phase"] for _a, d in recorder.ereignisse] == ["start", "ende"]


def test_verschachtelte_fenster_sind_verboten():
    spot = _spot(_Recorder(), _Abtaster())
    with spot.messfenster("aussen"):
        with pytest.raises(SpotlabError) as fehler:
            with spot.messfenster("innen"):
                pass
    assert "aussen" in str(fehler.value)


def test_nach_ausnahme_ist_wieder_ein_fenster_moeglich():
    spot = _spot(_Recorder(), _Abtaster())
    with pytest.raises(ValueError):
        with spot.messfenster("erstes"):
            raise ValueError
    with spot.messfenster("zweites"):
        pass


def test_ohne_abtaster_schreibt_es_nur_marken():
    """Ein direkt gebauter Spot (Test, Attrappe) darf daran nicht scheitern."""
    recorder = _Recorder()
    with _spot(recorder).messfenster("G1"):
        pass
    assert len(recorder.ereignisse) == 2


def test_ohne_recorder_faellt_nichts_um():
    with _spot().messfenster("G1"):
        pass


def test_reservierte_feldnamen_werden_abgewiesen():
    spot = _spot(_Recorder(), _Abtaster())
    for verboten in ("phase", "hz_soll"):
        with pytest.raises(SpotlabError) as fehler:
            with spot.messfenster("G1", **{verboten: "x"}):
                pass
        assert verboten in str(fehler.value)


def test_doppeltes_name_faengt_python_selbst_ab():
    """Deshalb steht `name` nicht in RESERVIERT — die Meldung ist schon klar."""
    spot = _spot(_Recorder(), _Abtaster())
    with pytest.raises(TypeError):
        with spot.messfenster("G1", name="zweimal"):
            pass


def test_connect_verdrahtet_den_abtaster(tmp_path):
    import spotlab

    with spotlab.connect(backend="dryrun", runs_dir=tmp_path / "runs") as spot:
        assert spot.sampler is not None
        with spot.messfenster("G1", hz=40):
            assert spot.sampler.takt() == (40, True)
        assert spot.sampler.takt() == (10.0, False)
