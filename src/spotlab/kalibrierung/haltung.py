"""Aufstehen aus dem Sitzen, gemessen an echten Läufen: die mittlere Gelenkbahn.

Quelle ist jedes `stand()`-Kommando eines Laufs am echten Spot, dem eine Sitzhaltung
vorausging (Hub über `MIN_HUB_M`) — in den Läufen der Schule fast jeder Programmstart.
Die Bahn beginnt bei der letzten ruhigen Probe vor der Bewegung (Sitzhaltung) und endet,
sobald die Höhe ruhig ist (Standhaltung); dazwischen wird jedes Gelenk auf `PUNKTE`
gleichmässige Stellen interpoliert und über die Läufe der Median genommen.

matura-spot fährt diese Bahn im Physikmodus (`spotsim/haltung.py`, wörtliche Kopie der
Datei mit Vergleichstest). Das HINSETZEN ist nicht aufgezeichnet — nach `sit()` enden die
Läufe nach höchstens 0.4 s —, dort gilt die Bahn rückwärts als Annahme (H2, Abnahme A41).

`z` in `zustand.jsonl` ist die Odometrie und driftet über einen Lauf; es zählt nur der
Unterschied innerhalb eines Vorgangs.
"""

import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

GELENKE = tuple(f"{bein}.{teil}" for bein in ("fl", "fr", "hl", "hr") for teil in ("hx", "hy", "kn"))
PUNKTE = 11
MIN_HUB_M = 0.2          # darunter war es ein stand() aus dem Stehen
BEWEGT_M = 0.01          # so weit weg von der Ausgangshöhe heisst: er bewegt sich
RUHIG_M = 0.005          # so wenig Änderung über RUHIG_PROBEN heisst: er steht still
RUHIG_PROBEN = 5
NACH_S = 8.0             # so lange nach dem Kommando wird gesucht
ERLAUBT = ("real",)      # die Kalibrierung liest nur echte Läufe (CLAUDE.md)

DATEI = Path(__file__).parent / "daten" / "haltung.json"


def _zeilen(pfad):
    with open(pfad, encoding="utf-8") as datei:
        return [json.loads(zeile) for zeile in datei if zeile.strip()]


def _interpoliert(zeiten, werte, t):
    for i in range(1, len(zeiten)):
        if t <= zeiten[i]:
            a = (t - zeiten[i - 1]) / (zeiten[i] - zeiten[i - 1]) if zeiten[i] > zeiten[i - 1] else 1.0
            return werte[i - 1] + a * (werte[i] - werte[i - 1])
    return werte[-1]


def _vorgang(zustand, t_kommando):
    vor = [z for z in zustand if t_kommando - 1.0 <= z["t"] <= t_kommando]
    nach = [z for z in zustand if t_kommando <= z["t"] <= t_kommando + NACH_S]
    if len(vor) < 3 or len(nach) < RUHIG_PROBEN + 2:
        return None
    z0 = statistics.median(z["daten"]["z"] for z in vor)
    bewegt = next((i for i, z in enumerate(nach) if abs(z["daten"]["z"] - z0) > BEWEGT_M), None)
    if bewegt is None:
        return None
    ende = next((i for i in range(bewegt, len(nach) - RUHIG_PROBEN + 1)
                 if max(nach[j]["daten"]["z"] for j in range(i, i + RUHIG_PROBEN))
                 - min(nach[j]["daten"]["z"] for j in range(i, i + RUHIG_PROBEN)) < RUHIG_M), None)
    if ende is None:
        return None
    reihe = ([vor[-1]] if bewegt == 0 else []) + nach[max(0, bewegt - 1):ende + 1]
    t_a, t_e = reihe[0]["t"], reihe[-1]["t"]
    hub = reihe[-1]["daten"]["z"] - z0
    if hub < MIN_HUB_M or t_e <= t_a:
        return None
    zeiten = [z["t"] for z in reihe]
    bahn = []
    for k in range(PUNKTE):
        t = t_a + (t_e - t_a) * k / (PUNKTE - 1)
        bahn.append([_interpoliert(zeiten, [z["daten"]["joints"][n]["position"] for z in reihe], t)
                     for n in GELENKE])
    return {"verzug_s": t_a - t_kommando, "dauer_s": t_e - t_a, "hub_m": hub, "bahn": bahn}


def aufstehvorgaenge(lauf_dir):
    """Die Aufstehvorgänge eines Laufs — leer, wenn er nicht echt oder nicht lesbar ist. Wirft nie."""
    lauf_dir = Path(lauf_dir)
    try:
        if json.loads((lauf_dir / "lauf.json").read_text(encoding="utf-8")).get("backend") not in ERLAUBT:
            return []
        ereignisse = _zeilen(lauf_dir / "ereignisse.jsonl")
        zustand = [z for z in _zeilen(lauf_dir / "zustand.jsonl")
                   if isinstance(z.get("daten", {}).get("z"), (int, float))
                   and isinstance(z["daten"].get("joints"), dict)]
        vorgaenge = []
        for e in ereignisse:
            if e.get("art") == "kommando" and e.get("daten", {}).get("name") == "stand":
                v = _vorgang(zustand, e["t"])
                if v is not None:
                    vorgaenge.append(v)
        return vorgaenge
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return []


def haltung(lauf_dirs):
    """Median über alle Aufstehvorgänge der Läufe."""
    vorgaenge = [v for d in lauf_dirs for v in aufstehvorgaenge(d)]
    if not vorgaenge:
        raise ValueError("Kein Aufstehen aus dem Sitzen in diesen Läufen gefunden.")
    return {
        "herkunft": {"quelle": "stand() aus dem Sitzen, echte Läufe (spotlab kalibrierung/haltung.py)",
                     "erzeugt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "anzahl": len(vorgaenge),
        "verzug_s": statistics.median(v["verzug_s"] for v in vorgaenge),
        "dauer_s": statistics.median(v["dauer_s"] for v in vorgaenge),
        "hub_m": statistics.median(v["hub_m"] for v in vorgaenge),
        "gelenke": list(GELENKE),
        "bahn": [[statistics.median(v["bahn"][k][j] for v in vorgaenge) for j in range(len(GELENKE))]
                 for k in range(PUNKTE)],
    }


def main(argv=None):
    ordner = [Path(a) for a in (sys.argv[1:] if argv is None else argv)]
    if not ordner:
        print("Aufruf: python -m spotlab.kalibrierung.haltung <runs-Ordner> ...")
        return 2
    laeufe = [d for o in ordner for d in sorted(o.iterdir()) if d.is_dir()]
    daten = haltung(laeufe)
    DATEI.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{daten['anzahl']} Aufstehvorgänge: Hub {daten['hub_m']:.3f} m, Dauer {daten['dauer_s']:.2f} s, "
          f"Verzug {daten['verzug_s']:.2f} s -> {DATEI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
