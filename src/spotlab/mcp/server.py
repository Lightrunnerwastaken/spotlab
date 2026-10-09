"""Der stdio-Server.

Er meldet die Funktionen aus werkzeuge.py beim Protokoll an und tut sonst
nichts. Alle Fachlogik liegt dort — deshalb ist sie ohne Server pruefbar, und
deshalb kostet eine Aenderung am Protokoll-Paket hier nur diese Datei.

Braucht weder GUI noch Roboter, nur den Arbeitsordner. Die Werkzeuge zum Fahren
(`fahren.py`, Agenten am Spot Teil 1) sprechen nur mit der Steuerzentrale, nie mit dem
Roboter selbst.
"""

import functools

from spotlab.mcp import fahren, werkzeuge

# Reihenfolge wie in der Spec: anbinden, ausfuehren, lesen.
WERKZEUGE = (
    (werkzeuge.projekt_anbinden,
     "Bindet ein fremdes Projekt an spotlab an. Erwartet den Pfad zum Ordner, in dem "
     "die spotlab.toml liegt."),
    (werkzeuge.anbindungen_auflisten,
     "Nennt alle angebundenen Projekte mit ihren Skripten und Panelnamen."),
    (werkzeuge.projekt_loesen,
     "Loest die Anbindung eines Projekts. Entfernt nur die Manifestkopie und die "
     "Panels unter dem Arbeitsordner; das Projekt selbst bleibt unberuehrt."),
    (werkzeuge.panel_setzen,
     "Schreibt oder ersetzt ein Panel in der Ansicht „Anbindungen“. Arten: kennzahlen "
     "(Liste aus name/wert/hinweis), tabelle (spalten/zeilen), reihe (x/y), bild (pfad), "
     "text (absaetze)."),
    (werkzeuge.panel_entfernen,
     "Entfernt ein Panel eines angebundenen Projekts."),
    (werkzeuge.skript_starten,
     "Startet ein im Manifest registriertes Skript. Der Lauf ist IMMER ohne Roboter: "
     "ein Trockenlauf, ausser das Skript waehlt selbst eine Simulation; Skripte mit "
     "roboter=true werden abgelehnt."),
    (werkzeuge.lauf_stoppen,
     "Beendet einen laufenden Lauf freundlich — der Spot setzt sich hin."),
    (werkzeuge.laeufe_auflisten,
     "Nennt die neuesten Läufe, wahlweise nur die eines angebundenen Projekts."),
    (werkzeuge.lauf_lesen,
     "Metadaten, Ergebnis und Dateipfade eines Laufs. Gibt bewusst keine Messdaten "
     "zurück — die Reihen liest man mit eigenen Dateiwerkzeugen unter den genannten Pfaden."),
    (werkzeuge.zustand_zusammenfassen,
     "Dauer, Strecke, Spitzentempo, Akku und vor allem die Abtastlücken einer "
     "Zustandsreihe. Grundlage für den Vergleich echter Läufe mit Simulationen."),
    (werkzeuge.karten_auflisten,
     "Nennt die aufgezeichneten GraphNav-Karten."),
    (werkzeuge.karte_lesen,
     "Wegpunkte und Kanten einer Karte als Grundriss."),
    (werkzeuge.spot_pruefen,
     "Prüft Netz, Anmeldung, Zeitsync, Not-Aus, Lease und Akku — wie `spotlab doctor`."),
) + tuple((getattr(fahren, name), beschreibung) for name, beschreibung in (
    # Agenten am Spot, Teil 1: sehen und fahren über die Steuerzentrale.
    ("zentrale_starten",
     "Startet die Steuerzentrale, über die du Spot siehst und fährst. ort: \"2d\" (Zeichnung), "
     "\"3d\" (Übungsraum mit Körper), \"physik\" (Kraftregler, nur ebene Räume) oder \"echt\" "
     "(der echte Spot). raum: Name des Übungsraums (sonst der aus der Konfiguration). Am echten "
     "Spot bleiben die Motoren aus, bis ein Mensch im Tab „Fahren“ „🤖 Agent darf fahren“ "
     "einschaltet. Wartet höchstens 30 s, bis das erste Lagebild da ist."),
    ("zentrale_status",
     "Läuft eine Zentrale? Ort, Lauf, ob sie antwortet, Motoren, Freigabe und welcher Agent "
     "gerade steuert."),
    ("zentrale_beenden",
     "Beendet die Zentrale freundlich: Spot hält an und setzt sich, die Verbindung wird "
     "abgebaut. Wartet bis zum Ende."),
    ("lage",
     "Die Lage als JSON: Spots Pose (x, y in Metern, blick_grad), Tempo, Akku, Motoren, Freigabe; "
     "die freie Strecke in 8 Richtungen relativ zu Spots Blick (0° voraus, +90° links, -90° "
     "rechts, 180° hinten): frei bis X m, dann Wand oder unbekannt; Kopfraum (hängt etwas über "
     "dem Weg?); Menschen und AprilTags mit Peilung und Abstand zu Spot und in Weltkoordinaten; "
     "der Stand deines letzten Befehls. Koordinaten im Rahmen „vision“: Meter, gilt für diesen "
     "Lauf, driftet langsam; 0° = +x, positive Grad nach links."),
    ("skizze",
     "Die Draufsicht um Spot als Bild (radius_m, Vorgabe 5): oben = +y, rechts = +x, Raster "
     "1 m; weiss frei, schwarz Wand, grau unbekannt; roter Pfeil Spot, blau Tags, orange "
     "Menschen, grün der Weg der laufenden Fahrt."),
    ("kamerabild",
     "Das Bild des Laufs: am echten Spot der Blick der beiden Frontkameras; im 3D-Übungsraum das "
     "Zimmer von AUSSEN (keine Roboterkamera); im 2D-Übungsraum gibt es keines."),
    ("tiefe_messen",
     "Misst mit den Tiefenkameras vorne die Abstände links, mitte (±10°) und rechts "
     "(5. Perzentil, Meter) und den Kopfraum. Ohne Tiefenkameras (Übungsraum): „nicht messbar“."),
    ("fahre_zu",
     "Fährt zum Punkt (x, y) in Metern im Rahmen „vision“ — über gesehenen Boden, mit "
     "Wegsuche um Hindernisse, langsam, höchstens 5 m weit, mit allen Schranken. warum: kurze "
     "Begründung (Pflicht, wird aufgezeichnet). Wartet bis 30 s; antwortet angekommen, "
     "abgelehnt, versperrt, abgebrochen (mit Grund) oder „läuft noch“."),
    ("fahre_relativ",
     "Fährt zu einem Punkt vor_m voraus und links_m links von Spot (negativ = zurück/rechts) — "
     "sonst wie fahre_zu. warum ist Pflicht."),
    ("drehe",
     "Dreht auf der Stelle um grad (positiv = links, gegen den Uhrzeiger), fertig auf 3° genau, "
     "höchstens 15 s. warum ist Pflicht."),
    ("stoss",
     "Ein kurzer Fahrstoss: vx vor/zurück und vy links/rechts in m/s, wz Drehrate in rad/s "
     "(+ links), dauer_s höchstens 2. Vorwärts mit den Schranken der Klickfahrt; seitwärts und "
     "rückwärts höchstens 0.2 m/s und nur über gesehenen Boden. warum ist Pflicht."),
    ("folge_mensch",
     "Folgt dem Menschen bei (x, y) (aus lage()) mit dem Folgemodus, bis ein neuer Befehl, "
     "stopp oder ein Mensch übernimmt. Braucht Bild- und Tiefenkameras. warum ist Pflicht."),
    ("stopp",
     "Hält sofort an und beendet deinen laufenden Befehl. Darf jeder Agent."),
    ("warten",
     "Wartet auf das Ende des laufenden Befehls (höchstens sekunden, ≤ 10) und gibt dann "
     "Befehlsstand und lage() zurück."),
    ("licht", "Setzt die LEDs am Kopf: aus, blau, gruen, gelb oder rot (nur am echten Spot)."),
    ("piep", "Ein kurzer Ton am Roboter (nur am echten Spot)."),
    ("suche",
     "Die Menschensuche der Zentrale: aus, sparsam, normal oder rundum (braucht Bild- und "
     "Tiefenkameras); gefundene Menschen stehen danach in lage()."),
))


