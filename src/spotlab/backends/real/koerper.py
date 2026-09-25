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

GESUCHT WIRD SEIT DEM 25.09.2026 MIT YOLOX, nicht mehr mit dem MediaPipe-Erkenner.
Lauf 20260925T125326Z: in 190 von 226 Such-Takten meldete jener NICHTS, und auf 7
von 8 Stichproben stand der Mensch gut sichtbar 2–5 m voraus. Offline über die
174 verpassten Bilder: MediaPipe 6, mit feineren Kacheln 41–59, YOLOX-S aus dem
Zoo auf dem ganzen Bild 141 — bei derselben Zeit (240 gegen 245 ms); auf 38
Folge-Bildern 38, im leeren Gang kein Fehlalarm. Der MediaPipe-Erkenner sucht
einen KOPF (kleiner Kopf auf 3 m, abgeschnittener Kopf nah: nichts), YOLOX den
ganzen Menschen. Die Pose bleibt MediaPipe (`kasten_zeile` legt sie in den
YOLOX-Kasten, 110 von 141 bekamen ein Skelett), die Spur auch. Ohne Skelett
zählt der Kasten selbst (`koerper_aus_kasten`). Fehlt das YOLOX-Modell, sucht
der Erkenner wie bisher und sagt es (`ohne_yolox`).
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
MODELL_PERSONEN = "object_detection_yolox_2022nov.onnx"          # 35 858 002 Bytes, YOLOX-S
# YOLOX: Klasse 0 ist "person" (COCO). Die Schwellen wie im Versuch vom 25.09.2026:
# der Zoo filtert bei 0.35 (NMS), genommen wird ab 0.4.
YOLOX_KONFIDENZ = 0.35
YOLOX_MINDEST = 0.4
YOLOX_EINGABE = 640
# Wo im YOLOX-Kasten eines stehenden Menschen die Hüfte liegt (von oben), und wo der
# Punkt über dem Kopf, den die Pose als Grösse und Drehung braucht (`person_aus_pose`).
KASTEN_HUEFTE = 0.52
KASTEN_OBEN = 0.02
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


def personenmodell(ordner=None, umgebung=None):
    """Der Pfad zum YOLOX-Modell — oder ein Fehler, der sagt, woher man es bekommt.

    Dieselben drei Orte wie `modellpfade`. Der Erkenner fängt den Fehler und sucht
    dann wie bisher mit MediaPipe: das Modell ist eine Verbesserung, keine Pflicht.
    """
    kandidaten = [ordner, (os.environ if umgebung is None else umgebung).get(ENV_ORDNER),
                  MODELL_ORDNER]
    for kandidat in kandidaten:
        if kandidat and (Path(kandidat) / MODELL_PERSONEN).is_file():
            return Path(kandidat) / MODELL_PERSONEN
    raise SpotlabError(
        f"Das YOLOX-Modell fehlt (gesucht in {MODELL_ORDNER}): `{MODELL_PERSONEN}` aus dem "
        f"OpenCV-Zoo ({BEZUGSQUELLE}, Ordner object_detection_yolox; git-lfs, der gewöhnliche "
        f"raw-Link liefert einen 132-Byte-Zeiger). Ohne es sucht spotlab Menschen wie vor dem "
        f"25.09.2026 und übersieht dabei viele — das Schüler-ZIP bringt es mit."
    )


def _zoo():
    from spotlab.backends.real.zoo import mp_persondet, mp_pose

    return mp_persondet.MPPersonDet, mp_pose.MPPose


def _rgb(feld):
    """Drei Kanäle in RGB, wie YOLOX sie will: das Panorama ist RGB, Grau wird verdreifacht."""
    feld = np.asarray(feld)
    if feld.ndim == 2:
        return np.ascontiguousarray(np.stack([feld] * 3, axis=-1))
    return np.ascontiguousarray(feld)


