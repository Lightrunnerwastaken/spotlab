# Abnahme am echten Spot

Was die Testsuite **nicht** beweisen kann. Alle Tests laufen gegen Attrappen; sie zeigen,
dass spotlab das Richtige *sendet* — nicht, dass der Roboter es so auslegt wie erwartet.

Format wie `matura-spot/notes/REALISMUS_GATES.md`: jeder Punkt trägt eine Prozedur, eine
Erwartung und ein Ergebnisfeld. Ergebnisse mit Datum, Software-Stand des Roboters und
spotlab-Version eintragen.

| Roboter | Software-Stand | spotlab | Datum | Abgenommen von |
|---|---|---|---|---|
| _(eintragen)_ | | 0.1.0 | | |

---

## A1 — Not-Aus-Koexistenz · **SPERRPUNKT**

**Bis dieser Punkt abgenommen ist, findet kein Schülerbetrieb statt.**

**Befund vorab (im SDK-Quelltext bestätigt, nicht vermutet):**
`EstopEndpoint.force_simple_setup()` trägt den Docstring *„Replaces the existing estop
configuration with a single-endpoint configuration."* und ruft `set_config` mit einer
Konfiguration, die nur den eigenen Endpunkt enthält. Der Endpunkt des Tablets fiele damit
aus der Konfiguration — der physische Not-Aus in der Hand der Aufsichtsperson wäre
wirkungslos, solange ein Schülerskript läuft.

**Gegenmassnahme, bereits umgesetzt:** `backends/real/estop.py::register_coexisting` liest
die aktive Konfiguration, übernimmt alle bestehenden Endpunkte und hängt den eigenen an.
Zwölf Tests decken das ab (`tests/test_real_estop.py`), darunter der Fall eines stale
eigenen Endpunkts nach einem Absturz.

**Zweiter Befund, nachträglich gefunden und behoben:** der Endpunktname `spotlab` ist eine
feste Konstante, und bis dahin wurde *jeder* Endpunkt dieses Namens entfernt — auch der
einer **lebenden zweiten spotlab-Sitzung**. Ein versehentlicher Doppelstart oder ein
zweiter Schüler hätte dem ersten Lauf den Not-Aus aus der Konfiguration geworfen.
Seither prüft `register_coexisting` über `time_since_valid_response`, ob sich der
gleichnamige Endpunkt noch meldet, und weist den zweiten Aufbau mit `EstopBusy` ab.
Ein instanzeigener Name wäre der naheliegende, aber falsche Fix gewesen: er zerstörte die
Selbstheilung nach einem Absturz, und ein abgestürzter Laptop hielte den Roboter dauerhaft
im CUT.

**Drittens:** scheitert nach der E-Stop-Registrierung ein weiterer Aufbauschritt (Lease
belegt, Strg-C), macht `connect()` den Aufbau jetzt rückgängig. Vorher blieben Endpunkt
und Keepalive-Thread verwaist zurück.

**Was am Gerät zu verifizieren bleibt:** dass der Roboter die erweiterte Konfiguration so
auslegt wie erwartet und der Tablet-Not-Aus danach weiterhin auslöst.

**Prozedur**
1. Tablet verbinden, Spot einschalten, Not-Aus am Tablet ist frei.
2. `spotlab doctor` — Stufe „Not-Aus" muss `frei` melden.
3. Ein Skript starten, das `power_on()` und `stand()` macht und dann 30 s wartet.
4. Während der Spot steht: **Not-Aus am Tablet auslösen.**
5. Beobachten.

**Erwartung** Der Spot schneidet die Motorleistung ab und setzt sich ab. Das Skript
bricht mit einer verständlichen Meldung ab.

**Gegenprobe** Vor Schritt 4 am Tablet prüfen, dass dort weiterhin ein aktiver
Not-Aus-Endpunkt angezeigt wird und nicht nur `spotlab`.

**Zusatz A1b — zwei spotlab-Sitzungen.** Von einem zweiten Laptop (oder in einem zweiten
Fenster) verbinden, während der erste Lauf läuft.

*Erwartung:* Der zweite Versuch bricht mit „Ein anderer spotlab-Lauf hält gerade den
Not-Aus dieses Roboters" ab. Der **erste** Lauf läuft unbeeinträchtigt weiter, und der
Not-Aus am Tablet löst danach immer noch aus (Schritt 4 wiederholen). Das ist der
entscheidende Teil: dass der abgewiesene Versuch nichts kaputt gemacht hat.

