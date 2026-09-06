"""Die Körperantwort auf Kommandos — aus KOMMANDIERTEN Läufen.

    python -m spotlab.kalibrierung.antwort <ordner-mit-laeufen>
    python -m spotlab.kalibrierung.antwort <ordner> --probe   # nur anzeigen

Die Gangkennlinie (`gang.py`) sagt, wie die Beine sich bei einem Tempo
bewegen. Sie sagt NICHT, wie der Roboter auf `move(forward=1.0)` reagiert:
wie schnell er anfährt, welches Reisetempo er sich wählt, wie er bremst. Im
Beobachter-Modus hat niemand kommandiert, dort gibt es diese Kurve nicht.

Seit dem 02.09.2026 gibt es sie: die ersten Läufe aus der spotlab-GUI am
Schul-Spot, `backend: "real"`, mit `move`-Kommando, Rückmeldung und 10-Hz-
Zustand dazwischen. Zwei Fahrten über 1.0 m, eine Drehung um 90°. Wenig —
aber gemessen, und das Modell sagt, wo es darüber hinausgeht.

Was gemessen wird, je Kommando:
- Spitze: 90. Perzentil des geglätteten Tempos (die Gangart lässt |v| im
  Zehntelsekundentakt um ±0.2 m/s pendeln; das Maximum wäre ein Ausreisser)
- Beschleunigung: Steigung der ansteigenden Flanke zwischen 10 % und 80 %
  der Spitze; Verzögerung: dasselbe an der fallenden Flanke
- Dauer: Kommando bis Rückmeldung „angekommen"
- Erreicht: integrierte Strecke bzw. Winkel — die Gegenprobe zum Sollwert

Das Modell daraus ist ein Trapezprofil: mit `a` anfahren, höchstens mit dem
Reisetempo fahren, so bremsen, dass es mit `b` zum Stillstand reicht. Das
Reisetempo ist das GEMESSENE bei 1 m — der echte Spot hat sich 0.65 m/s
gewählt, obwohl der Deckel 0.8 erlaubte. Für andere Strecken ist das eine
Annahme; `bericht()` des Sim zählt solche Ziele als ausserhalb der Messung.
Real-Prozedur: `matura-spot/scripts/gates_real.py` hinter Sperrpunkt A1.

Liest ausschliesslich. In die Lauf-Verzeichnisse wird nichts geschrieben.
"""

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DATEI = Path(__file__).parent / "daten" / "antwort.json"

# Nur kommandierte Läufe: ein Beobachter-Lauf hat keine Kommandos, ein
# Trockenlauf erfundene Geschwindigkeiten. Erlaubnisliste wie in aus_laeufen.
ECHTE_BACKENDS = ("real",)

GLAETTUNG = 3                  # Proben im gleitenden Mittel
SPITZE_PERZENTIL = 90
FLANKE_VON, FLANKE_BIS = 0.10, 0.80
NACHLAUF_S = 0.5               # so lange nach der Rückmeldung noch mitlesen
MINDESTPROBEN = 6
# Ein Ziel gilt als gemessen, wenn es innerhalb dieser Toleranz an einem
# gemessenen Sollwert liegt.
TOLERANZ = 0.10


@dataclass
class Antwortpunkt:
    """Die Antwort auf EIN Kommando."""

    art: str                   # "fahrt" | "drehung"
    soll: float                # kommandierte Strecke (m) bzw. Winkel (grad)
    dauer_s: float             # Kommando bis Rückmeldung
    spitze: float              # m/s bzw. rad/s
    beschleunigung: float      # m/s² bzw. rad/s²
    verzoegerung: float
    erreicht: float            # integriert: m bzw. grad
    proben: int
    herkunft: dict = field(default_factory=dict)


# ---------------------------------------------------------------- Rohdaten


def _zeilen(pfad):
    saetze = []
    if not pfad.is_file():
        return saetze
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return saetze


