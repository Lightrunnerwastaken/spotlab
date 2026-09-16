"""Der Koerper-Erkenner: MediaPipe-Pose aus dem OpenCV-Zoo, ueber cv2.dnn.

Gemessen am 16.09.2026 ueber 510 gespeicherte Panoramen: das Gesicht fand den
Menschen in 149 Takten, der Koerper (Huefte) in 134 -- in ANDEREN Momenten. 33-mal
nur der Koerper (die kopflosen Bilder: 1.3-2 m, aufrecht, Naht-Kerbe), 47-mal nur
das Gesicht (weit weg, fuer den 224-px-Erkenner zu klein). Zusammen 182.

Der Preis: der Personen-Erkenner kostet 375 ms je Bild (Ganzbild plus drei
Kacheln), die Pose 57 ms. Deshalb die SPUR: gesucht wird nur, wenn die Pose
abreisst; sonst laeuft die Pose auf dem Ausschnitt der letzten. Wie MediaPipe.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from spotlab.backends.real import koerper
from spotlab.errors import SpotlabError

# ------------------------------------------------------------------ Modelle


def test_fehlende_modelle_sagen_wo_sie_herkommen(monkeypatch, tmp_path):
    """Wie beim Gesicht: der Standardordner ist der letzte von drei Orten. Der Test
    zeigt auf einen leeren, sonst bestuende er nur auf Rechnern ohne Modell."""
    monkeypatch.setattr(koerper, "MODELL_ORDNER", tmp_path / "leer")
    with pytest.raises(SpotlabError) as fehler:
        koerper.modellpfade(umgebung={})
    text = str(fehler.value)
    assert koerper.BEZUGSQUELLE in text
    assert koerper.MODELL_ERKENNER in text and koerper.MODELL_POSE in text


def test_der_standardordner_wird_durchsucht(monkeypatch, tmp_path):
    for name in (koerper.MODELL_ERKENNER, koerper.MODELL_POSE):
        (tmp_path / name).write_bytes(b"x" * 10)
    monkeypatch.setattr(koerper, "MODELL_ORDNER", tmp_path)
    erkenner, pose = koerper.modellpfade(umgebung={})
    assert erkenner == tmp_path / koerper.MODELL_ERKENNER
    assert pose == tmp_path / koerper.MODELL_POSE


def test_die_umgebung_nennt_einen_anderen_ordner(monkeypatch, tmp_path):
    monkeypatch.setattr(koerper, "MODELL_ORDNER", tmp_path / "leer")
    anderswo = tmp_path / "anderswo"
    anderswo.mkdir()
    for name in (koerper.MODELL_ERKENNER, koerper.MODELL_POSE):
        (anderswo / name).write_bytes(b"x" * 10)
    erkenner, _ = koerper.modellpfade(umgebung={koerper.ENV_ORDNER: str(anderswo)})
    assert erkenner == anderswo / koerper.MODELL_ERKENNER


# ------------------------------------------------------- Aus der Pose lesen


def _landmarken(huefte_l, huefte_r, schulter_l, schulter_r, praesenz=0.95):
    """39x5 wie MPPose: x, y, z, Sichtbarkeit, Praesenz. Alles andere ist 'nicht da'."""
    lm = np.zeros((39, 5), dtype=float)
    for i, (x, y) in ((koerper.HUEFTE_L, huefte_l), (koerper.HUEFTE_R, huefte_r),
                      (koerper.SCHULTER_L, schulter_l), (koerper.SCHULTER_R, schulter_r)):
        lm[i, :2] = (x, y)
        lm[i, 3:] = praesenz
    return lm


def test_koerper_aus_pose_nimmt_hueft_und_schultermitte():
    lm = _landmarken((100.0, 400.0), (140.0, 400.0), (90.0, 200.0), (150.0, 200.0))
    k = koerper.koerper_aus_pose(lm, conf=0.97)
    assert k.huefte == pytest.approx((120.0, 400.0))
    assert k.schulter == pytest.approx((120.0, 200.0))
    assert k.conf == 0.97


def test_ein_versatz_verschiebt_alles_in_bildkoordinaten():
    """Auf einer Kachel gefunden: die x-Werte gehoeren ins ganze Panorama."""
    lm = _landmarken((100.0, 400.0), (140.0, 400.0), (90.0, 200.0), (150.0, 200.0))
    k = koerper.koerper_aus_pose(lm, conf=0.9, x_versatz=457)
    assert k.huefte[0] == pytest.approx(577.0) and k.schulter[0] == pytest.approx(577.0)


def test_ohne_huefte_und_schulter_ist_es_kein_koerper():
    lm = _landmarken((100.0, 400.0), (140.0, 400.0), (90.0, 200.0), (150.0, 200.0), praesenz=0.2)
    assert koerper.koerper_aus_pose(lm, conf=0.9) is None


def test_nur_die_schultern_reichen_fuer_einen_koerper():
    """Beine unten abgeschnitten (sehr nah): Schultern sind noch da -- das Ziel bleibt."""
    lm = _landmarken((100.0, 400.0), (140.0, 400.0), (90.0, 200.0), (150.0, 200.0))
    lm[koerper.HUEFTE_L, 3:] = 0.1
    lm[koerper.HUEFTE_R, 3:] = 0.1
    k = koerper.koerper_aus_pose(lm, conf=0.9)
    assert k is not None and k.huefte is None and k.schulter == pytest.approx((120.0, 200.0))


def test_person_aus_pose_ist_eine_erkennerzeile():
    """Fuer die Spur: aus der letzten Pose die Zeile, die der Pose-Schritt als
    'Person' erwartet -- Hueftmitte und ein Punkt darueber, der Groesse und Drehung
    traegt. 13 Werte wie beim Erkenner, sonst passt der Zuschnitt nicht."""
    lm = _landmarken((100.0, 400.0), (140.0, 400.0), (90.0, 200.0), (150.0, 200.0))
    zeile = koerper.person_aus_pose(lm)
    assert zeile.shape == (13,)
    assert zeile[4:6] == pytest.approx((120.0, 400.0)), "Hueftmitte"
    assert zeile[7] < 200.0, "der zweite Punkt liegt ueber den Schultern"
    assert zeile[6] == pytest.approx(120.0)


# ----------------------------------------------------------------- Die Spur


class _Zaehlt:
    def __init__(self, ergebnisse):
        self.aufrufe = 0
        self._ergebnisse = list(ergebnisse)

    def __call__(self, *a, **kw):
        self.aufrufe += 1
        return self._ergebnisse.pop(0) if self._ergebnisse else self._ergebnisse_ende()

    def _ergebnisse_ende(self):
        return None


def _pose_treffer():
    lm = _landmarken((100.0, 400.0), (140.0, 400.0), (90.0, 200.0), (150.0, 200.0))
    return (np.zeros((2, 2)), lm, np.zeros((39, 3)), None, None, 0.98)


def _erkenner_treffer():
    return np.array([[50.0, 150.0, 200.0, 450.0, 120.0, 400.0, 120.0, 100.0, 0, 0, 0, 0, 0.9]])


def _bild():
    return np.zeros((782, 1239), dtype=np.uint8)


def test_die_spur_erspart_den_erkenner():
    erkenner = _Zaehlt([_erkenner_treffer()])
    pose = _Zaehlt([_pose_treffer(), _pose_treffer(), _pose_treffer()])
    k = koerper.Koerpererkenner(erkenner=erkenner, pose=pose, kacheln=False)
    assert k.finde(_bild()) and k.finde(_bild()) and k.finde(_bild())
    assert erkenner.aufrufe == 1, "gesucht wird nur einmal"
    assert pose.aufrufe == 3
    assert k.suchen == 1 and k.spuren == 2


def test_reisst_die_spur_ab_sucht_er_wieder():
    erkenner = _Zaehlt([_erkenner_treffer(), _erkenner_treffer()])
    # Takt 1: Pose ok. Takt 2: Pose auf der Spur scheitert -> Suche -> Pose ok.
    pose = _Zaehlt([_pose_treffer(), None, _pose_treffer()])
    k = koerper.Koerpererkenner(erkenner=erkenner, pose=pose, kacheln=False)
    assert k.finde(_bild())
    assert k.finde(_bild()), "nach der abgerissenen Spur findet die Suche ihn wieder"
    assert erkenner.aufrufe == 2
    assert k.suchen == 2 and k.spuren == 0, "die Spur hat in keinem Takt getragen"


def test_ohne_person_bleibt_die_liste_leer_und_es_wird_jedes_mal_gesucht():
    erkenner = _Zaehlt([np.empty((0, 13)), np.empty((0, 13))])
    pose = _Zaehlt([])
    k = koerper.Koerpererkenner(erkenner=erkenner, pose=pose, kacheln=False)
    assert k.finde(_bild()) == [] and k.finde(_bild()) == []
    assert erkenner.aufrufe == 2 and pose.aufrufe == 0


def test_mit_kacheln_sieht_der_erkenner_vier_ausschnitte():
    """Gemessen: von 208 Treffern kamen 142 erst auf den Kacheln -- ein Mensch auf
    2-3 m ist im ganzen 224-px-Bild 15 px gross."""
    gesehen = []

    def erkenner(bild):
        gesehen.append(bild.shape[:2])
        return np.empty((0, 13))

    k = koerper.Koerpererkenner(erkenner=erkenner, pose=_Zaehlt([]), kacheln=True)
    k.finde(_bild())
    assert len(gesehen) == 4
    assert gesehen[0] == (782, 1239) and all(s == (782, 782) for s in gesehen[1:])


def test_ein_graues_bild_wird_dreikanalig_gereicht():
    """Die Zoo-Klassen verlangen BGR mit drei Kanaelen; die Frontbilder aelterer
    Spots sind grau."""
    formen = []

    def erkenner(bild):
        formen.append(bild.shape)
        return np.empty((0, 13))

    koerper.Koerpererkenner(erkenner=erkenner, pose=_Zaehlt([]), kacheln=False).finde(_bild())
    assert formen == [(782, 1239, 3)]


# ------------------------------------------------------------ Die Gegenprobe


class _Pano:
    """Zeile 400 = 0 Grad, jede Zeile 0.1 Grad; Spalte 620 = 0 Grad Peilung."""

    def winkel(self, spalte, zeile):
        return (620.0 - spalte) / 7.0, (400.0 - zeile) / 10.0

    def kamerahoehe(self, blick_grad=0.0):
        return 0.46


def _wolke(abstand, peilung_grad, hoehenwinkel_grad, anzahl=30):
    p, h = math.radians(peilung_grad), math.radians(hoehenwinkel_grad)
    return np.array([[abstand * math.cos(p), abstand * math.sin(p), abstand * math.tan(h)]] * anzahl)


def _koerper(huefte_zeile=400.0, schulter_zeile=250.0):
    return koerper.Koerper(huefte=(620.0, huefte_zeile), schulter=(620.0, schulter_zeile),
                           conf=0.95, kasten=(500.0, 100.0, 740.0, 700.0))


def test_die_huefte_auf_bodenhoehe_wird_genommen():
    """Huefte bei +10 Grad, 2 m: 0.46 + 2 tan 10 = 0.81 m -- ein stehender Mensch."""
    [b] = koerper.beurteile([_koerper(huefte_zeile=300.0)], _Pano(), _wolke(2.0, 0.0, 10.0), 0.46)
    assert b.genommen and b.grund is None
    assert b.distance == pytest.approx(2.0, abs=0.05)
    assert b.height == pytest.approx(0.81, abs=0.03)
    assert b.bild_oben == pytest.approx(15.0), "die Schulterlinie, koerperfest"


def test_zu_tief_heisst_kein_mensch():
    """Huefte bei -5 Grad auf 2 m: 0.29 m ueber dem Boden -- eine Kiste, kein Mensch."""
    [b] = koerper.beurteile([_koerper(huefte_zeile=450.0)], _Pano(), _wolke(2.0, 0.0, -5.0), 0.46)
    assert not b.genommen and b.grund == koerper.ZU_TIEF


def test_zu_hoch_heisst_kein_mensch():
    [b] = koerper.beurteile([_koerper(huefte_zeile=100.0)], _Pano(), _wolke(3.0, 0.0, 30.0), 0.46)
    assert not b.genommen and b.grund == koerper.ZU_HOCH


def test_ohne_tiefenpunkte_wird_verworfen():
    [b] = koerper.beurteile([_koerper()], _Pano(), np.zeros((0, 3)), 0.46)
    assert not b.genommen and b.grund == koerper.OHNE_TIEFE and b.distance is None


def test_ohne_huefte_prueft_die_gegenprobe_die_schulter():
    """Schultern bei +20 Grad auf 1.5 m: 0.46 + 1.5 tan 20 = 1.01 m -- ein sehr naher Mensch."""
    k = koerper.Koerper(huefte=None, schulter=(620.0, 200.0), conf=0.9, kasten=(0, 0, 1, 1))
    [b] = koerper.beurteile([k], _Pano(), _wolke(1.5, 0.0, 20.0), 0.46,
                            unten=koerper.SCHULTER_UNTEN_M, oben=koerper.SCHULTER_OBEN_M)
    assert b.genommen, b


def test_die_neigung_korrigiert_den_hoehenwinkel():
    """Nase 15 Grad hoch: derselbe Bildpunkt liegt in der Welt 15 Grad hoeher."""
    [b] = koerper.beurteile([_koerper(huefte_zeile=450.0)], _Pano(), _wolke(2.0, 0.0, 10.0), 0.46,
                            blick_grad=15.0)
    assert b.genommen, "im Bild -5 Grad, in der Welt +10: 0.81 m"


# ------------------------------------------------------ Der echte Erkenner


@pytest.mark.skipif(not all((koerper.MODELL_ORDNER / n).is_file()
                            for n in (koerper.MODELL_ERKENNER, koerper.MODELL_POSE)),
                    reason="Koerpermodelle nicht abgelegt")
def test_der_echte_erkenner_laeuft_auf_der_aufzeichnung_ohne_person():
    """Die Aufzeichnung vom 12.08.2026 zeigt einen leeren Gang: kein Koerper, kein
    Fehler. Das prueft die Verkettung Erkenner -> Pose auf den echten Dateien."""
    from PIL import Image

    daten = Path(__file__).parent / "daten" / "blick_real_20260812"
    bild = np.asarray(Image.open(daten / "takt90_frontleft.jpg").convert("L"))
    k = koerper.Koerpererkenner()
    assert k.finde(bild) == []
    assert k.suchen == 1
