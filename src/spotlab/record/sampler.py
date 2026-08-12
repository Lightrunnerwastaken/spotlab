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
import collections
import threading
import time

from spotlab.api.state import as_sample
from spotlab.record.run import STOPP_DATEI

# Ring der zuletzt geschriebenen Abtastungen, aus dem die Live-Anzeige des
# Beobachter-Modus liest. Begrenzt nach ANZAHL, ausgewertet wird nach ZEIT —
# sonst hinge die Fensterlänge der Live-Zahl an der gerade eingestellten Rate.
RING = 512


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
        self._ring = collections.deque(maxlen=RING)
        self._ring_sperre = threading.Lock()

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

    def _warte(self, sekunden):
        """Warten — genau, und trotzdem auf den Stopp reagierend.

        NICHT `self._stopp.wait(sekunden)`. Das geht unter Windows über den
        groben Zeitgeber mit 15.6 ms Auflösung: 20 ms angefordert werden zu
        31 ms geliefert, aus 50 Hz werden 32. `time.sleep()` nutzt seit
        Python 3.11 hochauflösende Timer und liefert 20.4 ms.

        Gemessen am 12.08.2026 auf dem Schullaptop, voller Takt nachgestellt:
        34.0 Hz mit `Event.wait`, 49.0 Hz mit `time.sleep`. Die reale Messfahrt
        am selben Tag kam auf 34.1 Hz — die Grenze war also nie das WLAN oder
        der Roboter, sondern diese eine Zeile. Bei einer Schwungphase von rund
        einer Viertelsekunde ist das der Unterschied zwischen acht und zwölf
        Stützstellen, und daran hängt, ob sich aus den Gelenkdaten Dynamik
        rechnen lässt.

        In Stücken schlafen, damit ein Stopp trotzdem binnen 20 ms greift statt
        erst nach einer vollen 10-Hz-Periode.
        """
        ende = time.monotonic() + sekunden
        while not self._stopp.is_set():
            rest = ende - time.monotonic()
            if rest <= 0:
                return
            time.sleep(min(rest, 0.02))

    def verlauf(self):
        """Kopie der zuletzt geschriebenen Abtastungen, älteste zuerst.

        Quelle der Live-Anzeige im Beobachter-Modus. Sie liest mit, statt selbst
        abzufragen: ein zweiter Abfragestrom wäre eine zweite Wahrheit über
        denselben Roboter und würde die Messung stören, um die es geht.
        """
        with self._ring_sperre:
            return tuple(self._ring)

    def _einmal(self, reich=False):
        """Eine Abtastung holen, schreiben, in den Ring legen.

        Gibt zurück, ob es geklappt hat. Eine fehlgeschlagene Abtastung darf den
        Lauf nie kippen — und sie darf auch nicht im Ring landen, sonst zeigte
        die Live-Anzeige eine Zahl aus einer Abtastung, die es nie gab.
        """
        try:
            satz = as_sample(self._backend.robot_state(), reich=reich)
        except Exception:
            return False
        self._recorder.sample(satz)
        with self._ring_sperre:
            self._ring.append(satz)
        return True

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            with self._takt_sperre:
                periode, reich = self._periode, self._reich
            self._pruefe_stopp()
            if not self._einmal(reich):
                self._warte(periode)
                continue
            # Nichts nachholen: dauert die RPC länger als die Periode, läuft die
            # Schleife eben langsamer. Nachholen erzeugte Bursts, die in der
            # Auswertung wie echte Dynamik aussehen.
            rest = periode - (time.monotonic() - beginn)
            if rest > 0:
                self._warte(rest)