def _kommandos(ereignisse):
    """[(t_kommando, felder, t_rueckmeldung)] je `move`."""
    gefunden = []
    offen = None
    for satz in ereignisse:
        daten = satz.get("daten") or {}
        if satz.get("art") == "kommando" and daten.get("name") == "move":
            offen = (float(satz["t"]), daten)
        elif satz.get("art") == "rückmeldung" and daten.get("name") == "move" and offen:
            gefunden.append((offen[0], offen[1], float(satz["t"])))
            offen = None
    return gefunden


def _glaette(werte, n=GLAETTUNG):
    if n <= 1 or len(werte) < n:
        return list(werte)
    halb = n // 2
    return [
        sum(werte[max(0, i - halb):i + halb + 1]) / len(werte[max(0, i - halb):i + halb + 1])
        for i in range(len(werte))
    ]


def _perzentil(werte, p):
    geordnet = sorted(werte)
    k = (len(geordnet) - 1) * p / 100.0
    unten, oben = int(math.floor(k)), int(math.ceil(k))
    return geordnet[unten] + (geordnet[oben] - geordnet[unten]) * (k - unten)


def _rampe(ts, vs, spitze, steigend):
    """Steigung zwischen 10 % und 80 % der Spitze — Anfahren oder Bremsen."""
    von, bis = FLANKE_VON * spitze, FLANKE_BIS * spitze
    if steigend:
        i_von = next((i for i, v in enumerate(vs) if v >= von), None)
        i_bis = next((i for i, v in enumerate(vs) if v >= bis), None)
    else:
        i_bis = next((i for i in range(len(vs) - 1, -1, -1) if vs[i] >= bis), None)
        i_von = next((i for i in range(len(vs) - 1, -1, -1) if vs[i] >= von), None)
        i_von, i_bis = i_bis, i_von        # zeitlich: erst 80 %, dann 10 %
    if i_von is None or i_bis is None or i_bis <= i_von:
        return None
    dt = ts[i_bis] - ts[i_von]
    if dt <= 0:
        return None
    return abs(vs[i_bis] - vs[i_von]) / dt


def _integral(ts, vs):
    return sum((ts[i + 1] - ts[i]) * (vs[i] + vs[i + 1]) / 2.0 for i in range(len(ts) - 1))


def punkte_aus_lauf(lauf_dir):
    """(Antwortpunkte, Verworfenes) aus einem kommandierten Lauf."""
    lauf_dir = Path(lauf_dir)
    meta = json.loads((lauf_dir / "lauf.json").read_text(encoding="utf-8"))
    ereignisse = _zeilen(lauf_dir / "ereignisse.jsonl")
    zustand = _zeilen(lauf_dir / "zustand.jsonl")
    punkte, verworfen = [], []
    for nummer, (t0, felder, t1) in enumerate(_kommandos(ereignisse), start=1):
        vor, links, dreh = (float(felder.get(k, 0.0))
                            for k in ("forward", "left", "turn_grad"))
        faehrt, dreht = (vor != 0.0 or links != 0.0), dreh != 0.0
        if faehrt == dreht:
            verworfen.append((nummer, "kombiniert oder leer"))
            continue
        art = "fahrt" if faehrt else "drehung"
        proben = [s for s in zustand if t0 <= float(s["t"]) <= t1 + NACHLAUF_S]
        if len(proben) < MINDESTPROBEN:
            verworfen.append((nummer, f"nur {len(proben)} Proben"))
            continue
        ts = [float(s["t"]) for s in proben]
        if art == "fahrt":
            roh = [math.hypot(*(s["daten"].get("velocity") or [0, 0, 0])[:2]) for s in proben]
        else:
            roh = [abs((s["daten"].get("velocity") or [0, 0, 0])[2]) for s in proben]
        vs = _glaette(roh)
        spitze = _perzentil(vs, SPITZE_PERZENTIL)
        if spitze <= 0.0:
            verworfen.append((nummer, "keine Bewegung"))
            continue
        a, b = _rampe(ts, vs, spitze, True), _rampe(ts, vs, spitze, False)
        if a is None or b is None:
            verworfen.append((nummer, "Flanke nicht auflösbar"))
            continue
        erreicht = _integral(ts, roh)
        punkte.append(Antwortpunkt(
            art=art,
            soll=round(math.hypot(vor, links) if faehrt else abs(dreh), 3),
            dauer_s=round(t1 - t0, 3),
            spitze=round(spitze, 4),
            beschleunigung=round(a, 4),
            verzoegerung=round(b, 4),
            erreicht=round(erreicht if faehrt else math.degrees(erreicht), 3),
            proben=len(proben),
            herkunft={
                "lauf": meta.get("id", lauf_dir.name),
                "gestartet": meta.get("gestartet"),
                "backend": meta.get("backend"),
                "kommando": nummer,
                "t_kommando": round(t0, 3),
            },
        ))
    return punkte, verworfen


