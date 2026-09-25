"""Folge-Aufnahme: was Spot beim Folgen sah, was er daraus machte, und wie lange es dauerte.

    folgen.folge(spot, finder, lauf_dir=spot.recorder.dir, aufnahme=True)

DER ANLASS. Der Folgelauf vom 25.09.2026 (11:37 UTC) hatte 191 Takte mit Ziel,
einen Takt-Median von 0.57 s, Spitzen bis 1.2 s und Lücken bis 100 s ohne Körper
und ohne Gesicht. Das Ereignis `ziel` sagt je Takt, WAS der Finder lieferte und
was befohlen wurde — aber nicht, was im Bild war, was die Gegenprobe verwarf und
wohin die 0.57 s gingen. Ohne das ist jede Verbesserung geraten.

WAS HIER LIEGT, neben der Aufzeichnung unter `<lauf>/folgen/`:

    takte.jsonl      je Takt EINE Zeile: Zeiten je Schritt (in ihrer Reihenfolge —
                     zweimal `kameras` heisst zwei Bildabrufe), die Sichten des
                     Takts, JEDER Körper und JEDES Gesicht mit Urteil, das Ziel
                     (roh und nachgeführt), der Befehl samt bremsender Schranke,
                     eine Geste und der Zustand (folgt, nachlauf, sucht,
                     angehalten).
    sichten/         je Sicht das Panorama als JPEG und die Tiefenpunkte als NPZ
                     (float16: auf 5 m rund 4 mm genau, ein Viertel der Grösse).
    kameras.json     einmal die Kalibrierung: das Video und ein Nachspielen der
                     Erkenner bauen daraus DASSELBE Panorama (`panorama_laden`),
                     nicht einen Nachbau.

EINE BEIGABE, KEINE BREMSE. Bilder und Tiefe schreibt ein eigener Faden über eine
begrenzte Warteschlange: ist sie voll, fällt das BILD weg und die Zeile sagt es —
der Takt wartet nie auf die Platte. Ein Schreibfehler wird gezählt
(`fehler`, `letzter_fehler`) und nie geworfen; `folge()` sagt ihn einmal. Die
Zeile selbst geht sofort auf die Platte, wie jedes Ereignis des Laufs.

WER SCHREIBT. `folge()` aktiviert die Aufnahme für die Dauer der Schleife
(`aktiviert()`); Finder und Bildaufnahme fragen `aktiv()` und bekommen ohne
Aufnahme ein Nichts, das jede Mitschrift schluckt. So bleiben die Signaturen der
Finder, wie sie sind, und eine Staffel aus `zuerst()` schreibt ohne Umbau mit.
Ausgewertet wird mit `python -m spotlab.workshop.folgenfilm <lauf>`.
"""

import contextlib
import contextvars
import json
import math
import queue
import threading
import time
from pathlib import Path

ORDNER = "folgen"
INDEX = "takte.jsonl"
KAMERAS = "kameras.json"
SICHTEN = "sichten"
WARTESCHLANGE = 16          # Sichten, die auf den Schreiber warten dürfen (~8 s bei 2 Hz)
GUETE = 85
SCHLIESSEN_FRIST_S = 10.0

_AKTIV = contextvars.ContextVar("folgeaufnahme", default=None)


def aktiv():
    """Die laufende Aufnahme — oder ein Nichts, das jede Mitschrift schluckt."""
    return _AKTIV.get() or _KEINE


class _Keine:
    """Keine Aufnahme: jede Methode tut nichts und kostet nichts."""

    def __bool__(self):
        return False

    def zeit(self, name):
        return contextlib.nullcontext()

    def zeit_eintragen(self, name, dauer_s):
        pass

    def sicht(self, aufnahme, finder):
        return None

    def koerper(self, sicht, koerper_liste, befunde, weg=None, landmarken=None):
        pass

    def gesichter(self, sicht, befunde):
        pass

    def ziel(self, ziel, ziel_jetzt=None, echt=True):
        pass

    def befehl(self, vx, wz, nick_grad, schranke="", gesperrt=False, angehalten=False):
        pass

    def geste(self, geste):
        pass

    def takt_beginnt(self):
        pass

    def takt_endet(self, zustand):
        pass


