# Quantitative Wahrnehmung

Die neuen Befehle lesen Sensordaten. Sie starten keine Bewegung. Tiefe und
Punktwolken funktionieren am echten Spot und im MuJoCo-Backend; dryrun und 2D-Sim
haben keine Tiefenkamera. Die gespeicherten Daten sind Momentaufnahmen, keine
vollständige Rekonstruktion und keine Fahrfreigabe.

## Tiefenbild in Metern

```python
from spotlab import connect

with connect() as spot:
    depth = spot.depth("frontleft")
    print(depth.distance_at(212, 120))  # Spalte, Zeile; Meter oder None
    depth.save("tiefe.npz")
```

`depth(name="frontleft")` akzeptiert Kamerakurznamen oder eine genaue gemeldete
Tiefenquelle wie frontleft_depth. Ein Farbbild wird nicht als Tiefe interpretiert.
DepthImage enthält:

| Feld / Methode | Bedeutung |
|---|---|
| raw | unveränderte uint16-Pixelwerte, Array [Zeile, Spalte] |
| meters | axiale Entfernung von der Bildebene, in m; ungültige Pixel sind NaN |
| valid | bool-Maske: 0 und 65535 sind keine gültigen Tiefenmessungen |
| depth_scale | Rohwerteinheiten pro Meter, aus der Aufnahme |
| intrinsics | 3×3-Kameramatrix einschließlich Skew |
| frame, transforms | Sensorrahmen und verfügbare Transformationen der Aufnahme |
| time | Erfassungszeit in der Roboterzeitbasis, nicht PC-Empfangszeit |
| source | tatsächlicher SDK-Quellname |
| distance_at(column,row) | Meter oder None bei ungültigem Pixel / außerhalb |
| save("tiefe.npz") | verlustfreier NPZ-Export einschließlich Kalibrierung und Transformationen |

Die Entfernung ist die Kamera-z-Komponente, nicht der euklidische Abstand zum
Pixelpunkt. NumPy-Arrays verwenden NaN plus Maske für fehlende Werte; einzelne
Abfragen geben None zurück. `camera().save()` bleibt ein Anzeige-PNG und ersetzt
diesen quantitativen Export nicht. Ungültige Kalibrierung oder komprimierte
Tiefenformate werden abgewiesen, statt still mit einer angenommenen Skala zu rechnen.

## Punktwolken

```python
# Genau dieselbe Aufnahme verwenden, ohne erneut über WLAN zu lesen:
cloud = depth.point_cloud(frame="body", stride=2, min_distance=0, max_distance=5)
print(cloud.points.shape)  # (N, 3), auch (0, 3) möglich
cloud.save("punkte.ply")
cloud.save("punkte.npz")

# Alternativ direkt eine neue Aufnahme holen:
cloud = spot.point_cloud("frontleft", frame="vision", stride=4)
```

PointCloud enthält points (Nx3, Meter), frame, time und source. `stride` ist eine
positive ganze Zahl und wählt jeden n-ten Pixel je Achse. Distanzfilter sind
strikt min_distance < Kameratiefe < max_distance; Minimum endlich ≥0, Maximum
endlich >Minimum. Leere Punktwolken bedeuten keine gültigen Punkte im gewählten
Bereich, nicht automatisch einen freien Raum.

| frame | Achsen / Einsatz |
|---|---|
| sensor | x rechts, y unten, z entlang der optischen Achse; tatsächlicher Sensorname steht im Ergebnis |
| body | x vorwärts, y links, z aufwärts relativ zum Körper; kippt mit dem Körper |
| vision | visueller Weltbezug; für räumliches Zusammenführen von Aufnahmen |
| odom | Odometriebezug; passt zum Rahmen von state.pose |

Alle Transformationen stammen aus dem Rahmenbaum **dieser Aufnahme**. Fehlende
Rahmen führen zu einem Fehler; es wird keine Identität angenommen. Beim
Zusammenführen verschiedener Zeitpunkte bleiben Drift und bewegte Objekte zu
berücksichtigen. Dies ist keine Registrierung/SLAM-Pipeline. PLY speichert XYZ
und Kommentare zu Rahmen/Zeit, NPZ zusätzlich strukturierte Metadaten. Keine
Farben werden erfunden oder ohne Bildregistrierung zugeordnet.

## Weitere LocalGrid-Ebenen

