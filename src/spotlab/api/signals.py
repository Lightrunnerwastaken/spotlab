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


LICHT_FRIST_S = 12.0          # so lange gilt eine gesetzte Farbe am Roboter
LICHT_AUFFRISCHEN_S = 5.0     # so oft wird sie erneuert, solange sie gleich bleibt
LICHT_HELLIGKEIT = .35


class Statuslicht:
    """Eine Farbe, die STEHEN BLEIBT — nicht blockierend, für eine laufende Schleife.

    `lights()` schläft die ganze Dauer und räumt danach auf. Im Folgetakt wäre das
    fatal: die Schleife hält den Totmann, und zwei Sekunden Schlaf je Takt sind
    zwei Sekunden ohne Fahrbefehl. Hier wird die Farbe einmal angelegt und nur
    dann erneut geschickt, wenn sie sich ÄNDERT oder die Frist abläuft — im
    ruhigen Fall eine Anfrage alle `auffrischen_s`.

    Die Frist ist der Totmann des Lichts: stirbt der Lauf, erlischt die Farbe von
    selbst. Ein hängendes Programm leuchtet nicht ewig grün.

    Ein Fehler hält nie den Lauf an — das Licht ist eine Beigabe, dieselbe Regel
    wie beim Gesichtserkenner im Fahrblick. Gezählt wird er trotzdem
    (`fehler`, `letzter_fehler`), verschwiegen wird nichts.
    """

    def __init__(self, spot, name=None, frist_s=LICHT_FRIST_S,
                 auffrischen_s=LICHT_AUFFRISCHEN_S, helligkeit=LICHT_HELLIGKEIT,
                 jetzt=time.time):
        self._spot = spot
        self._name = name or ('spotlab-status-' + uuid.uuid4().hex)
        self._frist_s = float(frist_s)
        self._auffrischen_s = float(auffrischen_s)
        self._helligkeit = float(helligkeit)
        self._jetzt = jetzt
        self._farbe = None
        self._gesendet = None        # wann zuletzt geschickt
        self._angelegt = False
        self.fehler = 0
        self.letzter_fehler = ''
        try:
            self.moeglich = spot.robot is not None and supports(spot, 'lights')
        except Exception:
            self.moeglich = False

    def _client(self):
        return self._spot.robot.ensure_client('audio-visual')

    def setze(self, farbe):
        """Die Farbe zeigen. Gleiche Farbe kostet nichts, bis die Frist knapp wird."""
        if not self.moeglich or farbe is None:
            return
        nun = self._jetzt()
        gleich = farbe == self._farbe
        if gleich and self._gesendet is not None and nun - self._gesendet < self._auffrischen_s:
            return
        rgb = COLORS.get(farbe) if isinstance(farbe, str) else farbe
        if not isinstance(rgb, (tuple, list)) or len(rgb) != 3:
            self._notiere(ValueError(f'Unbekannte Farbe {farbe!r}'))
            return
        try:
            client = self._client()
            if not gleich or not self._angelegt:
                behavior = av.AudioVisualBehavior(enabled=True, priority=0)
                for name in ('front_center', 'front_left', 'front_right',
                             'hind_left', 'hind_right'):
                    ziel = getattr(behavior.led_sequence_group, name)
                    c = ziel.solid_color_sequence.color.rgb
                    c.r, c.g, c.b = (round(v * self._helligkeit) for v in rgb)
                client.add_or_modify_behavior(self._name, behavior, timeout=5)
                self._angelegt = True
            antwort = client.run_behavior(
                self._name, end_time_secs=nun + self._frist_s, timeout=5
            )
            if antwort.run_result != av.RunBehaviorResponse.RESULT_BEHAVIOR_RUN:
                grund = av.RunBehaviorResponse.RunResult.Name(antwort.run_result)
                raise SpotlabError(f'Statuslicht nicht gestartet: {grund}.')
        except Exception as fehler:
            self._notiere(fehler)
            return
        self._farbe, self._gesendet = farbe, nun

    def aus(self):
        """Das Licht zurückgeben. Wirft nie, und zweimal aus löscht nicht zweimal."""
        if not self._angelegt:
            return
        self._angelegt = False
        self._farbe = self._gesendet = None
        try:
            client = self._client()
        except Exception as fehler:
            self._notiere(fehler)
            return
        for fn, arg in ((client.stop_behavior, self._name),
                        (client.delete_behaviors, [self._name])):
            try:
                fn(arg, timeout=5)
            except Exception as fehler:
                self._notiere(fehler)

    def _notiere(self, fehler):
        self.fehler += 1
        self.letzter_fehler = f'{type(fehler).__name__}: {fehler}'


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
