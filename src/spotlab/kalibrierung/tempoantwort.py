"""Die Körperantwort auf walk() — aus KOMMANDIERTEN Läufen.

    python -m spotlab.kalibrierung.tempoantwort <ordner-mit-laeufen> [...]
    python -m spotlab.kalibrierung.tempoantwort <ordner> --probe   # nur anzeigen

Die Gangkennlinie (`gang.py`) sagt, wie die Beine sich bei einem Tempo bewegen,
`antwort.py`, wie der Roboter ein `move()`-Ziel anfährt. Wie er auf ein
GESCHWINDIGKEITSKOMMANDO antwortet, stand bis zum 23.09.2026 nirgends: der Sim
setzte das Kommando sofort und vollständig um, und nach dem Loslassen stand er
im selben Takt. Seit dem 23.09.2026 gibt es die Kurve: 60 Läufe mit `fahren.py`
und `folgen.py` am Schul-Spot (07.–21.09.2026), `backend: "real"`, mit
`walk`-Kommandos und 10-Hz-Zustand dazwischen. Gemessen am Tempo, das der
Roboter selbst meldet (`velocity`, odom, in den Körperrahmen gedreht).

Was gemessen wird:
- SPRÜNGE: Anfahren aus dem Stand und Anhalten nach `stop`, je eine Achse.
  Angepasst wird Totzeit plus Glied erster Ordnung (die Anstiegszeit hängt
  kaum vom Sollwert ab — eine feste Beschleunigung wie bei `move()` passt
  nicht). Die Zeiten zählen vom Kommando-EREIGNIS des Laptops bis zum
  GEMELDETEN Tempo; die Übertragung in beide Richtungen steckt also drin —
  genau das, was ein Programm in seiner Schleife erlebt.
- DREHSCHWELLE: Reines Drehen auf der Stelle unter etwa 0.12 rad/s setzt der
  echte Spot NICHT um — er bleibt stehen (über 1700 Takte). Beim Gehen dreht
  er auch langsam. Ob die Schwelle unmittelbar nach dem Gehen gilt, ist mit
  24 Takten nicht zu sagen; das Modell wendet sie immer an.
- TEMPOANTEIL: Anteil des Sollwerts, der in Haltephasen (≥ 2 s gleiches
  Kommando, ab 1.5 s) erreicht wird. Bei 0.2 m/s rund 85 %, bei 0.8 m/s 100 %.

Das Modell daraus (`Folger`): jedes Kommando wirkt nach der LATENZ (Median
der Totzeit beim Anhalten, in Senderichtung geordnet); aus dem Stand kommt der
ANLAUF dazu (Totzeit beim Anfahren minus Latenz — der erste Schritt); danach
nähert sich das Tempo je Gruppe (Gehen, Drehen) mit eigener Zeitkonstante,
schneller beim Anhalten als beim Anfahren.

NICHT gemessen und nicht erfunden: eine Schwelle fürs Gehen unter 0.15 m/s
(es gibt keine Kommandos darunter — `gemessen()` sagt es), das Gierzittern
(gemessen 0.02 rad/s bei 3–5 Hz, als Winkel 0.06°: ein Drittel Pixel bei
330 px Brennweite — bewusst weggelassen), Seitwärtsfahrt (5 Haltephasen).

Liest ausschliesslich. In die Lauf-Verzeichnisse wird nichts geschrieben.
"""

import argparse
import json
import math
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from spotlab.kalibrierung.antwort import _median, _zeilen

DATEI = Path(__file__).parent / "daten" / "tempoantwort.json"

ECHTE_BACKENDS = ("real",)
# Wie lange ein walk-Kommando gilt -- dieselbe Zahl wie `api/motion.py`
# (KOMMANDO_GUELTIGKEIT_S); ein Test haelt beide zusammen. Kein Import: `api`
# zieht bosdyn herein, und dieses Modul liest nur Dateien.
GUELTIG_S = 1.0

