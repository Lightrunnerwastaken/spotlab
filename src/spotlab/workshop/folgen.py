"""Folgen: Spot geht einem Menschen hinterher — mit Abstand und mit Schranken.

Das Programm dazu ist `Beispiele/folgen.py` im Arbeitsordner. Es besteht aus
zwei Teilen, die man getrennt lesen und getrennt austauschen kann:

ZIEL-FINDER   sagt, wo das Ziel ist: `(Peilung in Grad, Abstand in Metern)`.
              Woher er das weiss, ist ihm überlassen — ein AprilTag am Rucksack
              (`tag_finder`), Spots eigener Personen-Tracker (`personen_finder`)
              oder etwas Selbstgebautes. Alle drei liefern dasselbe Paar.
REGLER        `folge()` hält daraus den Abstand und die Nase auf das Ziel.

Die Trennung ist der Punkt: der Regler bleibt gleich, wenn der Finder wechselt,
und damit lassen sich Strategien VERGLEICHEN, statt sie zu behaupten.

SCHRANKEN. Ein Roboter, der von selbst einem Menschen hinterherläuft, ist ein
anderer Fall als ein Roboter, den jemand fährt. Deshalb, alle gleichzeitig:

- Näher als `MIN_ABSTAND_M` geht er nie. Rückwärts fährt er auch nicht — nach
  hinten sieht er nichts; kommt der Mensch näher, bleibt Spot stehen.
- Ohne Ziel steht er. SOFORT, in demselben Takt, nicht nach einer Frist. Das
  ist derselbe Totmann-Gedanke wie im Fahrmodus.
- Vorwärts nur, wenn das Hindernisgitter voraus Platz meldet, wenn über dem
  Weg genug Kopfraum ist und wenn keine Sperrzone davorliegt. Jede Schranke,
  die ihre Daten NICHT lesen kann, verbietet die Fahrt (fail-closed) — eine
  Schranke, die bei Störung durchwinkt, ist keine.
- Das Tempo deckelt zusätzlich `config.toml`, wie bei jedem `walk()`.

Der Kopfraum wird nicht in jedem Takt geprüft: zwei Tiefenbilder über WLAN
kosten mehr Zeit als ein Takt. Er gilt `KOPFRAUM_TAKT_S` lang weiter, und in
dieser Zeit legt Spot höchstens einen halben Meter zurück — der geprüfte
Korridor reicht zwei Meter voraus.
"""

import math
import time
from dataclasses import dataclass
from pathlib import Path

from spotlab.record.run import STOPP_DATEI
from spotlab.workshop.beispiele import ORDNER

DATEINAME = "folgen.py"

WUNSCH_ABSTAND_M = 1.6           # so nah will Spot heran
MIN_ABSTAND_M = 1.0              # näher NIE
TOLERANZ_M = 0.25                # innerhalb davon fährt er gar nicht
MAX_TEMPO_M_S = 0.5              # zusätzlich zum Deckel aus config.toml
ANNAEHERUNG = 0.6                # m/s je Meter Abstandsfehler
MAX_DREHRATE_GRAD = 45.0
LENKUNG = 1.2                    # Grad/s je Grad Peilung
SCHWENK_GRAD = 40.0              # weiter seitlich: erst drehen, nicht fahren
FREIRAUM_M = 0.8                 # so viel muss voraus frei sein
KOPFRAUM_M = 1.0                 # so weit voraus darf nichts über dem Weg hängen
KOPFRAUM_TAKT_S = 1.0
ZONE_VORAUS_M = 1.0
# Quellen der Gesichtssuche: die zwei Frontkameras fuer das Bild, die zwei
# Tiefenkameras fuer die Entfernung -- in EINEM Abruf, nicht in zweien.
GESICHT_QUELLEN = ("frontright_fisheye_image", "frontleft_fisheye_image")
TIEFE_QUELLEN = ("frontleft_depth", "frontright_depth")
TAKT_S = 0.2
VERLOREN_S = 5.0                 # danach sagt er es einmal


