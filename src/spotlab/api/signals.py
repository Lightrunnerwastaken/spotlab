"""Zeitlich begrenzte LED-/Summer-Signale; keine globalen AV-Einstellungen."""

import time
import uuid

from bosdyn.api import audio_visual_pb2 as av

from spotlab.api.convenience import zahl
from spotlab.api.features import supports
from spotlab.errors import SpotlabError, UnsupportedCapability

COLORS = {'blue': (0, 0, 255), 'green': (0, 255, 0), 'red': (255, 0, 0),
          'white': (255, 255, 255), 'yellow': (255, 255, 0), 'purple': (128, 0, 255)}


def lights(spot, color='blue', duration=2.0, brightness=.25):
    duration = zahl(duration, 'duration', .05, 10)
    brightness = zahl(brightness, 'brightness', 0, 1)
    rgb = COLORS.get(color) if isinstance(color, str) else color
    if not isinstance(rgb, (tuple, list)) or len(rgb) != 3 or any(
        isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in rgb
    ):
        raise ValueError('color: blue, green, red, white, yellow, purple oder RGB-Tupel (0..255).')
    behavior = av.AudioVisualBehavior(enabled=True, priority=0)
    for name in ('front_center', 'front_left', 'front_right', 'hind_left', 'hind_right'):
        c = getattr(behavior.led_sequence_group, name).solid_color_sequence.color.rgb
        c.r, c.g, c.b = (round(v * brightness) for v in rgb)
    _run(spot, 'lights', behavior, duration, color=list(rgb), brightness=brightness)


def beep(spot, note='C', octave=5, duration=.3):
    duration = zahl(duration, 'duration', .05, 5)
    if isinstance(octave, bool) or not isinstance(octave, int) or not 0 <= octave <= 8:
        raise ValueError('octave muss eine ganze Zahl von 0 bis 8 sein.')
    if not isinstance(note, str) or note.upper() not in tuple('CDEFGAB'):
        raise ValueError('note muss C, D, E, F, G, A oder B sein.')
    behavior = av.AudioVisualBehavior(enabled=True, priority=0)
    ton = behavior.audio_sequence_group.buzzer.notes.add()
    ton.note.note = ton.note.DESCRIPTOR.fields_by_name['note'].enum_type.values_by_name['NOTE_' + note.upper()].number
    ton.note.octave.value = octave
    ton.duration.FromNanoseconds(round(duration * 1e9))
    _run(spot, 'beep', behavior, duration, note=note.upper(), octave=octave)


def _run(spot, art, behavior, duration, **daten):
    if not supports(spot, art):
        raise UnsupportedCapability(f'{art} braucht den audio-visual-Dienst; in diesem Backend nicht vorhanden.')
    rec = spot.recorder
    if rec is not None:
        rec.event('kommando', name=art, duration=duration, **daten)
    if spot.robot is None:
        # Echtes Protobuf ist gebaut; der Trockenlauf spielt nichts ab.
        if rec is not None:
            rec.event('rückmeldung', name=art, status='Protobuf geprueft (Trockenlauf)')
        return
    client = spot.robot.ensure_client('audio-visual')
    name = 'spotlab-' + uuid.uuid4().hex
    hauptfehler = None
    try:
        client.add_or_modify_behavior(name, behavior, timeout=5)
        response = client.run_behavior(name, end_time_secs=time.time() + duration, timeout=5)
        if response.run_result != av.RunBehaviorResponse.RESULT_BEHAVIOR_RUN:
            grund = av.RunBehaviorResponse.RunResult.Name(response.run_result)
            raise SpotlabError(f'{art} wurde nicht gestartet: {grund}. AV-System oder Prioritaet pruefen.')
        time.sleep(duration)
    except BaseException as exc:
        hauptfehler = exc
        raise
    finally:
        fehler = []
        for fn, arg in ((client.stop_behavior, name), (client.delete_behaviors, [name])):
            try:
                fn(arg, timeout=5)
            except Exception as exc:
                fehler.append(str(exc))
        if fehler:
            meldung = 'AV-Aufraeumen fehlgeschlagen: ' + '; '.join(fehler)
            if hauptfehler is not None:
                hauptfehler.add_note(meldung)
            else:
                raise SpotlabError(meldung)
    if rec is not None:
        rec.event('rückmeldung', name=art, status='beendet')
