"""Gehzeit: Spot steht, schaut zu und nimmt fuer jeden einzeln die Zeit.

Der Versuch aus der Verhaltensbiologie: wie haengt die Gehgeschwindigkeit von
der Gruppengroesse ab? Bisher steht ein Mensch mit der Stoppuhr im Gang und kann
immer nur EINE Gruppe messen. Spot kann fuer jeden gleichzeitig stoppen — und
weil er dabei nur zusieht, laeuft das Programm ueber `connect(nur_lesen=True)`:
kein Lease, kein Not-Aus-Endpunkt, die Aufsichtsperson behaelt das Tablet.

DREI TEILE, getrennt lesbar und getrennt austauschbar — dieselbe Aufteilung wie
beim Folgen:

    QUELLE      sagt, WO die Leute sind: je Person `(Kennung, Peilung, Abstand)`.
                Ein AprilTag am Rucksack (`tag_quelle`, heute nachweisbar) oder
                Spots eigener Personen-Tracker (`personen_quelle`). Welche taugt,
                entscheidet Abnahmepunkt A34 Teil 1 am Geraet.
    STRECKE     `experiment/strecke.py` — gemessen aus zwei AprilTags an den
                Enden, nicht eingetippt.
    ZEITNAHME   `experiment/zeitnahme.py` — eine Uhr je Person, drei
                Verwerfungsregeln.

KEINE GESICHTSQUELLE, und das ist kein Versehen. Ein Gesicht traegt keine
Kennung ueber die Zeit; die Zeitnahme braucht aber eine, sonst ist der Mensch
im naechsten Bild ein anderer. Ein selbstgebauter Verfolger darauf hiesse,
Identitaeten zu erfinden — bei einer Trefferlage, die am 12.08.2026 bei zwei von
zwei nachgesehenen Treffern danebenlag (Stuhllehne, Schienbein). Aus demselben
Grund gibt es KEINE Altersschaetzung aus dem Gesicht: sie stuende ununterscheidbar
neben gemessenen Zeiten.

WAS SPOT NICHT ENTSCHEIDET, ist die Gruppengroesse. Er meldet, wer gleichzeitig
unterwegs war (`durchgang.py`), und traegt es als Vorschlag in die Tabelle. Den
Rest traegt ein Mensch nach, nachdem er die Bilder des Abschnitts angesehen hat
— `python -m spotlab.experiment.nachtrag <lauf>`. Waehrend der Lauf laeuft,
gehoert die Tabelle dem Lauf: sie wird nach jedem fertigen Durchgang neu
geschrieben, und ein Eintrag von Hand ginge dabei verloren. Die anhaengende
`querungen.jsonl` ist ohnehin die Wahrheit; die Tabelle ist die Ansicht davon.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError
from spotlab.experiment import tabelle
from spotlab.experiment.durchgang import durchgaenge_aus
from spotlab.experiment.strecke import (
    MAX_STREUUNG_M,
    fortschritt,
    miss_strecke,
    punkt_aus,
    querabstand,
)
from spotlab.experiment.zeitnahme import Sicht, Zeitnahme
from spotlab.record.run import STOPP_DATEI
from spotlab.workshop.beispiele import ORDNER

DATEINAME = "gehzeit.py"

# Alles, was dieser Versuch schreibt, liegt in einem Unterordner des Laufs — die
# Aufzeichnung daneben bleibt die gewohnte.
ORDNER_NAME = "gehzeit"
CSV_NAME = "gehzeit.csv"
STRECKE_NAME = "strecke.json"
QUERUNGEN_NAME = "querungen.jsonl"

TAKT_S = 0.2
# So viele Abtastungen fuer die Strecke. Bei 0.2 s sind das gut zwei Sekunden —
# lang genug fuer einen Median, kurz genug, dass niemand wartet.
MESS_PROBEN = 12
MESS_TAKT_S = 0.2
DAUER_S = 600.0

# Bilder fuer den Nachtrag: waehrend jemand laeuft dicht, sonst duenn. NICHT
# null — `Bildmitschnitt.setze_rate(0)` schaltet nichts ab, sondern nimmt dem
# Bildthread die Wartezeit; er fragte dann so schnell, wie das WLAN hergibt.
BILD_HZ = 2.0
BILD_HZ_RUHE = 0.2
# Nur die zwei Frontkameras: der Gang liegt vor Spot, und fuenf Kameras bei zwei
# Bildern je Sekunde sind Bandbreite fuer Bilder, die niemand ansieht.
BILD_QUELLEN = ("frontleft_fisheye_image", "frontright_fisheye_image")
# Hoeher als die 75 der Live-Ansicht: diese Bilder soll ein Mensch anschauen und
# darauf Gesichter unterscheiden, und sie entstehen genau einmal.
BILD_GUETE = 90


@dataclass(frozen=True)
class Sichtung:
    """Eine Person in einem Takt, so wie eine Quelle sie sieht."""

    kennung: str
    bearing: float          # Grad, links positiv
    distance: float         # Meter


def skript_in(arbeitsordner):
    """Das Gehzeit-Programm im Projekt Beispiele des Arbeitsordners."""
    return Path(arbeitsordner) / ORDNER / DATEINAME


# ----------------------------------------------------------------- Quellen


def tag_quelle(ausser=()):
    """Jede Person traegt ein AprilTag — der Weg, der heute nachweislich geht.

    `ausser` nimmt die beiden Streckentags heraus; die haengen an der Wand und
    liefen sonst als zwei sehr geduldige Versuchspersonen mit.
    """
    ausgenommen = {int(t) for t in ausser}

    def sieh(spot):
        return [
            Sichtung(f"tag{tag.id}", tag.bearing, tag.distance)
            for tag in spot.tags()
            if tag.id not in ausgenommen
        ]

    return sieh


def personen_quelle(mindestsicherheit=None):
    """Spots eigener Personen-Tracker — kein eigenes Modell.

    Er vergibt die Kennung selbst und haelt sie ueber die Zeit; genau das
    braucht die Zeitnahme. Ob DIESER Roboter ihn hat, zeigt erst das Geraet
    (A34 Teil 1); liefert er nichts, sieht diese Quelle nichts.
    """

    def sieh(spot):
        leute = spot.people()
        if mindestsicherheit is not None:
            leute = [p for p in leute if p.likelihood >= mindestsicherheit]
        return [
            Sichtung(f"person{p.entity_id}", p.bearing, p.distance) for p in leute
        ]

    return sieh


# ------------------------------------------------------------ Bildmitschnitt


class _Kameras:
    """Nur-Lese-Bildquelle ueber das Backend — genau eine Methode.

    Gebaut wie `beobachtung/bildquelle.py::Bildquelle`, nur ueber die
    Backend-Fassade statt ueber den `ImageClient`: die Sitzung dieses Versuchs
    haelt kein Lease, und `RealSpot.images` ist der Weg, der auch die Farbfrage
    samt Graustufen-Rueckfall kennt.
    """

    def __init__(self, backend, quellen=BILD_QUELLEN, guete=BILD_GUETE):
        self._backend = backend
        self._quellen = list(quellen)
        self._guete = guete

    def bilder(self):
        return self._backend.images(self._quellen, farbe=True, guete=self._guete)


def bildmitschnitt(spot, quellen=BILD_QUELLEN, guete=BILD_GUETE, hz=BILD_HZ_RUHE):
    """Ein Mitschnitt fuer den Nachtrag — oder None, wenn dieser Lauf keine hat.

    Die Bilder sind der GRUND, warum ein Mensch die Gruppengroesse eintragen
    kann; ohne sie bliebe ihm nur Spots Vorschlag. Sie landen im gewohnten
    `kamera/` mit demselben anhaengenden Index wie beim Beobachter — und mit
    derselben Zeitbasis, in der die Zeitnahme stempelt.

    Ohne Kameras (Trockenlauf, Uebungsraum) gibt es keinen Mitschnitt und keine
    Fehlermeldung: die Zeiten stehen trotzdem in der Tabelle.
    """
    from spotlab.beobachtung.bilder import Bildmitschnitt

    if not spot.supports("camera") or getattr(spot, "recorder", None) is None:
        return None
    return Bildmitschnitt(_Kameras(spot.backend, quellen, guete), spot.recorder, hz=hz)


# ----------------------------------------------------------- Strecke messen


def miss(spot, proben=MESS_PROBEN, takt_s=MESS_TAKT_S, tag_start=None, tag_ziel=None,
         schlaf=time.sleep):
    """Die Strecke aus mehreren Blicken auf die beiden Tags.

    Mehrere, nicht einer: eine einzelne Tag-Messung ist eine Zahl ohne
    Fehlerbalken, und `miss_strecke` bildet daraus den Median samt Streuung.
    """
    gesammelt = []
    for nummer in range(int(proben)):
        gesammelt.append([(t.id, t.bearing, t.distance) for t in spot.tags()])
        if nummer + 1 < int(proben):
            schlaf(takt_s)
    return miss_strecke(gesammelt, tag_start=tag_start, tag_ziel=tag_ziel)


# --------------------------------------------------------------- Der Lauf


def _zeitgeber(spot, jetzt):
    """Die Zeitbasis der Aufzeichnung, wenn es eine gibt.

    `recorder.zeitmarke()` ist dieselbe Zahl wie `t` im Bildindex — nur so
    findet der Nachtrag die Bilder zu einem gemessenen Durchgang. Ohne
    Aufzeichnung (Tests) tut es die uebergebene Uhr.
    """
    recorder = getattr(spot, "recorder", None)
    if recorder is not None and hasattr(recorder, "zeitmarke"):
        return recorder.zeitmarke
    return jetzt


def _sichten(strecke, sichtungen):
    sichten = []
    for gesehen in sichtungen:
        punkt = punkt_aus(gesehen.bearing, gesehen.distance)
        sichten.append(
            Sicht(gesehen.kennung, fortschritt(strecke, punkt), querabstand(strecke, punkt))
        )
    return sichten


def _schreibe_querung(pfad, querung):
    zeile = {
        "kennung": querung.kennung, "richtung": querung.richtung,
        "t_start": round(querung.t_start, 3), "t_ende": round(querung.t_ende, 3),
        "dauer_s": None if querung.dauer_s is None else round(querung.dauer_s, 3),
        "tempo_m_s": None if querung.tempo_m_s is None else round(querung.tempo_m_s, 3),
        "verworfen": querung.verworfen, "grund": querung.grund,
    }
    with pfad.open("a", encoding="utf-8") as ziel:
        ziel.write(json.dumps(zeile, ensure_ascii=False) + "\n")


def gehzeit(spot, quelle=None, strecke=None, dauer_s=DAUER_S, takt_s=TAKT_S,
            melde=print, jetzt=time.monotonic, uhr=None, schlaf=time.sleep,
            laeuft=None, lauf_dir=None, ziel=None, mitschnitt=None,
            max_streuung_m=MAX_STREUUNG_M, tag_start=None, tag_ziel=None):
    """Strecke messen, zusehen, Zeiten schreiben. Bewegt nichts.

    ZWEI UHREN, wie in `api/motion.py`, und sie zu verschmelzen waere bequem und
    falsch: `jetzt` (monoton) haelt den Takt und die Gesamtdauer, `uhr` stempelt
    die Messwerte. `uhr` ist ohne Angabe `recorder.zeitmarke` — dieselbe Zahl wie
    `t` im Bildindex, sonst faende der Nachtrag die Bilder zu einer gemessenen
    Zeit nicht.

    Ohne `strecke` misst das Programm sie selbst aus den beiden Tags. Wer sie
    mit dem Massband genommen hat, reicht sie herein — auch das ist dann eine
    bewusste Handlung und keine Altlast.

    Testbar ohne Roboter: `spot` braucht `tags()` und was die Quelle abfragt.
    """
    ordner = Path(ziel) if ziel is not None else _ordner_von(spot, lauf_dir)
    ordner.mkdir(parents=True, exist_ok=True)
    csv_pfad, querungen_pfad = ordner / CSV_NAME, ordner / QUERUNGEN_NAME
    uhr = uhr or _zeitgeber(spot, jetzt)
    versatz = time.time() - uhr()

    if strecke is None:
        try:
            strecke = miss(spot, tag_start=tag_start, tag_ziel=tag_ziel, schlaf=schlaf)
        except SpotlabError as fehler:
            # Kein Abbruch mit Ausnahme: der Lauf hat schon stattgefunden, und
            # ein Programm, das mit einem Stacktrace endet, sagt einem Schueler
            # weniger als ein Satz. Der Grund geht mit zurueck.
            melde(f"Keine Messung: {fehler}")
            return {"strecke": None, "grund": str(fehler), "querungen": [],
                    "durchgaenge": [], "csv": None}

    if strecke.streuung_m > max_streuung_m:
        grund = (
            f"Die Strecke schwankt um {strecke.streuung_m:.2f} m zwischen den "
            f"Einzelmessungen (erlaubt: {max_streuung_m:.2f} m) — darauf lässt "
            "sich kein Tempo rechnen. Spot näher an die Tags stellen, sie fest "
            "und flach anbringen, oder die gemessene Länge mit `strecke=` "
            "übergeben."
        )
        melde(f"Keine Messung: {grund}")
        return {"strecke": strecke, "grund": grund, "querungen": [],
                "durchgaenge": [], "csv": None}

    (ordner / STRECKE_NAME).write_text(
        json.dumps({
            "laenge_m": round(strecke.laenge_m, 3),
            "streuung_m": round(strecke.streuung_m, 3),
            "tag_start": strecke.tag_start, "tag_ziel": strecke.tag_ziel,
            "proben": strecke.proben,
            "start": [strecke.start.x, strecke.start.y],
            "ziel": [strecke.ziel.x, strecke.ziel.y],
            "wanduhr_versatz": versatz,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    melde(
        f"Strecke {strecke.laenge_m:.2f} m zwischen Tag {strecke.tag_start} und "
        f"Tag {strecke.tag_ziel} (Streuung {strecke.streuung_m:.2f} m, "
        f"{strecke.proben} Abtastungen)."
    )

    quelle = quelle or tag_quelle(ausser=(strecke.tag_start, strecke.tag_ziel))
    laeuft = laeuft or _stopp_wache(ordner.parent)

    zeitnahme = Zeitnahme(strecke)
    querungen, gemeldet = [], False
    ende = jetzt() + float(dauer_s)
    while jetzt() < ende and laeuft():
        beginn = jetzt()
        try:
            sichtungen = quelle(spot)
        except Exception as fehler:
            # Eine Quelle, die aussetzt, beendet den Versuch nicht — sie meldet
            # sich EINMAL. Still uebergehen waere schlimmer: eine leere Tabelle
            # saehe aus wie ein Gang, durch den niemand ging.
            if not gemeldet:
                gemeldet = True
                melde(f"Die Quelle fällt aus: {fehler}")
            sichtungen = []
        fertig = zeitnahme.beobachte(uhr(), _sichten(strecke, sichtungen))
        for querung in fertig:
            _schreibe_querung(querungen_pfad, querung)
            querungen.append(querung)
            melde(_satz(querung, strecke))
        if fertig:
            _schreibe_tabelle(csv_pfad, querungen, strecke, versatz)
        if mitschnitt is not None:
            mitschnitt.setze_rate(BILD_HZ if zeitnahme.laufende() else BILD_HZ_RUHE)
        rest = takt_s - (jetzt() - beginn)
        if rest > 0:
            schlaf(rest)

    durchgaenge = _schreibe_tabelle(csv_pfad, querungen, strecke, versatz)
    melde(
        f"{len(durchgaenge)} Durchgänge, {sum(1 for q in querungen if not q.verworfen)} "
        f"von {len(querungen)} Querungen gemessen. Tabelle: {csv_pfad}"
    )
    return {"strecke": strecke, "grund": None, "querungen": querungen,
            "durchgaenge": durchgaenge, "csv": csv_pfad}


def _stopp_wache(lauf_ordner):
    """`laeuft()` aus der Stopp-Markierung des Laufs — wie im Folgemodus."""
    stopp = Path(lauf_ordner) / STOPP_DATEI

    def laeuft():
        return not stopp.exists()

    return laeuft


def _ordner_von(spot, lauf_dir):
    if lauf_dir is not None:
        return Path(lauf_dir) / ORDNER_NAME
    recorder = getattr(spot, "recorder", None)
    if recorder is None:
        raise ValueError("gehzeit() braucht `lauf_dir`, `ziel` oder eine Aufzeichnung.")
    return Path(recorder.dir) / ORDNER_NAME


def _satz(querung, strecke):
    if querung.verworfen:
        return f"  {querung.kennung}: verworfen ({querung.grund})"
    return (
        f"  {querung.kennung}: {querung.dauer_s:.2f} s für {strecke.laenge_m:.2f} m "
        f"= {querung.tempo_m_s:.2f} m/s"
    )


def _schreibe_tabelle(pfad, querungen, strecke, versatz):
    durchgaenge = durchgaenge_aus(querungen)
    tabelle.schreibe(pfad, [
        tabelle.zeile_aus(d, strecke_m=strecke.laenge_m, versatz=versatz)
        for d in durchgaenge
    ])
    return durchgaenge

