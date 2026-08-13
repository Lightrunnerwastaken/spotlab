"""Wie gut gibt das Gangmodell wieder, was gemessen wurde?

DIE FALLE ZUERST. Das Modell ist AUS diesen Daten gebaut. Es gegen dieselben
Daten zu halten misst die Interpolation, nicht die Gültigkeit — man bekäme
einen kleinen Fehler und wüsste nichts. Deshalb gibt es hier zwei getrennte
Prüfungen und eine Negativkontrolle.

1. SELBSTPRÜFUNG (leave-one-out). Eine Stützstelle wird herausgenommen, das
   Modell ohne sie neu gebaut, und dann muss es genau diese Stelle vorhersagen.
   Das beantwortet die Frage, die für den Sim zählt: **wie gut füllt die
   Interpolation eine Lücke?** Gerade dort, wo eine ist — zwischen 0.27 und
   0.45 m/s.

2. HALTEPROBE. Die Abschnitte aus B6 (Treppe) und B7 (Rundgang) sind nie ins
   Modell gegangen: `NUR_MIT_ABSICHT` schliesst sie aus, weil dort niemand ein
   Tempo halten wollte. Sie sind damit echte, ungesehene Messungen — dieselbe
   Maschine, derselbe Tag, aber nicht dieselben Zahlen.

3. NEGATIVKONTROLLE. B6 ist eine TREPPE. Ein Modell, das nur ebenen Gang kennt,
   MUSS dort schlechter sein als auf B7. Ist es das nicht, misst die Metrik
   nicht, was sie behauptet — dann ist nicht das Modell gut, sondern der
   Vergleich blind.

Gemessen wird in Radiant, über die zwölf Gelenkbahnen einer normierten
Gangphase. Kein Urteil, keine Schranke: was ein Fehler bedeutet, entscheidet,
wer ihn benutzt.
"""

import math

from spotlab.kalibrierung.modell import Gangmodell


def _abweichung(modell, stelle):
    """RMS-Abweichung der Gelenkbahnen in rad, je Gelenk und insgesamt."""
    tempo, dreh = stelle["tempo_m_s"], stelle["drehrate_rad_s"]
    punkte = len(next(iter(stelle["gelenke"].values())))
    je_gelenk = {}
    for name, gemessen in stelle["gelenke"].items():
        if name not in modell.gelenknamen:
            continue
        quadrate = []
        for k, wert in enumerate(gemessen):
            vorhergesagt = modell.gelenke(tempo, dreh, k / punkte)[name]
            quadrate.append((vorhergesagt - wert) ** 2)
        je_gelenk[name] = math.sqrt(sum(quadrate) / len(quadrate))
    if not je_gelenk:
        return None
    schlimmstes = max(je_gelenk, key=je_gelenk.get)
    return {
        "rms_rad": round(sum(je_gelenk.values()) / len(je_gelenk), 4),
        "schlimmstes_gelenk": schlimmstes,
        "schlimmstes_rms_rad": round(je_gelenk[schlimmstes], 4),
        "zyklus_ist_s": stelle["zyklusdauer_s"],
        "zyklus_modell_s": round(modell.zyklusdauer(tempo, dreh), 4),
        "ausserhalb": modell.rand(tempo, dreh),
    }


def _ohne(kennlinie, stelle):
    """Dieselbe Kennlinie ohne genau diese Stützstelle."""
    rest = [s for s in kennlinie["stuetzstellen"] if s is not stelle]
    return {**kennlinie, "stuetzstellen": rest}


def selbstpruefung(kennlinie, nur_fahrt=True):
    """Leave-one-out über die Stützstellen, die das Modell benutzt.

    Eine Stelle, die als EINZIGE ihre Gegend abdeckt, ist der interessante
    Fall: ohne sie muss das Modell über eine Lücke hinweg raten. Genau das tut
    der Sim in der Zone 0.27 bis 0.45.
    """
    ergebnisse = []
    for stelle in kennlinie["stuetzstellen"]:
        absicht = stelle.get("absicht") or {}
        if not absicht:
            continue
        if nur_fahrt and "ziel_m_s" not in absicht:
            continue
        try:
            ohne = Gangmodell(_ohne(kennlinie, stelle))
        except ValueError:
            continue                     # letzte Fahrt-Stelle, nichts zu bauen
        abweichung = _abweichung(ohne, stelle)
        if abweichung is None:
            continue
        nachbar = _naechster_abstand(ohne, stelle)
        ergebnisse.append({
            "tempo_m_s": stelle["tempo_m_s"],
            "fenster": stelle["herkunft"]["fenster"],
            "abschnitt": stelle["herkunft"]["abschnitt"],
            "abstand_zum_naechsten_m_s": nachbar,
            **abweichung,
        })
    return sorted(ergebnisse, key=lambda e: e["tempo_m_s"])


