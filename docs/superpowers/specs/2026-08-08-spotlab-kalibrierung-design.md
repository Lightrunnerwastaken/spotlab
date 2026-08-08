# spotlab Kalibrier-Infrastruktur — den echten Spot so messen, dass der Sim daran geeicht werden kann

**Datum:** 2026-08-08
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 7. Setzt Fundament (1+2), GUI (3), GraphNav (4), Editor (5) und die
Anbindung (6) voraus. **spotlab bekommt keinen Simulator** — siehe K6.

---

## 1 Zweck

`matura-spot` hat einen Sim, der neun Realismus-Gates besteht. Geeicht ist er am
menschlichen Auge. Diese Stufe baut die Gegenseite: **Messungen am echten Spot in einer
Form, gegen die man den Sim rechnen kann.**

Das Ziel ist ausdrücklich **nicht** ein perfekter Sim, sondern eine belastbare Differenz —
je Gate, je Stützstelle, mit benannter Unsicherheit.

### Vorgefundener Stand — drei Befunde

**1. Ohne Joint-Control-Lizenz ist sehr viel verfügbar.** `RobotStateClient.get_robot_state()`
liefert pro Abruf:

| Feld | Inhalt |
|---|---|
| `kinematic_state.joint_states[12]` | Name, Position, Geschwindigkeit, **Beschleunigung**, **`load` (Nm)** |
| `kinematic_state.acquisition_timestamp` | Zeitstempel **aus der Roboteruhr** |
| `kinematic_state.transforms_snapshot` | odom, vision, body, flat_body, **gpe**, feet_center |
| `kinematic_state.velocity_of_body_in_odom` / `_in_vision` | zwei unabhängige Geschwindigkeitsquellen |
| `foot_state[4].foot_position_rt_body`, `.contact` | Fussgeometrie und Kontakt |
| `foot_state[4].terrain` | **`ground_mu_est`**, `foot_slip_distance_rt_frame`, `foot_slip_velocity_rt_frame`, `ground_contact_normal_rt_frame`, `visual_surface_ground_penetration_mean/std` |
| `battery_states[]` | Ladung, Spannung, Strom, Temperaturen |
| `system_state.motor_temperatures[]` | je Motor |
| `behavior_state` | STANDING / STEPPING / TRANSITION |

Ein geschätzter Reibwert **je Fuss** und ein Drehmoment **je Gelenk** sind Grössen, die man
sonst aufwendig schätzt.

**2. Die Lizenz kostet den Zustandsstrom.** `robot-state-streaming` (333 Hz,
`CombinedJointStates` + **rohes `ImuState`**) taucht in der gesamten SDK nur in den
`joint_control`-Beispielen auf und steht im README der lizenzpflichtigen Joint-Control-API
als deren Bestandteil. Dasselbe README sagt, man solle den vollen `RobotState` „at a lower
rate" vom regulären Dienst holen — der unäre Dienst ist also der langsamere, aber
vollständigere. **Ob `robot-state-streaming` auf einem unlizenzierten Spot registriert ist,
ist ungeprüft** und wird als Doktor-Zeile beantwortet, nicht als Annahme.

**3. Der Messplan existiert bereits — in `matura-spot`.** `src/spotsim/gates.py` führt neun
`GateSpec` mit je einem Feld `real_procedure`: eine ausformulierte Anleitung, was am echten
Spot zu tun und zu messen ist, plus eine benannte **unbestätigte Annahme**.
`tests/test_gates.py::test_katalog_vollstaendig` lässt kein Gate ohne beides zu. Das
Sim-Protokoll (`out/gates/<lauf-id>/protokoll.json`) hat je Gate die Felder
`id, titel, bestanden, ergebnis, faehigkeit, messgroesse, schranke, annahme, real_prozedur,
messwerte, dauer_s`.

### Was die heutige Abtastung nicht kann

`api/state.py::as_sample` schreibt bereits Pose, Geschwindigkeit, **Gelenke mit Drehmoment**,
Fusskontakte und Akku. Drei Lücken machen die Gates trotzdem unmessbar:

1. **Keine Körperhöhe.** `pose` ist `(x, y, yaw)`. G1 misst „Höhe 0.38–0.52 m, Absacken
   ≤ 0.3 cm" — heute nicht auswertbar.
