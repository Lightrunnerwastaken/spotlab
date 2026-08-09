# spotlab härten — Befundlage und Fahrplan

Stand 09.08.2026. Erzeugt aus einer Mehr-Agenten-Untersuchung: **82 Sucher** in
sieben Aufgabengruppen, deren Code-Befunde anschliessend **adversarisch
gegengeprüft** wurden (Auftrag der Prüfer: widerlegen, im Zweifel verwerfen).
Insgesamt 169 Agenten, 98 Minuten.

| | |
|---|---|
| Befunde gemeldet | 174 |
| davon **bestätigt** | 102 |
| davon **widerlegt** und verworfen | 40 |
| ungeprüft (Gruppen ohne Prüfstufe) | 32 |
| Vorschläge (Erweiterungen, Umgebung, Automatisierung) | 131 |
| bestätigte Befunde mit Schwere „hoch" | 18 |

Die 40 widerlegten Befunde stehen bewusst **nicht** im Fahrplan. Sie sind in
`HAERTUNG_BEFUNDE.md` je Gruppe mit dem Grund der Widerlegung aufgeführt.

## Was unabhängig nachgeprüft wurde

Die folgenden Punkte sind nach dem Lauf von Hand am Code und am Boston-Dynamics-SDK
gegengelesen worden, nicht nur von Agenten gemeldet:

- **S1.1 `end_time_secs` — bestätigt.** `api/motion.py:58` sendet
  `end_time_secs=KOMMANDO_GUELTIGKEIT_S`, also die nackte Konstante `1.0`. Das SDK
  dokumentiert den Parameter in `time_sync.py:353-358` als
  „Timestamp in seconds since the unix epoch (e.g., from `time.time()`)" und
  wandelt ihn in `robot_command.py:475` über `robot_timestamp_from_local_secs`
  in Roboterzeit um. `1.0` heisst damit **1. Januar 1970, 00:00:01 UTC** — jedes
  Geschwindigkeitskommando käme rund 56 Jahre abgelaufen an. `move()`
  (`motion.py:79-85`) setzt gar kein `end_time_secs`.

- **KORREKTUR am vorgeschlagenen Fix.** Der Fahrplan schlägt
  `end_time_secs=jetzt() + KOMMANDO_GUELTIGKEIT_S` vor. **Das wäre erneut
  falsch:** `jetzt` ist in `walk()` mit `time.monotonic` vorbelegt
  (`motion.py:42`), also Sekunden seit einem beliebigen Bezugspunkt, nicht seit
  der Epoche. Der Wert muss aus `time.time()` kommen. Die Schleifensteuerung darf
  weiterhin `monotonic` benutzen — es sind zwei verschiedene Uhren, und genau
  diese Verwechslung hat den Fehler erzeugt. Wer den Fix baut, braucht **zwei**
  injizierbare Zeitquellen, nicht eine.

- **Warum 681 grüne Tests das nicht gefunden haben — bestätigt.**
  `backends/dryrun.py:48` nimmt `end_time_secs` entgegen und **ignoriert es**.
  Das Testdouble modelliert die Semantik nicht, an der das echte Kommando
  scheitert. Das ist der wichtigste strukturelle Befund des ganzen Laufs: die
  Suite kann die Klasse von Fehlern nicht sehen, die nur am echten Backend
  auftritt.

- **S1.5 E-Stop-Namenskollision — bestätigt.** `backends/real/estop.py:33-36`
  entfernt jeden Endpunkt, dessen Name gleich `ENDPOINT_NAME` (`"spotlab"`,
  Zeile 12) ist, ohne `time_since_valid_response` zu prüfen. Da der Name eine
  feste Konstante ist, trifft das auch einen **lebenden** Endpunkt einer zweiten
  spotlab-Instanz.

- **S1.2 `move()` ohne Geschwindigkeitsdeckel — bestätigt.** `motion.py:64` nimmt
  `limits` entgegen und benutzt es im ganzen Rumpf nicht; nur `walk()` ruft
  `clamp()` auf (Zeile 50).

Alles Übrige stammt aus dem Lauf und ist, wo es aus Gruppe G1, G2 oder G6 kommt,
durch mindestens eine adversarische Gegenprüfung gegangen. Befunde aus G3, G4, G5
und G7 sind **nicht** gegengeprüft — sie sind als Vorschläge zu lesen, nicht als
Feststellungen.

## Stand der Abarbeitung

| Punkt | Stand |
|---|---|
| **S1.1** `end_time_secs` in `walk()`/`move()` | **erledigt** — zwei getrennte Uhren (`jetzt` monoton für Dauern, `wanduhr` für Endzeiten), `move()` bekommt eine Endzeit gleich seinem `timeout` |
| **S1.2** `move()` an den Geschwindigkeitsdeckel | **erledigt** — `vel_limit` über `backends/mobility.py`, dieselbe Grenze wie die autonome Fahrt |
| **S1.3** Konfigurationswerte absichern | **erledigt** — `ConfigBroken` für kaputte Datei, unbekanntes Backend und für `max_speed`/`max_turn_rate`, die nicht endlich und positiv sind |
| **S1.4** `SPOTLAB_NUR_TROCKEN` tiefer verankern | **erledigt** — beim Import eingefroren, zusätzlich in `verbinde()` geprüft; bekannte Grenze in CLAUDE.md benannt |
| **S1.5** E-Stop-Frischeprüfung + `connect()`-Rollback | **erledigt** — `time_since_valid_response` statt reinem Namensabgleich, Selbstheilung bleibt; Rollback fängt `BaseException` |
| S1.6 – S1.13, S2, S3, S4 | offen |

Mit S1.1 fiel ein zweiter Befund mit: die Zeitüberschreitung in `move()` liess den
Roboter bisher weiterlaufen, weil `warte_auf` zwar wirft, aber keinen Stopp schickt.
Da die Endzeit jetzt genau der Geduld des Aufrufers entspricht, verfällt das Kommando
im selben Moment, in dem das Skript abbricht.

Zusätzlich gehärtet, weil es die Ursache dafür war, dass 681 grüne Tests den Fehler
nicht sahen: `DryRunBackend` **zeichnet `end_time_secs` auf und weist abgelaufene
Kommandos ab**, wie es der echte Roboter täte. Die Abnahmeprozedur A6 hat drei Zusätze
bekommen, die Deckel, Zeitüberschreitung und Kommandoannahme am Gerät prüfen.

## Aufbau dieses Dokuments

1. Fahrplan in vier Stufen (S1–S4), inklusive „Was ich streichen würde" und den
   Entscheidungen, die der Autor treffen muss
2. Sicherheitsliste vor dem ersten Schülerbetrieb, getrennt nach „am Code" und
   „nur am Gerät prüfbar"
3. Was diese Untersuchung **nicht** abgedeckt hat

Die Belege je Gruppe stehen in `HAERTUNG_BEFUNDE.md`.

---


# spotlab haerten - Fahrplan

## S1 - Vor dem ersten Schuelerbetrieb (Sicherheit und harte Fehler)

**1. `end_time_secs` in `walk()`/`move()` korrigieren.**
Wirkung: ohne diesen Fix scheitert jeder Bewegungsbefehl am echten Spot mit `ExpiredError` — nichts fährt. Muss vor jedem weiteren Punkt dieser Liste als Erstes am Gerät verifiziert werden, sonst verfälscht er alle folgenden Bewegungstests.
Aufwand: klein. Dateien: `src/spotlab/api/motion.py:58,85` (`end_time_secs=jetzt()+KOMMANDO_GUELTIGKEIT_S` als injizierbarer Parameter, analoges Feld bei `move()`), `src/spotlab/errors/translate.py` (`ExpiredError` ergänzen).
Verifiziert: `motion.py:58` sendet tatsächlich die feste Konstante `1.0`, `move()` (`:79-85`) hat gar kein `end_time_secs`.

**2. `move()` an den Geschwindigkeits-/Drehratendeckel binden.**
Wirkung: sonst fährt der erste Tutorial-Befehl (`hallo_spot.py`) ungebremst, während die Lehrperson glaubt, `max_speed` gelte überall.
Aufwand: mittel. Dateien: `src/spotlab/api/motion.py:64-89` (`limits` tatsächlich nutzen), neue Backend-Methode analog `travel_params()` in `backends/real/graphnav.py:104-111` (wegen Protobuf-Reinheitsregel in `api/`), Kommentar in `graphnav.py:107-109` korrigieren, Regressionstest in `tests/test_api_motion.py`.
Geht sinnvoll direkt nach Punkt 1, da dieselbe Datei.

**3. Konfigurationswerte absichern.**
Wirkung: `max_speed=inf`/negativ hebelt den Deckel aus oder erzeugt ungewollte Drehbewegung bei `wz=0`; eine beschädigte `config.toml` sperrt GUI, CLI und den Reparaturweg `spotlab login` gleichzeitig.
Aufwand: klein. Dateien: `src/spotlab/config.py:78-93` (`math.isfinite()`+Bereichsprüfung, `tomllib.TOMLDecodeError`/`UnicodeDecodeError`/`OSError` fangen, `Backend = Literal["real","dryrun"]` einführen und prüfen). Eigene Ausnahmeklasse verwenden, nicht `ConfigMissing` wiederverwenden (sonst fällt `__init__.py:32-35` still auf `dryrun` zurück).

