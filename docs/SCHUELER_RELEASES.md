# Schüler-Releases bauen (Entwickler)

Schüler erhalten das erzeugte Release-ZIP, keine Quellcode-Archive der Repositories.
`einrichten.ps1` installiert standardmäßig GUI + Sim aus den enthaltenen Wheels.
Für deine bisherige Entwicklungsumgebung gilt jetzt:

```powershell
.\einrichten.cmd -Entwickler -MitSim -SimPfad ..\matura-spot
```

## Release bauen

App-Version in `src/spotlab/__init__.py` vor jeder Veröffentlichung erhöhen.
Claude/andere laufende Änderungen abschließen und Tests durchführen. Die
Build-Umgebung benötigt `pip`, `setuptools>=68` und `wheel`.

```powershell
python tools/schueler_release.py --sim-quelle ..\matura-spot --ausgabe dist
```

Der Builder erstellt ein App-Wheel und `spotlab-sim-runtime` mit derselben Version.
Eine explizite Modulliste umfasst Wiedergabe, Sensoren und die verwendete Physik;
unbekannte statische `spotsim`-Importe brechen den Build ab. Explorer, Gates,
Messwerkzeuge, Tests, Notizen und Aufzeichnungen werden nicht kopiert. Benötigte
Modelldateien folgen den XML-Referenzen; Arm-Assets bleiben draußen. Modell-Lizenz
und SHA-256-Herkunft der Sim-Quelldateien sind im Runtime-Wheel enthalten.
Die Runtime stellt den bisherigen `spotsim`-Import bereit; nicht zusätzlich zur
editierbaren Forschungsinstallation in dieselbe Umgebung installieren.

Das fertige ZIP enthält Installer, Startskripte, Icon, Anleitung, zwei Wheels und
ein Manifest. Die Quellen für den App-Build werden zuerst in einen temporären
Ordner kopiert: der Build verändert das Arbeitsrepository nicht.
Ein vorhandenes gleichnamiges Release wird nicht überschrieben.

## Abnahme vor Veröffentlichung

ZIP in einen neuen Ordner entpacken. `einrichten.cmd` mit Internetzugang ausführen;
bei automatischer Prüfung `einrichten.ps1 -KeineVerknuepfung` verwenden. Ohne
Repository-/Conda-Pfade im `PYTHONPATH` GUI und 3D-Sim testen. `pip check`, Import
und Modellaufbau prüft der Installer selbst; Grafiktreiber und Bedienablauf brauchen
den GUI-Test. Paketliste mit `.venv/Scripts/python -m pip freeze` archivieren.
Release-ZIP anschließend als GitHub-Release-Anhang veröffentlichen.

Das ZIP enthält noch keine Drittanbieter-Wheels oder Python. Downloadmenge und
Speicherbedarf deshalb an einer frischen Installation messen und mit Version,
Python-Version und Plattform dokumentieren. Build allein ist keine Freigabe.
