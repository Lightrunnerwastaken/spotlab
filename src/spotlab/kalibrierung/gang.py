"""Gangkennlinie aus echten Messfahrten herausziehen.

Eine Stützstelle je Messfenster: bei WELCHEM erreichten Tempo bewegt der Spot
seine Beine WIE. Der gemittelte Gangzyklus — zwölf Gelenkbahnen über die
normierte Phase — ist der Kern; Duty, Kadenz, Phasenlage und Standhöhe stehen
daneben.

Die x-Achse ist das ERREICHTE Tempo, nie das beabsichtigte. Beim Beobachter-Modus
kommandiert niemand; „Ziel 0.60" ist die Absicht des Bedieners, gefahren wurden
0.53. Ein Sim, der auf die Absicht kalibriert wäre, liefe systematisch zu
schnell.

Nicht enthalten und bewusst nicht: irgendeine Physik. Das hier ist eine
Interpolation von Messungen. Was zwischen den Stützstellen liegt, wird
gemittelt; was ausserhalb liegt, gibt es nicht.
"""

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Stützstellen je Gangzyklus. 25 ist kein Zufall: bei der langsamsten
# vermessenen Gangart dauert ein Zyklus 2.2 s, bei 33 Hz also rund 70
# Abtastungen — 25 Phasenpunkte glätten das, ohne die Form zu verlieren. Bei der
# schnellsten (0.81 s, rund 27 Abtastungen) wird nicht mehr behauptet, als
# gemessen wurde.
PHASENPUNKTE = 25

# Weniger Zyklen als das, und ein Mittelwert behauptet mehr, als er weiss.
MINDESTZYKLEN = 3

# Zyklen ausserhalb dieses Bandes um den MEDIAN werden verworfen.
#
# Nicht willkürlich: die Kontakterkennung verpasst gelegentlich einen Aufsetzer,
# dann verschmelzen zwei Zyklen zu einem von rund doppelter Dauer. Umgekehrt
# erzeugt ein prellender Fuss einen halben. Gemessen an B2-7 (12.08.2026, Trab
# bei 0.51 m/s): Median 0.765 s, 26 Zyklen zwischen 0.65 und 0.81 — und vier bei
# 1.17 bis 1.54, also glatt das Doppelte.
#
# Das Band muss beides ausschliessen und echte Kadenzschwankung durchlassen.
# 0.7 bis 1.4 hat zu 0.5x und 2.0x jeweils Abstand.
#
# Warum das mehr ist als Kosmetik an einer Streuungszahl: ein verschmolzener
# Zyklus wird auf dieselbe Phase 0..1 normiert wie ein echter und dann
# mitgemittelt. Er zieht zwei Schritte in den Platz von einem — die gemittelte
# Gelenkbahn wird dadurch nicht ungenauer, sondern falsch.
ZYKLUS_BAND = (0.7, 1.4)

# Ein Messfenster wird in Abschnitte von so vielen Gangzyklen zerlegt, statt als
# Ganzes gemittelt zu werden.
#
# Grund: der Fensterschnitt mittelt Anfahren, Suchen und Anhalten mit. B2-1 im
# Lauf 20260812T111801Z hatte einen Schnitt von 0.054 m/s — die einzelnen
# Abschnitte darin lagen zwischen 0.08 und 0.77. Die Stützstelle behauptete eine
# langsame Gangart, die es nie gab, und war zugleich der unterste Punkt der
# Kennlinie.
#
# Fünf Zyklen sind der Kompromiss: genug zum Mitteln (MINDESTZYKLEN ist 3), kurz
# genug, dass das Tempo darin steht — bei 0.8 s Zyklusdauer sind das vier
# Sekunden.
SEGMENT_ZYKLEN = 5

