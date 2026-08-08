"""Auswertung einer Aufzeichnung — Qt-frei, SDK-frei.

Dieses Paket liest nur Dateien von der Platte und rechnet. Es importiert nichts
aus api/, backends/ oder gui/ und kein bosdyn; spotlab.record.read ist erlaubt,
weil es selbst SDK-frei ist.

spotlab liefert Messwerte, nicht Urteile: die Kriterien der Realismus-Gates
liegen in matura-spot, und spotlab darf davon nicht abhaengen.
"""