**Zusatz A1c — Selbstheilung nach Absturz.** Einen Lauf hart töten (Task-Manager), dann
sofort neu verbinden.

*Erwartung:* Der neue Lauf kommt durch — der zurückgelassene Endpunkt wird ersetzt, weil
er sich nicht mehr meldet. Kommt der neue Lauf NICHT durch, ist die Frischeprüfung zu
streng eingestellt und der Roboter wäre nach jedem Absturz blockiert. Notiere, wie lange
nach dem Töten der Neustart klappt.

**Ergebnis** _(offen)_

---

## A2 — Harter Prozessabbruch

**Prozedur** Skript starten, Spot steht. Prozess im Task-Manager beenden (nicht Ctrl-C).

**Erwartung** Innerhalb des E-Stop-Timeouts (5 s) schneidet der Roboter die Motorleistung
ab. Er bleibt nicht unkontrolliert stehen.

**Warum das der eigentliche Not-Aus ist** Er ist nicht programmiert, sondern die Folge
davon, dass das Keepalive aufhört. Man kann ihn nicht durch einen Fehler im Schülercode
umgehen.

**Ergebnis** _(offen)_

---

## A3 — Geordnetes Ende

**Prozedur** `spotlab run hallo_spot.py` vollständig durchlaufen lassen.

**Erwartung, in dieser Reihenfolge** Bewegung stoppt → Spot setzt sich kontrolliert hin →
Motoren aus → Lease frei (`spotlab lease` meldet `frei`) → `spotlab doctor` meldet
Not-Aus `frei` und kein zurückgelassener `spotlab`-Endpunkt.

Der letzte Teil ist seit S1.13 **automatisiert**: `spotlab doctor` hat eine eigene Stufe
„Not-Aus-Endpunkt" direkt hinter „Not-Aus". Sie muss `kein 'spotlab'-Endpunkt in der
Konfiguration` melden. Meldet sie „zurückgeblieben", ist dieser Punkt nicht bestanden —
auch wenn sich der Endpunkt beim nächsten Verbinden selbst ersetzt.

**Zusätzlich** Dasselbe mit Ctrl-C mitten im Lauf und mit einem Skript, das absichtlich
eine Ausnahme wirft. Beide Male muss der Abbau vollständig durchlaufen.

**Ctrl-C ist der wichtigere der beiden Fälle** (S1.6): der Abbau fing früher nur
`Exception`. Ein Ctrl-C im ersten Abbauschritt sprang aus `close()` heraus, Motoren
blieben an, und der Spot fiel beim Wegfallen der Keepalives aus dem STAND um, statt sich
hinzusetzen. Achte deshalb ausdrücklich darauf, **wie** er zu Boden kommt, nicht nur
darauf, dass er es tut.

**Ergebnis** _(offen)_

---

## A4 — Lease-Übernahme von einem zweiten Laptop

**Prozedur**
1. Laptop A startet ein Skript mit einer langen `walk()`-Phase.
2. Laptop B: `spotlab lease` — muss A als Halter mit Namen anzeigen.
3. Laptop B: `spotlab lease --take`, Rückfrage bejahen.

**Erwartung** Das Skript auf A bricht sauber ab mit „Kontrolle verloren — jemand anders
hat übernommen." Kein kryptischer `LeaseUseError`. Der Abbau auf A läuft vollständig
durch. Der Lauf auf A trägt in `lauf.json` das Ergebnis `lease_verloren`.

**Ergebnis** _(offen)_

---

## A5 — Zeitsynchronisierung

**Prozedur** Windows-Uhrzeit um mehrere Minuten verstellen, automatische Zeitsetzung aus.
`spotlab doctor`.

**Erwartung** Stufe „Zeitsync" schlägt fehl mit dem Rat, die Uhrzeit automatisch stellen
zu lassen. Die Kette bricht dort ab und prüft Lease und Akku nicht mehr.

**Ergebnis** _(offen)_

---

## A6 — `move()` hält, was es verspricht

**Prozedur** Auf freier Fläche Startposition markieren. `spot.move(forward=1.0)`.
Zurückgelegte Strecke messen. Fünf Wiederholungen. Danach `spot.move(turn=90)`, Drehwinkel
messen.

Dann drei Zusätze, die den Kern von `move()` prüfen — nicht nur das Ziel:

