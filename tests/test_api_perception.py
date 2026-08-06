import numpy as np
import pytest
from bosdyn.api import image_pb2

from spotlab.api.perception import Image, aufloesen, camera, cameras
from spotlab.backends.base import Capability
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import SpotlabError, UnsupportedCapability

QUELLEN = ["frontleft_fisheye_image", "frontleft_depth", "back_fisheye_image"]


class MitKamera(DryRunBackend):
    def capabilities(self):
        return (
            Capability.LOCOMOTION
            | Capability.POSTURE
            | Capability.POWER
            | Capability.GRAY_CAMERAS
            | Capability.DEPTH_CAMERAS
        )

    def image_sources(self):
        return list(QUELLEN)

    def images(self, sources):
        antwort = image_pb2.ImageResponse()
        antwort.source.name = sources[0]
        antwort.shot.image.cols = 4
        antwort.shot.image.rows = 2
        antwort.shot.image.pixel_format = image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8
        antwort.shot.image.format = image_pb2.Image.FORMAT_RAW
        antwort.shot.image.data = bytes(range(8))
        antwort.source.pinhole.intrinsics.focal_length.x = 200.0
        return [antwort]


def test_kurznamen_werden_aufgeloest():
    assert aufloesen("frontleft", QUELLEN) == "frontleft_fisheye_image"


def test_echter_quellname_geht_direkt_durch():
    assert aufloesen("back_fisheye_image", QUELLEN) == "back_fisheye_image"


def test_unbekannter_name_zaehlt_die_vorhandenen_auf():
    with pytest.raises(SpotlabError) as info:
        aufloesen("oben", QUELLEN)
    assert "frontleft" in str(info.value)


def test_cameras_meldet_nur_vorhandene_kurznamen():
    assert set(cameras(MitKamera())) == {"frontleft", "back"}


def test_bild_wird_zu_numpy_array():
    bild = camera(MitKamera(), None, "frontleft")
    assert isinstance(bild, Image)
    assert bild.array.shape == (2, 4)
    assert bild.array.dtype == np.uint8


def test_bild_traegt_intrinsics():
    bild = camera(MitKamera(), None, "frontleft")
    assert bild.intrinsics["focal_length_x"] == 200.0


def test_bild_speichern_erzeugt_datei(tmp_path):
    ziel = camera(MitKamera(), None, "frontleft").save(tmp_path / "vorne.png")
    assert ziel.exists() and ziel.stat().st_size > 0


def test_bild_wird_im_lauf_verzeichnet(tmp_path):
    from spotlab.record.run import RunRecorder

    rec = RunRecorder(tmp_path, None, backend="test")
    camera(MitKamera(), rec, "frontleft")
    rec.finish("ok")
    assert (rec.dir / "bilder" / "bilder.json").exists()


def test_ohne_kamera_faehigkeit_klare_verweigerung():
    with pytest.raises(UnsupportedCapability):
        camera(DryRunBackend(), None, "frontleft")
