"""Das Panorama der Frontkameras -- geprueft an einer echten Aufzeichnung.

`tests/daten/blick_real_20260812/HERKUNFT.md`: zwei Bildpaare vom Schul-Spot
samt Intrinsik und Rahmenbaum, zu genau den `ImageResponse`-Nachrichten
zusammengesetzt, die der ImageService liefert. Keine Attrappe -- an einer
erfundenen Kalibrierung faellt ein Vorzeichenfehler nie auf.
"""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("bosdyn.api")
pytest.importorskip("PIL")

from spotlab.backends.real import panorama  # noqa: E402
from spotlab.errors import SpotlabError  # noqa: E402

DATEN = Path(__file__).parent / "daten" / "blick_real_20260812"
RECHTS, LINKS = "frontright_fisheye_image", "frontleft_fisheye_image"


def _antwort(takt, name, zeit_ns=1_000_000_000):
    from bosdyn.api import geometry_pb2, image_pb2
    from google.protobuf import json_format

    quelle = next(q for q in json.loads((DATEN / "quellen.json").read_text(encoding="utf-8"))
                  if q["name"] == name)
    antwort = image_pb2.ImageResponse()
    antwort.source.name = name
    antwort.source.cols, antwort.source.rows = quelle["cols"], quelle["rows"]
    innen = antwort.source.pinhole.intrinsics
    innen.focal_length.x, innen.focal_length.y = quelle["intrinsik"]["fx"], quelle["intrinsik"]["fy"]
    innen.principal_point.x, innen.principal_point.y = quelle["intrinsik"]["cx"], quelle["intrinsik"]["cy"]
    antwort.shot.frame_name_image_sensor = quelle["sensorrahmen"]
    json_format.ParseDict(quelle["rahmenbaum"], antwort.shot.transforms_snapshot)
    seite = "frontright" if "right" in name else "frontleft"
    antwort.shot.image.data = (DATEN / f"takt{takt}_{seite}.jpg").read_bytes()
    antwort.shot.image.cols, antwort.shot.image.rows = quelle["cols"], quelle["rows"]
    antwort.shot.image.format = image_pb2.Image.FORMAT_JPEG
    antwort.shot.image.pixel_format = image_pb2.Image.PIXEL_FORMAT_GREYSCALE_U8
    antwort.shot.acquisition_time.FromNanoseconds(zeit_ns)
    assert isinstance(antwort.shot.transforms_snapshot, geometry_pb2.FrameTreeSnapshot)
    return antwort


def _paar(takt):
    return [_antwort(takt, RECHTS), _antwort(takt, LINKS)]


@pytest.fixture(scope="module")
def kameras():
    return panorama.kalibrierung_aus(_paar(90))


@pytest.fixture(scope="module")
def pano(kameras):
    return panorama.Panorama(kameras)


# ------------------------------------------------------------ Kalibrierung


def test_die_kalibrierung_kommt_aus_der_nachricht(kameras):
    """Die rechte Kamera blickt nach LINKS-vorn, die linke nach rechts-vorn (ueber
    Kreuz), beide nach unten. Genau das steht im Rahmenbaum -- nirgends sonst."""
    rechts, links = kameras
    assert (rechts.name, links.name) == (RECHTS, LINKS)
    assert (rechts.breite, rechts.hoehe) == (640, 480) and rechts.fx == pytest.approx(329.1, abs=0.1)
    achse_r, achse_l = rechts.lage[:3, 2], links.lage[:3, 2]
    assert achse_r[1] > 0.4 and achse_l[1] < -0.4, "ueber Kreuz: rechts schaut nach links"
    assert achse_r[2] < -0.2 and achse_l[2] < -0.2, "beide nach unten"
    assert rechts.lage[1, 3] < 0 < links.lage[1, 3], "rechts sitzt rechts (Koerper-y negativ)"


def test_ohne_extrinsik_kein_panorama():
    antwort = _antwort(90, RECHTS)
    antwort.shot.frame_name_image_sensor = "gibtsnicht"
    with pytest.raises(SpotlabError, match="Rahmenbaum"):
        panorama.kalibrierung_aus([antwort])


def test_die_aufnahmezeit_ist_der_stempel_der_kamera():
    assert panorama.aufnahmezeit(_antwort(90, RECHTS, zeit_ns=123_456_789)) == 123_456_789


# ---------------------------------------------------------------- Geometrie


def test_das_panorama_ist_ein_volles_rechteck_im_seitenverhaeltnis(pano):
    """Kein schwarzer Rand, nie: jedes Pixel kommt aus mindestens einer Kamera,
    und der Ausschnitt ist 16:9 wie auf dem Tablet."""
    assert pano.breite >= 600 and pano.hoehe == pytest.approx(pano.breite * 9 / 16, abs=1)
    ohne = panorama.Panorama(pano.kameras, ausgleich=False)
    eins = np.full((480, 640), 100, np.uint8)
    zwei = np.full((480, 640), 200, np.uint8)
    aus = ohne.zusammensetzen([eins, zwei])
    assert aus.shape == (pano.hoehe, pano.breite)
    assert aus.min() >= 100 and aus.max() <= 200, "ein Pixel kam aus keiner Kamera"
    # Rechts (Kamera 1) liegt links im Bild, links (Kamera 2) rechts -- ueber Kreuz.
    assert aus[:, :20].mean() == 100 and aus[:, -20:].mean() == 200
    assert pano.ueberlappung_px > 10_000, "in der Mitte sehen beide Kameras dasselbe"