@dataclass(frozen=True)
class Ziel:
    bearing: float               # Grad, links positiv
    distance: float              # Meter
    name: str = "Ziel"


def skript_in(arbeitsordner):
    """Das Folgeprogramm im Projekt Beispiele des Arbeitsordners."""
    return Path(arbeitsordner) / ORDNER / DATEINAME


# ----------------------------------------------------------------- Finder


def tag_finder(tag_id=None):
    """Folgt einem AprilTag — am Rucksack, auf einem Schild, in der Hand.

    Der zuverlässigste Weg und der einzige, der heute nachweislich funktioniert:
    Peilung und Abstand kommen aus demselben Dienst wie bei der Kartenaufnahme,
    in Grad und Metern. Ohne `tag_id` das nächste sichtbare Tag.
    """
    def finde(spot):
        gefunden = spot.tags(id=tag_id) if tag_id is not None else spot.tags()
        if not gefunden:
            return None
        tag = gefunden[0]
        return Ziel(tag.bearing, tag.distance, f"Tag {tag.id}")

    return finde


def personen_finder(mindestsicherheit=None):
    """Folgt einem Menschen, den Spots eigene Firmware verfolgt.

    Kein eigenes Modell — der Tracker steckt im Roboter (`spot.people()`).
    Ob dieser Spot ihn hat, zeigt erst das Gerät; liefert er nichts, findet
    dieser Finder nichts, und `folge()` lässt Spot stehen.
    """
    def finde(spot):
        leute = spot.people()
        if mindestsicherheit is not None:
            leute = [p for p in leute if p.likelihood >= mindestsicherheit]
        if not leute:
            return None
        person = leute[0]
        return Ziel(person.bearing, person.distance, f"Person {person.entity_id}")

    return finde


def gesicht_finder(modell=None, mindestscore=None, quellen=GESICHT_QUELLEN,
                   tiefe_quellen=TIEFE_QUELLEN):
    """Folgt einem Gesicht — mit Gegenprobe aus der Tiefenkamera.

    Die Kameras schauen nach unten: ein stehender Mensch hat erst ab gut
    zweieinhalb Metern ein Gesicht im Bild, näher sieht Spot Beine (gemessen,
    `backends/real/gesicht.py`). Deshalb gehört dieser Finder mit einem zweiten
    zusammengeschaltet — `zuerst(gesicht_finder(), tag_finder())` nimmt das
    Gesicht, solange es eines gibt, und sonst das Tag.

    Ein Kasten mit hoher Punktzahl ist noch kein Gesicht: über dieselbe
    Aufzeichnung fand der Erkenner eine Stuhllehne und ein Schienbein. Was
    nicht auf Kopfhöhe liegt, fällt hier heraus.

    Teuer: vier Bilder je Takt. Der Regler läuft dadurch langsamer, und das ist
    in Ordnung — jedes Kommando trägt eine Endzeit, Spot fährt nicht blind
    weiter, wenn der Takt einmal hängt.
    """
    gemerkt = {}

    def finde(spot):
        import numpy as np

        from spotlab.backends.real import gesicht as gesichtsmodul
        from spotlab.backends.real import panorama, tiefe

        antworten = spot.backend.images(list(quellen) + list(tiefe_quellen))
        nach_name = {a.source.name: a for a in antworten}
        grau = [nach_name[q] for q in quellen if q in nach_name]
        tiefen = [nach_name[q] for q in tiefe_quellen if q in nach_name]
        if len(grau) < 2 or not tiefen:
            return None
        if "pano" not in gemerkt:
            gemerkt["pano"] = panorama.Panorama(
                panorama.kalibrierung_aus(grau), zuschnitt=panorama.ALLES
            )
            gemerkt["erkenner"] = gesichtsmodul.erkenner(
                gemerkt["pano"].breite, gemerkt["pano"].hoehe, modell,
                mindestscore or gesichtsmodul.MINDESTSCORE,
            )
            gemerkt["hoehe"] = gemerkt["pano"].kamerahoehe()
        feld = gemerkt["pano"].zusammensetzen(panorama.bilder_aus(grau))
        punkte = np.vstack([tiefe.punkte_aus_bild(a) for a in tiefen])
        gefunden = gesichtsmodul.gesichter(
            feld, gemerkt["pano"], gemerkt["erkenner"], punkte, gemerkt["hoehe"]
        )
        if not gefunden:
            return None
        kopf = gefunden[0]
        return Ziel(kopf.bearing, kopf.distance, f"Gesicht auf {kopf.height:.2f} m")

    return finde


