# spotlab Umwelt — was Spot sieht, als API, Ansicht und Diagnose

**Datum:** 2026-09-02
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 9. Setzt Fundament (1+2), GUI (3), GraphNav (4) und
Beobachtung (8) voraus — letztere, weil der Gitter-Mitschnitt nach
`beobachtung/` zieht und dem Muster von `bilder.py` folgt.
Die Wahrnehmung beschränkte sich bisher auf Kamerabilder; diese Spec ergänzt
Objekte und Hindernisgeometrie und zieht dafür bestehenden Code aus
`matura-spot` heim.

---

## 1 Zweck

Ein Schüler soll den Spot fragen können, **was er gerade sieht** — und eine
Antwort bekommen, mit der sich weiterrechnen lässt:

```python
for tag in spot.tags():
    print(f"Tag {tag.id}: {tag.distance:.1f} m, {tag.bearing:+.0f}°")
spot.move(turn=spot.tags()[0].bearing)   # dreh dich zum Tag
```

Dieselbe Schicht trägt drei weitere Verbraucher: die GUI zeigt die Umgebung an,
eine leaselose Sonde fragt sie auf Knopfdruck ab, und `matura-spot` ersetzt damit
seine eigene Zweitimplementierung.

Dazu kommt eine erweiterte Geräte-Diagnose, die beantwortet, **was dieser
Roboter überhaupt kann** — Lizenz, Nutzlasten, Dienste, Zertifikat — statt es zu
raten.

### Vorgefundener Stand

`api/perception.py` kann Kameras (`Image`, `cameras`, `camera`) und sonst nichts.
Objekte, Fiducials und Hindernisgitter fehlen vollständig.

`matura-spot` hat beides bereits, aber am falschen Ort und in der falschen Form:

| Ort | Umfang | Problem |
|---|---|---|
| `spotsim/sdk_real.py: detect_target()` | ~40 Z. | Gibt `(pixel, peilung, distanz, quelle)` zurück — die Signatur von `detect_color()`, weil der Explorer sie erwartet. Als Schüler-API unbrauchbar. |
| `spotsim/gitter_mitschnitt.py` | 232 Z. | Fertiger, threadgestützter LocalGrid-Mitschnitt. Erkennbar nach dem Vorbild von `beobachtung/bilder.py` gebaut — gehört in dieses Repo. |

Die Abhängigkeitsrichtung steht bereits: `matura-spot` importiert an fünf
Stellen aus spotlab (`backends.real.verbindung`, `config`, `messung.fenster`,
`beobachtung.session`). Umgekehrt nie.

Die Diagnose (`workshop/doctor.py`) beantwortet die Lizenzfrage bisher
**indirekt** über die Dienstliste: steht `robot-state-streaming` darin, ist die
Joint-Control-Lizenz da. Das ist eine Heuristik, kein Befund.

---

## 2 Entschiedene Grundsatzfragen

**Grad, nicht Radiant.** `api/motion.py` rechnet `turn` von Grad nach Radiant
(`winkel = math.radians(float(turn))`) und protokolliert `turn_grad`. Die
Wahrnehmung spricht dieselbe Einheit. `spot.move(turn=tag.bearing)` muss
funktionieren, ohne dass jemand `math.degrees` kennt. `matura-spot` rechnet
intern in Radiant — die Umrechnung gehört in dessen Adapter, nicht in diese
Schicht.

**Links positiv**, gleiche Vorzeichenkonvention wie `move(left=…)`.

**Englische Bezeichner.** `api/` ist durchgehend englisch (`power_on`, `stand`,
`move`, `cameras`, `navigate_to`); nur `messfenster` ist deutsch, weil es zur
Kalibrierung gehört. Meldungen bleiben deutsch.

**Eine SDK-Abfrage, zwei Türen.** `tags()` ist ein Filter über
`world_objects()` mit reicherem Rückgabetyp, keine zweite Implementierung.

**„Nichts gesehen" ist eine Antwort, kein Fehler.** Leere Rückgabe ist `[]`,
nie `None`, nie eine Ausnahme.

