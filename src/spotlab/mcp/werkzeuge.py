"""Die Werkzeuge als gewoehnliche Funktionen.

Jede nimmt und liefert nur JSON-faehige Werte. Fehler kommen als
{"fehler": "..."} zurueck statt als Ausnahme: ein Absturz mitten im Protokoll
nimmt dem Agenten die Moeglichkeit, den Fehler zu lesen und zu beheben.

Der Server schreibt NIE in das fremde Projekt. Er liest dessen Manifest und
schreibt ausschliesslich unterhalb von anbindungen/.
"""

import functools
from pathlib import Path

from spotlab.anbindung import panel as panelmodul
from spotlab.anbindung import speicher
from spotlab.anbindung.manifest import skript_von
from spotlab.config import load_config
from spotlab.errors import SpotlabError
from spotlab.laufsuche import finde_lauf, lauf_verzeichnisse
from spotlab.maps import store as kartenspeicher
from spotlab.record.read import read_jsonl, read_run
from spotlab.workshop.control import ist_aktiv, stoppe_freundlich
from spotlab.workshop.doctor import diagnose
from spotlab.workshop.launcher import start_script

SOLLTAKT_S = 0.1                    # StateSampler laeuft mit 10 Hz
LUECKE_AB_S = 2 * SOLLTAKT_S


def arbeitsordner():
    cfg = load_config()
    if not cfg.workspace:
        raise SpotlabError(
            "Es ist kein Arbeitsordner eingerichtet. Wähle ihn im Fenster unter "
            "„Projekte“ oder richte spotlab mit `spotlab login` ein."
        )
    return Path(cfg.workspace)


def _antwortet(funktion):
    """Wandelt SpotlabError in {"fehler": ...} statt in einen Protokollabbruch."""

    @functools.wraps(funktion)
    def huelle(*args, **kwargs):
        try:
            return funktion(*args, **kwargs)
        except SpotlabError as fehler:
            return {"fehler": str(fehler)}
        except OSError as fehler:
            return {"fehler": f"Dateizugriff fehlgeschlagen: {fehler}"}

    return huelle


def _als_liste(funktion):
    """Wie _antwortet, aber fuer Werkzeuge, die eine Liste liefern."""

    @functools.wraps(funktion)
    def huelle(*args, **kwargs):
        try:
            return funktion(*args, **kwargs)
        except SpotlabError as fehler:
            return [{"fehler": str(fehler)}]
        except OSError as fehler:
            return [{"fehler": f"Dateizugriff fehlgeschlagen: {fehler}"}]

    return huelle


def _skript_json(skript):
    return {
        "name": skript.name,
        "datei": str(skript.datei),
        "argumente": list(skript.argumente),
        "roboter": skript.roboter,
        "beschreibung": skript.beschreibung,
    }


def _anbindung_json(anbindung):
    return {
        "name": anbindung.name,
        "beschreibung": anbindung.manifest.beschreibung,
        "quelle": str(anbindung.quelle),
        "vorhanden": anbindung.vorhanden,
        "angebunden": anbindung.angebunden,
        "skripte": [_skript_json(s) for s in anbindung.manifest.skripte],
        "panels": [p.name for p in panelmodul.panels(anbindung)],
    }


# ----------------------------------------------------------------- Anbinden


@_antwortet
def projekt_anbinden(pfad):
    """Liest die spotlab.toml des Projekts und bindet es an."""
    return _anbindung_json(speicher.binde_an(arbeitsordner(), Path(pfad)))


@_als_liste
def anbindungen_auflisten():
    """Alle angebundenen Projekte mit Skripten und Panelnamen."""
    return [_anbindung_json(a) for a in speicher.anbindungen(arbeitsordner())]


@_antwortet
def panel_setzen(projekt, name, art, titel, inhalt):
    """Schreibt oder ersetzt ein Panel. Arten: kennzahlen, tabelle, reihe, bild, text."""
    anbindung = speicher.finde(arbeitsordner(), projekt)
    return {"ok": True, "pfad": str(panelmodul.schreibe(anbindung, name, art, titel, inhalt))}


@_antwortet
def panel_entfernen(projekt, name):
    """Entfernt ein Panel eines angebundenen Projekts."""
    anbindung = speicher.finde(arbeitsordner(), projekt)
    return {"ok": panelmodul.entferne(anbindung, name)}