```python
print(spot.grid_types())
grid = spot.local_grid("terrain")
print(grid.values.shape, grid.unit, grid.frame)
print(grid.value_at(0.25, 0.25))  # native Gitterkoordinaten, Meter
centers = grid.cell_centers(frame="vision")
grid.save("terrain.npz")
```

`grid_types()` fragt am echten Spot den Dienst ab. `local_grid(name)` lädt den
benannten Typ und prüft Status, RAW/RLE-Kodierung, Dimensionen und Gültigkeitsmaske.
Gelände wird zusammen mit terrain_valid angefordert; nur gültige Zellen bleiben
bekannt. Unpassende Erfassungszeit oder Geometrie führt zu einem Fehler und muss
mit einer neuen Aufnahme geprüft werden. Es werden keine Masken anderer
Zeitpunkte stillschweigend übernommen.

| Typ | Werte |
|---|---|
| terrain | geschätzte Geländehöhe in Metern, Welt-z gemäß SDK; keine Höhe über Spots Rücken |
| terrain_valid | Gültigkeitswerte für Geländeschätzung |
| obstacle_distance | vorzeichenbehafteter Abstand zur Hindernisregion in Metern |
| no_step | Markierung von Bereichen, in die Spot nicht treten soll |
| intensity | Intensitäts-Rohwerte |

Die tatsächlich angebotenen Namen entscheidet die Firmware. Ein separater Typ
obstacle_height wird nicht vorausgesetzt; Höhen lassen sich über terrain oder
Tiefenpunktwolken untersuchen. Unbekannte zusätzliche Typen werden dekodiert,
aber ihre Einheit wird als unknown markiert.

GridLayer enthält name, values (HxW), known (bool), cell_size (m), frame, time,
transforms und unit. `value_at(x,y)` nimmt **native Gitterkoordinaten ab der Ecke
von Zelle 0/0**; unbekannt oder außerhalb liefert None. Zellmitten liegen bei
(col+0.5, row+0.5) × cell_size. `cell_centers(frame)` transformiert diese Positionen
mit vollständiger Drehung/Translation. Ihre z-Komponente beschreibt die
Gitterebene, nicht automatisch die gemessene Geländehöhe. values und known
behalten ihre Zeilen-/Spaltenzuordnung. Nicht einfach state.x/y als Gitter-x/y
einsetzen.

Das bisherige `obstacles()` und `look()` bleiben kompatibel. Für dryrun und
Simulation liefert der neue Zugang nur das vorhandene obstacle_distance-Gitter,
wenn LOCAL_GRID verfügbar ist. Terrain/no_step/intensity werden dort ausdrücklich
als nicht unterstützt gemeldet. Es werden keine idealen Raumeditor-Höhen als
simulierte Sensormessungen ausgegeben.

## Aufzeichnung, Beispiele und Prüfung

Jeder erfolgreiche depth-/local_grid-Aufruf speichert eine eigene NPZ unter
`runs/<Lauf>/sensoren/`, verknüpft über einen kommando-Eintrag im Ereignisprotokoll.
point_cloud über Spot speichert die zugrunde liegende Tiefenaufnahme; die daraus
gewählte Wolke wird bei Bedarf mit save exportiert. Automatische Speicherung
kostet Zeit und Speicherplatz: diese Komfortaufrufe sind keine Streaming-API.
NPZ lässt sich mit `numpy.load(path, allow_pickle=False)` lesen.

Beispiele im Beispiele-Ordner: tiefenbild_lesen.py, punktwolke_speichern.py,
localgrids_lesen.py. Sie schreiben manuelle Exporte in auswertung/ neben dem
Skript; wiederholte Starts ersetzen dort gleichnamige Exporte. Im Laufordner
bleiben die einzelnen Originalaufnahmen erhalten. Neue Beispieldateien erscheinen
beim nächsten GUI-Start, bestehende Benutzerdateien werden nicht überschrieben.

Geprüft mit synthetischen SDK-Protobufs und gespeicherten Roboteraufnahmen;
Hardware-Abnahme siehe [ABNAHME.md](ABNAHME.md). Die numerische Punktwolke wird
gegen die installierte SDK-Umrechnung verglichen.

Quellen: [SDK-Sensordienste](https://dev.bostondynamics.com/docs/concepts/robot_services.html),
[Image-Schema](https://github.com/boston-dynamics/spot-sdk/blob/master/protos/bosdyn/api/image.proto),
[LocalGrid-Schema](https://github.com/boston-dynamics/spot-sdk/blob/master/protos/bosdyn/api/local_grid.proto).
