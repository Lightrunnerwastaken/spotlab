"""Die Dateien zwischen einem Agenten (MCP), der GUI und `workshop/zentrale.py`.

Agenten am Spot, Teil 1 (`docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`).
Dasselbe Muster wie `record/zentrale.py`: die Platte ist der einzige Kanal, jede Datei wird
atomar ersetzt, und ein Leser nimmt eine fehlende, halb geschriebene oder kaputte Datei als
„nichts da“. Reine Standardbibliothek — GUI und MCP-Server importieren dieses Modul.

agent_befehl.json   Agent → Zentrale: ein Befehl mit Nummer, Begründung und Lebenszeichen.
freigabe.json       GUI → Zentrale: „Agent darf fahren“ (nur die GUI schreibt sie).
agent_besitz.json   MCP → MCP: welcher Agent die Zentrale gerade steuert.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from spotlab.record import atomar
from spotlab.record import zentrale as protokoll

BEFEHL = "agent_befehl.json"
FREIGABE = "freigabe.json"
BESITZ = "agent_besitz.json"
ARTEN_BEFEHL = ("ziel", "relativ", "drehen", "stoss", "folgen", "stopp", "tiefe", "licht",
                "piep", "suche")
# Wie die Klickfahrt: ein Lebenszeichen, das älter ist, heisst Stopp. Der MCP-Server frischt es
# alle AGENT_PULS_S auf, solange ein Befehl unterwegs ist; stirbt der Agent, endet sein
# MCP-Prozess, und das Lebenszeichen bleibt aus.
AGENT_TOTMANN_S = 0.5
AGENT_PULS_S = 0.2
# Die Freigabe gilt nur mit frischem Puls der Oberfläche (`record/zentrale.GUI_PULS`): stürzt
# die GUI ab, erlischt sie sofort -- nicht erst nach GUI_FRIST_S, wenn die Zentrale endet.
FREIGABE_PULS_S = 3.0
_FEHLER = (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError)


@dataclass(frozen=True)
class Befehl:
    nummer: int
    art: str
    werte: dict
    warum: str
    agent: str
    lebt: float                  # Wanduhr des MCP-Servers beim letzten Auffrischen


def schreibe_befehl(lauf_dir, nummer, art, werte, warum, agent, jetzt=time.time):
    if art not in ARTEN_BEFEHL:
        raise ValueError(f"Befehl {art!r} -- erwartet einer von {list(ARTEN_BEFEHL)}.")
    daten = {"nummer": int(nummer), "art": art, "werte": dict(werte or {}),
             "warum": str(warum or ""), "agent": str(agent or ""), "lebt": float(jetzt())}
    return atomar.schreibe_atomar(Path(lauf_dir) / BEFEHL, json.dumps(daten, ensure_ascii=False))


def lies_befehl(lauf_dir):
    """Der Befehl — oder None (fehlt, halb geschrieben, kaputt, unbekannte Art)."""
    try:
        roh = json.loads((Path(lauf_dir) / BEFEHL).read_text(encoding="utf-8"))
        art = str(roh["art"])
        if art not in ARTEN_BEFEHL or not isinstance(roh["werte"], dict):
            return None
        return Befehl(int(roh["nummer"]), art, dict(roh["werte"]), str(roh["warum"]),
                      str(roh["agent"]), float(roh["lebt"]))
    except _FEHLER:
        return None


def befehl_lebt(befehl, jetzt=time.time):
    return befehl is not None and jetzt() - befehl.lebt <= AGENT_TOTMANN_S


def schreibe_freigabe(lauf_dir, an, nummer, jetzt=time.time):
    daten = {"an": bool(an), "nummer": int(nummer), "t": float(jetzt())}
    return atomar.schreibe_atomar(Path(lauf_dir) / FREIGABE, json.dumps(daten))


def lies_freigabe(lauf_dir):
    try:
        roh = json.loads((Path(lauf_dir) / FREIGABE).read_text(encoding="utf-8"))
        return {"an": bool(roh["an"]), "nummer": int(roh["nummer"]), "t": float(roh["t"])}
    except _FEHLER:
        return None


def freigabe_gilt(lauf_dir, jetzt=time.time):
    """`an` UND ein Puls der Oberfläche, der höchstens FREIGABE_PULS_S alt ist."""
    freigabe = lies_freigabe(lauf_dir)
    if freigabe is None or not freigabe["an"]:
        return False
    puls = protokoll.lies_gui_puls(lauf_dir)
    return puls is not None and jetzt() - puls <= FREIGABE_PULS_S


def schreibe_besitz(lauf_dir, agent, pid, jetzt=time.time):
    daten = {"agent": str(agent), "pid": int(pid), "seit": float(jetzt())}
    return atomar.schreibe_atomar(Path(lauf_dir) / BESITZ, json.dumps(daten, ensure_ascii=False))


def lies_besitz(lauf_dir):
    try:
        roh = json.loads((Path(lauf_dir) / BESITZ).read_text(encoding="utf-8"))
        return {"agent": str(roh["agent"]), "pid": int(roh["pid"]), "seit": float(roh["seit"])}
    except _FEHLER:
        return None
