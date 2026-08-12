"""Bildmitschnitt im Beobachter-Modus: fünf Kameras im eigenen Takt.

Eigener Thread neben `StateSampler`, aus zwei Gründen getrennt: Bilder sind um
Grössenordnungen teurer als ein `RobotState`, und sie dürfen die Messung, um die
es eigentlich geht, nicht ausbremsen. Bleibt ein Bildabruf im WLAN hängen,
verlangsamt das den Bildtakt — nicht die Zustandsabtastung.

Bytes werden WÖRTLICH geschrieben, so wie der Roboter sie geschickt hat: JPEG
als `.jpg`, alles andere als `.raw`. Kein Umkodieren im Aufnahmepfad. Das ist
schneller, und vor allem verlustfrei — `api/perception.py::to_png_bytes()`
normiert Tiefenbilder für die ANZEIGE auf 8 Bit und zerstört dabei genau die
metrische Information, für die wir sie aufnehmen.

Was sich nie ändert (Intrinsik, Extrinsik, Tiefenskala), steht einmal in
`kamera/quellen.json`. Der Zeilenindex `kamera/kamera.jsonl` bleibt dadurch
schlank genug, um ihn nach einer Stunde noch am Stück zu lesen.
"""

import json
import threading
import time

from spotlab.beobachtung.bildquelle import ABRUF_FRIST_S


def _name_von(enum_typ, wert):
    try:
        return enum_typ.Name(wert)
    except (ValueError, KeyError):
        return str(wert)


def _sekunden(zeitstempel):
    return zeitstempel.seconds + zeitstempel.nanos * 1e-9


def _koerperpose(schnappschuss):
    """odom→body zum AUFNAHMEZEITPUNKT, oder None.

    Damit liegt jedes Bild exakt im selben Bezugsrahmen wie `zustand.jsonl` —
    ohne zwischen zwei Abtastungen zu interpolieren. Bei 0.3 m/s und 10 Hz wären
    das sonst gut anderthalb Zentimeter Ansetzfehler pro Bild.

    None heisst „nicht gemessen". Ein Ursprung wäre eine erfundene Pose und
    mittelte sich durch jede spätere Auswertung.
    """
    from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b

    try:
        pose = get_a_tform_b(schnappschuss, ODOM_FRAME_NAME, BODY_FRAME_NAME)
    except Exception:
        return None
    if pose is None:
        return None
    return [
        pose.position.x,
        pose.position.y,
        pose.position.z,
        pose.rotation.w,
        pose.rotation.x,
        pose.rotation.y,
        pose.rotation.z,
    ]


def _endung(bild):
    """`bild` ist `shot.image`, NICHT `shot` — `format` sitzt am inneren Proto."""
    from bosdyn.api import image_pb2

    return "jpg" if bild.format == image_pb2.Image.FORMAT_JPEG else "raw"


def _quellenblatt(antwort):
    """Die unveränderlichen Angaben einer Quelle — einmal je Messfahrt."""
    from bosdyn.api import image_pb2
    from google.protobuf import json_format

    quelle = antwort.source
    pinhole = quelle.pinhole.intrinsics
    return {
        "name": quelle.name,
        "cols": quelle.cols,
        "rows": quelle.rows,
        "bildart": _name_von(image_pb2.ImageSource.ImageType, quelle.image_type),
        # 0.0 bedeutet beim Spot „nicht gesetzt" (Graustufenkamera), nicht
        # „Skala null". Als None ist der Unterschied in der Auswertung sichtbar.
        "tiefenskala": quelle.depth_scale or None,
        "intrinsik": {
            "fx": pinhole.focal_length.x,
            "fy": pinhole.focal_length.y,
            "cx": pinhole.principal_point.x,
            "cy": pinhole.principal_point.y,
        },
        "sensorrahmen": antwort.shot.frame_name_image_sensor,
        # Der ganze Schnappschuss: darin steht die feste Kante body→Sensor, also
        # die Extrinsik. Einmal reicht — sie ändert sich während der Fahrt nicht.
        "rahmenbaum": json_format.MessageToDict(antwort.shot.transforms_snapshot),
    }


