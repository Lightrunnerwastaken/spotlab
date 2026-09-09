"""Gesichter in Spots Frontkameras — und die Prüfung, ob es überhaupt eines sein kann.

Der Erkenner ist YuNet aus OpenCV (`cv2.FaceDetectorYN`), ein kleines
ONNX-Modell. OpenCV ist KEINE Abhängigkeit von spotlab: wer Gesichter sucht,
installiert das Extra `[gesicht]` und legt die Modelldatei ab. Fehlt eines von
beidem, sagt es das im Klartext, statt still nichts zu finden.

WAS DIE KAMERAS SEHEN. Die Frontkameras schauen rund 20° nach unten. Gemessen
an der Aufzeichnung vom 12.08.2026:

    Abstand      höchster sichtbarer Punkt
    1.5 m        1.20 m
    2.0 m        1.45 m
    3.0 m        1.94 m
    4.0 m        2.43 m

Das Gesicht eines stehenden Erwachsenen liegt bei 1.5 bis 1.75 m — es kommt
also erst ab gut zweieinhalb Metern ins Bild. Näher sieht Spot Beine. Der
Folgemodus will 1.6 m Abstand halten; **die Gesichtssuche allein reicht dafür
nicht**, sie gehört mit einem zweiten Finder zusammengeschaltet.

UND WAS DER ERKENNER ANSTELLT. Über dieselbe Aufzeichnung fand YuNet in 4 von
107 Takten etwas; von Hand nachgesehen war der beste Treffer eine Stuhllehne
und der zweitbeste ein SCHIENBEIN. Ein Kasten mit hoher Punktzahl ist deshalb
noch kein Gesicht. Hier steht die Gegenprobe aus Geometrie: aus Höhenwinkel und
gemessenem Abstand folgt die Höhe des Kastens über dem Boden, und was nicht auf
Kopfhöhe liegt, ist keiner. Das Schienbein fällt damit heraus.

Der Abstand kommt aus den TIEFENKAMERAS, nicht aus der Grösse des Kastens: an
ihm hängt der Mindestabstand des Folgemodus, und eine geschätzte Entfernung
wäre dort eine erfundene Sicherheit.
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from spotlab.errors import SpotlabError

MODELL_DATEI = "face_detection_yunet_2023mar.onnx"
MODELL_ORDNER = Path.home() / ".spotlab" / "modelle"
ENV_MODELL = "SPOTLAB_GESICHTSMODELL"
BEZUGSQUELLE = "https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet"

MINDESTSCORE = 0.6
# Auf dieser Höhe über dem Boden darf ein Gesicht liegen. Unten: ein sitzender
# Mensch. Oben: ein sehr grosser stehender. Alles darunter ist ein Knie.
KOPF_UNTEN_M = 1.0
KOPF_OBEN_M = 2.1
# So weit um die Richtung des Kastens werden Tiefenpunkte gesammelt.
FENSTER_GRAD = 5.0
MIN_PUNKTE = 8


@dataclass(frozen=True)
class Gesicht:
    bearing: float           # Grad, links positiv
    elevation: float         # Grad, nach oben positiv
    distance: float          # Meter, aus der Tiefenkamera
    height: float            # Meter über dem Boden — die Gegenprobe
    score: float
    box: tuple               # (x, y, breite, hoehe) im Panorama, für die Anzeige


def modellpfad(pfad=None, umgebung=None):
    """Wo die Modelldatei liegt — oder ein Fehler, der sagt, woher man sie bekommt.

    Argument, dann `SPOTLAB_GESICHTSMODELL`, dann der Standardordner. Die
    Umgebungsvariable, damit eine schon vorhandene Kopie nicht kopiert werden muss.
    """
    kandidaten = [pfad, (os.environ if umgebung is None else umgebung).get(ENV_MODELL),
                  MODELL_ORDNER / MODELL_DATEI]
    for kandidat in kandidaten:
        if kandidat and Path(kandidat).is_file():
            return Path(kandidat)
    raise SpotlabError(
        f"Das Gesichtsmodell fehlt (gesucht: {MODELL_ORDNER / MODELL_DATEI}). Lade "
        f"`{MODELL_DATEI}` aus dem OpenCV-Zoo ({BEZUGSQUELLE}) und lege es dort ab, "
        f"oder setze {ENV_MODELL} auf eine vorhandene Kopie."
    )


def erkenner(breite, hoehe, pfad=None, mindestscore=MINDESTSCORE):
    """Ein YuNet-Erkenner für Bilder dieser Grösse."""
    try:
        import cv2
    except ImportError as fehler:
        raise SpotlabError(
            "Für die Gesichtssuche fehlt OpenCV. Installiere das Extra: "
            "pip install \"spotlab[gesicht]\""
        ) from fehler
    return cv2.FaceDetectorYN.create(
        str(modellpfad(pfad)), "", (int(breite), int(hoehe)), score_threshold=float(mindestscore)
    )


def kaesten(feld, erkenner_):
    """Die Kästen, die der Erkenner findet: (x, y, breite, hoehe, score)."""
    import cv2

    bild = feld if feld.ndim == 3 else cv2.cvtColor(feld, cv2.COLOR_GRAY2BGR)
    erkenner_.setInputSize((bild.shape[1], bild.shape[0]))
    _, gefunden = erkenner_.detect(bild)
    if gefunden is None:
        return []
    return [(float(g[0]), float(g[1]), float(g[2]), float(g[3]), float(g[14])) for g in gefunden]


def abstand_in_richtung(punkte, peilung, hoehenwinkel, fenster=FENSTER_GRAD,
                        min_punkte=MIN_PUNKTE):
    """Der Abstand in Metern zu den Tiefenpunkten in dieser Richtung — oder None.

    `punkte` sind Nx3 im aufgerichteten Körperrahmen (`backends/real/tiefe.py`):
    x vorwärts, y links, z nach oben, Ursprung Körpermitte. Genommen wird der
    MEDIAN, nicht das Minimum: ein einzelner Ausreisser vor dem Gesicht wäre
    sonst der gemeldete Abstand.
    """
    if punkte is None or len(punkte) < 1:
        return None
    punkte = np.asarray(punkte, dtype=float)
    eben = np.hypot(punkte[:, 0], punkte[:, 1])
    gueltig = eben > 1e-3
    if not gueltig.any():
        return None
    punkte, eben = punkte[gueltig], eben[gueltig]
    peilungen = np.degrees(np.arctan2(punkte[:, 1], punkte[:, 0]))
    winkel = np.degrees(np.arctan2(punkte[:, 2], eben))
    nah = (np.abs(peilungen - peilung) <= fenster) & (np.abs(winkel - hoehenwinkel) <= fenster)
    if int(nah.sum()) < min_punkte:
        return None
    return float(np.median(eben[nah]))


def gesichter(feld, pano, erkenner_, punkte, kamerahoehe,
              unten=KOPF_UNTEN_M, oben=KOPF_OBEN_M):
    """Geprüfte Gesichter aus einem Panorama, das nächste zuerst.

    Geprüft heisst: der Kasten hat eine gemessene Entfernung UND liegt damit auf
    Kopfhöhe. Ein Kasten ohne Tiefenpunkte zählt nicht — ohne Entfernung gibt es
    keine Gegenprobe, und ohne Gegenprobe ist ein Schienbein ein Gesicht.
    """
    gefunden = []
    for x, y, breite, hoehe, score in kaesten(feld, erkenner_):
        peilung, hoehenwinkel = pano.winkel(x + breite / 2.0, y + hoehe / 2.0)
        abstand = abstand_in_richtung(punkte, peilung, hoehenwinkel)
        if abstand is None:
            continue
        ueber_boden = kamerahoehe + abstand * math.tan(math.radians(hoehenwinkel))
        if not unten <= ueber_boden <= oben:
            continue
        gefunden.append(Gesicht(peilung, hoehenwinkel, abstand, ueber_boden, score,
                                (x, y, breite, hoehe)))
    return sorted(gefunden, key=lambda g: g.distance)