2. **Kein Roll und Pitch.** G1 fordert „Neigung ≤ 2°", G3 „Roll/Pitch ≤ 12°".
3. **Der Zeitstempel ist die Empfangszeit**, nicht `acquisition_timestamp`. Damit steckt die
   WLAN-Latenz samt Jitter in jeder Ableitung — und Kalibrierung besteht aus Ableitungen.

### Gemessen, nicht geschätzt: der Rekorder trägt

`RunRecorder._zeile` öffnet die Datei je Zeile und ruft `os.fsync()`. Der Verdacht, das
begrenze die Rate, **wurde gemessen und ist falsch**:

| | ms je Abtastung | Obergrenze | Bytes je Abtastung |
|---|---|---|---|
| heutiger Umfang | 2.82 | 354 Hz | 144 |
| mit Gelenken und Fuss-Terrain | 2.91 | 344 Hz | 1321 |
| dieselbe Zeile gepuffert (Vergleich) | 0.05 | 22 000 Hz | — |

Die Platte ist nicht die Engstelle. Die RPC über WLAN ist es, und die lässt sich ohne
Roboter nicht messen (→ A18). Ein reicher Satz ist aber **rund neunmal so gross**.

---

## 2 Entschiedene Grundsatzfragen

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| K1 | Reicher Logger oder Gate-Zwilling | **Gate-Zwilling.** Die neun Gates werden am echten Spot gefahren; reiches Logging ist Mittel, nicht Zweck. | Ein Logger ohne Messplan produziert Stunden Daten, aus denen man hinterher nicht sagen kann, **unter welcher Bedingung** sie entstanden — und Kalibrierung ist nichts anderes als „gleiche Bedingung, zwei Systeme, Differenz". Der Gate-Katalog hat diese Bedingungen schon präzise: Warmlaufzeit, Messfenster, Stützstellen, Kriterium — und nennt je Gate die Annahme, die die Messung beantworten soll. |
| K2 | Wer die Gates ausführt | **Ein Skript in `matura-spot`, das spotlab importiert.** spotlab liefert Infrastruktur, keine Gate-Logik. | spotlab darf nicht von `matura-spot` abhängen — deshalb sind es zwei Repos. Die Gegenrichtung ist seit Stufe 6 eingerichtet: `matura-spot` ist ein angebundenes Projekt, seine Skripte sind Knöpfe im Fenster, `roboter = true` erzwingt einen Menschen. Und die Gate-Kriterien sind Forschungsentscheidungen mit benannten Annahmen; sie gehören dorthin, wo das RESEARCH-DECISION-Protokoll gilt. |
| K3 | Gates als Daten statt als Code | **Nein.** | Die Prozeduren sind keine Daten: G6 ist ein physischer Stoss, G2 braucht 20 s Warmlauf für eine EMA, G5 misst einen Bremsweg nach dem Stoppbefehl, G7 lässt ein Kommando absichtlich ablaufen. Das deklarativ zu fassen hiesse, eine Prozedursprache zu erfinden — und das erste Gate, das nicht hineinpasst, bricht sie. |
| K4 | Wann dicht und reich geloggt wird | **Das Messfenster hebt Rate und Umfang.** Ausserhalb bleibt es bei 10 Hz und schlank. | Netzlast: der Sampler pollt über WLAN, und 50 Hz hiessen 50 RPCs pro Sekunde in **jedem** Schülerlauf, auf einem Netz, an dem das Tablet hängt. Und ein Regler statt zwei: das Fenster markiert ohnehin den Bereich, in dem Genauigkeit zählt. Ein Modus für den ganzen Lauf verlangt, vorher daran zu denken — und der Fall, in dem man es vergisst, ist der teure: eine Messfahrt, die man nicht wiederholen kann, weil der Spot-Termin vorbei ist. |
| K5 | Was spotlab am Ende ausgibt | **`messfenster.json` mit Kennzahlen je Fenster — nicht das Gate-Protokoll.** | Die Felder `schranke`, `annahme` und `real_prozedur` stehen im Gate-Katalog. spotlab kann sie nicht kennen, ohne die Abhängigkeitsrichtung umzudrehen. spotlab liefert `messwerte`, `matura-spot` legt seine Kriterien darüber. |
| K6 | MuJoCo behalten? | **Ja — und spotlab bekommt gar keinen Simulator.** | Der Sim besteht neun Gates mit dem Menagerie-Modell; ihn zu ersetzen wirft eine funktionierende Referenz weg und bringt der Kalibrierung nichts. Ein zweiter Sim in spotlab wäre die Abspaltung, wegen der die Repos getrennt sind. MuJoCo legt die Stellschrauben als schlichte Arrays offen (`geom_friction`, `solref`/`solimp`, `dof_damping`, `dof_armature`, Aktuator-Gains). **Drake wäre für strenge Systemidentifikation das bessere Werkzeug**, aber Modell, Gangerzeugung und neun Gates dort neu zu bauen steht in keinem Verhältnis. Isaac Sim will eine NVIDIA-GPU, Gazebo zieht ROS nach, Genesis ist zu jung. |
| K7 | Zustandsstrom mit 333 Hz | **Melden, nicht benutzen.** | Er hat eine andere Nachrichtenform — Gelenke nach Index statt nach Namen, IMU in Paketen — und wäre ein zweiter Datenpfad. Erst wissen, ob es ihn auf diesem Roboter gibt; dann entscheiden, ob er die Verdopplung wert ist. |