_KEINE = _Keine()


def _runde(wert, stellen=3):
    if wert is None:
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return round(zahl, stellen) if math.isfinite(zahl) else None


def _punkt(p):
    return None if p is None else [_runde(p[0], 1), _runde(p[1], 1)]


def jpeg_schreiben(pfad, feld, guete=GUETE):
    """Das Panorama als JPEG — RGB bleibt RGB, Grau bleibt Grau."""
    import numpy as np

    feld = np.asarray(feld)
    try:
        import cv2
    except ImportError:
        cv2 = None
    if cv2 is not None:
        bild = cv2.cvtColor(feld, cv2.COLOR_RGB2BGR) if feld.ndim == 3 else feld
        ok, daten = cv2.imencode(".jpg", bild, [cv2.IMWRITE_JPEG_QUALITY, int(guete)])
        if not ok:
            raise OSError("JPEG liess sich nicht kodieren")
        Path(pfad).write_bytes(daten.tobytes())
        return
    from PIL import Image

    Image.fromarray(feld).save(pfad, format="JPEG", quality=int(guete))


def tiefe_schreiben(pfad, punkte):
    import numpy as np

    np.savez_compressed(pfad, punkte=np.asarray(punkte, dtype=np.float16))


def _kameras_als_daten(kameras):
    return [{"name": k.name, "breite": int(k.breite), "hoehe": int(k.hoehe),
             "fx": float(k.fx), "fy": float(k.fy), "cx": float(k.cx), "cy": float(k.cy),
             "lage": [[float(v) for v in zeile] for zeile in k.lage]} for k in kameras]


def kameras_laden(lauf_dir):
    """Die Kalibrierung des Laufs als `panorama.Kamera` — oder None, wenn keine da ist."""
    import numpy as np

    from spotlab.backends.real import panorama

    datei = Path(lauf_dir) / ORDNER / KAMERAS
    if not datei.is_file():
        return None
    daten = json.loads(datei.read_text(encoding="utf-8"))
    return [panorama.Kamera(k["name"], k["breite"], k["hoehe"], k["fx"], k["fy"], k["cx"], k["cy"],
                            np.asarray(k["lage"], dtype=np.float64)) for k in daten["kameras"]]


def panorama_laden(lauf_dir):
    """DASSELBE Panorama wie im Lauf (Zuschnitt `ALLES`, wie `folgen.bildaufnahme`) — oder None."""
    from spotlab.backends.real import panorama

    kameras = kameras_laden(lauf_dir)
    if kameras is None:
        return None
    daten = json.loads((Path(lauf_dir) / ORDNER / KAMERAS).read_text(encoding="utf-8"))
    return panorama.Panorama(kameras, zuschnitt=daten.get("zuschnitt", panorama.ALLES))


