"""Der Blick beim Fahren: `ansicht.jpg` aus den Frontkameras, wie auf dem Tablet.

Wer mit W A S D Q E faehrt, will sehen, wohin. Im Uebungsraum rendert MuJoCo das
Zimmer von aussen; am echten Roboter gibt es das nicht -- dort ist der Blick das
Kamerabild, zu EINEM Rechteck zusammengesetzt. Beides heisst `ansicht.jpg`, und es
gibt nie zwei Schreiber. Die Antworten hier sind echte `ImageResponse`-Nachrichten
aus der Aufzeichnung vom 12.08.2026 (`tests/daten/blick_real_20260812/`).
"""

import io
import json
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("bosdyn.api")
pytest.importorskip("PIL")

import numpy as np  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from spotlab.backends.base import Capability  # noqa: E402
from spotlab.workshop import blick  # noqa: E402

DATEN = Path(__file__).parent / "daten" / "blick_real_20260812"


def _antwort(name, zeit_ns=1_000_000_000, farbe=False, mit_kalibrierung=True):
    from bosdyn.api import image_pb2
    from google.protobuf import json_format

    quelle = next(q for q in json.loads((DATEN / "quellen.json").read_text(encoding="utf-8"))
                  if q["name"] == name)
    antwort = image_pb2.ImageResponse()
    antwort.source.name = name
    seite = "frontright" if "right" in name else "frontleft"
    daten = (DATEN / f"takt90_{seite}.jpg").read_bytes()
    if farbe:
        puffer = io.BytesIO()
        PILImage.open(io.BytesIO(daten)).convert("RGB").save(puffer, format="JPEG", quality=85)
        daten = puffer.getvalue()
    antwort.shot.image.data = daten
    antwort.shot.image.cols, antwort.shot.image.rows = quelle["cols"], quelle["rows"]
    antwort.shot.image.format = image_pb2.Image.FORMAT_JPEG
    antwort.shot.image.pixel_format = (image_pb2.Image.PIXEL_FORMAT_RGB_U8 if farbe
                                       else image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8)
    antwort.shot.acquisition_time.FromNanoseconds(zeit_ns)
    if mit_kalibrierung:
        innen = antwort.source.pinhole.intrinsics
        innen.focal_length.x, innen.focal_length.y = quelle["intrinsik"]["fx"], quelle["intrinsik"]["fy"]
        innen.principal_point.x, innen.principal_point.y = quelle["intrinsik"]["cx"], quelle["intrinsik"]["cy"]
        antwort.shot.frame_name_image_sensor = quelle["sensorrahmen"]
        json_format.ParseDict(quelle["rahmenbaum"], antwort.shot.transforms_snapshot)
    return antwort


class _Backend:
    blick_aus_kameras = True

    def __init__(self, quellen=blick.KAMERAS, faehigkeiten=Capability.GRAY_CAMERAS,
                 farbe=False, mit_kalibrierung=True):
        self._quellen = list(quellen)
        self._faehigkeiten = faehigkeiten
        self.farbe, self.mit_kalibrierung = farbe, mit_kalibrierung
        self.zeit_ns = 1_000_000_000
        self.gefragt = []

    def capabilities(self):
        return self._faehigkeiten

    def image_sources(self):
        return list(self._quellen)

    def images(self, sources, **optionen):
        self.gefragt.append((tuple(sources), optionen))
        return [_antwort(q, self.zeit_ns, self.farbe, self.mit_kalibrierung) for q in sources]

    def naechstes_bild(self):
        self.zeit_ns += 66_000_000


class _Spot:
    def __init__(self, backend=None):
        self.backend = backend or _Backend()


def _gelesen(pfad):
    return np.asarray(PILImage.open(io.BytesIO(Path(pfad).read_bytes())))


# ------------------------------------------------------------------ Schreiben


def test_einmal_schreibt_ein_panorama_in_farbe_erbeten(tmp_path):
    spot = _Spot()
    b = blick.Blick(spot, tmp_path)
    assert b.einmal() and b.bilder == 1 and b.abrufe == 1
    bild = _gelesen(tmp_path / blick.DATEI)
    assert bild.ndim == 2, "die Aufzeichnung ist grau, also bleibt es grau"
    assert bild.shape[1] / bild.shape[0] == pytest.approx(16 / 9, abs=0.01), "ein Rechteck wie das Tablet"
    assert not list(tmp_path.glob("*.tmp")), "atomar geschrieben"
    assert spot.backend.gefragt == [(blick.KAMERAS, {"farbe": True, "guete": blick.GUETE_ANFRAGE})]


def test_farbe_kommt_als_farbe_an(tmp_path):
    b = blick.Blick(_Spot(_Backend(farbe=True)), tmp_path)
    assert b.einmal()
    assert _gelesen(tmp_path / blick.DATEI).ndim == 3


def test_dasselbe_bild_wird_nicht_zweimal_geschrieben(tmp_path):
    """Der Roboter liefert zwischen zwei Aufnahmen dasselbe Bild noch einmal;
    es erneut zu schreiben kostete Platte und einen GUI-Takt fuer nichts."""
    spot = _Spot()
    b = blick.Blick(spot, tmp_path)
    assert b.einmal() and b.einmal()
    assert b.abrufe == 2 and b.bilder == 1
    spot.backend.naechstes_bild()
    assert b.einmal() and b.bilder == 2


