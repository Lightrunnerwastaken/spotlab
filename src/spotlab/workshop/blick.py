"""Der Blick des Roboters: `ansicht.jpg` aus den beiden Frontkameras.

Wer den Spot mit W A S D Q E fährt, will sehen, wohin. Im Übungsraum rendert
das MuJoCo-Backend dafür das Zimmer von aussen (`backends/mujoco.py`,
Ansichtsthread); am ECHTEN Roboter gibt es kein Zimmer -- dort ist der Blick
das, was die Frontkameras sehen.

Beides landet unter demselben Namen im Lauf-Verzeichnis: `ansicht.jpg` ist
**die Ansicht dieses Laufs**, geschrieben von dem, der sie hat. Zwei Schreiber
gleichzeitig gibt es nie, denn ein Lauf hat genau ein Backend; `Blick` fragt
das Backend deshalb, ob es selbst rendert (`schreibt_ansicht`). Für die GUI
ändert sich damit nichts: sie liest wie bisher eine Datei von der Platte.

DREHUNG. Die Frontkameras sind schräg eingebaut; ihre Bilder kommen seitwärts
aus dem Roboter. Die Winkel stehen so im SDK-Beispiel `image_viewer.py` von
Boston Dynamics und sind an einer Aufzeichnung vom 12.08.2026 nachgeprüft:
gedreht steht der Boden unten, und `frontright` LINKS neben `frontleft` ergibt
eine durchgehende Szene (die Kameras schauen über Kreuz).

NICHT über `spot.camera()`: jenes schreibt über den `RunRecorder` mit, und
`bilder.json` wird dabei bei jedem Bild vollständig neu geschrieben -- bei
zwei Bildern je Sekunde wäre das quadratisch. Der Blick ist ein Strom, keine
Aufnahme; er ersetzt eine Datei und legt kein Ereignis an.
"""

import io
import threading
import time
from pathlib import Path

DATEI = "ansicht.jpg"
TAKT_S = 0.5
GUETE = 80

# (Quelle, Drehung in Grad) -- in dieser Reihenfolge nebeneinander.
KAMERAS = (("frontright_fisheye_image", -102.0), ("frontleft_fisheye_image", -78.0))


def bild_aus(antworten, drehungen=None, guete=GUETE):
    """Die Kamerabilder aufrecht und nebeneinander als JPEG-Bytes.

    `antworten` sind `ImageResponse`-Nachrichten in Anzeigereihenfolge; ohne
    `drehungen` kommt der Winkel aus `KAMERAS` (Quellenname).
    """
    from PIL import Image as PILImage

    from spotlab.api.perception import Image

    winkel = dict(KAMERAS) if drehungen is None else dict(drehungen)
    teile = []
    for antwort in antworten:
        bild = Image(antwort)
        feld = PILImage.fromarray(bild.array)
        teile.append(feld.rotate(winkel.get(bild.source, 0.0), expand=True))
    if not teile:
        raise ValueError("Kein Bild -- ohne Kamera gibt es keinen Blick.")
    hoehe = max(t.height for t in teile)
    zusammen = PILImage.new("L", (sum(t.width for t in teile), hoehe))
    x = 0
    for teil in teile:
        zusammen.paste(teil.convert("L"), (x, 0))
        x += teil.width
    puffer = io.BytesIO()
    zusammen.save(puffer, format="JPEG", quality=guete)
    return puffer.getvalue()


class Blick(threading.Thread):
    """Schreibt in festem Takt `ansicht.jpg` -- und hält den Lauf nie auf.

    Eigener Thread: ein Bildabruf über WLAN dauert länger als ein Fahrtakt,
    und die Fahrt darf davon nicht langsamer werden. Ein Fehler beendet den
    Blick, nie den Lauf: ohne Bild fährt man weiter (der Mensch steht daneben),
    ohne Fahrbefehle nicht.
    """

    def __init__(self, spot, lauf_dir, takt_s=TAKT_S, kameras=KAMERAS,
                 schlaf=time.sleep, jetzt=time.monotonic):
        super().__init__(name="spotlab-blick", daemon=True)
        self._spot = spot
        self._ziel = Path(lauf_dir) / DATEI
        self._takt_s = takt_s
        self._quellen = [q for q, _ in kameras]
        self._schlaf, self._jetzt = schlaf, jetzt
        self._halt = threading.Event()
        self.bilder = 0
        self.fehler = 0
        self.letzter_fehler = ""

    def beenden(self, frist_s=2.0):
        self._halt.set()
        if self.is_alive():
            self.join(timeout=frist_s)

    def einmal(self):
        """Ein Bild holen und schreiben. True, wenn es geklappt hat."""
        from spotlab.record import atomar

        try:
            antworten = self._spot.backend.images(self._quellen)
            atomar.schreibe_atomar(self._ziel, bild_aus(antworten))
        except Exception as fehler:
            self.fehler += 1
            self.letzter_fehler = f"{type(fehler).__name__}: {fehler}"
            return False
        self.bilder += 1
        return True

    def run(self):
        while not self._halt.is_set():
            beginn = self._jetzt()
            if not self.einmal() and self.fehler >= 3:
                from spotlab import protokoll

                protokoll.notiere(f"Blick aufgegeben: {self.letzter_fehler}")
                return
            rest = self._takt_s - (self._jetzt() - beginn)
            if rest > 0:
                self._schlaf(rest)


def starte(spot, lauf_dir, takt_s=TAKT_S):
    """Einen `Blick` starten -- oder None, wenn dieser Lauf keinen braucht.

    Keinen braucht er, wenn das Backend die Ansicht selbst rendert (MuJoCo
    zeichnet das Zimmer von aussen, das ist zum Fahren besser als ein
    Fischauge) oder wenn es keine Graustufenkameras hat (2D-Sim, Trockenlauf).
    """
    from spotlab.backends.base import Capability

    backend = getattr(spot, "backend", None)
    if backend is None or getattr(backend, "schreibt_ansicht", False):
        return None
    try:
        if not (backend.capabilities() & Capability.GRAY_CAMERAS):
            return None
        vorhanden = set(backend.image_sources())
    except Exception:
        return None
    if not all(q in vorhanden for q, _ in KAMERAS):
        return None
    blick = Blick(spot, lauf_dir, takt_s=takt_s)
    blick.start()
    return blick
