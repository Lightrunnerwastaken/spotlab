# spotlab

Programmiersystem für den Schul-Spot an der Kantonsschule. Entwurf und Begründungen:
`docs/superpowers/specs/2026-08-06-spotlab-fundament-design.md` ZUERST lesen.

Getrennt von `matura-spot` (Forschungsrepo) — Kopplung nur später als optionales,
versionsgepinntes Extra `spotlab[sim]`.

## Nicht verhandelbar

- **Der Abbau in `RealSpot.close()` läuft immer durch.** Jeder Schritt ist einzeln
  gekapselt; ein fehlgeschlagener Schritt darf die folgenden nicht verhindern. Jede
  Änderung daran braucht einen Test.
- **`EstopEndpoint.force_simple_setup()` ist verboten.** Es ersetzt laut eigenem
  Docstring die E-Stop-Konfiguration durch eine mit nur einem Endpunkt und verdrängt
  damit den Not-Aus des Tablets. Registrierung ausschliesslich über
  `backends/real/estop.py::register_coexisting`.
- **Lease wird mit `acquire` geholt, nie implizit mit `take`.** Übernahme ist eine
  bewusste, protokollierte Handlung.
- **`connect()` schaltet die Motoren nicht ein.** `power_on()` bleibt eine eigene Zeile
  im Schülerprogramm.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.**
  Die GUI hält nie ein Lease; sie liest Live-Daten aus dem Lauf-Verzeichnis.
- **Farben nur aus `gui/theme.py`.** Ein Farbliteral im Widget-Code bricht den zweiten
  Hell/Dunkel-Modus, ohne dass es auffällt.
- **`beende_hart` tötet nur einen Lauf, der nach `ist_aktiv()` noch lebt.** Prozess-IDs
  werden vom Betriebssystem wiederverwendet.
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von `src/spotlab/maps/`.**
  Aufzeichnen ist leaselos; nur deshalb darf die GUI es. Ein Lease dort bräche H1.
- **Autonome Fahrt bekommt immer `travel_params` mit `velocity_limit` aus der
  Konfiguration.** Ohne das führe ein Schüler autonom schneller als von Hand.
- **Das Kartenformat auf der Platte ist das des SDK.** Kein eigenes Format — sonst geht die
  Austauschbarkeit mit `graph_nav_command_line.py` und `view_map.py` verloren.
- **`errors/` darf nichts aus `backends/` importieren.** `backends/base.py` importiert
  `UnsupportedCapability` aus `errors`; die Gegenrichtung schliesst den Kreis, sobald
  `backends.base` zuerst geladen wird. Die Position der Importzeile hilft dagegen nicht.

## Regeln

- Kommandos ausschliesslich über `RobotCommandBuilder` — echte
  `bosdyn.api.RobotCommand`-Protobufs, keine parallele Eigen-API. Gleiche Regel wie in
  `matura-spot`; sie ist der Grund, warum der Sim-Adapter später ohne Umbau danebenpasst.
- **Python-Bezeichner englisch, Meldungen und Doku deutsch.** Ausnahmeklassen englisch
  (`UnsupportedCapability`), Meldungstext deutsch. Ausgenommen: Datei- und Feldnamen der
  Aufzeichnung sind deutsch (`lauf.json`, `ereignisse.jsonl`, Schlüssel `t`/`art`/`daten`).
- Die Aufzeichnung hängt an `connect()`, nicht am CLI. Wer das verschiebt, verliert alle
  Läufe, die aus VS Code heraus gestartet werden — also die meisten.
- `api/` bleibt protobuf-frei bis auf den `RobotCommandBuilder`. Rückmeldungen kommen als
  `backends.base.Feedback`, nicht als rohes Protobuf.
- Neue Fähigkeit ⇒ neuer Eintrag in `Capability`, Prüfung über `require()`, **und** ein
  neuer Punkt in `docs/ABNAHME.md`.
- Alle Meldungen an Nutzer sagen, **was zu tun ist**, nicht nur was kaputt ist. Und sie
  dürfen keine Ursache *behaupten*, die nicht geprüft ist — eine Meldung, die auf die
  falsche Fährte schickt, kostet mehr Zeit als gar keine.
- **Externe Programme immer erst mit `shutil.which()` auflösen, dann mit vollem Pfad
  starten.** Python startet über `CreateProcess`; das durchsucht den PATH, hängt aber nur
  `.exe` an und wertet `PATHEXT` nicht aus. `code.cmd` ist damit aus `subprocess` heraus
  unsichtbar, obwohl `code` in jeder Shell funktioniert.

## Tests

- `pytest` — läuft ohne Roboter und ohne Netz.
- `dryrun` ist das Standard-Testdouble. Protobufs werden echt gebaut und gegen die
  SDK-Schemata geprüft (Methode aus `matura-spot/tests/test_sdk_commands.py`).
- Zeitabhängige Funktionen nehmen `schlaf`/`jetzt` als Parameter — Tests reichen
  Attrappen herein, kein Test wartet real.
- **Wo ein externer Prozess im Spiel ist, braucht es mindestens einen Test, der ihn
  wirklich startet** (mit `skipif`, wenn das Programm fehlen darf). Attrappen-Tests prüfen
  nur, dass die richtigen Argumente gebaut werden — nicht, dass das Betriebssystem damit
  etwas anfangen kann. Genau daran ging „In VS Code öffnen" durch die ganze Suite.
- Was nur am Gerät prüfbar ist, gehört in `docs/ABNAHME.md`, nicht in einen Test, der
  Sicherheit bloss behauptet.
- Qt-Tests laufen mit `QT_QPA_PLATFORM=offscreen` (in `conftest.py` gesetzt) und werden
  ohne das Extra `[gui]` sauber übersprungen. **Im Offscreen-Modus gibt es keine
  Schriften** — gerenderte Bildschirmfotos zeigen Kästchen statt Text; das ist ein
  Artefakt, kein Fehler. Aussehen nur auf einem echten Desktop beurteilen.
- Widgets im Test in einer Variablen festhalten. Ein Wegwerf-Ausdruck wie
  `Header().hinweis.text()` wird sofort abgeräumt und wirft `libshiboken: Internal C++
  object already deleted`.
- Was nicht Widget ist, gehört in ein Qt-freies Modul — `record/tail.py`,
  `workshop/control.py`, `gui/theme.py`, `gui/watcher.py::RunScanner`.

## Umsetzungsstand

Fundament (Stufe 1+2) vollständig: Sitzungskern, Schülerbibliothek, Aufzeichnung,
Werkstatt-CLI. Offen und bewusst nicht gebaut: GUI, MCP-Server, Sim-Adapter,
NN-Anbindung, Mehrbenutzer-Dienst, Arm/GraphNav/Docking.
