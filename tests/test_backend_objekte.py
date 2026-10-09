"""Gegenstände im Kamerabild (YOLOX, eine COCO-Klasse) und ihre Lage im Raum.

Die Lage wird an ECHT gebauten `ImageResponse`-Protobufs geprüft: eine Kamera
im Körperursprung, die geradeaus schaut, ein Körper bei (1, 2) mit Blick nach
+y. Ein Kasten in der Bildmitte mit 2 m Tiefe muss dann bei (1, 4) landen,
einer 1 m rechts davon bei (2, 4) — ein Vorzeichen- oder Achsenfehler fiele
sofort auf.
"""

import math

import numpy as np
import pytest

pytest.importorskip("bosdyn.api")

from spotlab.backends.real import koerper, objekte  # noqa: E402
from spotlab.errors import SpotlabError  # noqa: E402

FX = FY = 50.0
CX, CY = 32.0, 24.0
SPALTEN, ZEILEN = 64, 48


def _antwort(art, daten, koerper_lage=(1.0, 2.0, math.radians(90.0)), mit_rahmen=True):
    from bosdyn.api import geometry_pb2, image_pb2
    from bosdyn.client import math_helpers

    a = image_pb2.ImageResponse()
    a.source.name = f"frontleft_{art}"
    a.source.rows, a.source.cols = ZEILEN, SPALTEN
    innen = a.source.pinhole.intrinsics
    innen.focal_length.x, innen.focal_length.y = FX, FY
    innen.principal_point.x, innen.principal_point.y = CX, CY
    bild = a.shot.image
    bild.rows, bild.cols = ZEILEN, SPALTEN
    if art == "tiefe":
        a.source.image_type = image_pb2.ImageSource.IMAGE_TYPE_DEPTH
        a.source.depth_scale = 1000.0
        bild.pixel_format = image_pb2.Image.PIXEL_FORMAT_DEPTH_U16
        bild.format = image_pb2.Image.FORMAT_RAW
        bild.data = daten.astype("<u2").tobytes()
    else:
        a.source.image_type = image_pb2.ImageSource.IMAGE_TYPE_VISUAL
        bild.pixel_format = image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8
        bild.format = image_pb2.Image.FORMAT_RAW
        bild.data = daten.astype(np.uint8).tobytes()
    a.shot.frame_name_image_sensor = "frontleft_fisheye"
    if not mit_rahmen:
        return a
    kanten = a.shot.transforms_snapshot.child_to_parent_edge_map
    kanten["vision"].parent_frame_name = ""
    x, y, gier = koerper_lage
    kanten["body"].parent_frame_name = "vision"
    kanten["body"].parent_tform_child.CopyFrom(
        math_helpers.SE3Pose(x, y, 0.5, math_helpers.Quat.from_yaw(gier)).to_proto())
    # Optikrahmen: z voraus (= Körper-x), x rechts (= −Körper-y), y unten (= −Körper-z)
    dreh = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
    kamera = kanten["frontleft_fisheye"]
    kamera.parent_frame_name = "body"
    kamera.parent_tform_child.CopyFrom(
        math_helpers.SE3Pose(0.0, 0.0, 0.0, math_helpers.Quat.from_matrix(dreh)).to_proto())
    assert isinstance(kamera.parent_tform_child, geometry_pb2.SE3Pose)
    return a


def _tiefe_im_kasten(kasten, mm=2000):
    t = np.zeros((ZEILEN, SPALTEN))
    x1, y1, x2, y2 = (int(v) for v in kasten[:4])
    t[y1:y2, x1:x2] = mm
    return t


def test_ein_kasten_in_der_mitte_liegt_geradeaus_im_raum():
    kasten = (22.0, 14.0, 42.0, 34.0, 0.9)
    fund = objekte.objekt_im_bild(_antwort("bild", np.zeros((ZEILEN, SPALTEN))),
                                  _antwort("tiefe", _tiefe_im_kasten(kasten)), kasten)
    assert fund.welt_xy == pytest.approx((1.0, 4.0), abs=1e-6)
    assert fund.tiefe_m == pytest.approx(2.0)


def test_ein_kasten_rechts_liegt_rechts_vom_roboter():
    kasten = (47.0, 14.0, 67.0, 34.0, 0.9)        # Mitte bei u = 57: 25 px = 1 m bei 2 m
    tiefe = np.full((ZEILEN, SPALTEN), 2000.0)
    fund = objekte.objekt_im_bild(_antwort("bild", np.zeros((ZEILEN, SPALTEN))),
                                  _antwort("tiefe", tiefe), kasten)
    assert fund.welt_xy == pytest.approx((2.0, 4.0), abs=1e-6)


def test_der_hintergrund_am_rand_des_kastens_zaehlt_nicht():
    """Ein Kasten umfasst immer etwas Wand: der Median über den INNEREN Teil."""
    kasten = (12.0, 4.0, 52.0, 44.0, 0.9)
    tiefe = np.full((ZEILEN, SPALTEN), 4000.0)                       # Wand dahinter
    tiefe[12:36, 22:42] = 1500.0                                      # der Gegenstand
    fund = objekte.objekt_im_bild(_antwort("bild", np.zeros((ZEILEN, SPALTEN))),
                                  _antwort("tiefe", tiefe), kasten)
    assert fund.tiefe_m == pytest.approx(1.5)


def test_ohne_tiefe_im_kasten_kein_fund():
    kasten = (22.0, 14.0, 42.0, 34.0, 0.9)
    assert objekte.objekt_im_bild(_antwort("bild", np.zeros((ZEILEN, SPALTEN))),
                                  _antwort("tiefe", np.zeros((ZEILEN, SPALTEN))), kasten) is None


