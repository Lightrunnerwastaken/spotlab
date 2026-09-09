"""Read-only sensor access; no changes to reconstruction or robot commands."""
from dataclasses import replace

import numpy as np

from spotlab.backends.base import Capability, require
from spotlab.backends.sensor_data import GridLayer, depth_from_response, grid_from_response
from spotlab.errors import SpotlabError, UnsupportedCapability


def depth(backend, name):
    require(backend, Capability.DEPTH_CAMERAS, 'Tiefenbilder lesen')
    sources = backend.image_sources()
    candidate = name if name in sources else name + '_depth'
    if candidate not in sources:
        raise UnsupportedCapability(f'Tiefenquelle {name!r} fehlt. Gemeldete Quellen: {sources}')
    responses = backend.images([candidate])
    if len(responses) != 1 or responses[0].source.name != candidate:
        raise SpotlabError('Tiefenquelle fehlt in der Antwort. Erneut aufnehmen.')
    return depth_from_response(responses[0])


def grid_types(backend, robot):
    require(backend, Capability.LOCAL_GRID, 'LocalGrid lesen')
    if robot is None:
        return ['obstacle_distance']
    return [entry.name for entry in robot.ensure_client('local-grid-service').get_local_grid_types()]


def local_grid(backend, robot, name):
    require(backend, Capability.LOCAL_GRID, 'LocalGrid lesen')
    if robot is None:
        if name != 'obstacle_distance':
            raise UnsupportedCapability('Dieses Backend liefert nur obstacle_distance. grid_types() verwenden.')
        grid = backend.local_grid()
        values = np.array(grid.cells, dtype=float, copy=True)
        known = np.isfinite(values)
        if grid.known is not None:
            known &= grid.known
        values[~known] = np.nan
        transform = np.eye(4)
        transform[:2, 3] = np.asarray(grid.origin) - grid.cell_size / 2
        return GridLayer(name, values, known, grid.cell_size, 'spotlab_grid', grid.time,
                         {'spotlab_grid': np.eye(4), 'vision': transform}, 'm')
    client = robot.ensure_client('local-grid-service')
    requested = [name, 'terrain_valid'] if name == 'terrain' else [name]
    responses = client.get_local_grids(requested)
    by_name = {r.local_grid_type_name or r.local_grid.local_grid_type_name: r for r in responses}
    if any(n not in by_name for n in requested):
        raise SpotlabError('LocalGrid-Antwort unvollstaendig. grid_types() pruefen und erneut lesen.')
    layer = grid_from_response(by_name[name])
    if name == 'terrain':
        valid = grid_from_response(by_name['terrain_valid'])
        same = (layer.values.shape == valid.values.shape and layer.cell_size == valid.cell_size
                and layer.time == valid.time and 'vision' in layer.transforms
                and 'vision' in valid.transforms
                and np.allclose(layer.transforms['vision'], valid.transforms['vision'], atol=1e-8, rtol=0))
        if not same:
            raise SpotlabError('terrain und terrain_valid passen zeitlich/raeumlich nicht zusammen. Erneut lesen.')
        known = layer.known & valid.known & (valid.values > 0)
        layer = replace(layer, known=known, values=np.where(known, layer.values, np.nan))
    return layer
