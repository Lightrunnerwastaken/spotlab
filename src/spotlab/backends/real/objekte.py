"""Gegenstände im Kamerabild finden — YOLOX-S aus dem Zoo, EINE COCO-Klasse.

Für die Vorführung von Versuch 3 in matura-spot (`notes/ENTWURF_versuch3.md`):
Spot sucht einen Teddybären statt eines AprilTags. Derselbe Erkenner wie beim
Körper (`koerper.YoloxPersonen`, Modell `object_detection_yolox_2022nov.onnx`,
Apache 2.0), nur eine andere Klasse.

Wo der Gegenstand steht, sagt die TIEFE, nie die Kastengrösse (dieselbe Regel
wie beim Gesicht): `objekt_im_bild` nimmt den Median des registrierten
Tiefenbilds (`*_depth_in_visual_frame`, am Schul-Spot vorhanden, Steckbrief
12.08.2026) im inneren Teil des Kastens und rechnet den Punkt über Intrinsik und
Rahmenbaum DIESER Aufnahme in den Rahmen „vision" — die Lage zum
Bildzeitpunkt. Am 07.09.2026 lief der Explorer an einem Tag vorbei, weil eine
alte Sichtung körperrelativ für immer „0.9 m voraus" stand; eine Weltlage aus
dem Bildzeitpunkt hat diesen Fehler nicht.
"""

import io
from dataclasses import dataclass

import numpy as np

from spotlab.backends.real import koerper
from spotlab.errors import SpotlabError

COCO = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
)
OBJEKT_MINDEST = koerper.YOLOX_MINDEST   # Mindestsicherheit je Kasten (wie beim Körper)
KERN_RAND = 0.25                         # je Seite so viel des Kastens bleibt für die Tiefe weg
# Die Fisheye-Kameras sind seitlich eingebaut; so weit drehen die SDK-Beispiele von
# Boston Dynamics (`get_image.py`, ROTATION_ANGLE) die Bilder, damit oben oben ist.
# Gemessen am 09.10.2026 (Rucksack, 2 m): rechts roh 0.25 „suitcase", aufgerichtet 0.57.
AUFRECHT_GRAD = {"frontleft_fisheye_image": -78.0, "frontright_fisheye_image": -102.0,
                 "right_fisheye_image": 180.0}


def klassen_index(name):
    """Index der COCO-Klasse; `teddy_bear` und `teddy bear` sind dasselbe."""
    gesucht = str(name).strip().lower().replace("_", " ")
    if gesucht in COCO:
        return COCO.index(gesucht)
    raise SpotlabError(
        f"YOLOX kennt keine Klasse '{name}'. Bekannt sind die 80 COCO-Klassen, z. B. "
        f"'teddy_bear', 'chair', 'backpack', 'suitcase', 'bottle'.")


class YoloxObjekte(koerper.YoloxPersonen):
    """Kästen einer oder mehrerer Klassen im ganzen Bild: `(rgb) -> [(x1, y1, x2, y2, score)]`.

    `klasse` mit Kommas nimmt mehrere (`"suitcase,backpack"`): ein kastenförmiger
    Rucksack heisst für YOLOX von vorn oft „suitcase" (gemessen 09.10.2026)."""

    def __init__(self, klasse="teddy bear", pfad=None, modell=None, mindest=OBJEKT_MINDEST):
        indizes = [klassen_index(k) for k in str(klasse).split(",") if k.strip()]
        if modell is None and pfad is None:
            pfad = koerper.personenmodell()
        super().__init__(pfad, modell=modell, mindest=mindest, klasse=tuple(indizes))
        self.klasse = "+".join(COCO[i] for i in indizes)


def aufrichten(bild, grad):
    """(gedreht, zurück): das Bild um `grad` gedreht (positiv = gegen den Uhrzeiger, wie
    die SDK-Beispiele), samt der Matrix, die Pixel des gedrehten Bildes ins Original
    zurückrechnet. Die Leinwand wächst mit, nichts wird abgeschnitten."""
    import cv2

    h, w = bild.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), float(grad), 1.0)
    c, s = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(round(h * s + w * c)), int(round(h * c + w * s))
    m[0, 2] += nw / 2.0 - w / 2.0
    m[1, 2] += nh / 2.0 - h / 2.0
    # Nächster Nachbar, kein Glätten: keine erfundenen Grauwerte. Gemessen am Rucksack
    # (09.10.2026, 2 m): bilinear 0.36, nächster Nachbar 0.57 — ein Grenzfall, der an
    # solchen Details hängt, ist kein verlässlicher Fund; die Erkennungsprobe sagt es.
    gedreht = cv2.warpAffine(np.ascontiguousarray(bild), m, (nw, nh), flags=cv2.INTER_NEAREST)
    return gedreht, cv2.invertAffineTransform(m)


