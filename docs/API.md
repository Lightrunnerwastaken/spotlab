# Python-API von spotlab

Stand: 7. September 2026. Die Spot-Fassade bietet **26 Methoden und 4 Properties**.
Diese Referenz beschreibt die lokale Implementierung, nicht sämtliche Funktionen des Boston-Dynamics-SDK.

## Einstieg

```python
from spotlab import connect

with connect(backend="dryrun") as spot:
    state = spot.state
    print(state.battery, state.x, state.y, state.heading, state.speed)
    spot.lights("blue", duration=1)
    spot.beep("C", duration=0.3)
```

`connect(backend=None, runs_dir=None, script=None, take=False, config_path=None,
nickname=None, raum=None)` ist ein Context Manager. Backend-Auswahl: Argument,
`SPOTLAB_BACKEND`, Konfiguration, sonst `dryrun`. Zulässige Betriebsarten sind
`dryrun`, `sim`, `mujoco`, `real`. Für den echten Spot Konfiguration mit `spotlab login`
einrichten. `connect()` schaltet die Motoren nicht ein.
`runs_dir` setzt das Aufzeichnungsziel, `script` die zugehörige Skriptdatei,
`config_path` eine andere Konfiguration, `nickname` den Namen im Lauf,
`raum` den Sim-Raum. `take=True` fordert eine Lease-Übernahme an und gehört nur
in bewusst gestartete Robotersitzungen. Der Context Manager beendet Abtastung,
Roboterverbindung und Aufzeichnung auch bei Ausnahmen.

## Alle Befehle

Zeitwerte sind Sekunden, Strecken Meter. Bewegung im Körperrahmen: x vorwärts,
y links. `move(turn=...)`, `pose(...)`, Tag-Peilungen und `state.heading` verwenden
**Grad**. `walk(wz=...)` verwendet **rad/s**; `state.pose[2]`, `state.roll` und
`state.pitch` bleiben **Radiant**. `schlaf` bei stand/sit ist eine Testfunktion,
normalerweise weglassen.

| Aufruf / Property | Bedeutung |
|---|---|
| `power_on()` | Schaltet die Motoren ein. Spot steht davon noch nicht auf. |
| `power_off(safe=True)` | Schaltet die Motoren ab; mit safe=True setzt Spot sich vorher hin. |
| `is_powered` | True, solange die Motoren eingeschaltet sind. |
| `battery` | Ladestand des Akkus in Prozent. |
| `stand(height=0.0, timeout=10.0, schlaf=None)` | Steht auf. height hebt oder senkt den Körper in Metern. |
| `sit(timeout=10.0, schlaf=None)` | Setzt sich hin. |
| `move(forward=0.0, left=0.0, turn=0.0, timeout=30.0)` | Geht eine feste Strecke in Metern und dreht sich um turn in Grad. |
| `walk(vx=0.0, vy=0.0, wz=0.0, duration=1.0, stop=True, nick_grad=0.0)` | Fährt duration Sekunden lang mit den angegebenen Geschwindigkeiten. `nick_grad` neigt den Körper während der Fahrt (negativ hebt die Nase, die Kameras schauen dann höher); nur am echten Roboter. |
| `stop()` | Hält sofort an. |
| `supports(feature)` | Prueft look, camera, tags, stairs, navigate_to, pose, lights oder beep. |
| `look(max_distance=1.8, margin=0.3, start=0.0)` | Umgebung relativ zu Spot: front/left/right/back mit status, distance und known. |
| `lights(color='blue', duration=2.0, brightness=0.25)` | LEDs fuer duration Sekunden; blockierend, mit anschliessendem Aufraeumen. |
| `beep(note='C', octave=5, duration=0.3)` | Spielt eine Note auf dem Summer; blockiert bis zum Ende (keine WAV-Wiedergabe). |
| `pose(roll=0.0, pitch=0.0, yaw=0.0, height=0.0, timeout=10.0)` | Richtet den Koerper im Stand aus: Winkel in Grad, Hoehenversatz in Metern. |
| `cameras()` | Nennt die Namen der Kameras, die dieser Spot hat. |
| `camera(name)` | Holt ein Bild der genannten Kamera und zeichnet es auf. |
| `depth(name='frontleft')` | Tiefenbild in Metern mit valid-Maske, Kalibrierung und Aufnahmezeit. |
| `point_cloud(name='frontleft', frame='body', stride=2, min_distance=0.0, max_distance=5.0)` | Punktwolke in Metern aus einer Tiefenaufnahme, mit angegebenem Rahmen. |
| `grid_types()` | Nennt die vom Backend angebotenen LocalGrid-Ebenen. |
| `local_grid(name='obstacle_distance')` | Liest eine LocalGrid-Ebene; terrain nutzt auch terrain_valid. |
| `world_objects(kinds=None)` | Nennt alles, was Spot gerade als Objekt führt — nächstes zuerst. |
| `tags(id=None)` | Die sichtbaren AprilTags, nächstes zuerst. Peilung in Grad. |
| `stairs()` | Die Treppen in Sicht, nächste zuerst: Richtung („auf"/„ab"), Stufen, Achse. |
| `obstacles()` | Das Hindernisgitter: wo ist Platz, wo nicht. |
| `state` | Der aktuelle Zustand: Pose, Geschwindigkeit, Füsse, Akku. |
| `load_map(name=None)` | Lädt eine GraphNav-Karte; ohne Namen die aktive aus der Konfiguration. |
| `localize()` | Bestimmt über ein Fiducial, wo Spot auf der geladenen Karte steht. |
| `map_pose()` | Wo Spot auf der geladenen Karte steht: (x, y, grad) im Kartenrahmen. |
| `people()` | Menschen, die Spots Firmware gerade verfolgt (nächste zuerst, Peilung in Grad, Abstand in Metern). Leer heisst: niemand da oder dieser Roboter verfolgt niemanden. |
| `process_map(melde=print, fiducial=True, odometry=True)` | Bearbeitet die geladene Karte nach (Schleifen schliessen, Anker optimieren) und schreibt sie zurück. Braucht das Lease, weil die Karte dafür hochgeladen wird; Spot bewegt sich nicht. |
| `navigate_to(ziel, timeout=120.0, abbruch=None)` | Fährt autonom zum genannten Wegpunkt der geladenen Karte. True bei Ankunft; `abbruch()` wird unterwegs je Nachsende-Takt gefragt — sagt es wahr, hält Spot an und die Antwort ist False. |
| `waypoints()` | Nennt die Wegpunkte der geladenen Karte. |
| `robot` | Das rohe bosdyn-Robot-Objekt (None im Trockenlauf). |
| `send(command, end_time_secs=None)` | Schickt ein rohes RobotCommand-Protobuf an den Roboter. |
| `messfenster(name, hz=50.0, **felder)` | Markiert ein Messfenster und tastet darin dicht und vollständig ab. |
| `close()` | Beendet die Verbindung. connect() ruft das am Ende selbst auf. |

