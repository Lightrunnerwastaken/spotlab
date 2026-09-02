"""„Spot, was siehst du gerade?" — eine Abfrage, kein Kommando.

Die Sonde haelt KEIN Lease und bewegt nichts. `WorldObjectClient` und
`LocalGridClient` sind reine Lesedienste; sie funktionieren neben einem fremden
Lease, etwa waehrend das Tablet fuehrt. Genau das macht sie zum Werkzeug fuer den
Moment VOR einem Lauf: erkennt Spot den Tag ueberhaupt, und wie weit reicht das?

Dieselbe Begruendung wie beim Beobachter-Modus — deshalb ist die Sonde vor
Abnahmepunkt A1 benutzbar.

Dass hier nichts bewegt wird, ist nicht nur behauptet: `tests/test_sonde.py`
haelt als Gate fest, dass dieses Modul keine Bewegungsfunktion aufruft.
"""

import time

from spotlab.errors import SpotlabError, UnsupportedCapability

DAUER_S = 5.0
HZ = 2.0


def sonde(spot, dauer_s=DAUER_S, hz=HZ, schlaf=time.sleep, jetzt=time.monotonic):
    """Fragt `dauer_s` lang mit `hz` die Umgebung ab und fasst zusammen.

    Je Objekt wird die NAECHSTE Sichtung behalten, nicht die letzte: wer wissen
    will, ob ein Tag in Reichweite kommt, interessiert sich fuer den besten
    Moment, nicht fuer den Zufall der letzten Abtastung.
    """
    ende = jetzt() + dauer_s
    takt = 1.0 / hz if hz > 0 else 0.0
    abtastungen = 0
    gesehen = {}
    letztes_gitter = None

    while jetzt() < ende:
        abtastungen += 1
        for objekt in spot.world_objects():
            schluessel = (objekt.kind, getattr(objekt, "id", objekt.name))
            vorher = gesehen.get(schluessel)
            if vorher is None or objekt.distance < vorher.distance:
                gesehen[schluessel] = objekt
        try:
            letztes_gitter = spot.obstacles()
        except (UnsupportedCapability, SpotlabError):
            # Ein Backend ohne Gitter ist kein Fehlschlag der Sonde — die
            # Objekte sind der Hauptzweck. Die Sim kann zum Beispiel keines.
            letztes_gitter = None
        schlaf(takt)

    return {
        "abtastungen": abtastungen,
        "objekte_gesehen": len(gesehen),
        "objekte": sorted(gesehen.values(), key=lambda o: o.distance),
        "gitter": letztes_gitter,
    }


def _bericht(ergebnis, drucke=print):
    drucke(f"{ergebnis['abtastungen']} Abtastungen, "
           f"{ergebnis['objekte_gesehen']} Objekte gesehen.")
    for objekt in ergebnis["objekte"]:
        kennung = getattr(objekt, "id", objekt.name)
        drucke(f"  {objekt.kind} {kennung}: "
               f"{objekt.distance:.2f} m, {objekt.bearing:+.0f} Grad")
    if ergebnis["gitter"] is None:
        drucke("  (kein Hindernisgitter — dieses Backend fuehrt keines)")


def _hauptprogramm():
    """Als Skript ueber `workshop/launcher.py` gestartet — schreibt einen Lauf.

    Das Lauf-Verzeichnis wird AUSDRUECKLICH gesetzt. Die uebliche Herleitung
    (`<skriptordner>/runs/`) taugt hier nicht: dieses Skript liegt im
    installierten Paket, und Laeufe gehoeren nicht dorthin. Die GUI startet die
    Sonde im Arbeitsordner, damit landen sie neben den anderen Laeufen.
    """
    import os
    from pathlib import Path

    import spotlab

    runs = os.environ.get("SPOTLAB_RUNS_DIR") or (Path.cwd() / "runs")
    with spotlab.connect(runs_dir=runs, script=__file__) as spot:
        ergebnis = sonde(spot)
    _bericht(ergebnis)


if __name__ == "__main__":
    _hauptprogramm()
