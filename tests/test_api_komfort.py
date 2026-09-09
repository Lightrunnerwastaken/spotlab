import math
from types import SimpleNamespace

import numpy as np
import pytest
from bosdyn.api import audio_visual_pb2 as av
from bosdyn.api.spot import robot_command_pb2 as spot_pb

from spotlab.api import signals
from spotlab.api.convenience import Surroundings
from spotlab.api.spot import Spot
from spotlab.api.state import State
from spotlab.backends.base import ObstacleGrid
from spotlab.backends.dryrun import DryRunBackend
from spotlab.backends.sim import SimBackend
from spotlab.errors import SpotlabError, UnsupportedCapability
from spotlab.record.run import RunRecorder


def ansicht(cells=None, known=None, **kw):
    grid = ObstacleGrid(np.ones((41, 41)) if cells is None else cells,
                        .1, (-2., -2.), 1., known=known)
    return Surroundings(grid, (0, 0), kw.get('heading', 0), 1.5, .3, kw.get('start', 0))


def test_look_unbekannt_wird_nie_frei():
    maske = np.ones((41, 41), dtype=bool)
    maske[20, 20] = False
    v = ansicht(known=maske)
    assert not v.front.known
    assert v.front.distance is None
    assert v.front.status == 'unknown'


def test_richtungen_rotieren_mit_dem_koerper():
    cells = np.ones((41, 41))
    cells[30, :] = 0
    v = ansicht(cells=cells, heading=90)
    assert v.front.status == 'blocked'
    assert .9 <= v.front.distance <= 1.1
    assert v.left.status == 'clear'
    assert v.back.status == 'clear'


def test_expliziter_start_laesst_luecke_sichtbar():
    mask = np.ones((41, 41), dtype=bool)
    mask[20, 20] = False
    v = ansicht(known=mask, start=.5)
    assert v.front.known
    assert v.front.start == .5


def test_look_nutzt_vision_statt_odom():
    class Backend(DryRunBackend):
        def frame_tree_snapshot(self):
            baum = super().frame_tree_snapshot()
            baum.child_to_parent_edge_map['odom'].parent_tform_child.position.x = 10
            return baum

    v = Spot(Backend()).look()
    assert v.position[0] == 10


def test_state_namen_lassen_rohwerte_unveraendert():
    s = State(88, True, (2, 3, math.pi/2), (.3, .4, 0), {}, ())
    assert (s.x, s.y, s.heading, s.speed) == (2, 3, 90, .5)
    assert s.pose[2] == math.pi/2


class AVClient:
    def __init__(self, result=av.RunBehaviorResponse.RESULT_BEHAVIOR_RUN):
        self.calls = []
        self.result = result

    def add_or_modify_behavior(self, name, behavior, **kw):
        self.calls.append(('add', name))
        self.behavior = behavior

    def run_behavior(self, name, end_time_secs, **kw):
        self.calls.append(('run', name))
        self.end = end_time_secs
        return av.RunBehaviorResponse(status=1, run_result=self.result)

    def stop_behavior(self, name, **kw):
        self.calls.append(('stop', name))

    def delete_behaviors(self, names, **kw):
        self.calls.append(('delete', names[0]))


def echt(client, recorder=None):
    robot = SimpleNamespace(list_services=lambda: [SimpleNamespace(name='audio-visual')],
                            ensure_client=lambda name: client)
    # Kein DryRunBackend: Test darf die reale Faehigkeitspruefung nicht umgehen.
    return Spot(SimpleNamespace(), robot=robot, recorder=recorder)


def test_licht_protobuf_endzeit_und_cleanup(monkeypatch, tmp_path):
    c = AVClient()
    rec = RunRecorder(tmp_path/'runs', None, backend='dryrun')
    monkeypatch.setattr(signals.time, 'sleep', lambda s: None)
    monkeypatch.setattr(signals.time, 'time', lambda: 1000.)
    echt(c, rec).lights('blue', duration=2, brightness=.25)
    assert c.behavior.led_sequence_group.front_center.solid_color_sequence.color.rgb.b == 64
    assert c.end == 1002
    assert [n for n, _ in c.calls] == ['add', 'run', 'stop', 'delete']
    assert len({n for _, n in c.calls}) == 1
    rec.finish('ok')
    assert 'lights' in (rec.dir/'ereignisse.jsonl').read_text(encoding='utf-8')


def test_summer_note_und_dauer(monkeypatch):
    c = AVClient()
    monkeypatch.setattr(signals.time, 'sleep', lambda s: None)
    echt(c).beep('D', octave=4, duration=.3)
    note = c.behavior.audio_sequence_group.buzzer.notes[0]
    assert note.note.note == note.note.NOTE_D
    assert note.note.octave.value == 4
    assert note.duration.nanos == 300_000_000


def test_av_unterdrueckt_ist_kein_erfolg(monkeypatch):
    c = AVClient(av.RunBehaviorResponse.RESULT_LOW_PRIORITY)
    with pytest.raises(SpotlabError, match='RESULT_LOW_PRIORITY'):
        echt(c).beep()
    assert [n for n, _ in c.calls][-2:] == ['stop', 'delete']


def test_av_raeumt_bei_abbruch_auf(monkeypatch):
    c = AVClient()
    def abbrechen(s):
        raise KeyboardInterrupt
    monkeypatch.setattr(signals.time, 'sleep', abbrechen)
    with pytest.raises(KeyboardInterrupt):
        echt(c).lights()
    assert [n for n, _ in c.calls][-2:] == ['stop', 'delete']


def test_av_cleanup_fehler_verschluckt_keinen_hauptfehler(monkeypatch):
    c = AVClient(av.RunBehaviorResponse.RESULT_SYSTEM_DISABLED)
    def kaputt(*a, **kw):
        raise RuntimeError('Stopp nicht erreichbar')
    c.stop_behavior = kaputt
    with pytest.raises(SpotlabError, match='RESULT_SYSTEM_DISABLED') as error:
        echt(c).beep()
    assert 'Aufraeumen' in error.value.__notes__[0]
    assert c.calls[-1][0] == 'delete'


def test_sim_verspricht_keine_av_oder_koerperpose():
    s = Spot(SimBackend())
    for name in ('lights', 'beep', 'pose'):
        assert not s.supports(name)
        with pytest.raises(UnsupportedCapability):
            getattr(s, name)()


def test_pose_grad_und_meter_in_echten_protobufs(monkeypatch):
    from spotlab.api import body
    monkeypatch.setattr(body, 'warte_auf', lambda *a: None)
    b = DryRunBackend()
    s = Spot(b)
    s.power_on()
    s.pose(pitch=10, height=.05)
    mobil = b.gesendet[-1].synchronized_command.mobility_command
    params = spot_pb.MobilityParams()
    mobil.params.Unpack(params)
    p = params.body_control.base_offset_rt_footprint.points[0].pose
    assert p.position.z == pytest.approx(.05)
    assert p.rotation.y == pytest.approx(math.sin(math.radians(10)/2))


@pytest.mark.parametrize('method,kwargs', [('lights', {'brightness': float('nan')}),
    ('beep', {'note': 'X'}), ('beep', {'duration': -1}), ('pose', {'pitch': 999}),
    ('look', {'start': 3}), ('look', {'margin': 0})])
def test_parameterfehler_vor_io(method, kwargs):
    with pytest.raises(ValueError):
        getattr(Spot(SimpleNamespace()), method)(**kwargs)
