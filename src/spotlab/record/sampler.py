"""10-Hz-Abtastung des Roboterzustands in einem Hintergrund-Thread.

Läuft unabhängig davon, was das Schülerskript tut — auch ein Skript, das nur
wartet, produziert damit verwertbare Messdaten für die Sim-Kalibrierung.

Zweite Aufgabe: der Thread ist der Zustellweg für den freundlichen Stopp der
GUI. Er prüft bei jedem Takt, ob <lauf>/stopp angelegt wurde, und löst dann
KeyboardInterrupt im Hauptthread aus — also genau den Abbruchpfad, den
connect() bereits behandelt.

Grenze, die den harten Not-Aus begründet: _thread.interrupt_main() wirkt erst,
wenn der Hauptthread wieder Python-Bytecode ausführt. Hängt er in einem
blockierenden gRPC-Aufruf, kommt der Abbruch verzögert oder gar nicht an.
"""

import _thread
import threading
import time

from spotlab.api.state import as_sample
from spotlab.record.run import STOPP_DATEI


class StateSampler:
    def __init__(self, backend, recorder, hz=10.0):
        self._backend = backend
        self._recorder = recorder
        self._takt_sperre = threading.Lock()
        self._hz = float(hz)
        self._periode = 1.0 / self._hz
        self._reich = False
        self._stopp = threading.Event()
        self._thread = None
        self._stopp_datei = recorder.dir / STOPP_DATEI
        self._abbruch_gemeldet = False

    def setze_takt(self, hz, reich):
        """Wirkt ab dem nächsten Tick. Vom Messfenster gerufen."""
        with self._takt_sperre:
            self._hz = float(hz)
            self._periode = 1.0 / self._hz
            self._reich = bool(reich)

    def takt(self):
        with self._takt_sperre:
            return self._hz, self._reich

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

    def _pruefe_stopp(self):
        """Genau einmal auslösen — sonst regnet es KeyboardInterrupts in den Abbau."""
        if self._abbruch_gemeldet:
            return
        try:
            vorhanden = self._stopp_datei.exists()
        except OSError:
            return
        if vorhanden:
            self._abbruch_gemeldet = True
            _thread.interrupt_main()

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            with self._takt_sperre:
                periode, reich = self._periode, self._reich
            self._pruefe_stopp()
            try:
                self._recorder.sample(as_sample(self._backend.robot_state(), reich=reich))
            except Exception:  # Abtastung darf den Lauf nie kippen
                self._stopp.wait(periode)
                continue
            # Nichts nachholen: dauert die RPC länger als die Periode, läuft die
            # Schleife eben langsamer. Nachholen erzeugte Bursts, die in der
            # Auswertung wie echte Dynamik aussehen.
            rest = periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
