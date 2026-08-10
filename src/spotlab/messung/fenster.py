"""Messfenster aus einer Aufzeichnung herausschneiden und auswerten.

Ein Messfenster ist der Bereich zwischen zwei `messfenster`-Ereignissen. Darin
tastet spotlab dicht und vollständig ab; hier werden daraus die Grössen
gerechnet, die die Realismus-Gates von `matura-spot` vergleichen.

Bewusst ohne Urteil: `schranke`, `annahme` und `real_prozedur` stehen im
Gate-Katalog, und spotlab darf davon nicht abhängen.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from spotlab.messung import schritt as schrittmodul
from spotlab.record.read import read_jsonl

DATEINAME = "messfenster.json"
STANDARD_HZ = 10.0                  # ausserhalb jedes Messfensters
FAHRKOMMANDOS = ("walk", "move")
# Schlüssel, deren Vorhandensein einen reich aufgezeichneten Satz ausmacht.
REICHE_SCHLUESSEL = ("feet_detail", "joint_acc", "velocity_vision")


@dataclass(frozen=True)
class Fenster:
    name: str
    felder: dict
    von_s: float
    bis_s: float
    hz_soll: float
    hz_ist: float
    abtastungen: int
    reich: bool
    unvollstaendig: bool
    zeitquelle: str                 # "robot" oder "empfang"
    kommandos: list = field(default_factory=list)
    messwerte: dict = field(default_factory=dict)


# ------------------------------------------------------------------ Einlesen


def _zeilen(pfad):
    return [z for z in read_jsonl(pfad) if isinstance(z, dict)]


def _marken(ereignisse):
    """(start, ende|None) in Reihenfolge. Verschachtelung ist beim Schreiben verboten."""
    paare, offen = [], None
    for eintrag in ereignisse:
        if eintrag.get("art") != "messfenster":
            continue
        daten = eintrag.get("daten") or {}
        if daten.get("phase") == "start":
            if offen is not None:
                paare.append((offen, None))
            offen = eintrag
        elif daten.get("phase") == "ende" and offen is not None:
            paare.append((offen, eintrag))
            offen = None
    if offen is not None:
        paare.append((offen, None))
    return paare


def _zeit(satz, quelle):
    if quelle == "robot":
        return float((satz.get("daten") or {}).get("t_robot") or 0.0)
    return float(satz.get("t") or 0.0)


def _quelle(saetze):
    """Roboteruhr nur, wenn JEDE Abtastung im Fenster einen Stempel hat.

    Ein einziger fehlender Stempel machte die Reihe auf eine Art ungleichmässig,
    die man in der Auswertung nicht mehr sieht.
    """
    if not saetze:
        return "empfang"
    alle = all(float((s.get("daten") or {}).get("t_robot") or 0.0) > 0 for s in saetze)
    return "robot" if alle else "empfang"


# ------------------------------------------------------------------ Kennzahlen


def _mittel(werte):
    return sum(werte) / len(werte) if werte else 0.0


def _gier_aufsummiert(winkel):
    """Fortlaufend, nicht Endwert minus Anfangswert.

    G4 verlangt das ausdrücklich: eine Drehung über 180° wechselt in der Differenz
    das Vorzeichen und ergäbe eine kleinere Zahl als die Wahrheit.
    """
    gesamt = 0.0
    for vorher, jetzt in zip(winkel, winkel[1:]):
        schritt = jetzt - vorher
        while schritt > math.pi:
            schritt -= 2 * math.pi
        while schritt < -math.pi:
            schritt += 2 * math.pi
        gesamt += schritt
    return gesamt


def _kommandiert(kommandos):
    """Das eine Fahrkommando im Fenster — oder {} bei Widerspruch.

    Lieber keine Zahl als eine über zwei Bedingungen gemittelte.
    """
    fahrten = [k for k in kommandos if k.get("name") in FAHRKOMMANDOS]
    if not fahrten:
        return {}
    eindeutig = {
        (
            round(float(k.get("vx") or 0.0), 6),
            round(float(k.get("vy") or 0.0), 6),
            round(float(k.get("wz") or 0.0), 6),
        )
        for k in fahrten
    }
    if len(eindeutig) != 1:
        return {}
    vx, vy, wz = next(iter(eindeutig))
    return {"vx": vx, "vy": vy, "wz": wz}


def _tracking(kommandiert, tempo_x, tempo_y, drehrate):
    """Prozent erreicht gegen kommandiert — auf der Achse, die kommandiert wurde."""
    for schluessel, erreicht in (("vx", tempo_x), ("vy", tempo_y), ("wz", drehrate)):
        soll = kommandiert.get(schluessel) or 0.0
        if abs(soll) > 1e-9:
            return round(100.0 * erreicht / soll, 2)
    return None


def _gelenke(saetze):
    je_gelenk = {}
    for satz in saetze:
        for name, g in ((satz.get("daten") or {}).get("joints") or {}).items():
            eintrag = je_gelenk.setdefault(name, {"rate_max": 0.0, "last_max": 0.0})
            eintrag["rate_max"] = max(
                eintrag["rate_max"], abs(float(g.get("velocity") or 0.0))
            )
            eintrag["last_max"] = max(eintrag["last_max"], abs(float(g.get("load") or 0.0)))
    return je_gelenk


def _fuesse(saetze, dauer):
    """Duty-Cycle und Schrittfrequenz — geht schon aus `feet`, ohne reiches Fenster."""
    reihen = [list((s.get("daten") or {}).get("feet") or ()) for s in saetze]
    breite = max((len(r) for r in reihen), default=0)
    if not breite:
        return [], None
    duty, flanken = [], 0
    for i in range(breite):
        spalte = [bool(r[i]) if i < len(r) else False for r in reihen]
        duty.append(round(sum(spalte) / len(spalte), 3))
        flanken += sum(1 for a, b in zip(spalte, spalte[1:]) if not a and b)
    frequenz = round(flanken / breite / dauer, 3) if dauer > 0 else None
    return duty, frequenz


def _terrain(saetze):
    """Reibwerte und Schlupf — nur aus reich aufgezeichneten Fenstern.

    Der Schlupfweg wird als GRÖSSTER beobachteter Betrag gemeldet, nicht
    aufsummiert: ob das SDK-Feld kumulativ oder momentan ist, ist nicht belegt,
    und eine Summe über eine kumulative Grösse wäre schlicht falsch.
    """
    mu, weg, tempo = [], 0.0, 0.0
    gesehen = False
    for satz in saetze:
        for fuss in (satz.get("daten") or {}).get("feet_detail") or ():
            gesehen = True
            if fuss.get("kontakt") and "mu" in fuss:
                mu.append(float(fuss["mu"]))
            if "slip_weg" in fuss:
                weg = max(weg, math.dist((0.0, 0.0, 0.0), fuss["slip_weg"]))
            if "slip_tempo" in fuss:
                tempo = max(tempo, math.dist((0.0, 0.0, 0.0), fuss["slip_tempo"]))
    if not gesehen:
        return None, None, None
    return (round(_mittel(mu), 4) if mu else None, round(weg, 5), round(tempo, 5))


def kennzahlen(saetze, kommandos, quelle, hz_soll):
    """Die Gate-Messgrössen aus den Abtastungen eines Fensters.

    Was nicht ableitbar ist, ist None — nie 0. Der Unterschied zwischen
    „gemessen und null" und „nicht gemessen" entscheidet, ob eine Kalibrierung
    gültig ist.
    """
    if not saetze:
        return {}

    zeiten = [_zeit(s, quelle) for s in saetze]
    daten = [s.get("daten") or {} for s in saetze]
    dauer = zeiten[-1] - zeiten[0]
    grenze = 2.0 / hz_soll if hz_soll > 0 else 2.0 / STANDARD_HZ
    # `ab_start_s` statt `von_s`: bei Zeitquelle „robot" sind `zeiten` absolute
    # Epochenstempel (1.78e9), während das Fenster selbst laufrelativ zählt —
    # eine Lücke liess sich damit nicht mehr im Fenster verorten. Der rohe
    # Stempel bleibt daneben stehen, in der Uhr, die `zeitquelle` nennt.
    luecken = [
        {
            "ab_start_s": round(zeiten[i - 1] - zeiten[0], 3),
            "laenge_s": round(zeiten[i] - zeiten[i - 1], 3),
            "t_roh_s": round(zeiten[i - 1], 3),
        }
        for i in range(1, len(zeiten))
        if zeiten[i] - zeiten[i - 1] > grenze
    ]

    hoehen = [float(d.get("z") or 0.0) for d in daten]
    posen = [d.get("pose") or [0.0, 0.0, 0.0] for d in daten]
    tempi = [d.get("velocity") or [0.0, 0.0, 0.0] for d in daten]

    strecke = sum(math.dist(a[:2], b[:2]) for a, b in zip(posen, posen[1:]))
    tempo_x = _mittel([t[0] for t in tempi])
    tempo_y = _mittel([t[1] for t in tempi])
    drehrate = _mittel([t[2] for t in tempi])
    kommandiert = _kommandiert(kommandos)
    duty, frequenz = _fuesse(saetze, dauer)
    mu_mittel, schlupf_weg, schlupf_tempo = _terrain(saetze)
    je_gelenk = _gelenke(saetze)
    versatz_x = posen[-1][0] - posen[0][0]
    versatz_y = posen[-1][1] - posen[0][1]
    schritt = schrittmodul.kennzahlen(
        saetze, zeiten, versatz_m=math.hypot(versatz_x, versatz_y)
    )

    return {
        "abtastungen": len(saetze),
        "dauer_s": round(dauer, 3),
        "hz_ist": round((len(saetze) - 1) / dauer, 2) if dauer > 0 else 0.0,
        "zeitquelle": quelle,
        "luecken": luecken,
        "hoehe_mittel": round(_mittel(hoehen), 4),
        "hoehe_min": round(min(hoehen), 4),
        "hoehe_max": round(max(hoehen), 4),
        "hoehe_drift": round(hoehen[-1] - hoehen[0], 4),
        "roll_max_grad": round(
            max(abs(math.degrees(d.get("roll") or 0.0)) for d in daten), 3
        ),
        "pitch_max_grad": round(
            max(abs(math.degrees(d.get("pitch") or 0.0)) for d in daten), 3
        ),
        "tempo_x_mittel": round(tempo_x, 4),
        "tempo_y_mittel": round(tempo_y, 4),
        "drehrate_mittel": round(drehrate, 4),
        "tempo_max": round(max(math.dist((0.0, 0.0), t[:2]) for t in tempi), 4),
        "strecke_m": round(strecke, 4),
        "netto_versatz_m": round(math.dist(posen[0][:2], posen[-1][:2]), 4),
        # Vorzeichenbehaftet je Achse: der Sim rechnet seine erreichte
        # Geschwindigkeit als dp[0]/dt. Ohne diese beiden Zahlen liesse sich das
        # real nicht nachrechnen, und der Vergleich waere keiner.
        "versatz_x_m": round(versatz_x, 4),
        "versatz_y_m": round(versatz_y, 4),
        "gierwinkel_grad": round(math.degrees(_gier_aufsummiert([p[2] for p in posen])), 2),
        # Ohne den Startwinkel ist nicht nachrechenbar, wie viel von `versatz_x`
        # und `versatz_y` nur daher kommt, dass der Roboter schräg zur odom-Achse
        # stand. Beides sind reine odom-Differenzen. Die echte Drehung ins
        # fensterlokale System ist eine RESEARCH DECISION für matura-spot — hier
        # wird nur die Zahl bereitgestellt, die sie möglich macht.
        "gier_start_grad": round(math.degrees(posen[0][2]), 2),
        "kommandiert": kommandiert,
        "tracking_prozent": _tracking(kommandiert, tempo_x, tempo_y, drehrate),
        "gelenk_rate_max": round(
            max((g["rate_max"] for g in je_gelenk.values()), default=0.0), 4
        ),
        "gelenk_last_max": round(
            max((g["last_max"] for g in je_gelenk.values()), default=0.0), 4
        ),
        "gelenke": je_gelenk,
        "fuss_duty": duty,
        "schrittfrequenz_hz": frequenz,
        "mu_mittel": mu_mittel,
        "schlupf_weg_max_m": schlupf_weg,
        "schlupf_tempo_max": schlupf_tempo,
        # Trennt zu kurze Schritte von zu langsamer Kadenz — die offene Frage
        # aus G2/G3.
        "schritt": schritt,
    }


# ------------------------------------------------------------------ Fenster


def fenster(lauf_dir):
    ordner = Path(lauf_dir)
    ereignisse = _zeilen(ordner / "ereignisse.jsonl")
    saetze = _zeilen(ordner / "zustand.jsonl")
    letzte_zeit = float(saetze[-1].get("t") or 0.0) if saetze else 0.0

    gefunden = []
    for start, ende in _marken(ereignisse):
        s_daten = start.get("daten") or {}
        von = float(start.get("t") or 0.0)
        bis = float(ende.get("t") or 0.0) if ende is not None else letzte_zeit
        # Die Zuordnung läuft über die EMPFANGSZEIT: nur sie steht in den
        # Ereignissen und in den Abtastungen auf derselben Uhr.
        drin = [s for s in saetze if von <= float(s.get("t") or 0.0) <= bis]
        quelle = _quelle(drin)
        zeiten = [_zeit(s, quelle) for s in drin]
        dauer = (zeiten[-1] - zeiten[0]) if len(zeiten) > 1 else 0.0
        hz_soll = float(s_daten.get("hz_soll") or 0.0)
        kommandos = [
            dict(e.get("daten") or {})
            for e in ereignisse
            if e.get("art") == "kommando" and von <= float(e.get("t") or 0.0) <= bis
        ]
        gefunden.append(
            Fenster(
                name=s_daten.get("name", ""),
                felder={
                    k: v for k, v in s_daten.items() if k not in ("phase", "name", "hz_soll")
                },
                von_s=von,
                bis_s=bis,
                hz_soll=hz_soll,
                hz_ist=round((len(drin) - 1) / dauer, 2) if dauer > 0 else 0.0,
                abtastungen=len(drin),
                # ÜBER ALLE Sätze, nicht nur den ersten: der Ratenwechsel wirkt
                # erst ab dem nächsten Takt, der erste Satz im Fenster ist also
                # oft noch schlank. `reich=False` stand dann genau dort, wo man
                # als Erstes nachsieht, ob Terrain-Daten vorliegen.
                reich=any(
                    k in (s.get("daten") or {})
                    for s in drin
                    for k in REICHE_SCHLUESSEL
                ),
                unvollstaendig=ende is None,
                zeitquelle=quelle,
                kommandos=kommandos,
                messwerte=kennzahlen(drin, kommandos, quelle, hz_soll),
            )
        )
    return gefunden


def als_json(liste):
    return {
        "fenster": [
            {
                "name": f.name,
                "felder": f.felder,
                "von_s": f.von_s,
                "bis_s": f.bis_s,
                "hz_soll": f.hz_soll,
                "hz_ist": f.hz_ist,
                "abtastungen": f.abtastungen,
                "reich": f.reich,
                "unvollstaendig": f.unvollstaendig,
                "zeitquelle": f.zeitquelle,
                "kommandos": f.kommandos,
                "messwerte": f.messwerte,
            }
            for f in liste
        ]
    }


def schreibe(lauf_dir):
    ordner = Path(lauf_dir)
    daten = {"lauf": ordner.name, **als_json(fenster(ordner))}
    ziel = ordner / DATEINAME
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel


# ------------------------------------------------------------------ Abschnitte


def abschnitte(lauf_dir, standard_hz=STANDARD_HZ):
    """Der Lauf in Abschnitte mit ihrer erwarteten Rate — für den Lückenmelder.

    Ohne das wäre jeder Ratenwechsel eine Falschmeldung, und ein Alarm, der bei
    jeder Messfahrt kommt, wird ignoriert.
    """
    ordner = Path(lauf_dir)
    ereignisse = _zeilen(ordner / "ereignisse.jsonl")
    saetze = _zeilen(ordner / "zustand.jsonl")
    ende = float(saetze[-1].get("t") or 0.0) if saetze else 0.0

    stuecke, zeiger = [], 0.0
    for start, schluss in _marken(ereignisse):
        von = float(start.get("t") or 0.0)
        bis = float(schluss.get("t") or 0.0) if schluss is not None else ende
        if von > zeiger:
            stuecke.append({"von_s": zeiger, "bis_s": von, "hz_soll": standard_hz})
        stuecke.append(
            {
                "von_s": von,
                "bis_s": bis,
                "hz_soll": float((start.get("daten") or {}).get("hz_soll") or standard_hz),
                "fenster": (start.get("daten") or {}).get("name", ""),
            }
        )
        zeiger = bis
    if ende > zeiger or not stuecke:
        stuecke.append({"von_s": zeiger, "bis_s": ende, "hz_soll": standard_hz})
    return stuecke


def hz_soll_zwischen(stuecke, von, bis, standard_hz=STANDARD_HZ):
    """Die KLEINSTE erwartete Rate der berührten Abschnitte.

    Eine Lücke, die über einen Ratenwechsel hinweg liegt, darf nicht gegen die
    schnellere Seite gemessen werden: direkt nach dem Herunterschalten von 50 auf
    10 Hz ist ein Abstand von 0.1 s genau richtig und keine Lücke. Die kleinste
    Rate gibt den grössten erlaubten Abstand — in die nachsichtige Richtung, damit
    kein Alarm entsteht, den man wegzuklicken lernt.
    """
    beruehrt = [s["hz_soll"] for s in stuecke if s["von_s"] <= bis and s["bis_s"] >= von]
    return min(beruehrt) if beruehrt else standard_hz
