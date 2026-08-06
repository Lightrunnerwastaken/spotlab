# spotlab — Fundament (Sitzungskern + Schülerbibliothek)

**Datum:** 2026-08-06
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 1+2 des Gesamtsystems. Kein GUI, kein MCP, kein Sim-Adapter.

---

## 1 Zweck

`spotlab` soll Schülerinnen und Schülern an der Kantonsschule erlauben, den Boston
Dynamics Spot zu programmieren, ohne zuvor die Betriebsmechanik des SDK
(Authentifizierung, Zeitsynchronisierung, E-Stop, Lease, Leistungsverwaltung) zu
beherrschen. Es senkt die Einstiegshürde, ohne den Weg zum echten SDK zu
verstellen.

Zweitzweck, gleichrangig: jeder Lauf am echten Roboter erzeugt eine
reproduzierbare Messaufzeichnung. Diese Aufzeichnungen sind später die
Datengrundlage, um die MuJoCo-Simulation aus `matura-spot` gegen das echte
Verhalten zu kalibrieren (Aufgabenfeld 4 der Maturaarbeit, Sim-zu-Real).

### Zielgruppe

1. **Schüler ohne Robotik-Vorerfahrung** — schreiben Python in VS Code, wollen dass
   der Roboter etwas tut, brauchen verständliche Fehlermeldungen.
2. **Fortgeschrittene Schüler und der Autor** — brauchen ungehinderten Zugang zum
   vollen `bosdyn`-SDK, wollen aber Lease, Not-Aus und Aufzeichnung geschenkt
   bekommen.
3. **Aufsichtführende Lehrpersonen** — müssen sehen können, wer die Kontrolle über
   den Roboter hat, und sich auf den physischen Not-Aus verlassen können.

---

## 2 Einordnung ins Gesamtsystem

Das angestrebte Gesamtsystem besteht aus sechs weitgehend unabhängigen
Subsystemen. Diese Spec deckt ausschliesslich die ersten beiden ab.

| Stufe | Subsystem | Status |
|---|---|---|
| **1** | **Verbindungs- und Sitzungskern** (IP, Auth, Zeitsync, E-Stop, Lease, Leistung) | **diese Spec** |
| **2** | **High-Level-Bibliothek** (Schülerverben über `bosdyn-client`) | **diese Spec** |
| 3 | App/GUI (Status, Kamerabild, Not-Aus-Knopf) | später |
| 4 | Werkstatt-Oberfläche in der GUI | später (CLI-Teil ist hier drin) |
| 5 | Run-History-Auswertung | Datenformat hier, Auswertung später |
| 6 | MCP-Server für Agents | später |
| — | Sim-Adapter, NN-Anbindung | später |

Stufen 3–6 sind ausdrücklich als **Klienten der Stufen 1+2** entworfen. Sie
bekommen keine eigene Roboter-Logik. Deshalb entsteht die Werkstatt in dieser
Stufe als Kommandozeile: was als Kommando existiert und geprüft ist, kann die
GUI *und* der MCP-Server später aufrufen. Entstünde die Funktionalität
gleichzeitig mit der GUI, läge sie in Fensterklassen und wäre weder testbar noch
von Agents erreichbar.

---

