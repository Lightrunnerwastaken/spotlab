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
- **Genau ein Lauf ist der, auf den Stopp und NOT-AUS zeigen.** `_lauf_begonnen` hängt die
  Live-Ansicht **nie bedingungslos** um: läuft der bisherige noch, wartet der neue in
  `_wartende_laeufe` und rückt erst nach. Zwei gleichzeitige Läufe sind kein konstruierter
  Fall — aus „Projekte" starten, dann aus „Code", oder zusätzlich F5 aus VS Code (A11).
  Zeigt die Ansicht auf den falschen Prozess, trifft der NOT-AUS den falschen, während der
  andere den Roboter hält.
- **`closeEvent` beendet auch die Kartenaufnahme.** `MapsView._worker` ist ein `QThread`
  mit einer OFFENEN Robotersitzung; ohne den Aufruf bliebe er als Kind eines zerstörten
  Widgets zurück. Dasselbe Absturzmuster wie beim `JediWorker`, nur mit einer laufenden
  Verbindung zum Spot.
- **Es gibt genau einen `OutputReader` pro Lauf.** Die Ausgabe-Pipe hat genau einen Leser;
  ein zweiter teilte sich die Zeilen zufällig mit dem ersten. Neue Ansichten hängen sich als
  weitere Senke an `app.py::_starte_leser`, nie mit einem eigenen Leser an den Prozess.
- **Ein Widget wird nie zerstört, solange ein Thread darunter arbeitet.** Vor
  `deleteLater()` auf einem `CodeEdit` erst `Vervollstaendigung.schliesse()` — sonst wird
  ein laufender `JediWorker`-QThread destruiert und reisst das ganze Fenster mit, samt
  NOT-AUS-Knopf. Dieselbe Regel gilt für `MapsView._worker` beim Fensterschliessen. Erst
  trennen, dann warten: eine Antwort, die eine Millisekunde zu spät kommt, darf das
  zerstörte Widget nicht mehr anfassen.
- **`Ausgabefeld.haenge_an` führt die Dokumentlänge laufend mit, statt `toPlainText()` zu
  rufen.** Jener kopiert bei jeder Zeile das ganze Dokument — gemessen 0.070 ms/Zeile bei
  500 Zeilen, 0.402 bei 4000, also quadratisch; auf 50 000 Zeilen Minuten, in denen die
  Ereignisschleife besetzt ist und ein Klick auf NOT-AUS in derselben Warteschlange steht.
  Die Zahl muss stimmen: an ihr hängen die Zeichenpositionen der anklickbaren
  Traceback-Stellen. **Eine Pufferbegrenzung gibt es bewusst nicht** — sie verschöbe alle
  Positionen und schickte den Schüler in die falsche Datei.
- **Ein Skript mit `roboter = true` aus „Anbindungen" holt die Live-Ansicht nach vorn.**
  Fremder Code ohne Trockenlauf-Schranke, der den echten Spot bewegt, ist der am wenigsten
  geprüfte Startweg im Fenster; da schlägt Sicherheit die Bequemlichkeit. Bei
  `roboter = false` bleibt die Ansicht bei den Panels, sonst wird die Regel im Alltag
  umgangen.
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
- **Der Takt wartet über `time.sleep()`, nie über `Event.wait()`.** Jenes geht unter
  Windows über den GROBEN Zeitgeber (Auflösung 15.6 ms): 20 ms angefordert werden zu
  31 ms geliefert, aus 50 Hz werden 32. `time.sleep()` nutzt seit Python 3.11
  hochauflösende Timer. Gemessen am 12.08.2026: 34.0 gegen 49.0 Hz im nachgestellten
  Takt, 34.09 gegen 46.13 Hz in der vollen Trockenprobe — und die reale Messfahrt
  desselben Tages kam auf 34.1 Hz. **Die Grenze war nie das WLAN und nie der Roboter,
  sondern diese eine Zeile.** Der Preis ist eine Stopp-Verzögerung von bis zu 20 ms;
  `_warte()` schläft deshalb in Stücken. Ein Ratentest dazu wäre lastabhängig — geprüft
  wird der Quelltext, plus eine grosszügige Gegenprobe auf die Wartezeit selbst.
- **Der Abtaster liest die Periode NACH dem Zeitstempel der Abtastung, und das
  Messfenster schaltet den Takt um, BEVOR es das Startereignis schreibt.** Das
  Startereignis ist die Abschnittsgrenze des Lückenmelders. Lag die Periode vor dem
  Stempel und die Grenze vor dem Umschalten, trug eine Abtastung einen Stempel nach der
  Grenze und schlief trotzdem den alten 100-ms-Takt — gemessen gegen die 50-Hz-Erwartung
  des Fensters war das „Lücke 0.101 s", einmal in fünf Messfahrten (06.09.2026). Kein
  Jitter: ein Wettlauf um 0.6 ms. Stempel und Periode müssen aus derselben Zeit stammen.
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
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von
  `src/spotlab/beobachtung/`.** Dieselbe Regel wie bei `maps/`, und sie ist der
  ganze Grund, warum der Beobachter-Modus **vor** Abnahmepunkt A1 benutzbar ist:
  er nimmt dem Tablet nichts weg und kann den Roboter nicht bewegen.
  `Zustandsquelle` hat genau eine Methode — es gibt gar nichts zu missbrauchen.
  Ein Test hält zusätzlich fest, dass `StateSampler` nicht heimlich anfängt,
  mehr als `robot_state()` zu verlangen; sonst reichte die Nur-Lese-Quelle nicht
  mehr und die Aussage wäre still falsch geworden. **`Bildquelle` steht unter
  derselben Regel**: eine Methode, `ImageClient` liest nur.
- **Der Bildmitschnitt geht NICHT über `RunRecorder.image()`.** Jenes schreibt
  `bilder.json` bei jedem Bild vollständig neu — quadratisch in der Bildzahl —
  und legt ein Ereignis an. Und `bilder/` ist das Verzeichnis, das
  `gui/watcher.py` bei JEDEM Takt globbt, um das neueste Bild zu finden.
  Beides trägt eine Handvoll Schnappschüsse aus einem Schülerskript, keinen
  Dauerstrom von fünf Kameras über eine Stunde. Der Strom liegt deshalb in
  `kamera/` mit anhängendem Index `kamera.jsonl`.
