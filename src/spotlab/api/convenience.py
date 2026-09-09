"""Benannte Koerperrichtungen statt Weltkoordinaten fuer LocalGrid-Abfragen."""

import math
from dataclasses import dataclass

from bosdyn.client.frame_helpers import BODY_FRAME_NAME, VISION_FRAME_NAME, get_a_tform_b

from spotlab.api.world import obstacles
from spotlab.errors import SpotlabError


def zahl(value, name, low, high):
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} muss eine Zahl sein.') from exc
    if not math.isfinite(n) or not low <= n <= high:
        raise ValueError(f'{name} muss zwischen {low} und {high} liegen.')
    return n


@dataclass(frozen=True)
class Direction:
    """Ein gepruefter Strahl; unbekannt ist keine freie Strecke."""
    status: str                 # clear, blocked, unknown
    distance: float | None      # Meter ab Koerpermitte; None bei unbekannt
    observed_distance: float   # Ende des lueckenlos geprueften Abschnitts
    start: float               # Beginn der Pruefung; davor keine Aussage

    @property
    def known(self):
        return self.status != 'unknown'


@dataclass(frozen=True)
class Surroundings:
    grid: object
    position: tuple
    heading: float
    max_distance: float
    margin: float
    start: float

    def direction(self, angle=0.0):
        """Relativer Winkel in Grad: 0 vorwaerts, +90 links; keine Fahrfreigabe."""
        angle = zahl(angle, 'angle', -360, 360)
        rad = math.radians(self.heading + angle)
        x, y = self.position
        schritt = max(.01, float(self.grid.cell_size) / 2)
        anzahl = max(1, math.ceil((self.max_distance - self.start) / schritt))
        letzte = self.start
        for i in range(anzahl + 1):
            strecke = self.start + (self.max_distance - self.start) * i / anzahl
            abstand = self.grid.distance_at(x + strecke * math.cos(rad), y + strecke * math.sin(rad))
            if abstand is None or not math.isfinite(abstand):
                return Direction('unknown', None, letzte, self.start)
            if abstand < self.margin:
                return Direction('blocked', strecke, letzte, self.start)
            letzte = strecke
        return Direction('clear', self.max_distance, self.max_distance, self.start)

    @property
    def front(self):
        return self.direction(0)

    @property
    def left(self):
        return self.direction(90)

    @property
    def right(self):
        return self.direction(-90)

    @property
    def back(self):
        return self.direction(180)


def look(backend, recorder, max_distance=1.8, margin=.3, start=0.0):
    max_distance = zahl(max_distance, 'max_distance', .01, 10)
    margin = zahl(margin, 'margin', .01, 2)
    start = zahl(start, 'start', 0, max_distance)
    grid = obstacles(backend, recorder)
    # ObstacleGrid verwendet vision (Real-Wahrnehmung); im Sim ist vision=odom.
    # Nicht state.pose verwenden: die ist odom und kann am echten Spot abweichen.
    tf = get_a_tform_b(backend.frame_tree_snapshot(), VISION_FRAME_NAME, BODY_FRAME_NAME)
    if tf is None:
        raise SpotlabError('Kein vision/body-Rahmen fuer das Hindernisgitter vorhanden.')
    q = tf.rotation
    yaw = math.atan2(2 * (q.w*q.z + q.x*q.y), 1 - 2 * (q.y*q.y + q.z*q.z))
    ansicht = Surroundings(grid, (tf.x, tf.y), math.degrees(yaw), max_distance, margin, start)
    if recorder is not None:
        recorder.event('kommando', name='look', max_distance=max_distance, margin=margin, start=start,
                       status={n: getattr(ansicht, n).status for n in ('front', 'left', 'right', 'back')})
    return ansicht