## 3 Entschiedene Grundsatzfragen

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| G1 | Topologie bei einem Roboter und vielen Schülern | **Lokal pro Laptop, mit expliziter Lease-Etikette.** Kein zentraler Dienst. | Ein zentraler Broker ist für diese Stufe Overkill und bindet an Schul-IT. Der eigentliche Unfall — jemand übernimmt mitten im Lauf eines anderen — wird nicht durch Infrastruktur gelöst, sondern dadurch, dass Besitz sichtbar und Übernahme eine bewusste Handlung ist. Ausbau zu einem zentralen Dienst bleibt möglich, weil der Kern die Lease-Frage bereits explizit modelliert. |
| G2 | Nur echter Spot, oder auch Simulation | **Echter Spot zuerst. Backend-Abstraktion von Anfang an. Sim später als optionales Extra** (`spotlab[sim]`, versionsgepinnt gegen `matura-spot`). | `matura-spot` ist ein Forschungsrepo mit offenen Entscheidungen; eine harte Abhängigkeit würde Unterricht und Forschung gegenseitig blockieren. Der Trockenlauf-Adapter fällt bei bestehender Abstraktion fast gratis ab und wird das Standard-Testdouble. |
| G3 | Wem gehört die Roboterverbindung, während ein Schülerskript läuft | **Dem Skript.** Lease und E-Stop leben im Skriptprozess. Die Bibliothek schreibt einen strukturierten Ereignisstrom in ein Lauf-Verzeichnis. | Der Abbruchweg ist damit „Prozess beenden", woraufhin die Keepalives sterben und der Roboter von selbst in den sicheren Zustand geht — bosdyns eigener Failsafe bleibt der Failsafe und kann nicht kaputtprogrammiert werden. Ein zentraler Dienst müsste diesen Pfad nachbauen. Zusatznutzen: der Ereignisstrom ist zugleich Run-History (Stufe 5) und Kalibrierdatenquelle. |
| G4 | Was heisst „Fundament fertig" | **Kern + Werkstatt, vollständig über die Kommandozeile.** Ein Schüler kann damit eine ganze Lektion bestreiten. | siehe Abschnitt 2. |
| G5 | Eigener E-Stop-Endpunkt | **Ja**, die Bibliothek registriert einen eigenen Endpunkt mit Keepalive. | Der Not-Aus wurde bisher physisch und über das SDK-Beispiel genutzt; ein Software-Not-Aus im eigenen Prozess ist die Voraussetzung dafür, dass Prozessende gleich sicherer Zustand bedeutet. **Mit Sperrpunkt A1**, siehe Abschnitt 10. |
| G6 | Sprache in der API | **Python-Bezeichner englisch, Meldungen und Doku deutsch.** | `spot.stehen()` baut genau dort eine Hürde auf, wo der Übergang zur (englischen) Boston-Dynamics-Dokumentation stattfinden soll. Gilt auch für Ausnahmeklassen: `UnsupportedCapability` mit deutscher Meldung, nicht `SpotKannDasNicht`. Ausgenommen sind Datei- und Feldnamen der Aufzeichnung, die bewusst deutsch sind (Abschnitt 5.6). |

---

## 4 Architektur

Abhängigkeiten laufen strikt in eine Richtung. Jede Schicht ist ohne die darüber
liegenden testbar.

```
cli.py            dünne Hülle: Argumente parsen, Aufrufe weiterreichen
   │
workshop/         Projekte anlegen, Läufe starten, VS Code öffnen, Läufe auflisten
   │
api/              Schülerverben: spot.stand(), spot.move(), spot.camera()
   │
backends/         base.py (Protokoll + Fähigkeiten) · real/ (bosdyn) · dryrun.py
   │
bosdyn-client / bosdyn-api

record/           Ereignisstrom + Lauf-Verzeichnis  — hängt an nichts
errors/           bosdyn-Ausnahmen → Klartext        — hängt an nichts
config.py         Konfiguration + Zugangsdaten       — hängt an nichts
```

### Verzeichnisaufbau

