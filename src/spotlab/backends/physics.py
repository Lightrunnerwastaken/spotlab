"""Experimenteller Physikmodus: Kontaktkraefte tragen den Koerper.

Separat von der kinematischen Puppe. Der bestehende SpotSdkSim-Regler bleibt
unveraendert; diese Klasse adaptiert Sitzung, Uhr, Abtastung und GUI.
"""
import itertools
import math
import queue
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import numpy as np
from bosdyn.api import robot_state_pb2
from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.backends import mobility
from spotlab.backends.base import Capability, Feedback, SafetyStatus
from spotlab.backends.dryrun import ZU_WEIT_S
from spotlab.errors import CommandRejected, NotPowered, SpotlabError, UnsupportedCapability

HINWEIS = ('Physikmodus: eigener Kraftregler aus matura-spot, nicht der Regler von '
           'Boston Dynamics. Ebene Raeume mit Waenden, Bloecken, Tags und Sperrzonen; '
           'Spot sitzt am Anfang, steht ueber die gemessene Bahn auf (142 echte Faelle), '
           'setzt sich hin und haelt im Stand eine Haltung (pose). Annahmen: Hinsetzen = '
           'Aufstehen rueckwaerts, 1 s je Haltungsaenderung (Messung A41). Rampen, Treppen '
           'und Gelaende noch nicht. Keine Realismusfreigabe.')
HINWEIS_OHNE_HALTUNG = ('Physikmodus: eigener Kraftregler aus matura-spot, nicht der Regler von '
                        'Boston Dynamics. Ebene Raeume mit Waenden, Bloecken, Tags und Sperrzonen; '
                        'stand, walk, move und stop. Sitzen bleibt stehen (diese spotsim-Fassung '
                        'kann es nicht); Rampen, Treppen, Gelaende und Koerperpose noch nicht. '
                        'Keine Realismusfreigabe.')

# Nullpunkt der Sim-Uhr ohne Echtzeit (`uhr()`). Nicht 0: eine nackte Dauer
# (`end_time_secs=1.0`) ist damit abgelaufen. Weit weg von der Wanduhr (1.7e9):
# `time.time() + 1` liegt dann jenseits von ZU_WEIT_S und wird abgewiesen, statt
# um die Rechnerlast daneben zu liegen. Derselbe Nullpunkt wie
# `kalibrierung.nachspiel.START` fuer den kinematischen Sim.
SIM_UHR_NULL = 1_000_000.0

# Vor einer Sperrzone prueft der Takt den Punkt, den Spot in dieser Zeit mit
# seinem jetzigen Tempo erreicht: ein Koerper mit Schwung haelt nicht auf der
# Stelle wie der kinematische Sim (`welt.kollision.zone_im_weg`).
ZONE_VORAUS_S = 0.5

# move(): der Physik-Takt regelt selbst zum Ziel -- der Kraftregler kennt nur
# Geschwindigkeiten. Alle ZIEL_TAKT_S Sim-Zeit ein Gehbefehl, der nach
# ZIEL_GUELTIG_S von selbst verfaellt (bleibt der Takt aus, steht Spot).
# Angekommen heisst ZIEL_M und ZIEL_GRAD, wie im Entwurf festgelegt.
ZIEL_TAKT_S = 0.1
ZIEL_GUELTIG_S = 0.3
ZIEL_M = 0.05
ZIEL_GRAD = 3.0
ZIEL_K_V = 1.0          # 1/s: 10 cm vor dem Ziel noch 0.1 m/s
ZIEL_V_MIN = 0.08       # m/s: darunter kommt der Gang nicht voran
ZIEL_K_W = 1.5          # 1/s
ZIEL_W_MIN = 0.15       # rad/s: der echte Spot dreht unter 0.125 gar nicht
# Beim Anhalten setzt der Regler noch Schritte ab und verschiebt den Koerper
# (gemessen 2-7 cm). Gezaehlt wird deshalb die Lage, wenn er STEHT; liegt sie
# daneben, setzt er hoechstens so oft nach.
ZIEL_NACHSETZEN = 2
# "Steht" heisst so lange ohne Bewegung. Ein einzelner ruhiger Takt mitten im
# Absetzen der Schritte galt vorher schon als Stand (28.09.2026: danach noch 5 cm).
RUHE_S = 0.3


class _Shutdown(BaseException):
    pass


