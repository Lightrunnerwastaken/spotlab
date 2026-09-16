"""Handgesten: MediaPipe-Handflächen-Erkenner und -Handpose aus dem OpenCV-Zoo, über `cv2.dnn`.

DER ANLASS. Wer Spot folgen lässt, hat oft die Hände frei und das Tablet nicht in
der Hand. Zwei Zeichen genügen: die OFFENE HAND heisst Halt, der DAUMEN HOCH
heisst Weiter. Beides kann nur nehmen und zurückgeben, was das Folgen ohnehin
erlaubt — eine Geste ist kein Fahrbefehl, und keine Schranke wird davon berührt.

GEMESSEN am 16.09.2026 über 510 gespeicherte Panoramen (640×480-Fischaugen, ohne
absichtliche Gesten): auf dem GANZEN Panorama (192 px Eingabe) fand die Handpose
keine einzige Hand, auf drei quadratischen Kacheln zwei; im Ausschnitt um den
Oberkörper aus der Körper-Pose 31 — sitzend nah 23 von 40 Takten, stehend auf
2–3 m mit hängenden Armen 3 von 120. Eine Hand auf 2 m ist im Panorama 30 px
gross, im ganzen Bild auf 192 px also fünf. Deshalb liest der Gestenleser die
Hand NUR beim gefolgten Körper, im Rumpf-Ausschnitt (`rumpf_ausschnitt`), und
nur dort ist die Frage auch sinnvoll: die Geste eines Zuschauers zählt nicht.
Preis je Lesung: Handfläche 45 ms, Handpose 18 ms.

Die Regel aus den 21 Landmarken steht in `geste_aus_landmarken`: ein Finger ist
gestreckt, wenn seine Spitze weiter vom Handgelenk liegt als sein Mittelgelenk.
Die offene Hand muss AUFRECHT stehen (Mittelfingerspitze mindestens `AUFRECHT`
Handflächenlängen über dem Handgelenk), der Daumen muss nach OBEN zeigen, nicht
nur abstehen. Gemessen an den 31 natürlichen Händen derselben Probe (hängend,
zwischen den Knien, auf dem Tablet): fünf hatten alle vier Finger gestreckt,
und bei allen 31 lagen die Spitzen unter dem Gelenk (−0.3 bis −2.75) oder knapp
darüber (+0.30); der Daumen stand bei jeder ab (1.4–2.0 Grundgelenk-Längen),
zeigte aber nach unten (−0.3 bis −1.0) oder kaum hinauf (+0.46). Ohne die beiden
Richtungsregeln wären das fünf falsche Halt gewesen; mit ihnen null Gesten aus
31 Händen, die keine zeigten. Und eine Geste zählt erst, wenn sie
`Entprellung.takte` Lesungen hintereinander steht, und dann genau einmal.

Die Referenzklassen des Zoos liegen unverändert in `zoo/` (Apache 2.0). Hier
steht nur, was spotlab dazutut: Modellsuche, Ausschnitt, Regel, Entprellung.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from spotlab.backends.real import gesicht
from spotlab.errors import SpotlabError

MODELL_HANDFLAECHE = "palm_detection_mediapipe_2023feb.onnx"       # 3 905 734 Bytes
MODELL_HANDPOSE = "handpose_estimation_mediapipe_2023feb.onnx"     # 4 099 621 Bytes
MODELL_ORDNER = gesicht.MODELL_ORDNER
ENV_ORDNER = "SPOTLAB_HANDMODELLE"
BEZUGSQUELLE = "https://github.com/opencv/opencv_zoo/tree/main/models"

# Landmarken nach MediaPipe Hands (21 Punkte): 0 Handgelenk, dann je Finger vier
# Punkte von der Wurzel zur Spitze — Daumen 1–4, Zeige 5–8, Mittel 9–12, Ring 13–16, Klein 17–20.
HANDGELENK = 0
DAUMEN_MCP, DAUMEN_SPITZE = 2, 4
MITTEL_MCP = 9
FINGER = ((6, 8), (10, 12), (14, 16), (18, 20))   # (Mittelgelenk, Spitze) der vier Finger

MINDESTSICHERHEIT = 0.5          # Handflächen-Erkenner und Handpose
GESTRECKT = 1.15                 # Spitze so viel weiter vom Handgelenk als das Mittelgelenk
DAUMEN_GESTRECKT = 1.3           # Daumenspitze so viel weiter als das Daumengrundgelenk
DAUMEN_OBEN = 0.6                # Anteil der Daumenlänge, den die Spitze über dem Grundgelenk liegt
AUFRECHT = 0.8                   # Mittelfingerspitze so viele Handflächenlängen über dem Handgelenk

AUSSCHNITT_FAKTOR = 3.0          # Seite des Rumpf-Ausschnitts in Schulterbreiten
MINDEST_AUSSCHNITT_PX = 160
KASTEN_ZU_SCHULTER = 1.5         # der Kasten über alle Punkte ist etwa so viel breiter als die Schultern

HALT = "halt"
WEITER = "weiter"


@dataclass(frozen=True)
class Hand:
    """Eine gefundene Hand, in Bildkoordinaten des Panoramas."""

    landmarken: object           # 21×3: x, y im Panorama, z relativ zum Handgelenk
    conf: float                  # Sicherheit der Handpose
    kasten: tuple                # (x1, y1, x2, y2)


# ---------------------------------------------------------------- Modelle


def modellpfade(ordner=None, umgebung=None):
    """(Handfläche, Handpose) — oder ein Fehler, der sagt, woher man sie bekommt.

    Argument, dann `SPOTLAB_HANDMODELLE`, dann der Standardordner (derselbe wie
    beim Gesicht und beim Körper). Ein Ordner zählt nur, wenn BEIDE Dateien darin liegen.
    """
    kandidaten = [ordner, (os.environ if umgebung is None else umgebung).get(ENV_ORDNER),
                  MODELL_ORDNER]
    for kandidat in kandidaten:
        if not kandidat:
            continue
        handflaeche = Path(kandidat) / MODELL_HANDFLAECHE
        handpose = Path(kandidat) / MODELL_HANDPOSE
        if handflaeche.is_file() and handpose.is_file():
            return handflaeche, handpose
    raise SpotlabError(
        f"Die Handmodelle fehlen (gesucht in {MODELL_ORDNER}): `{MODELL_HANDFLAECHE}` und "
        f"`{MODELL_HANDPOSE}` aus dem OpenCV-Zoo ({BEZUGSQUELLE}, Ordner "
        f"palm_detection_mediapipe und handpose_estimation_mediapipe; der Zoo führt sie über "
        f"git-lfs, der gewöhnliche raw-Link liefert einen 132-Byte-Zeiger). Dort ablegen, "
        f"oder {ENV_ORDNER} auf einen Ordner mit beiden Dateien setzen."
    )


def _zoo():
    from spotlab.backends.real.zoo import mp_handpose, mp_palmdet

    return mp_palmdet.MPPalmDet, mp_handpose.MPHandPose


# ------------------------------------------------------------- Die Regel


def geste_aus_landmarken(lm):
    """`"halt"` (offene, aufrechte Hand), `"weiter"` (Daumen hoch) oder None.

    Alles in Bildkoordinaten, y nach unten, und alles relativ zur Hand selbst —
    die Regel darf nicht daran hängen, wie gross die Hand im Bild ist. Ein
    Zeigefinger, eine Faust, ein Daumen nach unten und eine flach liegende
    offene Hand sind KEINE Geste: lieber eine übersehen als eine erfinden, denn
    ein erfundenes Halt hält den Roboter an, ein erfundenes Weiter lässt ihn
    losgehen.
    """
    lm = np.asarray(lm, dtype=float)
    gelenk = lm[HANDGELENK, :2]

    def abstand(i):
        return float(np.linalg.norm(lm[i, :2] - gelenk))

    gestreckt = [abstand(spitze) > abstand(mittel) * GESTRECKT for mittel, spitze in FINGER]
    handflaeche = max(abstand(MITTEL_MCP), 1e-6)
    aufrecht = (gelenk[1] - lm[FINGER[1][1], 1]) / handflaeche
    if all(gestreckt):
        return HALT if aufrecht >= AUFRECHT else None
    if any(gestreckt):
        return None
    daumen = lm[DAUMEN_SPITZE, :2] - lm[DAUMEN_MCP, :2]
    daumen_lang = abstand(DAUMEN_SPITZE) > abstand(DAUMEN_MCP) * DAUMEN_GESTRECKT
    daumen_oben = -daumen[1] >= DAUMEN_OBEN * max(float(np.linalg.norm(daumen)), 1e-6)
    if daumen_lang and daumen_oben:
        return WEITER
    return None


def geste_der_haende(haende):
    """Die Geste der SICHERSTEN Hand — oder None ohne Hand."""
    if not haende:
        return None
    return geste_aus_landmarken(max(haende, key=lambda h: h.conf).landmarken)


class Entprellung:
    """Eine Geste zählt erst, wenn sie `takte` Lesungen hintereinander steht — und dann EINMAL.

    Der Erkenner stolpert; ein einzelner Takt „offen" darf keinen fahrenden
    Roboter anhalten. Eine gehaltene Hand meldet nicht jeden Takt neu, sonst
    hielte „Halt" den Zähler und „Weiter" käme nie durch. Erst ein Aussetzer
    (keine Geste) oder ein Wechsel setzt die Zählung zurück.
    """

    def __init__(self, takte=3):
        self.takte = int(takte)
        self._geste = None
        self._anzahl = 0
        self._gemeldet = False

    def naechste(self, geste):
        if geste != self._geste:
            self._geste, self._anzahl, self._gemeldet = geste, 0, False
        if geste is None:
            return None
        self._anzahl += 1
        if self._anzahl >= self.takte and not self._gemeldet:
            self._gemeldet = True
            return geste
        return None


# -------------------------------------------------------- Der Ausschnitt


def rumpf_ausschnitt(koerper, breite, hoehe, faktor=AUSSCHNITT_FAKTOR, mindest=MINDEST_AUSSCHNITT_PX):
    """(x0, y0, seite): ein Quadrat um die Brust des Körpers, im Bild — oder None ohne Schultern.

    Mitte zwischen Schulter- und Hüftmitte (ohne Hüfte: unter den Schultern),
    Seite `faktor` Schulterbreiten, mindestens `mindest` Pixel, am Bildrand
    verschoben statt beschnitten. Dort sind die Hände, wenn jemand ein Zeichen
    gibt: vor der Brust oder neben dem Kopf.
    """
    if koerper.schulter is None:
        return None
    sx, sy = koerper.schulter
    schulterbreite = getattr(koerper, "schulterbreite", None)
    if not schulterbreite:
        x1, _, x2, _ = koerper.kasten
        schulterbreite = abs(x2 - x1) / KASTEN_ZU_SCHULTER
    if koerper.huefte is not None:
        mx, my = (sx + koerper.huefte[0]) / 2, (sy + koerper.huefte[1]) / 2
    else:
        mx, my = sx, sy + 0.8 * schulterbreite
    seite = max(int(round(faktor * schulterbreite)), int(mindest))
    seite = min(seite, int(breite), int(hoehe))
    x0 = int(min(max(mx - seite / 2, 0), breite - seite))
    y0 = int(min(max(my - seite / 2, 0), hoehe - seite))
    return x0, y0, seite


# ----------------------------------------------------------- Der Erkenner


def _dreikanalig(feld):
    """Die Zoo-Klassen wollen BGR mit drei Kanälen — dieselbe Regel wie beim Körper."""
    from spotlab.backends.real import koerper

    return koerper._dreikanalig(feld)


class Handerkenner:
    """Handfläche, dann Handpose je Handfläche. `finde(feld, ausschnitt)` gibt die Hände zurück.

    `handflaeche` und `handpose` sind die Testtüren: `handflaeche(bgr) -> Zeilen
    (N×19: Kasten, 7 Landmarken, Punktzahl)`, `handpose(bgr, zeile) -> Vektor
    (Kasten, 21×3 Bildpunkte, 21×3 Weltpunkte, Händigkeit, conf)` oder None.
    Ohne sie werden die Zoo-Klassen mit den Modelldateien gebaut. `ausschnitt`
    ist `(x0, y0, seite)` im Feld; die Hände kommen in FELD-Koordinaten zurück.
    """

    def __init__(self, ordner=None, handflaeche=None, handpose=None,
                 mindestsicherheit=MINDESTSICHERHEIT):
        if handflaeche is None or handpose is None:
            pfad_handflaeche, pfad_handpose = modellpfade(ordner)
            MPPalmDet, MPHandPose = _zoo()
            det = MPPalmDet(str(pfad_handflaeche), scoreThreshold=float(mindestsicherheit))
            pos = MPHandPose(str(pfad_handpose), confThreshold=float(mindestsicherheit))
            handflaeche = handflaeche or det.infer
            handpose = handpose or pos.infer
        self._handflaeche = handflaeche
        self._handpose = handpose
        self.suchen = 0

    def finde(self, feld, ausschnitt=None):
        bgr = _dreikanalig(feld)
        x0 = y0 = 0
        if ausschnitt is not None:
            x0, y0, seite = (int(v) for v in ausschnitt)
            bgr = np.ascontiguousarray(bgr[y0:y0 + seite, x0:x0 + seite])
        self.suchen += 1
        haende = []
        for zeile in np.asarray(self._handflaeche(bgr)):
            ergebnis = self._handpose(bgr, np.array(zeile, dtype=np.float32).copy())
            if ergebnis is None:
                continue
            ergebnis = np.asarray(ergebnis, dtype=float)
            landmarken = ergebnis[4:67].reshape(21, 3).copy()
            landmarken[:, 0] += x0
            landmarken[:, 1] += y0
            kasten = (float(ergebnis[0] + x0), float(ergebnis[1] + y0),
                      float(ergebnis[2] + x0), float(ergebnis[3] + y0))
            haende.append(Hand(landmarken, float(ergebnis[-1]), kasten))
        return haende
