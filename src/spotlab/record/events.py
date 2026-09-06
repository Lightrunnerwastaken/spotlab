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
        "angestossen",      # Übungsraum: Spot steht an einer Wand an (nur die Flanke)
        "ende",
    }
)

ERGEBNISSE = frozenset({"läuft", "ok", "fehler", "abgebrochen", "lease_verloren"})
