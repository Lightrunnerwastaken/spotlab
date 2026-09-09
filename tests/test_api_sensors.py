import math
from types import SimpleNamespace

import numpy as np
import pytest
from bosdyn.api import geometry_pb2 as geo
from bosdyn.api import image_pb2 as im
from bosdyn.api import local_grid_pb2 as lg

from spotlab.api.spot import Spot
from spotlab.backends.base import Capability
from spotlab.backends.dryrun import DryRunBackend
from spotlab.backends.sensor_data import depth_from_response, grid_from_response
from spotlab.errors import SpotlabError, UnsupportedCapability
from spotlab.record.run import RunRecorder


def frames(sensor):
    result = geo.FrameTreeSnapshot()
    result.child_to_parent_edge_map['vision'].parent_frame_name = ''
    for name in ('body', sensor):
        edge = result.child_to_parent_edge_map[name]
        edge.parent_frame_name = 'vision'
        edge.parent_tform_child.rotation.w = 1
    edge = result.child_to_parent_edge_map[sensor]
    edge.parent_tform_child.position.x = 10
    edge.parent_tform_child.rotation.w = math.sqrt(.5)
    edge.parent_tform_child.rotation.z = math.sqrt(.5)
    return result


def depth_response():
    r = im.ImageResponse(status=im.ImageResponse.STATUS_OK)
    r.source.name = 'frontleft_depth'
    r.source.image_type = im.ImageSource.IMAGE_TYPE_DEPTH
    r.source.depth_scale = 1000
    p = r.source.pinhole.intrinsics
    p.focal_length.x = 2
    p.focal_length.y = 2
    r.shot.image.rows = 2
    r.shot.image.cols = 3
    r.shot.image.pixel_format = im.Image.PIXEL_FORMAT_DEPTH_U16
    r.shot.image.format = im.Image.FORMAT_RAW
    r.shot.image.data = np.array([[1000, 0, 65535], [2000, 3000, 4000]], dtype='<u2').tobytes()
    r.shot.frame_name_image_sensor = 'camera'
    r.shot.transforms_snapshot.CopyFrom(frames('camera'))
    r.shot.acquisition_time.seconds = 42
    return r


def grid_response(name='terrain', rle=False):
    r = lg.LocalGridResponse(status=lg.LocalGridResponse.STATUS_OK, local_grid_type_name=name)
    g = r.local_grid
    g.local_grid_type_name = name
    g.extent.num_cells_x = 3
    g.extent.num_cells_y = 2
    g.extent.cell_size = .5
    g.cell_format = lg.LocalGrid.CELL_FORMAT_INT16
    g.encoding = lg.LocalGrid.ENCODING_RLE if rle else lg.LocalGrid.ENCODING_RAW
    g.data = np.array([1, 2, 3] if rle else [1, 1, 2, 2, 3, 3], dtype='<i2').tobytes()
    if rle:
        g.rle_counts.extend([2, 2, 2])
    g.cell_value_scale = .1
    g.cell_value_offset = -1
    g.unknown_cells = bytes([0, 1, 0, 0, 0, 0])
    g.frame_name_local_grid_data = 'grid'
    g.transforms_snapshot.CopyFrom(frames('grid'))
    g.acquisition_time.seconds = 42
    return r


def test_depth_units_invalid_pixels_and_export(tmp_path):
    d = depth_from_response(depth_response())
    assert d.distance_at(0, 0) == 1
    assert d.distance_at(1, 0) is None
    assert d.distance_at(2, 0) is None
    assert d.distance_at(-1, 0) is None
    assert np.isnan(d.meters[0, 2])
    data = np.load(d.save(tmp_path / 'depth.npz'), allow_pickle=False)
    assert data['depth_scale'] == 1000
    np.testing.assert_array_equal(data['raw'], d.raw)
    assert data['time'] == 42


