# Beispiele: Abdeckung und Grenzen

Stand: 7. September 2026. Themenmatrix, keine Behauptung einer vollständigen
1:1-Portierung jedes offiziellen SDK-Beispiels. SDK-only bedeutet: über
`spot.robot.ensure_client(...)` am echten Spot erreichbar, aber keine eigene
Komfortmethode. Das SDK erfordert weiter eigene Parameter und Rückmeldungsbehandlung.

| Beispielthema | spotlab-Zugang | Stand |
|---|---|---|
| Hello Spot, Stand/Sit, relative Bewegung | power_on, stand, sit, move, walk | vorhanden; hallo_spot.py |
| Körperorientierung | pose | neu; koerper_ausrichten.py; real/dryrun |
| Robot State | state, messfenster | komfortable x/y/heading/speed neu; zustand_lesen.py |
| LocalGrid / Hindernisse | obstacles, look | Richtungen und unknown neu; umgebung_lesen.py |
| Bildaufnahme | cameras, camera, Image.array/save | vorhanden |
| Tiefenbild in Metern / Punktwolke | depth, point_cloud, NPZ/PLY-Export | neu; tiefenbild_lesen.py, punktwolke_speichern.py; real/MuJoCo |
| Weitere LocalGrid-Ebenen / Gelände | grid_types, local_grid | neu; localgrids_lesen.py; terrain inkl. terrain_valid am echten Spot |
| SDK-Visualizer (Live-3D-Ansicht) | exportierte Punktwolken / Gitter | Datenzugang vorhanden; kein vollständiger Live-Visualizer |
| AprilTags / WorldObjects | tags, world_objects | vorhanden; uebungsraum.py |
| Durchgangssuche | Wahrnehmung + move/walk | durchgang_finden.py |
| Treppen | stairs + Bewegung | treppe_steigen.py; Firmware/Sim-Grenzen beachten |
| GraphNav-Navigation | load_map, localize, waypoints, navigate_to | vorhanden; vorbereitete Karte nötig |
| GraphNav-Aufzeichnung / Autowalk-Missionen | GUI-Kartenworkflow / SDK-Clients | keine vollständige Python-Komfort-API |
| AV-LEDs / Piezo-Summer | lights, beep | neu; licht_und_ton.py; audio-visual nötig |
| spot_light (Lichtquelle verfolgen) | camera().array + eigener Algorithmus + walk | Bildverarbeitung fehlt als Komfortbefehl; kein LED-Beispiel |
| Docking / Undocking | DockingClient | SDK-only |
| Arm, Greifer, Manipulation, Türen | entsprechende SDK-Clients | SDK-only; passende Hardware nötig |
| Spot CAM Audio/WAV, PTZ, Beleuchtung | Spot-CAM-Clients | SDK-only; Payload nötig; beep ersetzt dies nicht |
| Choreography | ChoreographyClient | SDK-only; Lizenz/Voraussetzungen prüfen |
| Data Acquisition / eigene Payload-Dienste | entsprechende SDK-Clients | SDK-only |
| RobotState-/Command-Streaming | entsprechende SDK-Clients | keine vollständige Komfort-API; Messfenster nutzt RobotState |

Neue Beispiele verwenden connect() und folgen der ausgewählten Backend-Einstellung.
Für einen garantiert roboterfreien Versuch vor dem Start in PowerShell:

```powershell
$env:SPOTLAB_NUR_TROCKEN = "1"
$env:SPOTLAB_BACKEND = "dryrun"
python .\licht_und_ton.py
```

Im GUI werden fehlende Beispieldateien beim nächsten Start ergänzt. Bereits vom
Benutzer veränderte Dateien einschließlich README werden nicht überschrieben.

[API-Referenz](API.md) · [Offizielle Beispiele](https://dev.bostondynamics.com/python/examples/readme)
· [spot_light](https://dev.bostondynamics.com/python/examples/spot_light/readme)