# ----------------------------------------------------------------- Ausführen


@_antwortet
def skript_starten(projekt, name):
    """Startet ein registriertes Skript — erzwungen ohne Roboter."""
    anbindung = speicher.finde(arbeitsordner(), projekt)
    skript = skript_von(anbindung.manifest, name)
    if skript is None:
        bekannt = ", ".join(s.name for s in anbindung.manifest.skripte) or "keine"
        raise SpotlabError(
            f"„{name}“ ist in {projekt} nicht registriert. Bekannt sind: {bekannt}."
        )
    if skript.roboter:
        # Erste Lage der Schranke: gar nicht erst starten, mit guter Meldung.
        # Die Durchsetzung haengt nicht daran — siehe ENV_NUR_TROCKEN unten.
        raise SpotlabError(
            f"„{name}“ fährt den echten Spot. Starte es selbst im Fenster unter "
            "„Anbindungen“ — ein Agent darf den Roboter nicht in Bewegung setzen."
        )

    start_script(skript.datei, argumente=skript.argumente, nur_trocken=True)
    return {
        "gestartet": True,
        "skript": str(skript.datei),
        "argumente": list(skript.argumente),
        "hinweis": (
            "Der Lauf läuft im Trockenlauf. Die Kennung erscheint in "
            "`laeufe_auflisten`, sobald die Aufzeichnung angelegt ist."
        ),
    }


@_antwortet
def lauf_stoppen(lauf_id):
    """Freundlicher Stopp über die stopp-Markierung."""
    verzeichnis = _verzeichnis_von(lauf_id)
    if not ist_aktiv(verzeichnis):
        return {"ok": False, "grund": "Dieser Lauf läuft nicht mehr."}
    stoppe_freundlich(verzeichnis)
    return {"ok": True}


# ----------------------------------------------------------------- Lesen


def _lauf_json(zusammenfassung):
    return {
        "id": zusammenfassung.id,
        "gestartet": zusammenfassung.gestartet,
        "dauer_s": zusammenfassung.dauer_s,
        "backend": zusammenfassung.backend,
        "ergebnis": zusammenfassung.ergebnis,
        "fehler": zusammenfassung.fehler,
        "skript": zusammenfassung.skript,
        "ereignisse_n": zusammenfassung.ereignisse_n,
        "abtastungen_n": zusammenfassung.abtastungen_n,
    }


@_als_liste
def laeufe_auflisten(projekt=None, anzahl=20):
    """Die neuesten Läufe. Mit `projekt` nur die eines angebundenen Projekts."""
    wurzel = arbeitsordner()
    verzeichnisse = lauf_verzeichnisse(wurzel)
    if projekt:
        anbindung = speicher.finde(wurzel, projekt)
        erlaubt = {str(p) for p in speicher.lauf_verzeichnisse_von(anbindung)}
        verzeichnisse = [v for v in verzeichnisse if str(v.parent) in erlaubt]
    neueste = sorted(verzeichnisse, key=lambda p: p.name, reverse=True)[: max(1, int(anzahl))]
    return [_lauf_json(read_run(v)) for v in neueste]


@_antwortet
def lauf_lesen(lauf_id):
    """Metadaten und PFADE — bewusst keine Messdaten.

    zustand.jsonl laeuft mit 10 Hz: fuenf Minuten sind 3000 Zeilen. Wer die
    Reihe braucht, liest sie mit den eigenen Dateiwerkzeugen und kann dabei
    filtern.
    """
    verzeichnis = _verzeichnis_von(lauf_id)
    daten = _lauf_json(read_run(verzeichnis))
    daten["laeuft"] = ist_aktiv(verzeichnis)
    daten["pfade"] = {
        "verzeichnis": str(verzeichnis),
        "zustand": str(verzeichnis / "zustand.jsonl"),
        "ereignisse": str(verzeichnis / "ereignisse.jsonl"),
        "bilder": str(verzeichnis / "bilder"),
    }
    return daten