---

## 3 Architektur

```
matura-spot     scripts/gates_real.py        fährt G1–G9 am echten Spot
                scripts/vergleich_real_sim.py   Protokoll gegen Protokoll
   │  importiert spotlab
   ▼
spotlab   api/spot.py::messfenster           Marken + Ratenumschaltung
          api/state.py                       reichere Abtastung
          record/sampler.py                  Rate und Umfang zur Laufzeit
          record/events.py                   neue Ereignisart
          messung/fenster.py        NEU      Kennzahlen je Fenster (Qt-frei, SDK-frei)
          mcp/werkzeuge.py                   Lückenmelder wird abschnittsweise
          workshop/doctor.py                 Zeile „Zustandsstrom"
```

`messung/` importiert **nichts** aus `api/`, `backends/`, `gui/` und kein `bosdyn`: es liest
eine Aufzeichnung von der Platte und rechnet. Dieselbe Regel wie `anbindung/`; `spotlab.errors`
ist erlaubt.

### Das Format von `zustand.jsonl`

Der Umschlag bleibt deutsch (`t`, `art`, `daten`), die Nutzdaten bleiben englisch
(`battery`, `pose`, `velocity`, `joints`, `feet`) — **so ist es heute, und Konsistenz
innerhalb der Datei wiegt schwerer als eine Regel, die die Datei bereits bricht.** Neue
Schlüssel folgen den Nutzdaten, also englisch.

**Bestehende Schlüssel ändern sich nicht.** `pose` bleibt `(x, y, yaw)`, `feet` bleibt eine
Liste von vier Wahrheitswerten — `gui/views/live.py` liest genau das, und alte
Aufzeichnungen bleiben lesbar.

**Immer geschrieben** (vier Zahlen, vernachlässigbar, und sie beheben G1):

```json
"t_robot": 1786293840.123,   // acquisition_timestamp in Sekunden, ROHE Roboteruhr
"z": 0.419,                  // Körperhöhe über odom
"roll": 0.008, "pitch": -0.014
```

**`t_robot` wird nicht in die Klientenzeit umgerechnet.** Die SDK könnte das über
`robot.time_sync`, aber für die Kalibrierung zählen Abstände **innerhalb** eines Laufs, und
die sind in der rohen Roboteruhr am saubersten — eine Umrechnung schöbe die Unsicherheit der
Zeitsynchronisierung in jede Ableitung. Der Umschlag-Zeitstempel `t` bleibt unverändert die
Empfangszeit seit Laufbeginn; damit stehen beide Uhren nebeneinander und die Latenz ist
sichtbar statt versteckt.

**Nur im Messfenster** (der teure Teil):

```json
"joint_acc": {"fl.hx": 0.31, ...},
"velocity_vision": [vx, vy, wz],
"behavior": "STEPPING",
"feet_detail": [
  {"pos": [0.33, 0.17, -0.42], "kontakt": true, "mu": 0.62,
   "slip_weg": [0.001, 0.0, 0.0], "slip_tempo": [0.01, 0.0, 0.0],
   "normal": [0.0, 0.02, 1.0], "durchdringung": 0.004},
  ...
],
"battery_detail": {"spannung": 56.2, "strom": -12.4, "temperaturen": [31.0, 32.5]},
"motor_temps": {"fl.hx": 42.0, ...}
```