def test_cloud_projection_rotation_translation_and_filter(tmp_path):
    d = depth_from_response(depth_response())
    cloud = d.point_cloud('sensor', stride=1, max_distance=4)
    np.testing.assert_allclose(cloud.points, [[0, 0, 1], [0, 1, 2], [1.5, 1.5, 3]])
    body = d.point_cloud('body', stride=1, max_distance=4)
    np.testing.assert_allclose(body.points, [[10, 0, 1], [9, 0, 2], [8.5, 1.5, 3]], atol=1e-12)
    assert body.frame == 'body'
    assert 'element vertex 3' in body.save(tmp_path / 'points.ply').read_text()
    assert d.point_cloud('sensor', stride=20).points.shape == (1, 3)
    assert d.point_cloud('sensor', min_distance=4, max_distance=5).points.shape == (0, 3)
    with pytest.raises(SpotlabError, match='fehlt'):
        d.point_cloud('missing')


@pytest.mark.parametrize('failure', ['status', 'format', 'scale', 'focal', 'bytes'])
def test_depth_rejects_bad_metadata(failure):
    r = depth_response()
    if failure == 'status':
        r.status = im.ImageResponse.STATUS_UNKNOWN
    elif failure == 'format':
        r.shot.image.format = im.Image.FORMAT_RLE
    elif failure == 'scale':
        r.source.depth_scale = 0
    elif failure == 'focal':
        r.source.pinhole.intrinsics.focal_length.x = 0
    else:
        r.shot.image.data = b'1'
    with pytest.raises((SpotlabError, ValueError)):
        depth_from_response(r)


@pytest.mark.parametrize('rle', [False, True])
def test_grid_decode_scale_mask_orientation_and_cell_bounds(rle):
    g = grid_from_response(grid_response(rle=rle))
    assert g.values.shape == (2, 3)
    assert g.value_at(0, 0) == pytest.approx(-.9)
    assert g.value_at(.5, 0) is None
    assert g.value_at(-.001, 0) is None
    assert g.value_at(1.5, 0) is None
    np.testing.assert_allclose(g.cell_centers('vision')[0, 0], [9.75, .25, 0], atol=1e-12)
    assert g.unit == 'm'


def test_grid_zero_scale_means_unscaled():
    r = grid_response()
    r.local_grid.cell_value_scale = 0
    r.local_grid.cell_value_offset = 0
    assert grid_from_response(r).value_at(0, 0) == 1


@pytest.mark.parametrize('failure', ['rle', 'mask', 'encoding', 'status'])
def test_grid_rejects_malformed_response(failure):
    r = grid_response(rle=True)
    if failure == 'rle':
        r.local_grid.rle_counts[0] = 1000000000
    elif failure == 'mask':
        r.local_grid.unknown_cells = b'\0'
    elif failure == 'encoding':
        r.local_grid.encoding = lg.LocalGrid.ENCODING_UNKNOWN
    else:
        r.status = lg.LocalGridResponse.STATUS_DATA_UNAVAILABLE
    with pytest.raises(SpotlabError):
        grid_from_response(r)


class Backend:
    def capabilities(self):
        return Capability.DEPTH_CAMERAS | Capability.LOCAL_GRID

    def image_sources(self):
        return ['frontleft_depth', 'frontleft_fisheye_image']

    def images(self, sources):
        assert sources == ['frontleft_depth']
        return [depth_response()]


def test_facade_uses_depth_alias_and_records_quantitative_data(tmp_path):
    recorder = RunRecorder(tmp_path, None, backend='dryrun')
    s = Spot(Backend(), recorder=recorder)
    assert s.supports('depth')
    assert s.supports('point_cloud')
    assert s.depth().source == 'frontleft_depth'
    assert len(s.point_cloud(stride=1).points) == 4
    assert len(list((recorder.dir / 'sensoren').glob('*.npz'))) == 2
    recorder.finish('ok')