class Bildmitschnitt:
    """Holt in festem Takt Bilder und legt sie neben die Aufzeichnung.

    Wirft nie nach aussen. Ein Bildabruf, der scheitert, wird gezählt und beim
    nächsten Takt erneut versucht — eine misslungene Aufnahme darf die Messfahrt
    nicht kippen, aber sie darf auch nicht unsichtbar bleiben: `zaehler()` ist
    die Grundlage der Meldung am Ende des Drehbuchs.
    """

    def __init__(self, quelle, recorder, hz=1.0):
        self._quelle = quelle
        self._recorder = recorder
        self._hz = float(hz)
        self._periode = 1.0 / self._hz if self._hz > 0 else 0.0
        self._stopp = threading.Event()
        self._thread = None
        self._sperre = threading.Lock()
        self._takt = 0
        self._bilder = 0
        self._bytes = 0
        self._fehler = 0
        self._letzter_fehler = None
        self._gesehen = set()
        self._quellenblatt = {}
        self._t0 = None

    # ----------------------------------------------------------- Steuerung

    def start(self):
        if self._thread is not None or self._periode <= 0:
            return
        self._t0 = time.monotonic()
        self._thread = threading.Thread(
            target=self._schleife, name="spotlab-bilder", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=ABRUF_FRIST_S + 2.0):
        """Anhalten und das Quellenblatt festschreiben.

        Grosszügigere Frist als beim Abtaster: ein Bildabruf ist um
        Grössenordnungen teurer, und die letzten Bilder sind es wert, auf sie zu
        warten. Läuft die Frist ab, ist der Thread ein Daemon und stirbt mit dem
        Prozess — geschriebene Bilder sind durch den anhängenden Index bereits
        gültig.
        """
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._schreibe_quellenblatt()

    def setze_rate(self, hz):
        """Wirkt ab dem nächsten Takt. Für Abschnitte, in denen die Bilder der
        Zweck sind und nicht die Beifracht.

        Startet nichts: ein Mitschnitt, der mit 0 Hz aufgesetzt wurde, hat gar
        keinen Thread, und ihn hier nachträglich anzuwerfen umginge die
        Entscheidung „keine Bilder" an der einzigen Stelle, wo sie steht.
        """
        with self._sperre:
            self._hz = float(hz)
            self._periode = 1.0 / self._hz if self._hz > 0 else 0.0

    def zaehler(self):
        with self._sperre:
            dauer = (time.monotonic() - self._t0) if self._t0 else 0.0
            return {
                "saetze": self._takt,
                "bilder": self._bilder,
                "bytes": self._bytes,
                "fehler": self._fehler,
                "letzter_fehler": self._letzter_fehler,
                "hz_soll": self._hz,
                "hz_ist": round(self._takt / dauer, 2) if dauer > 0 else None,
            }

    # ----------------------------------------------------------- Innenleben

    def _schreibe_quellenblatt(self):
        if not self._quellenblatt:
            return
        try:
            self._recorder.kamera_beilage(
                "quellen.json",
                json.dumps(
                    list(self._quellenblatt.values()),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            )
        except OSError:
            pass

    def _einmal(self):
        try:
            antworten = self._quelle.bilder()
        except Exception as fehler:
            with self._sperre:
                self._fehler += 1
                self._letzter_fehler = f"{type(fehler).__name__}: {fehler}"
            return
        with self._sperre:
            self._takt += 1
            nummer = self._takt
        for antwort in antworten:
            try:
                self._lege_ab(nummer, antwort)
            except Exception as fehler:      # eine kaputte Kamera, nicht alle
                with self._sperre:
                    self._fehler += 1
                    self._letzter_fehler = f"{type(fehler).__name__}: {fehler}"

    def _lege_ab(self, nummer, antwort):
        from bosdyn.api import image_pb2

        aufnahme = antwort.shot
        name = antwort.source.name or "unbenannt"
        if name not in self._gesehen:
            self._gesehen.add(name)
            self._quellenblatt[name] = _quellenblatt(antwort)
        roh = aufnahme.image.data
        self._recorder.kamerabild(
            nummer,
            name,
            roh,
            _endung(aufnahme.image),
            {
                # Roboteruhr, NICHT umgerechnet -- derselbe Schluessel und
                # dieselbe Zeitbasis wie in zustand.jsonl, damit sich Bild und
                # Zustand ohne Umweg zusammenfuehren lassen.
                "t_robot": _sekunden(aufnahme.acquisition_time),
                "rows": aufnahme.image.rows,
                "cols": aufnahme.image.cols,
                "format": _name_von(image_pb2.Image.Format, aufnahme.image.format),
                "pixel": _name_von(image_pb2.Image.PixelFormat, aufnahme.image.pixel_format),
                "pose": _koerperpose(aufnahme.transforms_snapshot),
            },
        )
        with self._sperre:
            self._bilder += 1
            self._bytes += len(roh)

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            with self._sperre:
                periode = self._periode
            self._einmal()
            # Nichts nachholen -- dieselbe Regel wie beim Abtaster. Ein Burst
            # nach einer Stoerung saehe in der Auswertung wie ein dichter
            # abgetasteter Abschnitt aus.
            rest = periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
