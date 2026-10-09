"""Der stdio-Server.

Er meldet die Funktionen aus werkzeuge.py beim Protokoll an und tut sonst
nichts. Alle Fachlogik liegt dort — deshalb ist sie ohne Server pruefbar, und
deshalb kostet eine Aenderung am Protokoll-Paket hier nur diese Datei.

Braucht weder GUI noch Roboter, nur den Arbeitsordner. Die Werkzeuge zum Fahren
(`fahren.py`, Agenten am Spot Teil 1) sprechen nur mit der Steuerzentrale, nie mit dem
Roboter selbst; ebenso die Werkzeuge für Karten und Merkorte (`karten.py`, Teil 2).
"""

import functools

from spotlab.mcp import fahren, karten, werkzeuge

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
     "Läuft eine Zentrale? Ort, Lauf, ob sie antwortet, Motoren, Freigabe, welcher Agent "
     "gerade steuert und die geladene Karte (am echten Spot)."),
    ("zentrale_beenden",
     "Beendet die Zentrale freundlich: Spot hält an und setzt sich, die Verbindung wird "
     "abgebaut. Wartet bis zum Ende."),
    ("lage",
     "Die Lage als JSON: Spots Pose (x, y in Metern, blick_grad), Tempo, Akku, Motoren, Freigabe; "
     "die freie Strecke in 8 Richtungen relativ zu Spots Blick (0° voraus, +90° links, -90° "
     "rechts, 180° hinten): frei bis X m, dann Wand oder unbekannt; Kopfraum (hängt etwas über "
     "dem Weg?); Menschen und AprilTags mit Peilung und Abstand zu Spot und in Weltkoordinaten; "
     "der Stand deines letzten Befehls; die Karte (Name, Zustand, verortet die nächsten BENANNTEN "
     "Wegpunkte) und deine Merkorte, beide mit Peilung und Abstand. Koordinaten im Rahmen „vision“: "
     "Meter, gilt für diesen Lauf, driftet langsam; 0° = +x, positive Grad nach links."),
    ("skizze",
     "Die Draufsicht um Spot als Bild (radius_m, Vorgabe 5): oben = +y, rechts = +x, Raster "
     "1 m; weiss frei, schwarz Wand, grau unbekannt; roter Pfeil Spot, blau Tags, orange "
     "Menschen, grün der Weg der laufenden Fahrt, violette Rauten Merkorte, türkise Punkte die "
     "benannten Wegpunkte der verorteten Karte."),
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
)) + tuple((getattr(karten, name), beschreibung) for name, beschreibung in (
    # Agenten am Spot, Teil 2: Karten (nur am echten Spot), Merkorte (überall), Rekonstruktion.
    ("karte_laden",
     "Nur am echten Spot (GraphNav): lädt eine gespeicherte Karte (Name aus karten_auflisten) "
     "auf den Roboter und verortet Spot darin. Wartet bis 30 s; karte.zustand „verortet“ oder "
     "„sucht_tag“ (dann einen AprilTag der Karte ins Bild drehen), sonst abgebrochen mit Grund."),
    ("aufnahme_starten",
     "Nur am echten Spot: beginnt eine Kartenaufnahme. Ist Spot in einer geladenen Karte "
     "verortet, wird sie weitergeführt, sonst beginnt eine neue. name: Wunschname (optional)."),
    ("aufnahme_beenden",
     "Nur am echten Spot: beendet die Aufnahme, bearbeitet sie nach und speichert sie unter "
     "einem FREIEN Namen (nie überschrieben). Wartet bis 120 s; karte.gespeichert_als nennt ihn."),
    ("wegpunkt_setzen",
     "Nur am echten Spot und nur während einer Aufnahme: setzt an Spots Ort einen benannten "
     "Wegpunkt, zu dem zum_wegpunkt später fährt."),
    ("zum_wegpunkt",
     "Nur am echten Spot, Karte geladen und verortet: fährt mit GraphNav zu einem BENANNTEN "
     "Wegpunkt der Karte (lage() nennt die nächsten mit Peilung und Abstand) — mit Tempodeckel, "
     "braucht die Freigabe. warum ist Pflicht. Antworten wie fahre_zu."),
    ("merkort_setzen",
     "Merkt sich einen Ort mit Namen — im Übungsraum und am echten Spot. Ohne x/y Spots "
     "jetziger Ort, sonst (x, y) in Metern im Rahmen „vision“. Ein vorhandener Name wird "
     "verschoben. Im Übungsraum bleiben Merkorte beim Raum gespeichert, am echten Spot nur bis "
     "zum Ende der Zentrale."),
    ("merkort_loeschen", "Vergisst einen Merkort (lage() nennt alle)."),
    ("zum_merkort",
     "Fährt zum Merkort mit der Wegsuche über den ganzen gesehenen Boden (ohne die 5-m-Grenze "
     "von fahre_zu), mit allen Schranken. warum ist Pflicht. Antworten wie fahre_zu."),
    ("raum_aus_karte",
     "Baut aus einer gespeicherten Karte einen Raum für den Übungsraum (Wände, Treppen, Rampen, "
     "Tags) und speichert ihn samt Pauspapier unter einem FREIEN Namen (name optional). Braucht "
     "keine Zentrale. Danach im Raumeditor korrigieren, dann zentrale_starten(\"3d\", raum=…)."),
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