**Aufgezeichnet wird, was abgefragt wird.** Kein Hintergrund-Polling der
Objekte: jeder `tags()`-Aufruf schreibt eine Zeile. Das hält die WLAN-Last
ehrlich und macht das Protokoll lesbar — man sieht, *wann gefragt wurde*, nicht
einen 10-Hz-Teppich. Das Gitter ist die Ausnahme (Abschnitt 4.3): es baut die
Karte über die Fahrt auf und läuft deshalb im eigenen Thread.

**Die GUI bleibt SDK-frei.** `gui/views/live.py` importiert kein bosdyn und
liest ausschliesslich das Lauf-Verzeichnis. Die neue Ansicht hält sich daran.
Eine eigene Roboterverbindung im GUI-Prozess wurde erwogen und **verworfen** —
sie bräuchte Zugangsdaten-Handling, und ein hängender Netzaufruf würde das
Fenster einfrieren. Die Sonde (4.6) löst dasselbe Problem ohne diesen Preis.

**Massendaten nicht in `zustand.jsonl`.** Der Recorder trennt bereits:
`sample()` schreibt Zeilen, `kamerabild()` schreibt Dateien plus Index. Das
Gitter folgt dem Bild-Muster.

---

## 3 Architektur

```
                 api/spot.py
        world_objects()  tags()  obstacles()
                      │
                 api/world.py          ← Datenklassen, SDK-frei
                      │
              backends/base.py         ← Schnittstelle
             ╱        │        ╲
   backends/real/  dryrun.py  sim.py
   wahrnehmung.py  (Attrappe) (Attrappe)
        │
   WorldObjectClient, LocalGridClient   ← reine Lesedienste
```

Neben diesem Strang, unabhängig:

```
   beobachtung/gitter.py  ──→  gitter/*.pb + gitter/gitter.jsonl
        (eigener Thread, 2 Hz)              │
                                            ▼
                                 gui/views/umwelt.py  (liest nur Dateien)
```

### Die Schichtregel

`api/world.py` enthält **keine bosdyn-Importe**. Datenklassen und Umrechnung
liegen dort, damit GUI und Tests sie ohne SDK importieren können — dieselbe
Regel, unter der `Map` in `navigation.py` steht. Alles Protokollnahe liegt in
`backends/real/wahrnehmung.py`.

### Warum eine neue Datei statt `api/perception.py`

`perception.py` handelt von **Pixeln** (`Image`, `cameras`), `world.py` von
**Geometrie**. Zwei Begriffe, zwei Dateien. Wer Bilder auswertet, braucht
Pillow und numpy; wer Objekte abfragt, braucht nur Zahlen.

---

## 4 Komponenten

### 4.1 `api/world.py` — die Datenklassen

```python
@dataclass
class WorldObject:
    name: str          # "world_obj_apriltag_001"
    kind: str          # "apriltag" | "dock" | "door" | "image_coordinates" | …
    bearing: float     # Grad, links positiv, im Körper-Frame
    distance: float    # Meter, in der Bodenebene
    world_xy: tuple    # Position im vision-Frame, oder None
    time: float        # Erfassungszeitpunkt, Zeitbasis wie zustand.jsonl

@dataclass
class Tag(WorldObject):
    id: int            # die aufgedruckte Nummer
    filtered: bool     # geglättete Pose oder rohe Einzelmessung
```

**Distanz in der Bodenebene**, nicht im Raum: der Tag hängt auf Kniehöhe, seine
Höhe interessiert beim Hinfahren niemanden. `math.hypot(x, y)` aus
`body_tform_object`, `bearing = degrees(atan2(y, x))`.

**`filtered`** unterscheidet `frame_name_fiducial_filtered` von
`frame_name_fiducial`. Spot glättet Fiducial-Posen über die Zeit; die geglättete
ist ruhiger, die rohe aktueller. Die Schicht bevorzugt die gefilterte und sagt
im Feld, welche es wurde — verschweigen wäre eine stille Genauigkeitsaussage.

### 4.2 `api/world.py` — die Verben

```python
def world_objects(backend, recorder, kinds=None): ...
def tags(backend, recorder, id=None): ...
def obstacles(backend, recorder): ...
```

Freie Funktionen mit `(backend, recorder, …)` — das Muster von
`api/navigation.py`. `api/spot.py` bekommt drei dünne Methoden darüber.

`tags(id=…)` filtert auf eine Nummer. Ohne `id` zählt jeder Tag, **der nächste
gewinnt** bei gleicher Auswertung. Die Liste ist nach Distanz sortiert, damit
`spot.tags()[0]` ohne Nachdenken das nächste Ziel ist.

