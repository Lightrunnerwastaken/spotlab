"""Echte walk()-Läufe im Sim nachspielen und das Tempo vergleichen.

    python -m spotlab.kalibrierung.nachspiel <lauf-oder-ordner> [...] [--tempoantwort DATEI]

Die Kommandos eines kommandierten Laufs gehen zu denselben Zeiten in ein
`SimBackend` mit eingespeister Uhr, abgetastet wird zu denselben Zeiten wie am
Roboter. Verglichen wird auf beiden Seiten das GEMELDETE Tempo im Körperrahmen:

- Verzug und Anteil je Achse: beste Anpassung ist(t) ≈ g · soll(t − L)
- Nachlauf: Weg bzw. Drehung in den 2 s nach einem Stopp, wenn danach Ruhe ist
- Drehschwelle: reines Drehen unter der Schwelle, erreicht / befohlen

DIE FALLE (wie in `pruefung.py`): die mitgelieferte Tempokennlinie ist AUS
diesen Läufen gebaut. Gegen dieselben Läufe gehalten misst das die Anpassung,
nicht die Gültigkeit. Für die Gültigkeit die Kennlinie aus einem Teil der Läufe
bauen (`tempoantwort <ordner> --ziel X`) und den ANDEREN Teil mit
`--tempoantwort X` nachspielen.

Liest ausschliesslich; es gibt keinen Roboter und kein Netz.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from spotlab.kalibrierung.antwort import _median
from spotlab.kalibrierung.tempoantwort import (
    ECHTE_BACKENDS,
    GUELTIG_S,
    _befehl_zu,
    _laeufe,
    _lies,
    drehproben,
    lade_modell,
)

ACHSEN = ("vx", "vy", "wz")
MAX_VERZUG_S = 1.5
VERZUG_RASTER_S = 0.02
NACHLAUF_S = 2.0
START = 1_000_000.0


class _Uhr:
    def __init__(self):
        self.t = START

    def __call__(self):
        return self.t


def nachspielen(befehle, zeiten, tempoantwort=None):
    """[(t, vx, vy, wz)] des Sim zu den `zeiten`, Kommandos zu ihren Zeiten."""
    from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b
    from bosdyn.client.robot_command import RobotCommandBuilder

    from spotlab.backends.sim import SimBackend

    uhr = _Uhr()
    backend = SimBackend(jetzt=uhr, tempoantwort=tempoantwort)
    backend.power_on()
    t_null = min([b[0] for b in befehle] + list(zeiten))
    plan = sorted([(b[0], 0, b) for b in befehle] + [(t, 1, None) for t in zeiten],
                  key=lambda e: (e[0], e[1]))
    reihe = []
    for t, art, b in plan:
        uhr.t = max(uhr.t, START + t - t_null)
        if art == 0:
            if b[1] == "walk":
                backend.send_command(
                    RobotCommandBuilder.synchro_velocity_command(v_x=b[2], v_y=b[3], v_rot=b[4]),
                    end_time_secs=uhr.t + GUELTIG_S)
            elif b[1] in ("stop", "sit"):
                backend.send_command(RobotCommandBuilder.stop_command())
            elif b[1] == "stand":
                backend.send_command(RobotCommandBuilder.synchro_stand_command())
        else:
            v = backend.robot_state().kinematic_state.velocity_of_body_in_odom
            q = get_a_tform_b(backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME).rotation
            yaw = 2 * math.atan2(q.z, q.w)
            c, s = math.cos(yaw), math.sin(yaw)
            reihe.append((t, c * v.linear.x + s * v.linear.y, -s * v.linear.x + c * v.linear.y,
                          v.angular.z))
    return reihe


def _wert_bei(reihe, t, i):
    """Lineare Interpolation der Spalte i zur Zeit t (Rand: festgehalten)."""
    lo, hi = 0, len(reihe) - 1
    if t <= reihe[0][0]:
        return reihe[0][i]
    if t >= reihe[hi][0]:
        return reihe[hi][i]
    while hi - lo > 1:
        mitte = (lo + hi) // 2
        if reihe[mitte][0] <= t:
            lo = mitte
        else:
            hi = mitte
    (t0, *a), (t1, *b) = reihe[lo], reihe[hi]
    return a[i - 1] + (b[i - 1] - a[i - 1]) * (t - t0) / (t1 - t0)


def anpassung(befehle, reihe, achse):
    """(Verzug s, Anteil) mit dem kleinsten Rest, oder None ohne Kommando auf der Achse."""
    i = ACHSEN.index(achse)
    zeiten = [p[0] for p in reihe]
    soll = [_befehl_zu(befehle, t)[i] for t in zeiten]
    if sum(1 for s in soll if abs(s) > 1e-9) < 10:
        return None
    best = None
    for k in range(int(MAX_VERZUG_S / VERZUG_RASTER_S) + 1):
        lag = k * VERZUG_RASTER_S
        ist = [_wert_bei(reihe, t + lag, i + 1) for t in zeiten]
        ss = sum(s * s for s in soll)
        g = sum(s * x for s, x in zip(soll, ist)) / ss
        rest = sum((x - g * s) ** 2 for s, x in zip(soll, ist))
        if best is None or rest < best[2]:
            best = (lag, g, rest)
    return best[0], best[1]


def nachlaeufe(befehle, reihe):
    """[(Weg m, Drehung rad)] in NACHLAUF_S nach jedem Stopp, auf den Ruhe folgt.

    VORZEICHENRICHTIG in Richtung des letzten Kommandos (None, wenn es die Achse
    nicht hatte). Der Betrag des Tempos zaehlte das Gangpendeln nach dem Stopp
    als Weg: 0.02 rad/s Rauschen ueber 2 s waren beim echten Spot 0.036 rad
    "Nachlauf", obwohl er netto stand.
    """
    out = []
    walks = [b for b in befehle if b[1] == "walk"]
    for b in befehle:
        vorher = [w for w in walks if b[0] - GUELTIG_S <= w[0] < b[0]]
        if b[1] != "stop" or not vorher:
            continue
        if any(b[0] < w[0] <= b[0] + NACHLAUF_S for w in walks):
            continue
        _, _, vx, vy, wz = vorher[-1]
        fenster = [p for p in reihe if b[0] <= p[0] <= b[0] + NACHLAUF_S]
        if len(fenster) < 10:
            continue
        v = math.hypot(vx, vy)
        weg = dreh = 0.0
        for p, q in zip(fenster, fenster[1:]):
            dt = q[0] - p[0]
            if v > 1e-9:
                weg += (p[1] * vx + p[2] * vy) / v * dt
            if abs(wz) > 1e-9:
                dreh += p[3] * math.copysign(1.0, wz) * dt
        out.append((weg if v > 1e-9 else None, dreh if abs(wz) > 1e-9 else None))
    return out


def drehen_unter(befehle, reihe, schwelle):
    """[erreicht/befohlen] je Takt mit reinem Drehkommando unter `schwelle` (rad/s)."""
    return [a for w, a in drehproben(befehle, reihe) if w < schwelle]


def vergleiche(lauf_dir, tempoantwort=None):
    """Kennzahlen fuer echt und Sim eines Laufs."""
    name, befehle, echt = _lies(lauf_dir)
    sim = nachspielen(befehle, [p[0] for p in echt], tempoantwort)
    schwelle = (tempoantwort or lade_modell()).drehschwelle_rad_s
    ergebnis = {"lauf": name, "dauer_s": round(echt[-1][0] - echt[0][0], 1)}
    for seite, reihe in (("echt", echt), ("sim", sim)):
        ergebnis[seite] = {
            "anpassung": {a: anpassung(befehle, reihe, a) for a in ACHSEN},
            "nachlauf": nachlaeufe(befehle, reihe),
            # Unter der GEMESSENEN Schwelle -- beim Sofort-Modell ist dessen eigene 0.
            "drehen_unter_schwelle": drehen_unter(befehle, reihe, lade_modell().drehschwelle_rad_s),
        }
    ergebnis["drehschwelle_modell"] = schwelle
    return ergebnis


def _zeile(werte):
    return " ".join(f"{w:>7.3f}" if w is not None else f"{'-':>7}" for w in werte)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ordner", nargs="+")
    ap.add_argument("--tempoantwort", help="eine andere Tempokennlinie (JSON)")
    ap.add_argument("--json", help="Ergebnisse zusaetzlich hierhin schreiben")
    ap.add_argument("--ab", default="", help="nur Laeufe, deren Name >= diesem Text ist (Datum)")
    args = ap.parse_args(argv)
    modell = lade_modell(args.tempoantwort) if args.tempoantwort else None
    ergebnisse = []
    for o in args.ordner:
        for lauf in _laeufe(o):
            if lauf.name < args.ab:
                continue
            if json.loads((lauf / "lauf.json").read_text(encoding="utf-8")).get("backend") not in ECHTE_BACKENDS:
                continue
            if not any(b[1] == "walk" for b in _lies(lauf)[1]):
                continue
            ergebnisse.append(vergleiche(lauf, modell))
    if not ergebnisse:
        print("Keine kommandierten walk()-Läufe gefunden.", file=sys.stderr)
        return 1
    print(f"{len(ergebnisse)} Läufe. Median über die Läufe:")
    print(f"{'':10}{'Verzug vx':>12}{'Anteil vx':>12}{'Verzug wz':>12}{'Anteil wz':>12}"
          f"{'Nachlauf m':>12}{'Nachl. rad':>12}{'Dreh<Schw.':>12}")
    for seite in ("echt", "sim"):
        def median_von(achse, k):
            w = [e[seite]["anpassung"][achse][k] for e in ergebnisse if e[seite]["anpassung"][achse]]
            return _median(w) if w else None

        nach = [n for e in ergebnisse for n in e[seite]["nachlauf"]]
        werte = [median_von("vx", 0), median_von("vx", 1), median_von("wz", 0), median_von("wz", 1),
                 _median(weg) if (weg := [n[0] for n in nach if n[0] is not None]) else None,
                 _median(dreh) if (dreh := [n[1] for n in nach if n[1] is not None]) else None]
        unter = [a for e in ergebnisse for a in e[seite]["drehen_unter_schwelle"]]
        werte.append(_median(unter) if unter else None)
        print(f"{seite:10}" + "".join(f"{_zeile([w]):>12}" for w in werte))
    if args.json:
        Path(args.json).write_text(json.dumps(ergebnisse, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