```
spotlab/
  pyproject.toml
  README.md
  CLAUDE.md
  docs/superpowers/specs/
  src/spotlab/
    __init__.py          connect(), Version
    config.py            config.toml + Anmeldeinformationsverwaltung
    errors/
      __init__.py        Ausnahmehierarchie
      translate.py       bosdyn-Ausnahme → SpotlabError mit Klartext
    backends/
      base.py            SpotBackend-Protokoll, Capability
      dryrun.py          Trockenlauf: baut und validiert Protobufs, bewegt nichts
      real/
        __init__.py      RealSpot
        session.py       Aufbau-/Abbausequenz
        estop.py         Endpunkt + Keepalive
        lease.py         Erwerb, Keepalive, Verlusterkennung
        power.py         An/Aus, sicheres Hinsetzen
    api/
      __init__.py        Spot-Fassade
      posture.py         stand, sit
      motion.py          move, walk, stop
      perception.py      cameras, camera
      state.py           Zustandsschnappschuss
    record/
      run.py             Lauf-Verzeichnis und Schreiber
      events.py          Ereignistypen
      sampler.py         10-Hz-Zustandsabtaster
      read.py            Leser für `spotlab runs`
    workshop/
      project.py         new
      launcher.py        run
      editor.py          open (VS Code)
      templates/
        hallo_spot.py
    cli.py
  tests/
```

**Kernentscheidung zur Schichtgrenze:** Verbindung, Lease und E-Stop leben in
`backends/real/`, **nicht** im Backend-Protokoll. Der Sim-Spot hat weder Lease
noch Not-Aus; würde das Protokoll diese Begriffe erzwingen, müsste er sie
fälschen. Nach oben durchdringt stattdessen eine **Fähigkeitsmenge**.

---

## 5 Komponenten

### 5.1 `config.py` — Konfiguration und Zugangsdaten

`~/.spotlab/config.toml`:

```toml
[robot]
ip = "192.168.80.3"
username = "student"
nickname = "Spot der Kanti"

[limits]
max_speed = 0.6        # m/s, wird geklemmt, nicht abgewiesen
max_turn_rate = 0.8    # rad/s

[editor]
command = "code"       # Programm für `spotlab open`

[defaults]
backend = "real"       # oder "dryrun"
```

Die Backend-Wahl ist überschreibbar: `spotlab.connect(backend="dryrun")` bzw.
`spotlab run --dryrun`. Damit kann ein Schüler sein Skript zu Hause auf Tippfehler
prüfen, ohne Roboter und ohne Netz.

Das Passwort geht über `keyring` in die Windows-Anmeldeinformationsverwaltung,
mit den Umgebungsvariablen `BOSDYN_CLIENT_USERNAME` / `BOSDYN_CLIENT_PASSWORD`
als Rückfallebene fürs Testen und für CI. **Kein Passwort im Klartext auf zwanzig
Schullaptops.**

### 5.2 `backends/base.py` — Protokoll und Fähigkeiten

```python
class Capability(enum.Flag):
    LOCOMOTION      # walk / move
    POSTURE         # stand / sit
    POWER           # Motoren an/aus
    DEPTH_CAMERAS
    GRAY_CAMERAS
    COLOR_CAMERAS
    LEASE
    ESTOP
```

Das `SpotBackend`-Protokoll umfasst genau:

| Methode | Bedeutung |
|---|---|
| `capabilities() -> Capability` | was dieses Backend wirklich kann |
| `send_command(cmd, end_time_secs) -> cmd_id` | ein `bosdyn.api.RobotCommand`-Protobuf ausführen |
| `command_feedback(cmd_id)` | Rückmeldung zu einem laufenden Kommando |
| `robot_state() -> robot_state_pb2.RobotState` | Zustand als echtes SDK-Protobuf |
| `image_sources()` / `images(sources)` | Bildquellen und `image_pb2.ImageResponse` |
| `power_on()` / `power_off(safe=True)` / `is_powered` | Leistungsverwaltung |
| `safety_status()` | Lease-Halter und E-Stop-Zustand, oder `None` wenn nicht zutreffend |

Alles Weitere — Auth, Zeitsync, Keepalives — ist Konstruktionssache des jeweiligen
Backends und taucht im Protokoll nicht auf.

### 5.3 `backends/real/` — der Sitzungskern

**Aufbau, in dieser Reihenfolge:**