RUHE_S = 1.5             # so lange kein Fahrkommando vor einem Anfahren
HALTEN_S = 1.5           # so lange muss das erste Kommando gleich bleiben
MIN_SPRUNG = 0.15        # kleinere Sollwerte verschwinden im Gangpendeln
FENSTER_AN = (-0.3, 2.5)
FENSTER_AB = (-1.0, 2.0)
NACH_STOPP_RUHE_S = 2.0
MIN_PROBEN = 15
TOTZEITEN = [i / 100 for i in range(0, 46)]
ZEITKONSTANTEN = [i / 100 for i in range(2, 81)]

DREH_VERZUG_S = 0.3      # so spaet wirkt ein Kommando (Totzeit beim Anfahren)
DREH_STABIL_S = 1.0      # so lange gleich, sonst misst man den Uebergang
DREH_OHNE_GEHEN_S = 2.0  # so lange vorher keine Fahrt
MIN_DREHPROBEN = 20      # Stufen mit weniger Takten zaehlen nicht fuer die Schwelle

HALT_S = 2.0
HALT_AB_S = 1.5
MIN_HALTE = 5

GRUPPEN = ("gehen", "gehen", "drehen")
RUHE_EPS = 1e-4


# ---------------------------------------------------------------- Rohdaten


def _befehle(ereignisse):
    out = []
    for satz in ereignisse:
        d = satz.get("daten") or {}
        if satz.get("art") != "kommando" or d.get("name") not in ("walk", "stop", "sit", "stand"):
            continue
        out.append((float(satz["t"]), d["name"], float(d.get("vx", 0.0)),
                    float(d.get("vy", 0.0)), float(d.get("wz", 0.0))))
    return sorted(out)


def _tempo(zustand):
    """[(t, vx, vy, wz)] im Koerperrahmen aus `velocity` (odom) und der Gier."""
    out = []
    for s in zustand:
        d = s.get("daten") or {}
        if d.get("pose") is None or d.get("velocity") is None:
            continue
        yaw = float(d["pose"][2])
        vx, vy, wz = (float(v) for v in d["velocity"][:3])
        c, sn = math.cos(yaw), math.sin(yaw)
        out.append((float(s["t"]), c * vx + sn * vy, -sn * vx + c * vy, wz))
    return sorted(out)


def _faehrt(b):
    return b[1] == "walk" and (abs(b[2]) + abs(b[3]) + abs(b[4])) > 1e-9


def _abschnitte(befehle):
    """Zusammenhaengende Fahrten: Listen von walk-Kommandos ohne Luecke > GUELTIG_S."""
    abschnitte, aktuell = [], None
    for b in befehle:
        if _faehrt(b):
            if aktuell and b[0] - aktuell[-1][0] <= GUELTIG_S:
                aktuell.append(b)
            else:
                if aktuell:
                    abschnitte.append(aktuell)
                aktuell = [b]
        elif aktuell:
            abschnitte.append(aktuell)
            aktuell = None
    if aktuell:
        abschnitte.append(aktuell)
    return abschnitte


def _achse(b):
    """Index der einzigen bewegten Achse, sonst None."""
    bewegt = [i for i in range(3) if abs(b[2 + i]) > 1e-9]
    return bewegt[0] if len(bewegt) == 1 else None


def _pt1(tt, totzeit, tau, steigend):
    x = max(0.0, tt - totzeit)
    f = 1.0 - math.exp(-x / tau)
    return f if steigend else 1.0 - f


def _anpassen(proben, steigend, endwert):
    """Totzeit und Zeitkonstante per Gitter (kleinste Quadrate)."""
    best = None
    for td in TOTZEITEN:
        for tau in ZEITKONSTANTEN:
            rest = sum((endwert * _pt1(t, td, tau, steigend) - v) ** 2 for t, v in proben)
            if best is None or rest < best[0]:
                best = (rest, td, tau)
    return best[1], best[2]


