"""Die Werkzeuge, mit denen ein Agent den Spot über die Steuerzentrale sieht und fährt.

Agenten am Spot, Teil 1 (`docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`). Der
MCP-Server hat KEINEN eigenen Weg zum Roboter: er startet die Zentrale über den einen Startweg
(`workshop/launcher.start_script`, Paketcode `workshop/zentrale.py`) und spricht mit ihr über
Dateien im Lauf-Verzeichnis (`record/agent.py`), wie der Tab „Fahren“. Jede Fahrt geht durch
die Schranken der Klickfahrt; am echten Spot nur, solange ein Mensch „🤖 Agent darf fahren“
eingeschaltet hat.

**Lebenszeichen:** solange ein Befehl unterwegs ist, frischt ein Hintergrundfaden `lebt` alle
`AGENT_PULS_S` auf. Endet der Agent, schliesst der Klient die Verbindung, dieser Prozess endet,
und nach `AGENT_TOTMANN_S` hält Spot an.

**Aufzeichnung:** jeder Werkzeugaufruf steht als Zeile in `<lauf>/agent.jsonl`, jedes Bild, das
der Agent bekam, unter `<lauf>/agent/`. Eine stolpernde Aufzeichnung hält keinen Befehl auf.

Alle Werkzeuge antworten mit kurzem JSON und werfen nie (`{"fehler": …}`, wie `werkzeuge.py`).
"""

import functools
import inspect
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from spotlab import ENV_RAUM
from spotlab.config import load_config
from spotlab.errors import SpotlabError
from spotlab.mcp import agentlage
from spotlab.mcp.werkzeuge import _fehlertext, arbeitsordner
from spotlab.pfade import sicherer_name
from spotlab.record import agent as agentdatei
from spotlab.record import zentrale as protokoll
from spotlab.record.read import read_run
from spotlab.workshop.control import ist_aktiv, stoppe_freundlich

ORTE = {"2d": "sim", "3d": "mujoco", "physik": "physics", "echt": "real"}
ECHT_BACKEND = "real"           # Tests tauschen es gegen den Trockenlauf (wie FAHREN_BACKEND)
START_WARTE_S = 30.0
ENDE_WARTE_S = 40.0             # der Abbau am echten Spot dauert bis zu 20 s (power_off)
BEFEHL_WARTE_S = 30.0
BESTAETIGUNG_S = 2.0
TIEFE_WARTE_S = 5.0
WARTEN_MAX_S = 10.0
NACHSEHEN_S = 0.05
ENDZUSTAENDE = ("angekommen", "abgelehnt", "versperrt", "abgebrochen", "gemessen", "erledigt")
LAEUFE_ANSEHEN = 30             # so viele jüngste Läufe werden nach einer Zentrale durchsucht
KURZ_ZEICHEN = 2000             # so lang wird eine Antwort in agent.jsonl höchstens
KEINE_ZENTRALE = ("Keine Steuerzentrale läuft — zuerst zentrale_starten(ort) mit ort = "
                  "\"2d\", \"3d\", \"physik\" oder \"echt\".")
AGENT_NAME = os.environ.get("SPOTLAB_AGENT", "agent")
_sperre = threading.Lock()
_zustand = {"puls": None, "lauf": None, "nummer": 0}


@dataclass(frozen=True)
class Bildantwort:
    """Ein Bild für den Agenten samt Text — `server.py` macht daraus ein MCP-Bild."""

    daten: bytes
    format: str              # "png" oder "jpeg"
    text: dict


# ------------------------------------------------------------ Hilfen


def _beispiel_runs(wurzel):
    from spotlab.workshop.beispiele import ORDNER as BEISPIELORDNER

    return Path(wurzel) / BEISPIELORDNER / "runs"


def _ist_laufende_zentrale(lauf):
    try:
        return ist_aktiv(lauf) and agentdatei.ist_zentrale(read_run(lauf, zaehlen=False).skript)
    except OSError:
        return False


def laufende_zentrale(wurzel=None):
    """Das Verzeichnis der laufenden Zentrale — oder None."""
    gemerkt = _zustand["lauf"]
    if gemerkt is not None:
        if _ist_laufende_zentrale(gemerkt):
            return gemerkt
        _zustand["lauf"] = None              # beendet: nicht mehr hineinschreiben
    runs = _beispiel_runs(wurzel or arbeitsordner())
    try:
        kandidaten = sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True)
    except OSError:
        return None
    for lauf in kandidaten[:LAEUFE_ANSEHEN]:
        if _ist_laufende_zentrale(lauf):
            _zustand["lauf"] = lauf
            return lauf
    return None


