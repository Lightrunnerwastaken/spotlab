"""Fluessiger Spot-Marker im Live-Fenster, die aufgezeichnete Spur bleibt exakt."""

import time

from PySide6.QtCore import Qt, QTimer

from spotlab.animation import ANZEIGE_VERZUG_S, Zeitpuffer, linear
from spotlab.gui.raumplot import RaumPlot


def _mische_pose(a, b, anteil):
    x, y = linear(a[:2], b[:2], anteil)
    drehung = (b[2] - a[2] + 180) % 360 - 180
    return x, y, a[2] + drehung * anteil


class LiveRaumPlot(RaumPlot):
    def __init__(self, palette, parent=None, jetzt=time.monotonic):
        super().__init__(palette, parent)
        self._jetzt = jetzt
        self._posen = Zeitpuffer(_mische_pose)
        self._animation = QTimer(self)
        self._animation.setTimerType(Qt.PreciseTimer)
        self._animation.setInterval(16)
        self._animation.timeout.connect(self._bild)

    def setze_start(self, pose):
        self._posen.leeren()
        self._animation.stop()
        super().setze_start(pose)

    def haenge_pose_an(self, x, y, grad=None):
        super().haenge_pose_an(x, y, grad)
        self._posen.anhaengen(self._jetzt(), (x, y, self._blick))
        if not self._animation.isActive():
            self._animation.start()

    def anzeigepose(self):
        pose = self._posen.bei(self._jetzt() - ANZEIGE_VERZUG_S)
        return pose if pose is not None else super().anzeigepose()

    def _bild(self):
        self.update()
        if self._posen.fertig(self._jetzt() - ANZEIGE_VERZUG_S):
            self._animation.stop()
