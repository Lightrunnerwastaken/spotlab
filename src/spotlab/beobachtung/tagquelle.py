"""Die Nur-Lese-Tagquelle — dritte Hälfte der Sicherheitsaussage.

Gebaut wie `quelle.Zustandsquelle` und `bildquelle.Bildquelle`: genau EINE
Methode, keine Kommando-Methode, kein Lease, kein Not-Aus-Endpunkt.
`WorldObjectClient` liest nur. Der Tagmitschnitt nimmt dem Tablet damit ebenso
wenig weg wie die Zustandsabtastung, und die Aussage „der Beobachter kann den
Roboter nicht bewegen" bleibt unverändert gültig — sie hängt an der Oberfläche
dieser Klassen, nicht an einer Prüfung zur Laufzeit.

WOFÜR. Für den Versuch „der Tag ist der Lehrer"
(`matura-spot/notes/VISION_umweltbezug.md`): ein Mensch fährt Spot mit dem
Tablet an einem Stuhl mit AprilTag vorbei, und der Tag liefert bei jedem Bild
ein exaktes, kostenloses Label — „hier ist der Stuhl". Bilder schreibt der
Beobachter längst mit; die Tag-Beobachtungen fehlten.

GEFRAGT WIRD NUR NACH FIDUCIALS. Alles zu holen wäre mehr Bandbreite für
Objekte, die niemand labelt, und der Mitschnitt läuft eine halbe Stunde. Wer
später etwas anderes lernen will, gibt `arten` mit.
"""


def _fiducial_typ():
    from bosdyn.api import world_object_pb2 as wo

    return [wo.WORLD_OBJECT_APRILTAG]


class Tagquelle:
    """Nur-Lese-Zugang zu den erkannten Objekten. Genau eine Methode."""

    def __init__(self, world_object_client, arten=None):
        self._client = world_object_client
        self._arten = _fiducial_typ() if arten is None else list(arten)

    def objekte(self):
        antwort = self._client.list_world_objects(object_type=self._arten)
        return list(antwort.world_objects)


# Lage des Attrappen-Tags im Vision-Rahmen: zwei Meter voraus, einen halben
# links, auf Kniehöhe. Feste Zahlen, weil der Stuhl STILLSTEHT — ein wandernder
# Attrappen-Tag verdeckte in der Probe einen Fehler, den es am Gerät nicht gibt.
TROCKEN_LAGE = (2.0, 0.5, 0.45)
TROCKEN_TAG = 1
# Kantenlänge des Boston-Dynamics-Fiducials in Metern (Sollmass; ein auf A4
# „an Seite angepasst" gedrucktes PDF misst 133 mm — siehe spotlab A22).
TAG_KANTE_M = 0.146


class TrockeneTagquelle:
    """Tagquelle für die Trockenprobe — baut ECHTE `WorldObject`-Protos.

    Dieselbe Haltung wie `TrockeneBildquelle` und `DryRunBackend`: die Attrappe
    fälscht die ZAHLEN, nicht das Format. Nur so beweist die Probe etwas über
    die Kette, die nachher am Roboter läuft — sie durchläuft dieselbe
    Serialisierung, denselben Schreibweg und denselben Index.

    Der Schnappschuss trägt `vision` als Elternrahmen: ohne ihn ist die
    Tag-Pose nicht in die Welt zu rechnen, und genau das braucht die
    Labelerzeugung.
    """

    def __init__(self, tag_id=TROCKEN_TAG, lage=TROCKEN_LAGE, uhr=None):
        import time

        self._tag_id = int(tag_id)
        self._lage = tuple(lage)
        self._uhr = uhr or time.time
        self._takt = 0

    def objekte(self):
        self._takt += 1
        return [self._eines()]

    def _eines(self):
        from bosdyn.api import geometry_pb2
        from bosdyn.api import world_object_pb2 as wo

        rahmen = f"fiducial_{self._tag_id}"
        objekt = wo.WorldObject(id=self._tag_id, name=f"world_obj_apriltag_{self._tag_id:03d}")
        jetzt = self._uhr()
        objekt.acquisition_time.seconds = int(jetzt)
        objekt.acquisition_time.nanos = int((jetzt % 1) * 1e9)

        eigenschaften = objekt.apriltag_properties
        eigenschaften.tag_id = self._tag_id
        eigenschaften.dimensions.x = TAG_KANTE_M
        eigenschaften.dimensions.y = TAG_KANTE_M
        eigenschaften.frame_name_fiducial = rahmen
        eigenschaften.frame_name_camera = "frontleft_fisheye"

        kante = objekt.transforms_snapshot.child_to_parent_edge_map[rahmen]
        kante.parent_frame_name = "vision"
        kante.parent_tform_child.CopyFrom(
            geometry_pb2.SE3Pose(
                position=geometry_pb2.Vec3(
                    x=self._lage[0], y=self._lage[1], z=self._lage[2]
                ),
                rotation=geometry_pb2.Quaternion(w=1.0),
            )
        )
        # `vision` selbst als Wurzel: der Rahmenbaum muss den Rahmen KENNEN,
        # sonst findet ihn `get_a_tform_b` nicht.
        objekt.transforms_snapshot.child_to_parent_edge_map["vision"].SetInParent()
        return objekt
