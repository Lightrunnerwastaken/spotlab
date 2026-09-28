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
    b = PhysicsBackend(haltung='stehend', raum=raum, autostart=False, realtime=False)
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

    b = PhysicsBackend(haltung='stehend', raum=_tagraum(), autostart=False, realtime=False)
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
    b = PhysicsBackend(haltung='stehend', raum=_tagraum((1.0, -1.0, 1.0, 1.0)), autostart=False, realtime=False)
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
    b = PhysicsBackend(haltung='stehend', recorder=rec, raum=raum, autostart=False, realtime=False)
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
    b = PhysicsBackend(haltung='stehend', raum=raum, start=(0, 0, 90), autostart=False, realtime=False)
    try:
        b.power_on()
        b.send_command(B.synchro_velocity_command(.6, 0, 0), end_time_secs=b.uhr() + 10)
        b.advance(7)
        y = b.qpos()[1]
        assert 1.0 < y < 2.0 - ROBOTER_RADIUS_M, f'Koerper bei y = {y:.2f}'
    finally:
        b.close()


# ------------------------------------------------------------------- move()


def _ziel(b, vor=0.0, links=0.0, grad=0.0):
    import math

    from bosdyn.client.robot_command import RobotCommandBuilder as B

    from spotlab.config import Limits

    return B.synchro_trajectory_command_in_body_frame(
        goal_x_rt_body=vor, goal_y_rt_body=links, goal_heading_rt_body=math.radians(grad),
        frame_tree_snapshot=b.frame_tree_snapshot(), params=b.mobility_params(Limits()))


def _bis_fertig(b, key, sim_s):
    """Auf der Sim-Uhr vorrechnen, bis die Rueckmeldung fertig oder abgewiesen ist."""
    ende = b.sim.time + sim_s
    while b.sim.time < ende:
        b.advance(.25)
        rueck = b.command_feedback(key)
        if rueck.done or rueck.rejected:
            return rueck
    return b.command_feedback(key)


def _gier_grad(b):
    import math

    q = b.qpos()
    return math.degrees(math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2)))


def test_move_einen_meter_vor():
    b = PhysicsBackend(haltung='stehend', autostart=False, realtime=False)
    try:
        b.power_on()
        key = b.send_command(_ziel(b, vor=1.0), end_time_secs=b.uhr() + 30)
        rueck = _bis_fertig(b, key, 30)
        assert rueck.done and not rueck.rejected, rueck.status
        x, y = b.qpos()[:2]
        assert x == pytest.approx(1.0, abs=.05) and y == pytest.approx(0.0, abs=.05)
        assert _gier_grad(b) == pytest.approx(0.0, abs=3.0)
        assert not b.sim.metrics.fell
    finally:
        b.close()


def test_move_eine_vierteldrehung():
    b = PhysicsBackend(haltung='stehend', autostart=False, realtime=False)
    try:
        b.power_on()
        key = b.send_command(_ziel(b, grad=90), end_time_secs=b.uhr() + 30)
        rueck = _bis_fertig(b, key, 30)
        assert rueck.done and not rueck.rejected, rueck.status
        assert _gier_grad(b) == pytest.approx(90.0, abs=3.0)
        assert abs(b.qpos()[0]) < .05 and abs(b.qpos()[1]) < .05
        assert not b.sim.metrics.fell
    finally:
        b.close()


def test_move_endet_an_der_frist_mit_grund():
    b = PhysicsBackend(haltung='stehend', autostart=False, realtime=False)
    try:
        b.power_on()
        key = b.send_command(_ziel(b, vor=3.0), end_time_secs=b.uhr() + 2)
        rueck = _bis_fertig(b, key, 6)
        assert rueck.rejected and 'Frist' in rueck.status and 'nicht erreicht' in rueck.status
        assert b.qpos()[0] < 2.0
    finally:
        b.close()


def test_move_haelt_vor_einer_sperrzone_und_sagt_es():
    raum = _raum(sperrzonen=(Sperrzone('glas', 2.5, 0.0, 1.0, 2.0),))
    b = PhysicsBackend(haltung='stehend', raum=raum, autostart=False, realtime=False)
    try:
        b.power_on()
        key = b.send_command(_ziel(b, vor=4.0), end_time_secs=b.uhr() + 30)
        rueck = _bis_fertig(b, key, 20)
        assert rueck.rejected and 'Sperrzone glas' in rueck.status
        assert b.qpos()[0] < 1.8
    finally:
        b.close()


# -------------------------------------------------------------------- sit()