def _lies(lauf_dir):
    lauf_dir = Path(lauf_dir)
    meta = json.loads((lauf_dir / "lauf.json").read_text(encoding="utf-8"))
    befehle = _befehle(_zeilen(lauf_dir / "ereignisse.jsonl"))
    tempo = _tempo(_zeilen(lauf_dir / "zustand.jsonl"))
    return meta.get("id", lauf_dir.name), befehle, tempo


def _ende(abschnitt, befehle):
    """(Ende der Fahrt, durch Stopp?) -- Stopp innerhalb der Gueltigkeit oder Ablauf."""
    letzte = abschnitt[-1][0]
    stopps = [b[0] for b in befehle if b[1] in ("stop", "sit") and letzte <= b[0] <= letzte + GUELTIG_S]
    return (min(stopps), True) if stopps else (letzte + GUELTIG_S, False)


def spruenge_aus_lauf(lauf_dir):
    """(Spruenge, Verworfenes): Anfahren aus dem Stand, Anhalten nach stop."""
    name, befehle, tempo = _lies(lauf_dir)
    spruenge, verworfen = [], []
    abschnitte = _abschnitte(befehle)
    ende_vorher = -math.inf
    for n, ab in enumerate(abschnitte):
        t0 = ab[0][0]
        t_ende, durch_stopp = _ende(ab, befehle)
        ruhe = t0 - ende_vorher >= RUHE_S
        ende_vorher = t_ende
        b0, i = ab[0], _achse(ab[0])
        if ruhe and i is not None and abs(b0[2 + i]) >= MIN_SPRUNG and ab[-1][0] - t0 >= HALTEN_S \
                and all(abs(b[2 + i] - b0[2 + i]) < 1e-3 and _achse(b) == i
                        for b in ab if b[0] <= t0 + HALTEN_S):
            proben = [(t - t0, v[i] / b0[2 + i]) for t, *v in tempo
                      if FENSTER_AN[0] <= t - t0 <= FENSTER_AN[1]]
            if len(proben) >= MIN_PROBEN:
                spaet = [v for t, v in proben if t >= 1.5]
                endwert = _median(spaet) if spaet else 1.0
                td, tau = _anpassen(proben, True, endwert)
                spruenge.append({"art": "anfahren", "gruppe": GRUPPEN[i], "soll": round(abs(b0[2 + i]), 3),
                                 "totzeit_s": td, "tau_s": tau, "endwert": round(endwert, 3),
                                 "herkunft": {"lauf": name, "t": round(t0, 3)}})
            else:
                verworfen.append((round(t0, 1), f"Anfahren: nur {len(proben)} Proben"))
        bl, i = ab[-1], _achse(ab[-1])
        weiter = abschnitte[n + 1][0][0] if n + 1 < len(abschnitte) else math.inf
        if durch_stopp and i is not None and weiter - t_ende >= NACH_STOPP_RUHE_S:
            proben = [(t - t_ende, v[i] / bl[2 + i]) for t, *v in tempo
                      if FENSTER_AB[0] <= t - t_ende <= FENSTER_AB[1]]
            vorher = [v for t, v in proben if t < 0]
            if len(proben) >= MIN_PROBEN and vorher and _median(vorher) > 0.5:
                start = _median(vorher)
                td, tau = _anpassen(proben, False, start)
                spruenge.append({"art": "anhalten", "gruppe": GRUPPEN[i], "soll": round(abs(bl[2 + i]), 3),
                                 "totzeit_s": td, "tau_s": tau, "endwert": round(start, 3),
                                 "herkunft": {"lauf": name, "t": round(t_ende, 3)}})
    return spruenge, verworfen


def _befehl_zu(befehle, t):
    """Das zur Zeit t gueltige walk-Kommando (vx, vy, wz), sonst Null."""
    gueltig = (0.0, 0.0, 0.0)
    for b in befehle:
        if b[0] > t:
            break
        gueltig = b[2:5] if b[1] == "walk" and t - b[0] <= GUELTIG_S else (0.0, 0.0, 0.0)
    return gueltig