- **Bilder werden wörtlich geschrieben, nie umkodiert.** JPEG als `.jpg`, alles
  andere als `.raw`. `api/perception.py::to_png_bytes()` normiert Tiefe für die
  ANZEIGE auf 8 Bit; im Aufnahmepfad wäre das ein stiller Totalverlust der
  Millimeterwerte — die Bilder sähen dabei völlig richtig aus.
- **Was konstant ist, steht einmal in `kamera/quellen.json`** (Intrinsik,
  Extrinsik, Tiefenskala), nicht in jeder der zehntausend Indexzeilen. Umgekehrt
  gehört `pose` in JEDE Zeile: sie ist zum Aufnahmezeitpunkt gelesen, und
  zwischen zwei 10-Hz-Abtastungen zu interpolieren kostete bei 0.3 m/s gut
  anderthalb Zentimeter je Bild.
- **Der Beobachter tastet ausserhalb der Messfenster REICH ab** — anders als
  `spotlab.connect()`. Dort ist der schlanke Satz richtig (50 RPCs/s über WLAN
  für Daten, die niemand ansieht); eine Messfahrt ist der umgekehrte Fall: sie
  findet einmal statt, und nur der reiche Satz trägt µ, Schlupf,
  Motortemperaturen und Faults.
- **Das Messfenster-Protokoll steht in `record/messfenster.py`, an genau einer
  Stelle.** `api/spot.py` und `beobachtung/session.py` delegieren beide dorthin.
  Zwei Formulierungen hiessen, dass `messung/fenster.py` bald zwei leicht
  verschiedene Fensterprotokolle lesen muss — und das fällt erst auf, wenn die
  Messfahrt vorbei ist.
- **Eine Trockenprobe mit leeren Messfenstern beweist nichts.** Der Zeitraffer
  darf die Wartezeiten kürzen, nicht die Messfenster: bei 40× blieben 0.05 s je
  Fenster, also null bis zwei Abtastungen, und die Probe liefe grün durch, ohne
  die Messkette berührt zu haben. `beobachten_real.py` hat dafür
  `PROBE_FENSTER_S` als Untergrenze in echten Sekunden, und ein Test prüft die
  Zahl der Abtastungen, nicht bloss die Existenz des Fensters.
- **Diagnose geht in eine DATEI, nie auf stdout oder stderr.** Die Ausgabe eines Laufs hat
  genau einen Leser, und der MCP-Server spricht über stdin/stdout ein Protokoll — ein
  `StreamHandler` dort hinein zerstörte beides. `spotlab/protokoll.py` schreibt neben die
  Aufzeichnung, wirft nie und schweigt ohne gesetztes Ziel. Die Abbaupfade fangen
  weiterhin alles, aber sie verschlucken es nicht mehr spurlos: nach einem Vorfall muss
  nachlesbar sein, warum der Spot sich nicht hingesetzt hat.
- **Vor dem Start werden ALLE geänderten Reiter gespeichert, nicht nur der sichtbare.** Und
  der Vergleich läuft gegen die Datei, nicht gegen Qts Modified-Flag: `setPlainText()`
  setzt das Flag zurück, die Markierung kann also falsch stehen.
- **Das Sim-Backend ist eine Interpolation von Messungen, keine Physik — und es
  sagt das.** `backend: "sim"` steht in `lauf.json`, der Hinweis „NICHT am Roboter
  erprobt" im `verbunden`-Ereignis. Wo keine Messung ist, steht **null oder gar
  nichts**: Gelenkmomente und -geschwindigkeiten bleiben 0.0, `terrain` wird nicht
  gesetzt, Kameras und GraphNav fehlen in `capabilities()`. Ein erfundener Reibwert
  0.6 oder ein erfundenes Bild sähe aus wie eine Messung und liefe in jede
  Auswertung — dieselbe Regel wie in `api/state.py`.
- **Es gibt keine Kurve „kommandiert → erreicht", und der Sim tut nicht so.** Im
  Beobachter-Modus hat niemand kommandiert; `ziel_m_s` ist die ABSICHT des
  Bedieners, und er hat mit der Live-Anzeige darauf hin gesteuert. Die Abweichung
  misst also die Tablet-Bedienung, nicht das Folgeverhalten des Roboters. Wer sie
  als Schleppfehler ausgibt, verkauft Bedienfehler als Robotereigenschaft. Der
  echte Schleppfehler bleibt unbekannt, bis jemand mit `gates_real.py`
  **kommandiert** misst — hinter Sperrpunkt A1.
- **Eine kombinierte Bewegung wurde nie vermessen.** Die B2-Fenster haben
  Drehraten um 0.000, die B3-Fenster Tempi um 0.005. Das Modell wählt deshalb die
  dominierende Achse, statt zwischen zwei Messreihen zu mischen, die nichts
  miteinander zu tun haben.
- **`OHNE_ROBOTER` in `spotlab/__init__.py` ist eine ERLAUBNISLISTE.** Nur die dort
  genannten Backends laufen unter `SPOTLAB_NUR_TROCKEN`. Ein neues Backend ist
  gesperrt, bis jemand es einträgt — und wer es einträgt, hat die Frage
  beantwortet, ob es den Spot bewegen kann. Als Sperrliste wäre jedes künftige
  Backend versehentlich frei.
- **Die Kalibrierung liest Läufe, sie schreibt keine.** `kalibrierung/` nimmt nur
  Läufe mit `backend` aus einer Erlaubnisliste — ein Trockenlauf hat erfundene
  Gelenkwerte. Bis zum 12.08.2026 ging das nicht: Probe und Messfahrt hiessen
  beide „beobachter", und die Probe fiel nur heraus, weil `DryRunBackend` alle
  Füsse am Boden lässt. Seither heisst die Probe **`beobachter-trocken`**.
- **Ein verschmolzener Gangzyklus verfälscht die Kennlinie, er verrauscht sie
  nicht.** Verpasst die Kontakterkennung einen Aufsetzer, entsteht ein Zyklus von
  doppelter Dauer; auf Phase 0..1 normiert zieht er zwei Schritte in den Platz von
  einem. `ZYKLUS_BAND` sortiert nach dem Median aus, und die Zahl der verworfenen
  Zyklen steht in der Herkunft — sonst sähe eine gesäuberte Kennlinie sauberer
  aus, als die Messung war.
