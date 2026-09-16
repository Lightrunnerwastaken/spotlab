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


# ------------------------------------------------------ Gesichter im Fahrblick


def _an(lauf_dir, gesicht=True):
    from spotlab.record import ansicht

    ansicht.schreibe(lauf_dir, gesicht=gesicht)


def _gruen(bild):
    """Bildpunkte, die deutlich gruener sind als rot und blau -- der Kastenrand.

    Ueber eine Schwelle und nicht ueber die genaue Farbe: JPEG ist verlustbehaftet,
    und eine duenne Linie auf grauem Grund verliert dabei Saettigung.
    """
    if bild.ndim != 3:
        return 0
    r, g, b = (bild[:, :, k].astype(int) for k in range(3))
    return int(((g > r + 40) & (g > b + 40)).sum())


def _rot(bild):
    if bild.ndim != 3:
        return 0
    r, g, b = (bild[:, :, k].astype(int) for k in range(3))
    return int(((r > g + 40) & (r > b + 40)).sum())


def test_ohne_schalter_wird_der_erkenner_nicht_einmal_gerufen(tmp_path):
    """Die Vorgabe. Ein Lauf ohne Schalter darf keine Rechenzeit fuer YuNet kosten --
    der Blick schreibt bis zu dreissig Bilder je Sekunde."""
    gerufen = []
    b = blick.Blick(_Spot(), tmp_path, gesichter_holen=lambda feld: gerufen.append(feld) or [])
    assert b.einmal()
    assert gerufen == []
    assert _gelesen(tmp_path / blick.DATEI).ndim == 2, "grau bleibt grau"


def test_mit_schalter_stehen_die_kaesten_im_bild(tmp_path):
    """Der ganze Zweck: was der Erkenner setzt, sieht man beim Fahren."""
    _an(tmp_path)
    b = blick.Blick(_Spot(), tmp_path,
                    gesichter_holen=lambda _feld: [(120.0, 90.0, 80.0, 80.0, 0.78)])
    assert b.einmal()
    bild = _gelesen(tmp_path / blick.DATEI)
    assert bild.ndim == 3, "fuer gruene Kaesten auf grauem Bild braucht es Farbe"
    assert _gruen(bild) > 50, "der Kastenrand steht im Bild"
    assert b.gesichter == 1


def test_der_erkenner_bekommt_das_bild_das_man_sieht(tmp_path):
    """Kein zweiter Bildweg: erkannt wird auf demselben Feld, das gleich JPEG wird.
    Sonst zeigte der Kasten auf eine Stelle, die es im gezeigten Bild nicht gibt."""
    _an(tmp_path)
    gesehen = []
    b = blick.Blick(_Spot(), tmp_path,
                    gesichter_holen=lambda feld: gesehen.append(feld) or [])
    assert b.einmal()
    [feld] = gesehen
    bild = _gelesen(tmp_path / blick.DATEI)
    assert feld.shape[:2] == bild.shape[:2]


def test_ein_fehlendes_modell_steht_im_BILD_und_wird_nicht_dauernd_neu_versucht(tmp_path):
    """Die Lehre vom 11.09.2026: ein Ausfall, der einmal ins Protokoll geht, ist
    beim Messen unsichtbar. Hier steht er dort, wo der Mensch ohnehin hinschaut."""
    from spotlab.errors import SpotlabError

    versuche = {"n": 0}

    def kaputt(_feld):
        versuche["n"] += 1
        raise SpotlabError("Das Gesichtsmodell fehlt (gesucht: irgendwo).")

    _an(tmp_path)
    spot = _Spot()
    b = blick.Blick(spot, tmp_path, gesichter_holen=kaputt)
    assert b.einmal()
    bild = _gelesen(tmp_path / blick.DATEI)
    assert _rot(bild) > 50, "die Meldung steht in rot im Bild"

    for _ in range(3):
        spot.backend.naechstes_bild()
        assert b.einmal()
    assert versuche["n"] == 1, "einmal gescheitert heisst nicht dreissigmal je Sekunde"
    assert _rot(_gelesen(tmp_path / blick.DATEI)) > 50, "die Meldung bleibt stehen"