1. Konfiguration lesen, Passwort aus der Anmeldeinformationsverwaltung
2. SDK erzeugen (`create_standard_sdk("spotlab")`), Robot-Objekt, `authenticate`
3. `time_sync.wait_for_sync()` — ohne das lehnt der Roboter jedes Kommando ab
4. E-Stop-Endpunkt registrieren, Keepalive starten
5. Lease erwerben (`acquire`, **nie** implizit `take`), Keepalive starten
6. Aufzeichnung starten: Lauf-Verzeichnis anlegen, 10-Hz-Abtaster starten

**Die Motoren gehen dabei nicht an.** Ein 30-kg-Roboter darf nicht deshalb
aufstehen, weil jemand ein Skript gestartet hat. `spot.power_on()` ist eine
eigene Zeile, die jemand geschrieben haben muss. `spot.stand()` ohne Strom
scheitert mit Klartext.

**Abbau — zwei getrennte Wege, beide korrekt für ihre Situation:**

*Normales Ende* (Skript läuft durch, Ausnahme, oder Ctrl-C), streng in dieser
Reihenfolge und garantiert auch im Ausnahmefall:

1. Bewegung stoppen
2. Sicher hinsetzen **und** Motoren abschalten — ein Schritt,
   `robot.power_off(cut_immediately=False)`: der Roboter setzt sich kontrolliert
   hin und schaltet erst danach ab
3. Lease freigeben
4. E-Stop-Endpunkt abmelden
5. Lauf abschliessen, `lauf.json` mit Ergebnis schreiben

*Prozess wird hart getötet* (Absturz, Task-Manager, Stecker): die Keepalives
sterben, der Roboter geht selbst in den sicheren Zustand.

Der Grund für die Trennung: hielte unser Prozess einen E-Stop-Endpunkt und
endete einfach, schnitte der Roboter beim Wegfall des Keepalives die
Motorleistung ab — ein stehender Spot fiele um. Deshalb ist das *geordnete*
Ende immer ein sitzender Spot mit abgeschalteten Motoren. Das ist vorhersehbar
und beseitigt die Fehlerklasse „der Roboter ist umgefallen, als mein Programm
fertig war".

**Lease-Etikette (G1).** Der Lease-Client meldet sich als
`spotlab/<windows-benutzer>@<rechnername>` an, damit ein Halter einen Namen hat.
Ist das Lease belegt, nennt der Fehler wer und seit wann. Übernahme nur über
ausdrückliches `spotlab lease --take` bzw. `connect(take=True)`, mit
Warnung und Protokolleintrag im Lauf. Umkehrfall: verliert ein *laufendes*
Skript das Lease, erkennt das der Keepalive, und die Bibliothek bricht den Lauf
sauber ab mit „Jemand anders hat die Kontrolle übernommen" — statt einen
kryptischen `LeaseUseError` durchschlagen zu lassen.

### 5.4 `backends/dryrun.py` — Trockenlauf

Nimmt dieselben Protobufs entgegen, validiert sie gegen die SDK-Schemata,
protokolliert sie in den Ereignisstrom und liefert einen synthetischen, aber
schema-korrekten `RobotState` zurück. Bewegt nichts, braucht kein Netz.

Fähigkeiten: `LOCOMOTION | POSTURE | POWER` — **keine** Kameras, **kein** Lease,
**kein** E-Stop. Damit ist er zugleich der Testfall dafür, dass die
Fähigkeitsprüfung greift.

### 5.5 `api/` — die Schülerbibliothek

```python
import spotlab

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()

    spot.move(forward=1.0)          # 1 m vorwärts, blockiert bis angekommen
    spot.move(turn=90)              # 90° drehen

    bild = spot.camera("frontleft")
    bild.save("vorne.png")

    print(spot.battery)             # Ladestand in Prozent
```

| Bereich | Verben |
|---|---|
| Leistung | `power_on()`, `power_off()`, `is_powered`, `battery` |
| Haltung | `stand(height=0.0)`, `sit()` |
| Bewegung | `move(forward, left, turn)`, `walk(vx, vy, wz, duration)`, `stop()` |
| Wahrnehmung | `cameras()`, `camera(name)`, `state` |