def _zentrale():
    lauf = laufende_zentrale()
    if lauf is None:
        raise SpotlabError(KEINE_ZENTRALE)
    return lauf


def _lebt(pid):
    """Lebt der Prozess? Im Zweifel ja (`backends/real/lease.lebt`, über `tasklist`)."""
    from spotlab.backends.real.lease import lebt

    return lebt(pid)


def _beanspruche(lauf):
    """Ein Agent zugleich: lebt der eingetragene Prozess noch, ist die Zentrale belegt."""
    besitz = agentdatei.lies_besitz(lauf)
    if besitz is not None and besitz["pid"] != os.getpid() and _lebt(besitz["pid"]):
        seit = datetime.fromtimestamp(besitz["seit"]).strftime("%H:%M:%S")
        raise SpotlabError(f"belegt von {besitz['agent']} seit {seit} — es fährt immer nur ein "
                           f"Agent. Warten, bis er fertig ist, oder ein Mensch beendet die "
                           f"Zentrale.")
    if besitz is None or besitz["pid"] != os.getpid():
        agentdatei.schreibe_besitz(lauf, AGENT_NAME, os.getpid())


def _warte(bedingung, frist_s, schlaf=time.sleep):
    """Den Wert von `bedingung()`, sobald er wahr ist — oder None nach `frist_s`."""
    ende = time.monotonic() + frist_s
    while True:
        wert = bedingung()
        if wert:
            return wert
        if time.monotonic() >= ende:
            return None
        schlaf(NACHSEHEN_S)


def _stand(lauf, nummer):
    """Der Platz `agent` im Lagebild, wenn er schon von Befehl `nummer` spricht."""
    agent = (protokoll.lies_lagebild(lauf) or {}).get("agent") or {}
    return agent if agent.get("nummer") == nummer else None


def _fertig(lauf, nummer):
    stand = _stand(lauf, nummer)
    return stand if stand is not None and stand.get("zustand") in ENDZUSTAENDE else None


def _naechste_nummer(lauf):
    befehl = agentdatei.lies_befehl(lauf)
    agent = (protokoll.lies_lagebild(lauf) or {}).get("agent") or {}
    nummer = max(_zustand["nummer"], befehl.nummer if befehl else 0,
                 int(agent.get("nummer") or 0)) + 1
    _zustand["nummer"] = nummer
    return nummer


class _Puls:
    """Frischt das Lebenszeichen EINES Befehls auf, bis er endet, ein anderer kommt oder
    `halt()` gerufen wird. Ein Agent, der nichts mehr sagt, muss Spot anhalten lassen —
    deshalb hängt das Lebenszeichen an diesem Prozess, nicht an einer Frist."""

    def __init__(self, lauf, nummer, art, werte, warum):
        self.lauf, self.nummer = lauf, nummer
        self._befehl = (art, werte, warum)
        self._halt = threading.Event()
        self._faden = threading.Thread(target=self._lauf, daemon=True, name="agent-puls")
        self._faden.start()

    def halt(self, warte_s=1.0):
        """Anhalten und warten, bis der Faden still ist -- sonst schriebe er seinen Befehl
        womöglich noch einmal über den nächsten."""
        self._halt.set()
        if self._faden is not threading.current_thread():
            self._faden.join(warte_s)

    @property
    def laeuft(self):
        return self._faden.is_alive()

    def _lauf(self):
        art, werte, warum = self._befehl
        while not self._halt.wait(agentdatei.AGENT_PULS_S):
            if _fertig(self.lauf, self.nummer):
                return
            jetzt = agentdatei.lies_befehl(self.lauf)
            if jetzt is not None and jetzt.nummer != self.nummer:
                return                           # ein neuer Befehl hat übernommen
            try:
                agentdatei.schreibe_befehl(self.lauf, self.nummer, art, werte, warum, AGENT_NAME)
            except OSError:
                pass                             # der nächste Takt versucht es wieder


def _neuer_puls(puls):
    with _sperre:
        alt, _zustand["puls"] = _zustand["puls"], puls
    if alt is not None:
        alt.halt()