1. **Der Geschwindigkeitsdeckel gilt auch hier.** In `~/.spotlab/config.toml`
   `max_speed = 0.2` setzen, `spot.move(forward=2.0)` fahren, Zeit stoppen. Bei einer
   Zieltrajektorie wählt der Roboter sein Tempo SELBST — das Klemmen der Sollwerte wie
   bei `walk()` wirkt hier nicht, der Deckel muss als `vel_limit` mitgeschickt werden.
   Der Punkt prüft genau das.
2. **Die Zeitüberschreitung hält den Roboter an.** `spot.move(forward=3.0, timeout=2.0)`.
   Das Skript bricht mit einer Ausnahme ab — der Roboter muss im selben Moment stehen
   bleiben, nicht weiterlaufen. (`warte_auf` schickt keinen Stopp; das Kommando läuft
   stattdessen genau bei `timeout` ab.)
3. **Ein Fahrkommando kommt überhaupt an.** Wenn `walk()` oder `move()` sofort mit
   „Kommando abgelehnt" scheitert, ist `end_time_secs` wieder falsch berechnet: das SDK
   liest den Wert als Sekunden seit dem 1.1.1970, nicht als Dauer. Das war einmal so und
   hätte bedeutet, dass sich der Roboter kein einziges Mal bewegt.

**Erwartung** 1.0 m ± 10 cm; 90° ± 10°. `move()` kehrt erst zurück, wenn der Roboter
„angekommen" meldet, nicht nach einer geschätzten Zeit. Zusatz 1: die Fahrt dauert
mindestens 2 m / 0.2 m/s = 10 s. Zusatz 2: Stillstand innerhalb von etwa einer Sekunde
nach dem Abbruch.

**Notieren** Streuung über die fünf Läufe — das ist eine Vergleichsgrösse für die spätere
Sim-Kalibrierung. Ausserdem die gemessene Dauer aus Zusatz 1: sie sagt, ob der Deckel
wirklich greift oder ob der Roboter ihn nur ungefähr beachtet.

**Ergebnis** _(offen)_

---

## A7 — Kameras

**Prozedur** `spot.cameras()` aufrufen und die gemeldeten Kurznamen notieren. Von jeder
ein Bild aufnehmen und speichern.

**Erwartung** Fünf Kurznamen (frontleft, frontright, left, right, back). Jedes Bild hat
plausible Abmessungen und Intrinsics ≠ 0. Die Heckkamera sieht die eigenen Hinterbeine.

**Prüft zugleich Annahme A2 der Spec** — die Zuordnung Kurzname → echter Quellname ist
geraten und wird hier gegen die tatsächlich gemeldeten Quellen verifiziert. Weichen die
Namen ab, ist `api/perception.py::KURZNAMEN` anzupassen.

**Ergebnis** _(offen)_

---

## A8 — Aufzeichnung ist kalibriertauglich

**Prozedur** 30-s-Lauf mit `walk(vx=0.3, duration=20)`. Danach `runs/<id>/zustand.jsonl`
auswerten.

**Erwartung** Rund 300 Abtastungen, keine Lücke grösser als 0.5 s. Jede Abtastung trägt
Pose, Geschwindigkeit, 12 Gelenke und Fusskontakte. Die gemessene Geschwindigkeit ist
gegen die kommandierten 0.3 m/s auswertbar.

**Warum das zählt** Diese Datei ist die Grundlage der späteren Real→Sim-Kalibrierung
(AF 4 der Maturaarbeit). Taugt sie nicht, ist der Sim-Adapter später nicht validierbar.

**Ergebnis** _(offen)_

---

## A9 — Freundlicher Stopp aus der GUI

**Prozedur** Skript mit langer `walk()`-Phase starten, in der GUI *Stopp* drücken.

**Erwartung** Spot bremst, setzt sich kontrolliert hin, Motoren aus, Lease frei.
`lauf.json` trägt `abgebrochen`. Der Knopf „Reagiert nicht — hart beenden" darf **nicht**
erscheinen; tut er es, kommt der `KeyboardInterrupt` nicht durch die gRPC-Aufrufe durch,
und das gehört ins Tagebuch.

**Zusatz A9b — NOT-AUS mitten im Abbau.** Der Punkt, den A9 bisher nur zu prüfen
behauptete. Bis S1.7 hing das Lebenszeichen allein an `zustand.jsonl`; der Abtaster hört
beim Stopp als Erstes auf, während `close()` noch bis zu 20 s läuft. In genau diesem
Fenster hielt die GUI den Lauf für tot, und der NOT-AUS-Knopf traf niemanden — obwohl der
Spot noch unter Strom stand.