**Zwei Bewegungsebenen mit Absicht.** `move()` ist eine relative Zieltrajektorie
im Körperframe (`synchro_trajectory_command_in_body_frame`) — „geh einen Meter"
schreibt man, ohne über Zeitintegration nachzudenken, und es kommt tatsächlich
an. `walk()` ist das Geschwindigkeitskommando des SDK und der Andockpunkt für
spätere Regelschleifen und neuronale Netze.

Beide blockieren standardmässig und warten auf die **echte Rückmeldung des
Roboters** (`stand()` bis „steht", `move()` bis „angekommen"), nicht auf
`sleep()`. `walk()` sendet intern automatisch nach, weil
Geschwindigkeitskommandos beim echten Spot ablaufen — die Lehre aus
`matura-spot`, hier eingebaut statt jedem Schüler überlassen.

**Kommandos werden ausschliesslich mit `RobotCommandBuilder` gebaut**, also echte
`bosdyn.api.RobotCommand`-Protobufs, keine parallele Eigen-API. Dieselbe Regel
wie in `matura-spot`, und genau der Grund, warum der Sim-Adapter später ohne
Umbau danebenpasst.

**Geschwindigkeitsdeckel** aus der Konfiguration wird geklemmt, nicht als Fehler
abgewiesen: ein Tippfehler soll langsam sein, nicht knallen.

**Die Abkürzung ist keine Mauer:**

```python
spot.robot                    # das rohe bosdyn-Robot-Objekt
spot.send(command)            # selbstgebautes RobotCommand-Protobuf
```

Fortgeschrittene kommen jederzeit an das volle SDK, **ohne spotlab zu
verlassen** und ohne Lease, E-Stop und Aufzeichnung aufzugeben. Dadurch ist das
hier ein Fundament und kein Spielzeug: die spätere NN-Schicht ist kein
Sonderfall, sondern ein weiterer Nutzer von `spot.walk()` und `spot.state`.

**Fähigkeiten sind sichtbar.** Jedes Verb deklariert, was es braucht. Fehlt es im
aktiven Backend, kommt `UnsupportedCapability: Dieses Backend hat keine
Kameras.` statt einer Attrappe.

### 5.6 `record/` — Aufzeichnung

Pro Lauf ein Verzeichnis `<projekt>/runs/<zeitstempel>_<skript-kurz-hash>/` — Zeitstempel als
`YYYYMMDDTHHMMSSZ` (UTC), Kurz-Hash die ersten 8 Zeichen des SHA-256 der
ausgeführten Skriptdatei, im selben
Geist wie `out/gates/<id>/` in `matura-spot`: jede Zahl zeigt auf einen
reproduzierbaren Lauf.

| Datei | Inhalt |
|---|---|
| `lauf.json` | Startzeit, Dauer, Backend, Roboter (Seriennr., Spitzname, Softwarestand), spotlab-Version, Skriptpfad + SHA-256, Ergebnis (`ok` / `fehler` / `abgebrochen` / `lease_verloren`), Benutzer und Rechner, ob übernommen wurde |
| `ereignisse.jsonl` | Je Zeile ein Ereignis: `{"t": <s seit Laufbeginn>, "art": ..., "daten": {...}}`. Arten: `verbunden`, `power_on`, `kommando`, `rückmeldung`, `bild`, `fehler`, `lease_verloren`, `ende` |
| `zustand.jsonl` | 10-Hz-Abtastung: Odometrie-Pose, lineare und winklige Geschwindigkeit, 12 Gelenke mit Position/Geschwindigkeit/Last, Fusskontakte, Batterie, IMU |
| `bilder/` | Kamerabilder plus Zeitstempel und Intrinsics in `bilder.json` |
| `ausgabe.log` | stdout/stderr des Skripts (nur bei `spotlab run`) |

