"""Quantitative Wahrnehmung fuer eigene Python-Skripte."""
from uuid import uuid4

from spotlab.backends import sensor_access


def _record(spot, name, data):
    if spot.recorder is not None:
        target = spot.recorder.dir / 'sensoren' / (name + '_' + uuid4().hex + '.npz')
        data.save(target)
        spot.recorder.event('kommando', name=name, datei=str(target.relative_to(spot.recorder.dir)),
                            t_robot=data.time, frame=data.frame)
    return data


def depth(spot, name):
    return _record(spot, 'depth', sensor_access.depth(spot.backend, name))


def point_cloud(spot, name, frame, stride, min_distance, max_distance):
    # Convert exactly the fetched capture, including its acquisition-time transforms.
    return depth(spot, name).point_cloud(frame, stride, min_distance, max_distance)


def grid_types(spot):
    return sensor_access.grid_types(spot.backend, spot.robot)


def local_grid(spot, name):
    return _record(spot, 'local_grid', sensor_access.local_grid(spot.backend, spot.robot, name))