def baue_server():
    """Legt den Server an und meldet die Werkzeuge an.

    Der Import steht in der Funktion: `spotlab mcp` soll ohne das Extra eine
    verstaendliche Meldung geben, und WERKZEUGE muss auch ohne `mcp` pruefbar
    bleiben.
    """
    from mcp.server import MCPServer

    from spotlab import __version__

    # NICHT noch einmal hingeschrieben: die Fassung stand hier als "0.1.0"
    # fest und waere beim naechsten Sprung stumm falsch geblieben. Ein
    # Agent, der ueber MCP spricht, sieht dann eine Zahl, die nichts mit dem
    # Stand zu tun hat, mit dem er redet.
    server = MCPServer("spotlab", version=__version__)
    for funktion, beschreibung in WERKZEUGE:
        server.add_tool(_mit_bild(funktion), name=funktion.__name__, description=beschreibung)
    return server


def _mit_bild(funktion):
    """Eine `fahren.Bildantwort` wird ein MCP-Bild samt Text; alles andere bleibt, wie es ist.

    Der Import steht in der Hülle: WERKZEUGE muss ohne das Extra `mcp` lesbar bleiben."""

    @functools.wraps(funktion)
    def huelle(*args, **kwargs):
        antwort = funktion(*args, **kwargs)
        if isinstance(antwort, fahren.Bildantwort):
            from mcp.server.mcpserver import Image

            return [Image(data=antwort.daten, format=antwort.format), antwort.text]
        return antwort

    return huelle


def main():
    baue_server().run(transport="stdio")
    return 0
