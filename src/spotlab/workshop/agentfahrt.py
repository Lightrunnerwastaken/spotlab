"""Fahrbausteine für Agentenbefehle — rein rechnerisch, ohne Roboter.

Agenten am Spot, Teil 1 (`docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`). Die
Zentrale gibt Lage, Gitter und Schranken hinein; hier wird nur gerechnet:

relativ_ziel      „1 m vor, 0.5 m links“ → ein Punkt im Rahmen der Skizze, dann fährt die
                  Klickfahrt dorthin wie zu einem Klick.
Drehung           auf der Stelle auf eine Gier drehen, fertig bei `DREH_FERTIG_GRAD`.
stoss_pruefen     ein kurzer Fahrstoss: gekappt, geprüft, oder mit Grund abgelehnt.
tiefe_sektoren    die Punktwolke der Frontkameras als drei Abstände (links, mitte, rechts).

Alle Schranken sind fail-closed wie beim Folgen: wer seine Daten nicht lesen kann, fährt nicht.
"""

import math

import numpy as np

from spotlab.record import fahrt as fahrtdatei
from spotlab.workshop import klickfahrt

STOSS_MAX_S = 2.0
STOSS_SEITE_MAX_M_S = 0.2       # seitwärts und rückwärts: langsam, und nur über gesehenen Boden
STOSS_PROBE_M = 0.1             # so dicht wird die Strecke im Gitter geprüft
DREH_FERTIG_GRAD = 3.0
DREH_FRIST_S = 15.0
# Reines Drehen unter 0.125 rad/s lässt der echte Spot stehen (`docs/SIM_ANTWORT.md`) — eine
# Drehung, die sich dem Ziel langsam nähert, käme sonst nie an.
DREH_MIN_RAD_S = 0.15
TIEFE_BODEN_M = -0.40           # darunter ist Boden (Körpermitte ~0.5 m über dem Grund)
TIEFE_SEKTOR_GRAD = 10.0
TIEFE_PERZENTIL = 5
TIEFE_MIN_PUNKTE = 20


def _wickle(rad):
    return (rad + math.pi) % (2.0 * math.pi) - math.pi


def relativ_ziel(lage, vor_m, links_m):
    """Ein Punkt `vor_m` voraus und `links_m` links von Spot, im Rahmen der Lage."""
    x, y, gier = lage
    c, s = math.cos(gier), math.sin(gier)
    return (x + c * vor_m - s * links_m, y + s * vor_m + c * links_m)


class Drehung:
    """Auf der Stelle auf `ziel_gier_rad` drehen; `schritt` sagt je Takt, wie schnell."""

    def __init__(self, ziel_gier_rad, t0, max_w=fahrtdatei.DREH_RAD_S):
        self.ziel = float(ziel_gier_rad)
        self.t0 = float(t0)
        self.max_w = float(max_w)

    def schritt(self, gier, t):
        """-> (wz, zustand, grund), zustand ∈ unterwegs | angekommen | abgebrochen."""
        abweichung = _wickle(self.ziel - gier)
        if abs(abweichung) <= math.radians(DREH_FERTIG_GRAD):
            return 0.0, "angekommen", ""
        if t - self.t0 > DREH_FRIST_S:
            return 0.0, "abgebrochen", (f"nach {DREH_FRIST_S:.0f} s nicht angekommen — "
                                        f"{math.degrees(abweichung):+.0f}° fehlen")
        wz = max(-self.max_w, min(self.max_w, klickfahrt.LENKUNG * abweichung))
        if abs(wz) < DREH_MIN_RAD_S:
            wz = math.copysign(DREH_MIN_RAD_S, abweichung)
        return wz, "unterwegs", ""


def _richtung(vx, vy):
    if vx < 0 and abs(vx) >= abs(vy):
        return "hinten"
    return "links" if vy > 0 else "rechts"


