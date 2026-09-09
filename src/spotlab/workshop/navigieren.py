"""Navigieren: Wegpunkte im Karten-Tab anklicken, Spot fährt hin — der Kern.

Das Programm dazu ist `Beispiele/navigieren.py` im Arbeitsordner (Vorlage in
`workshop/beispiele/`), gestartet vom Knopf „🧭 Zu Wegpunkten fahren" im Tab
„Karten" — über denselben einen Startweg wie „Starten" im Editor, am echten
Spot, mit Lease, Not-Aus-Endpunkt und dem Tempodeckel aus `config.toml`
(`api/navigation.py::navigate_to` schickt ihn als `velocity_limit` mit).
Es muss im Arbeitsordner liegen, nicht im Paket: Läufe landen neben dem
Skript, nur dort findet der Watcher sie (dieselbe Lehre wie beim Fahren).

Der Ablauf:

    1. Karte laden (`SPOTLAB_KARTE` aus dem Tab, sonst die aktive Karte).
    2. Verorten -- ein AprilTag der Karte muss im Bild sein. Klappt es nicht,
       wird alle zwei Sekunden neu versucht, bis es klappt oder „Stopp" kommt;
       der Stand sagt der GUI derweil, woran es liegt.
    3. Warten auf `ziel.json` (die GUI schreibt es beim Klick), hinfahren,
       den Stand mit Lage nachführen, fertig melden -- und wieder warten.

Ein neuer Klick WÄHREND der Fahrt bricht die laufende Fahrt ab (Spot hält
kurz an) und fährt das neue Ziel. „Stopp" bricht ab und beendet den Lauf.
Ein Ziel, das nicht erreicht wird (verloren, Zeit um, unbekannter Wegpunkt),
beendet NICHT den Lauf: der Stand sagt es, der nächste Klick geht wieder.
"""

import os
import time
from pathlib import Path

from spotlab import ENV_KARTE
from spotlab.errors import SpotlabError
from spotlab.record import navigation as datei
from spotlab.record.run import STOPP_DATEI
from spotlab.workshop.beispiele import ORDNER

DATEINAME = "navigieren.py"
TAKT_S = 0.25                 # Wartetakt auf ein Ziel
VERORTEN_PAUSE_S = 2.0        # zwischen zwei Verortungsversuchen
ZIEL_FRIST_S = 180.0          # länger als jede Route auf einer Schulkarte


def skript_in(arbeitsordner):
    """Das Navigationsprogramm im Projekt Beispiele des Arbeitsordners."""
    return Path(arbeitsordner) / ORDNER / DATEINAME


def karte_aus_umgebung(umgebung=None):
    """Die Karte, die der Tab beim Start mitgegeben hat -- oder None (aktive Karte)."""
    return (os.environ if umgebung is None else umgebung).get(ENV_KARTE) or None


def _ortung(spot):
    """(standort, versatz) aus dem Backend -- oder (None, None), wenn es das nicht kann."""
    lesen = getattr(getattr(spot, "backend", None), "localization", None)
    if lesen is None:
        return None, None
    try:
        ortung = lesen()
    except Exception:
        return None, None
    return (None, None) if ortung is None else ortung


def navigiere(spot, lauf_dir, karte=None, jetzt=time.time, schlaf=time.sleep,
              laeuft=None, takt_s=TAKT_S, verorten_pause_s=VERORTEN_PAUSE_S,
              ziel_frist_s=ZIEL_FRIST_S):
    """Die Schleife: Karte, Verortung, dann Ziele aus `ziel.json`, bis `laeuft()` falsch ist.

    Testbar ohne Roboter: `spot` braucht `load_map`, `localize`, `navigate_to`
    und `stop`; `jetzt` und `schlaf` sind die Uhr.
    """
    lauf_dir = Path(lauf_dir)
    if laeuft is None:
        def laeuft():
            return not (lauf_dir / STOPP_DATEI).exists()

    name = karte

    def stand(status, text="", ziel=None):
        standort, versatz = _ortung(spot)
        datei.schreibe_stand(lauf_dir, status, text=text, karte=name, ziel=ziel,
                             standort=standort, versatz=versatz, jetzt=jetzt)

    stand("lade_karte")
    try:
        geladen = spot.load_map(karte)
    except SpotlabError as fehler:
        stand("gescheitert", text=str(fehler))
        raise
    name = getattr(geladen, "name", None) or karte

    while laeuft():
        try:
            spot.localize()
        except SpotlabError as fehler:
            stand("verorte", text=str(fehler))
            schlaf(verorten_pause_s)
            continue
        break
    else:
        stand("beendet")
        return
    stand("bereit")

    letzte_nr = None
    try:
        while laeuft():
            ziel = datei.lies_ziel(lauf_dir)
            if ziel is None or ziel[1] == letzte_nr:
                schlaf(takt_s)
                continue
            wegpunkt, letzte_nr = ziel
            stand("unterwegs", ziel=wegpunkt)

            def abbruch(wegpunkt=wegpunkt, nr=letzte_nr):
                # Je Nachsende-Takt: die Lage nachführen und nachsehen, ob es
                # ein neues Ziel gibt oder „Stopp" gedrückt wurde.
                stand("unterwegs", ziel=wegpunkt)
                neues = datei.lies_ziel(lauf_dir)
                return (not laeuft()) or (neues is not None and neues[1] != nr)

            try:
                angekommen = spot.navigate_to(wegpunkt, timeout=ziel_frist_s, abbruch=abbruch)
            except SpotlabError as fehler:
                stand("gescheitert", text=str(fehler), ziel=wegpunkt)
                continue
            if angekommen:
                stand("angekommen", ziel=wegpunkt)
            elif laeuft():
                stand("bereit", text="Neues Ziel — die laufende Fahrt wurde abgebrochen.")
    finally:
        spot.stop()
        stand("beendet")
