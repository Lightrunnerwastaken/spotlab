"""Den Abschnitt ansehen, die Gruppengroesse eintragen, die Bilder loeschen.

    python -m spotlab.experiment.nachtrag <Lauf-Verzeichnis>

Der Teil, den ausdruecklich ein MENSCH macht. Spot liefert Zeiten und einen
Vorschlag, wer gleichzeitig unterwegs war; ob drei Leute eine Gruppe waren oder
drei Einzelne, sieht man auf den Bildern. Diese Aufteilung ist der Kern des
Versuchs — Spot misst, was er messen kann, und behauptet den Rest nicht.

DIE BILDER GEHEN WEG, wenn der Mensch es sagt. Es sind Aufnahmen von
Schuelerinnen und Schuelern im Schulhaus, aufgenommen fuer genau eine Frage; ist
sie beantwortet, gibt es keinen Grund mehr, sie zu behalten. Geloescht werden
die Dateien UND ihre Zeilen im Bildindex — ein Index, der auf nicht mehr
vorhandene Dateien zeigt, laedt nur dazu ein, sie irgendwo zu suchen.

Reine Standardbibliothek: Dateien und Text, kein Roboter.
"""

import json
import sys
from pathlib import Path

from spotlab.errors import SpotlabError
from spotlab.experiment import tabelle
from spotlab.record.atomar import schreibe_atomar
from spotlab.workshop.gehzeit import CSV_NAME, ORDNER_NAME

# So viel vor und nach der gemessenen Zeit gehoert noch zum Abschnitt: der
# Mensch soll sehen, wie die Leute ankommen und weggehen, nicht nur den
# Ausschnitt zwischen den beiden Linien.
RAND_S = 1.5

INDEX = "kamera/kamera.jsonl"


def csv_pfad(lauf):
    return Path(lauf) / ORDNER_NAME / CSV_NAME


# ------------------------------------------------------------------ Bilder


def _index(lauf):
    pfad = Path(lauf) / INDEX
    if not pfad.is_file():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            # Ein getoeteter Lauf hat eine halbe letzte Zeile. Dieselbe Regel
            # wie in `record/read.py`: nicht daran scheitern.
            continue
    return saetze


def bilder_zu(lauf, t_start, t_ende, rand_s=RAND_S):
    """Die Bilder im Zeitfenster eines Durchgangs, in Aufnahmereihenfolge.

    Die Zeiten sind LAUFZEIT — dieselbe Basis wie `t` im Bildindex. Nur
    deshalb geht das ohne Umrechnung (`record/run.py::zeitmarke`).
    """
    ordner = Path(lauf) / "kamera"
    fenster = [
        satz for satz in _index(lauf)
        if t_start - rand_s <= float(satz.get("t", -1)) <= t_ende + rand_s
    ]
    fenster.sort(key=lambda satz: float(satz.get("t", 0.0)))
    return [ordner / satz["datei"] for satz in fenster if (ordner / satz["datei"]).is_file()]


def _loesche(lauf, behalten):
    """`behalten(satz)` sagt, welche Indexzeilen bleiben. Gibt die Zahl der
    geloeschten Bilder zurueck."""
    ordner = Path(lauf) / "kamera"
    saetze = _index(lauf)
    bleiben, weg = [], 0
    for satz in saetze:
        if behalten(satz):
            bleiben.append(satz)
            continue
        datei = ordner / satz.get("datei", "")
        try:
            datei.unlink()
            weg += 1
        except OSError:
            # Schon weg oder gesperrt. Die Indexzeile faellt trotzdem: sie zeigt
            # ohnehin nicht mehr auf ein Bild, das jemand ansehen kann.
            pass
    if weg:
        schreibe_atomar(
            Path(lauf) / INDEX,
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in bleiben),
        )
    return weg


def loesche_bilder(lauf, t_start, t_ende, rand_s=RAND_S):
    """Die Bilder eines Durchgangs loeschen, samt ihren Indexzeilen."""
    def behalten(satz):
        t = float(satz.get("t", -1))
        return not (t_start - rand_s <= t <= t_ende + rand_s)

    return _loesche(lauf, behalten)