def stoss_pruefen(vx, vy, wz, dauer_s, lage, gitter, frei_m, kopf_frei, kopf_grund,
                  max_v, max_w):
    """Ein Fahrstoss, gekappt und geprüft: -> (vx, vy, wz, dauer_s, grund | None).

    Ein Grund heisst: gar nicht fahren. Vorwärts gelten die Schranken der Klickfahrt (frei
    voraus `frei_m` aus dem Hindernisgitter, dazu der Kopfraum). Seitwärts und rückwärts sieht
    keine Vorwärtsschranke etwas — dort fährt Spot höchstens `STOSS_SEITE_MAX_M_S`, und jeder
    Punkt der gefahrenen Bahn (alle `STOSS_PROBE_M`, mitgedreht um `wz`) muss im Gitter
    `klickfahrt.RAND_M` frei sein; Unbekanntes ist nicht frei.
    """
    dauer = max(0.0, min(STOSS_MAX_S, float(dauer_s)))
    vx = max(-max_v, min(max_v, float(vx)))
    vy = max(-max_v, min(max_v, float(vy)))
    wz = max(-max_w, min(max_w, float(wz)))
    if not all(math.isfinite(v) for v in (vx, vy, wz, dauer)):
        return 0.0, 0.0, 0.0, 0.0, "ungültige Zahl im Stoss"
    langsam = vx < 0 or vy != 0
    if langsam:
        betrag = math.hypot(vx, vy)
        if betrag > STOSS_SEITE_MAX_M_S:
            vx, vy = vx * STOSS_SEITE_MAX_M_S / betrag, vy * STOSS_SEITE_MAX_M_S / betrag
    if vx > 0:
        if frei_m is None:
            return vx, vy, wz, dauer, "Hindernisgitter nicht lesbar"
        noetig = vx * dauer + klickfahrt.RAND_M
        if frei_m < noetig:
            return vx, vy, wz, dauer, f"voraus nur {frei_m:.2f} m frei, nötig {noetig:.2f} m"
        if not kopf_frei:
            return vx, vy, wz, dauer, kopf_grund or "Kopfraum nicht frei"
    if langsam:
        if gitter is None:
            return vx, vy, wz, dauer, ("kein lesbares Gitter — seitwärts und rückwärts nur "
                                       "über gesehenen Boden")
        grund = _bahn_frei(vx, vy, wz, dauer, lage, gitter)
        if grund:
            return vx, vy, wz, dauer, grund
    return vx, vy, wz, dauer, None


def _bahn_frei(vx, vy, wz, dauer, lage, gitter):
    x, y, gier = lage
    weg = math.hypot(vx, vy) * dauer
    schritte = max(1, int(math.ceil(weg / STOSS_PROBE_M)))
    dt = dauer / schritte
    for _ in range(schritte):
        c, s = math.cos(gier), math.sin(gier)
        x += (c * vx - s * vy) * dt
        y += (s * vx + c * vy) * dt
        gier += wz * dt
        if not gitter.is_free(x, y, margin=klickfahrt.RAND_M):
            return (f"nach {_richtung(vx, vy)} nicht frei — bei ({x:.2f}, {y:.2f}) weniger als "
                    f"{klickfahrt.RAND_M:.1f} m Platz oder ungesehen")
    return None


def tiefe_sektoren(punkte_body):
    """Die Punkte der Frontkameras (Körperrahmen) als Abstand je Sektor.

    Nur Punkte über dem Boden (z > `TIEFE_BODEN_M`), vor Spot und ausserhalb des eigenen
    Rumpfs (dieselbe Ellipse wie der Kopfraum in `backends/real/tiefe.py`). Sektor „mitte“
    ist ±`TIEFE_SEKTOR_GRAD`, links und rechts der Rest. Abstand ist das
    `TIEFE_PERZENTIL`. Perzentil der waagrechten Entfernung — robuster als der nächste
    einzelne Punkt. Unter `TIEFE_MIN_PUNKTE` Punkten gibt es keine Zahl, sondern den Grund.
    """
    from spotlab.backends.real.tiefe import RUMPF_A_M, RUMPF_B_M

    p = np.asarray(punkte_body, dtype=float).reshape(-1, 3)
    p = p[np.isfinite(p).all(axis=1)]
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    eigen = (x / RUMPF_A_M) ** 2 + (y / RUMPF_B_M) ** 2 < 1.0
    p = p[(z > TIEFE_BODEN_M) & (x > 0) & ~eigen]
    abstand = np.hypot(p[:, 0], p[:, 1])
    peilung = np.degrees(np.arctan2(p[:, 1], p[:, 0]))
    masken = {"links": peilung > TIEFE_SEKTOR_GRAD,
              "mitte": np.abs(peilung) <= TIEFE_SEKTOR_GRAD,
              "rechts": peilung < -TIEFE_SEKTOR_GRAD}
    ergebnis = {}
    for name, maske in masken.items():
        n = int(maske.sum())
        if n < TIEFE_MIN_PUNKTE:
            ergebnis[name] = {"abstand_m": None, "punkte": n,
                              "grund": f"zu wenig Punkte ({n} < {TIEFE_MIN_PUNKTE})"}
        else:
            ergebnis[name] = {"abstand_m": round(float(np.percentile(abstand[maske],
                                                                     TIEFE_PERZENTIL)), 3),
                              "punkte": n, "grund": ""}
    return ergebnis