## Rückgaben und Ablauf

- `power_on`, `power_off`, `stand`, `sit`, `move`, `walk`, `stop`, `pose`, `lights`,
  `beep`, `close`: kein Nutzwert (`None`); `navigate_to` gibt True (angekommen) oder
  False (über `abbruch` abgebrochen). `stand`, `sit`, `move`, `pose` und `navigate_to`
  warten auf Rückmeldung bis zum Timeout.
- `walk(stop=True)` wartet die Dauer und stoppt; `stop=False` kehrt sofort zurück,
  benötigt laufende neue Kommandos und begrenzt die Gültigkeit auf höchstens eine Sekunde.
- `is_powered`: bool; `battery`: Prozent; `state`: neue State-Momentaufnahme;
  `robot`: SDK-Robot nur am echten Backend, sonst `None`.
- `cameras()`: Liste bekannter Kurznamen; `camera(name)`: Image. Kurznamen:
  frontleft, frontright, left, right, back. Auch exakte gemeldete SDK-Quellnamen
  werden angenommen. Image bietet `array` (NumPy), `raw`, `source`, `width`,
  `height`, `pixel_format`, `is_jpeg`, `intrinsics`, `to_png_bytes()` und
  `save(pfad)` (gibt Path zurück). Gespeicherte Tiefen-PNGs sind zur Anzeige
  normalisiert; quantitative Auswertung verwendet das ursprüngliche Array.
- `world_objects(kinds=None)`, `tags(id=None)`, `stairs()`: Listen, nächste zuerst,
  eventuell leer. WorldObject: name, kind, bearing (Grad relativ zum Körper),
  distance (m horizontal), world_xy (vision), time. Tag zusätzlich id und filtered.
  Staircase zusätzlich direction (auf/ab), steps, rise_m und axis_bearing (Grad bergauf).
- `load_map(name=None)`: Map mit name, dir, graph, waypoints und `id_fuer(name)`.
  Benötigt gespeicherte GraphNav-Karte im Workspace. `localize()` gibt die
  Wegpunktkennung zurück; `waypoints()` gibt Namen oder vor dem Laden `[]` zurück.