**4. `SPOTLAB_NUR_TROCKEN` als zweite, tiefere Schranke direkt in `RealSpot.connect()`/`verbinde()` einbauen.**
Wirkung: heute nur in `spotlab/__init__.py:47` geprüft — ein direkter Import von `RealSpot`/`verbinde()` oder ein Skript, das die Variable vor Verbindungsaufbau entfernt, umgeht die als „nicht verhandelbar" deklarierte Obergrenze.
Aufwand: klein bis mittel. Dateien: `src/spotlab/backends/real/session.py:57-95`, `src/spotlab/backends/real/verbindung.py:21-42`. Wert beim Modulimport einmal einfrieren statt live aus `os.environ` zu lesen.

**5. E-Stop-Koexistenz reparieren.**
Wirkung: trifft A1 direkt. `register_coexisting` verdrängt jeden gleichnamigen Endpunkt ohne Frischeprüfung (selbst gegengelesen: `estop.py:33-36` prüft nur den Namen, nie `time_since_valid_response`) — ein zweiter Verbindungsversuch (versehentlicher Doppelstart, zwei Schüler) kann eine fremde, aktive Sitzung aus der E-Stop-Konfiguration werfen. Zusätzlich hat `connect()` keinen Rollback: scheitert `lease.start()` nach erfolgreicher E-Stop-Registrierung, bleibt der Keepalive-Thread unbeaufsichtigt am Leben.
Aufwand: mittel. Dateien: `src/spotlab/backends/real/estop.py:23-45` (`EstopSystemStatus.endpoints`/`time_since_valid_response` statt reinem Namensabgleich — **nicht** auf instanzspezifische Namen wechseln, das zerstört die Selbstheilung nach Absturz, siehe Entscheidungsabschnitt), `src/spotlab/backends/real/session.py:64-95` (Aufbauschritte kapseln, bei Fehlschlag umgekehrt zurückrollen), `tests/test_real_estop.py` (dedizierter Test gegen die echte `EstopGuard`-Klasse, nicht nur die freie Funktion).
Geht nach Punkt 4 (gleiche Dateien, `session.py`).

