"""Das Messfenster-Protokoll — an genau einer Stelle.

Herausgelöst aus `api/spot.py`, weil die Logik nur an Recorder und Abtaster
hängt und nicht am Roboter: der Beobachter-Modus (`beobachtung/session.py`)
kommandiert nichts und braucht trotzdem dasselbe Protokoll. Zwei Formulierungen
davon hiessen, dass `messung/fenster.py` bald zwei leicht verschiedene
Fensterprotokolle lesen muss — und die Auswertung merkt so etwas erst, wenn die
Messfahrt vorbei ist.
"""

import contextlib
import math

from spotlab.errors import SpotlabError

# `name` fehlt hier absichtlich: es ist ein Positionsparameter von oeffne(),
# und Python weist ein doppeltes `name=` schon mit einer klaren Meldung ab.
RESERVIERT = ("phase", "hz_soll")


def _rate(hz):
    """`hz` als float > 0 -- sonst SpotlabError, BEVOR irgendetwas umgeschaltet ist.

    `hz=0` teilte im Abtaster durch null, `hz=-5` liess ihn ohne Pause laufen
    (Beta-Pruefung 23.09.2026).
    """
    try:
        zahl = float(hz)
    except (TypeError, ValueError):
        zahl = math.nan
    if not math.isfinite(zahl) or zahl <= 0.0:
        raise SpotlabError(
            f"Messfenster: hz={hz!r} ist keine Abtastrate. Gemeint ist eine Zahl über 0 "
            "in Hertz, zum Beispiel hz=50."
        )
    return zahl


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
        hz = _rate(hz)

        self._offen = name
        vorher = self._sampler.takt() if self._sampler is not None else None
        # Erst umschalten, dann das Startereignis schreiben: das Ereignis ist
        # die Abschnittsgrenze des Lueckenmelders. Staende es VOR dem
        # Umschalten, koennte eine Abtastung nach der Grenze noch den alten
        # Takt schlafen, und der zaehlte als Luecke im Fenster.
        try:
            if self._sampler is not None:
                self._sampler.setze_takt(hz, reich)
            if self._recorder is not None:
                self._recorder.event(
                    "messfenster", phase="start", name=name, hz_soll=hz, **felder
                )
        except BaseException:
            # Scheitert schon das Oeffnen, ist das Fenster NICHT offen: sonst
            # scheiterte jedes weitere an „schon offen“ (Beta-Pruefung p11).
            if self._sampler is not None and vorher is not None:
                self._sampler.setze_takt(*vorher)
            self._offen = None
            raise
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
