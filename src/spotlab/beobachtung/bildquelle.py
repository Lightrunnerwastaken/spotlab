"""Die Nur-Lese-Bildquelle — zweite Hälfte der Sicherheitsaussage.

Gebaut wie `quelle.Zustandsquelle`: genau EINE Methode, keine Kommando-Methode,
kein Lease, kein Not-Aus-Endpunkt. `ImageClient` liest nur. Der Bildmitschnitt
nimmt dem Tablet damit ebenso wenig weg wie die Zustandsabtastung, und die
Aussage „der Beobachter kann den Roboter nicht bewegen" bleibt unverändert
gültig — sie hängt an der Oberfläche dieser Klassen, nicht an einer Prüfung zur
Laufzeit.

Die Quellnamen werden gegen die vom Roboter GEMELDETEN Quellen aufgelöst, nie
gegen eine fest verdrahtete Liste — dieselbe Begründung wie in
`api/perception.py` (Spec A2: die Benennung ist eine unbestätigte Annahme).
"""

# Reihenfolge = Aufnahmereihenfolge. Vorne zuerst: bricht der Takt unter WLAN-Last
# zusammen, fehlen die hinteren Kameras, nicht die interessanten.
FISHEYE = (
    "frontleft_fisheye_image",
    "frontright_fisheye_image",
    "left_fisheye_image",
    "right_fisheye_image",
    "back_fisheye_image",
)
TIEFE = (
    "frontleft_depth",
    "frontright_depth",
    "left_depth",
    "right_depth",
    "back_depth",
)


def waehle_quellen(gemeldet, tiefe=False):
    """Die Quellen, die wir mitschreiben — geschnitten mit dem, was es gibt.

    Ein Name, den der Roboter nicht meldet, würde `get_image_from_sources()`
    für den GANZEN Abruf scheitern lassen. Ein Tippfehler oder ein anderes
    Kameramodell kostete damit nicht eine Kamera, sondern alle.
    """
    vorhanden = set(gemeldet)
    namen = FISHEYE + TIEFE if tiefe else FISHEYE
    return tuple(n for n in namen if n in vorhanden)


# Zeitgrenze eines einzelnen Bildabrufs. Ohne sie hinge der Bildthread an einem
# abgerissenen WLAN bis zum Ende der Messfahrt — und der Zähler zeigte weiterhin
# den letzten Stand, also „alles gut", während längst nichts mehr ankommt.
ABRUF_FRIST_S = 5.0


# JPEG-Güte der Fischaugenbilder. 75 ist die Vorgabe des SDK und für eine
# Live-Ansicht richtig; für eine Aufzeichnung, die einmal stattfindet, ist die
# verlorene Information nicht wiederzubeschaffen. 90 kostet grob ein Drittel
# mehr Bandbreite. Tiefenbilder sind davon unberührt — die kommen roh.
GUETE = 90


class Bildquelle:
    """Nur-Lese-Zugang zu den Kameras. Genau eine Methode."""

    def __init__(self, image_client, quellen, frist=ABRUF_FRIST_S, guete=GUETE):
        from bosdyn.client.image import build_image_request

        self._image = image_client
        self._anfragen = [
            build_image_request(name, quality_percent=guete) for name in quellen
        ]
        self._frist = frist

    def bilder(self):
        return self._image.get_image(self._anfragen, timeout=self._frist)


def gemeldete_quellen(image_client):
    """Namen der Quellen, die der Roboter anbietet."""
    return [q.name for q in image_client.list_image_sources()]