def drehproben_aus_lauf(lauf_dir):
    """[(|wz| befohlen, erreicht/befohlen)] je Takt mit reinem Drehkommando.

    Das Kommando muss DREH_STABIL_S gleich gewesen sein und wirkt um
    DREH_VERZUG_S verzoegert; davor DREH_OHNE_GEHEN_S keine Fahrt.
    """
    _, befehle, tempo = _lies(lauf_dir)
    return drehproben(befehle, tempo)


def drehproben(befehle, tempo):
    """Wie `drehproben_aus_lauf`, fuer eine beliebige Tempo-Reihe [(t, vx, vy, wz)]."""
    fahrten = [b[0] for b in befehle if b[1] == "walk" and (abs(b[2]) + abs(b[3])) > 1e-9]
    proben = []
    for t, _vx, _vy, wz in tempo:
        tk = t - DREH_VERZUG_S
        soll = _befehl_zu(befehle, tk)
        if abs(soll[0]) + abs(soll[1]) > 1e-9 or abs(soll[2]) < 0.005:
            continue
        schritte = [tk - DREH_STABIL_S * k / 10 for k in range(11)]
        if any(max(abs(a - b) for a, b in zip(_befehl_zu(befehle, s), soll)) > 0.01 for s in schritte):
            continue
        if any(tk - DREH_OHNE_GEHEN_S <= f <= tk for f in fahrten):
            continue
        proben.append((round(abs(soll[2]), 2), wz / soll[2]))
    return proben


def tempo_aus_lauf(lauf_dir):
    """Haltephasen: gleiches Kommando >= HALT_S, eine Gruppe; Anteil ab HALT_AB_S."""
    name, befehle, tempo = _lies(lauf_dir)
    out = []
    for ab in _abschnitte(befehle):
        laeufe, akt = [], [ab[0]]
        for b in ab[1:]:
            if b[2:5] == akt[0][2:5]:
                akt.append(b)
            else:
                laeufe.append(akt)
                akt = [b]
        laeufe.append(akt)
        for lauf in laeufe:
            a0, a1 = lauf[0][0], lauf[-1][0]
            vx, vy, wz = lauf[0][2:5]
            geht, dreht = math.hypot(vx, vy) > 1e-9, abs(wz) > 1e-9
            if a1 - a0 < HALT_S or geht == dreht:
                continue
            werte = []
            for t, ix, iy, iw in tempo:
                if a0 + HALT_AB_S <= t <= a1:
                    if geht:
                        v = math.hypot(vx, vy)
                        werte.append((ix * vx + iy * vy) / v / v)
                    else:
                        werte.append(iw / wz)
            if len(werte) >= 3:
                out.append({"gruppe": "gehen" if geht else "drehen",
                            "soll": round(math.hypot(vx, vy) if geht else abs(wz), 2),
                            "anteil": round(sum(werte) / len(werte), 4),
                            "herkunft": {"lauf": name, "t": round(a0, 3)}})
    return out


def _ist_lauf(pfad):
    return (pfad / "zustand.jsonl").is_file() and (pfad / "lauf.json").is_file() \
        and (pfad / "ereignisse.jsonl").is_file()


def _laeufe(ziel):
    ziel = Path(ziel)
    if _ist_lauf(ziel):
        return [ziel]
    return sorted(p for p in ziel.iterdir() if p.is_dir() and _ist_lauf(p))


