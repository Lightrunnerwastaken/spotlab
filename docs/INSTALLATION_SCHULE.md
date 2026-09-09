# Spotlab für Schülerinnen und Schüler

1. Das **Schüler-Release-ZIP** herunterladen (nicht GitHubs „Source code“).
2. In einen dauerhaft beschreibbaren Ordner entpacken, etwa `Dokumente/Spotlab`.
3. `einrichten.cmd` doppelklicken und die Installation abwarten.
4. Spotlab über die Desktop-Verknüpfung starten. Programmiert wird in der GUI.

Einmalig erforderlich: Python 3.11–3.14 (vorzugsweise 3.13), Internetzugang für
die Paketinstallation und ein Grafiktreiber für die 3D-Ansicht. Python wird nicht
automatisch installiert. Bei Schulrichtlinien hilft die Schul-IT.

Installiert werden Spotlab, das Spot-SDK, Qt-GUI/Editor, MuJoCo, NumPy/SciPy,
Bild-/Grafikbibliotheken und das Spot-Robotermodell. **Kein Matura-Repository,
keine Forschungs-/Messskripte, kein pytest/Ruff und kein MCP-Zusatzpaket.**
Die Pakete liegen in der eigenen `.venv`; das System-Python bleibt unverändert.
Der Sim-Code ist als normales Python-Paket enthalten, keine verschlüsselte Software.

Die Einrichtung prüft Paketkonflikte und lädt das Sim-Modell ohne Roboterverbindung.
Beim ersten Start zusätzlich eine Sim-Vorlage in der GUI öffnen und die 3D-Ansicht
testen. Es werden durch die Einrichtung keine Motoren eingeschaltet.

## Updates

Nur vom Entwickler freigegebene Releases installieren. Die neue Version in einen
neuen Ordner entpacken und dort `einrichten.cmd` ausführen. Die Desktop-Verknüpfung
zeigt anschließend auf diese Version. Den bisherigen Arbeitsordner in der GUI
wieder auswählen; Schülerprogramme gehören nicht in den Installationsordner.
Den alten Installationsordner erst entfernen, wenn die neue Version funktioniert.

Die App und der Sim-Kern sind im ZIP auf dieselbe Release-Version festgelegt.
Weitere Bibliotheken werden innerhalb der Paket-Versionsgrenzen heruntergeladen;
ihre genauen Versionen können sich zwischen Installationen unterscheiden.
Das ZIP allein ist deshalb **kein vollständiger Offline-Installer**.

Zugangsdaten zum echten Spot werden je Rechner separat eingerichtet. Für das
Programmieren im Sim ist kein Zugang zum echten Spot nötig.
