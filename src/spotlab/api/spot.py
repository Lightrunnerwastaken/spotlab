"""Die Fassade, die ein Schüler sieht.

Die Abkürzung ist keine Mauer: `spot.robot` und `spot.send()` führen jederzeit
zum vollen SDK — ohne Lease, Not-Aus und Aufzeichnung aufzugeben.
"""

from spotlab.api import motion, perception, posture
from spotlab.api.state import from_proto
from spotlab.config import Limits


class Spot:
    def __init__(self, backend, recorder=None, limits=None, robot=None):
        self.backend = backend
        self.recorder = recorder
        self.limits = limits or Limits()
        self._robot = robot

    # ------------------------------------------------------------ Leistung

    def power_on(self):
        self.backend.power_on()
        if self.recorder is not None:
            self.recorder.event("power_on")

    def power_off(self, safe=True):
        self.backend.power_off(safe=safe)
        if self.recorder is not None:
            self.recorder.event("power_off", safe=safe)

    @property
    def is_powered(self):
        return self.backend.is_powered

    @property
    def battery(self):
        return self.state.battery

    # ------------------------------------------------------------ Haltung

    def stand(self, height=0.0, timeout=10.0, schlaf=None):
        posture.stand(
            self.backend,
            self.recorder,
            height=height,
            timeout=timeout,
            **({"schlaf": schlaf} if schlaf else {}),
        )

    def sit(self, timeout=10.0, schlaf=None):
        posture.sit(
            self.backend,
            self.recorder,
            timeout=timeout,
            **({"schlaf": schlaf} if schlaf else {}),
        )

    # ------------------------------------------------------------ Bewegung

    def move(self, forward=0.0, left=0.0, turn=0.0, timeout=30.0):
        motion.move(
            self.backend,
            self.recorder,
            self.limits,
            forward=forward,
            left=left,
            turn=turn,
            timeout=timeout,
        )

    def walk(self, vx=0.0, vy=0.0, wz=0.0, duration=1.0):
        motion.walk(
            self.backend, self.recorder, self.limits, vx=vx, vy=vy, wz=wz, duration=duration
        )

    def stop(self):
        motion.stop(self.backend, self.recorder)

    # ------------------------------------------------------------ Wahrnehmung

    def cameras(self):
        return perception.cameras(self.backend)

    def camera(self, name):
        return perception.camera(self.backend, self.recorder, name)

    @property
    def state(self):
        return from_proto(self.backend.robot_state())

    # ------------------------------------------------------------ Rohzugang

    @property
    def robot(self):
        """Das rohe bosdyn-Robot-Objekt (None im Trockenlauf)."""
        return self._robot

    def send(self, command, end_time_secs=None):
        if self.recorder is not None:
            self.recorder.event("kommando", name="send", roh=True)
        return self.backend.send_command(command, end_time_secs=end_time_secs)

    def close(self):
        self.backend.close()
