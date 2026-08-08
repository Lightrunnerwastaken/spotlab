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
Sieben Tests decken das ab (`tests/test_real_estop.py`), darunter der Fall eines stale
eigenen Endpunkts nach einem Absturz.

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

**Zusätzlich** Dasselbe mit Ctrl-C mitten im Lauf und mit einem Skript, das absichtlich
eine Ausnahme wirft. Beide Male muss der Abbau vollständig durchlaufen.

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

**Erwartung** 1.0 m ± 10 cm; 90° ± 10°. `move()` kehrt erst zurück, wenn der Roboter
„angekommen" meldet, nicht nach einer geschätzten Zeit.

**Notieren** Streuung über die fünf Läufe — das ist eine Vergleichsgrösse für die spätere
Sim-Kalibrierung.

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

## Nach der Abnahme

Ergebnisse hier eintragen, Abweichungen als Befund in die Spec zurückspielen, und erst
dann Schüler an das Gerät lassen.