Jeder Aufruf schreibt über `recorder.event()` eine Zeile: Anzahl Treffer, IDs,
Distanzen. Kein Treffer wird ebenfalls geschrieben — „vier Sekunden lang nichts
gesehen" ist eine Information, die man nachher braucht.

### 4.3 `beobachtung/gitter.py` — der Gitter-Mitschnitt

Umzug von `matura-spot: spotsim/gitter_mitschnitt.py` (232 Z.), unverändert in
Substanz. Er spiegelt bereits `beobachtung/bilder.py`: eigener Thread, `start`,
`stop`, `zaehler()`, Indexblatt, wirft nie nach aussen.

Zwei Entscheidungen des Originals werden ausdrücklich übernommen:

- **Gespeichert wird die serialisierte `LocalGridResponse`, kein Eigenformat.**
  Damit dekodiert jeder Verbraucher identisch — GUI, Replay und Simulation
  können nicht auseinanderlaufen. Ein paar Kilobyte je Abtastung sind dafür
  kein Preis.
- **Fehler werden gezählt, nicht geworfen.** Ein Mitschnitt, der still nichts
  aufnimmt, fällt sonst erst auf, wenn der Roboter weg ist.

`ObstacleGrid` in `api/world.py` ist die dekodierte Sicht darauf:

```python
@dataclass
class ObstacleGrid:
    cells: "np.ndarray"   # Abstand zum nächsten Hindernis je Zelle, Meter
    cell_size: float
    origin: tuple
    time: float
    def distance_at(self, x, y): ...
    def is_free(self, x, y, margin=0.3): ...
```

### 4.4 `backends/real/wahrnehmung.py` — der Protokollteil

`WorldObjectClient.list_world_objects()` und `LocalGridClient.get_local_grids()`,
plus `frame_helpers.get_a_tform_b` für die Transformationen. Übersetzt
Protobufs in die Datenklassen aus 4.1 und sonst nichts.

**Beide Dienste sind reine Lesedienste.** Kein Lease, kein Kommando, keine
Möglichkeit, den Roboter zu bewegen.

### 4.5 Attrappen in `dryrun.py` und `sim.py`

Ohne sie sind Ansicht und Sonde nicht testbar. `dryrun` liefert einen festen,
plausiblen Satz: zwei Tags in bekannter Entfernung, ein Dock, ein Gitter mit
einer Wand. Deterministisch, damit Tests darauf zusicherbar sind.

### 4.6 Die Sonde

Ein eingebautes Skript, gestartet über den **vorhandenen**
`workshop/launcher.py` — die GUI startet Skripte ohnehin so, es entsteht kein
neuer Mechanismus.

1. verbindet lesend, **ohne Lease**
2. ruft 5 s lang mit 2 Hz `world_objects()` und `obstacles()`
3. schreibt ein normales Lauf-Verzeichnis und endet
4. die Ansicht zeigt es an — derselbe Anzeigeweg wie bei jedem Lauf

Die Sonde benutzt ausschliesslich die neue API und ist damit zugleich deren
Abnahme: taugt sie nicht für die Sonde, taugt sie nicht für Schüler.

**Die Leaselosigkeit wird als Test erzwungen**, nicht als Kommentar behauptet:
ein Gate prüft, dass das Sondenmodul keine Bewegungsfunktion importiert. Das
ist dasselbe Mittel, mit dem `matura-spot` erzwingt, dass `explorer.py` nichts
von gRPC weiss — eine Naht ist erst eine Naht, wenn sie reisst, sobald jemand
durchgreift.

### 4.7 Ansicht „Umwelt"

Siebte Ansicht, neben `live.py` und `maps.py`. **Importiert kein bosdyn.**

- **links** eine Liste des zuletzt Gesehenen: Art, ID, Peilung, Distanz, Alter
  der Beobachtung
- **rechts** eine Draufsicht: Hindernisgitter als Graustufen, Objekte als
  Marker, Spot in der Mitte
- **oben** der Knopf „Umgebung abfragen" (4.6)

Für die Draufsicht wird `gui/mapplot.py` (Stufe 4) nachgenutzt, nicht
verdoppelt.