def test_ein_fehlender_rahmen_ist_ein_fehler():
    kasten = (22.0, 14.0, 42.0, 34.0, 0.9)
    with pytest.raises(SpotlabError):
        objekte.objekt_im_bild(_antwort("bild", np.zeros((ZEILEN, SPALTEN)), mit_rahmen=False),
                               _antwort("tiefe", _tiefe_im_kasten(kasten)), kasten)


def test_das_graubild_wird_dreikanalig():
    grau = np.arange(ZEILEN * SPALTEN).reshape(ZEILEN, SPALTEN) % 256
    rgb = objekte.bild_als_array(_antwort("bild", grau))
    assert rgb.shape == (ZEILEN, SPALTEN, 3) and (rgb[..., 0] == grau).all()


class _YoloxAttrappe:
    def __init__(self, zeilen):
        self.zeilen = np.array(zeilen, dtype=float)

    def infer(self, bild):
        return self.zeilen


def test_yolox_nimmt_nur_die_gewaehlte_klasse():
    modell = _YoloxAttrappe([
        [10, 20, 100, 100, 0.9, 0],         # Mensch
        [200, 20, 50, 60, 0.8, 77],         # Teddybär
        [300, 20, 50, 60, 0.2, 77],         # zu unsicher
    ])
    teddy = objekte.YoloxObjekte("teddy_bear", modell=modell)
    [kasten] = teddy(np.zeros((640, 640, 3), dtype=np.uint8))
    assert kasten == pytest.approx((200.0, 20.0, 250.0, 80.0, 0.8))
    assert teddy.klasse == "teddy bear"
    assert len(koerper.YoloxPersonen(modell=modell)(np.zeros((640, 640, 3), np.uint8))) == 1


def test_mehrere_klassen_mit_komma():
    modell = _YoloxAttrappe([[10, 20, 50, 60, 0.6, 28], [100, 20, 50, 60, 0.7, 24],
                             [200, 20, 50, 60, 0.9, 0]])
    finder = objekte.YoloxObjekte("suitcase,backpack", modell=modell)
    kaesten = finder(np.zeros((640, 640, 3), dtype=np.uint8))
    assert [round(k[0]) for k in kaesten] == [100, 10] and finder.klasse == "suitcase+backpack"


def _fleck_finder(rgb):
    """Attrappe eines Erkenners: der Kasten um die hellen Pixel des Bildes, das er BEKOMMT."""
    zeilen, spalten = np.nonzero(rgb[..., 0] > 200)
    if zeilen.size == 0:
        return []
    return [(float(spalten.min()), float(zeilen.min()), float(spalten.max()), float(zeilen.max()), 0.9)]


@pytest.mark.parametrize("quelle", ["frontleft_fisheye_image", "frontright_fisheye_image",
                                    "back_fisheye_image"])
def test_kaesten_aus_dem_aufgerichteten_bild_landen_im_rohbild(quelle):
    """Gesucht wird im aufgerichteten Bild, zurück kommt der Kasten im Rohraster —
    dort, wo der Fleck wirklich ist (sonst träfe die Tiefe etwas anderes)."""
    grau = np.zeros((ZEILEN, SPALTEN))
    grau[10:20, 40:50] = 255                                     # Fleck, Mitte (44.5, 14.5)
    antwort = _antwort("bild", grau)
    antwort.source.name = quelle
    gesehen = []
    [kasten] = objekte.kaesten_aufrecht(lambda rgb: gesehen.append(rgb.shape) or _fleck_finder(rgb),
                                        antwort)
    mitte = ((kasten[0] + kasten[2]) / 2, (kasten[1] + kasten[3]) / 2)
    assert mitte == pytest.approx((44.5, 14.5), abs=1.5)
    if quelle in objekte.AUFRECHT_GRAD:
        assert gesehen[0][:2] != (ZEILEN, SPALTEN), "der Finder bekam das gedrehte Bild"


def test_aufrichten_dreht_gegen_den_uhrzeiger_wie_die_sdk_beispiele():
    """Positiver Winkel = gegen den Uhrzeiger (wie scipy/PIL in get_image.py): ein Fleck
    rechts neben der Mitte wandert bei +90° nach OBEN."""
    bild = np.zeros((41, 41), dtype=np.uint8)
    bild[20, 35] = 255
    gedreht, _ = objekte.aufrichten(bild, 90.0)
    z, s = np.unravel_index(np.argmax(gedreht), gedreht.shape)
    assert z < 10 and abs(s - 20) <= 1


def test_coco_kennt_achtzig_klassen_und_weist_fremde_ab():
    assert len(objekte.COCO) == 80
    assert objekte.klassen_index("person") == 0
    assert objekte.klassen_index("teddy bear") == objekte.klassen_index("teddy_bear") == 77
    assert objekte.COCO[56] == "chair"
    with pytest.raises(SpotlabError, match="teddy"):
        objekte.klassen_index("teddybaer")


@pytest.mark.skipif(not (koerper.MODELL_ORDNER / koerper.MODELL_PERSONEN).is_file(),
                    reason="YOLOX-Modell nicht abgelegt")
def test_das_echte_yolox_sieht_im_leeren_gang_keinen_teddy():
    """Die Aufzeichnung vom 12.08.2026 zeigt einen leeren Gang."""
    from test_backend_panorama import _paar

    from spotlab.backends.real import panorama

    pano = panorama.Panorama(panorama.kalibrierung_aus(_paar(90)), zuschnitt=panorama.ALLES)
    grau = pano.zusammensetzen(panorama.bilder_aus(_paar(90)))
    teddy = objekte.YoloxObjekte("teddy_bear", pfad=koerper.personenmodell())
    assert teddy(np.stack([grau] * 3, axis=-1)) == []
