"""Erlaubte Ereignis- und Ergebnisarten der Aufzeichnung.

Die Schlüssel sind bewusst deutsch (t/art/daten), die eingebetteten
SDK-Nutzlasten behalten ihre englischen Feldnamen.
"""

ARTEN = frozenset(
    {
        "verbunden",
        "power_on",
        "power_off",
        "kommando",
        "rückmeldung",
        "bild",
        "messfenster",
        "fehler",
        "lease_verloren",
        "lease_übernommen",
        "kein_ziel",        # Folgemodus: der Finder liefert nichts (mit seit_s, je_gesehen)
        "geste",            # Folgemodus: eine Handgeste (halt/weiter) und ob Spot danach steht
        "ziel",             # Folgemodus: was der Finder in diesem Takt lieferte (oder einmal: weg)
        "angestossen",      # Übungsraum: Spot steht an einer Wand an (nur die Flanke)
        "treppe_verweigert",  # Übungsraum: Treppe falsch herum (Nase bergab), nur die Flanke
        "ende",
    }
)

ERGEBNISSE = frozenset({"läuft", "ok", "fehler", "abgebrochen", "lease_verloren"})