def test_in_der_ueberlappung_stimmen_die_bilder_ueberein(pano):
    """Die Probe auf die Geometrie: wo beide Kameras hinsehen, muessen sie
    dasselbe zeigen. Mit vertauschter Kalibrierung ist der Fehler dreimal so gross."""
    bilder = panorama.bilder_aus(_paar(90))

    def fehler(a, b):
        a, b = a.astype(np.float32), b.astype(np.float32)
        return float(np.abs((a - a.mean()) - (b - b.mean())).mean())

    richtig = fehler(*pano.proben(bilder))
    vertauscht = fehler(*pano.proben(bilder[::-1]))
    assert richtig < 12, richtig
    assert vertauscht > 2 * richtig, (richtig, vertauscht)


def test_der_helligkeitsausgleich_zieht_die_kameras_zusammen(pano):
    """Takt 60: dieselbe Szene, 112 gegen 64 im Mittel -- die Kameras belichten
    getrennt. Ohne Ausgleich steht in der Mitte eine Kante."""
    bilder = panorama.bilder_aus(_paar(60))
    roh_a, roh_b = pano.proben(bilder, ausgleich=False)
    assert roh_a.mean() - roh_b.mean() > 30, "die Aufnahme zeigt die getrennte Belichtung"
    a, b = pano.proben(bilder)
    assert abs(float(a.mean()) - float(b.mean())) < 3, (a.mean(), b.mean())
    # Und das fertige Bild traegt den Abgleich: die Mitte ist kein Sprung mehr.
    aus = pano.zusammensetzen(bilder)
    assert aus.shape == (pano.hoehe, pano.breite) and aus.dtype == np.uint8


def test_farbe_bleibt_farbe_und_grau_bleibt_grau(pano):
    grau = panorama.bilder_aus(_paar(90))
    assert pano.zusammensetzen(grau).ndim == 2
    farbe = [np.repeat(g[..., None], 3, axis=2) for g in grau]
    aus = pano.zusammensetzen(farbe)
    assert aus.shape == (pano.hoehe, pano.breite, 3)
    assert np.array_equal(aus[..., 0], aus[..., 2])


def test_eine_fremde_bildgroesse_wird_abgewiesen(pano):
    with pytest.raises(SpotlabError, match="Karte gilt"):
        pano.zusammensetzen([np.zeros((240, 320), np.uint8), np.zeros((480, 640), np.uint8)])


# ============ Zweiter Zuschnitt: alles Gesehene, fuer Erkenner
#
# Die Fahransicht ist das groesste voll gedeckte Rechteck -- und reicht damit nur
# 7 Grad nach oben. Ein stehender Mensch hat darin nie ein Gesicht. Das volle
# Feld reicht 26 Grad hinauf; genau diese 19 Grad entscheiden.


def test_das_volle_feld_schaut_viel_weiter_hinauf(kameras):
    fahren = panorama.Panorama(kameras)
    alles = panorama.Panorama(kameras, zuschnitt=panorama.ALLES)
    assert alles.hoehe > fahren.hoehe and alles.breite > fahren.breite

    oben_fahren = fahren.winkel(fahren.breite / 2, 0)[1]
    oben_alles = alles.winkel(alles.breite / 2, 0)[1]
    assert oben_fahren == pytest.approx(6.7, abs=0.5)
    assert oben_alles == pytest.approx(26.2, abs=0.5)


def test_eine_spalte_ist_ein_azimut_und_eine_zeile_ein_hoehenwinkel(kameras):
    pano = panorama.Panorama(kameras, zuschnitt=panorama.ALLES)
    mitte_peilung, _ = pano.winkel(pano.breite / 2, pano.hoehe / 2)
    assert mitte_peilung == pytest.approx(0.0, abs=1.5), "die Mitte schaut nach vorn"

    links, _ = pano.winkel(0, pano.hoehe / 2)
    rechts, _ = pano.winkel(pano.breite - 1, pano.hoehe / 2)
    assert links > 0 > rechts, "Peilung links positiv, wie ueberall"
    assert abs(links) == pytest.approx(abs(rechts), abs=2.0)

    _, oben = pano.winkel(pano.breite / 2, 0)
    _, unten = pano.winkel(pano.breite / 2, pano.hoehe - 1)
    assert oben > 0 > unten, "Hoehenwinkel nach oben positiv"


def test_die_kamerahoehe_kommt_aus_der_kalibrierung(kameras):
    pano = panorama.Panorama(kameras, zuschnitt=panorama.ALLES)
    # Koerpermitte 0.51 m ueber dem Boden, die Kameras sitzen knapp darunter.
    assert pano.kamerahoehe() == pytest.approx(0.46, abs=0.02)


def test_ein_stehender_mensch_hat_erst_ab_zweieinhalb_metern_ein_gesicht(kameras):
    """Die Messung, die den Gesichts-Finder begrenzt -- keine Behauptung."""
    import math

    pano = panorama.Panorama(kameras, zuschnitt=panorama.ALLES)
    _, oben = pano.winkel(pano.breite / 2, 0)
    hoehe = pano.kamerahoehe()

    def sichtbar_bis(abstand):
        return hoehe + abstand * math.tan(math.radians(oben))

    assert sichtbar_bis(1.5) < 1.3, "auf anderthalb Metern sieht Spot Beine"
    assert sichtbar_bis(3.0) > 1.7, "ab drei Metern ist ein Kopf im Bild"
