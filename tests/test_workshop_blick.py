"""Der Blick beim Fahren: `ansicht.jpg` aus den Frontkameras.

Wer mit W A S D Q E faehrt, will sehen, wohin. Im Uebungsraum rendert MuJoCo das
Zimmer von aussen; am echten Roboter gibt es das nicht -- dort ist der Blick das
Kamerabild. Beides heisst `ansicht.jpg`, und es gibt nie zwei Schreiber.
"""

import io

import pytest

pytest.importorskip("bosdyn.api")
pytest.importorskip("PIL")

import numpy as np  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from spotlab.backends.base import Capability  # noqa: E402
from spotlab.workshop import blick  # noqa: E402


def _antwort(quelle, helligkeit, breite=40, hoehe=20):
    from bosdyn.api import image_pb2

    antwort = image_pb2.ImageResponse()
    antwort.source.name = quelle
    antwort.shot.image.cols, antwort.shot.image.rows = breite, hoehe
    antwort.shot.image.pixel_format = image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8
    antwort.shot.image.format = image_pb2.Image.FORMAT_RAW
    antwort.shot.image.data = bytes([helligkeit]) * (breite * hoehe)
    return antwort


class _Backend:
    def __init__(self, quellen=("frontright_fisheye_image", "frontleft_fisheye_image"),
                 faehigkeiten=Capability.GRAY_CAMERAS, schreibt_ansicht=False):
        self._quellen = list(quellen)
        self._faehigkeiten = faehigkeiten
        self.schreibt_ansicht = schreibt_ansicht
        self.gefragt = []

    def capabilities(self):
        return self._faehigkeiten

    def image_sources(self):
        return list(self._quellen)

    def images(self, sources):
        self.gefragt.append(tuple(sources))
        return [_antwort(q, 60 if "right" in q else 200) for q in sources]


class _Spot:
    def __init__(self, backend=None):
        self.backend = backend or _Backend()


# --------------------------------------------------------------------- Bild


def test_die_bilder_stehen_aufrecht_und_rechts_vor_links():
    """Die Frontkameras sind schraeg eingebaut und schauen ueber Kreuz: gedreht
    steht der Boden unten, und `frontright` gehoert LINKS neben `frontleft`.
    Verkehrt herum faehrt man nach der falschen Seite aus."""
    daten = blick.bild_aus([_antwort("frontright_fisheye_image", 60),
                            _antwort("frontleft_fisheye_image", 200)])
    bild = np.asarray(PILImage.open(io.BytesIO(daten)))
    assert bild.ndim == 2 and bild.shape[1] > bild.shape[0]
    links = bild[:, : bild.shape[1] // 2]
    rechts = bild[:, bild.shape[1] // 2 :]
    assert links[links > 0].mean() < rechts[rechts > 0].mean(), "rechts/links vertauscht"
    # Gedreht: aus 40x20 wird ein hoeheres Bild als das Original.
    assert bild.shape[0] > 20


def test_ohne_bild_wird_es_laut():
    with pytest.raises(ValueError):
        blick.bild_aus([])


# ------------------------------------------------------------------ Schreiben


def test_einmal_schreibt_die_ansicht(tmp_path):
    spot = _Spot()
    b = blick.Blick(spot, tmp_path)
    assert b.einmal() and b.bilder == 1
    ziel = tmp_path / blick.DATEI
    assert ziel.is_file() and ziel.stat().st_size > 100
    assert not list(tmp_path.glob("*.tmp")), "atomar geschrieben"
    assert spot.backend.gefragt == [("frontright_fisheye_image", "frontleft_fisheye_image")]


def test_ein_fehler_beim_bild_haelt_den_lauf_nicht_an(tmp_path):
    """Ohne Bild faehrt man weiter (der Mensch steht daneben), ohne Fahrbefehle nicht."""
    class _Kaputt(_Backend):
        def images(self, sources):
            raise RuntimeError("Kamera antwortet nicht")

    b = blick.Blick(_Spot(_Kaputt()), tmp_path)
    assert b.einmal() is False and b.fehler == 1
    assert "Kamera antwortet nicht" in b.letzter_fehler
    assert not (tmp_path / blick.DATEI).exists()


# --------------------------------------------------------------------- Start


def test_wer_selbst_rendert_bekommt_keinen_blick(tmp_path):
    """MuJoCo zeichnet das Zimmer von aussen -- zum Fahren besser als ein
    Fischauge, und zwei Schreiber auf einer Datei gibt es nie."""
    spot = _Spot(_Backend(schreibt_ansicht=True))
    assert blick.starte(spot, tmp_path) is None


def test_ohne_graustufenkameras_kein_blick(tmp_path):
    ohne = _Spot(_Backend(faehigkeiten=Capability.LOCOMOTION))
    assert blick.starte(ohne, tmp_path) is None
    fehlend = _Spot(_Backend(quellen=("back_fisheye_image",)))
    assert blick.starte(fehlend, tmp_path) is None


def test_mit_kameras_laeuft_der_blick(tmp_path):
    spot = _Spot()
    b = blick.starte(spot, tmp_path, takt_s=0.01)
    assert b is not None
    try:
        frist = __import__("time").monotonic() + 5.0
        while b.bilder == 0 and __import__("time").monotonic() < frist:
            __import__("time").sleep(0.02)
        assert b.bilder >= 1 and (tmp_path / blick.DATEI).is_file()
    finally:
        b.beenden()
    assert not b.is_alive()


def test_das_mujoco_backend_sagt_dass_es_selbst_rendert():
    """Die Verabredung steht am Backend, nicht in einer Liste von Namen."""
    pytest.importorskip("spotsim")
    from spotlab.backends.mujoco import MujocoBackend

    assert MujocoBackend.schreibt_ansicht is True


# ------------------------------------------------------------------ Fahrmodus


def test_fahre_startet_und_beendet_den_blick(tmp_path):
    from spotlab.workshop.fahren import fahre

    class _FahrSpot(_Spot):
        def __init__(self):
            super().__init__()
            self.kommandos = []

        def walk(self, **kw):
            self.kommandos.append(kw)

        def stop(self):
            self.kommandos.append("stop")

    spot = _FahrSpot()
    takte = {"n": 0}

    def laeuft():
        takte["n"] += 1
        return takte["n"] <= 3

    fahre(spot, tmp_path, schlaf=lambda _s: None, laeuft=laeuft)
    # Der Blick lief nebenher und ist am Ende beendet -- kein Thread bleibt zurueck.
    assert not [t for t in __import__("threading").enumerate() if t.name == "spotlab-blick"]
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