def _naechster_abstand(modell, stelle):
    """Wie weit ist die naechste verbliebene Stuetzstelle entfernt?

    Ohne diese Zahl ist ein Fehler nicht einzuordnen: eine Vorhersage ueber
    0.17 m/s hinweg darf schlechter sein als eine ueber 0.01.
    """
    tempo = stelle["tempo_m_s"]
    andere = [abs(s["tempo_m_s"] - tempo) for s in modell.fahren]
    return round(min(andere), 4) if andere else None


def lueckenprobe(kennlinie, von, bis):
    """Ein ganzes Tempoband herausnehmen und über die Lücke hinweg vorhersagen.

    Die Selbstprüfung ist für die Frage, die zählt, zu OPTIMISTISCH: eine
    einzelne Stelle zu entfernen, deren Nachbar 0.003 m/s entfernt liegt,
    beweist nichts über eine Lücke von 0.17 m/s. Hier fällt das ganze Band weg,
    und das Modell muss von aussen hineinraten — genau die Lage, in der es
    zwischen 0.27 und 0.45 m/s heute ist.

    Wer wissen will, was der Sim in einer ungemessenen Zone tut, muss diese
    Zone künstlich herstellen. Alles andere ist eine Vermutung.
    """
    drin = [
        s for s in kennlinie["stuetzstellen"]
        if s.get("absicht", {}).get("ziel_m_s") and von <= s["tempo_m_s"] <= bis
    ]
    if not drin:
        return {"band": [von, bis], "stellen": 0, "ergebnisse": []}
    rest = [s for s in kennlinie["stuetzstellen"] if s not in drin]
    try:
        ohne = Gangmodell({**kennlinie, "stuetzstellen": rest})
    except ValueError:
        return {"band": [von, bis], "stellen": len(drin), "ergebnisse": [],
                "hinweis": "ohne dieses Band bleibt keine Fahrt-Stützstelle übrig"}

    ergebnisse = []
    for stelle in drin:
        abweichung = _abweichung(ohne, stelle)
        if abweichung is None:
            continue
        ergebnisse.append({
            "tempo_m_s": stelle["tempo_m_s"],
            "fenster": stelle["herkunft"]["fenster"],
            "abstand_zum_naechsten_m_s": _naechster_abstand(ohne, stelle),
            **abweichung,
        })
    werte = [e["rms_rad"] for e in ergebnisse]
    return {
        "band": [von, bis],
        "stellen": len(drin),
        "rms_median": _median(werte),
        "rms_schlechteste": max(werte, default=None),
        "ergebnisse": sorted(ergebnisse, key=lambda e: e["tempo_m_s"]),
    }


def halteprobe(kennlinie, fenster=("B6", "B7")):
    """Gegen Abschnitte, die das Modell NIE gesehen hat.

    Sie stammen aus Fenstern ohne Absicht und sind durch `NUR_MIT_ABSICHT`
    aussen vor. Damit sind sie echte Haltedaten — nicht unabhaengig erhoben
    (dieselbe Maschine, derselbe Tag), aber nicht in die Kennlinie eingegangen.
    """
    modell = Gangmodell(kennlinie)
    ergebnisse = []
    for stelle in kennlinie["stuetzstellen"]:
        name = stelle["herkunft"]["fenster"]
        if stelle.get("absicht") or not name.startswith(fenster):
            continue
        abweichung = _abweichung(modell, stelle)
        if abweichung is None:
            continue
        ergebnisse.append({
            "tempo_m_s": stelle["tempo_m_s"],
            "drehrate_rad_s": stelle["drehrate_rad_s"],
            "fenster": name,
            **abweichung,
        })
    return sorted(ergebnisse, key=lambda e: (e["fenster"], e["tempo_m_s"]))


def _mittel(werte):
    return round(sum(werte) / len(werte), 4) if werte else None