def test_ein_fehler_im_erkenner_beendet_den_blick_nicht(tmp_path):
    """Ohne Kaesten faehrt man weiter. Ein Erkenner, der stolpert, darf weder den
    Blick noch den Lauf anhalten -- und er zaehlt NICHT als Bildfehler, sonst
    gaebe der Blick nach drei Takten auf, obwohl die Kamera tadellos liefert."""
    def stolpert(_feld):
        raise RuntimeError("YuNet hat schlechte Laune")

    _an(tmp_path)
    b = blick.Blick(_Spot(), tmp_path, gesichter_holen=stolpert)
    assert b.einmal()
    assert (tmp_path / blick.DATEI).is_file(), "das Bild kommt trotzdem"
    assert b.fehler == 0 and not b.aufgegeben
    assert b.gesicht_fehler == 1


def test_der_schalter_wirkt_waehrend_der_fahrt(tmp_path):
    """Umlegen mitten im Lauf, ohne Neustart -- das ist der Sinn eines Schalters."""
    b = blick.Blick(_Spot(), tmp_path,
                    gesichter_holen=lambda _feld: [(120.0, 90.0, 80.0, 80.0, 0.9)])
    assert b.einmal()
    assert _gelesen(tmp_path / blick.DATEI).ndim == 2

    _an(tmp_path)
    b._spot.backend.naechstes_bild()
    assert b.einmal()
    assert _gruen(_gelesen(tmp_path / blick.DATEI)) > 50

    _an(tmp_path, gesicht=False)
    b._spot.backend.naechstes_bild()
    assert b.einmal()
    assert _gelesen(tmp_path / blick.DATEI).ndim == 2, "und wieder aus"


def test_der_vorgabeweg_fuehrt_zum_echten_erkenner(monkeypatch, tmp_path):
    """Ohne Naht gebaut: die Kaesten kommen aus `gesicht.kaesten` mit einem
    YuNet-Erkenner -- also mit derselben Aufhellung wie Folgemodus und Messprobe."""
    from spotlab.backends.real import gesicht as gesichtsmodul

    gebaut, gefragt = [], []
    monkeypatch.setattr(gesichtsmodul, "erkenner",
                        lambda breite, hoehe, **kw: gebaut.append((breite, hoehe)) or "ERKENNER")
    monkeypatch.setattr(gesichtsmodul, "kaesten",
                        lambda feld, erk: gefragt.append(erk) or [])

    _an(tmp_path)
    b = blick.Blick(_Spot(), tmp_path)
    assert b.einmal()
    assert gefragt == ["ERKENNER"], "der echte Weg, nicht die Testnaht"
    assert len(gebaut) == 1, "ein Erkenner fuer den ganzen Lauf, nicht je Bild"


# --------------------------------------------------------- Haende im Fahrblick


def _hand_an(lauf_dir, gesicht=False, hand=True):
    from spotlab.record import ansicht

    ansicht.schreibe(lauf_dir, gesicht=gesicht, hand=hand)


def _gelb(bild):
    """Bildpunkte, die deutlich gelber sind als blau -- der Handkasten (HAND_FARBE)."""
    if bild.ndim != 3:
        return 0
    r, g, b = (bild[:, :, k].astype(int) for k in range(3))
    return int(((r > b + 60) & (g > b + 60) & (abs(r - g) < 80)).sum())


def _eine_hand(x=200.0, y=150.0, geste="halt", conf=0.97):
    from test_backend_gesten import _hand

    from spotlab.backends.real import gesten

    finger = (True, True, True, True) if geste == "halt" else (False, False, False, False)
    lm = _hand(finger, daumen="hoch") + (x - 100.0, y - 200.0, 0.0)
    return gesten.Hand(lm, conf, (x - 40.0, y - 100.0, x + 40.0, y + 10.0))


def test_ohne_handschalter_wird_der_handerkenner_nicht_gerufen(tmp_path):
    """Der Gesichtsschalter allein kostet keine Koerpersuche -- die ist mit 375 ms je
    Bild ohne Spur der teuerste Schritt im ganzen Blick."""
    _an(tmp_path)
    gerufen = []
    b = blick.Blick(_Spot(), tmp_path, gesichter_holen=lambda _feld: [],
                    haende_holen=lambda feld: gerufen.append(feld) or [])
    assert b.einmal()
    assert gerufen == []


