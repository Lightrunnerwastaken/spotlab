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
VERLOREN_S = 5.0                 # so lange ohne Ziel, dann sagt er es
# ...und dann immer wieder. Einmal am Anfang genügt nicht: nach einer halben
# Minute ist die Zeile weggescrollt, und ein stehender Spot ist von einem
# hängenden Programm nicht zu unterscheiden (gesehen am 16.09.2026).
STILLE_TAKT_S = 15.0
# Wie weit Spot die Nase hebt, damit die Kameras hoeher schauen. 0 = gar nicht.
# Gemessen (`backends/real/gesicht.py`): ohne Neigung kommt ein stehendes Gesicht
# erst ab 2.31 m ins Bild, mit 10 Grad ab 1.46 m, mit 15 Grad ab 1.18 m. Der
# Preis steht daneben: der Boden vor den Fuessen verschwindet, bei 15 Grad ist er
# erst ab 0.66 m statt 0.32 m im Bild.
BLICK_GRAD = 0.0
MAX_BLICK_GRAD = 20.0


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
    zuletzt = {"text": ""}

    def finde(spot):
        gefunden = spot.tags(id=tag_id) if tag_id is not None else spot.tags()
        zuletzt["text"] = (f"{len(gefunden)} Tags sichtbar" if gefunden
                           else "kein Tag sichtbar")
        if not gefunden:
            return None
        tag = gefunden[0]
        return Ziel(tag.bearing, tag.distance, f"Tag {tag.id}")

    finde.befund = lambda: zuletzt["text"]
    return finde


def personen_finder(mindestsicherheit=None):
    """Folgt einem Menschen, den Spots eigene Firmware verfolgt.

    Kein eigenes Modell — der Tracker steckt im Roboter (`spot.people()`).
    Ob dieser Spot ihn hat, zeigt erst das Gerät; liefert er nichts, findet
    dieser Finder nichts, und `folge()` lässt Spot stehen.
    """
    zuletzt = {"text": ""}

    def finde(spot):
        leute = spot.people()
        if mindestsicherheit is not None:
            leute = [p for p in leute if p.likelihood >= mindestsicherheit]
        zuletzt["text"] = (f"{len(leute)} Personen gemeldet" if leute
                           else "keine Person gemeldet")
        if not leute:
            return None
        person = leute[0]
        return Ziel(person.bearing, person.distance, f"Person {person.entity_id}")

    finde.befund = lambda: zuletzt["text"]

    # Der Hinweis hängt am Finder, nicht in `folge()`: nur der Finder weiss, warum
    # er leer ausgeht. `folge()` sagt ihn einmal, wenn wirklich nichts kommt --
    # sonst stünde er auch dort, wo der Tracker tut, was er soll.
    finde.hinweis = (
        "Hinweis zu personen_finder(): er fragt Spots eigenen Personen-Tracker. "
        "Am Schul-Spot lieferte der in 560 Abfragen null Treffer — diese "
        "Robotersoftware führt keine Personen (docs/ABNAHME.md, A34 Teil 1, "
        "gemessen am 11.09.2026). Nimm tag_finder() oder gesicht_finder(), oder "
        "staffle beide mit zuerst()."
    )
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
    zuletzt = {"text": ""}

    def finde(spot):
        from spotlab.backends.real import gesicht as gesichtsmodul

        aufnahme = gesichtsaufnahme(spot, gemerkt, quellen, tiefe_quellen,
                                    modell, mindestscore)
        if aufnahme is None:
            zuletzt["text"] = "keine Bilder (Kamera oder Tiefe fehlt)"
            return None
        # `beurteile` statt `gesichter`: dasselbe Ergebnis, aber mit dem Urteil je
        # Kasten. Ohne das ist „kein Gesicht" nicht von „alle verworfen" zu
        # unterscheiden -- genau die Frage, die am 16.09.2026 offen blieb.
        befunde = gesichtsmodul.beurteile(
            aufnahme.feld, aufnahme.pano, aufnahme.erkenner, aufnahme.punkte,
            aufnahme.pano.kamerahoehe(aufnahme.blick_grad),
            blick_grad=aufnahme.blick_grad,
        )
        zuletzt["text"] = _gesichtsbefund(befunde)
        genommen = sorted((b for b in befunde if b.genommen),
                          key=lambda b: b.distance)
        if not genommen:
            return None
        kopf = genommen[0]
        return Ziel(kopf.bearing, kopf.distance, f"Gesicht auf {kopf.height:.2f} m")

    finde.befund = lambda: zuletzt["text"]
    return finde


def _gesichtsbefund(befunde):
    """Was der Erkenner in diesem Takt sah — und was die Gegenprobe damit tat.

    Die drei Fälle führen zu verschiedenen Schritten: kein Kasten heisst zu
    dunkel, zu weit oder das Gesicht liegt ausserhalb der Deckung; alle
    verworfen heisst, die Geometrie stimmt nicht (`zu tief` ist der häufigste
    Fall, und dann hockt oder liegt der Mensch); genommen heisst, es lag am
    Regler oder an einer Schranke.
    """
    import collections

    if not befunde:
        return "kein Kasten vom Erkenner"
    genommen = sum(1 for b in befunde if b.genommen)
    if genommen:
        return f"{len(befunde)} Kästen, {genommen} genommen"
    gruende = collections.Counter(b.grund for b in befunde if b.grund)
    liste = ", ".join(f"{anzahl}× {grund}" for grund, anzahl in sorted(gruende.items()))
    return f"{len(befunde)} Kästen, alle verworfen ({liste})"


