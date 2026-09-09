"""Faehigkeiten der Komfort-API, ohne einen Sim-Erfolg vorzutäuschen."""

from spotlab.backends.base import Capability
from spotlab.backends.dryrun import DryRunBackend


def supports(spot, feature):
    """AV-Dienst wird beim expliziten Abfragen gelesen; Netzfehler bleiben Fehler."""
    if feature in ('lights', 'beep'):
        if isinstance(spot.backend, DryRunBackend):
            return True
        if spot.robot is None:
            return False
        return any(d.name == 'audio-visual' for d in spot.robot.list_services())
    if feature == 'pose':
        return spot.robot is not None or isinstance(spot.backend, DryRunBackend)
    gruppen = {'depth': Capability.DEPTH_CAMERAS, 'point_cloud': Capability.DEPTH_CAMERAS,
               'local_grid': Capability.LOCAL_GRID, 'grid_types': Capability.LOCAL_GRID,
               'look': Capability.LOCAL_GRID, 'camera': Capability.CAMERAS,
               'tags': Capability.WORLD_OBJECTS, 'stairs': Capability.STAIRS,
               'navigate_to': Capability.GRAPH_NAV}
    if feature not in gruppen:
        raise ValueError('Unbekannte Faehigkeit. Erlaubt: lights, beep, pose, ' + ', '.join(gruppen))
    return bool(spot.backend.capabilities() & gruppen[feature])
