"""Bewegung auf zwei Ebenen.

move()  — relative Zieltrajektorie: „geh einen Meter" ohne Zeitintegration.
walk()  — Geschwindigkeitskommando des SDK, Andockpunkt für Regelschleifen
          und spätere neuronale Netze.

Der Geschwindigkeitsdeckel klemmt und weist nicht ab: ein Tippfehler soll
langsam sein, nicht knallen. Er wirkt auf BEIDEN Wegen — bei `walk()` durch
Klemmen der gesendeten Geschwindigkeit, bei `move()` über `vel_limit` in den
MobilityParams. Bei einer Zieltrajektorie wählt der Roboter sein Tempo selbst;
Klemmen allein liefe dort ins Leere.

ZWEI UHREN, mit Absicht:

- `jetzt` (monoton) misst DAUERN — wie lange schon gefahren wird. Monoton, weil
  eine Zeitumstellung oder ein NTP-Sprung sonst eine Fahrt verlängert oder
  abschneidet.
- `wanduhr` (`time.time`) stempelt die ENDZEIT eines Kommandos. Das SDK rechnet
  `end_time_secs` als Sekunden seit dem 1.1.1970 in Roboterzeit um
  (`time_sync.py::robot_timestamp_from_local_secs`). Ein monotoner Wert wäre
  dort sinnlos — und eine nackte Dauer ist es erst recht: `end_time_secs=1.0`
  hiess „gültig bis 1.1.1970, 00:00:01", also bei jedem Kommando abgelaufen.

Die beiden nicht zu verwechseln ist der Grund, warum sie getrennt injizierbar
sind. Ein gemeinsamer Parameter wäre bequemer und wieder falsch.

Ohne übergebene `wanduhr` gilt die Uhr des Backends (`backend.uhr()`), falls
es eine hat, sonst `time.time`. Der Physikkörper ohne Echtzeit zählt seine
Ablaufzeiten in Sim-Zeit; mit der Wanduhr hinge das Ergebnis dort von der
Rechnerlast ab (24.09.2026).
"""

import math
import time

from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.api.posture import warte_auf
from spotlab.backends.base import Capability, require

NACHSENDE_INTERVALL_S = 0.4
KOMMANDO_GUELTIGKEIT_S = 1.0


def _endlich(wert, name):
    """`wert` als float -- oder ValueError mit deutschem Text.

    NaN und inf sind keine Geschwindigkeiten: `max(-0.8, min(0.8, nan))`
    liefert 0.8, also VOLLE Drehrate aus einem NaN, und `inf` wird beim
    Klemmen zu NaN (Beta-Prüfung 23.09.2026). Ein NaN entsteht leicht, etwa
    als Mittelwert einer leeren Liste mit numpy; darum wird er abgewiesen,
    bevor ein Kommando gebaut ist -- nie geklemmt oder zu 0 umgedeutet.
    """
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        raise ValueError(f"{name} muss eine Zahl sein, nicht {wert!r}.") from None
    if not math.isfinite(zahl):
        raise ValueError(
            f"{name} muss eine endliche Zahl sein, nicht {zahl}. Spot bekommt kein "
            "Kommando. Den Wert vor dem Aufruf prüfen (z. B. mit math.isfinite) -- "
            "NaN entsteht etwa als Mittelwert einer leeren Liste."
        )
    return zahl


def _uhr_von(backend, wanduhr):
    """Die übergebene Uhr, sonst die des Backends, sonst die Wanduhr."""
    if wanduhr is not None:
        return wanduhr
    return getattr(backend, "uhr", time.time)


def clamp(vx, vy, wz, limits):
    """Klemmt auf die Konfigurationsgrenzen und erhält dabei die Fahrtrichtung.

    Nicht endliche Werte weist sie ab (ValueError), statt sie zu klemmen.
    """
    vx, vy, wz = _endlich(vx, "vx"), _endlich(vy, "vy"), _endlich(wz, "wz")
    betrag = math.hypot(vx, vy)
    if betrag > limits.max_speed and betrag > 0.0:
        faktor = limits.max_speed / betrag
        vx, vy = vx * faktor, vy * faktor
    wz = max(-limits.max_turn_rate, min(limits.max_turn_rate, wz))
    return float(vx), float(vy), float(wz)


