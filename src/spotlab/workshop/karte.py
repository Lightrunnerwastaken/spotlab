"""Eine gespeicherte Karte nachbearbeiten — Schleifen schliessen, Anker optimieren.

Das Programm dazu ist `Beispiele/karte_verbessern.py` im Arbeitsordner,
gestartet vom Knopf „✨ Karte verbessern" im Tab „Karten" — über denselben einen
Startweg wie „Starten", „Fahren" und die Navigation.

Warum ein LAUF und nicht die GUI: die Karte muss dafür auf den Roboter, und
**Hochladen braucht ein Lease** (`UploadGraphRequest.lease`). Die GUI hält nie
eines (H1). Das Nachbearbeiten selbst und das Herunterladen brauchen keines —
deshalb macht die frische Aufnahme es leaselos gleich mit
(`maps/session.py::nachbearbeiten`), und nur die nachträgliche Runde für eine
alte Karte geht diesen Weg hier.

Spot bewegt sich dabei NICHT. Er lädt, rechnet und gibt zurück.
"""

import os
from pathlib import Path

from spotlab import ENV_KARTE
from spotlab.workshop.beispiele import ORDNER

DATEINAME = "karte_verbessern.py"


def skript_in(arbeitsordner):
    """Das Programm im Projekt Beispiele des Arbeitsordners."""
    return Path(arbeitsordner) / ORDNER / DATEINAME


def karte_aus_umgebung(umgebung=None):
    """Die Karte, die der Tab beim Start mitgegeben hat — oder None (aktive Karte)."""
    return (os.environ if umgebung is None else umgebung).get(ENV_KARTE) or None


def verbessere(spot, karte=None, melde=print, fiducial=True, odometrie=True):
    """Laden, nachbearbeiten, zurückschreiben. Gibt den Bericht zurück."""
    geladen = spot.load_map(karte)
    melde(f'Karte „{geladen.name}“ ist auf dem Spot: '
          f'{len(geladen.graph.waypoints)} Wegpunkte, {len(geladen.graph.edges)} Kanten.')
    bericht = spot.process_map(melde=melde, fiducial=fiducial, odometry=odometrie)
    if not bericht.gelaufen:
        melde("Nichts nachbearbeitet — die gespeicherte Karte bleibt, wie sie war.")
    return bericht