# Stetigkeit eines Abschnitts: die beiden Hälften müssen sich einig sein.
#
# Ein Abschnitt, der eine Beschleunigung überspannt, verschmiert die gemittelte
# Gelenkbahn genauso wie ein verschmolzener Zyklus. 15 % lässt natürliche
# Kadenzschwankung durch und schliesst Anfahren aus.
#
# VOR dem Blick in die Daten festgelegt. Ein Kriterium, das man nachträglich so
# dreht, bis die Kennlinie schön aussieht, misst die eigene Erwartung.
STETIGKEIT = 0.15

DATEI = Path(__file__).parent / "daten" / "gang.json"


@dataclass
class Stuetzstelle:
    """Der Gang bei einem gemessenen Tempo."""

    tempo_m_s: float                 # erreicht, nicht beabsichtigt
    drehrate_rad_s: float            # erreicht
    absicht: dict                    # was der Bediener vorhatte — nur zur Herkunft
    zyklusdauer_s: float
    zyklusdauer_streuung_s: float | None
    duty: list                       # je Bein, Anteil Bodenkontakt
    phasen: list                     # je Bein, Aufsetzphase relativ zum ersten
    muster: str                      # zweitakt | dreitakt | viertakt | unklar
    hoehe_m: float                   # Rumpf über den Füssen, NICHT odom-z
    gelenke: dict                    # name -> PHASENPUNKTE Winkel
    gelenke_streuung: dict           # name -> PHASENPUNKTE Standardabweichungen
    zyklen: int
    herkunft: dict = field(default_factory=dict)


# --------------------------------------------------------------- Beinzuordnung


def bein_zuordnung(saetze):
    """Welcher Eintrag in `feet` ist welches Bein? Abgeleitet, nicht geraten.

    Die Reihenfolge steht nicht in der Nachricht — `messung/schritt.py` sagt das
    ausdrücklich und vermeidet deshalb Beinnamen. Aus der mittleren Fussposition
    im Körperframe folgt sie aber eindeutig: vorne ist x > 0, links ist y > 0.

    Gibt eine Liste wie ["fl", "fr", "hl", "hr"] zurück, oder None, wenn keine
    Fussdetails vorliegen. None heisst „nicht bestimmbar", nicht „Standardfall".
    """
    summen, anzahl = {}, {}
    for satz in saetze:
        for i, fuss in enumerate(satz.get("feet_detail") or ()):
            pos = (fuss or {}).get("pos")
            if not pos or len(pos) < 2:
                continue
            x, y = summen.get(i, (0.0, 0.0))
            summen[i] = (x + pos[0], y + pos[1])
            anzahl[i] = anzahl.get(i, 0) + 1
    if len(summen) < 4 or any(anzahl.get(i, 0) < 10 for i in range(4)):
        return None
    namen = []
    for i in range(4):
        x, y = summen[i]
        namen.append(("f" if x / anzahl[i] > 0 else "h") + ("l" if y / anzahl[i] > 0 else "r"))
    return namen if len(set(namen)) == 4 else None


# --------------------------------------------------------------- Zyklen


def _kontakte(satz):
    roh = satz.get("feet")
    if roh:
        return [bool(k) for k in roh]
    return [bool((f or {}).get("kontakt")) for f in (satz.get("feet_detail") or ())]


def zyklen_grenzen(saetze, bein=0):
    """Indexpaare (Aufsetzen, nächstes Aufsetzen) des Bezugsbeins.

    Ein Gangzyklus ist von Aufsetzen zu Aufsetzen desselben Fusses definiert —
    dieselbe Konvention wie in `messung/schritt.py`.
    """
    reihe = [_kontakte(s) for s in saetze]
    if not reihe or bein >= len(reihe[0]):
        return []
    fuss = [r[bein] if bein < len(r) else False for r in reihe]
    aufsetzer = [i for i in range(1, len(fuss)) if fuss[i] and not fuss[i - 1]]
    return list(zip(aufsetzer, aufsetzer[1:]))