`feet` und `feet_detail` stehen nebeneinander. Das ist bewusst redundant: die schlanke
Fassung hält die Live-Ansicht und die alten Läufe am Laufen, die reiche trägt die
Kalibrierung.

---

## 4 Komponenten

### 4.1 `api/state.py` — reichere Abtastung

```python
@dataclass(frozen=True)
class JointState:
    position: float
    velocity: float
    load: float
    acceleration: float = 0.0

@dataclass(frozen=True)
class FootDetail:
    pos: tuple
    kontakt: bool
    mu: float
    slip_weg: tuple
    slip_tempo: tuple
    normal: tuple
    durchdringung: float

@dataclass(frozen=True)
class State:
    battery: float
    powered: bool
    pose: tuple          # (x, y, yaw) — unverändert
    z: float             # NEU
    roll: float          # NEU
    pitch: float         # NEU
    t_robot: float       # NEU, acquisition_timestamp; 0.0 wenn nicht gesetzt
    velocity: tuple
    velocity_vision: tuple
    joints: dict
    feet: tuple
    feet_detail: tuple
    behavior: str
    battery_detail: dict
    motor_temps: dict

def rpy_aus(quaternion) -> tuple      # (roll, pitch, yaw)
def from_proto(zustand) -> State
def as_sample(zustand, reich=False) -> dict
```

`rpy_aus` ersetzt `_yaw_aus` und liefert alle drei Winkel; die Yaw-Formel bleibt
bitgleich, damit bestehende Tests und Aufzeichnungen dieselben Werte sehen.

**Jedes Feld einzeln abgesichert.** `from_proto` fängt heute schon einen unvollständigen
Frame-Schnappschuss ab. Dasselbe gilt für alle neuen Felder: fehlt `terrain`, ist
`feet_detail` leer, nicht null-gefüllt — **ein erfundener Reibwert 0.0 wäre schlimmer als
gar keiner**, weil er sich durch jede Auswertung mittelt.

### 4.2 `record/sampler.py` — Rate und Umfang zur Laufzeit

```python
class StateSampler:
    def __init__(self, backend, recorder, hz=10.0)
    def setze_takt(self, hz, reich)        # thread-sicher, wirkt ab dem nächsten Tick
    def takt(self) -> tuple                # (hz_soll, reich)
```

Die Schleife liest Takt und Umfang bei jedem Durchlauf. **Nichts wird nachgeholt:** dauert
die RPC länger als die Periode, schläft die Schleife eben nicht — sonst entstünden Bursts,
die in der Auswertung wie echte Dynamik aussehen.

Die bestehende zweite Aufgabe des Samplers — die `stopp`-Markierung prüfen und
`KeyboardInterrupt` im Hauptthread auslösen — bleibt unverändert und wird bei jedem Tick
geprüft, also im Messfenster sogar häufiger.

### 4.3 `api/spot.py::messfenster` und die neue Ereignisart

```python
@contextlib.contextmanager
def messfenster(self, name, hz=50.0, **felder):
    """Markiert ein Messfenster und tastet darin dicht und vollständig ab."""
```

```python
with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
    spot.walk(vx=0.30, duration=8.0)
```

Schreibt beim Betreten `event("messfenster", phase="start", name=…, hz_soll=…, **felder)`,
stellt den Abtaster um, und beim Verlassen `phase="ende"` — **auch wenn der Block eine
Ausnahme wirft** (`try/finally`), sonst bliebe der Lauf für immer auf 50 Hz und das Fenster
ohne Ende.

`record/events.py::ARTEN` bekommt `"messfenster"` dazu; `event()` weist unbekannte Arten ab.

`connect()` reicht den Abtaster an den `Spot` durch. Ohne Abtaster (etwa in einem Test, der
`Spot` direkt baut) schreibt `messfenster` nur die Marken und ändert nichts — es darf nie
scheitern.

### 4.4 `messung/fenster.py` — Kennzahlen je Fenster