def sammle(*ordner, bis=None):
    """(Kennlinie, Bericht) ueber alle kommandierten Laeufe unter `ordner`.

    `bis`: nur Laeufe, deren Name kleiner ist (Laufnamen beginnen mit dem Datum) --
    fuer eine Kennlinie, die die spaeteren Laeufe nie gesehen hat.
    """
    spruenge, dreh, tempo, bericht = [], {}, [], []
    for o in ordner:
        for lauf in _laeufe(o):
            if bis and lauf.name >= bis:
                continue
            try:
                art = json.loads((lauf / "lauf.json").read_text(encoding="utf-8")).get("backend")
            except (OSError, ValueError):
                art = None
            if art not in ECHTE_BACKENDS:
                bericht.append(f"{lauf.name}: übersprungen (backend={art!r})")
                continue
            s, verworfen = spruenge_aus_lauf(lauf)
            d = drehproben_aus_lauf(lauf)
            h = tempo_aus_lauf(lauf)
            spruenge += s
            tempo += h
            for soll, anteil in d:
                dreh.setdefault(soll, []).append(anteil)
            if s or d or h:
                bericht.append(f"{lauf.name}: {len(s)} Sprünge, {len(d)} Drehproben, "
                               f"{len(h)} Haltephasen" + (f", verworfen {len(verworfen)}" if verworfen else ""))
    kennlinie = {
        "fassung": 1,
        "spruenge": spruenge,
        "drehschwelle": [{"soll_rad_s": s, "proben": len(v), "anteil": round(_median(v), 4)}
                         for s, v in sorted(dreh.items())],
        "tempo": tempo,
    }
    return kennlinie, bericht


# ------------------------------------------------------------------ Datei


