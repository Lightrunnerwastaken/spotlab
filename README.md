# spotlab

Den Boston Dynamics Spot programmieren — für den Unterricht an der Kantonsschule.

`spotlab` nimmt die Betriebsmechanik des Spot-SDK ab (Anmeldung, Zeitsynchronisierung,
Not-Aus, Lease, Leistungsverwaltung), damit ein Schüler mit fünf Zeilen Python anfangen
kann. Es verstellt dabei nicht den Weg zum echten SDK: `spot.robot` und `spot.send()`
führen jederzeit zum vollen `bosdyn`-Client.

Jeder Lauf wird vollständig aufgezeichnet — Kommandos, Roboterzustand mit 10 Hz, Bilder.
Diese Aufzeichnungen sind zugleich die Datengrundlage, um später die MuJoCo-Simulation
aus [`matura-spot`](../matura-spot) gegen das echte Verhalten zu kalibrieren.

## Installation

Auf einem Schul-Laptop einmalig, im Ordner dieser Datei:

```
powershell -ExecutionPolicy Bypass -File einrichten.ps1
```

Das Skript legt eine eigene Umgebung unter `.venv` an, installiert spotlab mit
allen drei Extras, **prüft danach nach**, dass SDK, Oberfläche, MCP und pytest
wirklich da sind, und legt zum Schluss eine **Verknüpfung „spotlab" auf den
Desktop**. Zweimal ausgeführt ändert es nichts.

Danach genügt ein Doppelklick auf das Symbol — kein Terminal, keine
Umgebung aktivieren. Fehlt die Umgebung einmal (neu aufgesetzter Laptop,
gelöschter Ordner), richtet der Klick sie zuerst selbst ein und startet dann;
nur dieser erste Klick dauert ein paar Minuten.

Die Verknüpfung allein noch einmal anlegen, ohne neu zu installieren:

```
powershell -ExecutionPolicy Bypass -File verknuepfung.ps1
```

Von Hand geht es auch — dann aber mit allen Extras:

```
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev,gui,mcp]"
```

`pip install -e ".[dev]"` allein reicht **nicht**: ohne `gui` gibt es kein
Fenster und keinen Editor, ohne `mcp` keine Agenten-Anbindung. Die
Grundausstattung ist trotzdem eine gültige Installation — `spotlab doctor`,
`spotlab run` und die Auswertung laufen damit, und die Tests, die Qt brauchen,
überspringen sich sauber. Genau das prüft die CI im Auftrag `nur [dev]`.

Getestet auf Windows mit Python 3.11 und 3.13.

## Schnellstart

```
spotlab login                    # IP, Benutzer, Passwort (Passwort in den Windows-Tresor)
spotlab doctor                   # Netz, Anmeldung, Zeitsync, Not-Aus, Lease, Akku,
                                 # Lizenz, Nutzlasten, Dienste, Zertifikatsablauf
spotlab new mein-projekt
spotlab open mein-projekt
spotlab run hallo_spot.py
```

Ohne Roboter üben — baut und prüft alle Kommandos, bewegt nichts:

```
spotlab run hallo_spot.py --dryrun
```

## Oberfläche

```
pip install -e .[gui]
spotlab gui
```

Neun Ansichten in einer Seitenleiste: **Projekte** (anlegen, in VS Code öffnen, starten —
mit Häkchen für Trockenlauf), **Code** (der eingebaute Editor), **Live-Lauf** (Ereignisse,
Telemetrie, Kamerabild, Ausgabe), **Läufe** (vergangene Läufe mit der Kurve kommandiertes
gegen gemessenes Tempo), **Karten** (GraphNav aufzeichnen und ansehen), **Umwelt** (was
Spot gerade sieht), **Übungsraum** (ohne Roboter fahren), **Anbindungen** (fremde Projekte) und **Spot** (Zugangsdaten und
Prüfung). Hell und dunkel folgen der Windows-Einstellung.