```python
@dataclass(frozen=True)
class Fenster:
    name: str
    felder: dict
    von_s: float
    bis_s: float
    hz_soll: float
    hz_ist: float
    abtastungen: int
    reich: bool
    kommandos: list
    messwerte: dict

def fenster(lauf_dir) -> list[Fenster]
def als_json(liste) -> dict
def schreibe(lauf_dir) -> Path        # <lauf>/messfenster.json
```

Die Kennzahlen, alle aus den Gate-Messgrössen abgeleitet:

| Schlüssel | Bedeutung |
|---|---|
| `dauer_s`, `abtastungen`, `hz_ist`, `luecken` | Messgüte zuerst |
| `zeitquelle` | `"robot"` oder `"empfang"` — worauf alle Zeitgrössen beruhen |
| `hoehe_mittel`, `hoehe_min`, `hoehe_max`, `hoehe_drift` | G1 |
| `roll_max_grad`, `pitch_max_grad` | G1, G3 |
| `tempo_x_mittel`, `tempo_y_mittel`, `drehrate_mittel`, `tempo_max` | G2, G3, G4 |
| `strecke_m`, `netto_versatz_m`, `gierwinkel_grad` | G2, G4 |
| `kommandiert` (aus den Ereignissen), `tracking_prozent` | G2, G3, G4 |
| `gelenk_rate_max`, `gelenk_last_max`, je Gelenk dasselbe | G1 („Gelenke in Ruhe"), Aktuatormodell |
| `fuss_duty[4]`, `schrittfrequenz_hz` | Gangphase |
| `mu_mittel`, `schlupf_weg_m` | Reibung, und die offene G3-Frage |

`hz_ist` ist `(abtastungen - 1) / dauer_s` über die Zeitstempel der ersten und letzten
Abtastung **im** Fenster — nicht über die Fenstermarken, deren Abstand die Wartezeit auf den
ersten Tick mitzählt.

**`gierwinkel_grad` wird fortlaufend aufsummiert**, nicht als Differenz von Anfang und Ende —
G4 verlangt das ausdrücklich, weil eine Drehung über 180° sonst das Vorzeichen wechselt.

**`tracking_prozent`** entsteht aus den `kommando`-Ereignissen im selben Zeitbereich:
`motion.walk` schreibt bereits `event("kommando", name="walk", vx=…, vy=…, wz=…)`. Sind im
Fenster mehrere widersprüchliche Kommandos, bleibt `kommandiert` leer und
`tracking_prozent` ist `None` — **lieber keine Zahl als eine über zwei Bedingungen
gemittelte.**

**Was in einem schlank aufgezeichneten Fenster nicht ableitbar ist, ist `None`, nicht 0.**
Der Unterschied zwischen „gemessen und null" und „nicht gemessen" entscheidet, ob eine
Kalibrierung gültig ist.

### 4.5 Der Lückenmelder wird abschnittsweise

`mcp/werkzeuge.py::zustand_zusammenfassen` vergleicht heute gegen feste
`LUECKE_AB_S = 0.2`. Mit Fenstern bei 50 Hz und 10 Hz ausserhalb wäre **jeder Ratenwechsel
eine Falschmeldung** — und ein Alarm, der bei jeder Messfahrt kommt, wird ignoriert.

Künftig liest es die `messfenster`-Ereignisse, baut daraus Abschnitte mit ihrem `hz_soll`
und misst je Abschnitt gegen `2 / hz_soll`. Ausserhalb aller Fenster bleibt es bei 10 Hz.
Die Antwort nennt zusätzlich `abschnitte` mit je Soll- und Ist-Rate.

### 4.6 `workshop/doctor.py` — eine Zeile „Zustandsstrom"

Eine neue Stufe nach „Zeitsync": ist der Dienst `robot-state-streaming` auf diesem Roboter
registriert? Die Zeile **benutzt ihn nicht**, sie beantwortet nur die offene Frage aus K7 —
und zwar dort, wo man ohnehin hinschaut, bevor man misst.

Ist er nicht da, ist das **kein Fehler**, sondern ein Hinweis: „Der 333-Hz-Zustandsstrom
braucht die Joint-Control-Lizenz. Ohne ihn liefert `RobotState` alles ausser rohem IMU."

### 4.7 `backends/dryrun.py` — plausible Werte für die neuen Felder

Der Trockenlauf muss die neuen Felder plausibel füllen (Höhe um 0.42 m, Reibwert um 0.6,
Kontakte im Gangtakt), sonst lässt sich die ganze Kette — Messfahrt, Fensterauswertung,
Vergleich — ohne Roboter nicht üben, und die erste echte Messfahrt wäre zugleich der erste
Test. **Es sind erfundene Zahlen, und die Aufzeichnung sagt das:** `backend: "dryrun"` steht
in `lauf.json`, und die Fensterauswertung reicht es nach `messfenster.json` durch.

### 4.8 Was `matura-spot` beisteuert

Kein Teil dieser Spec, aber der Zweck des Ganzen: `scripts/gates_real.py` fährt die
`real_procedure` je Gate mit `spot.messfenster(...)`, und `vergleich_real_sim.py` legt
`messfenster.json` gegen `protokoll.json`. Beides gehört in das Repo, in dem die
Gate-Kriterien und das RESEARCH-DECISION-Protokoll leben.

---

## 5 Datenfluss

```
gates_real.py (matura-spot)
   with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
       spot.walk(vx=0.30, duration=8.0)
          │
          ├─ event("messfenster", phase="start", …)  → ereignisse.jsonl
          ├─ sampler.setze_takt(50, reich=True)
          ├─ event("kommando", name="walk", vx=0.30) → ereignisse.jsonl
          ├─ 50 Hz × as_sample(reich=True)           → zustand.jsonl
          └─ event("messfenster", phase="ende", …)   → ereignisse.jsonl
                     │
messung/fenster.py::schreibe(lauf)  →  <lauf>/messfenster.json
                     │
vergleich_real_sim.py (matura-spot)  →  real gegen Sim, je Gate
```

---

## 6 Fehlerbehandlung

| Lage | Verhalten |
|---|---|
| `acquisition_timestamp` nicht gesetzt | `t_robot = 0.0`; die Fensterauswertung fällt auf `t` zurück **und vermerkt das in `messwerte["zeitquelle"]`** |
| `terrain` fehlt (Fuss ohne Kontakt) | Eintrag ohne `mu`/`slip`, nicht mit Nullen |
| Frame-Schnappschuss unvollständig | wie heute: Pose bleibt Ursprung, `z`/`roll`/`pitch` bleiben 0.0 |
| Ausnahme im Messfenster | `finally` schreibt das Ende-Ereignis und stellt den Takt zurück |
| Verschachtelte Messfenster | verboten; der zweite wirft `SpotlabError` mit dem Namen des offenen |
| Fenster ohne Ende (Prozess gestorben) | Auswertung nimmt die letzte Abtastung als Ende und setzt `unvollstaendig: true` |
| Fenster ohne Abtastungen | `messwerte` leer, `abtastungen: 0` — kein Absturz |
| Schlank aufgezeichnet, reiche Kennzahl angefragt | `None`, nie 0 |
| Widersprüchliche Kommandos im Fenster | `kommandiert` leer, `tracking_prozent: None` |
| Kein Zustandsstrom | Doktor-Hinweis, kein Fehler |

---

## 7 Prüfung

**Qt-frei und SDK-frei** — `messung/fenster.py` gegen synthetische Aufzeichnungen:
Fenster werden aus Ereignissen erkannt; Kennzahlen stimmen gegen von Hand gerechnete Werte;
**`gierwinkel_grad` summiert über 180° hinaus korrekt auf**; `tracking_prozent` aus
Kommando plus Abtastungen; widersprüchliche Kommandos ergeben `None`; schlanke Fenster
ergeben `None` statt 0; ein Fenster ohne Ende wird als `unvollstaendig` gemeldet; ein
Schichttest wie bei `anbindung/`.

**Gegen echte Protobufs** — `as_sample`: ein von Hand gebauter
`robot_state_pb2.RobotState` mit allen Feldern (Gelenke inkl. `acceleration`, `foot_state`
mit `terrain`, `behavior_state`, Batterie, Motortemperaturen, `acquisition_timestamp`) läuft
durch `from_proto` und `as_sample`; jedes neue Feld wird geprüft. Ein zweiter Protobuf
**ohne** `terrain` und **ohne** `acquisition_timestamp` beweist die Ausfallwege. Das ist die
Hausmethode aus `matura-spot/tests/test_sdk_commands.py`.

**Rückwärtskompatibilität als Test:** `as_sample(reich=False)` enthält exakt die heutigen
Schlüssel plus `t_robot`, `z`, `roll`, `pitch` — und `pose` hat weiterhin drei Elemente.
Eine alte Aufzeichnung läuft unverändert durch `zustand_zusammenfassen` und die Live-Ansicht.

**Der Abtaster** mit Attrappen-Backend und Attrappen-Uhr: `setze_takt` wirkt ab dem nächsten
Tick; ein langsamer Backend führt **nicht** zu nachgeholten Bursts; die `stopp`-Markierung
wirkt im Messfenster genauso.

**Der Lückenmelder:** eine Aufzeichnung mit einem 50-Hz-Fenster inmitten von 10 Hz meldet
**null Lücken**; eine echte Lücke im Fenster wird gefunden.

**Ende zu Ende im Trockenlauf**, mit echtem Prozess: ein Skript mit zwei Messfenstern läuft
über `start_script`, und `messung/fenster.py` findet beide Fenster mit plausiblen
Kennzahlen. Das ist die Regel, an der „In VS Code öffnen" durch die Suite gerutscht ist.

---

## 8 Abnahme am Gerät

### A18 — Abtastrate und Lücken über WLAN

**Prozedur** Eine Messfahrt mit `hz=50` über 30 s auf ebenem Boden, danach
`zustand_zusammenfassen` und `messfenster.json` ansehen.

**Erwartung** `hz_ist` und die Lückenliste werden **notiert, nicht bestanden oder
durchgefallen**. Diese Zahl entscheidet, ob 50 Hz realistisch sind oder ob die Fenster auf
20 Hz gehen müssen — und sie ist die einzige, die kein Test ohne Roboter liefern kann.

**Zusätzlich notieren:** ob `spotlab doctor` den Zustandsstrom meldet, und ob
`ground_mu_est` von null verschiedene Werte liefert. Ein Reibwert, der konstant 0 bleibt,
hiesse, dass diese Quelle für die Kalibrierung ausfällt — besser vor der Messkampagne
gewusst als danach.

**Ergebnis** _(offen)_

---

## 9 Nicht-Ziele

- **Ein Simulator in spotlab.** Siehe K6.
- **Automatische Parameteranpassung.** Das Fitten gehört zu den Gate-Kriterien, also nach
  `matura-spot`, und ist eine eigene Stufe.
- **Nutzung der lizenzpflichtigen APIs**, bevor die Doktor-Zeile sagt, dass es sie gibt.
- **Änderungen am Gate-Katalog.** Das ist Forschung, nicht Werkzeug.
- **Ein neues Aufzeichnungsformat.** `zustand.jsonl` bleibt jsonl; der Rekorder trägt es
  (gemessen, Abschnitt 1).
- **Kameras und Punktwolken in der Aufzeichnung.** Bilder werden schon einzeln abgelegt;
  Tiefenbilder im Messfenster wären ein Vielfaches der Datenmenge für Fragen, die keines der
  neun Gates stellt.

---

## 10 Annahmen

1. **`robot-state-streaming` ist ohne Lizenz nicht verfügbar.** Begründet, nicht bewiesen:
   der Dienst steht im README der lizenzpflichtigen API als deren Bestandteil und kommt in
   der SDK nur in `joint_control`-Beispielen vor. A18 beantwortet es. Ist er doch da, ändert
   das nichts an dieser Stufe — nur die nächste würde anders aussehen.
2. **Die WLAN-RPC trägt mehr als 10 Hz.** Unbekannt bis A18. Trägt sie nur 15 Hz, bleibt der
   Entwurf gültig; die Fenster laufen dann eben mit 15 statt 50, und `hz_ist` sagt es.
3. **`ground_mu_est` liefert am Schulboden brauchbare Werte.** Das Feld ist dokumentiert,
   aber sein Verhalten auf glattem Hallenboden ist ungeprüft — deshalb steht es in A18.
4. **`matura-spot` läuft in derselben Python-Umgebung wie spotlab.** Wie in Stufe 6; sonst
   bräuchte das Manifest ein Feld `interpreter`.

---

## 11 Abhängigkeiten

**Keine neue.** `messung/` benutzt die Standardbibliothek, `api/state.py` benutzt `bosdyn`
und `math` wie bisher. `numpy` ist bereits Kernabhängigkeit und wird nicht zusätzlich
gebraucht.