def test_mit_handschalter_stehen_die_handkaesten_gelb_im_bild(tmp_path):
    """Gelb, nicht gruen: man muss den Handkasten vom Gesichtskasten unterscheiden koennen."""
    _hand_an(tmp_path)
    b = blick.Blick(_Spot(), tmp_path, gesichter_holen=lambda _feld: [],
                    haende_holen=lambda _feld: [_eine_hand()])
    assert b.einmal()
    bild = _gelesen(tmp_path / blick.DATEI)
    assert bild.ndim == 3
    assert _gelb(bild) > 50, "der Handkasten steht im Bild"
    assert _gruen(bild) < 20, "und kein Gesichtskasten"
    assert b.haende == 1


def test_beide_schalter_zeichnen_beides(tmp_path):
    _hand_an(tmp_path, gesicht=True, hand=True)
    b = blick.Blick(_Spot(), tmp_path,
                    gesichter_holen=lambda _feld: [(120.0, 90.0, 80.0, 80.0, 0.78)],
                    haende_holen=lambda _feld: [_eine_hand(x=500.0, y=300.0)])
    assert b.einmal()
    bild = _gelesen(tmp_path / blick.DATEI)
    assert _gruen(bild) > 50 and _gelb(bild) > 50


def test_fehlende_handmodelle_stehen_im_bild_und_werden_nicht_neu_versucht(tmp_path):
    from spotlab.errors import SpotlabError

    versuche = {"n": 0}

    def kaputt(_feld):
        versuche["n"] += 1
        raise SpotlabError("Die Handmodelle fehlen (gesucht in irgendwo).")

    _hand_an(tmp_path)
    spot = _Spot()
    b = blick.Blick(spot, tmp_path, haende_holen=kaputt)
    assert b.einmal()
    assert _rot(_gelesen(tmp_path / blick.DATEI)) > 50, "die Meldung steht in rot im Bild"
    for _ in range(3):
        spot.backend.naechstes_bild()
        assert b.einmal()
    assert versuche["n"] == 1


def test_ein_fehler_im_handerkenner_beendet_den_blick_nicht(tmp_path):
    def stolpert(_feld):
        raise RuntimeError("die Pose hat schlechte Laune")

    _hand_an(tmp_path)
    b = blick.Blick(_Spot(), tmp_path, haende_holen=stolpert)
    assert b.einmal()
    assert (tmp_path / blick.DATEI).is_file()
    assert b.fehler == 0 and not b.aufgegeben
    assert b.hand_fehler == 1 and "schlechte Laune" in b.letzter_handfehler


def test_der_vorgabeweg_der_hand_geht_ueber_den_koerper(monkeypatch, tmp_path):
    """Dieselbe Kette wie im Folgemodus: Koerper (mit Spur) -> Rumpf-Ausschnitt -> Haende.
    Auf dem ganzen Bild faende die Handpose nichts (gemessen: 0 von 510)."""
    from spotlab.backends.real import gesten, koerper

    gebaut, gefragt = [], []
    ein_koerper = koerper.Koerper(huefte=(400.0, 300.0), schulter=(400.0, 150.0), conf=0.9,
                                  kasten=(300.0, 50.0, 500.0, 450.0), schulterbreite=100.0)

    class _Koerpererkenner:
        def __init__(self, **kw):
            gebaut.append("koerper")

        def finde(self, feld):
            return [ein_koerper]

    class _Handerkenner:
        def __init__(self, **kw):
            gebaut.append("hand")

        def finde(self, feld, ausschnitt=None):
            gefragt.append(ausschnitt)
            return [_eine_hand()]

    monkeypatch.setattr(koerper, "Koerpererkenner", _Koerpererkenner)
    monkeypatch.setattr(gesten, "Handerkenner", _Handerkenner)
    _hand_an(tmp_path)
    spot = _Spot()
    b = blick.Blick(spot, tmp_path)
    assert b.einmal()
    spot.backend.naechstes_bild()
    assert b.einmal()
    assert gebaut == ["koerper", "hand"], "je einer fuer den ganzen Lauf"
    feld_hoehe, feld_breite = _gelesen(tmp_path / blick.DATEI).shape[:2]
    assert gefragt == [gesten.rumpf_ausschnitt(ein_koerper, breite=feld_breite, hoehe=feld_hoehe)] * 2
    assert b.haende == 2