def _befehl(art, werte, warum, warte_s, beanspruchen=True):
    """Einen Befehl schicken, auf die Bestätigung warten (≤ `BESTAETIGUNG_S`), dann auf das
    Ende (≤ `warte_s`). Läuft er danach noch, fährt er weiter, solange dieser Prozess lebt."""
    lauf = _zentrale()
    if beanspruchen:
        _beanspruche(lauf)
    nummer = _naechste_nummer(lauf)
    _neuer_puls(None)                    # erst den alten Puls still, dann der neue Befehl
    agentdatei.schreibe_befehl(lauf, nummer, art, werte, warum, AGENT_NAME)
    puls = _Puls(lauf, nummer, art, werte, warum)
    _neuer_puls(puls)
    if _warte(lambda: _stand(lauf, nummer), BESTAETIGUNG_S) is None:
        puls.halt()
        raise SpotlabError(f"Zentrale antwortet nicht — Befehl {nummer} wurde in "
                           f"{BESTAETIGUNG_S:.0f} s nicht bestätigt; das Lebenszeichen hört auf, "
                           f"Spot hält. zentrale_status() prüfen.")
    stand = _warte(lambda: _fertig(lauf, nummer), warte_s)
    if stand is None:
        return {"nummer": nummer, "zustand": "läuft noch",
                "hinweis": "Der Befehl fährt weiter, solange dieser MCP-Prozess lebt — "
                           "warten(sekunden) für das Ergebnis, stopp() zum Anhalten."}
    antwort = {"nummer": nummer, "zustand": stand["zustand"], "grund": stand.get("grund", "")}
    if stand.get("tiefe") is not None:
        antwort["tiefe"] = stand["tiefe"]
    return antwort


def _zahl(wert, name):
    """Eine endliche Zahl — sonst ein Fehler, der sagt, welches Argument."""
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        raise SpotlabError(f"{name} muss eine Zahl sein, nicht {wert!r}.") from None
    if not math.isfinite(zahl):
        raise SpotlabError(f"{name} muss endlich sein, nicht {wert!r}.")
    return zahl


def _warum(warum):
    text = str(warum or "").strip()
    if not text:
        raise SpotlabError("warum fehlt — jeder Fahrbefehl braucht eine kurze Begründung; sie "
                           "wird aufgezeichnet.")
    return text


def _kurz(wert):
    if isinstance(wert, Bildantwort):
        wert = dict(wert.text, bild=f"{wert.format}, {len(wert.daten)} Bytes")
    text = json.dumps(wert, ensure_ascii=False, default=str)
    return text if len(text) <= KURZ_ZEICHEN else text[:KURZ_ZEICHEN] + " …"