def walk(
    backend,
    recorder,
    limits,
    vx=0.0,
    vy=0.0,
    wz=0.0,
    duration=1.0,
    stop=True,
    nick_grad=0.0,
    schlaf=time.sleep,
    jetzt=time.monotonic,
    wanduhr=None,
):
    """Fährt `duration` Sekunden mit der gegebenen Geschwindigkeit.

    Geschwindigkeitskommandos verfallen beim echten Spot — deshalb sendet diese
    Funktion laufend nach. Genau das soll kein Schüler selbst bauen müssen.

    Die Gültigkeit ist absichtlich kürzer als eine Fahrt: reisst die Verbindung
    ab, bleibt der Roboter nach `KOMMANDO_GUELTIGKEIT_S` stehen, statt mit dem
    letzten Kommando weiterzulaufen. Das ist eine Sicherheitseigenschaft, keine
    Sparsamkeit — sie wirkt nur, wenn die Endzeit ein echter Zeitpunkt ist.

    `stop=False` ist für Regelschleifen, die laufend neu lenken: das Kommando
    wird EINMAL gesendet, die Funktion kehrt sofort zurück, und am Ende steht
    kein Stopp. Spot fährt damit höchstens `KOMMANDO_GUELTIGKEIT_S` weiter —
    wer ihn fahren lassen will, ruft schneller nach. Mit `stop=True` (Vorgabe)
    hält jeder Aufruf am Ende an; eine Schleife daraus fährt in Schüben.
    """
    require(backend, Capability.LOCOMOTION, "gehen")
    vx, vy, wz = clamp(vx, vy, wz, limits)
    duration = _endlich(duration, "duration")
    nick_grad = _endlich(nick_grad, "nick_grad")
    if recorder is not None:
        recorder.event("kommando", name="walk", vx=vx, vy=vy, wz=wz, duration=duration,
                       stop=stop, nick_grad=float(nick_grad))
    # OHNE Neigung geht kein Feld mehr mit als bisher. Erst wer neigt, bekommt
    # ueberhaupt Parameter -- und dann auch Deckel und Treppenmodus, weil sie in
    # derselben Nachricht stehen. Der Deckel ist dieselbe Formulierung wie beim
    # Klemmen oben (`mobility.se2_grenze`), also kein zweiter Wert.
    params = backend.mobility_params(limits, nick_grad) if nick_grad else None
    wanduhr = _uhr_von(backend, wanduhr)

    def einmal():
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(
                v_x=vx, v_y=vy, v_rot=wz, params=params
            ),
            end_time_secs=wanduhr() + KOMMANDO_GUELTIGKEIT_S,
        )

    if not stop:
        einmal()
        return

    # Der letzte Schlaf ist nur der REST bis zum Ende, nicht die volle
    # Nachsendepause: sonst fuhr `duration=0.1` 0.4 s lang, `duration=1.0`
    # 1.2 s -- jede Dauer aufgerundet auf ein Vielfaches von 0.4 s, auch am
    # echten Roboter, denn der Stopp kam erst danach (Beta-Prüfung 23.09.2026).
    # Der Rest wird VOR dem Senden gemessen: so bleibt es bei einer Uhrabfrage
    # je Takt, und die Laufzeit des letzten Kommandos kommt hinzu, nicht 0.4 s.
    ende = jetzt() + duration
    while True:
        rest = ende - jetzt()
        if not rest > 0.0:
            break
        einmal()
        schlaf(min(NACHSENDE_INTERVALL_S, rest))
    _anhalten(backend, recorder)


def move(backend, recorder, limits, forward=0.0, left=0.0, turn=0.0, timeout=30.0,
         schlaf=time.sleep, wanduhr=None):
    """Relatives Ziel im Körperframe. `turn` in GRAD (Schülerfreundlichkeit).

    Die Endzeit ist genau die Geduld des Aufrufers: läuft `timeout` ab, ist das
    Kommando am Roboter im selben Moment verfallen. Ohne das liefe der Spot nach
    der Zeitüberschreitung weiter, während das Schülerskript längst mit einer
    Ausnahme abgebrochen hat — `warte_auf` schickt selbst keinen Stopp.

    Anders als bei `walk()` genügt Klemmen hier nicht: bei einer Zieltrajektorie
    wählt der Roboter sein Tempo selbst. Der Deckel muss deshalb als
    `vel_limit` mitgeschickt werden.
    """
    require(backend, Capability.LOCOMOTION, "gehen")
    forward, left = _endlich(forward, "forward"), _endlich(left, "left")
    turn, timeout = _endlich(turn, "turn"), _endlich(timeout, "timeout")
    if timeout <= 0.0:
        raise ValueError(f"timeout muss grösser als 0 sein, nicht {timeout}.")
    if forward == 0.0 and left == 0.0 and turn == 0.0:
        return
    winkel = math.radians(turn)
    if recorder is not None:
        recorder.event(
            "kommando",
            name="move",
            forward=float(forward),
            left=float(left),
            turn_grad=float(turn),
        )
    kommando = RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
        goal_x_rt_body=float(forward),
        goal_y_rt_body=float(left),
        goal_heading_rt_body=winkel,
        frame_tree_snapshot=backend.frame_tree_snapshot(),
        params=backend.mobility_params(limits),
    )
    wanduhr = _uhr_von(backend, wanduhr)
    kennung = backend.send_command(kommando, end_time_secs=wanduhr() + float(timeout))
    warte_auf(backend, kennung, timeout, "ankommen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="move", status="angekommen")


def stop(backend, recorder):
    require(backend, Capability.LOCOMOTION, "anhalten")
    if recorder is not None:
        recorder.event("kommando", name="stop")
    backend.send_command(RobotCommandBuilder.stop_command())


# `walk()` hat einen Parameter `stop` -- der verdeckt dort den Funktionsnamen.
# Gefunden von sechs Tests auf einmal: 'bool' object is not callable.
_anhalten = stop
