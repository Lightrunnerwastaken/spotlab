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


# Warum ein Kasten NICHT durchkam. Die Zeichenketten stehen so im Protokoll der
# Messprobe und sind damit Teil der Schnittstelle nach aussen.
OHNE_TIEFE = "keine tiefenpunkte"
ZU_TIEF = "zu tief"
ZU_HOCH = "zu hoch"
ZU_GROSS = "zu gross fuer die tiefe"
ZU_KLEIN = "zu klein fuer die tiefe"
# Wie breit ein YuNet-Kasten in Metern ist (rund 1.4-mal das Gesicht): gemessen am
# 16.09.2026 59 px bei 1.5 m, 44 bei 2 m, 29 bei 3 m -- bei 7 px je Grad jedes Mal 0.22 m.
KASTEN_BREITE_M = 0.22
# So weit darf die Kastenbreite von der zur gemessenen Tiefe passenden abweichen. Am
# 17.09.2026 setzte YuNet in einem Lauf sechsmal einen 170-190 px breiten Kasten an
# derselben Stelle bei +57 Grad: bei 2 m waere das ein 0.9 m breites Gesicht.
GROESSE_SPANNE = (0.4, 2.5)


@dataclass(frozen=True)
class Befund:
    """Ein Kasten des Erkenners MIT seinem Urteil — auch wenn er verworfen wurde.

    `gesichter()` gibt nur die genommenen zurück, und das ist für den Regler
    richtig. Am Gerät hiess das Ergebnis damit aber immer „nichts gefunden",
    ohne zu sagen, ob YuNet gar nichts sah oder ob die Gegenprobe etwas verwarf
    — und an welcher der beiden Schranken. Für Abnahmepunkt A34 Teil 3
    („notieren, ob trotzdem etwas durchkommt") reicht das nicht.

    Dieselbe Regel wie im Gehzeit-Versuch: verworfen heisst PROTOKOLLIERT, nicht
    verschwiegen. Und fehlende Messwerte sind None, nie 0 — ein Kasten ohne
    Tiefenpunkte hat keinen Abstand und keine Höhe, nicht Abstand null.
    """

    bearing: float
    elevation: float
    score: float
    box: tuple
    distance: float = None
    height: float = None
    genommen: bool = False
    grund: str = None


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


# So viele gedeckte Bildpunkte braucht es, bevor eine Kennlinie daraus etwas
# taugt. Darunter bleibt das Bild, wie es ist — ein abgerissener Bildabruf soll
# nicht in eine Division durch null laufen.
MINDESTPUNKTE_AUFHELLEN = 100


def aufhellen(feld):
    """Histogrammausgleich über die GEDECKTEN Bildpunkte — für den Erkenner.

    Die Frontbilder des Spot sind im Gebäude dunkel: über 60 echte Panoramen vom
    11.09.2026 lag die mittlere Helligkeit bei 36 von 255. YuNet kam damit auf
    Punktzahlen um 0.37, und der eine Kasten, den es setzte, war 493×551 px
    gross — ein halbes Bild, kein Gesicht. Nach dem Ausgleich sitzt ein
    123×137-Kasten mit 0.71 auf dem Gesicht, also über der Schwelle von 0.6.

    NUR ÜBER DIE GEDECKTEN PUNKTE. Die schwarzen Ecken des Zuschnitts `ALLES`
    sind rund ein Drittel der Fläche und kein Bildinhalt; nähme man sie mit,
    verschöbe schon die FORM des Zuschnitts die Helligkeit. Sie bleiben schwarz.

    Verglichen wurde an denselben 60 Bildern bei der Produktionsschwelle 0.6:
    roh 0 Treffer, Histogrammausgleich 2 (beide gesichtsgross),
    Perzentil-Streckung 0, CLAHE 0, Streckung mit CLAHE 1. **Zwei von sechzig
    ist keine brauchbare Erkennung** — die Grenze bleibt die Geometrie (das
    Gesicht liegt am oberen Rand der Deckung und wird von der Naht beschnitten).
    Das Aufhellen macht die Erkennung möglich, nicht zuverlässig.

    Die FAHRANSICHT bleibt unberührt: `ansicht.jpg` geht über einen eigenen Weg
    (`workshop/blick.py`, Zuschnitt `RECHTECK`). Ein aufgehelltes Livebild wäre
    eine Aussage über die Belichtung, die niemand geprüft hat.

    SEIT DEM 16.09.2026 IST DAS DER RÜCKFALL, NICHT DER HAUPTWEG. Der Schul-Spot
    liefert die Frontbilder in Farbe, und `folgen.gesichtsaufnahme` erbittet sie
    so; `kaesten()` hellt nur graue Bilder auf. Gemessen an demselben Bild durch
    beide Wege (390 Takte): Farbe ohne Aufhellung fand jedes echte Gesicht, das
    Grau mit Aufhellung fand — und sieben Riesenkästen weniger (Phantome auf
    Beinen und einem Regalbrett, 0.60–0.78). Ob Farbe auch das dunkle, liegende
    Bild vom 11.09. geschafft hätte, ist offen: davon gibt es keine Farbaufnahme.
    """
    import cv2

    gedeckt = feld > 0
    if int(gedeckt.sum()) < MINDESTPUNKTE_AUFHELLEN:
        return feld
    hist = cv2.calcHist([feld], [0], gedeckt.astype(np.uint8), [256], [0, 256]).ravel()
    summe = np.cumsum(hist)
    if summe[-1] <= 0:
        return feld
    # Monoton steigende Kennlinie: was dunkler war, bleibt dunkler. Sonst
    # verschöbe das Aufhellen Kanten, statt sie sichtbar zu machen.
    kennlinie = np.clip(summe / summe[-1] * 255.0, 0, 255).astype(np.uint8)
    hell = kennlinie[feld]
    hell[~gedeckt] = 0
    return hell