class YoloxPersonen:
    """Menschen im ganzen Bild: `(rgb) -> [(x1, y1, x2, y2, score)]`, der sicherste zuerst.

    Vor- und Nachbereitung wie im Zoo-Beispiel (`object_detection_yolox/demo.py`): das
    Bild RGB, auf 640 skaliert, oben links in ein Quadrat mit Rand 114 gelegt; die Kästen
    zurück in Bildpixel. `modell` ist die Testtür (`infer(bild) -> x, y, b, h, score,
    klasse`); ohne sie wird die Zoo-Klasse mit der Modelldatei gebaut.
    """

    def __init__(self, pfad=None, modell=None, mindest=YOLOX_MINDEST):
        if modell is None:
            from spotlab.backends.real.zoo.yolox import YoloX

            modell = YoloX(str(pfad), confThreshold=YOLOX_KONFIDENZ)
        self._modell = modell
        self._mindest = float(mindest)

    def __call__(self, rgb):
        import cv2

        rgb = np.asarray(rgb)
        faktor = min(YOLOX_EINGABE / rgb.shape[0], YOLOX_EINGABE / rgb.shape[1])
        quadrat = np.full((YOLOX_EINGABE, YOLOX_EINGABE, 3), 114.0, dtype=np.float32)
        klein = cv2.resize(rgb, (int(rgb.shape[1] * faktor), int(rgb.shape[0] * faktor)),
                           interpolation=cv2.INTER_LINEAR).astype(np.float32)
        quadrat[:klein.shape[0], :klein.shape[1]] = klein
        kaesten = []
        for zeile in np.asarray(self._modell.infer(quadrat)).reshape(-1, 6):
            if int(zeile[5]) != 0 or zeile[4] < self._mindest:
                continue
            x, y, b, h = (float(v) / faktor for v in zeile[:4])
            kaesten.append((x, y, x + b, y + h, float(zeile[4])))
        return sorted(kaesten, key=lambda k: -k[4])


def kasten_zeile(kasten):
    """Die Erkenner-Zeile (13 Werte) für die Pose aus einem YOLOX-Kasten.

    Dieselbe Form wie `person_aus_pose`: Hüftmitte und ein Punkt über dem Kopf, dessen
    Abstand die Grösse trägt. Aus dem Kasten geschätzt (Hüfte auf 52 %, der Punkt knapp
    unter der Oberkante) — die Pose findet die echten Punkte darin selbst.
    """
    x1, y1, x2, y2, score = kasten
    mitte, hoehe = (x1 + x2) / 2.0, y2 - y1
    return np.array([x1, y1, x2, y2, mitte, y1 + KASTEN_HUEFTE * hoehe, mitte,
                     y1 + KASTEN_OBEN * hoehe, 0.0, 0.0, 0.0, 0.0, score], dtype=np.float32)