### Der eingebaute Editor

Die Ansicht **Code** ist eine Ergänzung, kein Ersatz — `spotlab open` und „In VS Code
öffnen" bleiben. Sie kann: mehrere Reiter, Syntaxhervorhebung, Vervollständigung für
`spot.` und `spotlab.` mit deutscher Erklärung, Syntaxfehler nach einer kurzen Ruhepause,
Suchen und Ersetzen, Starten und Stoppen ohne die Ansicht zu wechseln, und **anklickbare
Dateinamen in Tracebacks** — ein Klick springt an die Zeile.

Zwei Dinge, die im Alltag zählen:

- **Vor dem Start wird alles gespeichert**, nicht nur der sichtbare Reiter. Ein Projekt aus
  mehreren Dateien läuft sonst mit der alten Fassung seiner Importe.
- **Beide Editoren dürfen dieselbe Datei offen haben.** Jeder Reiter merkt sich
  Änderungszeit und Grösse und fragt, bevor er fremde Änderungen überschreibt.

Nicht eingebaut: Debugger mit Haltepunkten, git-Integration, projektweite Suche,
Erweiterungen. Dafür ist VS Code da.

Die Oberfläche zeigt **jeden** Lauf im Arbeitsordner — auch die, die du in VS Code mit F5
startest.

**Zwei Arten anzuhalten**, und der Unterschied ist wichtig:

| Knopf | Wirkung |
|---|---|
| **Stopp** | Freundlich: das Programm bricht ab, der Abbau läuft, **der Spot setzt sich hin.** Reagiert es nach 3 s nicht, wird hartes Beenden angeboten. |
| **NOT-AUS** | Hart, ein Klick, keine Rückfrage: der Prozess wird getötet, **die Motoren gehen aus und der Spot sackt zusammen.** |

Der NOT-AUS wirkt nur auf das laufende spotlab-Programm. **Das primäre Sicherheitsmittel
bleibt der physische Not-Aus am Tablet.**

Die GUI hält **nie ein Lease** — sie liest alles aus dem Lauf-Verzeichnis mit. Deshalb gibt
es kein Live-Kamerabild ohne laufendes Skript: Bilder erscheinen, sobald ein Programm
welche aufnimmt.

## Karten

Der Spot kann einen Raum als GraphNav-Karte aufzeichnen und darauf danach autonom fahren.

**Aufzeichnen** — in der Ansicht „Karten" oder im Terminal:

```
spotlab record-map turnhalle
```

Zwei Voraussetzungen, die nicht verhandelbar sind: **der Spot muss beim Start ein Fiducial
sehen** (die AprilTag-Markierung), und **gefahren wird mit dem Tablet**. spotlab zeichnet nur
mit und übernimmt die Steuerung nicht — es braucht dafür kein Lease.

**Ansehen und auswählen** — `spotlab maps` listet auf, die Ansicht „Karten" zeigt eine
Draufsicht. *Als aktive Karte setzen* merkt die Wahl, danach reicht im Skript `load_map()`
ohne Argument.

**Darauf fahren:**

```python
with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()

    karte = spot.load_map()          # die in der GUI gewählte Karte
    print(karte.waypoints)           # ['start', 'kueche', 'fenster']

    spot.localize()                  # über das Fiducial verorten
    spot.navigate_to("kueche")
```

> **`navigate_to` bewegt den Roboter autonom.** Er fährt selbstständig eine Route ab. Sorge
> für freie Fläche und Aufsicht. Der Geschwindigkeitsdeckel aus `config.toml` gilt auch
> hier — er wird als `velocity_limit` an GraphNav durchgereicht.

Karten liegen im **Format des SDK** unter `<arbeitsordner>/karten/<name>/`. Eine mit spotlab
aufgezeichnete Karte lässt sich deshalb unverändert an `graph_nav_command_line.py` und
`view_map.py` aus dem Spot-SDK verfüttern — und umgekehrt.

