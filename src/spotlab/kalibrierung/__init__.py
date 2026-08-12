"""Was der echte Spot tatsächlich tut — als Datengrundlage für das Sim-Backend.

Hier wird nichts hergeleitet und nichts modelliert. Was in `daten/` liegt, ist
aus echten Messfahrten herausgezogen und trägt seine Herkunft mit: Lauf-IDs,
Datum, Zahl der ausgewerteten Gangzyklen.

Abhängigkeiten wie `messung/`: kein `bosdyn`, kein Qt, nichts aus `api/`,
`backends/` oder `gui/`. Die Kennlinie ist eine Datei, kein Roboter.
"""