def loesche_alle_bilder(lauf):
    """Alle Bilder des Laufs loeschen — nach dem letzten Eintrag."""
    return _loesche(lauf, lambda _satz: False)


# ---------------------------------------------------------------- Ansicht


def _zeile_text(zeile, bilder):
    zeit = "—" if zeile["laufzeit_s"] is None else f"{zeile['laufzeit_s']:.2f} s"
    tempo = "" if zeile["tempo_m_s"] is None else f", {zeile['tempo_m_s']:.2f} m/s"
    leute = "1 Person" if zeile["personen"] == 1 else f"{zeile['personen']} Personen"
    stand = "" if zeile["gueltig"] else f"  VERWORFEN ({' '.join(zeile['gruende']) or '—'})"
    eintrag = ""
    if zeile["gruppengroesse"] is not None or zeile["klasse"]:
        eintrag = (f"  [Klasse {zeile['klasse'] or '?'}, "
                   f"Gruppe {zeile['gruppengroesse'] or '?'}]")
    return (f"{zeile['nummer']:>3}  {zeile['uhrzeit']}  {leute}, {zeit}{tempo}"
            f"  {len(bilder)} Bilder{stand}{eintrag}")


def uebersicht(lauf):
    """Eine Textzeile je Durchgang — die Testtuer dieser Ansicht."""
    pfad = csv_pfad(lauf)
    if not pfad.is_file():
        raise SpotlabError(
            f"Keine Gehzeit-Tabelle in {lauf}. Erwartet: {pfad}. "
            "Erst den Versuch laufen lassen (Beispiele/gehzeit.py)."
        )
    return [
        _zeile_text(zeile, bilder_zu(lauf, zeile["t_start"], zeile["t_ende"]))
        for zeile in tabelle.lies(pfad)
    ]


def trage_ein(lauf, nummer, klasse=None, gruppengroesse=None):
    """Klasse und Gruppengroesse zu einem Durchgang. Nur diese beiden."""
    return tabelle.ergaenze(csv_pfad(lauf), nummer, klasse=klasse,
                            gruppengroesse=gruppengroesse)


# ------------------------------------------------------------ Hauptprogramm


def _offen(zeile):
    return zeile["gruppengroesse"] is None


def _hauptprogramm(argv=None, eingabe=input, drucke=print):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        drucke("Aufruf: python -m spotlab.experiment.nachtrag <Lauf-Verzeichnis>")
        return
    lauf = Path(argv[0])
    try:
        zeilen = tabelle.lies(csv_pfad(lauf))
    except (OSError, SpotlabError) as fehler:
        drucke(f"Keine Gehzeit-Tabelle: {fehler}")
        return

    for text in uebersicht(lauf):
        drucke(text)

    offen = [z for z in zeilen if _offen(z)]
    if not offen:
        drucke("Nichts offen — alle Durchgänge sind eingetragen.")
        return

    for zeile in offen:
        bilder = bilder_zu(lauf, zeile["t_start"], zeile["t_ende"])
        drucke("")
        drucke(f"Durchgang {zeile['nummer']} um {zeile['uhrzeit']}, "
               f"{zeile['personen']} gesehen, {len(bilder)} Bilder:")
        for pfad in bilder[:12]:
            drucke(f"    {pfad}")
        if len(bilder) > 12:
            drucke(f"    … und {len(bilder) - 12} weitere")
        klasse = (eingabe("Klasse (leer = überspringen): ") or "").strip()
        if not klasse:
            continue
        roh = (eingabe("Gruppengrösse: ") or "").strip()
        if not roh.isdigit():
            drucke("Keine Zahl — Durchgang übersprungen.")
            continue
        trage_ein(lauf, zeile["nummer"], klasse=klasse, gruppengroesse=int(roh))
        drucke(f"Eingetragen: Klasse {klasse}, Gruppe {roh}.")

    antwort = (eingabe("Bilder dieses Laufs jetzt löschen? [j/N] ") or "").strip().lower()
    if antwort.startswith("j"):
        drucke(f"{loesche_alle_bilder(lauf)} Bilder gelöscht.")
    else:
        drucke("Bilder bleiben liegen.")


if __name__ == "__main__":
    _hauptprogramm()