## Übungsraum — ohne Roboter fahren

Der Sim fährt nach den am 12.08.2026 **gemessenen Gangarten**. Ein Meter dauert
dort so lange wie am echten Spot — ein Programm, das im Übungsraum ankommt,
kommt auch am Gerät an.

In der Ansicht **Übungsraum** wählst du ein Zimmer und klickst die
Startposition hinein:

| Vorlage | Inhalt |
|---|---|
| `leer` | vier Wände, ein Tag — für die ersten Schritte |
| `moebliert` | Tisch, zwei Stuhlstapel, zwei Tags — Ausweichen üben |
| `durchgang` | zwei Zimmer, eine Tür, der Tag liegt drüben |

```python
with spotlab.connect(backend="sim") as spot:      # oder raum="durchgang"
    spot.power_on()
    spot.stand()
    spot.move(forward=1.5)
    for tag in spot.tags():
        print(f"Tag {tag.id}: {tag.distance:.1f} m")
```

**An Wänden bleibt Spot stehen** — kein Fehler, kein Abbruch, so wie am echten
Gerät. Die Stelle wird in der Zeichnung markiert und im Protokoll vermerkt.

### Zuschauen, während es läuft

Über dem Editor steht **„Wo läuft es?"** mit bis zu vier Möglichkeiten:

| Wahl | Was passiert |
|---|---|
| `Echter Spot` | der Roboter fährt |
| `Trockenlauf (nur Text)` | nichts bewegt sich, das Programm läuft durch — **keine Position** |
| `Übungsraum (virtuell)` | Spot fährt durch das gewählte Zimmer, als Zeichnung |
| `Übungsraum 3D (MuJoCo)` | dasselbe im 3D-Zimmer mit Kameras, Tiefengitter und Kollision — nur, wenn `spotsim` installiert ist (unten) |

Bei `Übungsraum (virtuell)` geht **ein eigenes Fenster** auf und zeichnet die
Fahrt mit, während sie läuft — Weg, Blickrichtung, Anstösse, die letzte
Ausgabezeile. Leg es neben den Editor, dann siehst du Code und Fahrt zugleich.
Der Knopf **„▶ Offene Datei starten"** in der Ansicht „Übungsraum" stellt diese
Wahl selbst ein; er kann den echten Spot nicht erreichen.
`spot.tags()` und `spot.obstacles()` arbeiten dabei aus der Raumgeometrie, du
kannst also die ganze Bibliothek ohne Roboter üben.

Eigene Räume: eine TOML-Datei unter `<arbeitsordner>/raeume/<name>.toml`, gebaut
wie die mitgelieferten unter `welt/vorlagen/`.

### Übungsraum 3D

`backend="mujoco"` ist derselbe Sim mit einem Körper: der Menagerie-Spot aus
`matura-spot`, kinematisch gesetzt (Weg A — Wiedergabe statt Regelung, Spec
`docs/superpowers/specs/2026-09-06-uebungsraum-3d-design.md`). Was dazukommt:

- **Kollision an der echten Geometrie** statt an einem Kreis von 0.35 m.
- **`spot.obstacles()` aus fünf gerenderten Tiefenbildern**, durch denselben
  Entpacker wie am Roboter — mit Verdeckung und unbekannten Zellen: was hinter
  dem Tisch liegt, ist *nicht frei*, weil ungesehen.
- **`spot.tags()` mit Kamerablickfeld, Ausrichtung und Sichtstrahl** — ein Tag
  hinter dem Tisch bleibt unsichtbar.
- **`spot.camera("frontleft_fisheye_image")`** und die fünf Tiefenkameras.
- Das Übungsfenster zeigt das gerenderte Zimmer über der Zeichnung.

Gemessen sind Gangarten (12.08.2026) und die Antwort auf `move()` (02.09.2026:
Anfahren, Reisetempo, Bremsen, Totzeiten); die Standhöhe folgt aus den
gemessenen Winkeln über die Kinematik des Modells und liegt 2–8 mm neben der
gemessenen. Annahmen stehen in `bericht()` und in `lauf.json`.