def zusammenfassung(kennlinie):
    """Beide Pruefungen plus die Negativkontrolle."""
    selbst = selbstpruefung(kennlinie)
    halte = halteprobe(kennlinie)
    eben = [e["rms_rad"] for e in halte if e["fenster"].startswith("B7")]
    treppe = [e["rms_rad"] for e in halte if e["fenster"].startswith("B6")]
    return {
        "selbstpruefung": {
            "stellen": len(selbst),
            "rms_median": _median([e["rms_rad"] for e in selbst]),
            "rms_schlechteste": max((e["rms_rad"] for e in selbst), default=None),
        },
        "halteprobe_eben_B7": {"stellen": len(eben), "rms_mittel": _mittel(eben)},
        "halteprobe_treppe_B6": {"stellen": len(treppe), "rms_mittel": _mittel(treppe)},
        # Die Kontrolle: das Modell kennt nur ebenen Gang. Ist es auf der
        # Treppe NICHT schlechter, misst die Metrik nicht, was sie behauptet.
        "negativkontrolle_bestanden": (
            None if not (eben and treppe) else _mittel(treppe) > _mittel(eben)
        ),
    }


def _median(werte):
    if not werte:
        return None
    geordnet = sorted(werte)
    n = len(geordnet)
    return round(
        geordnet[n // 2] if n % 2 else (geordnet[n // 2 - 1] + geordnet[n // 2]) / 2, 4
    )


def als_text(kennlinie, luecken_band=(0.20, 0.28)):
    """Bericht zum Mitlesen. Zahlen in Grad, weil rad niemand im Kopf hat."""
    zeilen = []
    z = zusammenfassung(kennlinie)
    selbst = z["selbstpruefung"]
    zeilen.append("SELBSTPRUEFUNG (leave-one-out, dichte Nachbarschaft)")
    zeilen.append(
        f"  {selbst['stellen']} Stellen, Median {_grad(selbst['rms_median'])}, "
        f"schlechteste {_grad(selbst['rms_schlechteste'])}"
    )
    zeilen.append("  Optimistisch: entfernt EINE Stelle, deren Nachbar oft 0.003 m/s")
    zeilen.append("  entfernt liegt. Sagt nichts ueber eine echte Luecke.")

    luecke = lueckenprobe(kennlinie, *luecken_band)
    zeilen.append("")
    zeilen.append(f"LUECKENPROBE (Band {luecken_band[0]}-{luecken_band[1]} m/s ganz entfernt)")
    if luecke["ergebnisse"]:
        zeilen.append(
            f"  {luecke['stellen']} Stellen, Median {_grad(luecke['rms_median'])}, "
            f"schlechteste {_grad(luecke['rms_schlechteste'])}"
        )
        for e in luecke["ergebnisse"]:
            zeilen.append(
                f"    {e['tempo_m_s']:.3f} m/s  {_grad(e['rms_rad'])}  "
                f"Zyklus {e['zyklus_ist_s']:.2f} gemessen / "
                f"{e['zyklus_modell_s']:.2f} vorhergesagt"
            )
    else:
        zeilen.append("  keine Stellen in diesem Band")

    zeilen.append("")
    zeilen.append("HALTEPROBE (B6/B7, nie ins Modell eingegangen)")
    zeilen.append(f"  eben (B7)  : {_grad(z['halteprobe_eben_B7']['rms_mittel'])}")
    zeilen.append(f"  Treppe (B6): {_grad(z['halteprobe_treppe_B6']['rms_mittel'])}")
    kontrolle = z["negativkontrolle_bestanden"]
    zeilen.append(
        "  Negativkontrolle: "
        + ("bestanden — die Treppe ist erwartungsgemaess schlechter"
           if kontrolle
           else "NICHT bestanden — dann misst die Metrik nicht, was sie behauptet"
           if kontrolle is False else "nicht durchfuehrbar (zu wenig Daten)")
    )
    return "\n".join(zeilen)


def _grad(rad):
    return "--" if rad is None else f"{rad:.3f} rad = {rad * 180 / math.pi:.1f} Grad"


def main(argv=None):
    import argparse

    from spotlab.kalibrierung import gang

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kennlinie", default=None)
    args = ap.parse_args(argv)
    print(als_text(gang.lade(args.kennlinie)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
