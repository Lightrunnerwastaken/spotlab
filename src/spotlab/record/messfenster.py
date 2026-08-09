"""Das Messfenster-Protokoll — an genau einer Stelle.

Herausgelöst aus `api/spot.py`, weil die Logik nur an Recorder und Abtaster
hängt und nicht am Roboter: der Beobachter-Modus (`beobachtung/session.py`)
kommandiert nichts und braucht trotzdem dasselbe Protokoll. Zwei Formulierungen
davon hiessen, dass `messung/fenster.py` bald zwei leicht verschiedene
Fensterprotokolle lesen muss — und die Auswertung merkt so etwas erst, wenn die
Messfahrt vorbei ist.
"""

import contextlib

from spotlab.errors import SpotlabError

# `name` fehlt hier absichtlich: es ist ein Positionsparameter von oeffne(),
# und Python weist ein doppeltes `name=` schon mit einer klaren Meldung ab.
RESERVIERT = ("phase", "hz_soll")


class Messfenster:
    """Schreibt die Fenstermarken und schaltet die Abtastung dichter.

    `recorder` und `sampler` dürfen None sein — Tests bauen `Spot` so, und ein
    Fenster ohne Aufzeichnung ist kein Fehler, sondern einfach wirkungslos.
    """

    def __init__(self, recorder, sampler):
        self._recorder = recorder
        self._sampler = sampler
        self._offen = None

    @property
    def offen(self):
        """Name des offenen Fensters, oder None."""
        return self._offen

    @contextlib.contextmanager
    def oeffne(self, name, hz=50.0, reich=True, **felder):
        doppelt = [k for k in RESERVIERT if k in felder]
        if doppelt:
            raise SpotlabError(
                f"Die Feldnamen {', '.join(doppelt)} sind im Messfenster belegt. "
                "Nimm einen anderen Namen."
            )
        if self._offen is not None:
            raise SpotlabError(
                f"Es ist schon ein Messfenster offen: „{self._offen}“. "
                "Verschachtelte Fenster wären in der Auswertung nicht "
                "auseinanderzuhalten."
            )

        self._offen = name
        vorher = self._sampler.takt() if self._sampler is not None else None
        if self._recorder is not None:
            self._recorder.event(
                "messfenster", phase="start", name=name, hz_soll=hz, **felder
            )
        if self._sampler is not None:
            self._sampler.setze_takt(hz, reich)
        try:
            yield
        finally:
            # Ohne finally bliebe der Lauf nach einer Ausnahme für immer auf
            # 50 Hz und das Fenster ohne Ende.
            if self._sampler is not None and vorher is not None:
                self._sampler.setze_takt(*vorher)
            if self._recorder is not None:
                self._recorder.event("messfenster", phase="ende", name=name, **felder)
            self._offen = None
