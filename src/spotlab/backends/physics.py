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

HINWEIS = ('Experimenteller Physikmodus: eigener Fussplaner, kein Boston-Dynamics-Regler. '
           'Start im Stand; bisher ebener Boden. Sitzen, move-Zieltrajektorien, '
           'Treppen und Koerperpose noch nicht unterstuetzt. Keine Realismusfreigabe.')

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


class _Shutdown(BaseException):
    pass


class PhysicsBackend:
    def __init__(self, recorder=None, raum=None, start=None, ansicht_ziel=None,
                 realtime=True, autostart=True):
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
        self.sim = simulator(szene=(model, data, data.ctrl.copy()))
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
        return HINWEIS

    def treppengang(self):
        return None

    def _check(self):
        if self._error is not None:
            raise SpotlabError(f'Physik-Simulation angehalten: {self._error}') from self._error
        if self._closed:
            raise SpotlabError('Physik-Sitzung ist beendet. Neu verbinden.')

    def power_on(self):
        with self._lock:
            self._check()
            self._powered = True

    def power_off(self, safe=True):
        # Nur die virtuelle Kommandofreigabe: kein vorgetaeuschtes Hinsetzen.
        with self._lock:
            if not self._closed:
                self._pending = ('off', RobotCommandBuilder.stop_command(), None)
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
        if not (stop or velocity or stand):
            raise UnsupportedCapability('Physik v1 unterstuetzt stand(), walk() und stop(). '
                                        'Sitzen und move() sind noch nicht implementiert.')
        params = sp.MobilityParams()
        mob.params.Unpack(params)
        if params.locomotion_hint not in (sp.HINT_UNKNOWN, sp.HINT_AUTO, sp.HINT_TROT):
            raise UnsupportedCapability('Physik v1 verwendet den kontinuierlichen Trab-Regler; HINT_AUTO waehlen.')
        if params.body_control.base_offset_rt_footprint.points:
            pose = params.body_control.base_offset_rt_footprint.points[-1].pose
            if abs(pose.position.z) > 1e-9 or any(abs(v) > 1e-9 for v in
                                                (pose.rotation.x, pose.rotation.y, pose.rotation.z)):
                raise UnsupportedCapability('Physik v1 unterstuetzt nur die neutrale Standhoehe und Orientierung.')
        if velocity:
            req = mob.se2_velocity_request
            if req.se2_frame_name != 'body':
                raise UnsupportedCapability('Physik v1 braucht Geschwindigkeiten im body-Rahmen.')
            values = (req.velocity.linear.x, req.velocity.linear.y, req.velocity.angular)
            if not all(math.isfinite(v) for v in values):
                raise ValueError('Geschwindigkeiten muessen endlich sein.')
            jetzt = self.uhr()
            if end_time_secs is None or not math.isfinite(end_time_secs) or end_time_secs <= jetzt:
                raise CommandRejected('Velocity braucht eine gueltige absolute Ablaufzeit.')
            if not self._realtime and end_time_secs > jetzt + ZU_WEIT_S:
                raise CommandRejected('Ohne Echtzeit laeuft die Ablaufzeit auf der Sim-Uhr: '
                                      'end_time_secs=backend.uhr() + Dauer, nicht time.time() + Dauer '
                                      '(motion.walk: wanduhr=backend.uhr).')
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
        with self._lock:
            self._check()
            if not self._powered and not stop:
                raise NotPowered('Kommandofreigabe aus: zuerst power_on() aufrufen.')
            key = str(next(self._ids))
            if self._pending is not None:
                self._feedback[self._pending[0]] = Feedback(False, 'durch neues Kommando ersetzt', True)
            self._feedback[key] = Feedback(False, 'wartet auf Physiktakt')
            self._pending = (key, copy, end_time_secs)
            return key

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
            key, command, deadline = pending
            if self._active is not None:
                with self._lock:
                    if not self._feedback[self._active].done:
                        self._feedback[self._active] = Feedback(False, 'ersetzt', True)
            expiry = self.sim.time + max(0., deadline - self.uhr()) if deadline else None
            self.sim.send_command(command, end_time_secs=expiry)
            self._active = key if key != 'off' else None
            self._deadline = deadline
            self._command_time = self.sim.time
            self._waiting_still = (command.full_body_command.HasField('stop_request')
                                   or command.synchronized_command.mobility_command.HasField('stand_request'))
            soll = command.synchronized_command.mobility_command.se2_velocity_request.velocity
            self._soll = (0., 0.) if self._waiting_still else (soll.linear.x, soll.linear.y)
        if self._deadline is not None and self.uhr() >= self._deadline:
            self.sim.send_command(RobotCommandBuilder.stop_command())
            self._deadline = None
            self._waiting_still = True
        if not self._waiting_still and self._raum is not None:
            self._zone_pruefen()
        if self.sim.metrics.fell:
            raise SpotlabError('Regler meldet einen Sturz; Versuch beendet. Lauf auswerten und neu starten.')
        if self._active is not None:
            still = np.linalg.norm(self.sim.data.qvel[:2]) < .04 and np.linalg.norm(self.sim.data.qvel[3:6]) < .15
            done = (self._waiting_still and still and not getattr(self.sim, "in_step", False)
                    and self.sim.time - self._command_time >= .2)
            with self._lock:
                self._feedback[self._active] = Feedback(bool(done), 'steht' if done else 'Physik laeuft')
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

        q = self.sim.data.qpos
        x, y = float(q[0]), float(q[1])
        gier = math.atan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2))
        vx, vy = (float(v) for v in self.sim.data.qvel[:2])
        sx, sy = self._soll
        wx = math.cos(gier) * sx - math.sin(gier) * sy
        wy = math.sin(gier) * sx + math.cos(gier) * sy
        t = ZONE_VORAUS_S
        zone = zone_im_weg(self._raum, (x, y), (x + vx * t, y + vy * t))
        if zone is None or zone_im_weg(self._raum, (x, y), (x + wx * t, y + wy * t)) != zone:
            return
        self.sim.send_command(RobotCommandBuilder.stop_command())
        self._deadline = None
        self._waiting_still = True
        self._command_time = self.sim.time
        if self._recorder is not None:
            self._recorder.event('angestossen', x=round(x, 3), y=round(y, 3),
                                 hindernis=f'Sperrzone {zone}')

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
