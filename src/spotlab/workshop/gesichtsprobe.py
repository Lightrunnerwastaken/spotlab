"""Messprobe: was der Gesichtserkenner wirklich sieht — und was damit passiert.

    python -m spotlab.workshop.gesichtsprobe --runs <ordner> --dauer 30

DER ANLASS. Am 11.09.2026 lief der Folgemodus am Schul-Spot mit
`zuerst(gesicht_finder(), tag_finder())`. In 73 von 73 Takten meldete das
Gesicht nichts, und das Tag trug allein. Aus der Aufzeichnung liess sich aber
NICHT ablesen, woran es lag: ob YuNet gar keinen Kasten setzte, oder ob die
Gegenprobe einen verwarf — und wenn ja, an welcher der beiden Schranken.

Ein Nullergebnis ohne Begründung ist keine Messung. Diese Probe liefert die
Begründung:

    Takt 12: 1 Kasten
      0.71 bei  3.24 m, Höhe 0.94 m über Boden  ->  VERWORFEN (zu tief)

WAS SIE TUT. Spot STEHT. Sie verbindet über `nur_lesen=True`, hält also kein
Lease und kann den Roboter nicht bewegen — das Tablet bleibt in der Hand der
Aufsicht. Je Takt holt sie dieselben vier Bilder wie `gesicht_finder`, baut
dasselbe Panorama und dieselbe Punktwolke, und schreibt je Kasten Punktzahl,
Peilung, Höhenwinkel, gemessenen Abstand, gerechnete Höhe über dem Boden und
das Urteil.

EINE FORMULIERUNG, NICHT ZWEI. Aufnahme und Gegenprobe kommen aus
`folgen.gesichtsaufnahme` und `gesicht.beurteile` — genau dem Code, den der
Folgemodus fährt. Eine nachgebaute Probe misst sonst etwas anderes als das, was
am Gerät wirklich passiert, und das fiele erst auf, wenn niemand mehr nachrechnet.

DIE KÖRPERZEILE (seit 16.09.2026). Der Körper steht in der Staffel VOR dem
Gesicht (`folgen.koerper_finder`; Messung über 510 Panoramen: 33-mal nur der
Körper, 47-mal nur das Gesicht). Deshalb schreibt die Probe je Takt BEIDE Wege
auf, mit derselben Formulierung wie der Folgemodus (`koerper.beurteile`):

    Takt 12: Körper 0.93: Hüfte 0.94 m über Boden bei 1.82 m, Peilung +3°  ->  genommen

Fehlen die Körpermodelle, läuft die Probe mit dem Gesicht weiter und sagt es
EINMAL; die Körperzeile heisst dann `null`. Ein stolpernder Erkenner wird
gezählt und einmal gemeldet, nicht verschwiegen.

DIE PANORAMEN BLEIBEN LIEGEN. Das ist der zweite Zweck: dem Projekt fehlt seit
dem ersten Tag ein Testbild MIT einem Gesicht darin. Die Aufzeichnung vom
12.08.2026 hat keines — leerer Gang, Tischreihe, und eine Person, von der nur
die Beine im Bild sind. Was hier aufgenommen wird, kann als Fixture dienen.
Mit `--ohne-bilder` bleibt es bei den Zahlen.
"""

import json
import time
from pathlib import Path

ORDNER_NAME = "gesicht"
INDEX = "gesicht/probe.jsonl"
BILDORDNER = "gesicht/panorama"

DAUER_S = 30.0
# Ein Takt kostet vier Bilder über WLAN. Schneller als einmal je Sekunde bringt
# nichts: die Person steht, und die Bilder sollen einzeln ansehbar bleiben.
TAKT_S = 1.0


def _befund_satz(befund):
    """Ein Befund als JSON-Zeile. Fehlende Messwerte bleiben None, nie 0."""
    return {
        "score": round(float(befund.score), 3),
        "bearing": round(float(befund.bearing), 1),
        "elevation": round(float(befund.elevation), 1),
        "distance": None if befund.distance is None else round(float(befund.distance), 2),
        "height": None if befund.height is None else round(float(befund.height), 2),
        "box": [round(float(v), 1) for v in befund.box],
        "genommen": bool(befund.genommen),
        "grund": befund.grund,
    }


def _satz_text(befund):
    if befund.distance is None:
        return f"    {befund.score:.2f}, kein Abstand  ->  VERWORFEN ({befund.grund})"
    urteil = "genommen" if befund.genommen else f"VERWORFEN ({befund.grund})"
    return (f"    {befund.score:.2f} bei {befund.distance:5.2f} m, "
            f"Höhe {befund.height:.2f} m über Boden, Peilung {befund.bearing:+.0f}°"
            f"  ->  {urteil}")