*Prozedur:* Skript mit langer `walk()`-Phase starten, *Stopp* drücken und **sofort
danach**, noch während sich der Spot hinsetzt, den NOT-AUS-Knopf drücken.

*Erwartung:* Der Knopf wirkt. Der Prozess stirbt, der Spot schneidet die Motorleistung ab
(er sackt zusammen — das ist die Bedeutung eines Not-Aus, kein Fehler). Es erscheint
**nicht** die Meldung „Der Lauf läuft nicht mehr". Erscheint sie doch, ist die Markierung
`abbau` im Lauf-Verzeichnis nicht angelegt worden.

*Und der umgekehrte Fall:* Lässt sich der Prozess nicht töten, muss die Meldung
„Das Programm liess sich NICHT beenden. Drücke sofort den physischen Not-Aus am Tablet."
kommen — und der harte Knopf **sichtbar bleiben**. Eine Entwarnung an dieser Stelle wäre
gefährlicher als gar keine Meldung.

**Ergebnis** _(offen)_

---

## A10 — NOT-AUS aus der GUI

**Vor diesem Punkt Freifläche und Aufsicht sicherstellen — der Spot fällt kontrolliert um.**

**Prozedur** Spot steht, NOT-AUS drücken.

**Erwartung** Motoren gehen sofort aus, Spot sackt zusammen. `lauf.json` bleibt auf `läuft`
stehen — der Prozess wurde getötet, `finish()` lief nie; das ist beabsichtigt und das
Erkennungsmerkmal eines harten Abbruchs. Der Roboter ist danach ohne Neustart wieder
verbindbar.

**Ergebnis** _(offen)_

---

## A11 — F5-Lauf aus VS Code

**Prozedur** GUI geöffnet lassen, in VS Code ein Skript mit F5 starten.

**Erwartung** Die GUI greift den Lauf innerhalb einer Sekunde auf, zeigt Telemetrie, und
**beide Stopp-Knöpfe wirken**.

**Warum das der Prüfstein ist** Fällt A11 durch, ist Grundsatzentscheidung H3 der
GUI-Spec falsch und die Oberfläche für den Unterrichtsalltag wertlos — denn F5 ist, was
die Schüler tatsächlich drücken.

**Zusatz A11b — zwei Läufe gleichzeitig.** Der Alltagsfall, nicht der konstruierte:
aus „Projekte" starten und dann, während es läuft, in VS Code F5 drücken.

*Erwartung:* Die Live-Ansicht bleibt beim **ersten** Lauf, und der NOT-AUS trifft
weiterhin ihn. Es erscheint eine Meldung, dass bereits ein Programm läuft. Wechselt die
Anzeige stattdessen zum zweiten Lauf, zeigt der NOT-AUS-Knopf auf den falschen Prozess —
und der erste hält womöglich gerade den Roboter.

*Danach:* Den ersten Lauf beenden. Die Anzeige muss dann von selbst auf den zweiten
umschalten, sofern der noch läuft.

*Notieren:* Ob die Ausgabe beider Läufe im selben Fenster erscheint. Das ist bekannt und
nicht gefährlich, aber verwirrend — falls es im Unterricht stört, wird daraus ein
eigener Punkt.

**Ergebnis** _(offen)_

---

## A12 — Fiducials · **VORAUSSETZUNG**

**Vorhanden:** ja, mit dem Spot mitgeliefert (Stand 07.08.2026). Damit ist nur noch die
Anbringung zu prüfen, nicht die Beschaffung.

**Die stille Falle — Grösse.** Aus `spot-sdk/docs/concepts/autonomy/initialization.md`:
*„Spot is configured to treat fiducials as 146mm squares and computes the distance based on
that size. If a fiducial is printed at another size, Spot will infer the wrong position."*

