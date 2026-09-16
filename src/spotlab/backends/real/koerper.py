"""Körper erkennen: MediaPipe-Pose aus dem OpenCV-Zoo, über `cv2.dnn` — kein neues Paket.

DER ANLASS. Am 16.09.2026 stand ein Mensch aufrecht 1.6 m vor Spot, und das
Gesicht war weg: die Naht-Kerbe der beiden Fischaugen schneidet genau voraus am
Hals ab, und unter 1.3 m sind nur noch Beine im Bild. Der Körper aber war in
beiden Bildern vollständig zu sehen — Schultern, Hüfte, Knie. Das Gesicht ist
das kleinste und höchste Ziel am Menschen; die Hüfte das grösste und mittlere.

GEMESSEN über 510 gespeicherte Panoramen desselben Tages: das Gesicht fand den
Menschen in 149 Takten, der Körper in 134 — in ANDEREN Momenten. 33-mal nur der
Körper (kopflos: 1.3–2 m, aufrecht, Kerbe), 47-mal nur das Gesicht (weit weg:
für den 224-px-Erkenner zu klein). Zusammen 182. Also nicht Körper STATT
Gesicht, sondern Körper vor Gesicht vor Tag — jede Stufe dort, wo sie stark ist.

DER PREIS, und die Antwort darauf: der Personen-Erkenner kostet 375 ms je Bild
(Ganzbild plus drei Kacheln — von 208 Treffern kamen 142 erst auf den Kacheln,
ein Mensch auf 2–3 m ist im ganzen Bild bei 224 px Eingabe 15 px gross), die
Pose 57 ms. Deshalb die SPUR, wie MediaPipe selbst: gesucht wird nur, wenn die
Pose abreisst; sonst läuft die Pose auf dem Ausschnitt, den die letzte Pose
vorgibt. Mit Spur kostet ein Takt rund 60 ms.

Die Referenzklassen des Zoos liegen unverändert in `zoo/` (Apache 2.0). Hier
steht nur, was spotlab dazutut: Modellsuche, Spur, Kacheln, und die Gegenprobe
der Hüfte auf Bodenhöhe — dieselbe Rechnung wie beim Gesicht (`gesicht.py`).
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from spotlab.backends.real import gesicht
from spotlab.errors import SpotlabError

MODELL_ERKENNER = "person_detection_mediapipe_2023mar.onnx"     # 11 990 159 Bytes
MODELL_POSE = "pose_estimation_mediapipe_2023mar.onnx"           #  5 557 238 Bytes
MODELL_ORDNER = gesicht.MODELL_ORDNER
ENV_ORDNER = "SPOTLAB_KOERPERMODELLE"
BEZUGSQUELLE = "https://github.com/opencv/opencv_zoo/tree/main/models"

# Landmarken nach BlazePose (33 Punkte; MPPose liefert 39, die letzten sechs sind Hilfspunkte).
NASE = 0
SCHULTER_L, SCHULTER_R = 11, 12
HUEFTE_L, HUEFTE_R = 23, 24
MINDESTPRAESENZ = 0.5            # so sicher muss ein Landmarkenpunkt im Bild sein
MINDESTSICHERHEIT = 0.5          # Personen-Erkenner und Pose

# Die Gegenprobe: wo über dem Boden liegt eine Hüfte, wo eine Schulter?
# Hüfte: sitzend am Boden ~0.6 m, gross stehend ~1.1 m. Schulter: 0.9–1.7 m.
HUEFTE_UNTEN_M = 0.6
HUEFTE_OBEN_M = 1.3
SCHULTER_UNTEN_M = 0.9
SCHULTER_OBEN_M = 1.7

OHNE_TIEFE = gesicht.OHNE_TIEFE
ZU_TIEF = gesicht.ZU_TIEF
ZU_HOCH = gesicht.ZU_HOCH


@dataclass(frozen=True)
class Koerper:
    """Ein gefundener Mensch, in Bildkoordinaten des Panoramas."""

    huefte: tuple                # (x, y) Mitte der Hüften — oder None (Beine abgeschnitten)
    schulter: tuple              # (x, y) Mitte der Schultern — oder None
    conf: float                  # Sicherheit der Pose
    kasten: tuple                # (x1, y1, x2, y2) über alle sichtbaren Punkte
    schulterbreite: float = None  # Abstand der Schultern in px — oder None (nur eine sichtbar)


@dataclass(frozen=True)
class Koerperbefund:
    """Ein Körper mit seinem Urteil — genommen oder warum nicht."""

    bearing: float
    elevation: float             # Höhenwinkel in der WELT (Neigung eingerechnet)
    conf: float
    punkt: str                   # "huefte" oder "schulter": worauf geprüft wurde
    distance: float = None
    height: float = None
    genommen: bool = False
    grund: str = None
    bild_oben: float = None      # Höhenwinkel der Schulterlinie im Bild, körperfest


# ---------------------------------------------------------------- Modelle


def modellpfade(ordner=None, umgebung=None):
    """(Erkenner, Pose) — oder ein Fehler, der sagt, woher man sie bekommt.

    Argument, dann `SPOTLAB_KOERPERMODELLE`, dann der Standardordner (derselbe
    wie beim Gesicht). Ein Ordner zählt nur, wenn BEIDE Dateien darin liegen.
    """
    kandidaten = [ordner, (os.environ if umgebung is None else umgebung).get(ENV_ORDNER),
                  MODELL_ORDNER]
    for kandidat in kandidaten:
        if not kandidat:
            continue
        erkenner, pose = Path(kandidat) / MODELL_ERKENNER, Path(kandidat) / MODELL_POSE
        if erkenner.is_file() and pose.is_file():
            return erkenner, pose
    raise SpotlabError(
        f"Die Körpermodelle fehlen (gesucht in {MODELL_ORDNER}): `{MODELL_ERKENNER}` und "
        f"`{MODELL_POSE}` aus dem OpenCV-Zoo ({BEZUGSQUELLE}, Ordner "
        f"person_detection_mediapipe und pose_estimation_mediapipe; der Zoo führt sie über "
        f"git-lfs, der gewöhnliche raw-Link liefert einen 132-Byte-Zeiger). Dort ablegen, "
        f"oder {ENV_ORDNER} auf einen Ordner mit beiden Dateien setzen."
    )


def _zoo():
    from spotlab.backends.real.zoo import mp_persondet, mp_pose

    return mp_persondet.MPPersonDet, mp_pose.MPPose


# ------------------------------------------------------ Aus der Pose lesen


def _mitte(lm, links, rechts, mindest=MINDESTPRAESENZ):
    """Mitte zweier Landmarken — aus beiden, sonst aus der einen, die da ist."""
    da = [i for i in (links, rechts) if lm[i, 4] > mindest]
    if not da:
        return None
    return tuple(float(v) for v in lm[da, :2].mean(axis=0))


def koerper_aus_pose(lm, conf, x_versatz=0.0, mindest=MINDESTPRAESENZ):
    """Ein `Koerper` aus den 39×5 Landmarken der Pose — oder None ohne Hüfte UND Schulter.

    `x_versatz` verschiebt in Panorama-Koordinaten, wenn die Pose auf einer
    Kachel lief. Nur Schultern reichen: sehr nah sind die Beine abgeschnitten,
    das Ziel bleibt.
    """
    lm = np.asarray(lm, dtype=float)
    huefte = _mitte(lm, HUEFTE_L, HUEFTE_R, mindest)
    schulter = _mitte(lm, SCHULTER_L, SCHULTER_R, mindest)
    if huefte is None and schulter is None:
        return None
    sichtbar = lm[:33][lm[:33, 4] > mindest]
    if len(sichtbar):
        x1, y1 = sichtbar[:, :2].min(axis=0)
        x2, y2 = sichtbar[:, :2].max(axis=0)
    else:
        x1 = y1 = x2 = y2 = 0.0

    def versetzt(p):
        return None if p is None else (p[0] + x_versatz, p[1])

    # Die Schulterbreite trägt der Gestenleser (`gesten.rumpf_ausschnitt`):
    # sie sagt, wie gross der Mensch im Bild ist, ohne die Tiefe zu fragen.
    schulterbreite = None
    if lm[SCHULTER_L, 4] > mindest and lm[SCHULTER_R, 4] > mindest:
        schulterbreite = float(np.linalg.norm(lm[SCHULTER_L, :2] - lm[SCHULTER_R, :2]))
    return Koerper(versetzt(huefte), versetzt(schulter), float(conf),
                   (float(x1 + x_versatz), float(y1), float(x2 + x_versatz), float(y2)),
                   schulterbreite)


def person_aus_pose(lm):
    """Die Erkenner-Zeile (13 Werte) für die SPUR, aus der letzten Pose.

    MPPose schneidet den Ausschnitt aus zwei Punkten: der Hüftmitte und einem
    Punkt darüber, dessen Abstand die Grösse und dessen Richtung die Drehung
    des Menschen trägt. Anderthalb Hüft-Schulter-Längen über der Hüfte liegt
    er über dem Kopf — der Ausschnitt deckt den ganzen Körper.
    """
    lm = np.asarray(lm, dtype=float)
    huefte = _mitte(lm, HUEFTE_L, HUEFTE_R, 0.0)
    schulter = _mitte(lm, SCHULTER_L, SCHULTER_R, 0.0)
    hx, hy = huefte
    sx, sy = schulter
    oben = (hx + 1.5 * (sx - hx), hy + 1.5 * (sy - hy))
    sichtbar = lm[:33]
    x1, y1 = sichtbar[:, :2].min(axis=0)
    x2, y2 = sichtbar[:, :2].max(axis=0)
    return np.array([x1, y1, x2, y2, hx, hy, oben[0], oben[1], 0.0, 0.0, 0.0, 0.0, 1.0],
                    dtype=np.float32)


# ------------------------------------------------------------------ Spur


def _dreikanalig(feld):
    """BGR mit drei Kanälen, wie die Zoo-Klassen es verlangen.

    Grau (ältere Spots, die Messprobe) wird verdreifacht; Farbe kommt aus dem
    Panorama als RGB und wird gedreht.
    """
    import cv2

    feld = np.asarray(feld)
    if feld.ndim == 2:
        return cv2.cvtColor(feld, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(feld, cv2.COLOR_RGB2BGR)


class Koerpererkenner:
    """Erkenner und Pose mit Spur. `finde(feld)` gibt die gefundenen Körper zurück.

    `erkenner` und `pose` sind die Testtüren: `erkenner(bgr) -> Zeilen (N×13)`,
    `pose(bgr, zeile) -> (kasten, landmarken, …, conf)` oder None. Ohne sie
    werden die Zoo-Klassen mit den Modelldateien gebaut.

    Zähler: `suchen` (Takte, in denen der Erkenner lief) und `spuren` (Takte,
    in denen die Spur getragen hat, ohne Erkenner).
    """

    def __init__(self, ordner=None, erkenner=None, pose=None, kacheln=True,
                 mindestsicherheit=MINDESTSICHERHEIT):
        if erkenner is None or pose is None:
            pfad_erkenner, pfad_pose = modellpfade(ordner)
            MPPersonDet, MPPose = _zoo()
            det = MPPersonDet(str(pfad_erkenner), scoreThreshold=float(mindestsicherheit))
            pos = MPPose(str(pfad_pose), confThreshold=float(mindestsicherheit))
            erkenner = erkenner or det.infer
            pose = pose or pos.infer
        self._erkenner = erkenner
        self._pose = pose
        self._kacheln = kacheln
        self._spur = None
        self.suchen = 0
        self.spuren = 0

    def _ausschnitte(self, bgr):
        """Das ganze Bild, dann drei quadratische Kacheln (links, Mitte, rechts)."""
        h, w = bgr.shape[:2]
        yield 0, bgr
        if self._kacheln and w > h:
            for x0 in (0, (w - h) // 2, w - h):
                yield x0, np.ascontiguousarray(bgr[:, x0:x0 + h])

    def finde(self, feld):
        bgr = _dreikanalig(feld)
        if self._spur is not None:
            ergebnis = self._pose(bgr, self._spur.copy())
            koerper = None if ergebnis is None else koerper_aus_pose(ergebnis[1], ergebnis[5])
            if koerper is not None:
                self.spuren += 1
                self._spur = person_aus_pose(ergebnis[1])
                return [koerper]
            self._spur = None

        self.suchen += 1
        kandidaten = []
        for x0, ausschnitt in self._ausschnitte(bgr):
            zeilen = np.asarray(self._erkenner(ausschnitt))
            for zeile in zeilen:
                kandidaten.append((float(zeile[-1]), zeile, x0, ausschnitt))
        if not kandidaten:
            return []
        _, zeile, x0, ausschnitt = max(kandidaten, key=lambda k: k[0])
        ergebnis = self._pose(ausschnitt, np.array(zeile, dtype=np.float32).copy())
        if ergebnis is None:
            return []
        koerper = koerper_aus_pose(ergebnis[1], ergebnis[5], x_versatz=x0)
        if koerper is None:
            return []
        landmarken = np.asarray(ergebnis[1], dtype=float).copy()
        landmarken[:, 0] += x0                       # die Spur lebt im ganzen Panorama
        self._spur = person_aus_pose(landmarken)
        return [koerper]


# ------------------------------------------------------------ Gegenprobe


def beurteile(koerper_liste, pano, punkte, kamerahoehe, blick_grad=0.0, unten=None, oben=None):
    """JEDER Körper mit seinem Urteil — dieselbe Rechnung wie `gesicht.beurteile`.

    Geprüft wird die Hüfte, notfalls die Schulter (Beine abgeschnitten), jeweils
    mit ihrem eigenen Höhenband über dem Boden. `blick_grad` ist die GEMESSENE
    Neigung nach oben: der Höhenwinkel im Bild ist körperfest.
    """
    befunde = []
    for k in koerper_liste:
        if k.huefte is not None:
            punkt, name = k.huefte, "huefte"
            band = (HUEFTE_UNTEN_M if unten is None else unten, HUEFTE_OBEN_M if oben is None else oben)
        else:
            punkt, name = k.schulter, "schulter"
            band = (SCHULTER_UNTEN_M if unten is None else unten,
                    SCHULTER_OBEN_M if oben is None else oben)
        peilung, im_bild = pano.winkel(punkt[0], punkt[1])
        hoehenwinkel = im_bild + float(blick_grad)
        bild_oben = None
        if k.schulter is not None:
            _, bild_oben = pano.winkel(k.schulter[0], k.schulter[1])
            bild_oben = float(bild_oben)
        abstand = gesicht.abstand_in_richtung(punkte, peilung, hoehenwinkel)
        if abstand is None:
            befunde.append(Koerperbefund(peilung, hoehenwinkel, k.conf, name,
                                         grund=OHNE_TIEFE, bild_oben=bild_oben))
            continue
        ueber_boden = kamerahoehe + abstand * math.tan(math.radians(hoehenwinkel))
        grund = None
        if ueber_boden < band[0]:
            grund = ZU_TIEF
        elif ueber_boden > band[1]:
            grund = ZU_HOCH
        befunde.append(Koerperbefund(peilung, hoehenwinkel, k.conf, name, distance=abstand,
                                     height=ueber_boden, genommen=grund is None, grund=grund,
                                     bild_oben=bild_oben))
    return befunde