def _interpoliere(phasen, werte, punkte):
    """Werte auf ein gleichmässiges Phasenraster legen, linear.

    `phasen` läuft von 0 bis 1 und ist aufsteigend. Das Raster nimmt die Punkte
    k/punkte, also 0 einschliesslich und 1 ausschliesslich — der letzte Punkt
    eines Zyklus IST der erste des nächsten und zählte sonst doppelt.
    """
    raster, j = [], 0
    for k in range(punkte):
        p = k / punkte
        while j + 2 < len(phasen) and phasen[j + 1] < p:
            j += 1
        p0, p1 = phasen[j], phasen[j + 1]
        w0, w1 = werte[j], werte[j + 1]
        anteil = 0.0 if p1 <= p0 else (p - p0) / (p1 - p0)
        raster.append(w0 + max(0.0, min(1.0, anteil)) * (w1 - w0))
    return raster


def _median(werte):
    geordnet = sorted(werte)
    n = len(geordnet)
    if not n:
        return None
    return geordnet[n // 2] if n % 2 else (geordnet[n // 2 - 1] + geordnet[n // 2]) / 2


def brauchbare_zyklen(saetze, bein=0):
    """Zyklusgrenzen ohne verschmolzene und ohne halbierte.

    Gibt (grenzen, dauern, verworfen) zurück — die Zahl der verworfenen gehört
    in die Herkunft, sonst sieht eine gesäuberte Kennlinie sauberer aus, als
    die Messung war.
    """
    roh = zyklen_grenzen(saetze, bein)
    paare = []
    for von, bis in roh:
        t0, t1 = saetze[von].get("t_robot"), saetze[bis].get("t_robot")
        if t0 is None or t1 is None or t1 <= t0:
            continue
        paare.append(((von, bis), t1 - t0))
    if len(paare) < MINDESTZYKLEN:
        return [g for g, _ in paare], [d for _, d in paare], len(roh) - len(paare)

    mitte = _median([d for _, d in paare])
    unten, oben = ZYKLUS_BAND[0] * mitte, ZYKLUS_BAND[1] * mitte
    behalten = [(g, d) for g, d in paare if unten <= d <= oben]
    return (
        [g for g, _ in behalten],
        [d for _, d in behalten],
        len(roh) - len(behalten),
    )


def _bewegung(saetze, von, bis):
    """(Tempo, Drehrate) zwischen zwei Abtastungen, aus der Pose."""
    a, b = saetze[von], saetze[bis]
    dt = (b.get("t_robot") or 0.0) - (a.get("t_robot") or 0.0)
    if dt <= 0 or not a.get("pose") or not b.get("pose"):
        return None, None
    tempo = math.hypot(b["pose"][0] - a["pose"][0], b["pose"][1] - a["pose"][1]) / dt
    dyaw = (b["pose"][2] - a["pose"][2] + math.pi) % (2 * math.pi) - math.pi
    return tempo / 1.0, dyaw / dt


def _gieren(saetze, von, bis):
    """Aufsummierter Gierwinkel — der Umschlag bei ±pi darf nicht durchschlagen."""
    summe = 0.0
    for i in range(von, bis):
        a, b = saetze[i].get("pose"), saetze[i + 1].get("pose")
        if not a or not b:
            continue
        summe += (b[2] - a[2] + math.pi) % (2 * math.pi) - math.pi
    return summe


def segmente(saetze, bein=0, zyklen=SEGMENT_ZYKLEN):
    """Stetige Abschnitte von je `zyklen` Gangzyklen.

    Gibt Tupel (grenzen, tempo, drehrate) zurück. Unstetige Abschnitte fallen
    weg — nicht, weil ihr Tempo unpassend wäre, sondern weil eine gemittelte
    Gelenkbahn über eine Beschleunigung hinweg keine Gangart beschreibt.
    """
    alle, _, _ = brauchbare_zyklen(saetze, bein)
    gefunden = []
    for i in range(0, len(alle) - zyklen + 1, zyklen):
        gruppe = alle[i:i + zyklen]
        von, bis = gruppe[0][0], gruppe[-1][1]
        tempo, _ = _bewegung(saetze, von, bis)
        if tempo is None:
            continue
        dauer = saetze[bis]["t_robot"] - saetze[von]["t_robot"]
        drehrate = _gieren(saetze, von, bis) / dauer if dauer > 0 else 0.0

        mitte = gruppe[len(gruppe) // 2]
        erst, _ = _bewegung(saetze, von, mitte[1])
        zweit, _ = _bewegung(saetze, mitte[0], bis)
        if erst is None or zweit is None:
            continue
        if abs(erst - zweit) > STETIGKEIT * max(tempo, 1e-6):
            continue
        gefunden.append((gruppe, round(tempo, 4), round(drehrate, 4)))
    return gefunden


def mittlerer_zyklus_aus(saetze, grenzen, punkte=PHASENPUNKTE):
    """Wie `mittlerer_zyklus`, aber über eine vorgegebene Zyklusliste."""
    return _mitteln(saetze, grenzen, punkte)


def mittlerer_zyklus(saetze, bein=0, punkte=PHASENPUNKTE):
    """Gemittelte Gelenkbahnen über die normierte Gangphase.

    Gibt (mittelwerte, streuungen, zyklen) zurück. Jeder Zyklus wird einzeln auf
    die Phase 0..1 normiert und dann gemittelt — sonst verschmierte eine
    schwankende Kadenz die Form.
    """
    grenzen, _, _ = brauchbare_zyklen(saetze, bein)
    return _mitteln(saetze, grenzen, punkte)


def _mitteln(saetze, grenzen, punkte=PHASENPUNKTE):
    if len(grenzen) < MINDESTZYKLEN:
        return {}, {}, len(grenzen)

    namen = sorted((saetze[0].get("joints") or {}).keys())
    if not namen:
        return {}, {}, 0

    gesammelt = {name: [[] for _ in range(punkte)] for name in namen}
    gezaehlt = 0
    for von, bis in grenzen:
        stueck = saetze[von:bis + 1]
        zeiten = [s.get("t_robot") for s in stueck]
        if any(t is None for t in zeiten) or zeiten[-1] <= zeiten[0]:
            continue
        spanne = zeiten[-1] - zeiten[0]
        phasen = [(t - zeiten[0]) / spanne for t in zeiten]
        brauchbar = True
        bahnen = {}
        for name in namen:
            werte = []
            for s in stueck:
                g = (s.get("joints") or {}).get(name)
                if g is None:
                    brauchbar = False
                    break
                werte.append(g["position"])
            if not brauchbar:
                break
            bahnen[name] = _interpoliere(phasen, werte, punkte)
        if not brauchbar:
            continue
        for name, bahn in bahnen.items():
            for k, wert in enumerate(bahn):
                gesammelt[name][k].append(wert)
        gezaehlt += 1

    if gezaehlt < MINDESTZYKLEN:
        return {}, {}, gezaehlt

    mittel, streuung = {}, {}
    for name, spalten in gesammelt.items():
        mittel[name] = [round(sum(s) / len(s), 5) for s in spalten]
        streuung[name] = [
            round(math.sqrt(sum((w - sum(s) / len(s)) ** 2 for w in s) / len(s)), 5)
            for s in spalten
        ]
    return mittel, streuung, gezaehlt


# --------------------------------------------------------------- Kennwerte


def standhoehe(saetze):
    """Rumpf über den Füssen — die Grösse, die `z` NICHT ist.

    `z` in `zustand.jsonl` kommt aus `odom_tform_body` und ist damit relativ zum
    Ursprung des odom-Frames, also dazu, wo der Roboter beim Hochfahren stand.
    Am 12.08.2026 waren das 0.265 m, während der Rumpf tatsächlich 0.514 m über
    den Füssen stand. Für einen Sim ist nur die zweite Zahl brauchbar.
    """
    werte = []
    for satz in saetze:
        zs = [
            (f or {}).get("pos", [0, 0, 0])[2]
            for f in (satz.get("feet_detail") or ())
            if (f or {}).get("kontakt")
        ]
        if zs:
            werte.append(-sum(zs) / len(zs))
    return round(sum(werte) / len(werte), 4) if werte else None


def duty(saetze):
    reihen = [_kontakte(s) for s in saetze]
    reihen = [r for r in reihen if len(r) == 4]
    if not reihen:
        return []
    return [round(sum(r[i] for r in reihen) / len(reihen), 3) for i in range(4)]


# --------------------------------------------------------------- Aus Läufen ziehen


def _saetze_im_fenster(lauf_dir, von_s, bis_s):
    """Abtastungen eines Fensters. Zuordnung über die EMPFANGSZEIT `t` —
    nur sie steht in Ereignissen und Abtastungen auf derselben Uhr
    (dieselbe Regel wie `messung/fenster.py`)."""
    drin = []
    with (Path(lauf_dir) / "zustand.jsonl").open(encoding="utf-8") as datei:
        for zeile in datei:
            zeile = zeile.strip()
            if not zeile:
                continue
            satz = json.loads(zeile)
            t = float(satz.get("t") or 0.0)
            if von_s <= t <= bis_s:
                drin.append(satz.get("daten") or {})
    return drin


def _erreicht(messwerte):
    """Erreichtes Tempo und erreichte Drehrate aus den Fensterkennzahlen."""
    dauer = messwerte.get("dauer_s") or 0.0
    if dauer <= 0:
        return None, None
    tempo = (messwerte.get("netto_versatz_m") or 0.0) / dauer
    dreh = math.radians(messwerte.get("gierwinkel_grad") or 0.0) / dauer
    return round(tempo, 4), round(dreh, 4)


def stuetzstellen_aus_lauf(lauf_dir, mindestzyklen=MINDESTZYKLEN):
    """Je STETIGEM ABSCHNITT eines Messfensters eine Stützstelle.

    Nicht je Fenster: der Fensterschnitt mittelt Anfahren, Suchen und Anhalten
    mit. B2-1 im Lauf 20260812T111801Z hatte einen Schnitt von 0.054 m/s,
    während die Abschnitte darin zwischen 0.08 und 0.77 lagen — eine langsame
    Gangart, die es nie gab, und zugleich der unterste Punkt der Kennlinie.

    WICHTIG für die Auswertung: mehrere Stützstellen aus demselben Fenster sind
    KEINE unabhängigen Messungen. Die Herkunft nennt deshalb Fenster und
    Abschnittsnummer.

    Lesend. Es wird nichts in das Lauf-Verzeichnis geschrieben.
    """
    from spotlab.messung import fenster as fenstermodul
    from spotlab.record.read import read_run

    lauf_dir = Path(lauf_dir)
    lauf = read_run(lauf_dir)
    gefunden, verworfen = [], []
    for f in fenstermodul.fenster(lauf_dir):
        saetze = _saetze_im_fenster(lauf_dir, f.von_s, f.bis_s)
        alle, _, aussortiert = brauchbare_zyklen(saetze)
        stuecke = segmente(saetze)
        if not stuecke:
            grund = (
                f"nur {len(alle)} Zyklen" if len(alle) < SEGMENT_ZYKLEN
                else "kein stetiger Abschnitt"
            )
            verworfen.append((f.name, grund))
            continue

        absicht = {k: v for k, v in f.felder.items() if k.startswith("ziel")}
        schritt = f.messwerte.get("schritt") or {}
        beine = bein_zuordnung(saetze)
        for nummer, (grenzen, tempo, drehrate) in enumerate(stuecke, start=1):
            mittel, streuung, zyklen = mittlerer_zyklus_aus(saetze, grenzen)
            if zyklen < mindestzyklen:
                continue
            von, bis = grenzen[0][0], grenzen[-1][1]
            teil = saetze[von:bis + 1]
            dauern = [
                saetze[b]["t_robot"] - saetze[a]["t_robot"] for a, b in grenzen
            ]
            kadenz = _median(dauern)
            kadenz_streuung = (
                math.sqrt(sum((d - kadenz) ** 2 for d in dauern) / len(dauern))
                if len(dauern) > 1 else None
            )
            gefunden.append(
                Stuetzstelle(
                    tempo_m_s=tempo,
                    drehrate_rad_s=drehrate,
                    absicht=absicht,
                    # Aus den BEHALTENEN Zyklen dieses Abschnitts, nicht aus
                    # `messung/schritt.py`: jenes rechnet über das ganze Fenster
                    # und ist eine wörtliche Kopie in matura-spot — es wird hier
                    # nicht angefasst, sondern nur nicht für diese Zahl benutzt.
                    zyklusdauer_s=round(kadenz, 4) if kadenz else None,
                    zyklusdauer_streuung_s=(
                        round(kadenz_streuung, 4)
                        if kadenz_streuung is not None else None
                    ),
                    duty=duty(teil),
                    # Muster und Phasenlage kommen aus dem GANZEN Fenster: sie
                    # brauchen mehr Zyklen als ein Abschnitt hat.
                    phasen=schritt.get("phasen") or [],
                    muster=schritt.get("muster") or "unklar",
                    hoehe_m=standhoehe(teil),
                    gelenke=mittel,
                    gelenke_streuung=streuung,
                    zyklen=zyklen,
                    herkunft={
                        "lauf": lauf.id,
                        "fenster": f.name,
                        "abschnitt": nummer,
                        "abschnitte_im_fenster": len(stuecke),
                        "gestartet": lauf.gestartet,
                        "backend": lauf.backend,
                        "hz_ist": f.hz_ist,
                        "beine": beine,
                        # Ohne diese Zahl sähe eine gesäuberte Kennlinie
                        # sauberer aus, als die Messung war.
                        "zyklen_verworfen_im_fenster": aussortiert,
                    },
                )
            )
    return gefunden, verworfen


def schreibe(stuetzstellen, ziel=DATEI, bemerkung=""):
    """Kennlinie als JSON. Trägt ihre Herkunft mit — ohne die ist sie wertlos."""
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    geordnet = sorted(stuetzstellen, key=lambda s: (abs(s.drehrate_rad_s), s.tempo_m_s))
    inhalt = {
        "fassung": 1,
        "erzeugt": datetime.now(UTC).isoformat(),
        "phasenpunkte": PHASENPUNKTE,
        "bemerkung": bemerkung,
        "hinweis": (
            "Interpolation von Messungen, keine Physik. Die x-Achse ist das "
            "ERREICHTE Tempo, nicht das beabsichtigte. Ausserhalb der "
            "Stützstellen gibt es keine Aussage."
        ),
        "stuetzstellen": [asdict(s) for s in geordnet],
    }
    ziel.write_text(
        json.dumps(inhalt, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    return ziel


def lade(pfad=None):
    """Die mitgelieferte Kennlinie. Wirft, wenn sie fehlt — ein Sim ohne
    Kalibrierdaten wäre eine Erfindung, kein Ersatz.

    `None` heisst „die mitgelieferte" — nicht als Vorgabewert in der Signatur,
    damit auch ein durchgereichtes `None` (etwa aus einem CLI-Argument) sie
    findet, statt an `Path(None)` zu scheitern."""
    pfad = Path(pfad) if pfad else DATEI
    if not pfad.exists():
        raise FileNotFoundError(
            f"Keine Gangkennlinie unter {pfad}. Sie entsteht aus echten "
            f"Messfahrten mit `python -m spotlab.kalibrierung.aus_laeufen <ordner>`."
        )
    return json.loads(pfad.read_text(encoding="utf-8"))