class TrockeneBildquelle:
    """Bildquelle für die Trockenprobe — baut ECHTE `ImageResponse`-Protos.

    Dieselbe Haltung wie `DryRunBackend`: das Testdouble fälscht die Daten, nicht
    das Format. Nur so beweist die Probe etwas über die Kette, die nachher am
    Roboter läuft — sie durchläuft dieselbe Fallunterscheidung (JPEG wörtlich,
    alles andere roh), dieselbe Namensbildung und denselben Index.

    `DryRunBackend` bekommt hierfür bewusst KEINE Kameras: dort hängt die
    Fähigkeitsmenge dran, und `spot.camera()` im Schülertrockenlauf soll
    weiterhin ehrlich sagen, dass es keine Kamera gibt.
    """

    BREITE = 64
    HOEHE = 48

    def __init__(self, quellen=FISHEYE, uhr=None):
        import time

        self._quellen = list(quellen)
        self._uhr = uhr or time.time
        self._takt = 0

    def bilder(self):
        self._takt += 1
        return [self._eine(name) for name in self._quellen]

    def _eine(self, name):
        from bosdyn.api import image_pb2

        antwort = image_pb2.ImageResponse()
        antwort.source.name = name
        antwort.source.cols = self.BREITE
        antwort.source.rows = self.HOEHE
        antwort.source.pinhole.intrinsics.focal_length.x = 200.0
        antwort.source.pinhole.intrinsics.focal_length.y = 200.0
        antwort.source.pinhole.intrinsics.principal_point.x = self.BREITE / 2
        antwort.source.pinhole.intrinsics.principal_point.y = self.HOEHE / 2

        aufnahme = antwort.shot
        aufnahme.frame_name_image_sensor = f"{name}_sensor"
        aufnahme.transforms_snapshot.CopyFrom(self._rahmenbaum())
        jetzt = self._uhr()
        aufnahme.acquisition_time.seconds = int(jetzt)
        aufnahme.acquisition_time.nanos = int((jetzt % 1) * 1e9)
        aufnahme.image.cols = self.BREITE
        aufnahme.image.rows = self.HOEHE

        if name.endswith("_depth"):
            antwort.source.depth_scale = 1000.0
            antwort.source.image_type = image_pb2.ImageSource.IMAGE_TYPE_DEPTH
            aufnahme.image.format = image_pb2.Image.FORMAT_RAW
            aufnahme.image.pixel_format = image_pb2.Image.PIXEL_FORMAT_DEPTH_U16
            aufnahme.image.data = self._tiefe_roh()
        else:
            antwort.source.image_type = image_pb2.ImageSource.IMAGE_TYPE_VISUAL
            aufnahme.image.format = image_pb2.Image.FORMAT_JPEG
            aufnahme.image.pixel_format = image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8
            aufnahme.image.data = self._jpeg()
        return antwort

    def _rahmenbaum(self):
        """vision → odom → body, mit wanderndem Körper.

        Ohne Rahmenbaum bliebe `pose` in der Probe immer None — und damit wäre
        genau das Feld ungeprüft, das Bild und Fahrtweg zusammenführt. Der
        Körper wandert je Takt, damit die Probe auch zeigt, dass die Pose je
        Aufnahme neu gelesen wird und nicht einmal beim Start.
        """
        from bosdyn.api import geometry_pb2
        from bosdyn.client.frame_helpers import (
            BODY_FRAME_NAME,
            ODOM_FRAME_NAME,
            VISION_FRAME_NAME,
        )

        def kante(eltern, x=0.0, z=0.0):
            rand = geometry_pb2.FrameTreeSnapshot.ParentEdge()
            rand.parent_frame_name = eltern
            rand.parent_tform_child.position.x = x
            rand.parent_tform_child.position.z = z
            rand.parent_tform_child.rotation.w = 1.0
            return rand

        baum = geometry_pb2.FrameTreeSnapshot()
        # Die Wurzel braucht einen EIGENEN, elternlosen Eintrag. Ohne ihn läuft
        # `validate_frame_tree_snapshot()` beim Hochlaufen ins Leere und wirft
        # `ValidateFrameTreeUnknownFrameError` — der Baum sähe vollständig aus.
        baum.child_to_parent_edge_map[VISION_FRAME_NAME].CopyFrom(
            geometry_pb2.FrameTreeSnapshot.ParentEdge()
        )
        baum.child_to_parent_edge_map[ODOM_FRAME_NAME].CopyFrom(kante(VISION_FRAME_NAME))
        baum.child_to_parent_edge_map[BODY_FRAME_NAME].CopyFrom(
            kante(ODOM_FRAME_NAME, x=0.1 * self._takt, z=0.52)
        )
        return baum

    def _tiefe_roh(self):
        """Ein Verlauf in Millimetern, U16 little-endian — wie der echte Spot."""
        import struct

        werte = [
            (1000 + 10 * ((x + self._takt) % 100)) for x in range(self.BREITE * self.HOEHE)
        ]
        return struct.pack(f"<{len(werte)}H", *werte)

    def _jpeg(self):
        """Ein echtes JPEG. Ein Platzhalter aus Zufallsbytes durchliefe zwar den
        Schreibweg, aber niemand sähe in der Probe, ob die Datei nachher
        aufgeht."""
        import io

        from PIL import Image as PILImage

        bild = PILImage.new("L", (self.BREITE, self.HOEHE), color=(self._takt * 7) % 256)
        puffer = io.BytesIO()
        bild.save(puffer, format="JPEG")
        return puffer.getvalue()