**Video.** Nach einem Lauf steht im Übungsfenster **„🎬 Video speichern"**, in
der Ansicht „Läufe" derselbe Knopf für jeden alten Lauf — auch für 2D- und für
**echte** Läufe: das Video entsteht nachträglich aus `zustand.jsonl` (Pose und
zwölf Gelenke, 10 Hz, auf 30 fps interpoliert), nicht aus dem Bildschirm. Auf
der Kommandozeile: `spotlab film <lauf>` → `<lauf>/film.mp4`.

Installation (einmalig; `matura-spot` liegt neben spotlab):

    pip install -e .[sim]
    pip install -e ../matura-spot
    python ../matura-spot/scripts/fetch_menagerie.py

## Umwelt — was Spot gerade sieht

Der Spot führt selbst eine Liste der Objekte, die er erkennt: AprilTags, Dockingstationen,
Türen. Dazu ein Hindernisgitter mit dem Abstand zum nächsten Hindernis je Zelle.

In der Ansicht **Umwelt** steht dafür ein Knopf: **„Umgebung abfragen"**.

```
   apriltag 1     2.06 m   +14 Grad   vor 3 s
   dock 3         1.00 m     +0 Grad   vor 3 s
```

**Die Abfrage hält kein Lease und sendet kein Kommando.** Der Spot kann sich dadurch
nicht bewegen, und sie funktioniert, während jemand anderes mit dem Tablet fährt. Genau
dafür ist sie gedacht: nachsehen, ob Spot einen Tag überhaupt erkennt und aus welcher
Entfernung — **bevor** ein Programm startet, das ihn bewegt.

Im eigenen Programm sind es die Verben `spot.tags()`, `spot.world_objects()` und
`spot.obstacles()` (siehe unten).

## Ein Programm

```python
import spotlab

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()

    spot.move(forward=1.0)       # 1 m vorwärts, wartet bis angekommen
    spot.move(turn=90)           # 90 Grad drehen

    bild = spot.camera("frontleft")
    bild.save("vorne.png")

    print(spot.battery, "%")
```

`connect()` meldet an, synchronisiert die Uhr, registriert den Not-Aus und holt das
Lease. Am Ende des `with`-Blocks setzt sich der Spot hin und schaltet die Motoren ab —
auch wenn das Programm mit einem Fehler abbricht.

**Die Motoren gehen beim Verbinden nicht an.** `spot.power_on()` ist eine eigene Zeile,
die jemand geschrieben haben muss: ein 30-kg-Roboter steht nicht auf, nur weil jemand
ein Programm gestartet hat.

## Verben

| Bereich | Verben |
|---|---|
| Leistung | `power_on()`, `power_off()`, `is_powered`, `battery` |
| Haltung | `stand(height=0.0)`, `sit()` |
| Bewegung | `move(forward, left, turn)`, `walk(vx, vy, wz, duration)`, `stop()` |
| Kameras | `cameras()`, `camera(name)`, `state` |
| Umwelt | `tags(id=None)`, `world_objects(kinds=None)`, `obstacles()` |
| Karten | `load_map(name)`, `localize()`, `navigate_to(ziel)`, `waypoints()` |
| Messen | `messfenster(name, hz=50)` |
| Roh | `robot`, `send(command)`, `close()` |

`move()` ist eine relative Zieltrajektorie und wartet auf die echte Rückmeldung des
Roboters — `turn` in **Grad**. `walk()` ist das Geschwindigkeitskommando des SDK und
sendet intern automatisch nach, weil Geschwindigkeitskommandos beim echten Spot
ablaufen.

`spot.cameras()` meldet, was das aktive Backend **wirklich** hat. Fehlt eine Fähigkeit,
gibt es einen klaren Fehler statt einer Attrappe.