def kasten_zurueck(kasten, zurueck):
    """Ein Kasten des gedrehten Bildes als achsparalleler Kasten im Original."""
    x1, y1, x2, y2, score = kasten
    ecken = np.array([[x1, y1, 1.0], [x2, y1, 1.0], [x1, y2, 1.0], [x2, y2, 1.0]])
    p = ecken @ np.asarray(zurueck).T
    return (float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()),
            float(p[:, 1].max()), float(score))


def kaesten_aufrecht(finder, antwort):
    """Kästen in ROHBILD-Koordinaten — gesucht im aufgerichteten Bild, wo die Quelle
    eine Drehung hat (`AUFRECHT_GRAD`); so passen sie zur Tiefe im Rohraster."""
    rgb = bild_als_array(antwort)
    grad = AUFRECHT_GRAD.get(antwort.source.name, 0.0)
    if not grad:
        return list(finder(rgb))
    gedreht, zurueck = aufrichten(rgb, grad)
    return [kasten_zurueck(k, zurueck) for k in finder(gedreht)]


@dataclass(frozen=True)
class Fund:
    welt_xy: tuple                       # (x, y) im Rahmen „vision"
    tiefe_m: float                       # Kamera-z des Gegenstands
    kasten: tuple                        # (x1, y1, x2, y2, score) im Bild
    quelle: str


def bild_als_array(antwort):
    """RGB (H, W, 3) uint8 aus einer Bild-`ImageResponse` — Grau wird verdreifacht."""
    from bosdyn.api import image_pb2

    bild = antwort.shot.image
    if bild.format == image_pb2.Image.FORMAT_JPEG:
        from PIL import Image

        feld = np.asarray(Image.open(io.BytesIO(bild.data)))
    else:
        feld = np.frombuffer(bild.data, dtype=np.uint8).reshape(bild.rows, bild.cols, -1)
    if feld.ndim == 2:
        feld = feld[..., None]
    if feld.shape[2] == 1:
        feld = np.repeat(feld, 3, axis=2)
    return np.ascontiguousarray(feld[..., :3])


def objekt_im_bild(bild, tiefe, kasten, rand=KERN_RAND):
    """Weltlage eines Kastens aus Bild + registrierter Tiefe, oder None ohne Tiefe.

    `tiefe` muss im Raster des Bildes liegen (`*_depth_in_visual_frame`); eine
    andere Auflösung wird umgerechnet. Ein fehlender Rahmen im Baum ist ein
    Fehler, keine Identität.
    """
    from bosdyn.api import image_pb2
    from bosdyn.client import frame_helpers as fh

    if tiefe.shot.image.pixel_format != image_pb2.Image.PIXEL_FORMAT_DEPTH_U16:
        raise SpotlabError(f"'{tiefe.source.name}' ist kein Tiefenbild (DEPTH_U16).")
    x1, y1, x2, y2 = (float(v) for v in kasten[:4])
    sx = tiefe.shot.image.cols / max(bild.shot.image.cols, 1)
    sy = tiefe.shot.image.rows / max(bild.shot.image.rows, 1)
    b, h = x2 - x1, y2 - y1
    i0, i1 = int(round((y1 + rand * h) * sy)), int(round((y2 - rand * h) * sy))
    j0, j1 = int(round((x1 + rand * b) * sx)), int(round((x2 - rand * b) * sx))
    roh = np.frombuffer(tiefe.shot.image.data, dtype="<u2").reshape(
        tiefe.shot.image.rows, tiefe.shot.image.cols)
    kern = roh[max(i0, 0):max(i1, i0 + 1), max(j0, 0):max(j1, j0 + 1)]
    gueltig = kern[(kern > 0) & (kern < 65535)]
    if gueltig.size == 0:
        return None
    z = float(np.median(gueltig)) / (tiefe.source.depth_scale or 1.0)

    innen = bild.source.pinhole.intrinsics
    u, v = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    punkt = np.array([(u - innen.principal_point.x) / innen.focal_length.x * z,
                      (v - innen.principal_point.y) / innen.focal_length.y * z, z, 1.0])
    rahmen = bild.shot.frame_name_image_sensor
    try:
        lage = fh.get_a_tform_b(bild.shot.transforms_snapshot, fh.VISION_FRAME_NAME, rahmen)
    except Exception:
        lage = None
    if lage is None:
        raise SpotlabError(f"Im Rahmenbaum von '{bild.source.name}' fehlt der Weg vision→{rahmen}; "
                           f"ohne ihn ist die Lage des Gegenstands geraten.")
    welt = np.asarray(lage.to_matrix()) @ punkt
    return Fund((float(welt[0]), float(welt[1])), z, tuple(kasten), bild.source.name)