**6. Geordneten Abbau robust gegen Ctrl-C machen.**
Wirkung: `RealSpot._versuche()` fängt nur `Exception`, nicht `BaseException`; `abtaster.stop()` läuft in `__init__.py` sogar ausserhalb jedes try/finally vor `spot.close()`. Ein Interrupt im ersten Abbauschritt lässt den Spot aus dem Stand umfallen statt sich zu setzen.
Aufwand: klein bis mittel. Dateien: `src/spotlab/backends/real/session.py:210-225` (pro Schritt `BaseException` fangen, erste Ausnahme merken, alle Schritte durchlaufen, danach erneut werfen — **nicht** `except BaseException: pass`, das würde den Lauf fälschlich als „ok" verbuchen), `src/spotlab/__init__.py:107-112` (`abtaster.stop()` in den geschützten Bereich holen).
Geht nach Punkt 5, gleiche Datei.

**7. GUI-NOT-AUS ehrlich machen + Abnahmepunkt A9 korrigieren.**
Wirkung: `beende_hart()` meldet Erfolg unabhängig vom tatsächlichen `taskkill`-Rückgabewert. Schwerer: das Liveness-Signal (`ist_aktiv()`) hängt an `zustand.jsonl`, das der Abtaster schon beim Interrupt stoppt — lange bevor `close()` (Hinsetzen, `power_off(timeout_sec=20)`) fertig ist. A9 kann damit „bestehen", ohne je gezeigt zu haben, dass NOT-AUS während eines laufenden Abbaus wirklich tötet.
Aufwand: mittel. Dateien: `src/spotlab/workshop/control.py:24-36,64-90` (Rückgabecode auswerten, Liveness-Signal von `zustand.jsonl` lösen — z. B. Prozess-Handle/PID oder eigenes „abbau_läuft"-Merkmal bis nach `close()`), `docs/ABNAHME.md:163` (A9 um Test mit künstlich verzögertem Abbau erweitern).

**8. Zwei gleichzeitige Läufe im Hauptfenster verhindern.**
Wirkung: startet ein Schüler nacheinander aus „Projekte" und „Code" (oder zusätzlich per F5, laut A11 ausdrücklich unterstützt), zeigt `LiveView._lauf` nur den zuletzt entdeckten Prozess — Stopp/NOT-AUS können am falschen oder an gar keinem Prozess wirken.
Aufwand: mittel. Dateien: `src/spotlab/gui/app.py:207,242,261`, `src/spotlab/gui/views/live.py` (aktiven Lauf pro Fenster gegen das gemeldete Verzeichnis abgleichen statt bedingungslos zu überschreiben).

**9. Neuer Abnahmepunkt + Stopp-Pfad für `roboter=true`-Start aus „Anbindungen".**
Wirkung: der dritte Startweg für den echten Roboter (fremder Code, ohne Trockenlauf-Schranke) hat keinen eigenen Stopp-Knopf und wechselt nicht automatisch zur Live-Ansicht — genau der am wenigsten geprüfte Weg, ohne analogen Abnahmepunkt zu A17.
Aufwand: klein (Doku) bis mittel (GUI-Verhalten). Dateien: `docs/ABNAHME.md` (neuer Punkt — Nummerierungskollision mit dem Schrittgeometrie-Vorschlag beim Einpflegen auflösen), `src/spotlab/gui/views/anbindungen.py:306-317`, `src/spotlab/gui/app.py:230-235`.
Geht nach Punkt 8 (gleiches Anzeigemuster).

**10. Editor-Absturz beim Reiterschliessen während laufender Codevervollständigung beheben.**
Wirkung: reproduzierter Absturz des gesamten Fensters (inkl. NOT-AUS-Knopf) beim Schliessen eines Reiters während `jedi` noch läuft — ein eventuell laufendes Roboterprogramm im Kindprozess wird dabei führerlos.
Aufwand: mittel. Dateien: `src/spotlab/gui/editor/completer.py:195-204`, `src/spotlab/gui/editor/view.py:364` (Worker vor `deleteLater()` sauber trennen/abwarten), dieselbe Lücke bei `OutputReader` in `src/spotlab/gui/app.py:214` beim Fensterschliessen während eines laufenden Programms.

**11. Beschädigte `graph`-Datei darf den GUI-Start nicht verhindern.**
Wirkung: eine defekte Karte verhindert heute den kompletten Programmstart, nicht nur die Kartenansicht — damit auch den Zugriff auf den NOT-AUS-Knopf.
Aufwand: klein. Datei: `src/spotlab/maps/store.py:62-83` (`google.protobuf.message.DecodeError` zusätzlich fangen, `karten()` pro Ordner einzeln absichern statt in einer Listcomprehension).

**12. Ausgabefenster nicht mehr quadratisch langsam machen.**
Wirkung: gemessen 3 Minuten durchgehend besetzte Qt-Ereignisschleife bei Ausgabeflut — ein Klick auf NOT-AUS steht in derselben Warteschlange.
Aufwand: klein bis mittel. Dateien: `src/spotlab/gui/workers.py` (Zeilen bündeln statt pro Zeile emittieren), `src/spotlab/gui/editor/view.py:101,108` (laufender Offset statt `toPlainText()` pro Zeile — Pufferbegrenzung nur zusammen mit Korrektur der `_stellen`-Traceback-Link-Positionen einführen, sonst zeigen Links auf falsche Dateien), `src/spotlab/gui/views/live.py:65-66,157-158`.

**13. `doctor.py`: zurückgelassenen `spotlab`-Endpunkt erkennen.**
Wirkung: A3 („kein zurückgelassener spotlab-Endpunkt") ist heute nicht automatisiert prüfbar — `doctor.py` fragt nur den aggregierten Systemstatus ab, nie `get_config()` auf einen Endpunkt namens `spotlab`.
Aufwand: klein. Datei: `src/spotlab/workshop/doctor.py:103-115`.
Geht nach Punkt 5, nutzt dieselbe Frische-Logik.

---

## S2 - Damit es im Unterricht traegt (Robustheit, Bedienbarkeit, Doku)

**1. Ungespeicherte Änderungen beim Fensterschliessen abfragen.**
Wirkung: X-Knopf/Alt+F4 verwerfen Arbeit heute kommentarlos, obwohl das einzelne Tab-Schliessen bereits fragt.
Aufwand: klein. Datei: `src/spotlab/gui/app.py:269-272` (`closeEvent` über Editor-Reiter iterieren, denselben Dialog wie beim Tab-Schliessen zeigen).

**2. Vor jedem Start alle verschmutzten Reiter speichern, nicht nur den aktuellen.**
Wirkung: Mehrdatei-Projekte laufen sonst mit veralteten importierten Dateien.
Aufwand: klein. Datei: `src/spotlab/gui/editor/view.py:380-397`.

**3. `_login()` überschreibt `workspace`/`active_map` nicht mehr.**
Wirkung: Passwort erneuern verliert heute kommentarlos Arbeitsordner und aktive Karte.
Aufwand: klein. Datei: `src/spotlab/cli.py:234ff` (`dataclasses.replace()` nutzen, Muster existiert bereits in `gui/app.py:174/181`).

**4. Diagnose-Logging und Crash-Reports ergänzen.**
Wirkung: sicherheitsrelevante Abbaupfade (`close()`, `EstopGuard.stop()`, `LeaseGuard.stop()`) verschlucken Ausnahmen heute spurlos — nach einem Vorfall ist nichts rekonstruierbar.
Aufwand: mittel. Dateien: `src/spotlab/backends/real/session.py:220-225`, `estop.py:82-86`, `lease.py:73-84` (Datei-Log, nie `StreamHandler` auf stdout/stderr — sonst bricht die Ein-Leser-Pipe/MCP-stdio), `record/events.py` (vorgesehene Art `"fehler"` tatsächlich schreiben), `gui/app.py::main()` (`sys.excepthook` + `traceback.txt` neben `lauf.json`), `gui/views/checkup.py:97-116` (eigenes try/except für Ersteinrichtung).

**5. `LeaseGuard` nicht bei jedem Keepalive-Fehler dauerhaft als verloren markieren.**
Wirkung: reiner WLAN-Aussetzer bricht heute grundlos einen Lauf ab und beschriftet ihn fälschlich mit `lease_verloren`.
Aufwand: klein. Datei: `src/spotlab/backends/real/lease.py:59-65` (Ausnahmeklasse auswerten, nur `LeaseUseError`/`DisplacedLeaseError` als echten Verlust werten).

**6. GraphNav-Fehlerübersetzung nachziehen.**
Wirkung: `navigate_step`/`upload_map`/`localize`/`power_off`/`command_feedback` liefern rohe SDK-Fehler statt deutscher Klartextmeldungen; `NotLocalized` ist im Ernstfall unerreichbar; `upload_map`/`clear_graph` sind gegen `CannotModifyMapDuringRecordingError` ungeschützt.
Aufwand: klein bis mittel. Dateien: `src/spotlab/backends/real/session.py:123-124,150,201-204`, `backends/real/graphnav.py:66-67,88`.

**7. Zeitsync-Fehler korrekt unterscheiden.**
Wirkung: echte Netzfehler werden heute immer als Uhrenabweichung gemeldet — schickt Schüler auf die falsche Fährte.
Aufwand: klein. Dateien: `src/spotlab/backends/real/verbindung.py:33-40`, `cli.py:313-340` (`_lease()` durch dieselbe `translate()`-Übersetzung schicken wie `lease.py`).

**8. `RunsView` auf `laufsuche.lauf_verzeichnisse()` umstellen.**
Wirkung: Läufe angebundener Fremdprojekte fehlen heute im Reiter „Läufe" — exakt der Fehler, den CLAUDE.md als „Stufe-3-Fehler in neuem Gewand" benennt und den zwei unabhängige Gruppen (G3, G7) wiederentdeckt haben.
Aufwand: klein. Datei: `src/spotlab/gui/views/runs.py:142-147`.

**9. `RunsView`-Performance und Ereignisliste reparieren.**
Wirkung: kompletter Neueinlese aller Läufe bei jedem Refresh friert den GUI-Thread ein; Ereignisliste zeigt bei `ende`/`bild`/`lease_übernommen` immer eine leere Beschreibung, genau an der Stelle, wo Erfolg/Fehlertext stünde; abgestürzte Läufe zeigen dauerhaft „läuft"/„0.0 s", obwohl der MCP-Pfad das schon korrekt löst.
Aufwand: klein bis mittel. Dateien: `src/spotlab/gui/views/runs.py`, `gui/views/live.py:144-150`, `record/read.py::read_run()` (Prüfung mit `ist_aktiv()` zentral verlegen, behebt GUI und CLI auf einmal).

**10. `doctor.py`: „Netz"-Stufe soll tatsächlich Netz prüfen.**
Wirkung: `create_robot()` macht keinen RPC; ein unerreichbarer Spot wird erst bei „Anmeldung" erkannt, während „Netz: OK" grün darübersteht.
Aufwand: klein. Datei: `src/spotlab/workshop/doctor.py:85`.

**11. `anbindung/manifest.py::lies()`: strukturell falsches TOML sauber melden.**
Wirkung: `[skript]` statt `[[skript]]` (häufigster TOML-Anfängerfehler) wirft heute eine rohe `AttributeError` statt `ManifestFehler` — bricht die MCP-Zusage.
Aufwand: klein. Datei: `src/spotlab/anbindung/manifest.py:83-92`.

**12. Editor-Alltagstauglichkeit.**
Wirkung: Dateibaum kann keine Dateien verwalten (kein Kontextmenü für Neu/Umbenennen/Löschen); `indent.py` erkennt keine Tabs und stuft Zeilen ohne „:" still falsch ein; Stopp-Knopf hängt dauerhaft auf „■ Stopp" fest, wenn ein Skript nie `zustand.jsonl` anlegt (jeder Syntaxfehler reicht).
Aufwand: mittel (Dateibaum), klein (indent.py, Stopp-Knopf). Dateien: `src/spotlab/gui/editor/tree.py:46-83`, `gui/editor/indent.py`, `workshop/control.py`/`RunWatcher`.

**13. Palette/Dark-Mode für Karten- und Lauf-Diagramme nachziehen.**
Wirkung: auf Windows-Standard „Hell" sind Wegpunktnamen praktisch unlesbar (Kontrast ~1,3:1) — trifft die Mehrheit der Schullaptops deterministisch.
Aufwand: klein. Dateien: `src/spotlab/gui/mapplot.py:25`, `gui/views/runs.py:63` (Palette durchreichen wie bei `EditorView`/`AnbindungenView`).

**14. Dokumentation nachziehen.**
Wirkung: Geschwindigkeitsreduktion für Anfängerstunden (`checkup.py`) ist in keinem Nutzerdokument erwähnt — sicherheitsrelevant für Lehrpersonen; eingebauter Editor hat null Zeilen Nutzerdoku; README verlinkt nur eine von sechs Design-Specs.
Aufwand: klein bis mittel. Dateien: `README.md`, `docs/`.

**15. `spotlab_version` sichtbar machen.**
Wirkung: wird in jede `lauf.json` geschrieben, aber von keinem Leseweg gezeigt — für Versionsvergleiche im Unterricht/für die Maturaarbeit nötig.
Aufwand: klein. Dateien: `record/read.py::RunSummary`, CLI-Ausgabe, GUI-Tabelle.

---

## S3 - Damit die Maturaarbeit belastbar wird (Sim-to-Real, Kalibrierung)

Reihenfolge wichtig: Punkte 1-6 betreffen die Aufzeichnung/Definition selbst und sollten stehen, **bevor** die erste echte Kalibrierkampagne gefahren wird — sonst werden Definitionsfehler erst nach dem teuren Robotertermin sichtbar. Punkte 7+ sind reine Simulationskorrekturen in matura-spot, die parallel oder danach laufen können.

**1. G6-Stossimpulse vor Datenverlust schützen.**
Wirkung: `protokoll_real.json` wird erst am Ende von `main()` geschrieben; jeder Abbruch verliert die von Hand eingetippten Stossimpulse unwiederbringlich — die einzige Vergleichsgrösse von G6. Muss vor der ersten echten Messfahrt stehen, da ein Wiederholungsversuch am Gerät teuer ist.
Aufwand: mittel. Datei: `matura-spot/scripts/gates_real.py:419-436` (Lauf-Verzeichnis sofort nach `power_on()` festhalten, Protokoll nach jedem Gate zwischenspeichern, Impulse sofort bei Eingabe persistieren).

**2. Bremsweg-Vergleich (G7): Zeitfenster und Geschwindigkeiten angleichen.**
Wirkung: real wird ab Kommandostart gemessen (bis zu 1,0 s Vorlauf bei 0,30 m/s), Sim erst ab Ablaufzeitpunkt; zusätzlich real mit 0,30 m/s, Sim mit 0,03 m/s — beide Fehler zusammen reissen eine 5-cm-Schranke ohne jede Warnung.
Aufwand: mittel. Dateien: `matura-spot/scripts/vergleich_real_sim.py:168`, `gates_real.py:231-236`, `src/spotsim/gates.py:610-631,929-931`.

**3. Odom-Heading-Drift sichtbar machen.**
Wirkung: „Erreichte Geschwindigkeit"/„Querdrift" sind reine Odom-x/y-Differenzen; reale Gierdrift über eine Sitzung (bis 25°/Fenster zulässig) erzeugt 6-20 % Scheinfehler ohne Hinweis.
Aufwand: klein (Diagnose). Datei: `spotlab/src/spotlab/messung/fenster.py:223-224` (Gierwinkel bei Fensterstart als zusätzliches Feld mitschreiben). Echte Rotation ins fensterlokale Koordinatensystem ist RESEARCH DECISION für matura-spot, nicht hier zu entscheiden.

**4. Zwei-Uhren-Problem und absolute vs. laufrelative Zeitangabe vereinheitlichen.**
Wirkung: `zustand_zusammenfassen` (Empfangszeit) und `fenster.kennzahlen()` (`t_robot`, sobald vorhanden) liefern für dieselbe Aufzeichnung unterschiedliche Lückenlisten/Ist-Raten; `von_s` ist bei Quelle „robot" absolut, sonst laufrelativ — eine Lücke lässt sich damit nicht mehr verorten.
Aufwand: klein. Dateien: `spotlab/src/spotlab/mcp/werkzeuge.py:231-262`, `messung/fenster.py:68-83,205-209`, `docs/ABNAHME.md` A18 (Satz zu Geltungsbereich/Uhrentyp ergänzen).

**5. Hardwarefehler ohne Sturz aufzeichenbar machen.**
Wirkung: `behavior_fault_state`/`system_fault_state`/`service_fault_state` werden nie gelesen — drei der neun Realismus-Gates (G2/G3/G4) fordern „kein Sturz" als Kriterium, ohne dass die reale Aufzeichnung ein Gegenstück liefert.
Aufwand: klein. Datei: `spotlab/src/spotlab/api/state.py:104` (Faultliste mit Zeitstempel als zusätzliches, rein tatsächliches Feld — kein Werturteil, das bleibt matura-spot vorbehalten).

**6. `fenster.reich` über alle Sätze prüfen.**
Wirkung: kann fälschlich `False` zeigen, obwohl Terrain-Daten vorliegen — genau dort, wo man als Erstes nachsieht.
Aufwand: klein. Datei: `spotlab/src/spotlab/messung/fenster.py:313-315`.

**7. Falsche gangspezifische Hinweistexte im Vergleichsbericht korrigieren.**
Wirkung: Kriechgang-Hinweistext erscheint im Trab-Bericht und umgekehrt — kein Test schützt die Zeichenketten.
Aufwand: klein. Datei: `matura-spot/scripts/vergleich_real_sim.py:113-118,143-144`.

**8. „Restgelenkrate" (G1): Hinweistext für Fenster-Maximum vs. Momentanwert.**
Wirkung: reale 10-s-Fenster-Maxima werden gegen einen simulierten Einzelwert am letzten Schritt geprüft — strukturell asymmetrisch, enge Schranke (0,05 rad/s).
Aufwand: klein (Hinweis); echte Angleichung ist RESEARCH DECISION, da sie das Bestehen von G1 beeinflusst. Datei: `matura-spot/scripts/vergleich_real_sim.py:137`.

**9. Trab-Tracking-Rückstand / `t_cycle`-Divergenz entscheiden.**
Wirkung: seit über zwei Wochen offene, dokumentierte Entscheidung (Option A empfohlen); `TrotController` läuft weiterhin mit Default `t_cycle=0.7`, während Tests `0.8` nutzen — betrifft jeden Trab-bezogenen Zahlenvergleich der Arbeit.
Aufwand: klein. Dateien: `matura-spot/src/spotsim/sdk_sim.py:211`, `tests/test_trot.py:25`.

**10. Kriechgang `CRAWL_ORDER`-Fehler beheben.**
Wirkung: geometrisch hergeleitete Hauptursache für den unausgeglichenen Schub (5/5 reproduziert); Tuning daran ist mit Sturzrisiko verbunden.
Aufwand: mittel. Dateien: `matura-spot/src/spotsim/sdk_sim.py:131`, `posture.py:168`.

**11. Tracking-Berechnung gegen tatsächlich kommandierten statt nominalen Sollwert rechnen.**
Wirkung: bei aktiver Geschwindigkeitskappung erscheint ein perfekt folgender Roboter als Tracking-Ausreisser.
Aufwand: klein. Datei: `matura-spot/scripts/vergleich_real_sim.py:225,247`.

**12. G6-Stossschwelle: Kraftraster verlängern oder als rechtszensiert kennzeichnen.**
Wirkung: „60,0 N·s longitudinal" ist der grösste getestete, nicht der gefundene Wert — suggeriert eine Richtungsanisotropie, die tatsächlich ein ausgeschöpftes Testraster ist.
Aufwand: klein. Datei: `matura-spot/src/spotsim/gates.py:505,559-569`.

**13. `fetch_menagerie.py`: Commit-SHA in Versionsangaben aufnehmen.**
Wirkung: Baseline-Protokoll dokumentiert Software-Versionen, aber kein Modell-Commit — Zitierfähigkeit der Arbeit betroffen. Nur die billige Hälfte (SHA loggen) jetzt, vollständiges Pinning später.
Aufwand: klein. Dateien: `matura-spot/scripts/fetch_menagerie.py:22-26`, `realismus_gates.py`.

---

## S4 - Damit es ein professionelles Produkt wird (Umgebung, Automatisierung)

**1. Timeout auf allen Subprocess-Aufrufen in Tests nachziehen.**
Wirkung: `readline()` ohne Timeout kann bereits lokal, nicht nur in CI, unbegrenzt hängen.
Aufwand: klein. Dateien: `tests/test_editor_verbs.py:140-145`, `tests/test_mcp_server.py:102` (Wert 60 s, analog `test_errors_graphnav.py:90`).

**2. CI/CD einrichten.**
Wirkung: keine automatisierte Prüfung ausserhalb des eigenen Laptops — jede Regression, die nur unter bestimmter Extras-Kombination auftritt, wird nur zufällig gefunden. Grundvoraussetzung für Lock-Datei-Pflege und Lint-Einführung.
Aufwand: klein bis mittel. Dateien: `pyproject.toml`, neues `.github/workflows/` (Hauptjob `windows-latest` alle drei Extras mit `timeout-minutes: 10`, Minimal-Job nur `[dev]` für den Skip-Vertrag, optionaler nicht-blockierender VS-Code-Job).

**3. Abhängigkeiten pinnen.**
Wirkung: `PySide6>=6.6,<7` fehlt trotz bereits eingetretenem API-Bruch (`gui/editor/tree.py:28-33`); `requires-python` breiter als das tatsächlich geprüfte Fenster (3.13.9).
Aufwand: klein. Datei: `pyproject.toml:9,20`. Geht nach Punkt 2, damit die Pins in CI getestet werden.

**4. `record/`-Schichtgrenzen-Verletzung beheben.**
Wirkung: `record/sampler.py` importiert transitiv `bosdyn` über `api/state.py` — bricht die in der Fundament-Spec zugesicherte Isolation von `record/`. Heute folgenlos, wird zum Hindernis, sobald ein Sim-Adapter „ohne Umbau daneben passen" soll.
Aufwand: mittel. Dateien: `src/spotlab/record/sampler.py:20`, `api/state.py` (State-Konvertierung in neutrales drittes Modul auslagern). Muss vor jedem Sim-Adapter-Code stehen.

**5. MCP-Werkzeuge härten.**
Wirkung: `_antwortet`/`_als_liste` fangen nur `SpotlabError`/`OSError` — ein `KeyError` reisst die ganze stdio-Sitzung ab; `skript_starten` liest nie `stdout`/`stderr` (Deadlock-Risiko), verwirft das Popen-Handle, gibt keine `lauf_id` zurück; `cli.py::_lease()` übersetzt Fehler nicht; fehlende Typannotationen liefern irreführende JSON-Schemas.
Aufwand: mittel. Dateien: `src/spotlab/mcp/werkzeuge.py:24,42-69,126-163`, `cli.py:313-340`.

**6. Panel-Lifecycle vervollständigen.**
Wirkung: `speicher.loese()` existiert und ist getestet, aber weder als MCP-Werkzeug noch in der GUI erreichbar — eine falsch angebundene Anbindung lässt sich nur durch manuelles Löschen auf der Platte rückgängig machen; `panel.schreibe()` prüft Bildpfade nicht gegen `bild_erlaubt()`; keine Live-Aktualisierung während eines laufenden Fremdskripts, obwohl `docs/ANBINDUNG.md` das verspricht.
Aufwand: klein bis mittel. Dateien: `src/spotlab/anbindung/speicher.py:98-104`, `mcp/server.py`, `anbindung/panel.py:18-92`, `gui/views/anbindungen.py:175,246-288`.

**7. Versions-Einheitlichkeit.**
Wirkung: `mcp/server.py:56` trägt das Literal `"0.1.0"` statt aus `spotlab.__version__` zu lesen — kann abweichen.
Aufwand: klein. Datei: `src/spotlab/mcp/server.py:56`, dazu CHANGELOG/SemVer-Konvention rückwirkend anlegen.

**8. Linting-Baseline einführen.**
Wirkung: Code hält sich schon fast vollständig an eine implizite Konvention — Einführungsrauschen ist praktisch null.
Aufwand: klein. Datei: `pyproject.toml` (`ruff`, `line-length=100`, `select=["E4","E7","E9","F","I","TID252","UP","PLW1514"]`, bewusst **ohne** `BLE`/`TRY`/`format` — sonst markiert es die für die Not-Aus-Koexistenz absichtlich gewählten `except Exception: pass`-Stellen fälschlich als Fehler).

**9. Verteilung an Schul-Laptops konzipieren.**
Wirkung: einziger dokumentierter Weg ist `pip install -e .` gegen PyPI — kein Offline-Pfad, kein maschinenweiter Konfigurationspfad für IP/Limits.
Aufwand: mittel. Dateien: `README.md`, `config.py` (Konfigurationssuche um maschinenweiten Pfad erweitern, nie Passwort).

---

## Die fuenf wichtigsten Punkte

**`end_time_secs`-Fehler in `motion.py` (S1.1).** Ohne diesen Fix ist ungeklärt, ob überhaupt irgendein anderer Befund am echten Roboter beobachtbar wird — `walk()` und `move()` scheitern beim allerersten Aufruf. Das ist der einzige Punkt, der buchstäblich vor jedem weiteren Gerätetest stehen muss.

**E-Stop-Frischeprüfung in `register_coexisting` (S1.5).** Das ist der Kern von Sperrpunkt A1 selbst: die Verdrängung eines aktiven, fremden Endpunkts ohne Prüfung auf `time_since_valid_response` ist bereits am Code, nicht nur konstruiert, nachvollzogen worden. Ein alltäglicher Fehler (Doppelstart) reicht als Auslöser.

**Abnahmepunkt A9 korrigieren (S1.7).** Eine Abnahmeprozedur, die „bestanden" zeigen kann, ohne das zu beweisen, was sie behauptet, ist gefährlicher als ein fehlender Test — sie erzeugt falsches Vertrauen genau in den Sperrpunkt, der vor Schülerbetrieb steht.

**Zwei gleichzeitige Läufe im Hauptfenster (S1.8).** Der sekundäre Software-Not-Aus ist in einer alltäglichen, nicht konstruierten Bedienreihenfolge (F5 aus VS Code plus GUI-Start) wirkungslos oder trifft den falschen Prozess — das untergräbt genau die zweite Verteidigungslinie, die die GUI bieten soll.

**`move()` an den Geschwindigkeitsdeckel binden (S1.2).** Der Code behauptet an der einzigen Stelle, wo darüber nachgedacht wurde, das Gegenteil dessen, was er tut. Eine Lehrperson, die das Tempo für Anfängerstunden herunterdreht, hat damit für die Hälfte der Bewegungsbefehle keine Wirkung erzielt.

## Was ich streichen wuerde

- **`clamp()` mit NaN/inf, `to_feedback()` Full-Body-Zweig, `DryRunBackend` rohe Bytes, battery `0.0` vs. `None`, `StateSampler.stop()`-Bestätigung, TOCTOU in `_freies_verzeichnis()`.** Alle sechs sind entweder ohne realistischen Auslöser (eine Gegenprüfung widerlegt ihn jeweils explizit) oder ohne jeden Konsumenten, der die Verwechslung bemerken könnte. Sechs kleine Fixe für sechs Befunde, die selbst ihre Entdecker als „nicht haltbar" oder „strittig, geringe Wirkung" einordnen — das lohnt die Aufmerksamkeit nicht.
- **Modaldialoge applikationsweit entschärfen (G2 Punkt 10).** Der einzige technisch mögliche Codefix (eigenes Kopfleistenfenster) hilft laut beiden Gegenprüfern nachweislich nicht, weil `ApplicationModal` alle Fenster sperrt. Ein Satz in `docs/ABNAHME.md` A10/A17 kostet nichts und trifft den Kern besser als ein Umbau, der „gross" wäre und das Problem nicht löst.
- **`beende_hart` während des geordneten Abbaus umbauen (G2 Punkt 11).** Stark umstritten, und die Gegenposition ist inhaltlich stark: ein harter Kill genau im Moment des Hinsetzens ist eher gefährlicher als die heutige Meldung „läuft nicht mehr". Höchstens die Beschriftung anpassen („Lauf baut ab" statt „beendet"), keinen Mechanismus bauen, solange der Widerspruch nicht aufgelöst ist.
- **Grid-Panel-Typ für 2D-Belegungsgitter.** Der Bericht selbst benennt die Spannung: das liegt gefährlich nah an der bewusst offen gelassenen „Diagrammbibliothek jenseits der fünf Panel-Arten". Umweg über den bestehenden Panel-Typ „bild" reicht, bis ein zweites reales Projekt (nicht nur matura-spot) den Bedarf zeigt.
- **Splitscreen, projektweite Suche, Git-Integration, Erweiterungssystem im Editor.** Bereits im Rohmaterial selbst geprüft und explizit nicht empfohlen (kein `git init` im ganzen Baum, ein Qt-Plugin-System liefe im Prozess mit dem NOT-AUS-Knopf) — hier nur bestätigt, nicht neu diskutiert.
- **Vollständiges `fetch_menagerie.py`-Pinning statt nur SHA-Logging.** Der Aufwandsunterschied zwischen „SHA aufschreiben" und „echtes Pinning-System bauen" ist gross, der Erkenntnisgewinn für die Zitierfähigkeit ist bei blossem Loggen schon fast vollständig erreicht.
- **Mehrbenutzer-Rechnerabgleich für `beende_hart` (G2 Punkt 12).** Setzt einen gemeinsamen Netzlaufwerk-Arbeitsordner voraus, der laut Projektbeschreibung nicht vorgesehen ist. Bauen, falls eine Schule das tatsächlich einrichtet — nicht vorab.
- **GUI-Kosmetik ohne visuelle Verifikation** (Search/Replace-Leiste-Breite, Ereignislisten-Padding). Der Befund selbst sagt „rechnerisch hergeleitet, nicht visuell verifiziert" — erst am echten Desktop ansehen, bevor daran etwas geändert wird.

## Entscheidungen, die der Autor treffen muss

**E-Stop-Namensschema: gemeinsamer Name mit Frischeprüfung vs. instanzspezifischer Name.** Der naheliegende Fix „jede Instanz bekommt einen eigenen Endpunktnamen" ist selbst gefährlich — er zerstört die Selbstheilung, mit der ein abgestürzter Lauf beim nächsten Start automatisch ersetzt wird (`tests/test_real_estop.py:64`); ein abgestürzter Schülerlaptop könnte den Roboter dann dauerhaft im CUT halten, ohne dass ihn jemand entfernen kann. Empfehlung: gemeinsamer Name `"spotlab"` bleibt, ergänzt um eine echte Frischeprüfung über `time_since_valid_response` (S1.5) — das behält die Selbstheilung und schliesst die Lücke gleichzeitig.

**Reihenfolge der sechs zurückgestellten Erweiterungen (Sim-Adapter, Debugger, Arm, Docking, Mehrbenutzer-Dienst, automatische Parameteranpassung).** Das hängt einzig davon ab, ob der Autor als Nächstes an einen echten Roboter mit Schülern will (dann: keine davon, erst A1 abschliessen) oder danach an der Maturaarbeit weiterbaut (dann: Sim-Adapter zuerst, da kein Personenschaden-Risiko und pädagogisch wertvoll — aber zwei Grundsatzentscheidungen vorher nötig: Zeitmodell-Konflikt zwischen `walk()`-Wanduhr-Sleeps und `SpotSdkSim.run(duration)`, sowie eine Power-Zustandsmaschine, die es heute nicht gibt). Arm klar zuletzt: einziges Nicht-Ziel mit Personenschaden-Risiko im ganzen Befundkatalog, braucht einen eigenen Sperrpunkt-Assistenten nach A1/A16-Muster, bevor irgendein Schülerskript den Arm bewegen darf. Empfehlung: Sim-Adapter vor Debugger vor Docking vor Arm, Mehrbenutzer-Dienst zuletzt oder nie (siehe nächster Punkt).

**Lehrersicht/Sammelansicht/Klassenverwaltung bauen oder nicht?** Echter Alltagsnutzen für Lehrpersonen, aber gross im Aufwand (mehrere `RunWatcher`-Timer auf Schullaptops) und bislang reine Vermutung, ohne dass eine einzige echte Unterrichtsstunde stattgefunden hat. Optionen: (a) jetzt nicht bauen, (b) minimale read-only Sammelansicht vorab. Empfehlung: (a) — zurückstellen, bis nach A1 und nach der ersten echten Schulstunde; dann zeigt sich, ob das Bedürfnis real ist oder ob eine geteilte Bildschirmansicht am Lehrerpult genügt.

**Wie viel MCP-Automatisierung für die Kalibrierkampagne lohnt sich (`vergleich_real_sim.py` als Manifest-Eintrag, S5 Punkt 12 aus dem Rohmaterial)?** Grosser Aufwand für einen Forschungsschritt, dessen Vergleichsdefinitionen selbst noch fehlerhaft sind (S3.2/S3.3). Empfehlung: zurückstellen, bis die Definitionsfixe aus S3 stehen — sonst automatisiert man eine noch falsche Vergleichsmethode und macht den Fehler schneller reproduzierbar statt ihn zu beheben.

**Private vs. öffentliche Fernablage für CI/CD.** Für ein Sicherheitsprodukt, das noch nicht am echten Gerät gelaufen ist, ist die Sichtbarkeit des Repos eine bewusste Wahl, keine rein technische. Empfehlung: privates GitHub-Repo — CI/CD-Funktionalität ändert sich dadurch nicht, das Risiko einer vorzeitigen öffentlichen Sicherheitsdiskussion entfällt.

---

## Sicherheit: vor dem ersten Schuelerbetrieb

**Gesamtbild:** Die Not-Aus-/Lease-Kernmechanik haelt im sauberen Einzelschueler-Normalfall (ein Laptop, ein Lauf, kein Absturz). Alle scharfen Luecken liegen an den Raendern: Verbindungsaufbau/-abbau, GUI-Nebenlaeufigkeit (zwei Laeufe, Editor-Crash, Ausgabeflut), der zweite Bewegungsbefehl `move()`, und Konfigurationsdateien ohne Pruefung. Kein Befund zeigt einen Weg, den Roboter *waehrend echter Bewegung* unkontrollierbar zu machen. **Wichtigster Vorbehalt fuer die gesamte Liste:** Kein einziger Punkt wurde am echten Spot beobachtet – alles stammt aus Code-Lektuere, SDK-Quelltext-Pruefung und Dry-Run-Ausfuehrung. Der Sperrpunkt A1 (Not-Aus-Koexistenz) ist explizit markiert; Punkte danach sind vor regulaerem Schuelerbetrieb, aber nicht zwingend vor A1 selbst zu klaeren.

### (A) Am Code zu beheben — vor A1

Risikoreihenfolge, hoechstes zuerst:

1. **E-Stop-Koexistenz-Kette kann eine fremde, aktive Sitzung hart abschalten.** `src/spotlab/backends/real/estop.py:12` (`ENDPOINT_NAME="spotlab"` fest) + `:34-36` (`register_coexisting` verdraengt jeden gleichnamigen Endpunkt ohne Frische-Pruefung ueber `time_since_valid_response`) + `src/spotlab/backends/real/session.py:64-70` (E-Stop wird vor der Lease ohne try/finally registriert; scheitert `lease.start()`, laeuft der Keepalive-Thread unbeaufsichtigt weiter) + `estop.py:48-88` (kein Pendant zu `LeaseGuard._melde_verlust` – ein verlorener eigener Endpunkt bleibt unsichtbar). Ausloeser: zwei spotlab-Sitzungen gegen dieselbe Config (auch derselbe Schueler, der versehentlich zweimal startet), im Fenster "verbunden, Motoren aus" – also Skriptstart/-ende. Wirkung: die zweite Registrierung kann die erste, aktive Sitzung auf `ESTOP_LEVEL_CUT` setzen (SDK: `register()` endet mit `stop()`); ueberlebt der verdraengende Prozess, bleibt der Endpunkt der ersten Sitzung dauerhaft verwaist – deren GUI-NOT-AUS wirkt dann nicht mehr auf die Motorleistung. Fix: Frische ueber `get_status()` pruefen statt Namensgleichheit, Aufbauschritte in `connect()` per try/except zurueckrollen. **Warnung fuer die Umsetzung:** ein instanzspezifischer Name waere selbst gefaehrlich – er zerstoert die in `tests/test_real_estop.py:64` geprueften Selbstheilung (abgestuerzter Lauf wird beim naechsten Start ersetzt); richtig ist Frische-Pruefung, nicht Namensaenderung.

2. **`spotlab doctor` kann A3 ("kein zurueckgelassener Endpunkt") nicht pruefen.** `src/spotlab/workshop/doctor.py:103-115` fragt nur den aggregierten `stop_level` ab, nie `get_config()` auf einen verwaisten `"spotlab"`-Endpunkt. Haengt direkt an Punkt 1 – ohne diese Erweiterung ist der wichtigste Beleg fuer "A1/A3 bestanden" nur durch Handpruefung am Tablet erreichbar, nicht automatisiert.

3. **`end_time_secs` ist ein Zeitpunkt, keine Dauer.** `src/spotlab/api/motion.py:58` uebergibt `end_time_secs=1.0` an `synchro_velocity_command`; im bosdyn-SDK ist das Feld ein absoluter Unix-Zeitstempel – `1.0` heisst "abgelaufen seit 1970". `move()` (`motion.py:85`) sendet die Trajektorie sogar ganz ohne dieses Feld. Falls zutreffend scheitert der erste Bewegungsbefehl (`walk()` oder `move()`, beides im Anfaengertutorial) am echten Roboter mit unuebersetzter Ausnahme (`ExpiredError`, von `errors/translate.py` nicht erkannt). Muss vor jedem weiteren Bewegungstest geklaert werden, sonst verfaelscht dieser Fehler alle A5/A6/A8/A9-Messungen. Tatsaechliches Verhalten nur am Geraet zu bestaetigen (siehe (B)).

4. **`move()` wendet den konfigurierten Geschwindigkeits-/Drehratendeckel nie an.** `src/spotlab/api/motion.py:64-89` nimmt `limits` entgegen, benutzt es nirgends – ausgefuehrt bestaetigt: `MobilityParams.vel_limit` bleibt leer. `walk()` klemmt korrekt (`clamp()`, `motion.py:26-30`), `navigate_to()` auch. Verschaerfend: `backends/real/graphnav.py:107-109` behauptet faelschlich, der Deckel gelte "fuer `walk()` und `move()`" – eine Lehrperson, die `max_speed` herunterdreht, glaubt faelschlich, `move()` sei mitgedeckelt. `move()` ist der erste Bewegungsbefehl im Tutorial (`workshop/templates/hallo_spot.py:22`) und laeuft ungebremst mit SDK-Standardtempo.

5. **`config.toml` ohne Wertebereichspruefung kann nicht angeforderte Bewegung erzeugen.** `src/spotlab/config.py:90-93` uebernimmt `max_speed`/`max_turn_rate` ungeprueft. Ausgefuehrt bestaetigt: ein negatives `max_turn_rate` laesst `clamp()` (`motion.py:26-30`) fuer **jedes** `wz`, auch `wz=0`, die volle Drehrate einsetzen – `walk(vx=0.3)` ohne jede Drehanforderung faehrt dann mit voller Drehrate ("erfundene Bewegung", kein blosses Fehlen einer Grenze). `max_speed=inf` macht den Deckel wirkungslos, negativ kehrt die Richtung um. Die GUI-Spinbox (`gui/views/checkup.py:45`) kann solche Werte nicht erzeugen, klemmt aber einen aus der Datei geladenen `inf`-Wert nur in der Anzeige still auf `1.6` – die Datei selbst bleibt gefaehrlich. `config.toml` ist eine gewoehnliche, vom Schueler beschreibbare Textdatei ohne Schutz.

6. **Kein Schutz gegen zwei gleichzeitige Laeufe im Hauptfenster.** `src/spotlab/gui/app.py:207,242,261` pruefen nirgends, ob bereits ein Lauf verfolgt wird; `LiveView._lauf` zeigt nur auf den zuletzt entdeckten Prozess. Reproduziert: startet ein Schueler zweimal (GUI+GUI oder GUI+F5 aus VS Code, laut A11 ausdruecklich unterstuetzt), kann Stopp/NOT-AUS "es laeuft kein Programm" melden, waehrend der zweite Lauf weiterfaehrt, oder den falschen Prozess treffen. Physischer Tablet-NOT-AUS bleibt unberuehrt, ersetzt den Fix aber nicht.

7. **Dritter Startweg (Anbindungen/MCP) fuer echten Roboterbetrieb hat keinen gleichwertigen Stopp-Zugang.** Ein `roboter=true`-Lauf aus "Anbindungen" hat keinen eigenen Stopp-Knopf und wechselt nicht automatisch zur Live-Ansicht (`gui/views/anbindungen.py:306-317`, kein Abnahmepunkt dafuer). Zusaetzlich startet `mcp/werkzeuge.py:144` Skripte ohne Prozessueberwachung, `lauf_stoppen` (`werkzeuge.py:24`) kennt nur den freundlichen Stopp (`_thread.interrupt_main()`, kann bei vollgelaufener Ausgabe-Pipe verzoegert/gar nicht wirken) – kein harter Stopp ueber MCP erreichbar. Ein so gestarteter echter Roboterlauf ist schwerer zu stoppen als ein regulaerer GUI-Lauf.

8. **`SPOTLAB_NUR_TROCKEN` wird nur an einer Stelle geprueft, nicht an der Backend-Quelle selbst.** Grep bestaetigt: Pruefung ausschliesslich in `src/spotlab/__init__.py:14,47`; `RealSpot.connect()`/`verbindung.py` enthalten keinen Bezug. Wert wird bei jedem `connect()` live aus `os.environ` gelesen statt eingefroren. Ein direkter Import von `RealSpot` unter Umgehung von `spotlab.connect()`, oder ein Skript, das die Variable vor dem Verbindungsaufbau entfernt, hebt die als "nicht verhandelbar" deklarierte Obergrenze auf. Relevant, sobald Fremdprojekte (Anbindung) eigenen Code ausfuehren.

9. **JediWorker-Thread beim Schliessen eines Editor-Reiters zerstoert das ganze Fenster.** `src/spotlab/gui/editor/completer.py:195-204` haengt einen `QThread` als Kind der `Vervollstaendigung`-Instanz auf; `EditorView._schliesse()` (`view.py:364`) ruft nur `deleteLater()`. Ausgefuehrt reproduziert: Absturz (`0xC0000409`) im Zeitfenster des ersten `jedi`-Aufrufs (~0,9-9,5s). Absturz des Fensters mit dem NOT-AUS-Knopf, waehrend ein Roboterlauf im Kindprozess (kein Job-Objekt) fuehrerlos weiterlaufen kann; dieselbe Luecke betrifft `OutputReader` in `app.py:214` beim Schliessen des ganzen Fensters waehrend eines laufenden Programms.

10. **GUI-NOT-AUS meldet Erfolg unabhaengig davon, ob `taskkill` wirklich wirkte.** `src/spotlab/workshop/control.py:64-72` verwirft den Rueckgabewert von `taskkill` (`check=False`); `beende_hart()` (`control.py:88-89`) meldet `True` unabhaengig vom tatsaechlichen Erfolg. Schlaegt `taskkill` fehl, zeigt die GUI trotzdem Erfolg und blendet den Eskalationsknopf aus – ein fehlgeschlagener NOT-AUS ist von einem erfolgreichen nicht unterscheidbar. Kein Test uebt den echten `taskkill`-Pfad aus.

11. **A9 (NOT-AUS waehrend des geordneten Abbaus) prueft nicht, was sie behauptet.** Das Liveness-Signal haengt an `zustand.jsonl`; `spotlab/__init__.py:107-110` stoppt den Abtaster als allerersten Abbauschritt, lange bevor `RealSpot.close()` (Hinsetzen, `power_off(timeout_sec=20)`) fertig ist. `ist_aktiv()` meldet daher "laeuft nicht mehr", waehrend der eigentliche Abbau noch laeuft; der Eskalations-Timer (3s) kommt praktisch immer zu spaet. A9 kann als "bestanden" gelten, ohne dass je gezeigt wurde, dass NOT-AUS waehrend eines echten Abbaus wirklich toetet. Fix: Liveness-Signal von der Abtaster-Datei loesen.

12. **Beschaedigte `config.toml` sperrt das gesamte Werkzeug inklusive Reparaturweg.** `src/spotlab/config.py:79` faengt `tomllib.TOMLDecodeError` nirgends ab – betrifft jeden Befehl, `gui/app.py:56-59` (das Fenster mit dem NOT-AUS-Knopf oeffnet gar nicht), sogar `spotlab login` selbst. Real ausloesbar durch einen unescaped Windows-Pfad unter `[editor]` (von der eigenen Fehlermeldung nahegelegt) oder Notepad-BOM/ANSI-Speicherung.

13. **Beschaedigte `graph`-Datei einer Karte kann den GUI-Start komplett verhindern.** `src/spotlab/maps/store.py:62-65` fangen nur `OSError`, nicht `DecodeError`; `MainWindow.__init__` ruft synchron `karten()` fuer den ganzen Arbeitsordner auf – reproduziert. Eine defekte Karte verhindert den Zugriff auf den NOT-AUS-Knopf vollstaendig.

### (A) Am Code zu beheben — nach A1, aber vor regulaerem Schuelerbetrieb

14. **Editor-Ausgabefenster wird bei Ausgabeflut quadratisch langsam und blockiert dabei den NOT-AUS.** `src/spotlab/gui/editor/view.py:101` ruft `toPlainText()` ueber das gesamte Dokument bei jeder Zeile. End-to-End mit echtem Kindprozess reproduziert: Qt-Ereignisschleife blieb drei Minuten durchgehend besetzt – ein NOT-AUS-Klick haette dort in der Warteschlange gestanden. Gleiches Muster in `gui/views/live.py:65-66,157-158`. Fix muss die Ursache (Zeilen buendeln in `workers.py`) angehen, nicht `setMaximumBlockCount` isoliert setzen (wuerde die absoluten Positionen der Traceback-Links verschieben).

15. **Ctrl-C waehrend `close()`/vor `spot.close()` ueberspringt Abbauschritte.** `src/spotlab/backends/real/session.py:220-225` faengt nur `Exception`; `abtaster.stop()` (`spotlab/__init__.py:107-112`, blockierend) liegt sogar ausserhalb jedes try/finally, vor `spot.close()`. Ein zweites, gezielt in dieses Fenster fallendes Ctrl-C ueberspringt `power_off`, Lease-Rueckgabe, Estop-Abmeldung. Fix: pro Schritt `BaseException` fangen, alle Schritte durchlaufen, danach erneut werfen – kein `except BaseException: pass` (wuerde Ctrl-C verschlucken und den Lauf faelschlich als "ok" verbuchen).

16. **Lease-Verlust waehrend der letzten Wartephase von `move()`/`stand()`/`sit()` bleibt unbemerkt.** `session.py:123-124` (`command_feedback()`) prueft weder Lease-Verlust noch uebersetzt Fehler, anders als `send_command()`/`power_on()`. Keine neue physische Gefahr (Server verweigert dem Laptop die Steuerung ohnehin), aber ein WLAN-Aussetzer waehrend des Wartens wirft eine rohe bosdyn-Ausnahme statt der deutschen Meldung.

17. **Backend-Bezeichner ist ein ungeprueftes freies String.** `spotlab/__init__.py:37` faellt bei jedem Wert ausser `"dryrun"` in den echten Roboter-Pfad; `default_backend` aus der TOML ebenso ungeprueft. Latentes Risiko bei Tippfehler in Handbearbeiteter `config.toml`.

18. **Keine Protokollierung sicherheitsrelevanter Abbau-Fehler.** `RealSpot.close()`, `EstopGuard.stop()` (`estop.py:82-86` – eigener Kommentar: fehlgeschlagene Deregistrierung hinterlaesst dem naechsten Schueler einen "scheinbar defekten Spot"), `LeaseGuard.stop()` verschlucken Ausnahmen spurlos; kein `logging` im gesamten `src/`-Baum. Wird kritisch, wenn nach einem Vorfall nichts mehr rekonstruierbar ist.

19. **"Gab es Not-Aus?" ist aus keiner Aufzeichnung rekonstruierbar.** `SafetyStatus.estop_level` wird im ganzen Quellbaum nirgends ausser der eigenen Definition benutzt – fuer eine Lehrperson, die einen Lauf nachtraeglich beurteilt, ist der Not-Aus-Status heute unsichtbar.

20. **`record/` verletzt die nicht-verhandelbare Schichtgrenzen-Regel.** `record/sampler.py:20` importiert transitiv `bosdyn`. Heute funktional folgenlos, aber Verstoss gegen eine erklaerte Nicht-verhandelbar-Regel und Hindernis fuer den kuenftigen Sim-Adapter – vor dessen Bau zu beheben.

21. **Testluecke: `EstopGuard` selbst nur ueber Attrappe geprueft.** `test_real_session.py` verwendet `FakeEstopGuard`; der echte Abbau-Pfad (inkl. `except Exception: pass`) wird nie direkt getestet. Luecke im Belastbarkeitsnachweis von A1, kein beobachteter Fehler.

22. **Modale Dialoge blockieren applikationsweit den NOT-AUS-Knopf (kontrovers, mittel/niedrig).** `QMessageBox`/`QFileDialog` mit `exec()` sind `ApplicationModal`, reproduziert. Kein Codefix von beiden Gegenpruefern empfohlen; Vorschlag: Regel in `docs/ABNAHME.md` ("waehrend eines Laufs keine Dialoge offen lassen").

### (B) Nur am Geraet in der Halle pruefbar — vor A1

- **Tatsaechliches Verhalten von `walk()`/`move()` am echten Spot** (Punkt 3 oben): wirft der Roboter wirklich `ExpiredError`, oder passiert etwas anderes? Muss vor jedem weiteren Bewegungstest geklaert werden, sonst verfaelscht dieser Fehler alle folgenden Messungen.
- **Physisches Verhalten bei einer `register_coexisting`-Verdraengung** (Punkt 1): faellt der Roboter kontrolliert in den Stand, oder tatsaechlich um? Zwischen den Gegenpruefern strittig, ob der Endzustand meist ein sicherer harter Cut ist.
- **A2 (Prozess-Kill, SDK-garantiert) unabhaengig vor oder parallel zu A1 verifizieren** – es ist die vom eigenen Code unabhaengige Rueckfallebene, falls A1 in der Halle unerwartet nicht reagiert.
- **Reale Reaktionszeit von `KeyboardInterrupt` waehrend eines laufenden gRPC-Aufrufs** – ob ein zweites Ctrl-C tatsaechlich in einem Abbauschritt landet oder von einem blockierenden Aufruf lange verzoegert wird.
- **Reales Timing von `power_off()` (Timeout 20s)** – ob und wie lange der Abbau tatsaechlich dauert, relevant fuer die A9-Eskalationslogik nach deren Reparatur.
- **Physisches Verhalten des Hardware-Not-Aus (Tablet) selbst** – im gesamten Rohmaterial ungeprueft, keine Aussage moeglich.

### (B) Nur am Geraet — nach A1, im laufenden Schulbetrieb zu beobachten

- Reales WLAN-Latenzprofil und Timesync-Drift der Schulhardware – beeinflusst z.B., ob ein RPC-Haenger die GUI faelschlich "beendet" anzeigen laesst, waehrend der Roboter real weiterfaehrt.
- Tatsaechliches Verhalten von `taskkill` auf den Schul-Laptops (Berechtigungen, Sonderfaelle).
- Organisatorisch sicherstellen, dass keine zwei Laptops denselben (z.B. Netzlaufwerk-)Arbeitsordner verwenden – sonst wirkt der harte NOT-AUS nicht rechneruebergreifend, waehrend der freundliche Stopp es faelschlich suggeriert. Laut Konzeption nicht vorgesehen, aber am Geraet/organisatorisch zu bestaetigen.
- Ob in der Praxis modale Dialoge waehrend eines laufenden Programms offen gelassen werden (Schulungsfrage, siehe Punkt 22).

### Vorarbeit fuer spaeter (Arm, Debugger) — nicht blockierend fuer heutigen Betrieb, aber vor Bau zu entscheiden

- **Arm:** kein Sperrpunkt-Aequivalent zum GraphNav-Geschwindigkeitsdeckel; das SDK selbst warnt "The robot Arm does not have any obstacle avoidance capability". Einziger Befund im gesamten Material mit Personenschaden- statt nur Sachschaden-Risiko. Vor jeder ersten Zeile Arm-Code: eigener Sperrpunkt nach A1/A16-Muster.
- **Debugger:** ein angehaltener Prozess mit gehaltenem Lease ist sicherheitstechnisch das Gegenteil der Stufe-1-Architektur; `move()/stand()/sit()` haben ohnehin kein Nachsende-Sicherheitsnetz, der EstopKeepAlive laeuft waehrend einer Pause unbeeinflusst weiter. Bestaetigt den bestehenden Nicht-Ziel-Entscheid als richtig.

### Was hier NICHT gefunden wurde

Kein Befund zeigt einen Weg, den Roboter waehrend aktiver Bewegung unkontrollierbar zu machen – alle scharfen Fenster liegen bei "Motoren aus" (Skriptstart/-ende) oder waehrend des geordneten Abbaus. Kein Verstoss gegen Lease-Disziplin oder den Ein-Leser-Grundsatz ausserhalb der oben genannten Punkte; die einzige gefundene Schichtgrenzen-Verletzung ist `record/`→`api/`→`bosdyn` (Punkt 20), heute ohne Laufzeitfolge. Nicht geprueft werden konnte, wie im Auftrag angelegt, jedes Verhalten, das nur am echten Geraet sichtbar wird (reale Reaktionszeiten, echtes WLAN-Verhalten, physischer Tablet-Not-Aus) – die oben unter (B) "vor A1" gelisteten Punkte sollten deshalb als Erstes am Geraet geklaert werden, bevor weitere A1-Tests darauf aufbauen.

---

## Was diese Untersuchung nicht abgedeckt hat

1. **Die Kartenaufzeichnung (`src/spotlab/maps/session.py`, `src/spotlab/gui/recorder.py`, `src/spotlab/gui/views/maps.py`) wurde von keinem der 7 Cluster inhaltlich geprüft.** Das zählt, weil CLAUDE.md diese Zone ausdrücklich als sicherheitsrelevante Sonderregel führt ("Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von `src/spotlab/maps/`") und `docs/ABNAHME.md` mit A13 einen eigenen Abnahmepunkt dafür hat — trotzdem kommt in keinem der 82 Sucher-Ergebnisse ein Fund zu diesem Code vor. Selbst geprüft: `MainWindow.closeEvent` (`gui/app.py:269-272`) stoppt beim Schliessen des Fensters nur den `RunWatcher`, ruft aber nie `MapsView._beende_worker()` auf. Läuft eine Kartenaufnahme (`RecordingWorker`, ein `QThread` mit einer echten, offenen Verbindung zum `GraphNavRecordingServiceClient`) und die Schülerin schliesst das Fenster über das X, bleibt der Thread als Kind eines zerstörten Widgets zurück — exakt dasselbe Absturzmuster, das G1 Punkt 5 für den `JediWorker` in `completer.py:195-204` fand, hier aber an einem Thread mit einer aktiven Robotersitzung statt an einer Autocomplete-Anfrage. Schliessen: gezielten Test/Review von `maps/session.py` + `gui/recorder.py` nachholen, `_beende_worker()` aus `closeEvent` erreichbar machen.

2. **Windows-spezifische Dateisperren (OneDrive/SharePoint-Sync, Echtzeit-Virenscan) auf dem fsync-lastigen Schreibpfad wurden von keinem Cluster geprüft**, obwohl mehrere Gruppen Atomarität und Fehlerbehandlung von `record/run.py` intensiv besprachen. Selbst geprüft: `_zeile()` (`record/run.py:130-135`) öffnet, schreibt und fsynct bei **jedem** Ereignis/jeder Abtastung neu, ohne try/except; `connect()`s abschliessender `recorder.finish()`-Aufruf sitzt ungeschützt in einer `finally`-Kette (`__init__.py:107-112`). Der 10-Hz-Sampler selbst fängt Schreibfehler ab (`record/sampler.py:80-84`), aber die einmaligen Ereignis-Schreibvorgänge (`lease_übernommen`, `ende`, `verbunden`) tun das nicht. Ein transientes `PermissionError`/`WinError 32` durch OneDrive-Ordnerumleitung oder Virenscan — auf verwalteten Schul-Laptops keine Seltenheit — würde am Ende eines Laufs die eigentliche Ursache (`LeaseLost`, `KeyboardInterrupt`) durch eine irreführende I/O-Ausnahme ersetzen. Schliessen: `recorder.finish()` in `connect()`s Finally-Block selbst absichern; Windows-Cloud-Sync/AV-Interferenz als eigene Testkategorie aufnehmen.

3. **Live-Wechsel des Windows-Hell/Dunkel-Modus während einer laufenden Lektion wurde nirgends untersucht.** G7 fand mehrfach fehlenden oder zu schwachen Kontrast in einzelnen Widgets (NOT-AUS-Beschriftung, Karten-/Laufdiagramm), aber alle Funde gehen von einem statischen Modus aus. Selbst geprüft: `system_ist_dunkel()` (`gui/app.py:39-45`) wird nur zweimal beim Programmstart gelesen (Zeile 61, 278); es existiert kein Listener auf `QStyleHints.colorSchemeChanged`. Schaltet Windows während der Stunde automatisch um (verbreitete Zeitplan-Einstellung), bleibt spotlab dauerhaft auf dem Start-Zustand eingefroren — was die bereits gefundenen Kontrastprobleme unbemerkbar für die ganze restliche Sitzung festschreiben kann. Schliessen: Signal abonnieren und Palette/Stylesheet zur Laufzeit neu anwenden, oder zumindest dokumentieren, dass ein Neustart nötig ist.

4. **Testabdeckung wird nirgends tatsächlich gemessen — das wurde von keinem Cluster hinterfragt.** `pyproject.toml` enthält kein `pytest-cov` und keine Coverage-Konfiguration (selbst geprüft, kein Treffer im ganzen Repo ausser einem unrelated `noqa`-Codenamen). "681 Tests, alle grün" wird von jedem der 7 Cluster als Vertrauensanker zitiert; G4, die Gruppe mit dem gründlichsten Blick auf CI/Tooling, diskutiert Linting, Typprüfung und Versionierung, fragt aber nie, welchen Anteil des Codes diese 681 Tests überhaupt ausführen. Ohne diese Zahl ist unklar, ob z. B. `backends/real/graphnav.py` oder `maps/session.py` (siehe Punkt 1) überhaupt in nennenswertem Umfang von der Suite berührt werden. Schliessen: `pytest-cov` einführen, Baseline-Prozentsatz je Modul festhalten, insbesondere für `backends/real/` und `maps/`.

5. **Schul-IT-spezifische Umgebungsfaktoren wurden nur oberflächlich als offene Frage benannt, nie als eigene Kategorie durchdacht.** G4 Punkt 9 sagt ausdrücklich "Verteilung an Schul-Laptops ist konzeptionell noch nicht angefangen", beschränkt sich dort aber auf Installationsweg und venv. Nicht gestellt wurde die Frage, was mit `keyring` passiert, wenn eine Gruppenrichtlinie den Windows-Anmeldeinformationsspeicher einschränkt oder umleitet (verbreitet auf domänenverwalteten Schulgeräten), oder was passiert, wenn der Arbeitsordner der Schülerin über "Bekannte Ordner verschieben" in OneDrive liegt (siehe auch Punkt 2). Schliessen: einmal an einem echten, von der Schul-IT verwalteten Laptop-Image prüfen, nicht nur an einer Entwicklungsmaschine.

6. **`src/spotlab/maps/geometry.py` (Grundriss-Berechnung aus dem GraphNav-Graph) hat keinen einzigen Treffer in den 82 Sucher-Ergebnissen.** Das ist eine dünne Stelle, weil `docs/ABNAHME.md` mit A14 ("Gegenprobe zur Interoperabilität") genau dieses Modul explizit als Prüfgegenstand nennt und es zwei nicht-triviale Rekonstruktionspfade enthält (`_aus_ankern`, `_aus_kette` mit Breitensuche). Weder Korrektheit noch Robustheit (z. B. gegen einen Graphen mit Zyklen ohne Anker, wo die Breitensuche in `_aus_kette` real bereits gegen doppelte Besuche abgesichert ist, aber nie mit einem gezielten Testfall gegengeprüft wurde) kommt in den Ergebnissen vor. Schliessen: gezielte Prüfung von `maps/geometry.py` nachholen, insbesondere den Fall unvollständiger Anker + Zyklen.

7. **Ob die gepinnte SDK-Version (`bosdyn-client==5.0.1.2`, `pyproject.toml:11`) mit der Firmware des konkreten Schul-Spot kompatibel ist, wurde von keinem Cluster gefragt.** G4 diskutiert Abhängigkeits-Reproduzierbarkeit ausführlich (Punkt 8), aber nur bezogen auf offene Untergrenzen bei `numpy`/`PySide6` usw., nie bezogen auf die Kompatibilität von Client- und Robot-Firmware-Version — in der Praxis eine der häufigsten Ursachen, warum an einem echten Spot zunächst gar nichts funktioniert, noch vor dem in G1/G2 gefundenen `end_time_secs`-Fehler. Schliessen: vor dem ersten Gerätetest die Firmware-Version des Schul-Spot gegen die SDK-Kompatibilitätstabelle von Boston Dynamics prüfen.

8. **Eine Behauptung in G5 blieb unbelegt, weil die vorhandene Testdatei nicht dagengelesen wurde.** G5 Punkt 2 schreibt, `SPOTLAB_NUR_TROCKEN` sei "nur einlagig geprüft" und leitet daraus die höchste Einzel-Schwere der ganzen Gruppe ab. Selbst geprüft: `tests/test_schranke.py` existiert bereits mit sieben gezielten Tests genau für diese Schranke (inklusive des Falls, dass ein explizites `backend="real"` die Umgebungsvariable überschreiben soll) — der von G5 tatsächlich korrekt gefundene Rest-Fund (direkter Import von `RealSpot`/`verbinde()` unter Umgehung von `spotlab.connect()`, geprüft in `tests/test_real_session.py`, wo `NUR_TROCKEN` kein einziges Mal vorkommt) ist damit präziser zu fassen als "der dokumentierte Weg ist gut getestet, der Bypass-Weg gar nicht" statt "nur einlagig geprüft". Das ändert nichts an der Dringlichkeit des Fixes, aber die Schärfe der Formulierung sollte auf den tatsächlich ungetesteten Bypass-Pfad zielen. Schliessen: `test_schranke.py` um einen Testfall für den direkten `RealSpot.connect()`-Aufruf ergänzen, dort wo die Lücke tatsächlich sitzt.

9. **Keine der 7 Gruppen hat nach einem Gesamtbild gefragt: wie viele der als "kritisch/hoch" eingestuften Befunde teilen sich denselben Auslöser (zwei gleichzeitig aktive Instanzen/Sitzungen)?** Das ist auffällig dünn, weil G1, G2 und G7 unabhängig voneinander mehrere Funde auf genau dieses eine Muster zurückführen (E-Stop-Verdrängung, Lauf-Verwechslung im Hauptfenster, Lease-Kollision), aber keine Gruppe das explizit als **einen** übergreifenden Konstruktionsfehler ("keine Instanzerkennung über mehrere gleichzeitige spotlab-Prozesse hinweg") benennt und daraus eine gemeinsame Lösung ableitet, statt vier bis fünf Einzel-Patches vorzuschlagen. Schliessen: vor Einzel-Fixes prüfen, ob ein gemeinsamer Mechanismus (z. B. ein prozessübergreifendes Sitzungs-Register unterhalb von `~/.spotlab/`) mehrere der in G1/G2/G7 gefundenen Lücken auf einmal schliesst, statt sie getrennt zu patchen.