def koerper_aus_kasten(kasten):
    """Ein `Koerper` aus dem Kasten allein — wenn die Pose darin kein Skelett fand.

    Die Hüfte auf 52 % (die Gegenprobe prüft sie wie jede andere), keine Schulter: ohne
    Skelett gibt es keine Schulterlinie für die Nase und keinen Rumpf für Handzeichen.
    """
    x1, y1, x2, y2, score = kasten
    huefte = ((x1 + x2) / 2.0, y1 + KASTEN_HUEFTE * (y2 - y1))
    return Koerper(huefte, None, float(score), (float(x1), float(y1), float(x2), float(y2)))


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
    werden die Zoo-Klassen mit den Modelldateien gebaut. `personen(rgb) ->
    [(x1, y1, x2, y2, score)]` ist die Suche mit YOLOX (`YoloxPersonen`); ohne
    Testtüren wird sie aus `personenmodell()` gebaut, und fehlt das Modell, sucht
    der MediaPipe-Erkenner wie bisher — `suchweg` sagt welcher, `ohne_yolox` warum.

    Zähler: `suchen` (Takte, in denen der Erkenner lief) und `spuren` (Takte,
    in denen die Spur getragen hat, ohne Erkenner). Für die Folge-Aufnahme
    (`workshop/folgeaufnahme.py`) dazu je `finde`: `letzter_weg` ("spur",
    "yolox", "yolox-kasten" ohne Skelett, oder "suche" mit MediaPipe) und `letzte_landmarken` — 33 × (x, y, Präsenz) im PANORAMA, auch
    wenn die Pose auf einer Kachel lief; None ohne Körper.
    """

    def __init__(self, ordner=None, erkenner=None, pose=None, kacheln=True,
                 mindestsicherheit=MINDESTSICHERHEIT, personen=None):
        self.ohne_yolox = None
        if personen is None and (erkenner is None or pose is None):
            try:
                personen = YoloxPersonen(personenmodell(ordner))
            except SpotlabError as fehler:
                self.ohne_yolox = str(fehler)
        if pose is None or (erkenner is None and personen is None):
            pfad_erkenner, pfad_pose = modellpfade(ordner)
            MPPersonDet, MPPose = _zoo()
            if pose is None:
                pose = MPPose(str(pfad_pose), confThreshold=float(mindestsicherheit)).infer
            if erkenner is None and personen is None:
                erkenner = MPPersonDet(str(pfad_erkenner),
                                       scoreThreshold=float(mindestsicherheit)).infer
        self._erkenner = erkenner
        self._pose = pose
        self._personen = personen
        self.suchweg = "mediapipe" if personen is None else "yolox"
        self._kacheln = kacheln
        self._spur = None
        self.suchen = 0
        self.spuren = 0
        self.letzter_weg = None
        self.letzte_landmarken = None

    def _ausschnitte(self, bgr):
        """Das ganze Bild, dann drei quadratische Kacheln (links, Mitte, rechts)."""
        h, w = bgr.shape[:2]
        yield 0, bgr
        if self._kacheln and w > h:
            for x0 in (0, (w - h) // 2, w - h):
                yield x0, np.ascontiguousarray(bgr[:, x0:x0 + h])

    def finde(self, feld):
        bgr = _dreikanalig(feld)
        self.letzte_landmarken = None
        if self._spur is not None:
            self.letzter_weg = "spur"
            ergebnis = self._pose(bgr, self._spur.copy())
            koerper = None if ergebnis is None else koerper_aus_pose(ergebnis[1], ergebnis[5])
            if koerper is not None:
                self.spuren += 1
                self._spur = person_aus_pose(ergebnis[1])
                self.letzte_landmarken = _skelett(ergebnis[1])
                return [koerper]
            self._spur = None

        self.suchen += 1
        if self._personen is not None:
            return self._suche_yolox(feld, bgr)
        self.letzter_weg = "suche"
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
        self.letzte_landmarken = _skelett(landmarken)
        return [koerper]

    def _suche_yolox(self, feld, bgr):
        """Der sicherste Mensch aus YOLOX, das Skelett aus der Pose in seinem Kasten."""
        self.letzter_weg = "yolox"
        kaesten = self._personen(_rgb(feld))
        if not kaesten:
            return []
        kasten = max(kaesten, key=lambda k: k[4])
        ergebnis = self._pose(bgr, kasten_zeile(kasten))
        koerper = None if ergebnis is None else koerper_aus_pose(ergebnis[1], ergebnis[5])
        if koerper is None:
            # Kein Skelett: der Kasten selbst ist das Ziel, eine Spur gibt es nicht.
            self.letzter_weg = "yolox-kasten"
            return [koerper_aus_kasten(kasten)]
        self._spur = person_aus_pose(ergebnis[1])
        self.letzte_landmarken = _skelett(ergebnis[1])
        return [koerper]


def _skelett(landmarken):
    """Die 33 Körperpunkte als (x, y, Präsenz) — was die Folge-Aufnahme zeichnet."""
    lm = np.asarray(landmarken, dtype=float)
    return np.column_stack([lm[:33, 0], lm[:33, 1], lm[:33, 4]])


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
