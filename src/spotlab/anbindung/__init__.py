"""Fremde Projekte an spotlab andocken.

Dieses Paket importiert nichts aus api/, backends/, maps/ oder gui/ und haelt
weder Lease-Client noch E-Stop-Endpunkt — dieselbe Bedingung, unter der maps/
von der GUI benutzt werden darf. spotlab.errors ist erlaubt: SpotlabError ist
der Fehlertyp, den CLI und GUI bereits abfangen.
"""