Das ist gefährlicher als ein Fehler, denn **es gibt keinen**: ein nachgedrucktes oder
kopiertes Fiducial in falscher Grösse wird erkannt, liefert aber eine falsche Entfernung —
die Karte wird still verzerrt. **Also nur die mitgelieferten Aufkleber verwenden.** Muss doch
nachgedruckt werden: AprilTag-Set Tag36h11, 146 mm im Quadrat, auf weissem, mattem Papier,
Druck mit 100 % Skalierung (kein „an Seite anpassen").

**Anbringung**, ebenfalls aus derselben Quelle:

- Eines **am Startpunkt** der Aufnahme.
- Flach und fest an eine **senkrechte Wand** kleben. Verrutscht ein Fiducial nach der
  Aufnahme, ist die Karte an dieser Stelle wertlos.
- **Tief hängen:** die Oberkante auf Kniehöhe, 45–60 cm über dem Boden.
- Jedes Fiducial in einer Karte nur **einmal** verwenden.
- Nicht in wechselndes Licht, nicht im Gegenlicht (also nicht auf ein Fenster).
- Dort hinhängen, wo sonst wenig zu sehen ist — etwa an einer langen kahlen Wand. Ecken,
  Möbel und Geräte liefern dem Roboter ohnehin genug Merkmale.

**Prozedur** Fiducials nach obiger Liste anbringen, Spot davorstellen,
`spotlab record-map test` starten.

**Erwartung** Kein `STATUS_MISSING_FIDUCIALS`; die Aufnahme läuft an.

**Warum das zuerst kommt** Ohne Fiducial ist die ganze GraphNav-Stufe nicht benutzbar —
weder Aufzeichnen noch Lokalisieren noch Fahren. Fällt A12 durch, sind A13–A16 gegenstandslos.

**Ergebnis** _(offen — Beschaffung erledigt, Anbringung und Erkennung offen)_

---

## A13 — Karte aufzeichnen

**Prozedur** Aufnahme starten, mit dem **Tablet** durch den Raum fahren, unterwegs zwei
benannte Wegpunkte setzen, beenden und speichern.

**Erwartung** Der Zähler in der GUI steigt sichtbar; `karten/<name>/graph` existiert; für
jeden Wegpunkt liegt ein Schnappschuss in `waypoint_snapshots/`; `spotlab maps` zeigt die
Karte mit plausiblen Zahlen; die benannten Wegpunkte tauchen in `spot.load_map(...).waypoints`
auf.

**Beobachten statt annehmen** Wie dicht der Dienst von selbst Wegpunkte setzt, ist nicht
dokumentiert festgelegt. Notieren, wie viele Wegpunkte auf welcher Strecke entstanden sind.

**Ergebnis** _(offen)_

---

## A14 — Gegenprobe zur Interoperabilität

**Prozedur** Dieselbe Karte in der Ansicht „Karten" **und** mit
`python view_map.py <pfad>` aus `spot-sdk/python/examples/graph_nav_view_map/` öffnen.

**Erwartung** Beide zeigen dieselbe Anordnung der Wegpunkte.

**Was das auf einen Schlag bestätigt** Das Kartenformat (Entscheidung N5) und die
Positionsrechnung in `maps/geometry.py`. Notieren, ob unsere Ansicht `anker` oder `kette`
als Quelle meldet — nach einem `load_map()` sollte es `anker` sein, weil wir mit
`generate_new_anchoring=True` hochladen.

**Ergebnis** _(offen)_

---

## A15 — Lokalisieren nach Neustart

**Prozedur** Roboter neu starten. Dann `spot.load_map("<name>")` und `spot.localize()`.

**Erwartung** Die Verortung gelingt und nennt einen Wegpunkt der Karte. Ohne sichtbares
Fiducial kommt stattdessen die Klartextmeldung, die zum Fiducial schickt.

**Ergebnis** _(offen)_

---

## A16 — Autonome Fahrt

**Freifläche und Aufsicht sicherstellen. Der Roboter fährt selbstständig.**

**Prozedur** `spot.navigate_to("<name>")` zu einem entfernten Wegpunkt.

**Erwartung** Der Spot erreicht den Wegpunkt. **Die aus `runs/<id>/zustand.jsonl` gemessene
Höchstgeschwindigkeit bleibt unter `max_speed` aus `config.toml`.** Der NOT-AUS in der GUI
wirkt während der Fahrt.

**Den gemessenen Wert notieren.** Er ist die Bestätigung, dass der Deckel greift und nicht
nur im Code steht — der einzige Punkt dieser Stufe, den kein Test ohne Roboter beweisen kann.

**Ergebnis** _(offen)_

---

## A17 — Ein aus dem Editor gestarteter Lauf lässt sich genauso stoppen

**Prozedur** Ein Programm aus der Ansicht „Code" starten. Im ersten Durchgang „Stopp"
drücken, im zweiten den NOT-AUS in der Kopfleiste.

**Erwartung** „Stopp" setzt Spot hin wie bei einem Lauf aus „Projekte". Der NOT-AUS schaltet
die Motoren ab. Der Lauf erscheint danach in „Läufe", und die Ansicht springt beim Starten
**nicht** weg von „Code".

**Warum das trotz Delegation am Gerät geprüft wird:** ein zweiter Startweg, der beim
Anhalten anders reagiert, wäre die gefährlichste Art, diese Stufe falsch zu bauen. Dass der
Knopf dieselbe Methode desselben Objekts ruft, steht im Code — dass die Kette aus Watcher,
Lauf-Verzeichnis und Stopp-Markierung auch bei diesem Startweg vollständig geschlossen ist,
zeigt erst der Roboter.

**Ergebnis** _(offen)_

---

## A18 — Abtastrate und Lücken über WLAN

**Prozedur** Eine Messfahrt mit `hz=50` über 30 s auf ebenem Boden, danach
`messfenster.json` und `zustand_zusammenfassen` ansehen.

**Erwartung** `hz_ist` und die Lückenliste werden **notiert, nicht bestanden oder
durchgefallen**. Diese Zahl entscheidet, ob 50 Hz realistisch sind oder ob die Fenster auf
20 Hz gehen müssen — und sie ist die einzige, die kein Test ohne Roboter liefern kann.

**Zusätzlich notieren:**

- ob `spotlab doctor` unter „Zustandsstrom" den 333-Hz-Dienst meldet,
- ob `ground_mu_est` von null verschiedene Werte liefert. Bleibt der Reibwert konstant 0,
  fällt diese Quelle für die Kalibrierung aus — besser vor der Messkampagne gewusst als
  danach.

**Ergebnis** _(offen)_

---

## A19 — Beobachtungssitzung

**Warum dieser Punkt VOR A1 kommen darf** Der Beobachter holt kein Lease und
registriert keinen Not-Aus-Endpunkt. Er kann den Roboter nicht bewegen —
`Zustandsquelle` hat genau eine Methode. Genau das ist hier zu **beweisen**,
nicht anzunehmen.

**Vorsicht trotzdem:** der Spot fährt, nur eben von Hand. Freifläche, Aufsicht,
Tablet in Reichweite. Dass spotlab nicht steuert, macht den Roboter nicht
harmlos.

**Bedienung** Zwei Personen: eine am Tablet, eine am Laptop.

**Prozedur**
1. `python scripts/beobachten_real.py` (in matura-spot) starten, Abschnitt B1.
2. Von einem zweiten Rechner: `spotlab lease` — muss `frei` melden.
3. Von einem zweiten Rechner: `spotlab doctor` — Stufe „Not-Aus-Endpunkt" muss
   `kein 'spotlab'-Endpunkt in der Konfiguration` melden.
4. Abschnitt B2-3: mit dem Tablet geradeaus fahren und die Anzeige auf
   0.17 m/s halten.
5. Strg-C mitten in einem Abschnitt.

**Erwartung**
- (2) und (3) beweisen die Leaselosigkeit. Meldet eines von beidem etwas
  anderes, ist der Beobachter nicht das, was er zu sein behauptet — dann darf
  er auch nicht vor A1 benutzt werden.
- (4) Die Live-Anzeige ist aus zwei Metern lesbar, und der Wert unter
  `messwerte.versatz_x_m / dauer_s` im Protokoll passt zu dem, was während der
  Fahrt angezeigt wurde.
- (5) Der Lauf ist sauber abgeschlossen (`lauf.json` trägt `abgebrochen`), und
  `protokoll_beobachtung.json` enthält die bis dahin gefahrenen Abschnitte samt
  eingetippter Impulse.

**Notieren** Ob sich ein Zielband überhaupt halten lässt. Davon hängt ab, ob die
Bänder taugen oder ob die Auswertung breiter binnen muss. Ausserdem `hz_ist` je
Fenster: über WLAN ist die erreichte Abtastrate ungemessen (siehe A18).

**Ergebnis** _(offen)_

---

## A20 — Fremdes Skript bewegt den Spot

Der dritte Startweg zum echten Roboter, und der am wenigsten geprüfte: aus
„Anbindungen" lässt sich **fremder Code** starten, ohne Trockenlauf-Schranke.
Ein Skript mit `roboter = true` im Manifest fährt damit den echten Spot.

**Prozedur**
1. Ein Projekt anbinden, dessen `spotlab.toml` ein Skript mit `roboter = true`
   führt (matura-spot: „Gates am echten Spot").
2. Aus der Ansicht „Anbindungen" starten.
3. Während es läuft: den Stopp-Knopf in „Anbindungen" drücken.

**Erwartung**
- (2) Das Fenster wechselt **von selbst** zur Live-Ansicht. Der NOT-AUS gehört
  in Sichtweite, sobald fremder Code den Roboter bewegt — bei einem Skript ohne
  `roboter = true` bleibt die Ansicht dagegen bei den Panels.
- (3) Der Spot bremst, setzt sich hin, Motoren aus. Derselbe Weg wie der
  Stopp-Knopf im Editor: er delegiert an dieselbe Live-Ansicht, weil der
  freundliche Stopp am Lauf-Verzeichnis hängt.

**Gegenprobe** Ein Skript mit `roboter = false` starten. Die Ansicht darf
**nicht** wechseln — sonst sieht niemand mehr seine Panels, und die Regel wird
im Alltag umgangen.

**Ergebnis** _(offen)_

---

## A21 — Die Sonde ist leaselos

**Vorgehen** Mit dem Tablet das Lease nehmen und den Spot stehen lassen. Dann am
Laptop in der Ansicht „Umwelt" auf „Umgebung abfragen" drücken.

**Erwartung**
- (1) Die Sonde läuft durch und listet Objekte — obwohl das Tablet das Lease hält.
- (2) Das Tablet **verliert sein Lease nicht** und meldet keine Übernahme.
- (3) Der Spot bewegt sich während der ganzen Abfrage um keinen Millimeter.

**Gegenprobe** Während die Sonde läuft, am Tablet fahren. Muss ungestört gehen —
ein reiner Lesedienst darf die Führung nicht beeinträchtigen.

**Warum am Gerät** `tests/test_sonde.py` hält fest, dass das Modul keine
Bewegungsfunktion aufruft. Dass `WorldObjectClient` und `LocalGridClient` neben
einem FREMDEN Lease funktionieren, kann kein Test beantworten — nur der Roboter.

**Ergebnis** _(offen)_

---

## A22 — Erkennungsreichweite der Fiducials

**Vorgehen** Einen AprilTag an eine Wand kleben, gemessene Kantenlänge notieren
(Soll 146 mm; ein auf A4 „an Seite angepasst" gedrucktes BD-PDF misst 133 mm und
liefert alle Distanzen um den Faktor 146/gemessen zu kurz). Den Spot in
1-m-Schritten entfernen, an jeder Stelle die Sonde auslösen.

**Erwartung** Die Entfernung notieren, ab der der Tag nicht mehr gemeldet wird.
Die Physik-Sim in matura-spot rechnet mit rund 12 m, der Übungsraum (2D und 3D)
mit `TAG_REICHWEITE_M = 3.0`; real werden 2–3 m erwartet. Dazu den Winkel: den
Tag schräg anfahren und notieren, bis zu welchem Winkel zwischen Tag-Normale
und Blickrichtung er noch gemeldet wird — der 3D-Übungsraum nimmt 60° an
(`spotsim.puppe.TAG_MAX_SCHRAEG_GRAD`). Beide Zahlen nach der Messung eintragen.

**Gegenprobe** Am Tablet nachsehen, ob Spot den Tag dort noch anzeigt. Zeigt das
Tablet ihn und die Sonde nicht, liegt es an der Abfrage, nicht am Tag.

**Der gemessene Wert gehört als Versuchsbedingung in die Maturaarbeit**, nicht
nur in dieses Dokument.

**Ergebnis** _(offen)_

---

## A23 — Raum bauen und in 3D fahren

**Vorgehen** Im Raumeditor die Vorlage `leer` laden, mit dem Werkzeug *Block*
einen Kasten von 1 × 0.4 m aufziehen, ihn über das Zahlenfeld um 30° drehen und
2 m vor den Start stellen, unter eigenem Namen speichern. Im Editor
`Übungsraum 3D (MuJoCo)` wählen und ein Programm starten, das `move(forward=3.0)`
fährt.

**Erwartung** Das Ereignis `angestossen` nennt den Blocknamen; die Stelle im
Übungsfenster liegt an der GEDREHTEN Kante, nicht an der Hülle des ungedrehten
Rechtecks. `spot.obstacles().free_distance(...)` in zwei Richtungen (entlang und
quer zum Block) gibt zwei verschieden lange Strecken, die zur Drehung passen.
Danach dasselbe mit `Übungsraum (virtuell)`: gleiche Stelle, gleicher Name.

**Ergebnis** _(offen)_

---

## A24 — Rekonstruierter Gang in 3D fahren

**Vorgehen** Im Raumeditor „Rekonstruieren…", die Katakomben-Karte wählen,
Vorschau, Übernehmen; grobe Fehlstücke mit `Entf` entfernen, die Türen prüfen,
unter `katakomben` speichern. `Übungsraum 3D (MuJoCo)` wählen und ein Programm
starten, das den Gang entlangfährt und `spot.tags()` ausgibt.

**Erwartung** Die Tag-Nummern und -Blickrichtungen stimmen mit den echten Tags
im Gang überein (z-Achse des Fiducial-Rahmens = Blick; an der Karte gemessen,
am Gerät zu bestätigen). Spot stösst an den rekonstruierten Wänden dort an, wo
im echten Gang Wände stehen.

**Ergebnis** _(offen)_

---

## A25 — Treppenmodus und die Regel „Nase bergauf"

**Vorgehen** `treppen = "auto"` in `config.toml [limits]`. Spot 1.5 m vor einer echten
Treppe (Fuss), Nase zur Treppe. `walk(vx=0.2, duration=8)` hinauf; oben `walk(vx=-0.2,
duration=8)` rückwärts hinunter, ohne Drehung. Danach absichtlich falsch herum: oben
umdrehen und `walk(vx=0.2, duration=4)` vorwärts auf die Kante zu — mit der Hand am
Not-Aus des Tablets.

**Erwartung** Hinauf und rückwärts hinunter gehen ohne Zutun (die Firmware nimmt die
Stufen). Was der Roboter beim vorwärts-abwärts tut — verweigern, anhalten, trotzdem
gehen —, wird hier notiert und in `welt/hoehe.py::treppe_erlaubt` übernommen: der Sim
verweigert bis dahin.

**Ergebnis** _(offen)_

---

## A26 — `spot.stairs()` vor einer echten Treppe

**Vorgehen** Am Fuss derselben Treppe `for t in spot.stairs(): print(t)`, dann am Kopf.

**Erwartung** Je einmal `direction == "auf"` bzw. `"ab"`, `steps` und `rise_m` wie
gezählt und gemessen (Stufen × Steigung), `axis_bearing` zeigt bergauf (Peilung
gegen Augenschein, ±15°), `distance` zur nächsten Kante (±0.3 m).

**Ergebnis** _(offen)_

---

## A27 — Das Hindernisgitter auf der Treppe

**Vorgehen** Am Fuss `spot.obstacles().free_distance(x, y, blick)` in Richtung der
Treppe; dann oben am Kopf in Richtung der Kante.

**Erwartung** Annahme im Sim: Stufen sind im Gitter frei, eine Absturzkante ist belegt
(Höhensprung über 0.25 m). Abweichungen hier eintragen und in `welt/wahrnehmung.py`
und `spotsim/local_grid.py` (Sprungregel) zurückspielen.

**Ergebnis** _(offen)_

---

## A28 — Die Katakomben, korrigiert, in 2D und 3D abgefahren

**Vorgehen** Im Raumeditor „Rekonstruieren…" (Katakomben-Karte), dann „Korrigieren…"
mit den Vorschlägen (unklare Zeilen so lassen), „Anwenden", unter `katakomben`
speichern. Im 2D-Sim ein Programm, das den aufgezeichneten Weg mit `spot.move`
von Wegpunkt zu Wegpunkt nachfährt (die Wegpunkte stehen im Pauspapier:
`welt.pauspapier.lies_weg`); dann dasselbe in `Übungsraum 3D (MuJoCo)`. Ein Bild
der 3D-Sicht ins Protokoll.

**Erwartung** Kein `angestossen`-Ereignis und keine „Kante" in beiden Sims;
`spot.state.z` folgt dem Gefälle (über 2 m Spanne); die Treppe steht auf dem
Gelände, hoch und rückwärts runter ohne `treppe_verweigert`. Im Test
`tests/test_katakomben_korrektur.py` läuft der Weg mit `bewege_mit_hoehe` ohne
Anstoss durch (07.09.2026).

**Ergebnis** _(offen)_

---

## Nach der Abnahme

Ergebnisse hier eintragen, Abweichungen als Befund in die Spec zurückspielen, und erst
dann Schüler an das Gerät lassen.