Namenskonvention: die von uns erzeugten Schlüssel sind deutsch (`t`, `art`,
`daten`), die eingebetteten SDK-Nutzlasten behalten ihre englischen Feldnamen.
Das ist bewusst und nicht versehentlich gemischt.

`zustand.jsonl` trägt die Real→Sim-Kalibrierung: kommandierte gegen tatsächlich
gemessene Geschwindigkeit, echte Gelenkverläufe, echtes Fusskontakt-Timing. Der
Abtaster läuft in einem Hintergrund-Thread, unabhängig davon, was das
Schülerskript tut — auch ein Skript, das nur wartet, produziert verwertbare
Messdaten.

**Warum jsonl und keine Datenbank:** man kann mitlesen, während der Lauf noch
läuft; ein Absturz kostet höchstens die letzte Zeile; man kann die Datei ohne
Werkzeug öffnen. Damit ist der **Lauf-Ordner zugleich der Kanal zur späteren
App** — die GUI liest dieselben Dateien wie `spotlab runs`. Ein eigenes
Live-Protokoll wäre eine zweite Schnittstelle, die nichts kann, was Mitlesen
nicht auch kann.

### 5.7 `errors/` — Fehlerübersetzung

Für die Zielgruppe eine der wichtigsten Komponenten: der Unterschied zwischen
`bosdyn.client.auth.InvalidLoginError` und einem verständlichen Satz entscheidet,
ob ein Schüler weiterkommt oder die Lehrperson ruft.

| Ursache | Was der Schüler liest |
|---|---|
| Netz nicht erreichbar | „Ich erreiche 192.168.80.3 nicht. Bist du im WLAN des Spot?" |
| Falsche Zugangsdaten | „Benutzername oder Passwort stimmt nicht — `spotlab login`" |
| Zeit nicht synchron | „Die Uhr deines Laptops weicht zu stark ab; Zeitsynchronisierung fehlgeschlagen." |
| Lease belegt | „Anna steuert den Spot seit 14:03. Mit `spotlab lease --take` übernehmen." |
| Not-Aus ausgelöst | „Der Not-Aus ist ausgelöst. Am Tablet oder Knopf freigeben." |
| Lease mitten im Lauf verloren | „Kontrolle verloren — jemand anders hat übernommen. Lauf abgebrochen." |
| Batterie leer | „Batterie bei 4 %. Der Spot muss auf die Ladestation." |
| Kommando abgelehnt | Statuscode im Klartext plus was zu tun ist |
| Motoren aus | „Die Motoren sind aus — rufe zuerst `spot.power_on()` auf." |

Jede übersetzte Ausnahme behält die originale als `__cause__`: für die Schüler
Klartext, für die Entwicklung die volle Wahrheit.

### 5.8 `workshop/` und `cli.py`

| Kommando | Zweck |
|---|---|
| `spotlab login` | IP, Benutzer, Passwort hinterlegen |
| `spotlab doctor` | Netz → Auth → Zeitsync → E-Stop → Lease → Batterie, stufenweise, jede Stufe mit Klartext-Rat |
| `spotlab new <name>` | Projektordner mit lauffähiger Vorlage, `.vscode/`, README, `runs/` |
| `spotlab open [projekt]` | VS Code öffnen, mit verständlichem Hinweis falls `code` nicht im PATH |
| `spotlab run <datei>` | Skript starten, aufzeichnen, Ctrl-C = sauberer Abbau |
| `spotlab runs` · `runs show <id>` | Läufe auflisten und ansehen |
| `spotlab lease` · `lease --take` | Wer hat die Kontrolle; bewusste Übernahme |

`doctor` ist das Kommando, das im Unterricht die meiste Zeit spart: es
beantwortet „warum geht es nicht" in der Reihenfolge, in der die Dinge
tatsächlich schiefgehen.