def test_ohne_opencv_sagt_der_handweg_es_wie_das_gesicht(monkeypatch, tmp_path):
    """Die Zoo-Klassen importieren cv2 erst beim Bau; ein ImportError dort ist kein
    Stolpern, sondern ein fehlendes Extra -- und steht deshalb in rot im Bild."""
    from spotlab.backends.real import koerper

    def ohne_cv2(**kw):
        raise ImportError("No module named 'cv2'")

    monkeypatch.setattr(koerper, "Koerpererkenner", ohne_cv2)
    _hand_an(tmp_path)
    b = blick.Blick(_Spot(), tmp_path)
    assert b.einmal()
    assert _rot(_gelesen(tmp_path / blick.DATEI)) > 50
    assert "OpenCV" in b._hand_meldung and "gesicht" in b._hand_meldung, "das Extra ist genannt"


def test_der_handkasten_traegt_das_zeichen():
    """Nicht nur ein Kasten: der Text sagt, was die Regel daraus liest."""
    from spotlab.backends.real import gesten

    assert gesten.beschriftung(_eine_hand(geste="halt", conf=0.97)) == "Halt 0.97"
    assert gesten.beschriftung(_eine_hand(geste="weiter", conf=0.8)) == "Weiter 0.80"


def _aus_bytes(daten):
    return np.asarray(PILImage.open(io.BytesIO(daten)))


def test_die_meldung_ist_gross_genug_zum_lesen():
    """Der Standardzeichensatz von PIL ist elf Bildpunkte hoch. Auf einem Panorama
    von tausend Punkten Breite liest das niemand -- und ausgerechnet „das Modell
    fehlt" ist die Zeile, wegen der dieser Weg ueberhaupt existiert."""
    bild = _aus_bytes(blick.zeichne_jpeg(np.zeros((200, 800), dtype=np.uint8),
                                         meldung="Modell fehlt"))
    r, g = (bild[:, :, k].astype(int) for k in range(2))
    zeilen = np.where((r > g + 40).any(axis=1))[0]
    assert zeilen.size, "die Meldung steht im Bild"
    assert zeilen.max() - zeilen.min() + 1 >= 12, "hoeher als der 11-px-Standard"


def test_ein_aelteres_pillow_ohne_groessenangabe_bricht_nicht(monkeypatch):
    """`load_default(size=)` gibt es erst ab Pillow 10.1, erlaubt ist ab 10.0.
    Eine fehlende Schriftgroesse darf den Blick nicht anhalten -- lieber klein."""
    from PIL import ImageFont

    echt = ImageFont.load_default
    monkeypatch.setattr(ImageFont, "load_default",
                        lambda *a, **kw: (_ for _ in ()).throw(TypeError("keine Groesse"))
                        if (a or kw) else echt())
    bild = _aus_bytes(blick.zeichne_jpeg(np.zeros((200, 800), dtype=np.uint8),
                                         meldung="Modell fehlt"))
    assert _rot(bild) > 20, "kleiner, aber da"


def test_eine_lange_meldung_zeigt_dass_sie_gekuerzt_ist():
    """Die Meldung „Modell fehlt" ist 304 Zeichen lang und passt nicht ins Bild.
    Vier Zeilen reichen fuer das Wesentliche -- aber ein Text, der mitten im Wort
    aufhoert, sieht aus wie ein Fehler statt wie eine Kuerzung. Der ganze Satz
    steht in `diagnose.log`."""
    kurz = blick._meldungszeilen("Das Gesichtsmodell fehlt.")
    assert kurz == ["Das Gesichtsmodell fehlt."], "was passt, bleibt unberuehrt"

    lang = blick._meldungszeilen("wort " * 200)
    assert len(lang) == blick.MELDUNG_ZEILEN
    assert lang[-1].endswith("…"), "die Kuerzung ist sichtbar"