**Das Alter jeder Beobachtung wird angezeigt.** Eine Objektliste ohne Alter
suggeriert Gegenwart; wenn der letzte Lauf zehn Minuten her ist, muss das
sichtbar sein.

### 4.8 Diagnose-Erweiterung

`workshop/doctor.py` hat heute: Konfiguration, Netz, Anmeldung, Zeitsync,
Not-Aus, Lease, Akku, Zustandsstrom. Dazu:

| Zeile | Quelle | beantwortet |
|---|---|---|
| **Lizenz** | `LicenseClient.get_license_info()` | `licensed_features` — autoritativ statt geraten. Plus `not_valid_after`. |
| **Nutzlasten** | `PayloadClient.list_payloads()` | GPS? Lidar? Ein für alle Mal. |
| **Zertifikat** | Portierung von `matura-spot: scripts/zertifikat_pruefen.py` | Gültig bis wann — **bevor** es zubeisst. |
| **Dienste** | `robot.list_services()` | Vollständig, statt zu einer Zeile destilliert. |

Die Zustandsstrom-Zeile bleibt, aber ihre Rolle ändert sich: sie ist die
**unabhängige Gegenprobe**. „Lizenziert, aber Dienst läuft nicht" ist ein
anderes Problem als „nicht lizenziert", und nur wer beides fragt, kann sie
unterscheiden.

Die Zertifikatszeile holt das Zertifikat **ungeprüft** ab und braucht kein
openssl. Sie funktioniert deshalb gerade dann, wenn die normale Verbindung
schon scheitert — genau dort will man sie haben. Anlass ist der Vorfall vom
02.09.2026 (siehe 10).

`gui/views/checkup.py` (125 Z.) wächst um einen aufklappbaren Abschnitt
„Gerät", **als Text kopierbar** — damit die Angaben ohne Abtippen an Schule
oder BD-Support gehen können.

---

## 5 Datenfluss

**Abfrage durch ein Skript:**

```
spot.tags(id=1)
  → api/world.tags()
  → backend.world_objects(kinds=["apriltag"])
  → WorldObjectClient.list_world_objects()
  → frame_helpers: body_tform_fiducial
  → Tag(id=1, bearing=-23.4, distance=2.7, …)
  → recorder.event("tags", treffer=1, ids=[1], distanzen=[2.7])
       → zustand.jsonl
```

**Gitter während einer Fahrt:**

```
Gittermitschnitt (eigener Thread, 2 Hz)
  → LocalGridClient.get_local_grids(["obstacle_distance"])
  → gitter/0001.pb  +  Zeile in gitter/gitter.jsonl
```

**Anzeige:**

```
gui/views/umwelt.py
  → liest zustand.jsonl  (Objekte)
  → liest gitter/*.pb    (Karte)
  → mapplot
```

Die GUI berührt zu keinem Zeitpunkt den Roboter.

---

## 6 Fehlerbehandlung

| Lage | Verhalten |
|---|---|
| Kein Objekt sichtbar | `[]`, keine Meldung. Das ist der Normalfall. |
| `WorldObjectClient` nicht erreichbar | Deutsche Meldung über `errors/translate.py`, `[]` zurück. Ein Wahrnehmungsausfall darf ein Schülerskript nicht abbrechen. |
| Transformation fehlt (`get_a_tform_b` → None) | Objekt wird übersprungen, nicht mit Distanz 0 geliefert. Eine falsche Zahl ist schlimmer als eine fehlende. |
| LocalGrid-Dienst antwortet nicht | Mitschnitt zählt den Fehler, läuft weiter, `zaehler()` macht es sichtbar. |
| Sonde ohne Roboter gestartet | Normale Verbindungsdiagnose, Lauf endet mit Fehlerstatus. |
| Lizenz-/Nutzlast-Abfrage schlägt fehl | Diagnose-Zeile „nicht ermittelbar" mit `ok=True` — ein fehlender Befund ist kein Defekt, ein rotes Kreuz wäre eine Falschaussage. Dieselbe Regel wie bei der Zustandsstrom-Zeile. |

---

## 7 Prüfung

TDD. Alle Tests laufen **ohne Roboter**.

- `test_world.py` — Datenklassen, Grad-Umrechnung, Vorzeichen (links positiv),
  Sortierung nach Distanz, `id`-Filter, leer → `[]`, `filtered` korrekt gesetzt,
  fehlende Transformation überspringt statt zu nullen