**Die Aufzeichnung hängt an `connect()`, nicht am CLI.** Drückt ein Schüler in VS
Code F5, läuft `python hallo_spot.py` — und der Lauf wird trotzdem vollständig
aufgezeichnet. `spotlab run` ergänzt nur stdout-Mitschnitt und
Prozessverwaltung. Hinge die Aufzeichnung am Kommando, verlöre jeder
VS-Code-Lauf seine Daten, also gerade die Läufe, die die Schüler wirklich
machen.

Die Vorlage von `new` ist ein vollständiges, kommentiertes `hallo_spot.py` —
aufstehen, Bild machen, hinsetzen. Kein leeres Gerüst.

---

## 6 Datenfluss eines Laufs

```
Schülerskript
   │  spotlab.connect()
   ▼
Sitzungsaufbau (Auth → Zeitsync → E-Stop → Lease → Aufzeichnung)
   │
   ├─────────────► record/  ──► runs/<id>/lauf.json, ereignisse.jsonl
   │                                        ▲
   │  spot.move(forward=1.0)                │ 10 Hz
   ▼                                        │
api/motion  ──RobotCommandBuilder──►  RobotCommand-Protobuf
   │                                        │
   ▼                                   record/sampler ──► zustand.jsonl
backends/real ──gRPC──► Spot
   │
   ◄── Rückmeldung (blockiert bis „angekommen")
   │
   ▼
Sitzungsabbau (stoppen → sitzen → Motoren aus → Lease frei → E-Stop ab)
```

---

## 7 Fehlerbehandlung

Drei Ebenen, klar getrennt:

1. **Erwartete Betriebszustände** (Lease belegt, Not-Aus gedrückt, Batterie leer):
   werden zu `SpotlabError`-Unterklassen mit deutschem Klartext übersetzt
   (Tabelle 5.7) und beenden den Lauf geordnet.
2. **Verlust der Kontrolle im Lauf** (Lease weg, Verbindung weg): Keepalive
   erkennt es, der Lauf bricht ab, `lauf.json` bekommt `lease_verloren` bzw.
   `fehler`, der Abbau läuft trotzdem vollständig durch.
3. **Programmierfehler im Schülerskript**: Ausnahme propagiert unverändert nach
   oben, aber der Sitzungsabbau läuft garantiert (Kontextmanager mit `finally`),
   und die Ausnahme landet im Ereignisstrom.

In allen drei Fällen gilt: **der Abbau läuft immer**. Das ist die einzige
Invariante, die nicht verhandelbar ist.

---

## 8 Prüfung ohne Roboter

Das `dryrun`-Backend ist das Standard-Testdouble.

- **Alle Verben**: Protobufs werden echt gebaut und gegen die SDK-Schemata
  validiert — dieselbe Methode wie `tests/test_sdk_commands.py` in `matura-spot`.
- **Fehlerübersetzung**: pro Zeile der Tabelle 5.7 ein Test.
- **Sitzungs-Zustandsmaschine** gegen einen Fake-Roboter: Aufbaureihenfolge,
  Abbaureihenfolge, Abbau bei Ausnahme, Abbau bei Lease-Verlust, Abbau bei
  Ctrl-C.
- **Fähigkeitsprüfung**: `camera()` gegen `dryrun` muss `UnsupportedCapability`
  auslösen.
- **Geschwindigkeitsdeckel**: überhöhte Werte werden geklemmt, nicht abgewiesen.
- **Lauf-Verzeichnis**: schreiben → lesen → identisch; **abgeschnittene jsonl muss
  lesbar bleiben** (der Absturzfall).
- **Jedes CLI-Kommando** gegen `dryrun`.

Vorgehen: testgetrieben, Test vor Implementierung.

---

## 9 Abnahme am Gerät

Nur am echten Spot verifizierbar. Format analog `notes/REALISMUS_GATES.md`: jeder
Punkt trägt eine Prozedur und ein Ergebnisfeld.