@_antwortet
def zustand_zusammenfassen(lauf_id):
    """Was man sonst nur durch Laden der ganzen Datei erführe.

    Die Abtastluecken sind der eigentliche Zweck: fuer die Real->Sim-Eichung
    macht eine unbemerkte Luecke den Vergleich still ungueltig, und das muss
    vor der ersten Zahl sichtbar sein, nicht nach der letzten.
    """
    verzeichnis = _verzeichnis_von(lauf_id)
    saetze = [s for s in read_jsonl(verzeichnis / "zustand.jsonl") if isinstance(s, dict)]
    if not saetze:
        return {"lauf": lauf_id, "abtastungen": 0, "luecken": []}

    # sample() schreibt {"t": ..., "daten": {...}} — die Nutzdaten liegen
    # geschachtelt, der Zeitstempel oben.
    zeiten = [float(s.get("t") or 0.0) for s in saetze]
    inhalte = [s.get("daten") or {} for s in saetze]

    strecke, tempo_max, dreh_max = 0.0, 0.0, 0.0
    vorige = None
    for daten in inhalte:
        pose = daten.get("pose") or [0.0, 0.0, 0.0]
        if vorige is not None:
            strecke += ((pose[0] - vorige[0]) ** 2 + (pose[1] - vorige[1]) ** 2) ** 0.5
        vorige = pose
        tempo = daten.get("velocity") or [0.0, 0.0, 0.0]
        tempo_max = max(tempo_max, (tempo[0] ** 2 + tempo[1] ** 2) ** 0.5)
        dreh_max = max(dreh_max, abs(tempo[2]) if len(tempo) > 2 else 0.0)

    luecken = [
        {"von_s": round(zeiten[i - 1], 3), "laenge_s": round(zeiten[i] - zeiten[i - 1], 3)}
        for i in range(1, len(zeiten))
        if zeiten[i] - zeiten[i - 1] > LUECKE_AB_S
    ]
    dauer = zeiten[-1] - zeiten[0]
    akkus = [d.get("battery") for d in inhalte if d.get("battery") is not None]
    return {
        "lauf": lauf_id,
        "abtastungen": len(saetze),
        "dauer_s": round(dauer, 3),
        "takt_ist_hz": round(len(saetze) / dauer, 2) if dauer > 0 else 0.0,
        "takt_soll_hz": round(1 / SOLLTAKT_S, 2),
        "strecke_m": round(strecke, 3),
        "tempo_max": round(tempo_max, 3),
        "drehrate_max": round(dreh_max, 3),
        "akku_von": akkus[0] if akkus else None,
        "akku_bis": akkus[-1] if akkus else None,
        "luecken": luecken,
    }


@_als_liste
def karten_auflisten():
    """Nennt die aufgezeichneten GraphNav-Karten."""
    return [
        {
            "name": k.name,
            "aufgezeichnet": k.aufgezeichnet,
            "roboter": k.roboter,
            "wegpunkte": k.wegpunkte,
            "kanten": k.kanten,
            "ordner": str(k.dir),
        }
        for k in kartenspeicher.karten(arbeitsordner())
    ]


@_antwortet
def karte_lesen(name):
    """Wegpunkte und Kanten einer Karte als Grundriss."""
    from spotlab.maps.geometry import grundriss

    karte = kartenspeicher.finde(arbeitsordner(), name)
    riss = grundriss(kartenspeicher.lade_graph(karte.dir))
    return {
        "name": karte.name,
        "quelle": riss.quelle,
        "hinweis": riss.hinweis,
        "wegpunkte": [
            {"id": p.id, "name": p.name, "x": round(p.x, 3), "y": round(p.y, 3)}
            for p in riss.punkte
        ],
        "kanten": [list(k) for k in riss.kanten],
    }


@_als_liste
def spot_pruefen():
    """Dieselbe Prüfung wie `spotlab doctor` — braucht Netz und Anmeldung."""
    return [
        {"name": c.name, "ok": c.ok, "detail": c.detail, "rat": c.rat} for c in diagnose()
    ]


def _verzeichnis_von(lauf_id):
    verzeichnis = finde_lauf(arbeitsordner(), lauf_id)
    if verzeichnis is None:
        raise SpotlabError(
            f"Es gibt keinen Lauf mit der Kennung „{lauf_id}“. "
            "`laeufe_auflisten` nennt die vorhandenen."
        )
    return verzeichnis