def schreibe(kennlinie, ziel=DATEI, bemerkung=""):
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    inhalt = {
        **kennlinie,
        "erzeugt": datetime.now(UTC).isoformat(),
        "bemerkung": bemerkung,
        "hinweis": (
            "Antwort des echten Spot auf walk()-Kommandos: Totzeit und Zeitkonstante "
            "beim Anfahren und Anhalten, Drehschwelle auf der Stelle, Tempoanteil in "
            "Haltephasen. Gemessen am gemeldeten Tempo; Zeiten ab dem Kommando-Ereignis."
        ),
    }
    ziel.write_text(json.dumps(inhalt, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return ziel


def lade(pfad=None):
    """Die mitgelieferte Kennlinie. Wirft, wenn sie fehlt."""
    return json.loads(Path(pfad or DATEI).read_text(encoding="utf-8"))


# ----------------------------------------------------------------- Modell


def _interpoliere(tabelle, x):
    if not tabelle:
        return 1.0
    if x <= tabelle[0][0]:
        return tabelle[0][1]
    if x >= tabelle[-1][0]:
        return tabelle[-1][1]
    for (x0, y0), (x1, y1) in zip(tabelle, tabelle[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return tabelle[-1][1]


class Tempoantwort:
    """Parameter aus der Kennlinie: Latenz, Anlauf, Zeitkonstanten, Schwelle, Anteil."""

    def __init__(self, kennlinie):
        spruenge = kennlinie["spruenge"]

        def werte(art, feld, gruppe=None):
            return [s[feld] for s in spruenge if s["art"] == art and (gruppe is None or s["gruppe"] == gruppe)]

        for art in ("anfahren", "anhalten"):
            for gruppe in ("gehen", "drehen"):
                if not werte(art, "tau_s", gruppe):
                    raise ValueError(f"Die Tempokennlinie braucht Sprünge '{art}' für '{gruppe}'.")
        self.latenz_s = _median(werte("anhalten", "totzeit_s"))
        self.anlauf_s = max(0.0, _median(werte("anfahren", "totzeit_s")) - self.latenz_s)
        self.tau = {g: (_median(werte("anfahren", "tau_s", g)), _median(werte("anhalten", "tau_s", g)))
                    for g in ("gehen", "drehen")}
        self.drehschwelle_rad_s = self._schwelle(kennlinie.get("drehschwelle", []))
        self.anteil = {}
        for gruppe in ("gehen", "drehen"):
            stufen = {}
            for p in kennlinie.get("tempo", []):
                if p["gruppe"] == gruppe:
                    stufen.setdefault(round(p["soll"], 2), []).append(p["anteil"])
            self.anteil[gruppe] = sorted((s, _median(v)) for s, v in stufen.items() if len(v) >= MIN_HALTE)
        self.zahlen = {"spruenge": len(spruenge),
                       "drehproben": sum(b["proben"] for b in kennlinie.get("drehschwelle", [])),
                       "haltephasen": len(kennlinie.get("tempo", []))}

    @classmethod
    def sofort(cls):
        """Die alte Annahme: kommandiert IST erreicht, sofort, ohne Schwelle.

        Nur fuer Pruefungen, die etwas ANDERES als die Antwort messen -- die
        Wiedergabe des Gangs (G11) oder die Mechanik der Zeitintegration. Ein
        Sim fuer Programme nimmt die gemessene Kennlinie.
        """
        null = [{"art": a, "gruppe": g, "soll": 1.0, "totzeit_s": 0.0, "tau_s": 1e-9, "endwert": 1.0}
                for a in ("anfahren", "anhalten") for g in ("gehen", "drehen")]
        return cls({"fassung": 1, "spruenge": null, "drehschwelle": [], "tempo": []})

    @staticmethod
    def _schwelle(stufen):
        """Mitte zwischen der letzten Stufe, die nicht dreht, und der ersten, ab der alle drehen."""
        gut = sorted((b["soll_rad_s"], b["anteil"]) for b in stufen if b["proben"] >= MIN_DREHPROBEN)
        if not gut:
            return 0.0
        ab = None
        for k in range(len(gut) - 1, -1, -1):
            if gut[k][1] < 0.5:
                break
            ab = k
        if ab is None:
            raise ValueError("Keine Drehstufe, ab der Spot dreht: die Drehschwelle ist nicht bestimmbar.")
        if ab == 0:
            return 0.0
        return (gut[ab - 1][0] + gut[ab][0]) / 2.0

    def ziel(self, vx, vy, wz):
        """((vx, vy, wz) wie der Roboter sie umsetzt, unter der Drehschwelle?)."""
        v = math.hypot(vx, vy)
        if v < 1e-9 and 0.0 < abs(wz) < self.drehschwelle_rad_s:
            return (0.0, 0.0, 0.0), True
        fv = _interpoliere(self.anteil["gehen"], v) if v > 1e-9 else 1.0
        fw = _interpoliere(self.anteil["drehen"], abs(wz)) if abs(wz) > 1e-9 else 1.0
        return (vx * fv, vy * fv, wz * fw), False

    def gemessen(self, vx, vy, wz):
        """Liegt das Kommando im vermessenen Bereich des Tempoanteils?"""
        def drin(tabelle, x):
            return x < 1e-9 or (tabelle and tabelle[0][0] - 1e-9 <= x <= tabelle[-1][0] + 1e-9)

        v = math.hypot(vx, vy)
        if v < 1e-9 and abs(wz) < self.drehschwelle_rad_s:
            return True
        return bool(drin(self.anteil["gehen"], v) and drin(self.anteil["drehen"], abs(wz)))

    def beschreibung(self):
        return {
            "latenz_s": round(self.latenz_s, 3),
            "anlauf_s": round(self.anlauf_s, 3),
            "tau_gehen_s": [round(t, 3) for t in self.tau["gehen"]],
            "tau_drehen_s": [round(t, 3) for t in self.tau["drehen"]],
            "drehschwelle_rad_s": round(self.drehschwelle_rad_s, 3),
            "tempoanteil_gehen": [[s, round(a, 3)] for s, a in self.anteil["gehen"]],
            "tempoanteil_drehen": [[s, round(a, 3)] for s, a in self.anteil["drehen"]],
            **self.zahlen,
        }


def lade_modell(pfad=None):
    return Tempoantwort(lade(pfad))


class Folger:
    """Das Ist-Tempo auf dem Weg zum Kommando: Latenz, Anlauf, erste Ordnung.

    `befehl(t, ziel)` merkt ein Kommando vor (`ziel` schon durch `ziel()`),
    `schritt(t, dt)` schreibt das Ist-Tempo von t nach t+dt fort. Kommandos
    wirken in der Reihenfolge, in der sie kamen. Kein Uhrzugriff: die Zeit
    bringt der Aufrufer mit.
    """

    def __init__(self, modell, ist=(0.0, 0.0, 0.0)):
        self._m = modell
        self.zuruecksetzen(ist)

    def zuruecksetzen(self, ist=(0.0, 0.0, 0.0)):
        self.ist = tuple(float(v) for v in ist)
        self._ziel = self.ist
        self._plan = deque()
        self._anlauf_bis = None

    @property
    def ruht(self):
        return not self._plan and self._ziel == (0.0, 0.0, 0.0) and self.ist == (0.0, 0.0, 0.0)

    def befehl(self, t, ziel):
        self._plan.append((t + self._m.latenz_s, tuple(float(v) for v in ziel)))

    def naechstes_ereignis(self):
        """Wann sich als Naechstes etwas aendert (Kommando wirkt, Anlauf endet) -- oder None.

        Der Aufrufer teilt seine Schritte dort: sonst wirkte ein Kommando erst am
        Anfang des naechsten Schritts, und der Verlauf hinge davon ab, wie oft
        jemand nach dem Zustand fragt.
        """
        zeiten = [z for z in (self._plan[0][0] if self._plan else None, self._anlauf_bis) if z is not None]
        return min(zeiten) if zeiten else None

    def schritt(self, t, dt):
        while self._plan and self._plan[0][0] <= t + 1e-9:
            wirksam, self._ziel = self._plan.popleft()
            if self._ziel == (0.0, 0.0, 0.0):
                self._anlauf_bis = None
            elif self.ist == (0.0, 0.0, 0.0) and self._anlauf_bis is None:
                self._anlauf_bis = wirksam + self._m.anlauf_s     # der erste Schritt
        ab = t
        if self._anlauf_bis is not None:
            if t + dt <= self._anlauf_bis:
                return self.ist
            ab = max(t, self._anlauf_bis)
            self._anlauf_bis = None
        dauer = t + dt - ab
        neu = []
        for i, gruppe in enumerate(GRUPPEN):
            auf, runter = self._m.tau[gruppe]
            z, x = self._ziel[i], self.ist[i]
            tau = auf if (abs(z) > abs(x) or z * x < 0) else runter
            x += (z - x) * (1.0 - math.exp(-dauer / tau))
            if z == 0.0 and abs(x) < RUHE_EPS:
                x = 0.0
            neu.append(x)
        self.ist = tuple(neu)
        return self.ist


# -------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ordner", nargs="+", help="Läufe oder Ordner mit Läufen")
    ap.add_argument("--ziel", default=str(DATEI))
    ap.add_argument("--bemerkung", default="")
    ap.add_argument("--probe", action="store_true", help="nur anzeigen, nichts schreiben")
    ap.add_argument("--bis", default=None, help="nur Laeufe, deren Name kleiner ist (Datum)")
    args = ap.parse_args(argv)
    for o in args.ordner:
        if not Path(o).is_dir():
            print(f"Kein Verzeichnis: {o}", file=sys.stderr)
            return 2
    kennlinie, bericht = sammle(*args.ordner, bis=args.bis)
    for zeile in bericht:
        print(zeile)
    try:
        modell = Tempoantwort(kennlinie)
    except ValueError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    print("\n" + json.dumps(modell.beschreibung(), ensure_ascii=False, indent=1))
    if args.probe:
        print("\n--probe: nichts geschrieben.")
        return 0
    print(f"\ngeschrieben: {schreibe(kennlinie, args.ziel, args.bemerkung)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