- `send(command, end_time_secs=None)`: Kommando-ID; nimmt RobotCommand-Protobuf
  und optional absolute lokale Ablaufzeit. Wartet nicht auf Abschluss.
- `messfenster(name, hz=50, **felder)`: Context Manager für markierte Messung.
  hz ist die angeforderte Abtastrate, keine zugesicherte effektive Rate.
  Metadaten etwa `bedingung="A"` werden zur Messung gespeichert.

`spot.state` einmal lesen und den Wert weiterverwenden, wenn mehrere Felder zur
selben Momentaufnahme gehören sollen. State: battery, powered, pose=(x,y,yaw)
in odom, velocity, joints, feet, z, roll, pitch, t_robot, velocity_vision,
feet_detail, behavior, battery_detail, motor_temps, faults. Neu: x/y in m,
heading in Grad und speed als Betrag der horizontalen Geschwindigkeit in m/s.
Gelenke liefern position, velocity, load, acceleration. `t_robot` ist die rohe
Roboterzeit. Die Komfortfelder ändern das bestehende Aufzeichnungsformat nicht.

## LocalGrid ohne Koordinatenrechnen

```python
view = spot.look(max_distance=1.8, margin=0.3)
for name in ("front", "left", "right", "back"):
    ray = getattr(view, name)
    print(name, ray.status, ray.distance)
print(view.direction(45))  # 45 Grad nach links
```

`look()` liefert Surroundings mit grid, position, heading, max_distance, margin,
start. position und heading beziehen sich auf **vision**. Vier Richtungs-Properties
und `direction(angle=0)` liefern Direction:

| Feld | Bedeutung |
|---|---|
| status | clear: geprüfter Abschnitt frei; blocked: Sicherheitsabstand unterschritten; unknown: unbekannte Zelle/Gittergrenze |
| distance | clear: max_distance; blocked: Abtastposition ab Körpermitte; unknown: None |
| known | status ist clear oder blocked; keine Aussage hinter einem Hindernis |
| observed_distance | Ende des zuvor lückenlos geprüften Abschnitts |
| start | Beginn der Prüfung; davor wird keine Aussage gemacht |

max_distance: 0.01–10 m, margin: 0.01–2 m, start: 0–max_distance.
Unbekannte Bereiche einschließlich Körperschatten werden standardmäßig **nicht
übersprungen**. Wer `start=0.9` setzt, blendet den Nahbereich ausdrücklich aus;
ein clear gilt dann nur für diesen Ausschnitt. Die Probe ist ein diskreter Strahl
mit Hindernisabstand, keine vollständige Kollisionsprüfung oder Fahrfreigabe.
Gitter und Körpertransformation werden nacheinander erfasst, nicht atomar.

`obstacles()` bleibt für eigene Algorithmen: ObstacleGrid mit cells (Abstandsfeld
in m), known (Beobachtungsmaske), cell_size, origin, time. `distance_at(x,y)`
liefert Abstand oder None; `is_free(x,y,margin=0.3)` liefert bool. Die Koordinaten
sind vision, **nicht state.pose (odom)**. Bestehendes `free_distance(x,y,heading,
max_distance=1.8,margin=0.3)` verwendet Weltwinkel in Grad und überspringt unbekannte
Nahzellen unter 0.9 m. Für neue Skripte mit expliziter Unbekannt-Behandlung look nutzen.

## Licht, Summer, Körperhaltung

`lights(color="blue", duration=2, brightness=0.25)` akzeptiert blue, green, red,
white, yellow, purple oder RGB-Tupel mit Ganzzahlen 0–255. brightness: 0–1,
duration: 0.05–10 s. Steuert fünf Haupt-LED-Gruppen.
`beep(note="C", octave=5, duration=0.3)` spielt C/D/E/F/G/A/B auf dem Piezo-Summer;
octave: 0–8, duration: 0.05–5 s. Die Firmware kann zusätzliche Grenzen setzen.
Dies ist keine WAV-/Sprachwiedergabe.

Beide Aufrufe benötigen den Dienst audio-visual und blockieren am echten Spot.
Sie registrieren einen eigenen temporären Behavior mit Priorität 0 und begrenzter
Laufzeit; danach werden Stop und Löschen auch bei Abbruch versucht. Globale
AV-Einstellungen werden nicht geändert. AV-Behaviors umfassen Licht und Ton;
auch ein Summer-Behavior kann die angezeigten LEDs während seiner Laufzeit
beeinflussen. Höhere Priorität oder deaktiviertes AV führt zu einer klaren
Fehlermeldung, nicht zu vorgetäuschtem Erfolg. Ein erzwungener Prozessabbruch kann
Aufräumen verhindern; die serverseitige Ablaufzeit begrenzt die Wiedergabe.