**Die Umwelt-Verben sprechen Grad und Meter**, dieselbe Einheit wie `move()`:

```python
for tag in spot.tags():
    print(f"Tag {tag.id}: {tag.distance:.1f} m, {tag.bearing:+.0f} Grad")

spot.move(turn=spot.tags()[0].bearing)      # dreh dich zum nächsten Tag
```

Die Liste ist nach Distanz sortiert, `spot.tags()[0]` ist also ohne Nachdenken das
nächste Ziel. **Nichts gesehen ist eine Antwort, kein Fehler** — dann kommt `[]` zurück.
`spot.obstacles()` liefert das Hindernisgitter mit `distance_at(x, y)` und
`is_free(x, y)`; wo Spot nicht hingesehen hat, gilt „nicht frei", nicht „frei".

## Kommandos

| Kommando | Zweck |
|---|---|
| `spotlab login` | IP, Benutzer und Passwort hinterlegen |
| `spotlab doctor` | stufenweise Diagnose, bricht beim ersten Fehler ab; sagt auch, was dieser Roboter **kann** (Lizenz, Nutzlasten, Dienste) und wann sein Zertifikat abläuft |
| `spotlab new <name>` | Projekt mit lauffähiger Vorlage anlegen |
| `spotlab open [projekt]` | in VS Code öffnen |
| `spotlab run <datei> [--dryrun]` | starten und aufzeichnen |
| `spotlab runs` · `runs <id>` | Läufe auflisten und ansehen |
| `spotlab lease [--take]` | wer steuert den Spot; bewusste Übernahme |
| `spotlab gui` | das Fenster öffnen (braucht `pip install -e .[gui]`) |
| `spotlab maps` | aufgezeichnete Karten auflisten |
| `spotlab record-map <name>` | eine GraphNav-Karte aufzeichnen |
| `spotlab mcp` | MCP-Server für Agenten, über stdin/stdout |

Die Aufzeichnung hängt an `connect()`, nicht an `spotlab run` — wer in VS Code F5
drückt, bekommt sie genauso.

## Läufe

Pro Lauf ein Verzeichnis unter `runs/<zeitstempel>_<skript-hash>/`:

| Datei | Inhalt |
|---|---|
| `lauf.json` | Metadaten, Roboterkennung, Ergebnis, Dauer |
| `ereignisse.jsonl` | Kommandos, Rückmeldungen, Fehler, mit Zeitstempel |
| `zustand.jsonl` | 10 Hz: Pose, Geschwindigkeit, 12 Gelenke, Fusskontakte, Akku |
| `bilder/` | einzelne Kamerabilder aus `spot.camera(...)`, mit Intrinsics |
| `kamera/` | nur im Beobachter-Modus: laufender Bildmitschnitt aller Kameras |

`kamera/` ist bewusst von `bilder/` getrennt. Dort liegen die Schnappschüsse, die ein
Schülerskript anfordert — eine Handvoll je Lauf, und die Live-Ansicht sucht darin bei
jedem Takt das neueste Bild. Der Mitschnitt einer Messfahrt sind zehntausend Dateien;
er bekommt deshalb ein eigenes Verzeichnis mit anhängendem Index `kamera.jsonl`.
Bilder liegen dort so, wie der Roboter sie geschickt hat: JPEG als `.jpg`, Tiefe roh
als `.raw` — umkodieren hiesse bei Tiefenbildern, die Millimeterwerte wegzuwerfen.

## Sicherheit

Zwei getrennte Wege, beide korrekt für ihre Situation:

- **Geordnetes Ende** (durchgelaufen, Ausnahme, Ctrl-C): stoppen → sicher hinsetzen →
  Motoren aus → Lease frei → Not-Aus-Endpunkt abmelden.
- **Prozess hart getötet**: die Keepalives sterben, der Roboter geht von selbst in den
  sicheren Zustand. Dieser Weg lässt sich nicht kaputtprogrammieren.

