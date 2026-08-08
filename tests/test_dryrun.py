import pytest
from bosdyn.api import robot_command_pb2
from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.backends.base import Capability
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import NotPowered, UnsupportedCapability


def test_faehigkeiten_sind_ehrlich():
    koennen = DryRunBackend().capabilities()
    assert koennen & Capability.LOCOMOTION
    assert not (koennen & Capability.CAMERAS)
    assert not (koennen & Capability.LEASE)


def test_echtes_protobuf_wird_angenommen_und_abgelegt():
    backend = DryRunBackend()
    backend.power_on()
    kommando = RobotCommandBuilder.synchro_stand_command()
    kennung = backend.send_command(kommando)
    assert isinstance(kennung, str)
    assert len(backend.gesendet) == 1
    assert backend.gesendet[0].HasField("synchronized_command")


def test_bytes_werden_ebenfalls_akzeptiert():
    """Wie über gRPC: dasselbe Kommando als serialisierte Bytes."""
    backend = DryRunBackend()
    backend.power_on()
    roh = RobotCommandBuilder.synchro_velocity_command(0.5, 0.0, 0.0).SerializeToString()
    backend.send_command(roh)
    assert backend.gesendet[0].synchronized_command.mobility_command.HasField(
        "se2_velocity_request"
    )


def test_fremdes_protobuf_wird_abgelehnt():
    backend = DryRunBackend()
    backend.power_on()
    with pytest.raises(ValueError, match="RobotCommand"):
        backend.send_command(robot_command_pb2.RobotCommandResponse())


def test_kommando_ohne_strom_wird_abgelehnt():
    backend = DryRunBackend()
    with pytest.raises(NotPowered):
        backend.send_command(RobotCommandBuilder.synchro_stand_command())


def test_rueckmeldung_wird_nach_einem_abruf_fertig():
    backend = DryRunBackend()
    backend.power_on()
    kennung = backend.send_command(RobotCommandBuilder.synchro_stand_command())
    assert backend.command_feedback(kennung).done is False
    assert backend.command_feedback(kennung).done is True


def test_robot_state_hat_batterie_und_gelenke():
    zustand = DryRunBackend().robot_state()
    assert zustand.battery_states[0].charge_percentage.value > 0
    assert len(zustand.kinematic_state.joint_states) == 12


def test_frame_tree_snapshot_enthaelt_body_und_odom():
    schnappschuss = DryRunBackend().frame_tree_snapshot()
    assert "body" in schnappschuss.child_to_parent_edge_map
    assert "odom" in schnappschuss.child_to_parent_edge_map


def test_kameras_werden_ehrlich_verweigert():
    backend = DryRunBackend()
    assert backend.image_sources() == []
    with pytest.raises(UnsupportedCapability):
        backend.images(["frontleft_fisheye_image"])


def test_safety_status_ist_leer():
    zustand = DryRunBackend().safety_status()
    assert zustand.lease_holder is None and zustand.estop_level is None


# --------------------------------------------------------- Kalibrierfelder (Stufe 7)


def test_trockenlauf_liefert_die_kalibrierfelder():
    """Sonst waere die erste echte Messfahrt zugleich der erste Test."""
    from spotlab.api.state import from_proto

    backend = DryRunBackend()
    backend.power_on()
    s = from_proto(backend.robot_state())
    assert 0.35 < s.z < 0.50
    assert s.t_robot > 0
    assert len(s.feet_detail) == 4
    assert all(0.3 < f["mu"] < 1.0 for f in s.feet_detail if f["kontakt"])
    assert s.behavior in ("STANDING", "STEPPING", "TRANSITION")
    assert s.battery_detail["spannung"] > 0
    assert len(s.motor_temps) == 12


def test_trockenlauf_zeitstempel_laeuft_weiter():
    from spotlab.api.state import from_proto

    backend = DryRunBackend()
    erst = from_proto(backend.robot_state()).t_robot
    zweit = from_proto(backend.robot_state()).t_robot
    assert zweit >= erst > 0