- **Genau eine Datei unter `src/spotlab/` importiert `spotsim`: `backends/mujoco.py`.**
  Die Kopplung an matura-spot ist das Extra `[sim]`; ein zweiter Import wäre der Anfang
  einer Kopplung, die niemand entschieden hat, und fiele erst auf, wenn ein Laptop ohne
  matura-spot beim Start stirbt. Die GUI bleibt frei von `mujoco` und `spotsim`; sie liest
  das gerenderte Zimmer als `ansicht.jpg` aus dem Lauf-Verzeichnis
  (`tests/test_naht_spotsim.py`). `MujocoBackend` ERBT von `SimBackend` — Kommandos,
  Ziele, Gangphase, Antwort und Aufzeichnung gibt es genau einmal.
- **`unknown_cells` im LocalGrid ist ein BYTE je Zelle, x läuft am schnellsten.** Gemessen
  an einer echten `LocalGridResponse` vom 12.08.2026 (`tests/daten/gitter_real_20260812`);
  bis zum 06.09.2026 entpackte `gitter_aus` bitweise, und `is_free()` hielt am echten Spot
  Unbekanntes für frei. Das Gitter des echten Dienstes ist an den WELTACHSEN ausgerichtet;
  `ObstacleGrid` rechnet in Weltkoordinaten — `is_free(0.5, 0.0)` ist ein Weltpunkt, nicht
  „einen halben Meter voraus".
- **Eine Sperrzone ist eine REGEL, kein Hindernis.** Sie steht in keinem Gitter, wirft
  keinen Schatten und verändert das Gelände nicht — `zone_bei` sitzt bewusst NEBEN
  `hindernis_bei`, nicht darin. Das ist ihr ganzer Zweck: sie hält dort, wo der SENSOR frei
  sagt. Glas löst keine Tiefenkamera und kein Hindernisgitter; am 07.09.2026 fuhr der
  Explorer am echten Spot dicht an eine Glasfront. Wer es weiss, ist der Mensch, also trägt
  er es im Raumeditor ein. Zonen haben **keine Höhe** (die Gefahr ist der Ort, nicht das
  Volumen), halten nur beim HINEINfahren (wer drinsteht, muss herauskommen) und gelten in
  beiden Sims wie eine Wand — nur heisst das Hindernis „Sperrzone <name>", damit im
  Protokoll steht, warum. Der Sicherheitsabstand ist `ZONE_RAND_M` zusätzlich zum
  Roboterradius: am echten Gerät kommt die Pose aus der GraphNav-Verortung, und die driftet.
- **Der rekonstruierte Raum kennt seine Karte (`[karte]`, Fassung 5).** `ausrichten()` dreht
  ihn und schiebt die Hülle nach (0, 0), `rekonstruiere` zieht den tiefsten Boden auf z = 0
  — bis zum 07.09.2026 wurde diese Beziehung weggeworfen. Ohne sie weiss ein Lauf am echten
  Roboter nicht, WO IM RAUM er steht, und jede Sperrzone wäre geraten. `welt/raum.py::
  aus_karte`/`nach_karte` rechnen um, `spot.map_pose()` liefert `seed_tform_body` aus
  GraphNav (leerer `waypoint_id` heisst NICHT verortet und gibt `None` — eine Ursprungspose
  wäre eine erfundene Position). Geprüft gegen die echte Katakomben-Karte: ein Tag des
  Raums landet über `nach_karte` auf 5 cm genau auf seiner Ankerlage in der Karte.
- **Das Hindernisgitter ist eine BODENkarte — Überhänge stehen nicht darin.**
  `obstacle_distance` ist flach; eine Tischplatte in 75 cm Höhe kommt darin nicht vor,
  und unter einer Tischreihe steht für jeden Planer freie Fläche mit unerkundetem Raum
  dahinter. Genau dort ist der Explorer aus matura-spot am 07.09.2026 hineingefahren und
  musste mit dem Not-Aus geholt werden. Die Tiefenkameras SEHEN die Unterseite der Platte;
  `backends/real/tiefe.py` rechnet sie über Intrinsik und Extrinsik der Aufnahme in den
  Körperrahmen, richtet Roll und Nick heraus (das Höhenband hängt an der Schwerkraft, nicht
  am Rücken) und meldet, was zwischen 0.05 und 0.70 m über der Körpermitte im
  Vorwärtskorridor hängt. **Geprüft an einer echten Aufnahme**, nicht an einer Attrappe
  (`tests/daten/tiefe_real_20260812/`, Beobachtungsfahrt 12.08.2026): der Boden landet bei
  −0.51 m, also auf der gemessenen Standhöhe — ein Vorzeichenfehler oder eine verdrehte
  Achse fiele dort sofort auf; ein freier Gang lässt das Band leer; eine Tischreihe
  erscheint 0.72 m voraus. Über die ganze Fahrt (1181 Takte): 341 Takte mit Überhang im
  Korridor, davon 71 näher als ein Meter. **Der eigene Rumpf zählt nie mit** (dieselbe
  Blindzone-Ellipse wie beim Tiefengitter) — die Kameras sehen den eigenen Rücken, und wer
  den mitzählt, meldet dauernd Überhang. **Glas sieht auch das nicht:** die Tiefenkameras
  schauen hindurch wie das Gitter, das bleibt eine physikalische Lücke.
- **`ObstacleGrid.free_distance` übergeht Unbekanntes nur im Körperschatten (bis
  `FREI_AB_M`), Bekanntes nie.** Dicht am Körper sieht Spot nichts — die Frontkameras
  treffen den Boden erst 0.9 m vor der Mitte; ein Strahl, der deshalb 0.0 meldete, wäre
  wertlos, und bis zum 06.09.2026 sprang die freie Strecke von Zyklus zu Zyklus zwischen
  1.8 und 0.0. Aber eine BEKANNTE Wand 0.4 m vor der Nase (nach einer Drehung auf der
  Stelle) zählt: sie zu überspringen hiess hineinlaufen. Weiter draussen gilt Unbekanntes
  als zu, wie in `is_free`.