`spotlab` registriert seinen Not-Aus-Endpunkt **zusätzlich** zur bestehenden
Konfiguration, damit der physische Not-Aus am Tablet wirksam bleibt. Der bequeme
SDK-Weg `force_simple_setup()` würde ihn verdrängen und wird deshalb nicht benutzt.

> **Vor dem ersten Schülerbetrieb** ist die Abnahmeliste in [`docs/ABNAHME.md`](docs/ABNAHME.md)
> abzuarbeiten, insbesondere Punkt **A1** (Not-Aus-Koexistenz am echten Gerät).

### Für die Lehrperson: das Tempo herunterdrehen

In der Ansicht **Spot** lassen sich `max_speed` und `max_turn_rate` setzen; sie landen in
`~/.spotlab/config.toml`. **Für eine Anfängerstunde lohnt sich 0.2 m/s statt der
Voreinstellung 0.6.** Der Deckel wirkt auf allen drei Wegen — `walk()`, `move()` und die
autonome Fahrt — und ein Schülerskript kann ihn nicht überschreiben.

Werte, die keine Sicherheitsgrenze mehr wären, werden abgewiesen statt stillschweigend
übernommen: `inf`, `0` und negative Zahlen führen zu einer Fehlermeldung beim Start, nicht
zu einem wirkungslosen Deckel.

## Weiterlesen

**Für die Benutzung**

- Abnahme am Gerät: [`docs/ABNAHME.md`](docs/ABNAHME.md) — 22 Punkte, A1 ist der Sperrpunkt
- Fremde Projekte anbinden: [`docs/ANBINDUNG.md`](docs/ANBINDUNG.md)

**Für die Entwicklung** — jede Stufe hat ihren eigenen Entwurf mit Begründungen:

| Stufe | Entwurf |
|---|---|
| Fundament | [`2026-08-06-spotlab-fundament-design.md`](docs/superpowers/specs/2026-08-06-spotlab-fundament-design.md) |
| Oberfläche | [`2026-08-07-spotlab-gui-design.md`](docs/superpowers/specs/2026-08-07-spotlab-gui-design.md) |
| GraphNav | [`2026-08-07-spotlab-graphnav-design.md`](docs/superpowers/specs/2026-08-07-spotlab-graphnav-design.md) |
| Editor | [`2026-08-07-spotlab-ide-design.md`](docs/superpowers/specs/2026-08-07-spotlab-ide-design.md) |
| Anbindung + MCP | [`2026-08-07-spotlab-anbindung-design.md`](docs/superpowers/specs/2026-08-07-spotlab-anbindung-design.md) |
| Kalibrierung | [`2026-08-08-spotlab-kalibrierung-design.md`](docs/superpowers/specs/2026-08-08-spotlab-kalibrierung-design.md) |
| Beobachter-Modus | [`2026-08-09-spotlab-beobachtung-design.md`](docs/superpowers/specs/2026-08-09-spotlab-beobachtung-design.md) |
| Umwelt | [`2026-09-02-spotlab-umwelt-design.md`](docs/superpowers/specs/2026-09-02-spotlab-umwelt-design.md) |
| Übungsraum | [`2026-09-02-spotlab-uebungsraum-design.md`](docs/superpowers/specs/2026-09-02-spotlab-uebungsraum-design.md) |

- Umsetzungspläne: [`docs/superpowers/plans/`](docs/superpowers/plans/)
- Härtung, Befunde und Fahrplan: [`docs/HAERTUNG.md`](docs/HAERTUNG.md)
- Nicht verhandelbare Regeln und ihre Begründungen: [`CLAUDE.md`](CLAUDE.md)

## Tests

```
pytest
```

Alle Tests laufen ohne Roboter und ohne Netz. Das `dryrun`-Backend ist das
Standard-Testdouble; die Kommando-Protobufs werden dabei echt gebaut und gegen die
SDK-Schemata geprüft.