def zuerst(*finder):
    """Der erste Finder, der etwas findet, gewinnt.

    Damit lassen sich Strategien staffeln statt zu wählen: das Gesicht, solange
    es sichtbar ist, und darunter das Tag — genau die Lücke, die die Geometrie
    der Frontkameras aufmacht.

    Ein Finder, der WIRFT, hält die Staffel nicht auf: fehlt OpenCV oder das
    Gesichtsmodell, soll das Tag weiter funktionieren. Der Grund steht einmal
    im Protokoll — still übergehen wäre schlimmer als gar nicht staffeln.
    """
    gemeldet = set()

    def finde(spot):
        for nummer, einer in enumerate(finder):
            try:
                ziel = einer(spot)
            except Exception as fehler:
                if nummer not in gemeldet:
                    from spotlab import protokoll

                    gemeldet.add(nummer)
                    protokoll.notiere(f"Finder {nummer} faellt aus: {fehler}")
                continue
            if ziel is not None:
                return ziel
        return None

    return finde


# ---------------------------------------------------------------- Schranken


def frei_voraus(spot, meter=FREIRAUM_M):
    """(darf fahren, Grund). Fail-closed: kein Gitter heisst kein Vorwärts."""
    try:
        gitter = spot.obstacles()
        x, y, yaw = spot.state.pose
        frei = gitter.free_distance(x, y, math.degrees(yaw))
    except Exception as fehler:
        return False, f"Hindernisgitter nicht lesbar ({fehler})"
    if frei < meter:
        return False, f"nur {frei:.1f} m frei voraus"
    return True, ""


def kopfraum_frei(spot, meter=KOPFRAUM_M, quellen=("frontleft_depth", "frontright_depth")):
    """(darf fahren, Grund) — hängt etwas über dem Weg? Fail-closed.

    Das Hindernisgitter ist eine BODENkarte; eine Tischplatte in 75 cm Höhe
    steht nicht darin. Genau dort ist der Explorer am 07.09.2026 hineingefahren.
    """
    from spotlab.backends.base import Capability
    from spotlab.backends.real import tiefe

    backend = getattr(spot, "backend", None)
    if backend is None or not (backend.capabilities() & Capability.DEPTH_CAMERAS):
        return True, ""                      # kein Tiefensinn: die Schranke gibt es nicht
    try:
        punkte = tiefe.ueberhang_aus_bildern(backend.images(list(quellen)))
        weite = tiefe.kopfraum(punkte)
    except Exception as fehler:
        return False, f"Tiefenbild nicht lesbar ({fehler})"
    if weite is not None and weite <= meter:
        return False, f"Überhang {weite:.2f} m voraus"
    return True, ""


def zone_voraus(spot, raum, strecke=ZONE_VORAUS_M):
    """(darf fahren, Grund) — liegt eine eingezeichnete Sperrzone davor?

    Nur mit einem Raum, der seine Karte kennt, UND einer Verortung. Fehlt eines
    davon, gibt es die Schranke nicht — und `folge()` sagt das einmal, statt
    Sicherheit vorzutäuschen.
    """
    from spotlab.welt import kollision
    from spotlab.welt import raum as raummodul

    if raum is None or not raum.sperrzonen:
        return True, ""
    lage = spot.map_pose()
    if lage is None:
        return False, "nicht auf der Karte verortet"
    im_raum = raummodul.aus_karte(raum, lage[0], lage[1], lage[2])
    if im_raum is None:
        return False, "der Raum kennt seine Karte nicht"
    name = kollision.zone_voraus(raum, im_raum, strecke)
    if not name:
        return True, ""
    # Der Grund steht dabei: „Sperrzone glasfront voraus" sagt einem Menschen
    # weniger als „…(Glasfront, kein Sensor sieht sie)".
    zone = next((z for z in raum.sperrzonen if z.name == name), None)
    grund = f" ({zone.grund})" if zone is not None and zone.grund else ""
    return False, f"Sperrzone {name}{grund} voraus"