- **Der Kreis des 2D-Sims (`welt/kollision.py::ROBOTER_RADIUS_M`) ist eine Gitterzelle
  KLEINER als der Vorgabe-Rand von `ObstacleGrid.is_free`.** Was das Gitter frei nennt,
  muss im Sim begehbar sein; mit 0.35 m blieb ein Programm, das der freien Strecke
  folgte, an der Türkante hängen (06.09.2026). Die Zelle Luft braucht es, weil das Gitter
  Abstände nur je Zellmitte kennt. `tests/test_welt_kollision.py` hält die Kopplung fest.
- **Die Welt wird je `MAX_SCHRITT_M` Weg und je Abfrage geprüft, nie je Integrationsschritt.**
  `SimBackend._fortschreiben` integriert in 5-ms-Schritten (fürs Zielprofil) und ruft
  `_welt_pruefen` erst, wenn der Weg seit der letzten Prüfung 0.1 m erreicht, und am Ende
  jeder Abfrage — eine Pose sieht niemand, bevor sie geprüft war. Auf den korrigierten
  Katakomben kostete eine Prüfung 2–3 ms (61 Wände, rund 280 Klippenstrecken des Geländes;
  in MuJoCo Puppe setzen, `mj_forward`, Kontakte lesen) und lief 200-mal je Sekunde: der Sim
  fiel hinter die Echtzeit, `walk` brauchte 50–100 ms statt 9–12, der Fahrmodus „hing"
  (07.09.2026). Die Zusicherung „kein Tunneln" hängt an der Strecke, nicht am Takt; beide
  Backends haben einen Test, der die Prüfungen zählt.
- **`welt/` bleibt Standardbibliothek — auch `bearbeitung.py`.** Das ist der Grund, warum
  die GUI es importieren darf (`tests/test_welt_raum.py`); numpy nur in `wahrnehmung.py`.
- **Der Raumeditor arbeitet auf unveränderlichen Räumen; Undo ist eine Liste von
  Schnappschüssen, kein Kommando-Muster.** Griffe, Blender-Tasten und Zahlenfelder rufen
  dieselben Funktionen aus `welt/bearbeitung.py`; die Steuerung
  (`gui/raumeditor/steuerung.py`) kennt keine Pixel und kein Qt — jeder Bedienfall ist ein
  Test ohne Fenster.
- **Drehung nach einem Prinzip:** ein Punkt wird in den Rahmen des Blocks gedreht
  (`Block.lokal`), danach rechnet alles achsparallel — Kollision, Gitter, 3D-Welt. Eine
  zweite Formulierung fiele erst auf, wenn ein Block in 2D trifft und in 3D nicht.
- **Jeder virtuelle Start speichert den Raum vorher, wenn nötig, und lehnt einen Start im
  Hindernis ab — nicht nur der Knopf im Raumeditor.** `SPOTLAB_RAUM` ist ein Name; ein Lauf
  in einem Raum, der so nicht auf der Platte liegt, wäre nicht nachspielbar. Die Regel steht
  an EINER Stelle, `RaumeditorView.bereit_fuer_lauf()`, und `app.py::_umgebung_fuer_lauf`
  ruft sie für den Start aus „Code" — den einzigen Weg mit virtuellem Backend; „Projekte"
  startet Trockenlauf oder Roboter, ohne Raum: ein ungespeicherter Raum verweigert den
  Start mit `SpotlabError` (der Editor meldet ihn), statt still ohne Raum zu fahren. Bis zum
  06.09.2026 ging der Start aus „Code" am Knopf vorbei — die rekonstruierten Katakomben waren
  namenlos, `SPOTLAB_RAUM` ging leer mit, MuJoCo fuhr auf leerem Boden, und das
  Übungsfenster zeigte trotzdem die Wände, weil es aus der Ansicht vorbelegt war. Deshalb
  leert `Uebungsfenster.setze_raum_name(None)` die Zeichnung und sagt es: das
  `verbunden`-Ereignis ist die einzige Wahrheit über den Raum des Laufs.
- **PyOpenGL nur in `gui/raumeditor/sicht3d.py`, erst in `initializeGL` importiert.** Ohne
  das Paket oder ohne OpenGL-3.3-Kontext zeigt die Sicht eine Tafel und der Umschalter bleibt
  grau; ein Import auf Modulebene liesse die ganze GUI ohne PyOpenGL sterben
  (`tests/test_gui_raumeditor_sicht3d.py`). Und `QOpenGLContext.create()` ohne
  `QGuiApplication` ist kein Fehler, sondern eine Zugriffsverletzung — `gl_verfuegbar()` prüft
  die Anwendung zuerst. Uniforms gehen über PyOpenGL, nicht über
  `QOpenGLShaderProgram.setUniformValue`: PySide6 wählt für `(location, 0.0)` die
  int-Überladung, und `glUniform1i` auf ein float-Uniform ist GL_INVALID_OPERATION.