- `test_gitter.py` — zieht mit dem Modul um; Ablage, Index, Wiedereinlesen,
  Fehlerzählung
- `test_sonde.py` — **das Gate**: das Sondenmodul importiert keine
  Bewegungsfunktion
- `test_doctor.py` — Lizenz, Nutzlasten, Zertifikat, Dienste gegen Attrappen;
  insbesondere „Abfrage schlägt fehl" → `ok=True`
- `test_umwelt_view.py` — Ansicht gegen ein vorbereitetes Lauf-Verzeichnis;
  Zusicherung, dass das Modul **kein bosdyn importiert**

Regression in `matura-spot`: dessen **212 Tests** laufen vor und nach der
Umstellung. `test_explorer_naht.py` muss grün bleiben.

---

## 8 Abnahme am Gerät

- **A21 — Sonde ist leaselos.** Die Sonde läuft, während das Tablet das Lease
  hält, ohne es zu stören. Erst danach gilt die Leaselosigkeit als belegt und
  nicht nur als getestet.
- **A22 — Tag-Erkennungsreichweite.** Am Gerät messen. Die Sim rechnet mit
  ~12 m, real werden ~2–3 m erwartet. Das ist eine Versuchsbedingung der
  Maturaarbeit und gehört protokolliert.

---

## 9 Nicht-Ziele

- **Raycast.** SDK-Client vorhanden, setzt aber eine geladene GraphNav-Karte
  voraus. Zurückgestellt, bis ein Anwendungsfall existiert.
- **GPS.** Setzt eine GPS-Nutzlast voraus. Ob dieser Roboter eine hat, klärt
  4.8; vorher wird dafür nichts gebaut.
- **Punktwolken.** Brauchen eine Lidar-Nutzlast. Gleiche Begründung.
- **Objekterkennung mit neuronalen Netzen.** Der `WorldObjectClient` liefert,
  was Spots Firmware erkennt. Eigene Erkennung ist ein anderes Projekt.
- **Live-Verbindung aus dem GUI-Prozess.** Bewusst verworfen, siehe 2.

---

## 10 Offene Annahmen

- **Der Zertifikatsvorfall vom 02.09.2026 ist unerklärt.** Der Roboter lieferte
  ein Zertifikat mit `notAfter = 2026-03-10` aus, obwohl er monatelang
  störungsfrei lief; ein Neustart behob es. Warum es an diesem Tag auftrat, ist
  offen. Die Diagnosezeile in 4.8 macht den Zustand künftig sichtbar, erklärt
  ihn aber nicht. Aufgehoben: `matura-spot: spot_zertifikat_vor_neustart.pem`.
- **Erkennungsreichweite der Fiducials** ist geschätzt, nicht gemessen — A22.
- **`world_object`-Typen ausserhalb von AprilTag und Dock** sind ungetestet an
  diesem Gerät. Die Schicht behandelt sie generisch; ob Spot sie überhaupt
  meldet, zeigt der erste Lauf.
- **Rate des Gitter-Mitschnitts über WLAN** ist mit 2 Hz angesetzt, in Anlehnung
  an A18 (Rate über WLAN, am Gerät zu messen).

---

## 11 Abhängigkeiten

- **Voraus:** Fundament (1+2), GUI (3), GraphNav (4) für `mapplot.py`,
  Beobachtung (8) für das Ablagemuster und den Ort von `gitter.py`.
- **Neu im SDK genutzt:** `world_object`, `local_grid`, `license`, `payload`.
  Alle in bosdyn-client 5.0.1.2 vorhanden, keine neue Paketabhängigkeit.
- **Nachgelagert:** `matura-spot` wird Klient — **als letzter Schritt und nur
  bei grüner Lage**. Geht die Zeit aus, ist spotlab fertig und `matura-spot`
  unberührt lauffähig.

### Reihenfolge

1. Wahrnehmungs-Schicht + Attrappen (4.1, 4.2, 4.4, 4.5)
2. Sonde + Umwelt-Ansicht (4.6, 4.7) — das Werkzeug für den nächsten Messtag
3. Diagnose (4.8)
4. `matura-spot`-Umstellung: `detect_target()` → Adapter über `spot.tags()`,
   `gitter_mitschnitt.py` → Import aus spotlab
