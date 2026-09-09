# Beispiele

Dieser Ordner kommt von spotlab. Du darfst alles darin ändern — deine Fassung
bleibt. Löschst du eine Datei, kommt das Original beim nächsten Start wieder.

| Datei | Was sie zeigt |
|---|---|
| `hallo_spot.py` | aufstehen, ein Meter vorwärts, ein Bild, eine Drehung |
| `uebungsraum.py` | im gezeichneten Zimmer fahren, Tags und Hindernisgitter lesen |
| `durchgang_finden.py` | mit den Sensoren eine Tür finden, in den nächsten Raum gehen, absitzen |
| `treppe_steigen.py` | die Treppe mit `spot.stairs()` finden, vorwärts hinauf, rückwärts hinunter |
| `fahren.py` | selbst fahren: W/S, A/D, Q/E im Übungsfenster — der Knopf „🎮 Fahren" startet es |

Starten: Datei öffnen, über dem Editor „Wo läuft es?" wählen, ▶ Starten.
Für `durchgang_finden.py` vorher im Raumeditor den Raum `durchgang` wählen,
für `treppe_steigen.py` den Raum `treppe`.

Weitere Python-Beispiele: `zustand_lesen.py`, `umgebung_lesen.py`,
`licht_und_ton.py` und `koerper_ausrichten.py`. Die letzten beiden pruefen im
Trockenlauf nur Kommandos; in Sim/MuJoCo melden sie fehlende Unterstuetzung.
Die vollstaendige Referenz steht im Projekt unter `docs/API.md`, die
SDK-Abdeckungsmatrix unter `docs/EXAMPLE_COVERAGE.md`.

Quantitative Wahrnehmung: `tiefenbild_lesen.py`, `punktwolke_speichern.py`,
`localgrids_lesen.py`. Export unter `auswertung/` neben dem Skript (erneuter Lauf
ersetzt diese Beispiel-Exporte); Originalaufnahmen bleiben im jeweiligen Lauf
unter `sensoren/`. Tiefe/Punktwolken brauchen real oder MuJoCo. Weitere
LocalGrid-Ebenen wie terrain werden derzeit nur am echten Spot abgefragt.

`physik_gehen.py`: Stand, Gehen und Stopp mit dem experimentellen Physikmodus.
Dafuer einen ebenen Raum ohne Hoehenflaechen waehlen. Kein Sitzbefehl;
Treppen sind in dieser ersten Version noch nicht unterstuetzt.


Experimenteller Einzelstufenversuch: `physik_einzelstufe.py` mit Raum
`physik_einzelstufe` und Start `(0, 0, 0)` im Modus **Physik 3D**.
6-cm-Podest vorwärts hinauf, rückwärts herunter; mehrere Minuten Laufzeit.
Grenzen und Messwerte: Projektdatei `docs/PHYSICS.md`.


Neu: `physik_treppe_3stufen.py` mit Raum `physik_treppe_3stufen`,
Physik 3D und Start `(0,0,0)`: drei niedrige 4-cm-Stufen vorwärts hinauf und
rückwärts herunter. Etwa 7–12 Minuten; Grenzen und Messwerte in `docs/PHYSICS.md`.
