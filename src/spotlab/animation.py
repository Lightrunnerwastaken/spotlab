"""Zeitliche Zwischenbilder fuer die Anzeige; veraendert keine Messdaten."""

import threading
from collections import deque

ANZEIGE_VERZUG_S = 0.12


def linear(a, b, anteil):
    return tuple(x + (y - x) * anteil for x, y in zip(a, b))


class Zeitpuffer:
    """Begrenzte, kopierte Posen. Bei Datenluecken halten statt extrapolieren."""

    def __init__(self, mische=linear):
        self._proben = deque(maxlen=128)
        self._sperre = threading.Lock()
        self._mische = mische

    def anhaengen(self, t, werte):
        probe = (float(t), tuple(werte))
        with self._sperre:
            if self._proben and t < self._proben[-1][0]:
                return
            if self._proben and t == self._proben[-1][0]:
                self._proben.pop()
            self._proben.append(probe)

    def leeren(self):
        with self._sperre:
            self._proben.clear()

    def bei(self, t):
        with self._sperre:
            if not self._proben:
                return None
            if t <= self._proben[0][0]:
                return self._proben[0][1]
            for (ta, a), (tb, b) in zip(self._proben, list(self._proben)[1:]):
                if t <= tb:
                    return self._mische(a, b, (t - ta) / (tb - ta))
            return self._proben[-1][1]

    def fertig(self, t):
        with self._sperre:
            return not self._proben or t >= self._proben[-1][0]