def _ist_lauf(pfad):
    return (pfad / "zustand.jsonl").is_file() and (pfad / "lauf.json").is_file()


def _laeufe(ziel):
    if _ist_lauf(ziel):
        return [ziel]
    return sorted(p for p in ziel.iterdir() if p.is_dir() and _ist_lauf(p))


def sammle(ordner):
    """(Antwortpunkte, Bericht) über alle kommandierten Läufe unter `ordner`."""
    alle, bericht = [], []
    for lauf in _laeufe(Path(ordner)):
        try:
            art = json.loads((lauf / "lauf.json").read_text(encoding="utf-8")).get("backend")
        except (OSError, ValueError):
            art = None
        if art not in ECHTE_BACKENDS:
            bericht.append(f"{lauf.name}: übersprungen (backend={art!r})")
            continue
        punkte, verworfen = punkte_aus_lauf(lauf)
        alle.extend(punkte)
        bericht.append(
            f"{lauf.name}: {len(punkte)} Antwortpunkte"
            + (f", verworfen: {', '.join(f'#{n} ({w})' for n, w in verworfen)}"
               if verworfen else "")
        )
    return alle, bericht


# ------------------------------------------------------------------ Datei


def schreibe(punkte, ziel=DATEI, bemerkung=""):
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    inhalt = {
        "fassung": 1,
        "erzeugt": datetime.now(UTC).isoformat(),
        "bemerkung": bemerkung,
        "hinweis": (
            "Antwort des echten Spot auf move()-Kommandos: Anfahren, Reisetempo, "
            "Bremsen. Gemessen nur bei den genannten Sollwerten; für andere "
            "Strecken und Winkel ist das Trapezprofil eine Annahme."
        ),
        "punkte": [asdict(p) for p in sorted(punkte, key=lambda p: (p.art, p.soll))],
    }
    ziel.write_text(
        json.dumps(inhalt, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    return ziel


def lade(pfad=None):
    """Die mitgelieferte Antwortkennlinie. Wirft, wenn sie fehlt."""
    pfad = Path(pfad) if pfad else DATEI
    return json.loads(pfad.read_text(encoding="utf-8"))


# ----------------------------------------------------------------- Modell


def _median(werte):
    geordnet = sorted(werte)
    n = len(geordnet)
    return geordnet[n // 2] if n % 2 else (geordnet[n // 2 - 1] + geordnet[n // 2]) / 2.0


class Antwortmodell:
    """Trapezprofil aus den gemessenen Antwortpunkten.

    tempo(jetzt, rest, dt, deckel): das nächste Tempo — steigt mit `a`, fährt
    höchstens das Reisetempo (und nie über den Deckel), und bremst so, dass es
    mit `b` gerade zum Stillstand reicht: v ≤ sqrt(2·b·rest). Ohne
    Zeitbuchführung, deterministisch, für Fahrt und Drehung dieselbe Regel.
    """

    def __init__(self, kennlinie):
        punkte = kennlinie["punkte"]
        self.fahrten = [p for p in punkte if p["art"] == "fahrt"]
        self.drehungen = [p for p in punkte if p["art"] == "drehung"]
        if not self.fahrten or not self.drehungen:
            raise ValueError("Die Antwortkennlinie braucht Fahrt- UND Dreh-Punkte.")
        self.a_fahrt = _median([p["beschleunigung"] for p in self.fahrten])
        self.b_fahrt = _median([p["verzoegerung"] for p in self.fahrten])
        self.v_fahrt = _median([p["spitze"] for p in self.fahrten])
        self.a_dreh = _median([p["beschleunigung"] for p in self.drehungen])
        self.b_dreh = _median([p["verzoegerung"] for p in self.drehungen])
        self.w_dreh = _median([p["spitze"] for p in self.drehungen])

    @property
    def gemessene_strecken_m(self):
        return sorted({p["soll"] for p in self.fahrten})

    @property
    def gemessene_winkel_grad(self):
        return sorted({p["soll"] for p in self.drehungen})

    @staticmethod
    def _naechstes(jetzt, rest, dt, a, b, reise, deckel):
        ziel = reise if deckel is None or deckel <= 0 else min(reise, deckel)
        bremse = math.sqrt(max(0.0, 2.0 * b * max(rest, 0.0)))
        return max(0.0, min(ziel, jetzt + a * dt, bremse))

    def tempo(self, jetzt, rest_m, dt, deckel=None):
        return self._naechstes(jetzt, rest_m, dt, self.a_fahrt, self.b_fahrt, self.v_fahrt, deckel)

    def drehrate(self, jetzt, rest_rad, dt, deckel=None):
        return self._naechstes(jetzt, rest_rad, dt, self.a_dreh, self.b_dreh, self.w_dreh, deckel)

    def gemessen(self, strecke_m, winkel_grad):
        """Liegt das Ziel bei einem gemessenen Sollwert (±10 %)?"""
        def nahe(wert, gemessene):
            return any(abs(wert - g) <= TOLERANZ * g for g in gemessene)

        faehrt, dreht = strecke_m > 1e-6, abs(winkel_grad) > 1e-6
        if faehrt and dreht:
            return False                         # kombiniert wurde nie gemessen
        if faehrt:
            return nahe(strecke_m, self.gemessene_strecken_m)
        if dreht:
            return nahe(abs(winkel_grad), self.gemessene_winkel_grad)
        return True

    def beschreibung(self):
        return {
            "fahrt": {"a_m_s2": round(self.a_fahrt, 3), "b_m_s2": round(self.b_fahrt, 3),
                      "reisetempo_m_s": round(self.v_fahrt, 3),
                      "gemessen_bei_m": self.gemessene_strecken_m},
            "drehung": {"a_rad_s2": round(self.a_dreh, 3), "b_rad_s2": round(self.b_dreh, 3),
                        "reisetempo_rad_s": round(self.w_dreh, 3),
                        "gemessen_bei_grad": self.gemessene_winkel_grad},
        }


def lade_modell(pfad=None):
    return Antwortmodell(lade(pfad))


# -------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ordner", help="ein Lauf oder ein Ordner mit Läufen")
    ap.add_argument("--ziel", default=str(DATEI))
    ap.add_argument("--bemerkung", default="")
    ap.add_argument("--probe", action="store_true", help="nur anzeigen, nichts schreiben")
    args = ap.parse_args(argv)

    ordner = Path(args.ordner)
    if not ordner.is_dir():
        print(f"Kein Verzeichnis: {ordner}", file=sys.stderr)
        return 2
    punkte, bericht = sammle(ordner)
    for zeile in bericht:
        print(zeile)
    if not punkte:
        print("\nKeine Antwortpunkte gefunden.", file=sys.stderr)
        return 1

    print(f"\n{len(punkte)} Antwortpunkte:")
    print(f"  {'Art':<8}{'Soll':>7}{'Dauer':>7}{'Spitze':>8}{'Anfahrt':>9}{'Bremse':>8}"
          f"{'Erreicht':>10}  Herkunft")
    for p in sorted(punkte, key=lambda p: (p.art, p.soll)):
        print(f"  {p.art:<8}{p.soll:7.2f}{p.dauer_s:7.2f}{p.spitze:8.3f}"
              f"{p.beschleunigung:9.3f}{p.verzoegerung:8.3f}{p.erreicht:10.3f}  "
              f"{p.herkunft['lauf']} #{p.herkunft['kommando']}")
    if args.probe:
        print("\n--probe: nichts geschrieben.")
        return 0
    ziel = schreibe(punkte, args.ziel, args.bemerkung)
    print(f"\ngeschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
