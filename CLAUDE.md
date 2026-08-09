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
  werden vom Betriebssystem wiederverwendet. Der Rückgabewert ist eine Aussage über den
  **Prozess**, nicht über den Knopfdruck: der Killer meldet, ob er getroffen hat. `False`
  hat zwei sehr verschiedene Bedeutungen — nichts zu töten (harmlos) und Töten gescheitert
  (gefährlich). Die GUI muss sie trennen; eine Entwarnung im zweiten Fall wäre schlimmer
  als gar keine Meldung.
- **Der Abbau legt `ABBAU_DATEI` an, und `ist_aktiv()` liest sie.** Der Abtaster ist das
  Lebenszeichen und hört beim Stopp als Erstes auf, während `close()` noch bis zu 20 s
  läuft (`power_off(timeout_sec=20)`). Ohne die Markierung gilt der Lauf in genau diesem
  Fenster als tot, und der NOT-AUS-Knopf trifft niemanden — obwohl der Spot noch unter
  Strom steht. Ein **ausdrückliches Merkmal**, kein grosszügigeres Zeitfenster: ein
  abgestürzter Prozess kommt nie dazu, die Datei anzulegen, und die Prozess-ID-Regel
  bleibt dadurch unberührt.
- **`RealSpot.close()` fängt je Schritt `BaseException` und wirft einen Abbruch erst am
  Ende.** Nur `Exception` zu fangen liess Strg-C aus dem ersten Abbauschritt herausspringen:
  Motoren blieben an, und der Spot fiel beim Wegfallen der Keepalives aus dem STAND um,
  statt sich hinzusetzen. Verschlucken ist ebenso falsch — der Lauf würde als „ok" verbucht.
  In `spotlab.connect()` steht `abtaster.stop()` aus demselben Grund **innerhalb** des
  `try`, das `spot.close()` und `recorder.finish()` schützt.
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von `src/spotlab/maps/`.**
  Aufzeichnen ist leaselos; nur deshalb darf die GUI es. Ein Lease dort bräche H1.
- **Autonome Fahrt bekommt immer `travel_params` mit `velocity_limit` aus der
  Konfiguration.** Ohne das führe ein Schüler autonom schneller als von Hand.
- **Das Kartenformat auf der Platte ist das des SDK.** Kein eigenes Format — sonst geht die
  Austauschbarkeit mit `graph_nav_command_line.py` und `view_map.py` verloren.
- **`editor/` darf nichts aus `api/`, `backends/` oder `maps/` importieren und nichts
  ausserhalb der Standardbibliothek.** `api/spot.py` zieht über `motion`/`posture`/`state`/
  `perception` bosdyn, numpy und Pillow herein; für `editor/verbs.py` ist `api/spot.py`
  **Text, keine Schnittstelle** — gelesen mit `ast`, nicht importiert. Ein Import wäre der
  bequeme Weg zur Introspektion und würde den Editor an das SDK ketten.
  `tests/test_editor_verbs.py` hält das in einem Unterprozess fest.
- **Es gibt genau einen `OutputReader` pro Lauf.** Die Ausgabe-Pipe hat genau einen Leser;
  ein zweiter teilte sich die Zeilen zufällig mit dem ersten. Neue Ansichten hängen sich als
  weitere Senke an `app.py::_starte_leser`, nie mit einem eigenen Leser an den Prozess.
- **Der Stopp-Knopf im Editor delegiert an `LiveView.stoppe()`.** Dieselbe Funktion
  aufzurufen genügt nicht — der freundliche Stopp hängt am Lauf-Verzeichnis, das nur die
  Live-Ansicht vom Watcher bekommt. Delegation heisst dasselbe Objekt mit demselben Zustand.
- **Fremde Projekte liefern Daten, keinen Code.** Panels sind deklarative JSON-Dateien, die
  spotlab mit den eigenen Widgets zeichnet. Ein Qt-Plugin-System liefe im Prozess mit dem
  NOT-AUS-Knopf; eine Schleife oder ein Absturz darin nähme dem Fenster den Failsafe, um den
  Stufe 1 herumgebaut ist.
