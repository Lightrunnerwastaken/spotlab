"""Der Blick des Roboters: `ansicht.jpg` aus den beiden Frontkameras — wie auf dem Tablet.

Wer den Spot mit W A S D Q E fährt, will sehen, wohin. Im Übungsraum rendert
das MuJoCo-Backend dafür das Zimmer von aussen (`backends/mujoco.py`,
Ansichtsthread); am ECHTEN Roboter gibt es kein Zimmer -- dort ist der Blick
das, was die Frontkameras sehen: zu EINEM Rechteck zusammengesetzt
(`backends/real/panorama.py`), in Farbe, wo die Kamera Farbe kann, und so
schnell, wie der Roboter Bilder liefert.

Beides landet unter demselben Namen im Lauf-Verzeichnis: `ansicht.jpg` ist
**die Ansicht dieses Laufs**, geschrieben von dem, der sie hat. Zwei Schreiber
gleichzeitig gibt es nie: `starte()` legt einen Blick nur an, wenn das Backend
es ERLAUBT (`blick_aus_kameras`, gesetzt am echten Roboter) -- eine
Erlaubnisliste, keine Sperrliste, denn ein Sim, der Kameras vortäuscht und die
Ansicht selbst rendert, hätte sonst zwei Schreiber auf einer Datei. Für die GUI
ändert sich nichts: sie liest wie bisher eine Datei von der Platte.

BILDRATE. Ein Bildabruf über WLAN dauert länger als ein Fahrtakt und ist
reine Wartezeit; Zusammensetzen und Schreiben dauern rund 15 ms und sind
Rechenzeit. Deshalb zwei Threads: einer holt in Schleife und legt die neueste
Antwort ab, der andere setzt zusammen und schreibt -- und kommt er nicht nach,
fällt das ältere Bild weg, nie das neueste. Die Obergrenze ist `TAKT_S`; die
wirkliche Rate bestimmen Kamera und WLAN. Dasselbe Bild (gleiche
Aufnahmezeit) wird nie zweimal geschrieben.

RÜCKFALL. Ohne Intrinsik oder Rahmenbaum gibt es kein Panorama; dann kommen
die Bilder aufrecht gedreht nebeneinander (−102° und −78°, die Winkel des
SDK-Beispiels `image_viewer.py`, `frontright` LINKS neben `frontleft` -- die
Kameras schauen über Kreuz). Ein Fehler beendet den Blick, nie den Lauf: ohne
Bild fährt man weiter (der Mensch steht daneben), ohne Fahrbefehle nicht.

NICHT über `spot.camera()`: jenes schreibt über den `RunRecorder` mit, und
`bilder.json` wird dabei bei jedem Bild vollständig neu geschrieben -- bei
zwanzig Bildern je Sekunde wäre das quadratisch. Der Blick ist ein Strom,
keine Aufnahme; er ersetzt eine Datei und legt kein Ereignis an.
"""

import io
import threading
import time
from pathlib import Path

from spotlab.errors import SpotlabError

DATEI = "ansicht.jpg"
TAKT_S = 1.0 / 30           # Obergrenze der Abrufe: schneller fragt niemand
GUETE_ANFRAGE = 60          # JPEG vom Roboter, übers WLAN: klein
GUETE = 80                  # JPEG auf der Platte: das Bild, das man sieht
FEHLER_BIS_AUFGABE = 3      # Fehler NACHEINANDER; ein Erfolg setzt zurück

# Anzeigereihenfolge: rechts LINKS im Bild -- die Kameras schauen über Kreuz.
KAMERAS = ("frontright_fisheye_image", "frontleft_fisheye_image")
# Drehung für den Rückfall ohne Kalibrierung (Grad, gegen den Uhrzeigersinn).
DREHUNG = {"frontright_fisheye_image": -102.0, "frontleft_fisheye_image": -78.0}


def jpeg_bytes(feld, guete=GUETE):
    """Ein uint8-Feld (HxW oder HxWx3) als JPEG-Bytes."""
    from PIL import Image as PILImage

    puffer = io.BytesIO()
    PILImage.fromarray(feld).save(puffer, format="JPEG", quality=guete)
    return puffer.getvalue()


def bild_aus(antworten, drehungen=None, guete=GUETE):
    """Rückfall: die Kamerabilder aufrecht gedreht und nebeneinander, als JPEG-Bytes."""
    from PIL import Image as PILImage

    from spotlab.api.perception import Image

    winkel = DREHUNG if drehungen is None else dict(drehungen)
    teile = []
    for antwort in antworten:
        bild = Image(antwort)
        feld = PILImage.fromarray(bild.array)
        teile.append(feld.rotate(winkel.get(bild.source, 0.0), expand=True))
    if not teile:
        raise ValueError("Kein Bild -- ohne Kamera gibt es keinen Blick.")
    modus = "RGB" if any(t.mode == "RGB" for t in teile) else "L"
    hoehe = max(t.height for t in teile)
    zusammen = PILImage.new(modus, (sum(t.width for t in teile), hoehe))
    x = 0
    for teil in teile:
        zusammen.paste(teil.convert(modus), (x, 0))
        x += teil.width
    puffer = io.BytesIO()
    zusammen.save(puffer, format="JPEG", quality=guete)
    return puffer.getvalue()


