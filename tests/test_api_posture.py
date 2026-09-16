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


# Lauf 20260916T144908Z am Schul-Spot: `stand()` abgelehnt "wegen eines
# Hardwarefehlers". WELCHE Hardware, stand nur in der Fehlerhistorie des
# Roboters: spot.fl.kna.mc.fault, "Current error", Dauer 0 s -- beim Nachfragen
# laengst kein aktueller Systemfehler mehr. Die Meldung soll das Teil nennen,
# das den Verhaltensfehler ausgeloest hat: den kritischen Systemfehler, dessen
# Beginn zum Beginn des Verhaltensfehlers passt.


def _zustand_mit_hardwarefehler(name="spot.fl.kna.mc.fault", text="Current error",
                                abstand_s=0.0, schwere=None, historisch=True):
    from bosdyn.api import robot_state_pb2 as rs

    zustand = rs.RobotState()
    bf = zustand.behavior_fault_state.faults.add()
    bf.behavior_fault_id = 5
    bf.cause = rs.BehaviorFault.CAUSE_HARDWARE
    bf.status = rs.BehaviorFault.STATUS_CLEARABLE
    bf.onset_timestamp.seconds = 1_000
    liste = zustand.system_fault_state.historical_faults if historisch else zustand.system_fault_state.faults
    sf = liste.add()
    sf.name = name
    sf.error_message = text
    sf.severity = rs.SystemFault.SEVERITY_CRITICAL if schwere is None else schwere
    sf.onset_timestamp.seconds = 1_000 + int(abstand_s)
    return zustand


def _abweisend_mit(zustand):
    class Backend(_Abweisend):
        def robot_state(self):
            return zustand

    backend = Backend()
    backend.power_on()
    return backend


def test_ein_hardwarefehler_nennt_das_betroffene_teil():
    backend = _abweisend_mit(_zustand_mit_hardwarefehler())
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    text = str(info.value)
    assert "Hardwarefehler" in text
    assert "spot.fl.kna.mc.fault" in text and "Current error" in text, text


def test_eine_warnung_ist_kein_hardwarefehler():
    """Die Akku-Firmware-Warnung stand wochenlang an -- sie hat nichts abgelehnt."""
    from bosdyn.api import robot_state_pb2 as rs

    zustand = _zustand_mit_hardwarefehler(
        name="battery_fault", text="Battery needs firmware update",
        schwere=rs.SystemFault.SEVERITY_WARN, historisch=False,
    )
    backend = _abweisend_mit(zustand)
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    assert "battery_fault" not in str(info.value)


def test_ein_alter_kritischer_fehler_wird_nicht_genannt():
    """Zehn Minuten vor dem Verhaltensfehler: eine andere Geschichte."""
    backend = _abweisend_mit(_zustand_mit_hardwarefehler(abstand_s=-600))
    with pytest.raises(CommandRejected) as info:
        stand(backend, None, schlaf=lambda _: None)
    assert "spot.fl.kna.mc.fault" not in str(info.value)


def test_verhaltensfehler_traegt_die_passende_hardware():
    from spotlab.api.state import verhaltensfehler

    [fehler] = verhaltensfehler(_abweisend_mit(_zustand_mit_hardwarefehler()))
    assert fehler["ursache"] == "CAUSE_HARDWARE"
    assert fehler["hardware"] == ["spot.fl.kna.mc.fault: Current error"]
