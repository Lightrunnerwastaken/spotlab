"""Schrittgeometrie aus den Fussdaten eines Messfensters.

Die Frage dahinter: kommt eine zu langsame Fahrt aus zu kurzen Schritten oder
aus einer zu langsamen Kadenz? Ein Sim mit fester Zyklusdauer erzeugt
Geschwindigkeit allein ueber die Schrittlaenge — der echte Spot verlaengert den
Schritt UND passt die Kadenz an. Genau das trennt dieses Modul.

Gerechnet wird aus dem, was ohnehin im Messfenster steht: Fussposition im
Koerperframe, Kontaktzustand, volle Koerperlage. Fusspositionen werden dafuer in
den odom-Frame gedreht — im Koerperframe wandert ein stehender Fuss nach hinten,
waehrend der Rumpf vorrueckt, und man maesse den Rumpf statt den Schritt.

Qt-frei und SDK-frei wie der Rest von messung/.
"""

import math

# Toleranz, bis zu der zwei Aufsetzzeitpunkte als "gleichzeitig" gelten,
# in Bruchteilen der Zyklusdauer.
PHASENTOLERANZ = 0.15


def _mittel(werte):
    return sum(werte) / len(werte) if werte else None


def dreh_matrix(roll, pitch, yaw):
    """Rotation Koerper -> odom, Konvention ZYX wie in api/state.py::rpy_aus."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def fuss_in_odom(daten, index):
    """Fussposition in der Welt — oder None, wenn das Fenster schlank ist.

    Ohne diese Drehung waere jede Schrittlaenge falsch: im Koerperframe bewegt
    sich ein stehender Fuss um genau die Strecke, die der Rumpf zuruecklegt.
    """
    detail = daten.get("feet_detail") or ()
    if index >= len(detail):
        return None
    pos = (detail[index] or {}).get("pos")
    if not pos or len(pos) < 3:
        return None
    pose = daten.get("pose") or [0.0, 0.0, 0.0]
    r = dreh_matrix(
        float(daten.get("roll") or 0.0),
        float(daten.get("pitch") or 0.0),
        float(pose[2]),
    )
    ursprung = (float(pose[0]), float(pose[1]), float(daten.get("z") or 0.0))
    return tuple(
        ursprung[i] + sum(r[i][j] * float(pos[j]) for j in range(3)) for i in range(3)
    )


def _kontakte(daten, fuesse):
    """Kontaktzustaende — aus `feet` (immer da) oder ersatzweise aus `feet_detail`."""
    roh = daten.get("feet")
    if roh:
        return [bool(k) for k in roh] + [False] * (fuesse - len(roh))
    detail = daten.get("feet_detail") or ()
    return [bool((f or {}).get("kontakt")) for f in detail] + [False] * (
        fuesse - len(detail)
    )


def flanken(reihe):
    """(Aufsetzer, Abheber) als Indizes. Aufsetzen ist False -> True."""
    aufsetzer = [i for i in range(1, len(reihe)) if reihe[i] and not reihe[i - 1]]
    abheber = [i for i in range(1, len(reihe)) if not reihe[i] and reihe[i - 1]]
    return aufsetzer, abheber


def _phasen(aufsetzzeiten, zyklus):
    """Phasenlage der Fuesse relativ zum ersten, der aufsetzt."""
    erste = [z[0] if z else None for z in aufsetzzeiten]
    bezug = min((t for t in erste if t is not None), default=None)
    if bezug is None or not zyklus:
        return [None] * len(aufsetzzeiten)
    return [
        None if t is None else round(((t - bezug) / zyklus) % 1.0, 3) for t in erste
    ]


def _muster(phasen):
    """Grobes Gangmuster aus der Zahl der Phasengruppen.

    Bewusst OHNE Beinnamen: welcher Eintrag in `foot_state` welches Bein ist,
    steht nicht in der Nachricht. Trab und Pass unterscheiden sich genau darin —
    deshalb heisst es hier „zweitakt" und nicht „Trab". Die rohen Phasen stehen
    daneben; wer die Beinreihenfolge kennt, liest es dort ab.
    """
    werte = sorted(p for p in phasen if p is not None)
    if len(werte) < 2:
        return "unklar"
    gruppen = [[werte[0]]]
    for p in werte[1:]:
        if p - gruppen[-1][-1] <= PHASENTOLERANZ:
            gruppen[-1].append(p)
        else:
            gruppen.append([p])
    # Kreisschluss: die letzte Gruppe kann zur ersten gehoeren.
    if len(gruppen) > 1 and (1.0 - gruppen[-1][-1]) + gruppen[0][0] <= PHASENTOLERANZ:
        gruppen[0] = gruppen.pop() + gruppen[0]
    return {1: "gleichzeitig", 2: "zweitakt", 3: "dreitakt", 4: "viertakt"}.get(
        len(gruppen), "unklar"
    )


def kennzahlen(saetze, zeiten, versatz_m=None):
    """Schrittgeometrie eines Messfensters.

    `zeiten` sind die schon gewaehlten Zeitstempel (Roboteruhr oder Empfang),
    damit hier nicht zum zweiten Mal entschieden wird, welche Uhr gilt.

    Was ohne `feet_detail` nicht ableitbar ist, bleibt None — Schrittlaenge und
    Schwunghoehe brauchen Fusspositionen, Takt und Phasen nicht.
    """
    if len(saetze) < 2:
        return {}
    daten = [s.get("daten") or {} for s in saetze]
    fuesse = max((len(_kontakte(d, 0)) for d in daten), default=0)
    if not fuesse:
        return {}

    zyklen_je_fuss, schwung, stand = [], [], []
    laengen, hoehen = [], []
    aufsetzzeiten = []

    for i in range(fuesse):
        reihe = [_kontakte(d, fuesse)[i] for d in daten]
        aufsetzer, abheber = flanken(reihe)
        aufsetzzeiten.append([zeiten[k] for k in aufsetzer])

        zyklen_je_fuss += [
            zeiten[b] - zeiten[a] for a, b in zip(aufsetzer, aufsetzer[1:])
        ]
        # Schwung: Abheben -> naechstes Aufsetzen. Stand: umgekehrt.
        for ab in abheber:
            nach = [a for a in aufsetzer if a > ab]
            if nach:
                schwung.append(zeiten[nach[0]] - zeiten[ab])
        for auf in aufsetzer:
            nach = [b for b in abheber if b > auf]
            if nach:
                stand.append(zeiten[nach[0]] - zeiten[auf])

        # Schrittlaenge: Abstand der Aufsetzpunkte in der Welt.
        punkte = [(k, fuss_in_odom(daten[k], i)) for k in aufsetzer]
        punkte = [(k, p) for k, p in punkte if p is not None]
        for (_ka, a), (_kb, b) in zip(punkte, punkte[1:]):
            laengen.append(math.dist(a[:2], b[:2]))

        # Schwunghoehe: Gipfel ueber der Sehne zwischen Abheben und Aufsetzen.
        for ab in abheber:
            nach = [a for a in aufsetzer if a > ab]
            if not nach:
                continue
            start, ende = fuss_in_odom(daten[ab], i), fuss_in_odom(daten[nach[0]], i)
            if start is None or ende is None:
                continue
            bahn = [
                fuss_in_odom(daten[k], i) for k in range(ab, nach[0] + 1)
            ]
            bahn = [p for p in bahn if p is not None]
            if bahn:
                hoehen.append(max(p[2] for p in bahn) - 0.5 * (start[2] + ende[2]))

    zyklus = _mittel(zyklen_je_fuss)
    dauer = zeiten[-1] - zeiten[0]
    phasen = _phasen(aufsetzzeiten, zyklus)

    weg_je_zyklus = None
    if zyklus and dauer > 0 and versatz_m is not None:
        weg_je_zyklus = abs(versatz_m) * zyklus / dauer

    return {
        "zyklusdauer_s": None if zyklus is None else round(zyklus, 4),
        "zyklen": None if not zyklus else round(dauer / zyklus, 2),
        "schwungdauer_s": None if (m := _mittel(schwung)) is None else round(m, 4),
        "standdauer_s": None if (m := _mittel(stand)) is None else round(m, 4),
        "schrittlaenge_m": None if (m := _mittel(laengen)) is None else round(m, 4),
        "schritte": len(laengen),
        "schwunghoehe_m": None if (m := _mittel(hoehen)) is None else round(m, 4),
        "phasen": phasen,
        "muster": _muster(phasen),
        "weg_je_zyklus_m": None if weg_je_zyklus is None else round(weg_je_zyklus, 4),
    }
