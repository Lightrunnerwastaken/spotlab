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


# ----------------------------------------- Treue des Testdoubles: end_time_secs
#
# Diese Gruppe existiert wegen eines echten Fehlers: api/motion.py schickte
# `end_time_secs=1.0` — die nackte Gueltigkeitsdauer statt eines Zeitpunkts.
# Das SDK liest den Wert als Sekunden seit dem 1.1.1970
# (time_sync.py::robot_timestamp_from_local_secs), der echte Spot haette jedes
# Fahrkommando mit ExpiredError abgewiesen. 681 gruene Tests sahen nichts davon,
# weil dieses Backend den Parameter entgegennahm und wegwarf.


FIXZEIT = 1_800_000_000.0


def _bereit(jetzt=lambda: FIXZEIT):
    backend = DryRunBackend(jetzt=jetzt)
    backend.power_on()
    return backend


def _fahrbefehl():
    from bosdyn.client.robot_command import RobotCommandBuilder

    return RobotCommandBuilder.synchro_velocity_command(v_x=0.2, v_y=0.0, v_rot=0.0)


def test_abgelaufene_endzeit_wird_abgewiesen():
    """Der Fehler, der 56 Jahre alt beim Roboter angekommen waere."""
    from spotlab.errors import CommandRejected

    backend = _bereit()
    with pytest.raises(CommandRejected) as fehler:
        backend.send_command(_fahrbefehl(), end_time_secs=1.0)
    assert "keine Dauer" in str(fehler.value)


def test_endzeit_in_ferner_zukunft_wird_abgewiesen():
    """Millisekunden statt Sekunden — der zweite naheliegende Zahlendreher."""
    from spotlab.errors import CommandRejected

    backend = _bereit()
    with pytest.raises(CommandRejected):
        backend.send_command(_fahrbefehl(), end_time_secs=FIXZEIT * 1000)


def test_gueltige_endzeit_wird_mitgeschrieben():
    backend = _bereit()
    backend.send_command(_fahrbefehl(), end_time_secs=FIXZEIT + 1.0)
    assert backend.endzeiten == [FIXZEIT + 1.0]


def test_ohne_endzeit_bleibt_es_erlaubt():
    """Haltungskommandos brauchen keine — nur Geschwindigkeit, Trajektorie, Stance."""
    backend = _bereit()
    backend.send_command(_fahrbefehl())
    assert backend.endzeiten == [None]


def test_endzeiten_laufen_parallel_zu_gesendet():
    backend = _bereit()
    backend.send_command(_fahrbefehl())
    backend.send_command(_fahrbefehl(), end_time_secs=FIXZEIT + 2.0)
    assert len(backend.endzeiten) == len(backend.gesendet) == 2


def test_deckel_kommt_aus_derselben_quelle_wie_beim_echten_backend():
    from spotlab.backends.mobility import mit_grenze
    from spotlab.config import Limits

    grenzen = Limits(max_speed=0.4, max_turn_rate=0.7)
    assert DryRunBackend().mobility_params(grenzen) == mit_grenze(grenzen)


def test_dryrun_meldet_wahrnehmungsfaehigkeiten():
    backend = DryRunBackend()
    assert backend.capabilities() & Capability.WORLD_OBJECTS
    assert backend.capabilities() & Capability.LOCAL_GRID


def test_dryrun_liefert_zwei_tags_und_ein_dock():
    objekte = DryRunBackend().world_objects()
    assert sorted(o.kind for o in objekte) == ["apriltag", "apriltag", "dock"]


def test_dryrun_tags_sind_deterministisch():
    erste = DryRunBackend().world_objects()
    zweite = DryRunBackend().world_objects()
    assert [(o.name, o.distance) for o in erste] == [(o.name, o.distance) for o in zweite]


def test_dryrun_filtert_nach_art():
    nur_tags = DryRunBackend().world_objects(kinds=["apriltag"])
    assert len(nur_tags) == 2
    assert all(o.kind == "apriltag" for o in nur_tags)


def test_dryrun_gitter_hat_eine_wand():
    gitter = DryRunBackend().local_grid()
    assert gitter.cell_size > 0
    assert gitter.cells.min() < 0.2      # irgendwo ist die Wand
    assert gitter.cells.max() > 1.0      # und irgendwo ist frei


def test_der_treppenmodus_steht_in_denselben_mobility_params():
    from bosdyn.api.spot import robot_command_pb2 as spot_pb2

    from spotlab.backends.mobility import mit_grenze
    from spotlab.config import Limits

    assert mit_grenze(Limits()).stairs_mode == spot_pb2.MobilityParams.STAIRS_MODE_AUTO
    assert mit_grenze(Limits(treppen="aus")).stairs_mode == spot_pb2.MobilityParams.STAIRS_MODE_OFF
    assert not mit_grenze(Limits()).stair_hint