- **Protobufs (`bosdyn.api`) nur unter `maps/` und `backends/`.** Die Rekonstruktion
  (`maps/rekonstruktion.py`) liefert der GUI `Raum`, Punkte und Bericht; das Pauspapier ist
  eine Standardbibliotheks-Datei (`welt/pauspapier.py`), damit die GUI sie ohne numpy liest.
  Gemessen an der Katakomben-Karte (06.09.2026): die **z-Achse** des Fiducial-Rahmens zeigt
  aus der Tag-Fläche zu den Beobachtern — sie ist die Blickrichtung; der Boden gilt **je
  Schnappschuss** (Niveauunterschiede), nicht für die ganze Karte; nach jeder RANSAC-Linie
  fallen die Nachbarreihen (3 × Inlier-Abstand) weg, sonst wird jede Zellreihe einer dicken
  Wand eine eigene „Wand". **Die Sichtprüfung ist der eigentliche Filter:** eine Zelle, die
  von mehr Schnappschüssen durchquert als getroffen wurde, ist frei — Tiefen-Artefakte liegen
  auf dem Strahl vor der Wand, und die Strahlen zu den Punkten dahinter entlarven sie. Ohne
  sie bestanden die Katakomben aus 261 Stücken voller Strahlen im Ganginneren, mit ihr aus 61,
  die Gänge sauber umrandet (Bilder vom 06.09.2026). Ein Schichten-Filter („eine Wand füllt
  das Höhenband") war der falsche Weg: er zerhackt Wände, die eine Kamera nur teilweise sieht.
- **Ein Hindernis ist ein Höhensprung über `MAX_STUFE_M` (0.25 m).** Dieselbe Zahl in
  `welt/raum.py` und `spotsim/local_grid.py`, geprüft in `tests/test_backend_mujoco.py`;
  Kollision (Körperband `KOERPER_BAND_M`, Klippen), das 2D-Gitter und das Tiefengitter der
  Puppe formulieren nur sie. Im Tiefengitter ist belegt, was vom Boden unter dem Roboter
  nicht über Sprünge bis `MAX_STUFE_M` erreichbar ist (Flutfüllung über gesehene Zellen);
  nur Strahlen in Bodennähe räumen frei, der Boden hinter einer Klippe bleibt UNBEKANNT.
- **Höhe nach einem Prinzip:** `welt/hoehe.py::boden_bei(raum, x, y, z_nahe)` ist die
  einzige Antwort auf „wie hoch ist der Boden hier" — ohne `z_nahe` der höchste Boden, mit
  `z_nahe` der höchste erreichbare, sonst der nächste. Der Grundboden liegt überall bei 0,
  Böden liegen darauf (der tiefste Boden eines rekonstruierten Raums IST die 0).
  `kaesten_fuer` ist die einzige Zerlegung eines Bodens in Kästen — MuJoCo-Welt und
  3D-Sicht bekommen dieselben. **Eine Nick-Konvention:** Drehung um y nach der
  Rechte-Hand-Regel, Nase hoch ist NEGATIV — so liest `rpy_aus` den echten Spot, so
  rechnet MuJoCo, so liefern `nick_grad` und `kaesten_fuer`.
- **Die Puppe spielt auf der Treppe den ebenen Gang** und sagt es (`treppengang:
  "nicht gemessen"` im `verbunden`-Ereignis und im Bericht). Ein Treppengang kommt aus
  B6 der Messfahrt, nie aus einer erfundenen Kurve. Berührungen mit `boden_`, `stufe_`,
  `rampe_` sind kein Anstoss — die Füsse stecken beim ebenen Gang in den Stufen.
- **Auf einer Treppe zeigt die Nase bergauf: vorwärts hoch, rückwärts runter.** Der Sim
  verweigert den Rest (`treppe_verweigert`, einmal je Flanke, Rückmeldung sagt wie herum),
  bis Abnahmepunkt A25 etwas anderes ergibt. Klippen halten wie Wände („Kante").
- **`treppen` in `[limits]` gilt an einer Stelle:** `mobility.mit_grenze` setzt daraus
  `stairs_mode` für alle drei Wege, der Sim liest denselben Wert (bei „aus" sind Rampen und
  Treppen Klippen).
- **Die Körperantwort auf `move()` ist gemessen, aber nur bei 1 m und 90°**
  (`kalibrierung/antwort.py`, kommandierte Läufe vom 02.09.2026). Andere Ziele fahren
  dasselbe Trapez und zählen in `bericht()` als ausserhalb der Messung. Kombinierte
  Bewegung wurde nie gemessen. Der Deckel kommt aus `vel_limit` im Kommando — demselben
  Feld, das der echte Roboter liest.
- **Der Grund ist das Gelände, wo es eines gibt, sonst 0 — und nur `boden_bei` entscheidet
  das.** Kein Modul fragt `raum.gelaende` nach der Höhe an einem Punkt, ausser über
  `welt/hoehe.py` (die Sichten holen sich das Raster nur für ihr Bild). Das Gelände wird
  **nie von Hand gesetzt**: es kommt aus `maps/gelaende_bau.py`, aus Wänden, gelaufenem
  Weg und Pauspapier; wer es anders will, zieht Wände nach und lässt den Korrigierer neu
  laufen. **PAUS2 trägt den Weg** mit Bodenhöhe im Raumrahmen — Stütze des Geländes und
  das Signal „der Roboter lief hindurch"; PAUS1 bleibt lesbar. **Farben mischt nur
  `theme.mische`.** Und im Geländebau sperren Pauspapier-Punkte nur den Rand: eingeschlossene
  Knoten werden Boden, gesperrte Cluster bekommen die Nachbarhöhe kopiert (nicht Membran —
  eine Wand leitete sonst Höhe an sich entlang), Wegknoten mitteln sich im Umkreis von 1 m
  (zwei Fahrten mit 0.7 m Drift). Geländeklippen unter einem Boden zählen nicht. **Das
  2D-Gitter rechnet nur mit dem, was bis `FENSTER_RAND_M` (1 m) um es liegt** — ein Gelände
  hat Hunderte Klippenstrecken über die ganze Karte, jede gegen 16384 Zellen kostete 0.57 s
  je `obstacles()`, jetzt 0.03 s; für eine Randzelle zählt ein Hindernis weiter draussen nur
  als Abstand über einem Meter, mehr als jeder Rand von `is_free`. In MuJoCo liegen Knoten
  ohne Boden 2 cm UNTER der Bodenebene (Puppe `GELAENDE_SENKE_M`), sonst flimmern zwei
  Flächen auf derselben Höhe. **Was je gezeichnetem Punkt gefragt wird, muss O(1) sein:**
  `gelaende.umriss` wird einmal beim Bau gerechnet (`huelle` fragt ihn, der Raumplot fragt
  `huelle` je Punkt — 56 s je Bild, „Python reagiert nicht"), und das Pauspapier ist in
  `Sicht2D` ein einmal gerastertes Bild (`raumzeichnung.pauspapier_bild`), keine 190 000
  einzelnen `drawPoint`. Dieselbe Regel im Übungsfenster: `RaumPlot` merkt sich `huelle(raum)`
  in `setze_raum`; `_massstab` rechnete sie je `meter_zu_schirm` neu — 950-mal je Bild,
  172 ms auf den Katakomben, bei zehn Zuständen je Sekunde stand die GUI (07.09.2026).
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
- **Wer im Test `deleteLater()` auslöst, arbeitet es auch ab** —
  `QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)`. Sonst liegt die
  Zerstörung in der Warteschlange, bis ein späterer Test eine verschachtelte
  Ereignisschleife laufen lässt, und stürzt dort ab: der Bericht zeigt dann auf eine
  fremde Datei, die nichts damit zu tun hat. Genau so ist ein `Fatal Python error:
  Aborted` in `test_gui_tree.py` entstanden, ausgelöst von einem Reiter-Schliessen in
  `test_gui_editorview.py`.
- **`QObject.disconnect()` ohne Argument ist verboten.** Es kappt ALLE Signale des
  Objekts, auch `finished` und `destroyed`, an denen Qt seine eigene Aufräumarbeit hängt.
  Immer die eine Verbindung nennen: `arbeiter.fertig.disconnect(self._jedi_fertig)`.
- Was nicht Widget ist, gehört in ein Qt-freies Modul — `record/tail.py`,
  `workshop/control.py`, `gui/theme.py`, `gui/watcher.py::RunScanner`.
- **Jeder Aufruf, der auf einen Prozess wartet, bekommt eine Zeitgrenze** —
  `TEST_TIMEOUT_S` aus `tests/tests_zeitgrenzen.py` für `subprocess.run`/`wait`,
  `zeile_mit_frist()` für `readline()`, das sich nicht unterbrechen lässt. Ohne sie
  HÄNGT ein Lauf, statt zu scheitern: ein kaputter Zwischenstand hat einen Testlauf
  drei Stunden laufen lassen. `pytest-timeout` (300 s je Test) ist das Netz darunter,
  nicht der Ersatz — es sagt nur, DASS etwas hing, nicht wo.
- **Ein Test, der absichtlich `stop()` scheitern lässt, hält den Thread trotzdem
  an.** Die Attrappe merkt sich die getroffene Instanz, das Teardown ruft das echte
  `stop()` darauf (`tests/test_kette.py::klemmender_abtaster`). Ohne das lief der
  Abtaster als Daemon bis zum Prozessende weiter — mit 10 Hz gegen ein `tmp_path`,
  das pytest längst gelöscht hatte. Die Dauerlast hat einen ganz anderen Test
  gekippt, in einem von drei vollständigen Läufen. **Ein Leck fällt nie dort auf,
  wo es entsteht.**
- **Ein Test, der von der Maschinenlast abhängt, prüft die falsche Sache.** Ein
  20-ms-Takt rutscht unter Windows regelmässig auf 31 ms (Zeitgeberauflösung 15.6 ms).
  Nicht die Abwesenheit von Jitter behaupten, sondern die ART des Fehlers prüfen, gegen
  den der Test steht — siehe `test_die_messfahrt_meldet_keine_falschen_luecken`.
- **Eine Mitschreiber-Attrappe beweist nicht, dass die Ereignisart erlaubt ist.**
  `angestossen` fehlte bis zum 06.09.2026 in `record/events.py::ARTEN`; die Sim-Tests mit
  Attrappe waren grün, und jeder 2D-Lauf starb beim ersten Wandkontakt mitten in
  `robot_state()`. Wo ein Backend ein neues Ereignis schreibt, prüft ein Test es gegen
  den echten `RunRecorder`.
- **Der Raumeditor wird über `Steuerung` getestet** (Meter, Tastennamen, kein Fenster);
  die Qt-Tests prüfen nur die Haut: Klick → Auswahl, Feld → Modell, Speichern → Datei.

## Linter und CI

- `ruff check .` muss grün sein; die CI führt es **vor** den Tests aus. Es hat einen
  `NameError` in einem Abbaupfad gefunden, den 844 Tests nicht sahen.
- Die Regelauswahl in `pyproject.toml` ist bewusst schmal und bleibt es. **Kein `BLE`**
  — die Abbaupfade fangen absichtlich alles, damit `close()` durchläuft. **Kein
  `ruff format`** — es würde die Kommentarspalten zerlegen, an denen hier Begründungen
  hängen.
- **`# noqa: E402` wird einzeln gesetzt, nie als `per-file-ignores`.** Eine
  Pauschalfreigabe deckt auch die Datei, in der jemand aus Versehen mitten im Code
  importiert.
- CI läuft auf **`windows-latest`**, nicht Linux. Die Fehler dieses Projekts —
  `CreateProcess` mit nacktem Editornamen, cp1252 statt UTF-8, CRLF beim Speichern —
  gibt es nur unter Windows. Geprüft werden Python 3.11 **und** 3.13.
- Ein zweiter Auftrag installiert **nur `[dev]`** und prüft, dass ohne die Extras
  weder alles scheitert noch alles übersprungen wird. Lokal ist PySide6 immer da; ohne
  diesen Auftrag sieht niemand, ob `importorskip` wirklich greift.
- **Jede Abhängigkeit hat eine Obergrenze** (`pyproject.toml`), und die Fassungsnummer
  steht an genau EINER Stelle: `src/spotlab/__init__.py`.

## Umsetzungsstand

**Stufe 14 (07.09.2026): Korrigierer und Gelände — alle drei Etappen gebaut**
— Raumformat v4: `Raum.gelaende` (`welt/gelaende.py`, Höhenraster mit `None` für „kein
Boden", bilinear abgetastet, Klippen an Knotensprüngen über `MAX_STUFE_M`, Plateaus als
Ebenen, Binärdatei `.gelaende` neben der Raumdatei mit Verweis `[gelaende]`); der Grund in
`boden_bei` ist das Gelände, wo es eines gibt, sonst 0; `klippen_von` merkt sich Klippen je
Böden und Gelände; Pauspapier PAUS2 trägt den gelaufenen Weg mit Bodenhöhe, die
Rekonstruktion liefert ihn (`Ergebnis.weg`), der Tab speichert und lädt ihn. Sichten: 2D als
Relief-Bild mit Höhenlinien alle 0.25 m (einmal je Raum gerendert, `theme.mische`), Markierung,
Kandidaten und offene Ränder in `Sicht2D`; 3D als Dreiecksnetz je Höhenband; MuJoCo als
`hfield` (Puppe Fassung 5, Zeilenrichtung per Strahl geprüft); im Editor eine Listenzeile,
nur lesend, verschieben/heben/löschen. Etappe 3: `welt/korrektur.py` (Kandidaten Lücke,
Ecke, Anschluss, kreuzende Wand; Vorschlag aus Weg und Pauspapier; `wende_an`,
`uebernimm_gelaende` mit Treppen auf dem Gelände), `maps/gelaende_bau.py` (Sperren, Fluten,
offene Ränder, Löcher und Taschen, Membran mit gemittelten Wegstützen, Flächenglättung,
Cluster-Kopien), Dialog „Korrigieren…" (nicht modal, Tabelle mit Vorschlag und Grund, Gelände
im Arbeiter, ein Verlaufsschritt), Katakomben: 73 Kandidaten (70 Wand, 1 Durchgang, 2 unklar),
Gelände ~6900 Knoten, Weg ohne Anstoss abgefahren (`tests/test_katakomben_korrektur.py`).
Abnahme A28. Spec `docs/superpowers/specs/2026-09-07-korrigierer-gelaende-design.md`
(§ 14 Nachträge), Pläne `docs/superpowers/plans/2026-09-07-gelaende-*.md`. Danach
(07.09.2026): die Live-Animation von GPT Astra eingeräumt (`animation.py`, `gui/liveplot.py`,
30-Hz-Zimmeransicht ohne Schatten), und die **Zimmeransicht hat Kameramodi**: „Verfolgen"
(schräg hinter Spot, `spotsim.puppe.zimmerkamera(modus, zoom)`) und Mausrad-Zoom im
Übungsfenster; der Wunsch geht als `kamera.json` ins Lauf-Verzeichnis (`record/kamera.py`,
Standardbibliothek), der Ansichtsthread liest ihn je Bild über die Änderungszeit — die GUI
hält weiter keinen Draht in den Lauf, die Platte ist der einzige Kanal, in beide Richtungen.
Dazu der **Fahrmodus**: „🎮 Fahren" im Raumeditor startet `Beispiele/fahren.py` aus dem
Arbeitsordner (Vorlage `workshop/beispiele/fahren.py`, Kern `workshop/fahren.py::fahre`) über
denselben einen Startweg wie die offene Datei (`editor/view.py::starte_skript`, virtuelles
Backend erzwungen, gleiche Raum- und Startregeln); das Übungsfenster schreibt die Tasten
W A S D Q E als `fahrt.json` (`record/fahrt.py`, Tastenbelegung ohne Qt prüfbar), `fahren.py`
liest mit 20 Hz und fährt mit `walk(stop=False)`; **ein Befehl älter als 0.5 s heisst Stopp**
(Totmannschalter). Beide Dateien schreibt `record/atomar.py`: `.tmp`, dann `os.replace` —
das scheitert unter Windows mit `PermissionError`, solange der Leser die Datei gerade offen
hat (20-mal je Sekunde); der Schreiber wiederholt kurz und gibt dann auf, ohne zu werfen,
denn der nächste Takt schreibt ohnehin, und ein Fahrbefehl darf nie die GUI oder den Lauf
anhalten. **Ein Programm, das die GUI startet, muss in einem Projekt des
Arbeitsordners liegen, nie im Paket:** Läufe landen neben dem Skript, und der Watcher sucht
nur unter `<Arbeitsordner>/<Projekt>/runs/` — die erste Fassung lag im Paket, die Läufe
lagen unter `src/spotlab/workshop/runs/`, niemand fand sie, und das Übungsfenster erfuhr das
Verzeichnis nie (07.09.2026). Im Fahrmodus **greift das Übungsfenster die Tastatur**
(`grabKeyboard`, bis „Stopp" oder Schliessen): so kommen die Tasten an, egal welches Widget
den Fokus hat, und die Leertaste drückt nicht den fokussierten Stopp-Knopf. Ein Test fährt
die ganze Kette — Knopf, Prozess, Watcher, Fenster, Taste, Aufzeichnung. **Der Tab
„Fahren"** (`gui/views/fahren.py`) fährt damit den ECHTEN Spot: dasselbe Programm aus
Beispiele, derselbe eine Startweg (`app.py::_starte_fahrt(FAHREN_BACKEND)`, Backend „real"
erzwungen, nie die Wahl im Editor geerbt), die Tasten über `gui/tastenfahrt.py` — die eine
Formulierung für Übungsfenster und Tab (Tastenmenge, 200-ms-Takt, Tempostufen
`record/fahrt.py::STUFEN` langsam 0.5 / normal 1 / schnell 2 als Faktor auf alle drei
Achsen, Tasten 1 2 3; im Tab ist langsam vorausgewählt, im Übungsfenster normal; ein
Wechsel schreibt sofort, sonst führe eine gehaltene Taste bis zum nächsten Takt weiter).
Der Tab hält die Tastatur nur, solange er sichtbar ist und der Lauf lebt; **Reiterwechsel
und Fokusverlust der App lassen alle Tasten los und schreiben Stillstand** — Qt schickt bei
Alt-Tab kein KeyRelease, der Takt frischte den letzten Befehl sonst blind auf. Stopp
delegiert an `LiveView.stoppe()`, der NOT-AUS steht im Kopf. Stirbt der Prozess vor dem
ersten Lauf-Verzeichnis (Roboter nicht erreichbar), setzt `laeuft_geaendert` die Erwartung
zurück, sonst gälte ein späterer fremder Lauf als Fahrt. Die Kette läuft im Test mit dem
Trockenlauf statt des Roboters (`FAHREN_BACKEND` getauscht); am Gerät: A29.

**Stufe 13 (06.09.2026): Höhe, Rampen und Treppen — alle vier Etappen gebaut** — Raumformat
v3 (`Boden` als Podest, Rampe oder Treppe; `z` an Wand, Block, Tag), `welt/hoehe.py`
(Boden unter einem Punkt, Neigung, Ebenen, Klippen, Treppenlage und -regel, Kästen),
Körperband und Klippen in Kollision und Gitter, der 2D-Sim mit `z` und Nick (vorhandene
Felder, jetzt mit echten Werten), Treppenmodus `treppen` in Konfiguration und
Mobility-Parametern, Puppe Fassung 4 (Nick, Bodenhöhe, Sprungregel im Tiefengitter),
MuJoCo-Welt mit Stufen, Rampen und Podesten aus `kaesten_fuer`, Video mit Höhe und Nick.
Spec `docs/superpowers/specs/2026-09-06-hoehe-treppen-design.md`, Pläne
`docs/superpowers/plans/2026-09-06-hoehe-*.md`. Etappe 2: Werkzeug Boden, Ebenenwahl
der 2D-Sicht (andere Ebenen blass, `Palette.blass`), `G` dann `Z` hebt, Zahlenfelder `z`,
`anstieg`, `stufen`, Böden und Klippen in 2D, dieselben Kästen wie MuJoCo in 3D, Höhe und
Neigung im Übungsfenster. Etappe 3: das Höhenprofil kommt aus den WEGPUNKTEN (Körper
0.54 m über dem Boden) — das 5. Perzentil der Wolke bliebe auf einer Treppe unten; Treppen
aus den Treppenkanten des SDK (Kette in Laufreihenfolge, Fuss und Kopf an den Enden, Stufen
aus Anstieg / 0.17 m, Breite aus den Bandpunkten quer zur Achse, dieselbe Treppe hoch und
runter ist EINE), Rampen und Podeste aus dem Profil (Douglas-Peucker 10 cm, je gerader
Teilstrecke ein Rechteck so breit wie der Gang, kurze Stücke gehen im Nachbarn auf — eine
Lücke im Schlauch wäre eine Klippe); der tiefste Boden ist die 0, Wände und Tags tragen ihre
Ebene. Katakomben: 1 Treppe (1.78 m, 10 Stufen), 10 Rampen, grösstes Gefälle 5.3°, 6 s.
Etappe 4: `spot.stairs()` (`Staircase` mit `direction`, `steps`, `rise_m`, `axis_bearing`,
`Capability.STAIRS`; im Sim aus dem Raum, am Roboter aus `staircase_properties`), Vorlage
`treppe`, Beispiel `treppe_steigen.py` (in 2D und 3D geprüft, falsch herum wird verweigert),
Abnahme A25–A27, B6 im Messfahrt-Ablauf.

**Stufe 12 (06.09.2026): Raumeditor, Etappe 1 von 3** — der Tab „Übungsraum" ist der
Tab „Raumeditor": Wände (Linien mit Dicke und Höhe je Raum), drehbare Blöcke mit Höhe,
Tags mit Hängehöhe; Griffe und Blender-Tasten, Liste, Zahlenfelder, Hinweise, eigene Räume
unter `raeume/`. Raumformat v2 (`welt/raum.py`, alte Schreibweise wird gelesen), Drehung in
Kollision, Gitter und Puppe (`PUPPE_FASSUNG = 3`). Etappe 2: die 3D-Sicht (OpenGL 3.3 über
`QOpenGLWidget` + PyOpenGL, Orbit-Kamera, Farb-ID-Auswahl, Rückfall auf 2D; Geometrie und
Kamera GL-frei in `geometrie3d.py`). Etappe 3: Rekonstruktion aus GraphNav-Karten
(`maps/rekonstruktion.py`, Dialog mit Arbeiter-Thread, Pauspapier in beiden Sichten;
Katakomben-Karte: 31 Tags, 261 Wandstücke, 2.6 s) — Spec
`docs/superpowers/specs/2026-09-06-raumeditor-design.md`. Alle drei Etappen gebaut.

**Stufe 11 (06.09.2026): Übungsraum 3D** — `backend="mujoco"`, der 2D-Sim mit dem
Menagerie-Körper aus matura-spot (Weg A, Wiedergabe statt Regelung; Spec
`docs/superpowers/specs/2026-09-06-uebungsraum-3d-design.md`). Gates: G10 Gitterformat
(matura-spot, gegen eine echte Aufzeichnung — fand zwei Formatfehler), G11 Wiedergabe
gegen die Messung (`tests/test_wiedergabe.py`). Die Gitterachsen sind seit dem
06.09.2026 auch im Sim weltfest (matura-spot, LocalGrid v3). In jedem Arbeitsordner liegt
das Projekt `Beispiele` (`workshop/beispiele/`); `durchgang_finden.py` fährt laufend
(`walk(…, stop=False)`), den Kurs aus `free_distance` alle 5°, durch Lücken in der Mitte —
geprüft in 2D und 3D (`tests/test_workshop_beispiele.py`). Videos: `spotlab film <lauf>`.

Fundament (1+2), GUI (3), GraphNav (4), der eingebaute Editor (5), die Anbindung fremder
Projekte samt MCP-Server (6), die Kalibrier-Infrastruktur (7) und der Beobachter-Modus (8)
sind vollständig. Der Beobachter (`beobachtung/`) schreibt leaselos mit, während ein
Mensch mit dem Tablet fährt — Zustand reich bei 10 Hz, 50 Hz im Messfenster, dazu ein
Bildmitschnitt aller fünf Kameras (Tiefe auf Wunsch) nach `kamera/`. Das Drehbuch dazu
liegt in `matura-spot/scripts/beobachten_real.py`, der Ablauf für den Messtag in
`matura-spot/notes/MESSFAHRT_ABLAUF.md`. Noch nicht gebaut: der Vergleich gegen den Sim
über die neue x-Achse (erreichtes statt kommandiertes Tempo); er berührt nur
`matura-spot/scripts/vergleich_real_sim.py`. **Aufgehoben am 12.08.2026:** „ein Simulator in spotlab" stand hier als bewusstes
Nicht-Ziel. Der Autor hat das gekippt, wie zuvor beim Editor in Stufe 5. Gebaut ist
jetzt `backends/sim.py` — eine Interpolation der am 12.08.2026 gemessenen Gangarten,
**keine Physik**. MuJoCo bleibt in `matura-spot`; die geplante Kopplung als optionales
Extra `spotlab[sim]` bleibt der Weg für alles, was neue Bedingungen braucht (Treppe,
Stoss, Traglast). Die Matura-Experimente gehören weiterhin dorthin, nicht hierher.

Offen
und bewusst nicht gebaut: NN-Anbindung, Mehrbenutzer-Dienst, Arm und Docking.
Im Editor: Debugger mit Haltepunkten, git-Integration, Erweiterungen, projektweite Suche.
In der Anbindung: MCP über Netz, Mehrbenutzer, Qt-Code aus fremden Projekten, eine
Diagrammbibliothek jenseits der fünf Panel-Arten. In der Kalibrierung: **ein Simulator in
spotlab** (MuJoCo bleibt in `matura-spot`), automatische Parameteranpassung, die Nutzung
der lizenzpflichtigen 333-Hz-APIs.

Specs unter `docs/superpowers/specs/`. Anleitungen: `docs/ANBINDUNG.md` (fremde Projekte
und Messfahrt).
