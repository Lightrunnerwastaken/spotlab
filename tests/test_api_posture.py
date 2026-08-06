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
