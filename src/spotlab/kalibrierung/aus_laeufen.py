"""Gangkennlinie aus Messfahrten ziehen.

    python -m spotlab.kalibrierung.aus_laeufen <ordner-mit-laeufen>
    python -m spotlab.kalibrierung.aus_laeufen <lauf> --ziel andere.json
    python -m spotlab.kalibrierung.aus_laeufen <ordner> --probe   # nur anzeigen

Liest ausschliesslich. In die Lauf-Verzeichnisse wird nichts geschrieben — sie
sind Forschungsdaten und gehören dem, der sie aufgenommen hat.

Nur echte Läufe zählen: ein Trockenlauf hat erfundene Gelenkwerte, und eine
Kennlinie daraus wäre eine Erfindung, die aussieht wie eine Messung.

Erkannt wird das am `backend` in `lauf.json`. Bis zum 12.08.2026 ging das nicht:
Probe und Messfahrt hiessen beide „beobachter". Eine Probe fiel damals nur
heraus, weil `DryRunBackend` alle Füsse am Boden lässt und damit null Gangzyklen
liefert — sobald das Sim-Backend die Beine bewegt, hätte sie nicht mehr
herausgefallen. Deshalb heisst die Probe jetzt „beobachter-trocken", und diese
Liste ist eine ERLAUBNIS, keine Sperrliste: ein unbekannter Backend-Name wird
übersprungen, nicht durchgelassen.
"""

import argparse
import json
import sys
from pathlib import Path

from spotlab.kalibrierung import gang

ECHTE_BACKENDS = ("beobachter", "real")


def _ist_lauf(pfad):
    return (pfad / "zustand.jsonl").is_file() and (pfad / "lauf.json").is_file()


def _laeufe(ziel):
    if _ist_lauf(ziel):
        return [ziel]
    return sorted(p for p in ziel.iterdir() if p.is_dir() and _ist_lauf(p))


def _backend(lauf):
    try:
        return json.loads((lauf / "lauf.json").read_text(encoding="utf-8")).get("backend")
    except (OSError, ValueError):
        return None


def sammle(ordner, mindestzyklen=gang.MINDESTZYKLEN):
    """(Stützstellen, Bericht) über alle echten Läufe unter `ordner`."""
    alle, bericht = [], []
    for lauf in _laeufe(Path(ordner)):
        art = _backend(lauf)
        if art not in ECHTE_BACKENDS:
            bericht.append(f"{lauf.name}: übersprungen (backend={art!r})")
            continue
        gefunden, verworfen = gang.stuetzstellen_aus_lauf(lauf, mindestzyklen)
        alle.extend(gefunden)
        bericht.append(
            f"{lauf.name}: {len(gefunden)} Stützstellen"
            + (f", verworfen: {', '.join(f'{n} ({w})' for n, w in verworfen)}"
               if verworfen else "")
        )
    return alle, bericht


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ordner", help="ein Lauf oder ein Ordner mit Läufen")
    ap.add_argument("--ziel", default=str(gang.DATEI))
    ap.add_argument("--bemerkung", default="")
    ap.add_argument("--mindestzyklen", type=int, default=gang.MINDESTZYKLEN)
    ap.add_argument("--probe", action="store_true", help="nur anzeigen, nichts schreiben")
    args = ap.parse_args(argv)

    ordner = Path(args.ordner)
    if not ordner.is_dir():
        print(f"Kein Verzeichnis: {ordner}", file=sys.stderr)
        return 2

    stuetzstellen, bericht = sammle(ordner, args.mindestzyklen)
    for zeile in bericht:
        print(zeile)
    if not stuetzstellen:
        print("\nKeine brauchbaren Stützstellen gefunden.", file=sys.stderr)
        return 1

    print(f"\n{len(stuetzstellen)} Stützstellen:")
    kopf = f"  {'Tempo':>7}{'Drehrate':>10}{'Zyklus':>8}{'Muster':>10}{'Hoehe':>7}{'Zyklen':>8}  Herkunft"
    print(kopf)
    for s in sorted(stuetzstellen, key=lambda s: (abs(s.drehrate_rad_s), s.tempo_m_s)):
        zyklus = f"{s.zyklusdauer_s:.2f}" if s.zyklusdauer_s else "-"
        hoehe = f"{s.hoehe_m:.3f}" if s.hoehe_m else "-"
        print(f"  {s.tempo_m_s:7.3f}{s.drehrate_rad_s:10.3f}{zyklus:>8}{s.muster:>10}"
              f"{hoehe:>7}{s.zyklen:8}  {s.herkunft['fenster']}")

    if args.probe:
        print("\n--probe: nichts geschrieben.")
        return 0

    ziel = gang.schreibe(stuetzstellen, args.ziel, args.bemerkung)
    print(f"\ngeschrieben: {ziel}  ({ziel.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