def _koerpersatz(b):
    """Ein Körperbefund als JSON-Zeile. Fehlende Messwerte bleiben None, nie 0."""
    return {
        "conf": round(float(b.conf), 3),
        "punkt": b.punkt,
        "bearing": round(float(b.bearing), 1),
        "elevation": round(float(b.elevation), 1),
        "distance": None if b.distance is None else round(float(b.distance), 2),
        "height": None if b.height is None else round(float(b.height), 2),
        "bild_oben": None if b.bild_oben is None else round(float(b.bild_oben), 1),
        "genommen": bool(b.genommen),
        "grund": b.grund,
    }


def _koerpertext(b):
    teil = "Hüfte" if b.punkt == "huefte" else "Schulter"
    if b.distance is None:
        return f"Körper {b.conf:.2f}: {teil}, kein Abstand  ->  VERWORFEN ({b.grund})"
    urteil = "genommen" if b.genommen else f"VERWORFEN ({b.grund})"
    return (f"Körper {b.conf:.2f}: {teil} {b.height:.2f} m über Boden bei {b.distance:.2f} m, "
            f"Peilung {b.bearing:+.0f}°  ->  {urteil}")


def _schreibe_bild(ordner, nummer, feld):
    """Das Panorama als PNG — verlustfrei, weil es Fixture werden soll."""
    from PIL import Image

    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"{nummer:04d}_panorama.png"
    Image.fromarray(feld).save(pfad)
    return pfad


def probe(spot, dauer_s=DAUER_S, takt_s=TAKT_S, ziel=None, lauf_dir=None,
          bilder=True, melde=print, jetzt=time.monotonic, schlaf=time.sleep,
          aufnahme_holen=None, kaesten_holen=None, laeuft=None, koerper_holen=None):
    """Steht still, schaut, und schreibt je Kasten das Urteil auf.

    `aufnahme_holen` und `kaesten_holen` sind die Testtüren: ohne sie kommen
    Aufnahme und Kästen aus dem echten Weg (`folgen.gesichtsaufnahme`,
    `gesicht.kaesten`).
    """
    from spotlab.backends.real import gesicht as gesichtsmodul
    from spotlab.workshop import folgen

    ordner = Path(ziel) if ziel is not None else _ordner_von(spot, lauf_dir)
    ordner.mkdir(parents=True, exist_ok=True)
    index = ordner / Path(INDEX).name
    bildordner = ordner / Path(BILDORDNER).name

    from spotlab.backends.real import koerper as koerpermodul
    from spotlab.errors import SpotlabError

    aufnahme_holen = aufnahme_holen or folgen.gesichtsaufnahme
    kaesten_holen = kaesten_holen or gesichtsmodul.kaesten
    laeuft = laeuft or (lambda: True)

    # Der Körper-Weg: ein Erkenner für die ganze Probe, gebaut beim ersten Takt.
    # Fehlen die Modelle, geht der Weg dauerhaft aus (`aus`) -- die Probe läuft
    # mit dem Gesicht weiter und sagt es einmal.
    koerper_stand = {"aus": None, "gemeldet": False}

    def koerper_vorgabe(feld):
        if "erkenner" not in koerper_stand:
            koerper_stand["erkenner"] = koerpermodul.Koerpererkenner()
        return koerper_stand["erkenner"].finde(feld)

    koerper_holen = koerper_holen or koerper_vorgabe
    koerper_takte = koerper_genommen = koerper_fehler = 0
    koerper_gruende = {}

    gemerkt = {}
    takte = kaesten_gesamt = genommen = fehler = 0
    gruende = {}
    gemeldet = False
    ende = jetzt() + float(dauer_s)

    while jetzt() < ende and laeuft():
        beginn = jetzt()
        try:
            aufnahme = aufnahme_holen(spot, gemerkt)
        except Exception as fehlgriff:
            fehler += 1
            if not gemeldet:
                gemeldet = True
                melde(f"Die Aufnahme fällt aus: {fehlgriff}")
            aufnahme = None
        if aufnahme is None:
            _warte(jetzt, schlaf, takt_s, beginn)
            continue

        takte += 1
        befunde = gesichtsmodul.beurteile(
            aufnahme.feld, aufnahme.pano, aufnahme.erkenner, aufnahme.punkte,
            aufnahme.pano.kamerahoehe(aufnahme.blick_grad),
            blick_grad=aufnahme.blick_grad,
            kaesten_holen=kaesten_holen,
        )
        koerper_befunde = None
        if koerper_stand["aus"] is None:
            try:
                koerper_befunde = koerpermodul.beurteile(
                    koerper_holen(aufnahme.feld), aufnahme.pano, aufnahme.punkte,
                    aufnahme.pano.kamerahoehe(aufnahme.blick_grad),
                    blick_grad=aufnahme.blick_grad,
                )
            except SpotlabError as fehlgriff:
                # Modelle fehlen: dauerhaft aus, einmal gesagt, das Gesicht misst weiter.
                koerper_stand["aus"] = str(fehlgriff)
                melde(f"Körper: {fehlgriff}")
            except Exception as fehlgriff:
                koerper_fehler += 1
                if not koerper_stand["gemeldet"]:
                    koerper_stand["gemeldet"] = True
                    melde(f"Der Körper-Erkenner fällt aus: {fehlgriff}")
        if koerper_befunde:
            koerper_takte += 1
            koerper_genommen += sum(1 for b in koerper_befunde if b.genommen)
            for b in koerper_befunde:
                if b.grund:
                    koerper_gruende[b.grund] = koerper_gruende.get(b.grund, 0) + 1

        bildpfad = None
        if bilder:
            bildpfad = _schreibe_bild(bildordner, takte, aufnahme.feld)

        kaesten_gesamt += len(befunde)
        genommen += sum(1 for b in befunde if b.genommen)
        for b in befunde:
            if b.grund:
                gruende[b.grund] = gruende.get(b.grund, 0) + 1

        satz = {
            "takt": takte,
            "nick_grad": round(float(aufnahme.blick_grad), 1),
            "bild": None if bildpfad is None else bildpfad.name,
            "befunde": [_befund_satz(b) for b in befunde],
            "koerper": (None if koerper_befunde is None
                        else [_koerpersatz(b) for b in koerper_befunde]),
        }
        with index.open("a", encoding="utf-8") as datei:
            datei.write(json.dumps(satz, ensure_ascii=False) + "\n")

        if befunde:
            melde(f"Takt {takte}: {len(befunde)} Kasten"
                  + ("" if len(befunde) == 1 else "n"))
            for b in befunde:
                melde(_satz_text(b))
        if koerper_befunde:
            for b in koerper_befunde:
                melde(f"Takt {takte}: " + _koerpertext(b))
        _warte(jetzt, schlaf, takt_s, beginn)

    melde("")
    melde(f"{takte} Takte, {kaesten_gesamt} Kästen, davon {genommen} genommen.")
    for grund, wie_oft in sorted(gruende.items()):
        melde(f"   verworfen — {grund}: {wie_oft}")
    if fehler:
        melde(f"   {fehler} Takte ohne Aufnahme")
    if koerper_stand["aus"] is not None:
        melde(f"Körper: aus — {koerper_stand['aus']}")
    else:
        melde(f"Körper: in {koerper_takte} Takten gesehen, {koerper_genommen} genommen.")
        for grund, wie_oft in sorted(koerper_gruende.items()):
            melde(f"   verworfen — {grund}: {wie_oft}")
        if koerper_fehler:
            melde(f"   {koerper_fehler} Takte mit ausgefallenem Körper-Erkenner")
    melde(f"Einzelheiten: {index}")
    return {"takte": takte, "kaesten": kaesten_gesamt, "genommen": genommen,
            "gruende": gruende, "fehler": fehler, "index": index,
            "koerper": {"takte": koerper_takte, "genommen": koerper_genommen,
                        "gruende": koerper_gruende, "fehler": koerper_fehler,
                        "aus": koerper_stand["aus"]}}


