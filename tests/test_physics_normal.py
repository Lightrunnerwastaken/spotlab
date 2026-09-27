"""Physikmodus als normaler Übungsraum — Stufe A (28.09.2026).

Raumregel, Tags, Sperrzonen, move() und sit() im Kraftregler-Backend; alles ohne
Echtzeit auf der Sim-Uhr, damit die Rechnerlast nichts entscheidet.
"""
import pytest

from spotlab.backends.physics import PhysicsBackend
from spotlab.errors import UnsupportedCapability
from spotlab.welt.raum import Raum, Sperrzone, raum_laden

spotsim = pytest.importorskip('spotsim')
pytestmark = pytest.mark.skipif(not spotsim.spot_asset_available(), reason='Menagerie fehlt')


def _raum(**felder):
    return Raum(name='t', beschreibung='', start=(0.0, 0.0, 0.0), **felder)


def test_ein_raum_mit_sperrzone_laeuft_jetzt_in_der_physik():
    raum = _raum(sperrzonen=(Sperrzone('glas', 3.0, 0.0, 1.0, 1.0),))
    b = PhysicsBackend(raum=raum, autostart=False, realtime=False)
    b.close()


def test_das_backend_fragt_dieselbe_regel_wie_der_tab():
    with pytest.raises(UnsupportedCapability, match='Übungsraum 3D'):
        PhysicsBackend(raum=raum_laden('treppe'), autostart=False, realtime=False)
    with pytest.raises(UnsupportedCapability, match='Start'):
        PhysicsBackend(raum=raum_laden('physik_treppe_3stufen'), start=(1, 0, 0),
                       autostart=False, realtime=False)


def _tagraum(*waende):
    from spotlab.welt.raum import RaumTag

    # Der Tag bei x = 2 schaut zurueck zu Spot (Blickrichtung 180 Grad).
    return _raum(waende=list(waende), tags=(RaumTag(7, 2.0, 0.0, 180.0),))


def test_ein_tag_vor_spot_wird_gesehen():
    from spotlab.backends.base import Capability

    b = PhysicsBackend(raum=_tagraum(), autostart=False, realtime=False)
    try:
        assert b.capabilities() & Capability.WORLD_OBJECTS
        gefunden = b.world_objects()
        assert [t.id for t in gefunden] == [7]
        assert gefunden[0].kind == 'apriltag'
        assert gefunden[0].distance == pytest.approx(2.0, abs=0.1)
        assert gefunden[0].bearing == pytest.approx(0.0, abs=2.0)
        assert b.world_objects(kinds=['tracked_entity']) == []
    finally:
        b.close()


def test_ein_tag_hinter_einer_wand_bleibt_unsichtbar():
    b = PhysicsBackend(raum=_tagraum((1.0, -1.0, 1.0, 1.0)), autostart=False, realtime=False)
    try:
        assert b.world_objects() == []
    finally:
        b.close()


def _ereignisse(rec, art):
    import json

    zeilen = (rec.dir / 'ereignisse.jsonl').read_text(encoding='utf-8').splitlines()
    return [json.loads(z)['daten'] for z in zeilen if z.strip() and json.loads(z)['art'] == art]


def test_spot_haelt_vor_einer_sperrzone_und_kommt_wieder_heraus(tmp_path):
    """Die Zone reicht ab x = 2.0. Spot faehrt mit Hoechsttempo darauf zu,
    haelt mit dem ganzen Koerper davor, ein zweiter Anlauf haelt wieder, und
    rueckwaerts geht es heraus. Das Ereignis prueft der ECHTE RunRecorder."""
    from bosdyn.client.robot_command import RobotCommandBuilder as B

    from spotlab.record.run import RunRecorder
    from spotlab.welt.kollision import ROBOTER_RADIUS_M

    rec = RunRecorder(tmp_path, None, backend='physics')
    raum = _raum(sperrzonen=(Sperrzone('glas', 2.5, 0.0, 1.0, 2.0),))
    b = PhysicsBackend(recorder=rec, raum=raum, autostart=False, realtime=False)
    try:
        b.power_on()
        b.send_command(B.synchro_velocity_command(.85, 0, 0), end_time_secs=b.uhr() + 12)
        b.advance(8)
        assert not b.sim.metrics.fell
        x = b.qpos()[0]
        assert 1.0 < x < 2.0 - ROBOTER_RADIUS_M, f'Koerper bei x = {x:.2f}'
        treffer = _ereignisse(rec, 'angestossen')
        assert treffer and treffer[0]['hindernis'] == 'Sperrzone glas'

        b.send_command(B.synchro_velocity_command(.5, 0, 0), end_time_secs=b.uhr() + 6)
        b.advance(4)
        assert b.qpos()[0] < 2.0 - ROBOTER_RADIUS_M, 'der zweite Anlauf haelt auch'

        vorher = b.qpos()[0]
        b.send_command(B.synchro_velocity_command(-.3, 0, 0), end_time_secs=b.uhr() + 3)
        b.advance(3)
        assert b.qpos()[0] < vorher - .3, 'rueckwaerts heraus ist frei'
    finally:
        b.close()
        rec.finish('ok')


def test_die_sperrzone_haelt_auch_gedreht():
    """Start mit 90 Grad: vorwaerts ist Welt-y. Der Befehl kommt im Koerperrahmen,
    die Zone liegt im Raumrahmen -- eine falsche Drehung liesse ihn durchfahren."""
    from bosdyn.client.robot_command import RobotCommandBuilder as B

    from spotlab.welt.kollision import ROBOTER_RADIUS_M

    raum = _raum(sperrzonen=(Sperrzone('glas', 0.0, 2.5, 2.0, 1.0),))
    b = PhysicsBackend(raum=raum, start=(0, 0, 90), autostart=False, realtime=False)
    try:
        b.power_on()
        b.send_command(B.synchro_velocity_command(.6, 0, 0), end_time_secs=b.uhr() + 10)
        b.advance(7)
        y = b.qpos()[1]
        assert 1.0 < y < 2.0 - ROBOTER_RADIUS_M, f'Koerper bei y = {y:.2f}'
    finally:
        b.close()