# ------------------------------------------------------------------ Regler


def befehl(ziel, wunsch=WUNSCH_ABSTAND_M, mindest=MIN_ABSTAND_M, toleranz=TOLERANZ_M):
    """(vx, wz) aus Peilung und Abstand — ohne Roboter prüfbar.

    Rückwärts gibt es nicht: nach hinten sieht Spot nichts. Ist der Mensch zu
    nah, bleibt er stehen und dreht sich höchstens mit.
    """
    wz = math.radians(max(-MAX_DREHRATE_GRAD, min(MAX_DREHRATE_GRAD, LENKUNG * ziel.bearing)))
    if abs(ziel.bearing) > SCHWENK_GRAD:
        return 0.0, wz                       # erst die Nase hin, dann gehen
    fehler = ziel.distance - wunsch
    if fehler <= toleranz or ziel.distance <= mindest:
        return 0.0, wz
    return min(MAX_TEMPO_M_S, ANNAEHERUNG * fehler), wz


def folge(spot, finder=None, raum=None, melde=print, jetzt=time.monotonic,
          schlaf=time.sleep, takt_s=TAKT_S, laeuft=None, lauf_dir=None,
          kopfraum_takt_s=KOPFRAUM_TAKT_S):
    """Die Schleife: Ziel suchen, Abstand halten, bei jeder Schranke stehen bleiben.

    Testbar ohne Roboter: `spot` braucht `walk` und `stop`, dazu was der Finder
    und die Schranken abfragen. Am Ende hält Spot immer.
    """
    finder = finder or tag_finder()
    if laeuft is None:
        if lauf_dir is None:
            raise ValueError("folge() braucht `lauf_dir` oder `laeuft`.")
        stopp = Path(lauf_dir) / STOPP_DATEI

        def laeuft():
            return not stopp.exists()

    zuletzt_gesehen = jetzt()
    verloren_gemeldet = False
    letzter_grund = ""
    kopfraum = (True, "")
    kopfraum_geprueft = None
    faehrt = False

    try:
        while laeuft():
            ziel = _sicher(finder, spot)
            if ziel is None:
                if faehrt:
                    spot.stop()
                    faehrt = False
                if not verloren_gemeldet and jetzt() - zuletzt_gesehen >= VERLOREN_S:
                    melde("Ziel verloren — Spot wartet.")
                    verloren_gemeldet = True
                schlaf(takt_s)
                continue

            if verloren_gemeldet:
                melde(f"{ziel.name} wieder da.")
            zuletzt_gesehen, verloren_gemeldet = jetzt(), False
            vx, wz = befehl(ziel)

            if vx > 0.0:
                if kopfraum_geprueft is None or jetzt() - kopfraum_geprueft >= kopfraum_takt_s:
                    kopfraum = kopfraum_frei(spot)
                    kopfraum_geprueft = jetzt()
                for darf, grund in (frei_voraus(spot), kopfraum, zone_voraus(spot, raum)):
                    if not darf:
                        vx = 0.0
                        if grund != letzter_grund:
                            melde(f"Stehen geblieben: {grund}.")
                            letzter_grund = grund
                        break
                else:
                    letzter_grund = ""

            if (vx, wz) == (0.0, 0.0):
                if faehrt:
                    spot.stop()
                    faehrt = False
            else:
                spot.walk(vx=vx, vy=0.0, wz=wz, stop=False)
                faehrt = True
            schlaf(takt_s)
    finally:
        spot.stop()
        melde("Folgen beendet.")


def _sicher(finder, spot):
    """Ein Finder, der wirft, darf den Lauf nicht beenden — er findet dann nichts."""
    try:
        return finder(spot)
    except Exception:
        return None
