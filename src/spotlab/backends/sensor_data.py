"""Quantitative Sensordaten; SDK-Dekodierung bleibt unterhalb der API."""
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from spotlab.errors import SpotlabError


def _positive(value, name):
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f'{name} muss endlich und positiv sein.')
    return float(value)


def _save(path, **data):
    path = Path(path)
    if path.suffix.lower() != '.npz':
        raise ValueError('Bitte eine Datei mit Endung .npz angeben.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        np.savez_compressed(stream, **data)
    return path


def _transforms(snapshot, source):
    from bosdyn.client.frame_helpers import get_a_tform_b

    matrices = {source: np.eye(4)}
    for target in ('body', 'vision', 'odom'):
        if target == source:
            continue
        # Missing frames are allowed on capture; requesting one later is explicit.
        if source in snapshot.child_to_parent_edge_map and target in snapshot.child_to_parent_edge_map:
            pose = get_a_tform_b(snapshot, target, source)
            if pose is not None:
                matrices[target] = np.asarray(pose.to_matrix())
    return matrices


@dataclass(frozen=True)
class PointCloud:
    points: object
    frame: str
    time: float
    source: str

    def save(self, path):
        """NPZ mit Metadaten oder ASCII-PLY in Metern."""
        path = Path(path)
        if path.suffix.lower() == '.ply':
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8', newline='\n') as stream:
                stream.write(f'ply\nformat ascii 1.0\ncomment frame {self.frame}\n'
                             f'comment acquisition_time {self.time}\n'
                             f'element vertex {len(self.points)}\nproperty double x\n'
                             'property double y\nproperty double z\nend_header\n')
                np.savetxt(stream, self.points, fmt='%.9g')
            return path
        return _save(path, points=self.points, frame=self.frame, time=self.time, source=self.source)


@dataclass(frozen=True)
class DepthImage:
    raw: object
    meters: object
    valid: object
    intrinsics: object
    depth_scale: float
    frame: str
    time: float
    source: str
    transforms: dict

    def distance_at(self, column, row):
        """Axiale Tiefe in Metern, None bei unbekannt oder ausserhalb."""
        if not isinstance(column, (int, np.integer)) or not isinstance(row, (int, np.integer)):
            raise ValueError('Pixelkoordinaten muessen ganze Zahlen sein.')
        if not (0 <= row < self.raw.shape[0] and 0 <= column < self.raw.shape[1]):
            return None
        return float(self.meters[row, column]) if self.valid[row, column] else None

    def point_cloud(self, frame='body', stride=2, min_distance=0.0, max_distance=5.0):
        """Punkte in Metern aus dieser Aufnahme; Filter auf axiale Kameratiefe."""
        if isinstance(stride, bool) or not isinstance(stride, int) or stride < 1:
            raise ValueError('stride muss eine positive ganze Zahl sein.')
        if not math.isfinite(float(min_distance)) or min_distance < 0:
            raise ValueError('min_distance muss endlich und nicht negativ sein.')
        maximum = _positive(max_distance, 'max_distance')
        if maximum <= min_distance:
            raise ValueError('max_distance muss groesser als min_distance sein.')
        target = self.frame if frame == 'sensor' else frame
        if target not in self.transforms:
            raise SpotlabError(f'Rahmen {target!r} fehlt in der Aufnahme. Nutze frame="sensor" oder eine Aufnahme mit Rahmenbaum.')
        z = self.meters[::stride, ::stride]
        valid = self.valid[::stride, ::stride] & (z > min_distance) & (z < maximum)
        v, u = np.nonzero(valid)
        z = z[v, u]
        pixels = np.column_stack((u * stride, v * stride, np.ones(len(u))))
        rays = pixels @ np.linalg.inv(self.intrinsics).T
        points = rays * z[:, None]
        matrix = self.transforms[target]
        points = points @ matrix[:3, :3].T + matrix[:3, 3]
        return PointCloud(points, target, self.time, self.source)

    def save(self, path):
        return _save(path, raw=self.raw, meters=self.meters, valid=self.valid,
                     intrinsics=self.intrinsics, depth_scale=self.depth_scale,
                     frame=self.frame, time=self.time, source=self.source,
                     **{'transform_' + k: v for k, v in self.transforms.items()})


def depth_from_response(response):
    from bosdyn.api import image_pb2 as im

    if response.status != im.ImageResponse.STATUS_OK:
        raise SpotlabError(f'Tiefenbild nicht verfuegbar (Status {response.status}). Erneut aufnehmen.')
    source, shot = response.source, response.shot
    image = shot.image
    if (source.image_type != im.ImageSource.IMAGE_TYPE_DEPTH
            or image.pixel_format != im.Image.PIXEL_FORMAT_DEPTH_U16
            or image.format != im.Image.FORMAT_RAW):
        raise SpotlabError('Erwartet ein RAW-DEPTH_U16-Tiefenbild. Eine gemeldete Tiefenquelle waehlen.')
    if not source.HasField('pinhole'):
        raise SpotlabError('Pinhole-Kalibrierung fehlt; andere Tiefenquelle waehlen.')
    if image.rows <= 0 or image.cols <= 0 or len(image.data) != image.rows * image.cols * 2:
        raise SpotlabError('Tiefenbild hat unvollstaendige Abmessungen/Bytes. Erneut aufnehmen.')
    scale = _positive(source.depth_scale, 'depth_scale')
    p = source.pinhole.intrinsics
    matrix = np.array([[p.focal_length.x, p.skew.x, p.principal_point.x],
                       [p.skew.y, p.focal_length.y, p.principal_point.y], [0, 0, 1.]])
    if (not np.isfinite(matrix).all() or p.focal_length.x <= 0 or p.focal_length.y <= 0
            or abs(np.linalg.det(matrix)) < 1e-12):
        raise SpotlabError('Ungueltige Kamerakalibrierung. Andere Tiefenaufnahme verwenden.')
    raw = np.frombuffer(image.data, dtype='<u2').reshape(image.rows, image.cols).copy()
    valid = (raw != 0) & (raw != 65535)
    meters = np.where(valid, raw.astype(float) / scale, np.nan)
    frame = shot.frame_name_image_sensor
    if not frame:
        raise SpotlabError('Sensorrahmen fehlt. Aufnahme mit vollstaendigen Metadaten verwenden.')
    return DepthImage(raw, meters, valid, matrix, scale, frame,
                      shot.acquisition_time.seconds + shot.acquisition_time.nanos / 1e9,
                      source.name, _transforms(shot.transforms_snapshot, frame))


@dataclass(frozen=True)
class GridLayer:
    name: str
    values: object
    known: object
    cell_size: float
    frame: str
    time: float
    transforms: dict
    unit: str

    def value_at(self, x, y):
        """Wert an x/y im nativen Gitterrahmen (Ecke 0/0); unbekannt -> None."""
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('Koordinaten muessen endlich sein.')
        col, row = math.floor(x / self.cell_size), math.floor(y / self.cell_size)
        if not (0 <= row < self.values.shape[0] and 0 <= col < self.values.shape[1]):
            return None
        return float(self.values[row, col]) if self.known[row, col] else None

    def cell_centers(self, frame=None):
        """HxWx3 der Zellmitten auf der Gitterebene, nicht die Gelaendehoehen."""
        row, col = np.indices(self.values.shape)
        points = np.stack(((col + .5) * self.cell_size, (row + .5) * self.cell_size,
                           np.zeros_like(row)), axis=-1)
        target = frame or self.frame
        if target not in self.transforms:
            raise SpotlabError(f'Rahmen {target!r} fehlt. Nutze den nativen Gitterrahmen.')
        matrix = self.transforms[target]
        return points @ matrix[:3, :3].T + matrix[:3, 3]

    def save(self, path):
        return _save(path, values=self.values, known=self.known, cell_size=self.cell_size,
                     frame=self.frame, time=self.time, name=self.name, unit=self.unit,
                     **{'transform_' + k: v for k, v in self.transforms.items()})


def grid_from_response(response):
    from bosdyn.api import local_grid_pb2 as lg

    if response.status != lg.LocalGridResponse.STATUS_OK:
        raise SpotlabError(f'LocalGrid {response.local_grid_type_name!r} nicht verfuegbar '
                           f'(Status {response.status}). grid_types() pruefen oder erneut lesen.')
    g = response.local_grid
    types = {lg.LocalGrid.CELL_FORMAT_FLOAT32: '<f4', lg.LocalGrid.CELL_FORMAT_FLOAT64: '<f8',
             lg.LocalGrid.CELL_FORMAT_INT16: '<i2', lg.LocalGrid.CELL_FORMAT_UINT16: '<u2',
             lg.LocalGrid.CELL_FORMAT_INT8: 'i1', lg.LocalGrid.CELL_FORMAT_UINT8: 'u1'}
    nx, ny = g.extent.num_cells_x, g.extent.num_cells_y
    count = nx * ny
    if nx <= 0 or ny <= 0 or count > 4_000_000 or g.cell_format not in types:
        raise SpotlabError('Ungueltige LocalGrid-Abmessungen oder Zellformat. Andere Aufnahme verwenden.')
    size = _positive(g.extent.cell_size, 'cell_size')
    dtype = np.dtype(types[g.cell_format])
    if len(g.data) % dtype.itemsize:
        raise SpotlabError('Unvollstaendige LocalGrid-Bytes. Erneut lesen.')
    raw = np.frombuffer(g.data, dtype=dtype)
    if g.encoding == lg.LocalGrid.ENCODING_RLE:
        counts = np.asarray(g.rle_counts, dtype=np.int64)
        if len(counts) != len(raw) or np.any(counts < 0) or counts.sum() != count:
            raise SpotlabError('Ungueltige LocalGrid-RLE-Laengen. Erneut lesen.')
        raw = np.repeat(raw, counts)
    elif g.encoding != lg.LocalGrid.ENCODING_RAW:
        raise SpotlabError('Unbekannte LocalGrid-Kodierung. RAW oder RLE erforderlich.')
    if raw.size != count:
        raise SpotlabError('LocalGrid-Zellzahl stimmt nicht. Erneut lesen.')
    # SDK: scale is only meaningful if nonzero; zero means unscaled data.
    scale = g.cell_value_scale or 1.0
    if not math.isfinite(scale) or not math.isfinite(g.cell_value_offset):
        raise SpotlabError('Ungueltige LocalGrid-Skalierung. Erneut lesen.')
    values = raw.astype(float).reshape(ny, nx) * scale + g.cell_value_offset
    known = np.isfinite(values)
    if g.unknown_cells:
        if len(g.unknown_cells) != count:
            raise SpotlabError('LocalGrid-Maske braucht ein Byte pro Zelle. Andere Aufnahme verwenden.')
        known &= np.frombuffer(g.unknown_cells, dtype='u1').reshape(ny, nx) == 0
    values[~known] = np.nan
    name = g.local_grid_type_name or response.local_grid_type_name
    frame = g.frame_name_local_grid_data
    if not frame:
        raise SpotlabError('LocalGrid-Rahmen fehlt. Andere Aufnahme verwenden.')
    unit = {'terrain': 'm', 'obstacle_distance': 'm', 'terrain_valid': 'bool',
            'no_step': 'bool', 'intensity': 'raw'}.get(name, 'unknown')
    return GridLayer(name, values, known, size, frame,
                     g.acquisition_time.seconds + g.acquisition_time.nanos / 1e9,
                     _transforms(g.transforms_snapshot, frame), unit)
