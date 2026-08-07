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

```
pip install -e .[dev]
```

## Schnellstart

```
spotlab login                    # IP, Benutzer, Passwort (Passwort in den Windows-Tresor)
spotlab doctor                   # Netz, Anmeldung, Zeitsync, Not-Aus, Lease, Akku
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

Vier Ansichten in einer Seitenleiste: **Projekte** (anlegen, in VS Code öffnen, starten —
mit Häkchen für Trockenlauf), **Live-Lauf** (Ereignisse, Telemetrie, Kamerabild, Ausgabe),
**Läufe** (Liste vergangener Läufe mit der Kurve kommandiertes gegen gemessenes Tempo) und
**Spot** (Zugangsdaten und Prüfung). Hell und dunkel folgen der Windows-Einstellung.

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
| Wahrnehmung | `cameras()`, `camera(name)`, `state` |
| Roh | `robot`, `send(command)` |

`move()` ist eine relative Zieltrajektorie und wartet auf die echte Rückmeldung des
Roboters — `turn` in **Grad**. `walk()` ist das Geschwindigkeitskommando des SDK und
sendet intern automatisch nach, weil Geschwindigkeitskommandos beim echten Spot
ablaufen.

`spot.cameras()` meldet, was das aktive Backend **wirklich** hat. Fehlt eine Fähigkeit,
gibt es einen klaren Fehler statt einer Attrappe.

## Kommandos

| Kommando | Zweck |
|---|---|
| `spotlab login` | IP, Benutzer und Passwort hinterlegen |
| `spotlab doctor` | stufenweise Diagnose, bricht beim ersten Fehler ab |
| `spotlab new <name>` | Projekt mit lauffähiger Vorlage anlegen |
| `spotlab open [projekt]` | in VS Code öffnen |
| `spotlab run <datei> [--dryrun]` | starten und aufzeichnen |
| `spotlab runs` · `runs <id>` | Läufe auflisten und ansehen |
| `spotlab lease [--take]` | wer steuert den Spot; bewusste Übernahme |

Die Aufzeichnung hängt an `connect()`, nicht an `spotlab run` — wer in VS Code F5
drückt, bekommt sie genauso.

## Läufe

Pro Lauf ein Verzeichnis unter `runs/<zeitstempel>_<skript-hash>/`:

| Datei | Inhalt |
|---|---|
| `lauf.json` | Metadaten, Roboterkennung, Ergebnis, Dauer |
| `ereignisse.jsonl` | Kommandos, Rückmeldungen, Fehler, mit Zeitstempel |
| `zustand.jsonl` | 10 Hz: Pose, Geschwindigkeit, 12 Gelenke, Fusskontakte, Akku |
| `bilder/` | Kamerabilder mit Intrinsics |

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

## Weiterlesen

- Entwurf und Begründungen: [`docs/superpowers/specs/2026-08-06-spotlab-fundament-design.md`](docs/superpowers/specs/2026-08-06-spotlab-fundament-design.md)
- Umsetzungsplan: [`docs/superpowers/plans/`](docs/superpowers/plans/)
- Abnahme am Gerät: [`docs/ABNAHME.md`](docs/ABNAHME.md)

## Tests

```
pytest
```

Alle Tests laufen ohne Roboter und ohne Netz. Das `dryrun`-Backend ist das
Standard-Testdouble; die Kommando-Protobufs werden dabei echt gebaut und gegen die
SDK-Schemata geprüft.
