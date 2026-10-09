"""Die Werkzeuge, mit denen ein Agent Karten und Merkorte nutzt.

Agenten am Spot, Teil 2 (`docs/superpowers/specs/2026-10-09-agent-karten-design.md`). Wie in
`fahren.py` gibt es KEINEN eigenen Weg zum Roboter: Kartenaufträge, Wegpunkt- und Merkortfahrten
sind Befehle an die Zentrale (`agent_befehl.json`), und die Zentrale gibt sie an DIESELBE
Kartenarbeit und dieselbe Navigation wie der Tab „Fahren“. Am echten Spot fahren
`zum_wegpunkt` und `zum_merkort` nur mit Freigabe.

**Karten gibt es nur am echten Spot** (GraphNav). Im Übungsraum merkt sich der Agent Orte mit
Namen (Merkorte) und fährt mit der Wegsuche hin — die Karten-Werkzeuge sagen das, bevor sie einen
Befehl schicken.

**Wegpunkte sind die BENANNTEN Wegpunkte der Karte.** GraphNav legt beim Aufnehmen alle paar Meter
selbst einen an; die heissen nicht und sind keine Ziele.

Nur `raum_aus_karte` rechnet hier selbst: es liest eine gespeicherte Karte von der Platte und
schreibt einen Raum für den Übungsraum — ohne Zentrale und ohne Roboter.
"""

from dataclasses import replace

from spotlab import OHNE_ROBOTER
from spotlab.errors import SpotlabError
from spotlab.mcp import fahren
from spotlab.mcp.fahren import _befehl, _warum, _werkzeug, _zahl, _zentrale
from spotlab.pfade import sicherer_name
from spotlab.record.read import read_run

KARTE_WARTE_S = 30.0            # Hochladen und Verorten (gemessen an den Katakomben: 4 s)
SPEICHERN_WARTE_S = 120.0       # Beenden, Nachbearbeiten und Herunterladen einer Aufnahme
MERKORT_WARTE_S = 3.0
NUR_ECHT = ("Karten gibt es nur am echten Spot (GraphNav) — im Übungsraum merkort_setzen und "
            "zum_merkort.")
SUCHT_TAG = ("Die Karte ist geladen, Spot weiss aber noch nicht, wo er darin steht — einen "
             "AprilTag der Karte ins Bild drehen (drehe). Spot versucht es von selbst wieder; "
             "lage() zeigt karte.zustand.")


def _nur_echt():
    """Der Lauf der Zentrale — wenn sie am echten Spot läuft, sonst der Hinweis auf Merkorte."""
    lauf = _zentrale()
    if read_run(lauf, zaehlen=False).backend in OHNE_ROBOTER:
        raise SpotlabError(NUR_ECHT)
    return lauf


def _name(name, frage):
    text = str(name or "").strip()
    if not text:
        raise SpotlabError(f"name fehlt — {frage}")
    return text


# ------------------------------------------------------------ Karten (echter Spot)


@_werkzeug
def karte_laden(name: str):
    """Lädt eine gespeicherte Karte auf den Roboter und verortet Spot darin (≤ 30 s)."""
    _nur_echt()
    antwort = _befehl("karte_laden", {"name": _name(name, "welche Karte? (karten_auflisten)")},
                      "Karte laden", KARTE_WARTE_S)
    if (antwort.get("karte") or {}).get("zustand") == "sucht_tag":
        antwort["hinweis"] = SUCHT_TAG
    return antwort


@_werkzeug
def aufnahme_starten(name: str | None = None):
    """Beginnt eine Aufnahme — verortet in einer geladenen Karte führt sie diese weiter."""
    _nur_echt()
    werte = {"name": str(name).strip()} if name and str(name).strip() else {}
    return _befehl("aufnahme_start", werte, "Aufnahme starten", KARTE_WARTE_S)


@_werkzeug
def aufnahme_beenden():
    """Beendet die Aufnahme und wartet aufs Speichern (≤ 120 s); nennt den freien Namen."""
    _nur_echt()
    return _befehl("aufnahme_stopp", {}, "Aufnahme beenden", SPEICHERN_WARTE_S)