@dataclass(frozen=True)
class Gesichtsaufnahme:
    """Alles, was eine Gesichtsprüfung in EINEM Takt braucht."""

    feld: object              # das zusammengesetzte Panorama (Graustufen)
    pano: object              # die virtuelle Kamera dazu — rechnet Spalte/Zeile in Winkel
    erkenner: object          # YuNet, einmal gebaut
    punkte: object            # Nx3 Tiefenpunkte im aufgerichteten Körperrahmen
    blick_grad: float         # der GEMESSENE Nick, nach oben positiv


def gesichtsaufnahme(spot, gemerkt, quellen=GESICHT_QUELLEN,
                     tiefe_quellen=TIEFE_QUELLEN, modell=None, mindestscore=None):
    """Vier Bilder holen und daraus Panorama, Erkenner und Punktwolke — oder None.

    Die gemeinsame Vorbereitung von `gesicht_finder` und der Messprobe
    (`workshop/gesichtsprobe.py`). EINE Formulierung: sonst misst die Probe
    etwas anderes, als der Folgemodus tut, und das fiele erst am Gerät auf.

    `gemerkt` ist ein Wörterbuch, das der Aufrufer hält — Panorama und Erkenner
    werden einmal gebaut und dann wiederverwendet; YuNet je Takt neu zu bauen
    kostete mehr als der Abruf.
    """
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
    feld = gemerkt["pano"].zusammensetzen(panorama.bilder_aus(grau))
    punkte = np.vstack([tiefe.punkte_aus_bild(a) for a in tiefen])
    # Der GEMESSENE Nick, nicht der befohlene: so stimmt die Rechnung auch,
    # wenn Spot an einer Rampe steht oder unsere Neigung nicht ganz umsetzt.
    # `state.pitch` ist im Bogenmass, Nase hoch NEGATIV (Projektkonvention).
    return Gesichtsaufnahme(feld, gemerkt["pano"], gemerkt["erkenner"], punkte,
                            -math.degrees(_nick(spot)))


def _nick(spot):
    """Der gemessene Nickwinkel des Körpers in RAD — 0.0, wenn nicht lesbar."""
    try:
        return float(spot.state.pitch)
    except Exception:
        return 0.0


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

    # Hinweise UND Befunde der Mitglieder wandern mit: sonst verschwände
    # ausgerechnet beim Staffeln die Auskunft, warum ein Finder nichts liefert --
    # und dort ist die Frage erst recht offen, welcher der beiden schwieg.
    finde.hinweis = "\n".join(
        h for h in (getattr(einer, "hinweis", "") for einer in finder) if h
    )
    finde.befund = lambda: " · ".join(b for b in (_befund(e) for e in finder) if b)
    return finde


