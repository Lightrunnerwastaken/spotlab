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
- Alle Meldungen an Nutzer sagen, **was zu tun ist**, nicht nur was kaputt ist.

## Tests

- `pytest` — läuft ohne Roboter und ohne Netz.
- `dryrun` ist das Standard-Testdouble. Protobufs werden echt gebaut und gegen die
  SDK-Schemata geprüft (Methode aus `matura-spot/tests/test_sdk_commands.py`).
- Zeitabhängige Funktionen nehmen `schlaf`/`jetzt` als Parameter — Tests reichen
  Attrappen herein, kein Test wartet real.
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