`pose(roll=0,pitch=0,yaw=0,height=0,timeout=10)` sendet einen Standbefehl.
Roll/Pitch: ±20°, Yaw: ±30°, Höhe: ±0.15 m relativ zur normalen Standhöhe,
timeout: 0.1–60 s. Motoren müssen an sein. Yaw verdreht den Körper gegenüber
der Standfläche; eine Richtungsänderung beim Gehen erfolgt mit move(turn=...).
`pose()` stellt neutrale Körperausrichtung und Höhe ein.

## Verfügbarkeit und Fehler

`supports(feature)` akzeptiert look, camera, tags, stairs, navigate_to, pose,
lights, beep. Es prüft Fähigkeiten, bei AV auch die Dienstliste. Es garantiert
keine erfolgreiche Ausführung: Motorzustand, Lease, Firmware, Lizenz und aktuelle
Bedingungen können einen Aufruf verhindern. Netzfehler werden nicht als False versteckt.

| Funktion | Real | dryrun | sim / mujoco |
|---|---|---|---|
| Bewegung / State | Roboter | synthetische Rückmeldung | simuliert |
| look / obstacles | LocalGrid | synthetisches Gitter | abhängig vom Backend/Raum; supports prüfen |
| Kamera / Tags / Treppen | Sensorik / Firmware | keine Kamera; weitere Fähigkeiten prüfen | abhängig vom Backend/Raum; supports prüfen |
| GraphNav | Karte und passende Berechtigungen nötig | keine reale Navigation | supports prüfen |
| lights / beep | audio-visual nötig | Protobuf prüfen und protokollieren, kein Ton/Licht | UnsupportedCapability |
| pose | Standkommando | Protobuf und Rückmeldung prüfen | UnsupportedCapability |

Sim/MuJoCo modellieren die neue Körperausrichtung noch nicht korrekt. Deshalb
melden diese Funktionen dort keinen Erfolg. Ungültige neue Parameter ergeben
ValueError; fehlende Fähigkeiten UnsupportedCapability (SpotlabError).
Kommandofehler/Timeouts und SDK-Verbindungsfehler werden weitergereicht.
Kommandos und relevante Rückmeldungen landen im normalen Laufprotokoll;
Sensorbilder werden beim camera-Aufruf aufgezeichnet. Direkte SDK-Aufrufe über
robot werden nicht automatisch vollständig als Komfortkommando protokolliert.

## Beispiele und SDK

Vier neue ausführbare Beispiele stehen unter `src/spotlab/workshop/beispiele/`:
zustand_lesen.py, umgebung_lesen.py, licht_und_ton.py, koerper_ausrichten.py.
Die [Abdeckungsmatrix](EXAMPLE_COVERAGE.md) zeigt verbleibende SDK-Funktionen.
Offizielle Grundlagen: [SDK-Beispiele](https://dev.bostondynamics.com/python/examples/readme),
[Audio/Visual](https://dev.bostondynamics.com/docs/concepts/audio_visual.html),
[AV-Protobuf](https://github.com/boston-dynamics/spot-sdk/blob/master/protos/bosdyn/api/audio_visual.proto).


## Tiefenbilder, Punktwolken und weitere LocalGrids

Ausführliche Beispiele und Koordinatenregeln: [Quantitative Wahrnehmung](PERCEPTION.md).
`depth(name="frontleft")` liefert DepthImage, `point_cloud(name="frontleft",
frame="body",stride=2,min_distance=0,max_distance=5)` PointCloud.
`grid_types()` liefert angebotene Namen, `local_grid(name="obstacle_distance")`
eine GridLayer. supports akzeptiert zusätzlich depth, point_cloud, grid_types,
local_grid. Es prüft den Diensttyp, nicht jede einzelne Grid-Ebene.
`map_pose()` (bestehender Navigationszugang) gibt (x, y, Grad) im Kartenrahmen
oder None zurück, solange keine Lokalisierung vorliegt.

## Experimenteller Physikmodus

`connect(backend="physics")` verwendet echte MuJoCo-Dynamik auf ebenem Boden.
Unterstuetzt stand in Neutralhoehe, walk, stop, State, Kameras und LocalGrid;
noch kein sit, move, pose oder Treppenlauf. Start bereits im Stand.
[Details und Einschraenkungen](PHYSICS.md).
