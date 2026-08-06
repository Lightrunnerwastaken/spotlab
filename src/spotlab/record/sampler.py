"""10-Hz-Abtastung des Roboterzustands in einem Hintergrund-Thread.

Läuft unabhängig davon, was das Schülerskript tut — auch ein Skript, das nur
wartet, produziert damit verwertbare Messdaten für die Sim-Kalibrierung.
"""

import threading
import time

from spotlab.api.state import as_sample


class StateSampler:
    def __init__(self, backend, recorder, hz=10.0):
        self._backend = backend
        self._recorder = recorder
        self._periode = 1.0 / float(hz)
        self._stopp = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._schleife, name="spotlab-sampler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=2.0):
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            try:
                self._recorder.sample(as_sample(self._backend.robot_state()))
            except Exception:  # Abtastung darf den Lauf nie kippen
                self._stopp.wait(self._periode)
                continue
            rest = self._periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
