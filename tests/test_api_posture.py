import pytest

from spotlab.api.posture import sit, stand, warte_auf
from spotlab.backends.base import Feedback
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import CommandRejected, SpotlabError


def _backend():
    backend = DryRunBackend()
    backend.power_on()
    return backend


def test_stand_baut_ein_echtes_stand_protobuf():
    backend = _backend()
    stand(backend, None, schlaf=lambda _: None)
    kommando = backend.gesendet[0].synchronized_command.mobility_command
    assert kommando.HasField("stand_request")


def test_stand_reicht_koerperhoehe_durch():
    backend = _backend()
    stand(backend, None, height=0.05, schlaf=lambda _: None)
    params = backend.gesendet[0].synchronized_command.mobility_command.params
    assert params.value  # MobilityParams sind gesetzt


def test_sit_baut_ein_echtes_sit_protobuf():
    backend = _backend()
    sit(backend, None, schlaf=lambda _: None)
    kommando = backend.gesendet[0].synchronized_command.mobility_command
    assert kommando.HasField("sit_request")


def test_abgelehntes_kommando_wird_zu_klartext():
    class Abweisend(DryRunBackend):
        def command_feedback(self, command_id):
            return Feedback(done=False, status="abgelehnt", rejected=True)

    backend = Abweisend()
    backend.power_on()
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    assert "abgelehnt" in str(info.value)


def test_zeitueberschreitung_meldet_klartext():
    class Endlos(DryRunBackend):
        def command_feedback(self, command_id):
            return Feedback(done=False, status="unterwegs")

    backend = Endlos()
    backend.power_on()
    uhr = iter([0.0, 5.0, 20.0, 40.0])
    with pytest.raises(SpotlabError) as info:
        warte_auf(
            backend,
            "x",
            timeout=10.0,
            was="aufstehen",
            schlaf=lambda _: None,
            jetzt=lambda: next(uhr),
        )
    assert "aufstehen" in str(info.value)


def test_ereignisse_werden_aufgezeichnet(tmp_path):
    from spotlab.record.run import RunRecorder

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    stand(_backend(), rec, schlaf=lambda _: None)
    rec.finish("ok")
    text = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert '"kommando"' in text and "stand" in text


# ================== Verhaltensfehler beim Namen nennen
#
# Lauf 20260911T162238Z am Schul-Spot: `stand()` wurde abgelehnt, spotlab sagte
# "vom naechsten Kommando ueberschrieben". Die wahre Ursache -- ein
# Verhaltensfehler, den nur ein Mensch am Tablet loescht -- stand ausschliesslich
# in diagnose.log, weil erst der Abbau daran scheiterte. Der Roboter meldet den
# Fehler in JEDEM RobotState. Eine Meldung, die auf die falsche Faehrte schickt,
# kostet mehr Zeit als gar keine (CLAUDE.md).


def _zustand_mit_sturz():
    from bosdyn.api import robot_state_pb2 as rs

    zustand = rs.RobotState()
    fehler = zustand.behavior_fault_state.faults.add()
    fehler.behavior_fault_id = 3
    fehler.cause = rs.BehaviorFault.CAUSE_FALL
    fehler.status = rs.BehaviorFault.STATUS_CLEARABLE
    return zustand


class _Abweisend(DryRunBackend):
    def command_feedback(self, command_id):
        return Feedback(done=False, status="vom nächsten Kommando überschrieben", rejected=True)


def test_ein_abgelehntes_kommando_nennt_den_verhaltensfehler():
    class MitSturz(_Abweisend):
        def robot_state(self):
            return _zustand_mit_sturz()

    backend = MitSturz()
    backend.power_on()
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    text = str(info.value)
    assert "Verhaltensfehler" in text
    assert "Sturz" in text, "die Ursache aus dem RobotState, nicht geraten"
    assert "Tablet" in text, "und was zu tun ist"


def test_ohne_verhaltensfehler_bleibt_die_bisherige_meldung():
    """Kein Fehler im Zustand -> keine behauptete Ursache. Dieselbe Regel wie
    beim Lease-Verlust: keine Ursache nennen, die nicht geprueft ist."""
    backend = _Abweisend()
    backend.power_on()
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    assert "Verhaltensfehler" not in str(info.value)
    assert "überschrieben" in str(info.value)


def test_ein_unlesbarer_zustand_verdeckt_die_ablehnung_nicht():
    """Die Nachfrage darf den urspruenglichen Fehler nie ueberschreiben --
    dieselbe Regel wie beim Rollback in `RealSpot.connect()`."""
    class Stumm(_Abweisend):
        def robot_state(self):
            raise RuntimeError("Funk weg")

    backend = Stumm()
    backend.power_on()
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    assert "überschrieben" in str(info.value)


def test_verhaltensfehler_liest_die_liste_und_wirft_nie():
    from spotlab.api.state import verhaltensfehler

    class MitSturz(DryRunBackend):
        def robot_state(self):
            return _zustand_mit_sturz()

    class Stumm(DryRunBackend):
        def robot_state(self):
            raise RuntimeError("Funk weg")

    assert verhaltensfehler(DryRunBackend()) == []
    [fehler] = verhaltensfehler(MitSturz())
    assert fehler["ursache"] == "CAUSE_FALL" and fehler["id"] == 3
    assert verhaltensfehler(Stumm()) == []
