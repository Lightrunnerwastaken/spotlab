"""Kamerabilder.

Die Quellnamen des echten Spot sind sperrig (`frontleft_fisheye_image`). Die
Bibliothek nimmt Kurznamen entgegen und löst sie gegen die vom Roboter
GEMELDETEN Quellen auf — nicht gegen eine fest verdrahtete Liste, denn die
Benennung ist eine unbestätigte Annahme (Spec A2).
"""

import io
from pathlib import Path

import numpy as np
from bosdyn.api import image_pb2

from spotlab.backends.base import Capability, require
from spotlab.errors import SpotlabError

KURZNAMEN = {
    "frontleft": ("frontleft_fisheye_image", "frontleft_depth"),
    "frontright": ("frontright_fisheye_image", "frontright_depth"),
    "left": ("left_fisheye_image", "left_depth"),
    "right": ("right_fisheye_image", "right_depth"),
    "back": ("back_fisheye_image", "back_depth"),
}

_FORMATE = {
    image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8: (np.uint8, 1),
    image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U16: (np.uint16, 1),
    image_pb2.Image.PIXEL_FORMAT_DEPTH_U16: (np.uint16, 1),
    image_pb2.Image.PIXEL_FORMAT_RGB_U8: (np.uint8, 3),
    image_pb2.Image.PIXEL_FORMAT_RGBA_U8: (np.uint8, 4),
}


class Image:
    """Ein Kamerabild mit Rohdaten, Array und Intrinsics."""

    def __init__(self, antwort):
        self._antwort = antwort
        aufnahme = antwort.shot.image
        self.source = antwort.source.name
        self.width = aufnahme.cols
        self.height = aufnahme.rows
        self.raw = aufnahme.data
        self.pixel_format = aufnahme.pixel_format
        self.is_jpeg = aufnahme.format == image_pb2.Image.FORMAT_JPEG
        pinhole = antwort.source.pinhole.intrinsics
        self.intrinsics = {
            "focal_length_x": pinhole.focal_length.x,
            "focal_length_y": pinhole.focal_length.y,
            "principal_point_x": pinhole.principal_point.x,
            "principal_point_y": pinhole.principal_point.y,
        }

    @property
    def array(self):
        if self.is_jpeg:
            from PIL import Image as PILImage

            return np.asarray(PILImage.open(io.BytesIO(self.raw)))
        dtype, kanaele = _FORMATE.get(self.pixel_format, (np.uint8, 1))
        daten = np.frombuffer(self.raw, dtype=dtype)
        if kanaele == 1:
            return daten.reshape(self.height, self.width)
        return daten.reshape(self.height, self.width, kanaele)

    def to_png_bytes(self):
        from PIL import Image as PILImage

        feld = self.array
        if feld.dtype == np.uint16:  # Tiefe für die Anzeige normieren
            gueltig = feld[feld > 0]
            obergrenze = int(gueltig.max()) if gueltig.size else 1
            feld = (feld.astype(np.float32) / max(obergrenze, 1) * 255).astype(np.uint8)
        puffer = io.BytesIO()
        PILImage.fromarray(feld).save(puffer, format="PNG")
        return puffer.getvalue()

    def save(self, pfad):
        ziel = Path(pfad)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(self.to_png_bytes())
        return ziel

    def __repr__(self):
        return f"<Image {self.source} {self.width}x{self.height}>"


def aufloesen(name, vorhandene):
    if name in vorhandene:
        return name
    for kandidat in KURZNAMEN.get(name, ()):
        if kandidat in vorhandene:
            return kandidat
    kurz = sorted({k for k, werte in KURZNAMEN.items() if any(w in vorhandene for w in werte)})
    raise SpotlabError(
        f"Kamera '{name}' gibt es nicht. Verfügbar: {', '.join(kurz) or 'keine'}."
    )


def cameras(backend):
    vorhandene = set(backend.image_sources())
    return [kurz for kurz, werte in KURZNAMEN.items() if any(w in vorhandene for w in werte)]


def camera(backend, recorder, name):
    require(backend, Capability.CAMERAS, "Kamerabilder aufnehmen")
    quelle = aufloesen(name, backend.image_sources())
    antwort = backend.images([quelle])[0]
    bild = Image(antwort)
    if recorder is not None:
        recorder.image(
            name,
            bild.to_png_bytes(),
            {
                "source": bild.source,
                "width": bild.width,
                "height": bild.height,
                "intrinsics": bild.intrinsics,
            },
        )
    return bild