def _warte(jetzt, schlaf, takt_s, beginn):
    rest = takt_s - (jetzt() - beginn)
    if rest > 0:
        schlaf(rest)


def _ordner_von(spot, lauf_dir):
    if lauf_dir is not None:
        return Path(lauf_dir) / ORDNER_NAME
    recorder = getattr(spot, "recorder", None)
    if recorder is None:
        raise ValueError("probe() braucht `lauf_dir`, `ziel` oder eine Aufzeichnung.")
    return Path(recorder.dir) / ORDNER_NAME


# ------------------------------------------------------------ Hauptprogramm


def _hauptprogramm(argv=None, drucke=print):
    """Als Skript gestartet — schreibt einen Lauf, wie die Sonde.

    Paketcode und `nur_lesen=True`: die Probe kann den Roboter nicht bewegen,
    also darf sie neben einem führenden Tablet laufen.
    """
    import os
    import sys

    import spotlab

    argv = list(sys.argv[1:] if argv is None else argv)
    runs = argv[argv.index("--runs") + 1] if "--runs" in argv else None
    runs = runs or os.environ.get("SPOTLAB_RUNS_DIR") or (Path.cwd() / "runs")
    dauer = float(argv[argv.index("--dauer") + 1]) if "--dauer" in argv else DAUER_S

    with spotlab.connect(runs_dir=runs, script=__file__, nur_lesen=True) as spot:
        drucke("Gesichtsprobe: Spot steht und schaut. Stell dich davor.")
        probe(spot, dauer_s=dauer, lauf_dir=spot.recorder.dir,
              bilder="--ohne-bilder" not in argv, melde=drucke)


if __name__ == "__main__":
    _hauptprogramm()