def test_sit_haelt_an_bleibt_stehen_und_sagt_es_einmal(tmp_path, monkeypatch):
    from bosdyn.client.robot_command import RobotCommandBuilder as B

    import spotlab.backends.mujoco as mj
    from spotlab.api import posture
    from spotlab.record.run import RunRecorder

    # Seit Stufe B sitzt der Physikmodus echt; dieser Rückfall gilt für eine spotsim-Fassung
    # ohne Haltung (tests/test_physics_haltung.py prüft das echte Sitzen).
    monkeypatch.setattr(mj, '_haltung_fassung', lambda: 0)
    rec = RunRecorder(tmp_path, None, backend='physics')
    b = PhysicsBackend(recorder=rec, autostart=False, realtime=False)
    try:
        assert b.kann_sitzen is False
        b.power_on()
        b.send_command(B.synchro_velocity_command(.4, 0, 0), end_time_secs=b.uhr() + 20)
        b.advance(2)
        gesagt = []
        posture.sit(b, rec, melde=gesagt.append)
        posture.sit(b, rec, melde=gesagt.append)
        b.advance(3)
        assert gesagt == [posture.SITZEN_FEHLT_PHYSIK]
        assert abs(b.sim.data.qvel[0]) < .05, 'sit() haelt an'
        assert b.qpos()[2] > .3, 'und Spot steht noch'
        rueck = [e for e in _ereignisse(rec, 'rückmeldung') if e.get('name') == 'sit']
        assert rueck and 'steht' in rueck[0]['status']
    finally:
        b.close()
        rec.finish('ok')


# ------------------------------------------------ die Zentrale als Prozess


def test_die_zentrale_faehrt_im_physikraum_per_klick_und_endet_sauber(tmp_path):
    """Das echte Programm des Tabs „Fahren“ mit Backend physics: Lagebilder kommen, ein
    Klickziel einen Meter voraus wird angefahren (Klickfahrt mit Lebenszeichen, wie der Tab
    es schreibt), und der freundliche Stopp beendet den Lauf ohne Absturz. Ein eigener
    Prozess, weil ein Absturz hier sonst die ganze Suite mitnaehme."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    import spotlab
    from spotlab.record import zentrale as protokoll
    from tests_zeitgrenzen import TEST_TIMEOUT_S, warte_bis

    quelle = str(Path(spotlab.__file__).resolve().parents[1])     # das gepruefte Paket
    env = dict(os.environ, SPOTLAB_BACKEND='physics', SPOTLAB_RAUM='leer',
               SPOTLAB_NUR_TROCKEN='1',
               PYTHONPATH=os.pathsep.join([quelle] + [os.environ.get('PYTHONPATH', '')]))
    prozess = subprocess.Popen(
        [sys.executable, '-m', 'spotlab.workshop.zentrale', '--runs', str(tmp_path)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
        errors='replace')
    try:
        lauf = warte_bis(lambda: next((p for p in tmp_path.iterdir() if p.is_dir()), None)
                         if prozess.poll() is None else 'tot', 'das Lauf-Verzeichnis')
        assert lauf != 'tot', prozess.communicate()[0][-3000:]
        warte_bis(lambda: (protokoll.lies_lagebild(lauf) or {}).get('spot')
                  or prozess.poll() is not None, 'ein Lagebild mit Spots Lage')
        assert prozess.poll() is None, prozess.communicate()[0][-3000:]

        start = protokoll.lies_lagebild(lauf)['spot']
        ziel = (start['x'] + 1.0, start['y'])
        stand = {}

        def herzschlag():
            protokoll.schreibe_klickziel(lauf, 1, ziel, 'normal')

        def fertig():
            bild = protokoll.lies_lagebild(lauf) or {}
            stand.update(bild.get('klickfahrt') or {}, spot=bild.get('spot'))
            return (stand.get('nummer') == 1 and stand.get('zustand') not in (None, 'unterwegs')
                    or prozess.poll() is not None)

        warte_bis(fertig, lambda: f'Ankunft der Klickfahrt (zuletzt {stand})',
                  takt_s=0.1, zwischendurch=herzschlag)
        assert prozess.poll() is None, prozess.communicate()[0][-3000:]
        assert stand['zustand'] == 'angekommen', stand
        assert stand['spot']['x'] == pytest.approx(ziel[0], abs=.35), stand
        (lauf / 'stopp').write_text('', encoding='utf-8')
        ausgabe, _ = prozess.communicate(timeout=TEST_TIMEOUT_S)
    finally:
        if prozess.poll() is None:
            prozess.kill()
            prozess.communicate()
    import json

    assert json.loads((lauf / 'lauf.json').read_text(encoding='utf-8'))['backend'] == 'physics'
    # Der freundliche Stopp endet ueber KeyboardInterrupt: unter Windows 0xC000013A, sonst 1.
    assert prozess.returncode in (0, 1, 0xC000013A), (hex(prozess.returncode), ausgabe[-3000:])
    assert 'Sturz' not in ausgabe and 'access violation' not in ausgabe, ausgabe[-3000:]