class Folgeaufnahme:
    """Die Mitschrift eines Folgelaufs. `takt_beginnt` … `takt_endet` klammern einen Takt.

    `uhr` liefert die Laufzeit in Sekunden — im Lauf `recorder.zeitmarke`, damit
    `t` dieselbe Basis hat wie `ereignisse.jsonl`. `bild_schreiber(pfad, feld)`
    und `tiefe_schreiber(pfad, punkte)` sind die Testtüren.
    """

    def __init__(self, lauf_dir, uhr=None, bild_schreiber=None, tiefe_schreiber=None,
                 warteschlange=WARTESCHLANGE):
        self.dir = Path(lauf_dir) / ORDNER
        (self.dir / SICHTEN).mkdir(parents=True, exist_ok=True)
        if uhr is None:
            start = time.monotonic()

            def uhr():
                return time.monotonic() - start

        self._uhr = uhr
        self._bild_schreiber = bild_schreiber or jpeg_schreiben
        self._tiefe_schreiber = tiefe_schreiber or tiefe_schreiben
        self._auftraege = queue.Queue(maxsize=max(1, int(warteschlange)))
        self._sperre = threading.Lock()
        self._kameras_da = False
        self._takt = None
        self._t_beginn = None
        self.takte = 0
        self.sichten = 0
        self.verworfen = 0
        self.fehler = 0
        self.letzter_fehler = ""
        self._faden = threading.Thread(target=self._schreibe, name="folgeaufnahme", daemon=True)
        self._faden.start()

    def __bool__(self):
        return True

    # ------------------------------------------------------------ Rahmen

    @contextlib.contextmanager
    def aktiviert(self):
        marke = _AKTIV.set(self)
        try:
            yield self
        finally:
            _AKTIV.reset(marke)

    def takt_beginnt(self):
        self.takte += 1
        self._t_beginn = self._jetzt()
        self._takt = {"takt": self.takte, "t": _runde(self._t_beginn), "arbeit_s": None,
                      "zeiten": [], "sichten": [], "koerper": [], "gesichter": [],
                      "ziel": None, "befehl": None, "geste": None, "zustand": None}

    def takt_endet(self, zustand):
        takt = self._takt
        if takt is None:
            return
        self._takt = None
        takt["zustand"] = zustand
        takt["arbeit_s"] = _runde(self._jetzt() - self._t_beginn)
        try:
            with (self.dir / INDEX).open("a", encoding="utf-8") as ziel:
                ziel.write(json.dumps(takt, ensure_ascii=False) + "\n")
        except Exception as fehler:
            self._fehler(fehler)

    # ------------------------------------------------------------ Zeiten

    @contextlib.contextmanager
    def zeit(self, name):
        beginn = self._jetzt()
        try:
            yield
        finally:
            self.zeit_eintragen(name, self._jetzt() - beginn)

    def zeit_eintragen(self, name, dauer_s):
        if self._takt is not None:
            self._takt["zeiten"].append([str(name), _runde(dauer_s, 4)])

    # ------------------------------------------------------------ Inhalt

    def sicht(self, aufnahme, finder):
        """Eine Bildaufnahme des Takts — das Bild geht an den Schreiber. Gibt ihre Nummer."""
        if self._takt is None:
            return None
        nr = len(self._takt["sichten"])
        stamm = f"{self._takt['takt']:05d}_{nr}"
        feld = getattr(aufnahme, "feld", None)
        punkte = getattr(aufnahme, "punkte", None)
        form = getattr(feld, "shape", (None, None))
        eintrag = {"nr": nr, "t": _runde(self._jetzt()), "finder": str(finder),
                   "nick_grad": _runde(getattr(aufnahme, "blick_grad", None), 2),
                   "gier": _runde(getattr(aufnahme, "gier", None), 4),
                   "breite": form[1], "hoehe": form[0],
                   "bild": None, "tiefe": None, "grund": None}
        self._takt["sichten"].append(eintrag)
        self._kameras_merken(getattr(aufnahme, "pano", None))
        if feld is not None:
            bild = f"{SICHTEN}/{stamm}.jpg"
            if self._auftrag(("bild", self.dir / bild, feld)):
                eintrag["bild"] = bild
                self.sichten += 1
            else:
                eintrag["grund"] = "Schreiber kam nicht nach — Bild verworfen"
                self.verworfen += 1
        if punkte is not None and eintrag["bild"] is not None:
            tiefe = f"{SICHTEN}/{stamm}.npz"
            if self._auftrag(("tiefe", self.dir / tiefe, punkte)):
                eintrag["tiefe"] = tiefe
        return nr

    def koerper(self, sicht, koerper_liste, befunde, weg=None, landmarken=None):
        if self._takt is None:
            return
        landmarken = list(landmarken or [])
        for i, (k, b) in enumerate(zip(koerper_liste, befunde)):
            lm = landmarken[i] if i < len(landmarken) else None
            self._takt["koerper"].append({
                "sicht": sicht, "weg": weg, "conf": _runde(k.conf),
                "huefte": _punkt(k.huefte), "schulter": _punkt(k.schulter),
                "kasten": [_runde(v, 1) for v in k.kasten],
                "landmarken": None if lm is None else [[_runde(v, 1) for v in p[:2]] + [_runde(p[2], 2)]
                                                       for p in lm],
                "punkt": b.punkt, "peilung": _runde(b.bearing, 2),
                "hoehenwinkel": _runde(b.elevation, 2), "abstand": _runde(b.distance),
                "hoehe": _runde(b.height), "bild_oben": _runde(b.bild_oben, 2),
                "genommen": bool(b.genommen), "grund": b.grund,
            })

    def gesichter(self, sicht, befunde):
        if self._takt is None:
            return
        for b in befunde:
            self._takt["gesichter"].append({
                "sicht": sicht, "kasten": [_runde(v, 1) for v in b.box], "score": _runde(b.score),
                "peilung": _runde(b.bearing, 2), "hoehenwinkel": _runde(b.elevation, 2),
                "abstand": _runde(b.distance), "hoehe": _runde(b.height),
                "genommen": bool(b.genommen), "grund": b.grund,
            })

    def ziel(self, ziel, ziel_jetzt=None, echt=True):
        if self._takt is None or ziel is None:
            return
        jetzt_ = ziel_jetzt if ziel_jetzt is not None else ziel
        self._takt["ziel"] = {"name": str(ziel.name), "peilung": _runde(ziel.bearing, 2),
                              "peilung_jetzt": _runde(jetzt_.bearing, 2),
                              "abstand": _runde(ziel.distance), "bild_oben": _runde(ziel.bild_oben, 2),
                              "echt": bool(echt)}

    def befehl(self, vx, wz, nick_grad, schranke="", gesperrt=False, angehalten=False):
        if self._takt is None:
            return
        self._takt["befehl"] = {"vx": _runde(vx), "wz_grad": _runde(math.degrees(float(wz)), 2),
                                "nick_grad": _runde(nick_grad, 2), "schranke": str(schranke or ""),
                                "gesperrt": bool(gesperrt), "angehalten": bool(angehalten)}

    def geste(self, geste):
        if self._takt is not None and geste is not None:
            self._takt["geste"] = str(geste)

    # ------------------------------------------------------------ Schreiber

    def schliessen(self, frist_s=SCHLIESSEN_FRIST_S):
        """Wartet höchstens `frist_s` auf den Schreiber. Gibt die Zähler zurück."""
        if self._takt is not None:
            self.takt_endet(self._takt.get("zustand") or "abbruch")
        with contextlib.suppress(queue.Full):
            self._auftraege.put(None, timeout=frist_s)
        self._faden.join(frist_s)
        return {"takte": self.takte, "sichten": self.sichten, "verworfen": self.verworfen,
                "fehler": self.fehler, "letzter_fehler": self.letzter_fehler,
                "ordner": str(self.dir)}

    def _auftrag(self, auftrag):
        try:
            self._auftraege.put_nowait(auftrag)
            return True
        except queue.Full:
            return False

    def _schreibe(self):
        while True:
            auftrag = self._auftraege.get()
            if auftrag is None:
                return
            art, pfad, inhalt = auftrag
            try:
                if art == "bild":
                    self._bild_schreiber(pfad, inhalt)
                elif art == "tiefe":
                    self._tiefe_schreiber(pfad, inhalt)
                elif art == "json":
                    Path(pfad).write_text(json.dumps(inhalt, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
            except Exception as fehler:
                self._fehler(fehler)

    def _kameras_merken(self, pano):
        """Die Kalibrierung EINMAL — die Finder haben je ein Panorama, aber dieselben Kameras."""
        kameras = getattr(pano, "kameras", None)
        if self._kameras_da or not kameras:
            return
        from spotlab.backends.real import panorama

        try:
            daten = {"zuschnitt": panorama.ALLES, "kameras": _kameras_als_daten(kameras)}
        except Exception as fehler:
            self._fehler(fehler)
            return
        self._kameras_da = self._auftrag(("json", self.dir / KAMERAS, daten))

    def _fehler(self, fehler):
        with self._sperre:
            self.fehler += 1
            self.letzter_fehler = f"{type(fehler).__name__}: {fehler}"

    def _jetzt(self):
        return float(self._uhr())
