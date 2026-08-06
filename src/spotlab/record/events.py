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
        "fehler",
        "lease_verloren",
        "lease_übernommen",
        "ende",
    }
)

ERGEBNISSE = frozenset({"läuft", "ok", "fehler", "abgebrochen", "lease_verloren"})