class PhysicsBackend:
    # Ohne spotsim-Haltung (Fassung 0) kann der Regler nicht sitzen -- `api/posture.sit`
    # haelt dann an und sagt es (Stufe A). Mit Fassung >= 1 setzt `__init__` beides wahr.
    kann_sitzen = False
    kann_pose = False

    def __init__(self, recorder=None, raum=None, start=None, ansicht_ziel=None,
                 realtime=True, autostart=True, haltung=None):
        from spotlab.backends import mujoco as _mj
        from spotlab.backends.mujoco import (
            _Ansichtsschreiber,
            _physik_grenzen,
            _physik_laden,
            welt_aus_raum,
        )

        puppe, self._sensorik, SpotSdkSim, TerrainSdkSim = _physik_laden()
        # Grenzen des Gangreglers aus spotsim (trab 0.3/0.5, kraft 0.85/1.0)
        self._max_tempo, self._max_drehrate = _physik_grenzen()

        # Welche Raeume gehen, sagt EINE Regel (welt/physik.py) -- der Tab fragt dieselbe.
        from spotlab.welt import physik

        ok, art, grund = physik.tauglich(raum, start)
        if not ok:
            raise UnsupportedCapability(grund)
        self._terrain_steps = art != physik.EBEN
        # Stufe B: wie der echte Spot sitzend beginnen, aufstehen, hinsetzen, Haltung halten --
        # wenn spotsim es kann. Die zwei Stufenszenen sind stehend validiert und bleiben es.
        fassung = _mj._haltung_fassung()
        self.kann_sitzen = self.kann_pose = fassung >= 1
        if haltung is None:
            haltung = 'sitzend' if self.kann_sitzen and not self._terrain_steps else 'stehend'
        if haltung == 'sitzend' and (not self.kann_sitzen or self._terrain_steps):
            raise UnsupportedCapability('Sitzend beginnt der Physikmodus nur in ebenen Raeumen und mit '
                                        'einer spotsim-Fassung, die sitzen kann.')
        self._hoehe_grenzen, self._lage_grenzen, self._haltung_rampe_s = (
            _mj._haltung_grenzen() if self.kann_pose else ((0.0, 0.0), (0.0, 0.0, 0.0), 0.0))
        self._erwartet = None              # 'sitzt' | 'steht' | 'pose' fuer die Rueckmeldung
        self._aus_nach_sitzen = False
        self._recorder = recorder
        self._lock = threading.RLock()
        self._halt = threading.Event()
        self._jobs = queue.Queue()
        self._ids = itertools.count(1)
        self._feedback = {}
        self._pending = None
        self._active = None
        self._deadline = None
        self._waiting_still = True
        self._command_time = 0.0
        self._soll = (0., 0.)
        self._ziel = None
        self._ziel_ruht = False
        self._nachsetzen = 0
        self._ziel_naechster = 0.0
        self._ruhig_seit = None
        self._raum = raum
        self._powered = False
        self._error = None
        self._closed = False
        self._realtime = realtime
        self._thread = None
        self._ansicht = None
        self.welt = welt_aus_raum(raum, puppe)
        model, data = puppe.bau_modell(self.welt)
        if start is not None:
            import mujoco

            x, y, grad = start
            yaw = math.radians(grad)
            # Einmalige Anfangsbedingung. Danach schreibt nur mj_step die Basis.
            data.qpos[:2] = (x, y)
            data.qpos[3:7] = (math.cos(yaw / 2), 0, 0, math.sin(yaw / 2))
            mujoco.mj_forward(model, data)
        simulator = SpotSdkSim
        if self._terrain_steps:
            simulator = TerrainSdkSim
        extra = {'haltung': haltung} if fassung >= 1 else {}
        self.sim = simulator(szene=(model, data, data.ctrl.copy()), **extra)
        if haltung == 'sitzend':
            self.sim.motoren(False)        # wie am echten Spot: bis power_on() liegt er schlaff
        self.model = model
        # Was `SpotPuppe.sichtbare_tags` von einer Puppe braucht, hier aus der Physik.
        self._puppe = puppe
        self._tagsicht = SimpleNamespace(
            lock=threading.RLock(), model=model, data=self.sim.data, welt=self.welt,
            sensors=self.sim.sensors, _torso=model.body(puppe.TORSO).id)
        self._qpos = data.qpos.copy()
        self._sim_start = self.sim.time
        self._wall_start = time.monotonic()
        self._publish()
        if ansicht_ziel:
            from pathlib import Path

            proxy = SimpleNamespace(model=model, welt=self.welt, qpos=self.qpos)
            self._ansicht = _Ansichtsschreiber(puppe, proxy, Path(ansicht_ziel))
            self._ansicht.start()
        if autostart:
            self._thread = threading.Thread(target=self._run, name='spotlab-physik', daemon=True)
            self._thread.start()

    def capabilities(self):
        return (Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
                | Capability.DEPTH_CAMERAS | Capability.GRAY_CAMERAS | Capability.LOCAL_GRID
                | Capability.WORLD_OBJECTS)

    def hinweis_zur_gueltigkeit(self):
        if self._terrain_steps:
            return ('Experimenteller Kriechgang: Podest bis 6 cm oder Versuchstreppe 3 x 4 cm; vorwaerts auf, '
                    'rueckwaerts ab, nur Welt-x. Hoehen aus bekannter Szenengeometrie, '
                    'keine Tiefenwahrnehmung. Schritt wird vor Stopp fertig abgesetzt. '
                    'Keine Freigabe fuer normale Treppen oder Sim-zu-Real.')
        return HINWEIS if self.kann_sitzen else HINWEIS_OHNE_HALTUNG

    def treppengang(self):
        return None

    def _check(self):
        if self._error is not None:
            raise SpotlabError(f'Physik-Simulation angehalten: {self._error}') from self._error
        if self._closed:
            raise SpotlabError('Physik-Sitzung ist beendet. Neu verbinden.')

    def power_on(self):
        """Kommandofreigabe -- und mit spotsim-Haltung die Motoren: Spot sitzt dann, bis stand()."""
        with self._lock:
            self._check()
        if self.kann_sitzen and self.sim.haltung == 'aus':
            self._call(lambda: self.sim.motoren(True))
        with self._lock:
            self._powered = True

    def power_off(self, safe=True):
        """Wie `power_off(safe=True)` am echten Spot: erst hinsetzen, dann Motoren aus.

        Ohne spotsim-Haltung nur die Kommandofreigabe (Stufe A)."""
        with self._lock:
            if not self._closed:
                if self.kann_sitzen:
                    self._pending = ('off', RobotCommandBuilder.synchro_sit_command(), None, None)
                    self._aus_nach_sitzen = True
                else:
                    self._pending = ('off', RobotCommandBuilder.stop_command(), None, None)
            self._powered = False

    @property
    def is_powered(self):
        with self._lock:
            return self._powered

    def uhr(self):
        """Die Uhr fuer `end_time_secs`; `motion.walk` nimmt sie als `wanduhr`.

        In Echtzeit die Wanduhr, wie am Roboter: reisst die Verbindung ab, steht
        Spot nach der Gueltigkeit still, auch wenn die Physik hinterherhinkt.
        Ohne Echtzeit die Sim-Zeit: eine Wanduhr mass dort die Rechnerlast, und
        dieselbe Tastaturfahrt stuerzte unter Last und lief einzeln durch
        (24.09.2026).
        """
        if self._realtime:
            return time.time()
        return SIM_UHR_NULL + self.sim.time

    def send_command(self, command, end_time_secs=None):
        from bosdyn.api.spot import robot_command_pb2 as sp

        copy = type(command)()
        copy.CopyFrom(command)
        mob = copy.synchronized_command.mobility_command
        stop = copy.full_body_command.HasField('stop_request')
        velocity = mob.HasField('se2_velocity_request')
        stand = mob.HasField('stand_request')
        goal = mob.HasField('se2_trajectory_request')
        sit = mob.HasField('sit_request') and self.kann_sitzen
        if not (stop or velocity or stand or goal or sit):
            raise UnsupportedCapability('Der Physikmodus kann stand(), walk(), move() und stop(); '
                                        'Sitzen und Koerperpose kann diese spotsim-Fassung noch nicht.')
        params = sp.MobilityParams()
        mob.params.Unpack(params)
        if params.locomotion_hint not in (sp.HINT_UNKNOWN, sp.HINT_AUTO, sp.HINT_TROT):
            raise UnsupportedCapability('Physik v1 verwendet den kontinuierlichen Trab-Regler; HINT_AUTO waehlen.')
        pose_befohlen = False
        if params.body_control.base_offset_rt_footprint.points:
            pose = params.body_control.base_offset_rt_footprint.points[-1].pose
            pose_befohlen = abs(pose.position.z) > 1e-9 or any(
                abs(v) > 1e-9 for v in (pose.rotation.x, pose.rotation.y, pose.rotation.z))
            if pose_befohlen and not (stand and self.kann_pose):
                raise UnsupportedCapability('Eine Koerperhaltung gibt es im Physikmodus nur im Stand '
                                            '(pose()); beim Gehen bleibt sie neutral.')
            if pose_befohlen:
                copy = self._gekappte_pose(pose)
        if velocity:
            req = mob.se2_velocity_request
            if req.se2_frame_name != 'body':
                raise UnsupportedCapability('Physik v1 braucht Geschwindigkeiten im body-Rahmen.')
            values = (req.velocity.linear.x, req.velocity.linear.y, req.velocity.angular)
            if not all(math.isfinite(v) for v in values):
                raise ValueError('Geschwindigkeiten muessen endlich sein.')
            self._frist_pruefen(end_time_secs)
            # Grenzen des Gangreglers (spotsim.tempo_grenzen); Sättigung sichtbar melden.
            if self._terrain_steps and (abs(values[1]) > 1e-9 or abs(values[2]) > 1e-9):
                raise UnsupportedCapability('Einzelstufenmodus bisher nur vorwaerts/rueckwaerts; kein Drehen/Seitwaerts.')
            max_speed = .02 if self._terrain_steps else self._max_tempo
            speed = math.hypot(*values[:2])
            factor = min(1., max_speed / speed) if speed else 1.
            req.velocity.linear.x *= factor
            req.velocity.linear.y *= factor
            req.velocity.angular = max(-self._max_drehrate, min(self._max_drehrate, values[2]))
            if factor < 1 or req.velocity.angular != values[2]:
                if self._recorder is not None:
                    self._recorder.event('kommando', name='physik_grenze',
                                         max_speed=max_speed, max_turn_rate=self._max_drehrate)
        ziel = self._ziel_aus(mob, params, end_time_secs) if goal else None
        with self._lock:
            self._check()
            if not self._powered and not stop:
                raise NotPowered('Kommandofreigabe aus: zuerst power_on() aufrufen.')
            if (velocity or goal) and self.kann_sitzen and self.sim.haltung in ('sitzt', 'setzt_sich', 'aus'):
                raise CommandRejected('Spot sitzt -- zuerst stand() aufrufen, wie am echten Spot.')
            key = str(next(self._ids))
            if self._pending is not None:
                self._feedback[self._pending[0]] = Feedback(False, 'durch neues Kommando ersetzt', True)
            self._feedback[key] = Feedback(False, 'wartet auf Physiktakt')
            self._pending = (key, copy, end_time_secs, ziel)
            return key

    def _gekappte_pose(self, pose):
        """Das Stehkommando mit der Haltung in den Grenzen des Reglers; Kappung wird gemeldet."""
        from bosdyn.geometry import EulerZXY, to_euler_zxy

        e = to_euler_zxy(pose.rotation)
        roh = (pose.position.z, e.roll, e.pitch, e.yaw)
        if not all(math.isfinite(v) for v in roh):
            raise ValueError('Die Haltung muss endlich sein.')
        (h_min, h_max), grenzen = self._hoehe_grenzen, self._lage_grenzen
        hoehe = min(h_max, max(h_min, roh[0]))
        winkel = [min(g, max(-g, v)) for v, g in zip(roh[1:], grenzen)]
        if self._recorder is not None and (hoehe != roh[0] or winkel != list(roh[1:])):
            self._recorder.event('kommando', name='physik_grenze',
                                 hoehe_m=round(hoehe, 4), roll_grad=round(math.degrees(winkel[0]), 2),
                                 pitch_grad=round(math.degrees(winkel[1]), 2),
                                 yaw_grad=round(math.degrees(winkel[2]), 2))
        return RobotCommandBuilder.synchro_stand_command(
            body_height=hoehe, footprint_R_body=EulerZXY(roll=winkel[0], pitch=winkel[1], yaw=winkel[2]))

    def _frist_pruefen(self, end_time_secs):
        jetzt = self.uhr()
        if end_time_secs is None or not math.isfinite(end_time_secs) or end_time_secs <= jetzt:
            raise CommandRejected('Fahrbefehle brauchen eine gueltige absolute Ablaufzeit.')
        if not self._realtime and end_time_secs > jetzt + ZU_WEIT_S:
            raise CommandRejected('Ohne Echtzeit laeuft die Ablaufzeit auf der Sim-Uhr: '
                                  'end_time_secs=backend.uhr() + Dauer, nicht time.time() + Dauer '
                                  '(motion.walk: wanduhr=backend.uhr).')

    def _ziel_aus(self, mob, params, end_time_secs):
        """((x, y, gier) im odom-Rahmen, Tempodeckel m/s, Drehdeckel rad/s) aus move().

        In der Physik ist odom der Weltrahmen (spotsim `frame_tree_snapshot`). Ein
        anderer Rahmen wird nicht geraten, wie im kinematischen Sim. Der Deckel ist
        der kleinere aus `vel_limit` (Konfiguration) und den Grenzen des Reglers.
        """
        from bosdyn.client.frame_helpers import ODOM_FRAME_NAME

        if self._terrain_steps:
            raise UnsupportedCapability('Im Stufenversuch geht nur walk() vorwaerts und rueckwaerts; '
                                        'move() geht in ebenen Raeumen.')
        req = mob.se2_trajectory_request
        if req.se2_frame_name != ODOM_FRAME_NAME or not req.trajectory.points:
            raise CommandRejected('move() braucht ein Ziel im odom-Rahmen mit mindestens einem Punkt.')
        pose = req.trajectory.points[-1].pose
        lage = (pose.position.x, pose.position.y, pose.angle)
        if not all(math.isfinite(v) for v in lage):
            raise ValueError('Das Ziel muss endlich sein.')
        self._frist_pruefen(end_time_secs)
        tempo, dreh = self._max_tempo, self._max_drehrate
        if params.HasField('vel_limit'):
            grenze = params.vel_limit.max_vel
            if grenze.linear.x > 0:
                tempo = min(tempo, grenze.linear.x)
            if grenze.angular > 0:
                dreh = min(dreh, grenze.angular)
        return lage, tempo, dreh

    def command_feedback(self, key):
        with self._lock:
            self._check()
            return self._feedback.get(key, Feedback(False, 'unbekannte Kommando-ID', True))

    def _publish(self):
        state = self._sensorik.robot_state_proto(self.sim.sensors)
        with self._lock:
            state.power_state.motor_power_state = (robot_state_pb2.PowerState.STATE_ON
                if self._powered else robot_state_pb2.PowerState.STATE_OFF)
            self._state = state
            self._qpos = self.sim.data.qpos.copy()
        if self._ansicht is not None:
            self._ansicht.publiziere(self._qpos)

    def _tick(self, phase=None):
        if self._halt.is_set():
            raise _Shutdown()
        # Der Worker allein greift auf Controller und MjData zu.
        with self._lock:
            pending, self._pending = self._pending, None
        if pending is not None:
            key, command, deadline, ziel = pending
            if self._active is not None:
                with self._lock:
                    if not self._feedback[self._active].done:
                        self._feedback[self._active] = Feedback(False, 'ersetzt', True)
            self._ziel = ziel
            self._ziel_ruht = False
            self._nachsetzen = ZIEL_NACHSETZEN
            if ziel is None:
                expiry = self.sim.time + max(0., deadline - self.uhr()) if deadline else None
                self.sim.send_command(command, end_time_secs=expiry)
            else:
                self._ziel_naechster = self.sim.time      # der erste Regelschritt sofort
            self._active = key if key != 'off' else None
            self._deadline = deadline
            self._command_time = self.sim.time
            mob = command.synchronized_command.mobility_command
            self._waiting_still = ziel is None and (
                command.full_body_command.HasField('stop_request')
                or mob.HasField('stand_request') or mob.HasField('sit_request'))
            self._erwartet = None
            if self.kann_sitzen and mob.HasField('sit_request'):
                self._erwartet = 'sitzt'
            elif self.kann_sitzen and mob.HasField('stand_request'):
                self._erwartet = 'pose' if self._hat_pose(mob) else 'steht'
            soll = command.synchronized_command.mobility_command.se2_velocity_request.velocity
            self._soll = (0., 0.) if self._waiting_still else (soll.linear.x, soll.linear.y)
        if self._deadline is not None and self.uhr() >= self._deadline:
            self._halte()
            self._deadline = None
            if self._ziel is not None:
                self._ziel_beenden(f'Frist abgelaufen, Ziel nicht erreicht ({self._rest()})')
        if self._ziel is not None and not self._ziel_ruht and self.sim.time >= self._ziel_naechster:
            self._zum_ziel()
        if not self._waiting_still and self._raum is not None:
            self._zone_pruefen()
        if self._aus_nach_sitzen and self.sim.haltung == 'sitzt':
            self.sim.motoren(False)         # power_off: erst sitzen, dann aus
            self._aus_nach_sitzen = False
        if self.sim.metrics.fell:
            raise SpotlabError('Regler meldet einen Sturz; Versuch beendet. Lauf auswerten und neu starten.')
        if self._active is not None:
            ruhig = (np.linalg.norm(self.sim.data.qvel[:2]) < .04
                     and np.linalg.norm(self.sim.data.qvel[3:6]) < .15
                     and not getattr(self.sim, "in_step", False))
            if not ruhig:
                self._ruhig_seit = None
            elif self._ruhig_seit is None:
                self._ruhig_seit = self.sim.time
            done = (self._waiting_still and ruhig and self.sim.time - self._ruhig_seit >= RUHE_S
                    and self.sim.time - self._command_time >= .2)
            if done and self._ziel is not None:
                done = self._ankunft_pruefen()
            if done and self._erwartet == 'sitzt':
                done = self.sim.haltung == 'sitzt'
            elif done and self._erwartet in ('steht', 'pose'):
                done = self.sim.haltung == 'steht' and (
                    self._erwartet == 'steht' or self.sim.time - self._command_time >= self._haltung_rampe_s)
            if self._active is not None:
                status = ('sitzt' if self._erwartet == 'sitzt' else 'steht') if done else 'Physik laeuft'
                with self._lock:
                    self._feedback[self._active] = Feedback(bool(done), status)
        self._publish()
        # Maximal eine Sensorarbeit je Takt; Last erzeugt keinen Nachhol-Burst.
        try:
            fn, future = self._jobs.get_nowait()
        except queue.Empty:
            pass
        else:
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(fn())
                except Exception as exc:
                    future.set_exception(exc)
        if self._realtime:
            target = self._wall_start + self.sim.time - self._sim_start
            now = time.monotonic()
            if now > target + .1:
                self._wall_start += now - target
                target = now
            while not self._halt.is_set() and time.monotonic() < target:
                time.sleep(min(.005, max(0., target - time.monotonic())))

    def _zone_pruefen(self):
        """Eine Sperrzone haelt wie eine Wand -- nur mit dem Bremsweg gerechnet.

        Faehrt Spot auf eine Zone zu und laege er nach `ZONE_VORAUS_S` in ihrem
        Rand, geht ein Stopp an den Regler, und `angestossen` nennt die Zone wie in
        den anderen Uebungsraeumen. Heraus und entlang bleibt frei. Zaehlen muessen
        BEIDE Richtungen, die gemessene und die befohlene: beim Anlaufen schwingt der
        Koerper kurz nach vorn, und nah am Rand hielt sonst jeder Rueckwaertsbefehl.
        """
        from spotlab.welt.kollision import zone_im_weg

        x, y, gier = self._lage()
        vx, vy = (float(v) for v in self.sim.data.qvel[:2])
        sx, sy = self._soll
        wx = math.cos(gier) * sx - math.sin(gier) * sy
        wy = math.sin(gier) * sx + math.cos(gier) * sy
        t = ZONE_VORAUS_S
        zone = zone_im_weg(self._raum, (x, y), (x + vx * t, y + vy * t))
        if zone is None or zone_im_weg(self._raum, (x, y), (x + wx * t, y + wy * t)) != zone:
            return
        self._halte()
        self._deadline = None
        if self._recorder is not None:
            self._recorder.event('angestossen', x=round(x, 3), y=round(y, 3),
                                 hindernis=f'Sperrzone {zone}')
        if self._ziel is not None:
            self._ziel_beenden(f'vor Sperrzone {zone} angehalten, Ziel nicht erreicht ({self._rest()})')

    @staticmethod
    def _hat_pose(mob):
        from bosdyn.api.spot import robot_command_pb2 as sp

        params = sp.MobilityParams()
        mob.params.Unpack(params)
        punkte = params.body_control.base_offset_rt_footprint.points
        if not punkte:
            return False
        p = punkte[-1].pose
        return abs(p.position.z) > 1e-9 or any(abs(v) > 1e-9 for v in (p.rotation.x, p.rotation.y, p.rotation.z))

    def _lage(self):
        """(x, y, gier) des Koerpers im Weltrahmen -- in der Physik ist das odom."""
        q = self.sim.data.qpos
        gier = math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2))
        return float(q[0]), float(q[1]), gier

    def _halte(self):
        self.sim.send_command(RobotCommandBuilder.stop_command())
        self._waiting_still = True
        self._command_time = self.sim.time
        self._soll = (0., 0.)

    def _ziel_abstand(self):
        """(Strecke m, Winkelfehler rad) von der jetzigen Lage zum Ziel."""
        (zx, zy, zgier), _, _ = self._ziel
        x, y, gier = self._lage()
        return math.hypot(zx - x, zy - y), (zgier - gier + math.pi) % (2 * math.pi) - math.pi

    def _rest(self):
        strecke, winkel = self._ziel_abstand()
        return f'noch {strecke:.2f} m und {abs(math.degrees(winkel)):.0f} Grad'

    def _ziel_beenden(self, grund):
        """Ein move() endet ohne Ankunft: die Rueckmeldung sagt warum, und bleibt so."""
        with self._lock:
            if self._active is not None:
                self._feedback[self._active] = Feedback(False, grund, True)
        self._active = None
        self._ziel = None
        self._ziel_ruht = False

    def _ankunft_pruefen(self):
        """Spot steht nach einem move(): angekommen, nachsetzen oder ehrlich daneben."""
        strecke, winkel = self._ziel_abstand()
        if strecke <= ZIEL_M and abs(winkel) <= math.radians(ZIEL_GRAD):
            self._ziel = None
            return True
        if self._nachsetzen > 0:
            self._nachsetzen -= 1
            self._ziel_ruht = False
            self._waiting_still = False
            self._ziel_naechster = self.sim.time
            return False
        self._ziel_beenden(f'Ziel nach {ZIEL_NACHSETZEN + 1} Anlaeufen nicht erreicht ({self._rest()})')
        return False

    def _zum_ziel(self):
        """Ein Regelschritt: Gehbefehl im Koerperrahmen zum Ziel, oder Halt bei Ankunft.

        Proportional mit Mindesttempo (darunter kommt der Gang nicht voran) und
        den Deckeln aus `_ziel_aus`; nah am Ziel wird er von selbst langsam. Der
        Kraftregler bleibt unveraendert -- er bekommt nur Geschwindigkeiten.
        """
        (zx, zy, _), tempo_max, dreh_max = self._ziel
        self._ziel_naechster = self.sim.time + ZIEL_TAKT_S
        strecke, winkel = self._ziel_abstand()
        genug_nah = strecke <= ZIEL_M
        genug_gedreht = abs(winkel) <= math.radians(ZIEL_GRAD)
        if genug_nah and genug_gedreht:
            self._halte()
            self._ziel_ruht = True            # gezaehlt wird, wenn er steht: _ankunft_pruefen
            return
        x, y, gier = self._lage()
        vx = vy = wz = 0.
        if not genug_nah:
            tempo = min(tempo_max, max(ZIEL_V_MIN, ZIEL_K_V * strecke))
            dx, dy = zx - x, zy - y
            vx = (math.cos(gier) * dx + math.sin(gier) * dy) / strecke * tempo
            vy = (-math.sin(gier) * dx + math.cos(gier) * dy) / strecke * tempo
        if not genug_gedreht:
            wz = math.copysign(min(dreh_max, max(ZIEL_W_MIN, ZIEL_K_W * abs(winkel))), winkel)
        self.sim.send_command(RobotCommandBuilder.synchro_velocity_command(vx, vy, wz),
                              end_time_secs=self.sim.time + ZIEL_GUELTIG_S)
        self._soll = (vx, vy)

    def advance(self, seconds):
        """Deterministische Offline-Pruefung ohne Worker; Sekunden auf der Sim-Uhr."""
        if self._thread is not None:
            raise RuntimeError('advance nur ohne Worker verwenden.')
        self._tick()
        self.sim.run(seconds, on_tick=self._tick)

    def _run(self):
        try:
            while not self._halt.is_set():
                self._tick()
                self.sim.run(.01, on_tick=self._tick)
        except _Shutdown:
            pass
        except BaseException as exc:
            with self._lock:
                self._error = exc
        finally:
            self.sim.close()
            while not self._jobs.empty():
                _, future = self._jobs.get_nowait()
                if not future.done():
                    future.set_exception(SpotlabError('Physik-Worker beendet. Neu verbinden.'))

    def _call(self, function):
        self._check()
        if self._thread is None:
            return function()
        future = Future()
        self._jobs.put((function, future))
        try:
            return future.result(timeout=10)
        except TimeoutError as exc:
            future.cancel()
            raise SpotlabError('Sensorabfrage dauert zu lange. Physik-Lauf pruefen.') from exc

    def robot_state(self):
        with self._lock:
            self._check()
            state = type(self._state)()
            state.CopyFrom(self._state)
            return state

    def frame_tree_snapshot(self):
        return self.robot_state().kinematic_state.transforms_snapshot

    def qpos(self):
        with self._lock:
            return self._qpos.copy()

    def image_sources(self):
        return [n + suffix for n in self._sensorik.CAMERAS for suffix in ('_depth', '_fisheye_image')]

    def images(self, sources):
        def read():
            results = []
            for name in sources:
                if name not in self.image_sources():
                    raise UnsupportedCapability('Bildquelle fehlt; cameras() pruefen.')
                if name.endswith('_depth'):
                    results.append(self._sensorik.depth_image_proto(self.sim.sensors, name.removesuffix('_depth')))
                else:
                    results.append(self._sensorik.gray_image_proto(self.sim.sensors, name.removesuffix('_fisheye_image')))
            return results
        return self._call(read)

    def local_grid(self):
        from spotlab.backends.real.wahrnehmung import gitter_aus

        return self._call(lambda: gitter_aus(self.sim.local_grid()))

    def world_objects(self, kinds=None):
        """AprilTags mit derselben Sichtpruefung wie im Uebungsraum 3D.

        `SpotPuppe.sichtbare_tags` (Reichweite, Bild einer Graukamera, zugewandt,
        freier Strahl) rechnet hier auf dem Modell und Zustand der PHYSIK — im
        Physik-Faden, der allein `MjData` anfasst. Keine zweite Formulierung.
        """
        from spotlab.backends.base import Tag, richtung
        from spotlab.welt.wahrnehmung import TAG_REICHWEITE_M

        if kinds is not None and 'apriltag' not in kinds:
            return []

        def sehen():
            gefunden = []
            for marke, (dx, dy) in self._puppe.SpotPuppe.sichtbare_tags(
                    self._tagsicht, TAG_REICHWEITE_M):
                peilung, distanz = richtung(dx, dy)
                gefunden.append(Tag(
                    name=f'world_obj_apriltag_{marke.id:03d}', kind='apriltag',
                    bearing=peilung, distance=distanz, world_xy=(marke.x, marke.y),
                    time=self.uhr(), id=marke.id, filtered=False))
            return gefunden
        return self._call(sehen)

    def mobility_params(self, limits, nick_grad=0.0):
        return mobility.mit_grenze(limits)

    def safety_status(self):
        return SafetyStatus(None, None)

    def bericht(self):
        return {'hinweis': self.hinweis_zur_gueltigkeit(), 'physik': True,
                'regler': 'TerrainStepper' if self._terrain_steps else 'SpotSdkSim/TrotController',
                'terrain_source': 'scene_oracle' if self._terrain_steps else None,
                'sim_zeit_s': self._state.kinematic_state.acquisition_timestamp.seconds,
                'modell_masse_kg': float(self.model.body_subtreemass[self.model.body("body").id]),
                'kontakt_diagnostik': self.sim.stepper.contacts.report() if self._terrain_steps else None,
                'treppen_validiert': False}

    def close(self):
        if self._closed:
            return
        self._halt.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise SpotlabError('Physik-Worker beendet sich nicht. Prozess stoppen.')
        else:
            self.sim.close()
        if self._ansicht is not None:
            self._ansicht.beenden()
        self._powered = False
        self._closed = True
