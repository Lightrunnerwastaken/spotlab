"""Zeitlich begrenzte LED-/Summer-Signale; keine globalen AV-Einstellungen."""

import threading
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
# So lange wartet `aus()` hoechstens auf den Boten. Es steht im Abbau NACH dem
# Anhalten; laenger haelt ein haengender AV-Dienst das Programmende nicht auf,
# und die Farbe erlischt ohnehin mit ihrer Frist.
LICHT_AUS_WARTE_S = 1.0

_AUS = object()               # der Wunsch „Licht zurueckgeben" -- keine Farbe


def _im_hintergrund(arbeit):
    """Der Bote: ein Faden je Schub. Als Daemon -- ein haengender RPC haelt kein Programmende auf."""
    threading.Thread(target=arbeit, name='spotlab-statuslicht', daemon=True).start()


class Statuslicht:
    """Eine Farbe, die STEHEN BLEIBT — nicht blockierend, für eine laufende Schleife.

    `lights()` schläft die ganze Dauer und räumt danach auf. Im Folgetakt wäre das
    fatal: die Schleife hält den Totmann, und zwei Sekunden Schlaf je Takt sind
    zwei Sekunden ohne Fahrbefehl. Hier wird die Farbe einmal angelegt und nur
    dann erneut geschickt, wenn sie sich ÄNDERT oder die Frist abläuft — im
    ruhigen Fall eine Anfrage alle `auffrischen_s`.

    `setze()` und `aus()` BLOCKIEREN NIE den Aufrufer: die Anfragen an den Roboter
    gehen über einen Boten (`ausfuehren`, Vorgabe ein Hintergrundfaden). Bis zum
    22.09.2026 liefen sie im Takt der Schleife, mit bis zu 5 s Frist je Anfrage —
    ein hängender AV-Dienst hätte den Folgetakt um Sekunden verlängert, und
    während dieser Zeit lief der letzte Fahrbefehl weiter. Solange der Bote
    unterwegs ist, gilt nur der NEUESTE Wunsch; er wird geschickt, sobald der Bote
    zurück ist. Die Entscheidung, OB geschickt wird, fällt beim Aufrufer mit
    dessen Uhr — so bleibt sie ohne Faden prüfbar (`ausfuehren=lambda a: a()`).

    Die Frist ist der Totmann des Lichts: stirbt der Lauf, erlischt die Farbe von
    selbst. Ein hängendes Programm leuchtet nicht ewig grün.

    Ein Fehler hält nie den Lauf an — das Licht ist eine Beigabe, dieselbe Regel
    wie beim Gesichtserkenner im Fahrblick. Gezählt wird er trotzdem
    (`fehler`, `letzter_fehler`), verschwiegen wird nichts: der Aufrufer liest
    die beiden und sagt es (`folgen.folge` einmal). Nach einem Fehler setzt das
    Licht bis zur nächsten Auffrischfrist AUS (Rückoff) — vorher ging bei einem
    kaputten Dienst in JEDEM Takt eine neue Anfrage hinaus (p07: sechs in sechs
    Takten).
    """

    def __init__(self, spot, name=None, frist_s=LICHT_FRIST_S,
                 auffrischen_s=LICHT_AUFFRISCHEN_S, helligkeit=LICHT_HELLIGKEIT,
                 jetzt=time.time, ausfuehren=None, aus_warte_s=LICHT_AUS_WARTE_S):
        self._spot = spot
        self._name = name or ('spotlab-status-' + uuid.uuid4().hex)
        self._frist_s = float(frist_s)
        self._auffrischen_s = float(auffrischen_s)
        self._helligkeit = float(helligkeit)
        self._jetzt = jetzt
        self._ausfuehren = ausfuehren or _im_hintergrund
        self._aus_warte_s = float(aus_warte_s)
        self._sperre = threading.Lock()
        self._leer = threading.Event()   # gesetzt, solange kein Bote unterwegs ist
        self._leer.set()
        self._unterwegs = False
        self._wunsch = None              # die zuletzt gewuenschte Farbe -- oder _AUS
        self._farbe = None
        self._gesendet = None            # wann zuletzt geschickt
        self._pause_bis = None           # Rueckoff: bis dahin nach einem Fehler nichts senden
        self._angelegt = False
        self._av = None
        self.fehler = 0
        self.letzter_fehler = ''
        try:
            self.moeglich = spot.robot is not None and supports(spot, 'lights')
        except Exception:
            self.moeglich = False

    def _client(self):
        if self._av is None:
            self._av = self._spot.robot.ensure_client('audio-visual')
        return self._av

    def setze(self, farbe):
        """Die Farbe zeigen. Gleiche Farbe kostet nichts, bis die Frist knapp wird. Blockiert nie."""
        if not self.moeglich or farbe is None:
            return
        rgb = COLORS.get(farbe) if isinstance(farbe, str) else farbe
        if not isinstance(rgb, (tuple, list)) or len(rgb) != 3:
            self._notiere(ValueError(f'Unbekannte Farbe {farbe!r}'))
            return
        self._auftrag(farbe)

    def aus(self):
        """Das Licht zurückgeben. Wirft nie, und zweimal aus löscht nicht zweimal.

        Wartet höchstens `aus_warte_s` auf den Boten — gehört im Abbau deshalb
        HINTER das Anhalten des Roboters, nie davor.
        """
        if not self.moeglich:
            return
        self._auftrag(_AUS)
        self._leer.wait(self._aus_warte_s)

    # ------------------------------------------------------------- intern

    def _auftrag(self, wunsch):
        """Den Wunsch vormerken und, falls nötig und niemand unterwegs ist, den Boten schicken."""
        with self._sperre:
            self._wunsch = wunsch
            if self._unterwegs or not self._noetig(wunsch, self._jetzt()):
                return                   # der Bote nimmt den neuesten Wunsch mit
            self._unterwegs = True
            self._leer.clear()
        try:
            self._ausfuehren(self._arbeite)
        except Exception as fehler:      # kein Faden zu haben -- dann eben kein Licht
            with self._sperre:
                self._unterwegs = False
                self._leer.set()
            self._notiere(fehler)

    def _noetig(self, wunsch, nun):
        """Muss für diesen Wunsch etwas an den Roboter? Nur unter der Sperre rufen."""
        if wunsch is _AUS:
            return self._angelegt        # zurueckgeben auch im Rueckoff: es ist das Ende
        if wunsch is None:
            return False
        if self._pause_bis is not None and nun < self._pause_bis:
            return False
        return not (wunsch == self._farbe and self._gesendet is not None
                    and nun - self._gesendet < self._auffrischen_s)

    def _arbeite(self):
        """Der Bote: schickt, bis nichts mehr nötig ist. Wirft nie."""
        while True:
            with self._sperre:
                wunsch, nun = self._wunsch, self._jetzt()
                if not self._noetig(wunsch, nun):
                    self._unterwegs = False
                    self._leer.set()
                    return
                if wunsch is _AUS:
                    self._angelegt = False
                    self._farbe = self._gesendet = None
            if wunsch is _AUS:
                self._loesche()
            else:
                self._sende(wunsch, nun)

    def _sende(self, farbe, nun):
        rgb = COLORS.get(farbe) if isinstance(farbe, str) else farbe
        with self._sperre:
            anlegen = farbe != self._farbe or not self._angelegt
        try:
            client = self._client()
            if anlegen:
                behavior = av.AudioVisualBehavior(enabled=True, priority=0)
                for name in ('front_center', 'front_left', 'front_right',
                             'hind_left', 'hind_right'):
                    ziel = getattr(behavior.led_sequence_group, name)
                    c = ziel.solid_color_sequence.color.rgb
                    c.r, c.g, c.b = (round(v * self._helligkeit) for v in rgb)
                client.add_or_modify_behavior(self._name, behavior, timeout=5)
                with self._sperre:
                    self._angelegt = True
            antwort = client.run_behavior(
                self._name, end_time_secs=nun + self._frist_s, timeout=5
            )
            if antwort.run_result != av.RunBehaviorResponse.RESULT_BEHAVIOR_RUN:
                grund = av.RunBehaviorResponse.RunResult.Name(antwort.run_result)
                raise SpotlabError(f'Statuslicht nicht gestartet: {grund}.')
        except Exception as fehler:
            self._notiere(fehler)
            with self._sperre:
                # RUECKOFF: bis zur naechsten Auffrischfrist nichts mehr -- ab dem
                # Ende DIESES Versuchs gezaehlt, auch wenn er seine 5 s ausgeschoepft hat.
                self._pause_bis = self._jetzt() + self._auffrischen_s
            return
        with self._sperre:
            self._farbe, self._gesendet, self._pause_bis = farbe, nun, None

    def _loesche(self):
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
        with self._sperre:
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