@_werkzeug
def wegpunkt_setzen(name: str):
    """Setzt während einer Aufnahme einen benannten Wegpunkt an Spots Ort."""
    _nur_echt()
    return _befehl("wegpunkt_setzen", {"name": _name(name, "wie soll der Wegpunkt heissen?")},
                   "Wegpunkt setzen", KARTE_WARTE_S)


@_werkzeug
def zum_wegpunkt(name: str, warum: str):
    """Fährt mit der Karte (GraphNav) zum benannten Wegpunkt — wie ein Klick darauf im Tab."""
    _nur_echt()
    return _befehl("zum_wegpunkt", {"name": _name(name, "welcher Wegpunkt? (lage() nennt die nächsten)")},
                   _warum(warum), fahren.BEFEHL_WARTE_S)


# ------------------------------------------------------------ Merkorte (überall)


@_werkzeug
def merkort_setzen(name: str, x: float | None = None, y: float | None = None):
    """Merkt sich einen Ort mit Namen: (x, y) im Rahmen „vision“, ohne x/y Spots jetziger Ort."""
    werte = {"name": _name(name, "wie soll der Merkort heissen?")}
    if x is not None or y is not None:
        werte.update(x=_zahl(x, "x"), y=_zahl(y, "y"))
    return _befehl("merkort_setzen", werte, "Merkort setzen", MERKORT_WARTE_S)


@_werkzeug
def merkort_loeschen(name: str):
    """Vergisst einen Merkort."""
    return _befehl("merkort_loeschen", {"name": _name(name, "welcher Merkort? (lage() nennt sie)")}, "Merkort löschen",
                   MERKORT_WARTE_S)


@_werkzeug
def zum_merkort(name: str, warum: str):
    """Fährt mit der Wegsuche über den ganzen gesehenen Boden zum Merkort — ohne 5-m-Grenze."""
    return _befehl("zum_merkort", {"name": _name(name, "welcher Merkort? (lage() nennt sie)")}, _warum(warum),
                   fahren.BEFEHL_WARTE_S)


# ------------------------------------------------------------ Rekonstruktion (ohne Zentrale)


def _kartenordner(ws, karte):
    from spotlab.maps import store

    return store.finde(ws, karte)


def _freier_raumname(ws, wunsch):
    """`wunsch` (bereinigt), sonst mit „-2“, „-3“ … — nie ein eigener Raum, nie eine Vorlage."""
    from spotlab.welt.raum import raum_pfad, vorlagen

    basis = sicherer_name(wunsch, ersatz="raum")
    belegt = set(vorlagen())

    def frei(name):
        return name not in belegt and not raum_pfad(ws, name).exists()

    if frei(basis):
        return basis
    k = 2
    while not frei(f"{basis}-{k}"):
        k += 1
    return f"{basis}-{k}"


@_werkzeug
def raum_aus_karte(karte: str, name: str | None = None):
    """Baut aus einer gespeicherten Karte einen Raum für den Übungsraum (ohne Korrigierer)."""
    from spotlab.maps.rekonstruktion import rekonstruiere
    from spotlab.welt import pauspapier
    from spotlab.welt.raum import raum_pfad, raum_speichern

    ws = fahren.arbeitsordner()
    ordner = _kartenordner(ws, _name(karte, "welche Karte? (karten_auflisten)"))
    ergebnis = rekonstruiere(ordner)
    raumname = _freier_raumname(ws, str(name).strip() if name and str(name).strip()
                                else ordner.name)
    pfad = raum_pfad(ws, raumname)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    raum_speichern(replace(ergebnis.raum, name=raumname), pfad)
    pauspapier.schreibe(pauspapier.pfad_zu(pfad), ergebnis.pauspapier, weg=ergebnis.weg)
    b = ergebnis.bericht
    return {"name": raumname, "pfad": str(pfad), "karte": ordner.name,
            "waende": b.get("waende"), "treppen": b.get("treppen"), "rampen": b.get("rampen"),
            "tags": b.get("tags"), "dauer_s": b.get("dauer_s"),
            "hinweise": list(b.get("hinweise") or ()),
            "hinweis": f"Im Raumeditor korrigieren (Lücken schliessen, Gelände bauen), dann "
                       f"zentrale_starten(\"3d\", raum=\"{raumname}\")."}