def test_ohne_kalibrierung_der_rueckfall_gedreht_nebeneinander(tmp_path):
    b = blick.Blick(_Spot(_Backend(mit_kalibrierung=False)), tmp_path)
    assert b.einmal() and (tmp_path / blick.DATEI).is_file()
    assert b._rueckfall, "ohne Rahmenbaum kein Panorama -- aber ein Bild"


def test_ein_fehler_beim_bild_haelt_den_lauf_nicht_an(tmp_path):
    """Ohne Bild faehrt man weiter (der Mensch steht daneben), ohne Fahrbefehle nicht."""
    class _Kaputt(_Backend):
        def images(self, sources, **optionen):
            raise RuntimeError("Kamera antwortet nicht")

    b = blick.Blick(_Spot(_Kaputt()), tmp_path)
    assert b.einmal() is False and b.fehler == 1
    assert "Kamera antwortet nicht" in b.letzter_fehler
    assert not (tmp_path / blick.DATEI).exists() and not b.aufgegeben


def test_erst_drei_fehler_nacheinander_beenden_den_blick(tmp_path):
    """Ein WLAN-Schluckauf ist keine Aufgabe: ein Erfolg setzt den Zaehler zurueck."""
    class _Wackelig(_Backend):
        plan = iter([False, False, True, False, False, False])

        def images(self, sources, **optionen):
            if not next(self.plan):
                raise RuntimeError("weg")
            return super().images(sources, **optionen)

    b = blick.Blick(_Spot(_Wackelig()), tmp_path)
    assert [b.einmal() for _ in range(3)] == [False, False, True] and not b.aufgegeben
    assert [b.einmal() for _ in range(3)] == [False, False, False] and b.aufgegeben


# --------------------------------------------------------------------- Start


def test_nur_wer_es_erlaubt_bekommt_einen_blick(tmp_path):
    """Eine Erlaubnisliste: ein Sim, der Kameras vortaeuscht und die Ansicht
    selbst rendert, haette als Sperrliste zwei Schreiber auf einer Datei."""
    class _Sim(_Backend):
        blick_aus_kameras = False

    assert blick.starte(_Spot(_Sim()), tmp_path) is None
    from spotlab.backends.real.session import RealSpot

    assert RealSpot.blick_aus_kameras is True
    from spotlab.backends.mujoco import MujocoBackend

    assert not getattr(MujocoBackend, "blick_aus_kameras", False)


def test_ohne_frontkameras_kein_blick(tmp_path):
    ohne = _Spot(_Backend(faehigkeiten=Capability.LOCOMOTION))
    assert blick.starte(ohne, tmp_path) is None
    fehlend = _Spot(_Backend(quellen=("back_fisheye_image",)))
    assert blick.starte(fehlend, tmp_path) is None
    assert blick.starte(object(), tmp_path) is None


def test_der_blick_holt_und_schreibt_in_zwei_threads_und_haelt_an(tmp_path):
    class _Laufend(_Backend):
        def images(self, sources, **optionen):
            antworten = super().images(sources, **optionen)
            self.naechstes_bild()
            return antworten

    b = blick.starte(_Spot(_Laufend()), tmp_path, takt_s=0.005)
    assert b is not None
    try:
        frist = time.monotonic() + 10.0
        while b.bilder < 3 and time.monotonic() < frist:
            time.sleep(0.02)
        assert b.bilder >= 3 and b.abrufe >= b.bilder and (tmp_path / blick.DATEI).is_file()
        assert any(t.name == "spotlab-blick-abruf" for t in threading.enumerate())
    finally:
        b.beenden()
    assert not b.is_alive()
    frist = time.monotonic() + 3.0
    while any(t.name == "spotlab-blick-abruf" for t in threading.enumerate()) and time.monotonic() < frist:
        time.sleep(0.02)
    assert not any(t.name == "spotlab-blick-abruf" for t in threading.enumerate())


# ------------------------------------------------------------------ Fahrmodus


class _FahrSpot(_Spot):
    def __init__(self, backend=None):
        super().__init__(backend)
        self.kommandos = []

    def walk(self, **kw):
        self.kommandos.append(kw)

    def stop(self):
        self.kommandos.append("stop")


def test_fahre_startet_und_beendet_den_blick(tmp_path):
    from spotlab.workshop.fahren import fahre

    spot = _FahrSpot()
    takte = {"n": 0}

    def laeuft():
        takte["n"] += 1
        return takte["n"] <= 3

    fahre(spot, tmp_path, schlaf=lambda _s: None, laeuft=laeuft)
    # Der Blick lief nebenher und ist am Ende beendet -- kein Thread bleibt zurueck.
    assert not [t for t in threading.enumerate() if t.name == "spotlab-blick"]
    assert spot.kommandos[-1] == "stop"


def test_ohne_blick_faehrt_es_auch(tmp_path):
    from spotlab.workshop.fahren import fahre

    class _NurFahren:
        def __init__(self):
            self.kommandos = []

        def walk(self, **kw):
            self.kommandos.append(kw)

        def stop(self):
            self.kommandos.append("stop")

    spot = _NurFahren()          # kein `backend` -- wie die Attrappen der alten Tests
    fahre(spot, tmp_path, schlaf=lambda _s: None, laeuft=lambda: False)
    assert spot.kommandos == ["stop"]