class Blick(threading.Thread):
    """Holt Bilder in Schleife, setzt sie zusammen und ersetzt `ansicht.jpg`.

    Zwei Threads (siehe oben): dieser setzt zusammen und schreibt, ein innerer
    holt. Zähler: `abrufe` (Antworten vom Roboter), `bilder` (geschriebene
    Dateien), `fehler` (Fehler nacheinander), `letzter_fehler`.
    """

    def __init__(self, spot, lauf_dir, takt_s=TAKT_S, kameras=KAMERAS,
                 schlaf=time.sleep, jetzt=time.monotonic):
        super().__init__(name="spotlab-blick", daemon=True)
        self._spot = spot
        self._ziel = Path(lauf_dir) / DATEI
        self._takt_s = takt_s
        self._quellen = list(kameras)
        self._schlaf, self._jetzt = schlaf, jetzt
        self._halt = threading.Event()
        self._neu = threading.Condition()
        self._antworten = None
        self._panorama = None
        self._rueckfall = False
        self._letzte_aufnahme = None
        self.abrufe = 0
        self.bilder = 0
        self.fehler = 0
        self.letzter_fehler = ""
        self.aufgegeben = False

    # -------------------------------------------------------------- Schritte

    def holen(self):
        """Die Antworten des Roboters für die beiden Frontkameras."""
        return self._spot.backend.images(self._quellen, farbe=True, guete=GUETE_ANFRAGE)

    def schreiben(self, antworten):
        """`ansicht.jpg` aus den Antworten ersetzen. False, wenn es dasselbe Bild war."""
        from spotlab.backends.real import panorama
        from spotlab.record import atomar

        aufnahme = tuple(panorama.aufnahmezeit(a) for a in antworten)
        if aufnahme == self._letzte_aufnahme:
            return False
        atomar.schreibe_atomar(self._ziel, self._bild_bytes(antworten))
        self._letzte_aufnahme = aufnahme
        self.bilder += 1
        return True

    def _bild_bytes(self, antworten):
        from spotlab.backends.real import panorama

        if not self._rueckfall:
            try:
                if self._panorama is None:
                    self._panorama = panorama.Panorama(panorama.kalibrierung_aus(antworten))
                return jpeg_bytes(self._panorama.zusammensetzen(panorama.bilder_aus(antworten)))
            except SpotlabError as fehler:
                from spotlab import protokoll

                self._rueckfall = True
                protokoll.notiere(f"Blick ohne Panorama (gedreht nebeneinander): {fehler}")
        return bild_aus(antworten)

    def einmal(self):
        """Ein Bild holen und schreiben, in diesem Thread. True, wenn es geklappt hat."""
        try:
            antworten = self.holen()
            self.abrufe += 1
            self.schreiben(antworten)
        except Exception as fehler:
            self._fehler(fehler)
            return False
        self.fehler = 0
        return True

    def _fehler(self, fehler):
        self.fehler += 1
        self.letzter_fehler = f"{type(fehler).__name__}: {fehler}"
        if self.fehler >= FEHLER_BIS_AUFGABE and not self.aufgegeben:
            from spotlab import protokoll

            self.aufgegeben = True
            protokoll.notiere(f"Blick aufgegeben: {self.letzter_fehler}")
            self._halt.set()
            with self._neu:
                self._neu.notify_all()

    # ---------------------------------------------------------------- Threads

    def beenden(self, frist_s=2.0):
        self._halt.set()
        with self._neu:
            self._neu.notify_all()
        if self.is_alive():
            self.join(timeout=frist_s)

    def _holschleife(self):
        while not self._halt.is_set():
            beginn = self._jetzt()
            try:
                antworten = self.holen()
            except Exception as fehler:
                self._fehler(fehler)
                self._schlaf(self._takt_s)
                continue
            self.abrufe += 1
            self.fehler = 0
            with self._neu:
                self._antworten = antworten          # das Neueste ersetzt das Alte
                self._neu.notify_all()
            rest = self._takt_s - (self._jetzt() - beginn)
            if rest > 0:
                self._schlaf(rest)

    def _naechste(self, frist_s=0.5):
        with self._neu:
            if self._antworten is None:
                self._neu.wait(frist_s)
            antworten, self._antworten = self._antworten, None
            return antworten

    def run(self):
        holer = threading.Thread(target=self._holschleife, name="spotlab-blick-abruf", daemon=True)
        holer.start()
        try:
            while not self._halt.is_set():
                antworten = self._naechste()
                if antworten is None:
                    continue
                try:
                    self.schreiben(antworten)
                except Exception as fehler:
                    self._fehler(fehler)
        finally:
            self._halt.set()
            # Der Holer hängt schlimmstenfalls in einem Abruf (Frist im Backend);
            # als Daemon stirbt er mit dem Prozess, hier nur kurz warten.
            holer.join(timeout=0.5)


def starte(spot, lauf_dir, takt_s=TAKT_S):
    """Einen `Blick` starten -- oder None, wenn dieser Lauf keinen bekommt.

    Keinen bekommt er, wenn das Backend es nicht ausdrücklich erlaubt
    (`blick_aus_kameras`; MuJoCo rendert das Zimmer von aussen selbst, 2D-Sim
    und Trockenlauf haben keine Kameras) oder die Frontkameras fehlen.
    """
    from spotlab.backends.base import Capability

    backend = getattr(spot, "backend", None)
    if backend is None or not getattr(backend, "blick_aus_kameras", False):
        return None
    try:
        if not (backend.capabilities() & Capability.GRAY_CAMERAS):
            return None
        vorhanden = set(backend.image_sources())
    except Exception:
        return None
    if not all(q in vorhanden for q in KAMERAS):
        return None
    blick = Blick(spot, lauf_dir, takt_s=takt_s)
    blick.start()
    return blick
