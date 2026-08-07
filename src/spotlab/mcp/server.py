"""Der stdio-Server.

Er meldet die Funktionen aus werkzeuge.py beim Protokoll an und tut sonst
nichts. Alle Fachlogik liegt dort — deshalb ist sie ohne Server pruefbar, und
deshalb kostet eine Aenderung am Protokoll-Paket hier nur diese Datei.

Braucht weder GUI noch Roboter, nur den Arbeitsordner.
"""

from spotlab.mcp import werkzeuge

# Reihenfolge wie in der Spec: anbinden, ausfuehren, lesen.
WERKZEUGE = (
    (werkzeuge.projekt_anbinden,
     "Bindet ein fremdes Projekt an spotlab an. Erwartet den Pfad zum Ordner, in dem "
     "die spotlab.toml liegt."),
    (werkzeuge.anbindungen_auflisten,
     "Nennt alle angebundenen Projekte mit ihren Skripten und Panelnamen."),
    (werkzeuge.panel_setzen,
     "Schreibt oder ersetzt ein Panel in der Ansicht „Anbindungen“. Arten: kennzahlen "
     "(Liste aus name/wert/hinweis), tabelle (spalten/zeilen), reihe (x/y), bild (pfad), "
     "text (absaetze)."),
    (werkzeuge.panel_entfernen,
     "Entfernt ein Panel eines angebundenen Projekts."),
    (werkzeuge.skript_starten,
     "Startet ein im Manifest registriertes Skript. Der Lauf ist IMMER ein Trockenlauf "
     "ohne Roboter; Skripte mit roboter=true werden abgelehnt."),
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
)


def baue_server():
    """Legt den Server an und meldet die Werkzeuge an.

    Der Import steht in der Funktion: `spotlab mcp` soll ohne das Extra eine
    verstaendliche Meldung geben, und WERKZEUGE muss auch ohne `mcp` pruefbar
    bleiben.
    """
    from mcp.server import MCPServer

    server = MCPServer("spotlab", version="0.1.0")
    for funktion, beschreibung in WERKZEUGE:
        server.add_tool(funktion, name=funktion.__name__, description=beschreibung)
    return server


def main():
    baue_server().run(transport="stdio")
    return 0