def kaesten(feld, erkenner_, mit_ausgleich=True):
    """Die Kästen, die der Erkenner findet: (x, y, breite, hoehe, score).

    `mit_ausgleich=False` füttert das ROHE Bild — für den Vergleich in der
    Messprobe und für den Schienbein-Test, der die Gegenprobe prüft und dafür
    einen Fehltreffer braucht. Im Betrieb wird immer ausgeglichen.
    """
    import cv2

    if mit_ausgleich and feld.ndim == 2:
        feld = aufhellen(feld)
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
              unten=KOPF_UNTEN_M, oben=KOPF_OBEN_M, blick_grad=0.0):
    """Geprüfte Gesichter aus einem Panorama, das nächste zuerst.

    Geprüft heisst: der Kasten hat eine gemessene Entfernung UND liegt damit auf
    Kopfhöhe. Ein Kasten ohne Tiefenpunkte zählt nicht — ohne Entfernung gibt es
    keine Gegenprobe, und ohne Gegenprobe ist ein Schienbein ein Gesicht.

    `blick_grad` ist die Neigung des Körpers nach OBEN. Der Höhenwinkel aus dem
    Panorama ist KÖRPERFEST: hebt Spot die Nase, erscheint derselbe Punkt weiter
    unten im Bild. Ohne diese Korrektur läge ein Gesicht auf drei Metern bei 15°
    Neigung rund 80 cm zu tief und fiele durch die Prüfung. Die Tiefenpunkte sind
    dagegen schon schwerkraftgerecht aufgerichtet (`tiefe.py`), deshalb wird auch
    für sie der korrigierte Winkel genommen.
    """
    gefunden = [
        Gesicht(b.bearing, b.elevation, b.distance, b.height, b.score, b.box)
        for b in beurteile(feld, pano, erkenner_, punkte, kamerahoehe,
                           unten=unten, oben=oben, blick_grad=blick_grad)
        if b.genommen
    ]
    return sorted(gefunden, key=lambda g: g.distance)


def beurteile(feld, pano, erkenner_, punkte, kamerahoehe,
              unten=KOPF_UNTEN_M, oben=KOPF_OBEN_M, blick_grad=0.0,
              kaesten_holen=None):
    """JEDER Kasten des Erkenners mit seinem Urteil — genommen oder warum nicht.

    Die eine Formulierung der Gegenprobe; `gesichter()` ist die Auswahl daraus.
    Zwei Formulierungen hiessen, dass die Messprobe etwas anderes misst, als der
    Folgemodus tut — und das fiele erst am Gerät auf, wo niemand es nachrechnet.

    `kaesten_holen` ist die Testtür: ohne sie fragt sie den echten Erkenner.
    """
    hole = kaesten_holen or kaesten
    befunde = []
    for x, y, breite, hoehe, score in hole(feld, erkenner_):
        peilung, im_bild = pano.winkel(x + breite / 2.0, y + hoehe / 2.0)
        hoehenwinkel = im_bild + float(blick_grad)
        kasten = (x, y, breite, hoehe)
        abstand = abstand_in_richtung(punkte, peilung, hoehenwinkel)
        if abstand is None:
            befunde.append(Befund(peilung, hoehenwinkel, score, kasten, grund=OHNE_TIEFE))
            continue
        ueber_boden = kamerahoehe + abstand * math.tan(math.radians(hoehenwinkel))
        grund = None
        if ueber_boden < unten:
            grund = ZU_TIEF
        elif ueber_boden > oben:
            grund = ZU_HOCH
        else:
            grund = groesse_passt(_kastenbreite_grad(pano, x, y, breite, hoehe), abstand)
        befunde.append(Befund(peilung, hoehenwinkel, score, kasten,
                              distance=abstand, height=ueber_boden,
                              genommen=grund is None, grund=grund))
    return befunde


def _kastenbreite_grad(pano, x, y, breite, hoehe):
    """Die Winkelbreite des Kastens aus dem Panorama — 0, wenn es keine kennt."""
    links, _ = pano.winkel(x, y + hoehe / 2.0)
    rechts, _ = pano.winkel(x + breite, y + hoehe / 2.0)
    return abs(float(links) - float(rechts))


def groesse_passt(breite_grad, abstand):
    """None, wenn der Kasten bei dieser Tiefe ein Gesicht sein kann — sonst `ZU_GROSS`/`ZU_KLEIN`.

    Ohne Winkelbreite (0, etwa eine Attrappe mit fester Richtung) wird nicht
    geraten, sondern die Probe ausgelassen: die Höhenprobe steht dann allein.
    """
    if breite_grad <= 0.0 or abstand <= 0.0:
        return None
    erwartet = 2.0 * math.degrees(math.atan(KASTEN_BREITE_M / 2.0 / abstand))
    verhaeltnis = breite_grad / erwartet
    if verhaeltnis > GROESSE_SPANNE[1]:
        return ZU_GROSS
    if verhaeltnis < GROESSE_SPANNE[0]:
        return ZU_KLEIN
    return None