def _befund(finder):
    """Was der Finder zuletzt gesehen hat — leer, wenn er nichts dazu sagt.

    Eine Auskunft über den Zustand darf den Zustand nie verändern und erst recht
    keinen fahrenden Roboter anhalten: ein Finder, der beim Erzählen stolpert,
    bleibt stumm statt zu werfen.
    """
    holen = getattr(finder, "befund", None)
    if holen is None:
        return ""
    try:
        return str(holen() or "")
    except Exception:
        return ""


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
          kopfraum_takt_s=KOPFRAUM_TAKT_S, blick_grad=BLICK_GRAD):
    """Die Schleife: Ziel suchen, Abstand halten, bei jeder Schranke stehen bleiben.

    `blick_grad` hebt die Nase während der Fahrt, damit die Kameras höher
    schauen — positiv, in Grad. Damit kommt ein stehendes Gesicht schon auf
    Folgeabstand ins Bild statt erst ab zweieinhalb Metern. Der Preis: der Boden
    dicht vor den Füssen fällt aus dem Blickfeld, und das ist genau der Bereich,
    in dem die Hindernisschranke prüft. Deshalb ist die Vorgabe 0.

    Auch im STEHEN bleibt die Neigung: sonst legt Spot die Nase ab, sobald er im
    Wunschabstand ist, verliert das Gesicht und pendelt zwischen Suchen und
    Fahren. Ein Kommando mit Tempo null hält die Lage; es verfällt wie jedes
    andere nach rund einer Sekunde.

    WENN NICHTS KOMMT, sagt er es — wiederholt, unterschieden und aufgeschrieben.
    Ein stehender Spot sieht aus wie ein hängendes Programm, deshalb meldet die
    Schleife die Stille alle `STILLE_TAKT_S`, trennt „noch kein Ziel" von „Ziel
    verloren", gibt den `hinweis` des Finders einmal aus und schreibt das
    Ereignis `kein_ziel` in die Aufzeichnung.

    Testbar ohne Roboter: `spot` braucht `walk` und `stop`, dazu was der Finder
    und die Schranken abfragen. Am Ende hält Spot immer.
    """
    blick_grad = max(0.0, min(MAX_BLICK_GRAD, float(blick_grad)))
    if blick_grad and not getattr(getattr(spot, "backend", None), "neigt_beim_gehen", False):
        melde("Dieses Backend neigt sich beim Gehen nicht — der Blickwinkel bleibt flach.")
        blick_grad = 0.0
    nick = -blick_grad          # Projektkonvention: Nase hoch ist negativ
    finder = finder or tag_finder()
    if laeuft is None:
        if lauf_dir is None:
            raise ValueError("folge() braucht `lauf_dir` oder `laeuft`.")
        stopp = Path(lauf_dir) / STOPP_DATEI

        def laeuft():
            return not stopp.exists()

    zuletzt_gesehen = jetzt()
    je_gesehen = False              # hatte er ueberhaupt je ein Ziel?
    stille_gemeldet = None          # wann zuletzt ueber die Stille berichtet wurde
    hinweis_gesagt = False
    schreibfehler_gemeldet = False
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
                nun = jetzt()
                seit = nun - zuletzt_gesehen
                faellig = stille_gemeldet is None or nun - stille_gemeldet >= STILLE_TAKT_S
                if seit >= VERLOREN_S and faellig:
                    stille_gemeldet = nun
                    befund = _befund(finder)
                    melde(_stille(je_gesehen, seit) + (f"  ({befund})" if befund else ""))
                    if not hinweis_gesagt:
                        hinweis_gesagt = True
                        hinweis = getattr(finder, "hinweis", "")
                        if hinweis:
                            melde(hinweis)
                    fehlschlag = _notiere_stille(spot, seit, je_gesehen, befund)
                    if fehlschlag and not schreibfehler_gemeldet:
                        schreibfehler_gemeldet = True
                        melde(f"Die Stille liess sich nicht aufzeichnen: {fehlschlag}")
                schlaf(takt_s)
                continue

            if stille_gemeldet is not None:
                # „wieder da" nur, wenn er wirklich schon einmal da war.
                melde(f"{ziel.name} {'wieder da' if je_gesehen else 'gefunden'}.")
            zuletzt_gesehen, stille_gemeldet = jetzt(), None
            je_gesehen = True
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

            if (vx, wz) == (0.0, 0.0) and not blick_grad:
                if faehrt:
                    spot.stop()
                    faehrt = False
            else:
                # Mit Neigung auch bei Tempo null: das haelt die Nase oben.
                spot.walk(vx=vx, vy=0.0, wz=wz, stop=False, nick_grad=nick)
                faehrt = True
            schlaf(takt_s)
    finally:
        spot.stop()
        melde("Folgen beendet.")


def _stille(je_gesehen, seit_s):
    """Was Spot sagt, während er wartet — und der Unterschied ist die Sache selbst.

    Am 16.09.2026 stand er 28 Sekunden lang, weil `personen_finder()` auf diesem
    Roboter nie etwas liefert. „Ziel verloren" wäre dabei eine falsche Auskunft
    gewesen: verloren hat er nichts, er hatte nie eines. Genau diese beiden Fälle
    verlangen verschiedene Schritte — einmal näher herangehen, einmal den Finder
    wechseln.
    """
    if je_gesehen:
        return f"Ziel verloren, seit {seit_s:.0f} s — Spot wartet."
    return f"Noch kein Ziel nach {seit_s:.0f} s — Spot wartet."


def _notiere_stille(spot, seit_s, je_gesehen, befund=""):
    """Die Stille in die Aufzeichnung — EINE Zeile statt 135 gleicher Abfragen.

    Am 16.09.2026 liess sich nur deshalb klären, was los war, weil
    `ereignisse.jsonl` 135 erfolglose `world_objects` enthielt — die musste man
    erst zählen.

    Gibt den FEHLERTEXT zurück, wenn das Schreiben scheitert, statt ihn zu
    verschlucken. Genau das war hier schon einmal falsch: die Art `kein_ziel`
    fehlte in der Erlaubnisliste (`record/events.py`), `event()` warf, ein
    `except Exception: pass` schluckte es — und in keinem einzigen Lauf stand
    eine Zeile, während die Tests grün blieben, weil ihre Attrappe jede Art
    annahm. Anhalten darf ein Schreiber den Roboter trotzdem nie: ohne Eintrag
    fährt man weiter, ohne Regler nicht. Also melden statt werfen, und der
    Aufrufer sagt es einmal.
    """
    recorder = getattr(spot, "recorder", None)
    if recorder is None:
        return ""
    try:
        recorder.event("kein_ziel", seit_s=round(float(seit_s), 1),
                       je_gesehen=bool(je_gesehen), befund=str(befund))
    except Exception as fehler:
        return f"{type(fehler).__name__}: {fehler}"
    return ""


def _sicher(finder, spot):
    """Ein Finder, der wirft, darf den Lauf nicht beenden — er findet dann nichts."""
    try:
        return finder(spot)
    except Exception:
        return None