- **`register_coexisting` verdrängt einen gleichnamigen Endpunkt nur, wenn er nachweislich
  stumm ist.** `ENDPOINT_NAME` ist eine feste Konstante; ohne Frischeprüfung über
  `time_since_valid_response` wirft ein zweiter Verbindungsversuch der ersten, laufenden
  Sitzung den Not-Aus aus der Konfiguration. **Der naheliegende Gegenfix ist verboten:** ein
  instanzeigener Endpunktname („spotlab-4711") zerstört die Selbstheilung, und ein
  abgestürzter Schülerlaptop hielte den Roboter dauerhaft im CUT. Gemeinsamer Name plus
  Frischeprüfung behält beides.
- **`RealSpot.connect()` macht den Aufbau rückgängig, wenn ein Schritt nach der
  E-Stop-Registrierung scheitert** — und fängt dafür `BaseException`, nicht `Exception`.
  Strg-C ist der häufigste Abbruch überhaupt; sonst bliebe genau dort ein Endpunkt samt
  Keepalive-Thread zurück. Der Rollback ist stumm: der ursprüngliche Fehler ist die
  Nachricht, ein Folgefehler beim Aufräumen dürfte sie nicht überschreiben.
- **Sicherheitswerte aus `config.toml` werden geprüft, nicht geglaubt.** `max_speed` und
  `max_turn_rate` müssen endlich und echt positiv sein. `inf` macht den Deckel wirkungslos,
  und ein NEGATIVER Wert ist schlimmer als keiner: `motion.clamp()` liefert dann für ein
  kommandiertes `wz = 0` eine Dauerdrehung. Eine kaputte Datei wirft `ConfigBroken` —
  ausdrücklich **kein** Untertyp von `ConfigMissing`, denn `connect()` fängt jenes ab und
  fiele still auf den Trockenlauf zurück.
- **`SPOTLAB_NUR_TROCKEN` wird beim Import EINMAL eingefroren** (`spotlab.NUR_TROCKEN`) und
  zusätzlich in `backends/real/verbindung.py::verbinde` geprüft — dem gemeinsamen Engpass
  von `RealSpot` und der Kartenaufzeichnung. Nur `spotlab.connect()` zu prüfen genügt nicht:
  ein direkter Import von `verbinde()` kam daran vorbei, und genau solche Skripte schreibt
  der Agent, für den die Schranke gedacht ist. **Bekannte Grenze:** wer die Variable löscht,
  *bevor* irgendetwas aus `spotlab` importiert wird, hebt sie auf. Kein In-Prozess-Mittel
  kann das verhindern — wer die Schranke wirklich braucht, darf dem Prozess die Variable
  nicht als einziges Hindernis mitgeben.
- **`SPOTLAB_NUR_TROCKEN=1` ist eine Obergrenze, keine Vorgabe.** `connect()` weist ein
  explizites `backend="real"` damit ab, statt es stillschweigend herunterzustufen.
  `SPOTLAB_BACKEND` genügt dafür nicht: `art = backend or os.environ.get(...)` — ein
  Skriptargument überschreibt die Variable. **Ein veraltetes Manifest darf den Roboter nicht
  bewegen können.** Die Prüfung steht vor dem `RunRecorder`, sonst bliebe ein leeres
  Lauf-Verzeichnis liegen.
- **`anbindung/` importiert nichts aus `api/`, `backends/`, `maps/`, `gui/`** und hält weder
  Lease-Client noch E-Stop-Endpunkt — dieselbe Regel wie `maps/`. `spotlab.errors` ist
  erlaubt und erwünscht.
- **Wo Läufe liegen, entscheidet `laufsuche.py` — an genau einer Stelle.** Läufe fremder
  Projekte liegen unter `<skriptordner>/runs/`, also ausserhalb des Arbeitsordners. Zwei
  Suchen mit verschiedenen Ergebnissen sind der Fehler aus Stufe 3 in neuem Gewand;
  `gui/watcher.py` exportiert die Funktion nur weiter.
- **Bestehende Schlüssel in `zustand.jsonl` ändern sich nicht.** `pose` bleibt
  `(x, y, yaw)`, `feet` bleibt vier Wahrheitswerte. Die Live-Ansicht liest genau das, und
  alte Aufzeichnungen müssen lesbar bleiben. Neue Felder kommen dazu, nie an ihre Stelle.
- **`t_robot` wird nicht in die Klientenzeit umgerechnet.** Für die Kalibrierung zählen
  Abstände innerhalb eines Laufs; eine Umrechnung schöbe die Unsicherheit der
  Zeitsynchronisierung in jede Ableitung. Der Umschlag-Zeitstempel `t` bleibt die
  Empfangszeit — beide Uhren nebeneinander machen die Latenz sichtbar statt versteckt.
- **Der Abtaster holt nichts nach.** Dauert die RPC länger als die Periode, läuft die
  Schleife langsamer. Nachholen erzeugte Bursts, die in der Auswertung wie echte Dynamik
  aussehen.
- **`messung/` importiert nichts aus `api/`, `backends/`, `gui/` und kein `bosdyn`.**
  `spotlab.record.read` und `spotlab.errors` sind erlaubt.
- **`end_time_secs` ist ein ZEITPUNKT in Sekunden seit dem 1.1.1970, keine Dauer.**
  Das SDK rechnet ihn über `time_sync.py::robot_timestamp_from_local_secs` in Roboterzeit
  um. Eine nackte Dauer bedeutet „gültig bis 1970" — der echte Spot weist jedes solche
  Kommando mit `ExpiredError` ab und bewegt sich nie. Deshalb führt `api/motion.py` **zwei**
  injizierbare Uhren: `jetzt` (monoton) misst Dauern, `wanduhr` (`time.time`) stempelt
  Endzeiten. Sie zu verschmelzen wäre bequem und wieder falsch. `DryRunBackend` weist
  abgelaufene Endzeiten ab — genau das hat 681 grüne Tests lang gefehlt.
- **Der Geschwindigkeitsdeckel wirkt auf allen drei Wegen, und es gibt genau eine
  Formulierung davon.** `walk()` klemmt die Sollwerte, `move()` und die autonome Fahrt
  schicken `vel_limit` mit — bei einer Zieltrajektorie wählt der Roboter sein Tempo selbst,
  Klemmen liefe dort ins Leere. Die Grenze wird ausschliesslich in
  `backends/mobility.py::se2_grenze` gebaut. `RobotCommandBuilder.mobility_params()` kennt
  den Parameter `vel_limit` nicht (geprüft an bosdyn-client 5.0.1.2); das Feld wird direkt
  am Protobuf gesetzt, deshalb liegt es in `backends/` und nicht in `api/`.
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
- **Fehlende Messwerte sind `None`, nie 0.** Der Unterschied zwischen „gemessen und null"
  und „nicht gemessen" entscheidet, ob eine Kalibrierung gültig ist. Das gilt besonders für
  `ground_mu_est`: ein erfundener Reibwert 0.0 mittelt sich durch jede Auswertung.
- spotlab liefert **Messwerte, keine Urteile**. Die Kriterien der Realismus-Gates liegen in
  `matura-spot`; `schranke`, `annahme` und `real_prozedur` gehören dorthin, wo das
  RESEARCH-DECISION-Protokoll gilt.
- Der Lückenmelder misst **abschnittsweise** gegen die erwartete Rate, und über eine
  Abschnittsgrenze hinweg gegen die *kleinere* der beiden. Ein Alarm, der bei jeder
  Messfahrt kommt, wird ignoriert.
- Panels bestimmen keine Farben. Ein Panel, das eine Farbe mitbringt, ist in einem der beiden
  Modi unlesbar. Bildpfade dürfen nur ins Projekt oder in den Anbindungsordner zeigen —
  dieselbe Regel wie bei den anklickbaren Tracebacks.
- **`anbindung/panel.py::lies` wirft nie.** Ein Panel, das im Sekundentakt überschrieben
  wird, ist regelmässig halb geschrieben; eine Ansicht, die daran leer wird, flackert im
  Betrieb, und **ein** kaputtes Panel darf die anderen nicht löschen.
- Der eingebaute Editor ist eine **Ergänzung**, kein Ersatz: `spotlab open` und „In VS Code
  öffnen" bleiben. Genau deshalb haben regelmässig beide Editoren dieselbe Datei offen —
  jeder Reiter merkt sich Änderungszeit und Grösse und fragt vor dem Überschreiben.
- Der Editor schreibt Dateien mit `encoding="utf-8", newline="\n"`. Ohne das schreibt Python
  auf Windows CRLF, und jede Datei sieht nach dem ersten Speichern in git vollständig
  geändert aus.
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

Fundament (1+2), GUI (3), GraphNav (4), der eingebaute Editor (5), die Anbindung fremder
Projekte samt MCP-Server (6) und die Kalibrier-Infrastruktur (7) sind vollständig. Offen
und bewusst nicht gebaut: Sim-Adapter, NN-Anbindung, Mehrbenutzer-Dienst, Arm und Docking.
Im Editor: Debugger mit Haltepunkten, git-Integration, Erweiterungen, projektweite Suche.
In der Anbindung: MCP über Netz, Mehrbenutzer, Qt-Code aus fremden Projekten, eine
Diagrammbibliothek jenseits der fünf Panel-Arten. In der Kalibrierung: **ein Simulator in
spotlab** (MuJoCo bleibt in `matura-spot`), automatische Parameteranpassung, die Nutzung
der lizenzpflichtigen 333-Hz-APIs.

Specs unter `docs/superpowers/specs/`. Anleitungen: `docs/ANBINDUNG.md` (fremde Projekte
und Messfahrt).
