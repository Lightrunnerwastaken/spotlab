"""`RealSpot.images`: Farbe erbitten, wo die Kamera es kann -- ohne den Lauf zu stoeren."""

import pytest

pytest.importorskip("bosdyn.api")

from bosdyn.api import image_pb2  # noqa: E402
from bosdyn.client.image import UnsupportedPixelFormatRequestedError  # noqa: E402

from spotlab.backends.real.session import RealSpot  # noqa: E402


class _Bilddienst:
    def __init__(self, farbe_geht=True):
        self.farbe_geht = farbe_geht
        self.anfragen = []

    def get_image(self, anfragen, timeout=None):
        self.anfragen.append(([(a.image_source_name, a.pixel_format, list(a.fallback_formats),
                                a.quality_percent) for a in anfragen], timeout))
        if not self.farbe_geht and any(a.pixel_format == image_pb2.Image.PIXEL_FORMAT_RGB_U8
                                       for a in anfragen):
            raise UnsupportedPixelFormatRequestedError(None, "kein RGB")
        return ["antwort"] * len(anfragen)


def _spot(dienst):
    return RealSpot(robot=None, command_client=None, state_client=None,
                    image_client=dienst, lease_guard=None, estop_guard=None)


def test_ohne_farbe_bleibt_alles_wie_es_war():
    dienst = _Bilddienst()
    _spot(dienst).images(["frontleft_fisheye_image"])
    [(anfragen, frist)] = dienst.anfragen
    assert anfragen == [("frontleft_fisheye_image", image_pb2.Image.PIXEL_FORMAT_UNKNOWN, [], 75)]
    assert frist is not None, "ein Bildabruf ohne Zeitgrenze haelt einen Thread ewig"


def test_farbe_wird_mit_grau_als_rueckfall_erbeten():
    dienst = _Bilddienst()
    _spot(dienst).images(["a", "b"], farbe=True, guete=60)
    [(anfragen, _)] = dienst.anfragen
    assert anfragen == [
        ("a", image_pb2.Image.PIXEL_FORMAT_RGB_U8, [image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8], 60),
        ("b", image_pb2.Image.PIXEL_FORMAT_RGB_U8, [image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8], 60),
    ]


def test_ein_roboter_ohne_farbe_wird_einmal_gefragt_und_dann_grau_bedient():
    """Aeltere Software kennt den Rueckfall nicht und weist RGB ab: dann grau --
    und beim naechsten Bild gleich grau, nicht wieder zwei Fragen uebers WLAN."""
    dienst = _Bilddienst(farbe_geht=False)
    spot = _spot(dienst)
    assert spot.images(["a"], farbe=True) == ["antwort"]
    assert len(dienst.anfragen) == 2 and dienst.anfragen[1][0][0][1] == image_pb2.Image.PIXEL_FORMAT_UNKNOWN
    spot.images(["a"], farbe=True)
    assert len(dienst.anfragen) == 3 and dienst.anfragen[2][0][0][1] == image_pb2.Image.PIXEL_FORMAT_UNKNOWN