def test_terrain_valid_combined_and_mismatch_rejected():
    terrain = grid_response()
    valid = grid_response('terrain_valid')
    valid.local_grid.cell_value_scale = 1
    valid.local_grid.cell_value_offset = 0
    valid.local_grid.data = np.array([1, 1, 0, 1, 1, 1], dtype='<i2').tobytes()
    calls = []
    def get(names):
        calls.append(names)
        return [valid, terrain]
    client = SimpleNamespace(get_local_grids=get,
                             get_local_grid_types=lambda: [SimpleNamespace(name='terrain')])
    robot = SimpleNamespace(ensure_client=lambda name: client)
    s = Spot(Backend(), robot=robot)
    assert s.grid_types() == ['terrain']
    g = s.local_grid('terrain')
    assert calls == [['terrain', 'terrain_valid']]
    assert not g.known[0, 1] and not g.known[0, 2]
    assert np.isnan(g.values[0, 2])
    valid.local_grid.acquisition_time.seconds += 1
    with pytest.raises(SpotlabError, match='nicht zusammen'):
        s.local_grid('terrain')


def test_dryrun_grid_only_no_fake_depth_or_terrain():
    s = Spot(DryRunBackend())
    assert not s.supports('depth')
    with pytest.raises(UnsupportedCapability):
        s.depth()
    if s.supports('local_grid'):
        assert s.grid_types() == ['obstacle_distance']
        assert s.local_grid().name == 'obstacle_distance'
        with pytest.raises(UnsupportedCapability):
            s.local_grid('terrain')


def test_recorded_robot_depth_matches_sdk():
    from pathlib import Path

    from bosdyn.client.image import depth_image_to_pointcloud

    folder = Path(__file__).parent / 'daten/tiefe_real_20260812'
    for path in folder.glob('*.pb'):
        response = im.ImageResponse.FromString(path.read_bytes())
        # Historical fixtures reconstruct capture/source, without the RPC status.
        assert response.status == im.ImageResponse.STATUS_UNKNOWN
        response.status = im.ImageResponse.STATUS_OK
        response.source.rows = response.shot.image.rows
        response.source.cols = response.shot.image.cols
        depth = depth_from_response(response)
        expected = depth_image_to_pointcloud(response, min_dist=0, max_dist=5)
        cloud = depth.point_cloud('sensor', stride=1, max_distance=5)
        np.testing.assert_allclose(cloud.points, expected, atol=1e-10)
        assert len(depth.point_cloud('body').points) > 0
        assert len(depth.point_cloud('vision').points) > 0


def test_recorded_robot_grid_decodes_byte_mask():
    from pathlib import Path

    path = Path(__file__).parent / 'daten/gitter_real_20260812/000001_obstacle_distance.pb'
    response = lg.LocalGridResponse.FromString(path.read_bytes())
    grid = grid_from_response(response)
    expected = np.frombuffer(response.local_grid.unknown_cells, dtype='u1') == 0
    np.testing.assert_array_equal(grid.known.reshape(-1), expected)
    assert np.isfinite(grid.cell_centers('vision')).all()


def test_mujoco_depth_and_cloud_integration():
    spotsim = pytest.importorskip('spotsim')
    if not spotsim.spot_asset_available():
        pytest.skip('Menagerie-Asset fehlt')
    from spotlab.backends.mujoco import MujocoBackend
    from spotlab.welt.raum import raum_laden

    backend = MujocoBackend(raum=raum_laden('durchgang'), jetzt=lambda: 1000000.)
    try:
        spot = Spot(backend)
        depth = spot.depth()
        assert depth.valid.any()
        cloud = depth.point_cloud('body')
        assert len(cloud.points) > 0
        assert np.isfinite(cloud.points).all()
        assert spot.grid_types() == ['obstacle_distance']
        grid = spot.local_grid()
        assert grid.known.any()
        assert np.isfinite(grid.cell_centers('vision')).all()
    finally:
        backend.close()
