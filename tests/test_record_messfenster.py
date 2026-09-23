"""Das Messfenster-Protokoll fuer sich, ohne Roboter und ohne Spot.

Herausgeloest aus api/spot.py, damit der Beobachter-Modus dieselbe Definition
benutzt. Zwei Formulierungen haetten bedeutet, dass messung/fenster.py bald
zwei leicht verschiedene Fensterprotokolle lesen muss.
"""

import pytest

from spotlab.errors import SpotlabError
from spotlab.record.messfenster import Messfenster


class FakeRecorder:
    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))


class FakeSampler:
    def __init__(self):
        self.hz, self.reich = 10.0, False

    def takt(self):
        return self.hz, self.reich

    def setze_takt(self, hz, reich):
        self.hz, self.reich = hz, reich


def test_fenster_hebt_die_rate_und_setzt_sie_zurueck():
    rec, abt = FakeRecorder(), FakeSampler()
    with Messfenster(rec, abt).oeffne("G3", hz=50.0):
        assert abt.takt() == (50.0, True)
    assert abt.takt() == (10.0, False)


def test_der_takt_wird_umgeschaltet_bevor_das_startereignis_steht():
    """Das Startereignis ist die Abschnittsgrenze des Lueckenmelders. Steht es
    VOR dem Umschalten, kann eine Abtastung nach der Grenze noch den alten
    100-ms-Takt schlafen -- und der zaehlt dann gegen die 50-Hz-Erwartung des
    Fensters als Luecke (06.09.2026)."""
    reihenfolge = []

    class Recorder(FakeRecorder):
        def event(self, art, **daten):
            super().event(art, **daten)
            reihenfolge.append(("ereignis", daten.get("phase")))

    class Sampler(FakeSampler):
        def setze_takt(self, hz, reich):
            super().setze_takt(hz, reich)
            reihenfolge.append(("takt", hz))

    with Messfenster(Recorder(), Sampler()).oeffne("G3", hz=50.0):
        pass
    assert reihenfolge[:2] == [("takt", 50.0), ("ereignis", "start")], reihenfolge


def test_fenster_schreibt_start_und_ende():
    rec, abt = FakeRecorder(), FakeSampler()
    with Messfenster(rec, abt).oeffne("G3", hz=50.0, stuetzstelle="0.30"):
        pass
    assert [a for a, _ in rec.ereignisse] == ["messfenster", "messfenster"]
    assert rec.ereignisse[0][1]["phase"] == "start"
    assert rec.ereignisse[0][1]["name"] == "G3"
    assert rec.ereignisse[0][1]["hz_soll"] == 50.0
    assert rec.ereignisse[0][1]["stuetzstelle"] == "0.30"
    assert rec.ereignisse[1][1]["phase"] == "ende"


def test_ausnahme_setzt_die_rate_trotzdem_zurueck():
    """Ohne finally bliebe der Lauf fuer immer auf 50 Hz und das Fenster offen."""
    rec, abt = FakeRecorder(), FakeSampler()
    with pytest.raises(ValueError):
        with Messfenster(rec, abt).oeffne("G3"):
            raise ValueError("mittendrin")
    assert abt.takt() == (10.0, False)
    assert rec.ereignisse[-1][1]["phase"] == "ende"


def test_verschachtelung_ist_verboten():
    fenster = Messfenster(FakeRecorder(), FakeSampler())
    with fenster.oeffne("aussen"):
        with pytest.raises(SpotlabError, match="aussen"):
            with fenster.oeffne("innen"):
                pass


def test_nach_einer_ausnahme_ist_das_fenster_wieder_frei():
    fenster = Messfenster(FakeRecorder(), FakeSampler())
    with pytest.raises(ValueError):
        with fenster.oeffne("erstes"):
            raise ValueError("x")
    with fenster.oeffne("zweites"):
        pass


def test_reservierte_feldnamen_werden_abgewiesen():
    fenster = Messfenster(FakeRecorder(), FakeSampler())
    with pytest.raises(SpotlabError, match="phase"):
        with fenster.oeffne("G3", phase="start"):
            pass


@pytest.mark.parametrize("hz", [0, 0.0, -5, float("nan"), float("inf"), "fünfzig", None])
def test_eine_unsinnige_rate_wird_abgewiesen_und_das_fenster_bleibt_frei(hz, tmp_path):
    """Beta-Prüfung 23.09.2026 (p11): `hz=0` warf ZeroDivisionError im Abtaster
    -- und `_offen` blieb gesetzt: jedes weitere Fenster des Laufs scheiterte an
    „Es ist schon ein Messfenster offen“, einer Ursache, die es nicht gab.
    `hz=-5` lief ungebremst. Der ECHTE Abtaster, keine Attrappe: nur er rechnet
    1/hz (gestartet wird er nicht)."""
    from types import SimpleNamespace

    from spotlab.backends.dryrun import DryRunBackend
    from spotlab.record.sampler import StateSampler

    rec = FakeRecorder()
    abtaster = StateSampler(DryRunBackend(), SimpleNamespace(dir=tmp_path))
    vorher = abtaster.takt()
    fenster = Messfenster(rec, abtaster)
    with pytest.raises(SpotlabError, match="hz"):
        with fenster.oeffne("G1", hz=hz):
            pass
    assert fenster.offen is None
    assert abtaster.takt() == vorher
    assert rec.ereignisse == []
    with fenster.oeffne("G2", hz=50):                     # das naechste geht
        assert abtaster.takt() == (50.0, True)


def test_ohne_recorder_und_abtaster_laeuft_es_durch():
    """Tests bauen Spot ohne beides; das darf nicht werfen."""
    with Messfenster(None, None).oeffne("G3"):
        pass


def test_spot_delegiert_an_dieselbe_stelle():
    """Sonst gaebe es doch wieder zwei Fensterprotokolle."""
    from spotlab.api.spot import Spot
    from spotlab.backends.dryrun import DryRunBackend

    rec, abt = FakeRecorder(), FakeSampler()
    spot = Spot(DryRunBackend(), recorder=rec, sampler=abt)
    with spot.messfenster("G3", hz=25.0):
        assert abt.takt() == (25.0, True)
    assert [a for a, _ in rec.ereignisse] == ["messfenster", "messfenster"]