def _aufzeichnen(name, argumente, antwort, lauf=None):
    """Eine Zeile nach `<lauf>/agent.jsonl` — wirft nie. `lauf`: der Lauf, in dem der Aufruf
    begann (auch `zentrale_beenden` gehört noch in die Aufzeichnung seines Laufs)."""
    try:
        lauf = _zustand["lauf"] or lauf or laufende_zentrale()
        if lauf is None:
            return
        zeile = {"t": time.time(), "werkzeug": name, "agent": AGENT_NAME,
                 "argumente": argumente, "antwort": _kurz(antwort)}
        with (Path(lauf) / "agent.jsonl").open("a", encoding="utf-8") as datei:
            datei.write(json.dumps(zeile, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _werkzeug(funktion):
    """Kein Werfen (`{"fehler": …}`) und jede Antwort in die Aufzeichnung."""
    signatur = inspect.signature(funktion)

    @functools.wraps(funktion)
    def huelle(*args, **kwargs):
        try:
            argumente = dict(signatur.bind(*args, **kwargs).arguments)
        except TypeError:
            argumente = {"args": list(args), **kwargs}
        vorher = _zustand["lauf"]
        try:
            antwort = funktion(*args, **kwargs)
        except Exception as fehler:
            antwort = {"fehler": _fehlertext(fehler)}
        _aufzeichnen(funktion.__name__, argumente, antwort, vorher)
        return antwort

    return huelle


def _bild_ablegen(lauf, name, daten, endung):
    """Was der Agent sah, als er entschied: das Bild unter `<lauf>/agent/`. Wirft nie."""
    try:
        ordner = Path(lauf) / "agent"
        ordner.mkdir(exist_ok=True)
        marke = datetime.now().strftime("%H%M%S_%f")[:-3]
        (ordner / f"{marke}_{name}.{endung}").write_bytes(daten)
    except OSError:
        pass


# ------------------------------------------------------------ Starten und Beenden


def _raum_pruefen(ort, raum, wurzel):
    """Der Name des Übungsraums — geprüft wie im Tab, sonst ein Grund."""
    from spotlab.welt import physik
    from spotlab.welt.raum import raum_laden

    name = raum or load_config().raum
    if not name:
        raise SpotlabError("Kein Übungsraum gewählt — raum=\"…\" angeben (eine Vorlage wie "
                           "\"durchgang\" oder ein eigener Raum aus dem Raumeditor).")
    geladen = raum_laden(name, wurzel)
    if ort == "physik":
        ok, _art, grund = physik.tauglich(geladen)
        if not ok:
            raise SpotlabError(grund)
    return name


def _simulation_da():
    import importlib.util

    return importlib.util.find_spec("spotsim") is not None


@_werkzeug
def zentrale_starten(ort: str, raum: str | None = None):
    """Startet die Steuerzentrale: Übungsraum (2d, 3d, physik) oder echter Spot (echt)."""
    from spotlab.welt.physik import OHNE_SIMULATION
    from spotlab.workshop import zentrale
    from spotlab.workshop.beispiele import bereitstellen
    from spotlab.workshop.launcher import start_script

    ort = str(ort or "").strip().lower()
    if ort not in ORTE:
        raise SpotlabError(f"ort muss eines von {list(ORTE)} sein, nicht {ort!r}.")
    wurzel = arbeitsordner()
    laufend = laufende_zentrale(wurzel)
    if laufend is not None:
        raise SpotlabError(f"Es läuft schon eine Zentrale (Lauf {laufend.name}) — "
                           f"zentrale_status() oder zentrale_beenden().")
    runs = _beispiel_runs(wurzel)
    andere = [p.name for p in (sorted(runs.iterdir(), reverse=True)[:LAEUFE_ANSEHEN]
                               if runs.is_dir() else []) if p.is_dir() and ist_aktiv(p)]
    if andere:
        raise SpotlabError(f"Es läuft schon ein Programm (Lauf {andere[0]}) — erst wenn es "
                           f"endet, startet die Zentrale. Genau ein Lauf hält den Roboter.")
    echt = ort == "echt"
    backend = ECHT_BACKEND if echt else ORTE[ort]
    if ort in ("3d", "physik") and not _simulation_da():
        raise SpotlabError(OHNE_SIMULATION)
    umgebung = {} if echt else {ENV_RAUM: _raum_pruefen(ort, raum, wurzel)}
    bereitstellen(wurzel)
    argumente = ["--runs", str(runs), "--arbeitsordner", str(wurzel)]
    if echt:
        argumente.append("--auf-freigabe-warten")
    protokolle = wurzel / "mcp-ausgabe"
    protokolle.mkdir(parents=True, exist_ok=True)
    marke = datetime.now().strftime("%Y%m%d-%H%M%S")
    ausgabedatei = protokolle / f"{marke}-{sicherer_name('zentrale-' + ort, ersatz='zentrale')}.log"
    vorher = {p.name for p in runs.iterdir()} if runs.is_dir() else set()
    with open(ausgabedatei, "w", encoding="utf-8", errors="replace") as strom:
        prozess = start_script(zentrale.SKRIPT, argumente=argumente, backend=backend,
                               nur_trocken=not echt, ausgabe=strom, umgebung=umgebung)

    def neuer_lauf():
        if prozess.poll() is not None:
            return "tot"
        try:
            return next((p for p in runs.iterdir() if p.is_dir() and p.name not in vorher), None)
        except OSError:
            return None

    def gescheitert(wann):
        try:
            ende = ausgabedatei.read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            ende = ""
        return SpotlabError(f"Die Zentrale ist {wann} beendet. Ausgabe ({ausgabedatei}): {ende}")

    lauf = _warte(neuer_lauf, START_WARTE_S)
    if lauf == "tot":
        raise gescheitert("vor dem Verbinden")
    if lauf is None:
        raise SpotlabError(f"Kein Lauf nach {START_WARTE_S:.0f} s — die Ausgabe steht in "
                           f"{ausgabedatei}. Am echten Spot: Netz und Anmeldung prüfen.")
    if _warte(lambda: protokoll.lies_lagebild(lauf) or prozess.poll() is not None,
              START_WARTE_S) in (None, True):
        raise gescheitert("ohne Lagebild")
    _zustand["lauf"] = lauf
    agentdatei.schreibe_besitz(lauf, AGENT_NAME, os.getpid())
    antwort = {"gestartet": True, "lauf": lauf.name, "ort": ort, "backend": backend,
               "ausgabe": str(ausgabedatei)}
    if echt:
        antwort["hinweis"] = ("Verbunden, Motoren AUS. Spot steht erst auf, wenn ein Mensch im "
                              "Tab „Fahren“ „🤖 Agent darf fahren“ einschaltet — bis dahin "
                              "werden Fahrbefehle abgelehnt, lesen geht.")
    else:
        antwort["hinweis"] = (f"Übungsraum {umgebung[ENV_RAUM]} ohne Roboter. Fahrbefehle "
                              f"brauchen hier keine Freigabe.")
    return antwort


@_werkzeug
def zentrale_status():
    """Läuft eine Zentrale, wo, mit welchen Motoren, mit Freigabe, und wer steuert?"""
    lauf = laufende_zentrale()
    if lauf is None:
        return {"laeuft": False, "hinweis": KEINE_ZENTRALE}
    lauf_info = read_run(lauf, zaehlen=False)
    ort = next((o for o, b in ORTE.items() if b == lauf_info.backend), lauf_info.backend)
    lage = agentlage.lage_aus(lauf)
    besitz = agentdatei.lies_besitz(lauf)
    if besitz is not None:
        besitz = dict(besitz, lebt=besitz["pid"] == os.getpid() or _lebt(besitz["pid"]),
                      bin_ich=besitz["pid"] == os.getpid())
    return {"laeuft": True, "lauf": lauf.name, "ort": ort, "backend": lauf_info.backend,
            "antwortet": "fehler" not in lage, "motoren": lage.get("motoren"),
            "freigabe": lage.get("freigabe"), "steuert": besitz}


@_werkzeug
def zentrale_beenden():
    """Freundlicher Stopp: Spot hält an und setzt sich, die Zentrale baut ab."""
    lauf = _zentrale()
    _beanspruche(lauf)
    _neuer_puls(None)
    stoppe_freundlich(lauf)
    beendet = _warte(lambda: not ist_aktiv(lauf), ENDE_WARTE_S) is not None
    if beendet:
        _zustand["lauf"] = None
    return {"beendet": beendet, "lauf": lauf.name,
            **({} if beendet else {"hinweis": "Der Abbau dauert noch — gleich noch einmal "
                                              "zentrale_status() fragen."})}


# ------------------------------------------------------------ Sehen


@_werkzeug
def lage():
    """Pose, Tempo, Akku, Motoren, Freigabe, freie Strecke in 8 Richtungen, Menschen, Tags."""
    return agentlage.lage_aus(_zentrale())


@_werkzeug
def skizze(radius_m: float = agentlage.SKIZZE_RADIUS_M):
    """Die Draufsicht um Spot als Bild (+y oben, Raster 1 m)."""
    lauf = _zentrale()
    radius = min(max(_zahl(radius_m, "radius_m"), 1.0), 15.0)
    daten, legende = agentlage.skizze_bild(lauf, radius)
    _bild_ablegen(lauf, "skizze", daten, "png")
    return Bildantwort(daten, "png", {"legende": legende, "radius_m": radius})


@_werkzeug
def kamerabild():
    """`ansicht.jpg` des Laufs: echter Spot = Frontkameras, 3D = Zimmer von aussen."""
    lauf = _zentrale()
    backend = read_run(lauf, zaehlen=False).backend
    if backend == "sim":
        return {"bild": None, "hinweis": "Kein Bild in diesem Übungsraum (2D) — skizze() und "
                                         "lage() zeigen, was Spot „sieht“."}
    try:
        daten = (Path(lauf) / "ansicht.jpg").read_bytes()
    except OSError:
        return {"bild": None, "hinweis": "Noch kein Bild — kurz warten und noch einmal fragen."}
    _bild_ablegen(lauf, "kamerabild", daten, "jpg")
    if backend in ("mujoco", "physics"):
        was = ("das gerenderte Übungszimmer VON AUSSEN (keine Kamera des Roboters) — Spot ist "
               "darin zu sehen")
    else:
        was = "Spots Blick nach vorn: beide Frontkameras als ein Bild"
    return Bildantwort(daten, "jpeg", {"was": was, "backend": backend})


@_werkzeug
def tiefe_messen():
    """Abstände vorne aus den Tiefenkameras: links, mitte, rechts (5. Perzentil) und Kopfraum."""
    return _befehl("tiefe", {}, "Tiefe messen", TIEFE_WARTE_S, beanspruchen=True)


# ------------------------------------------------------------ Fahren


@_werkzeug
def fahre_zu(x: float, y: float, warum: str):
    """Fährt über gesehenen Boden zum Punkt (x, y) im Rahmen „vision“ — wie ein Klick."""
    return _befehl("ziel", {"x": _zahl(x, "x"), "y": _zahl(y, "y")}, _warum(warum), BEFEHL_WARTE_S)


@_werkzeug
def fahre_relativ(vor_m: float, links_m: float, warum: str):
    """Fährt zu einem Punkt `vor_m` voraus und `links_m` links von Spot."""
    return _befehl("relativ", {"vor_m": _zahl(vor_m, "vor_m"), "links_m": _zahl(links_m, "links_m")}, _warum(warum),
                   BEFEHL_WARTE_S)


@_werkzeug
def drehe(grad: float, warum: str):
    """Dreht auf der Stelle um `grad` (positiv = links), fertig auf 3° genau."""
    return _befehl("drehen", {"grad": _zahl(grad, "grad")}, _warum(warum), BEFEHL_WARTE_S)


@_werkzeug
def stoss(vx: float, vy: float, wz: float, dauer_s: float, warum: str):
    """Ein kurzer Fahrstoss (höchstens 2 s): vx vor, vy links in m/s, wz in rad/s (+ links)."""
    werte = {"vx": _zahl(vx, "vx"), "vy": _zahl(vy, "vy"), "wz": _zahl(wz, "wz"), "dauer_s": _zahl(dauer_s, "dauer_s")}
    return _befehl("stoss", werte, _warum(warum), BEFEHL_WARTE_S)


@_werkzeug
def folge_mensch(x: float, y: float, warum: str):
    """Folgt dem Menschen bei (x, y) — wie ein Klick auf ihn im Tab."""
    return _befehl("folgen", {"x": _zahl(x, "x"), "y": _zahl(y, "y")}, _warum(warum), BEFEHL_WARTE_S)


@_werkzeug
def stopp():
    """Hält sofort an — jeder Agent darf das, auch ohne Besitz."""
    return _befehl("stopp", {}, "stopp", BESTAETIGUNG_S, beanspruchen=False)


@_werkzeug
def warten(sekunden: float = 5.0):
    """Wartet auf das Ende des laufenden Befehls (höchstens `sekunden` ≤ 10), dann die Lage."""
    lauf = _zentrale()
    frist = min(max(_zahl(sekunden, "sekunden"), 0.0), WARTEN_MAX_S)
    agent = (protokoll.lies_lagebild(lauf) or {}).get("agent") or {}
    nummer = agent.get("nummer")
    stand = _warte(lambda: _fertig(lauf, nummer), frist) if nummer else None
    return {"befehl": stand or ((protokoll.lies_lagebild(lauf) or {}).get("agent")),
            "lage": agentlage.lage_aus(lauf)}


# ------------------------------------------------------------ Nebenbei


@_werkzeug
def licht(farbe: str):
    """LEDs am Kopf: aus, blau, gruen, gelb, rot (nur am echten Spot)."""
    return _befehl("licht", {"farbe": farbe}, "Licht", BESTAETIGUNG_S + 1.0)


@_werkzeug
def piep():
    """Ein kurzer Ton (nur am echten Spot)."""
    return _befehl("piep", {}, "Piep", BESTAETIGUNG_S + 1.0)


@_werkzeug
def suche(stufe: str):
    """Menschensuche: aus, sparsam, normal, rundum (braucht Bild- und Tiefenkameras)."""
    return _befehl("suche", {"stufe": stufe}, "Menschensuche", BESTAETIGUNG_S + 1.0)