| # | Prüfung | Warum |
|---|---|---|
| **A1** | **E-Stop-Koexistenz**: registriert unser Endpunkt sich *neben* dem des Tablets, oder verdrängt er ihn? | **Sperrpunkt.** Siehe Abschnitt 10. |
| A2 | Prozess hart töten (Task-Manager) → Spot geht in den sicheren Zustand | Der Failsafe aus G3 |
| A3 | Normales Ende → sitzt, Motoren aus, Lease frei | Der geordnete Weg aus 5.3 |
| A4 | Übernahme von einem zweiten Laptop → laufendes Skript bricht sauber ab mit Klartext | Lease-Etikette aus G1 |
| A5 | Uhr verstellen → richtige Zeitsync-Meldung | Häufigster Klassenraum-Fehler |
| A6 | `move(forward=1.0)` fährt gemessen 1 m ± Toleranz | `move()` muss halten, was es verspricht |
| A7 | Alle fünf Kameras liefern Bilder mit plausiblen Intrinsics | Grundlage für Wahrnehmungsaufgaben |
| A8 | `zustand.jsonl` eines 30-s-Laufs enthält lückenlos ~300 Abtastungen | Kalibriertauglichkeit der Aufzeichnung |

---

## 10 Offene Annahmen

**A1 — E-Stop-Verdrängung (Sperrpunkt).** Der bequeme SDK-Weg
`EstopEndpoint.force_simple_setup()` legt nach unserem Verständnis eine *neue*
E-Stop-Konfiguration an, in der nur der eigene Endpunkt steht. Träfe das zu,
verdrängte er den Endpunkt des Tablets — der physische Not-Aus in der Hand der
Aufsichtsperson wäre wirkungslos, solange ein Schülerskript läuft. Das ist im
Schulbetrieb nicht hinnehmbar.

*Auflösung:* am Gerät verifizieren. Bestätigt sich die Verdrängung, registriert
die Bibliothek ihren Endpunkt **zusätzlich zur bestehenden Konfiguration**,
statt sie zu ersetzen. **Bis A1 geklärt ist, findet kein Schülerbetrieb statt.**

**A2 — Bildquellen-Namen.** Die Benennung der Kameraquellen
(`frontleft_fisheye_image` usw.) wird zur Laufzeit über `image_sources()`
gelesen, nicht fest verdrahtet. `spot.camera("frontleft")` bildet auf die real
gemeldeten Namen ab; die Zuordnungstabelle wird bei A7 gegen das Gerät geprüft.

**A3 — Softwarestand des Roboters.** Die Zielversion des SDK ist
`bosdyn-client`/`bosdyn-api` 5.0.1.2 (in `matura-spot` unter Python 3.13 offline
verifiziert). Weicht der Softwarestand des Schul-Spot ab, wird die Version
angepasst; die Kompatibilität wird bei der Abnahme mitprotokolliert.

---

## 11 Nicht-Ziele dieser Stufe

GUI · MCP-Server · Sim-Adapter · NN-Anbindung · zentraler Mehrbenutzer-Dienst ·
Arm und Manipulation · GraphNav · Docking · Autowalk · Fiducial-Erkennung ·
Payloads · Audio · Missionen.

Alles davon ist später ein additiver Schritt hinter derselben Backend- und
Fähigkeitsabstraktion.

---

## 12 Abhängigkeiten

| Paket | Zweck |
|---|---|
| `bosdyn-client`, `bosdyn-api` (5.0.1.2) | das echte SDK |
| `keyring` | Passwort in der Windows-Anmeldeinformationsverwaltung |
| `numpy` | Bilddaten |
| `Pillow` | Bilder speichern |
| `pytest` (dev) | Tests |

Kommandozeile mit `argparse` aus der Standardbibliothek — die Abhängigkeitsfläche
bleibt klein, weil das Ding auf zwanzig Schullaptops installiert werden muss.

Python ≥ 3.11, entwickelt auf 3.13.
