# Raumeditor Etappe 3 „Rekonstruktion" — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aus einer GraphNav-Karte (Wegpunkte, Punktwolken, verankerte AprilTags) wird ein `Raum` mit Wänden, Tags und Start; die Punktwolke bleibt als Pauspapier im Editor, wo man Wände nachzieht. Ohne Wolken ein Schlauch um den Pfad.

**Architecture:** `maps/rekonstruktion.py` (darf bosdyn und numpy) liest die Karte, transformiert die Wolken in den Seed-Rahmen (Kette aus `map_viewer/transformer.py`), schneidet das Höhenband, rastert, findet Linien per RANSAC, teilt an Lücken (Türen), richtet aus und liefert `Ergebnis(raum, pauspapier, bericht)`. `welt/pauspapier.py` (Standardbibliothek) schreibt und liest die Punktdatei, damit die GUI sie ohne numpy zeichnen kann. Der Tab bekommt einen Dialog mit Arbeiter-`QThread` (Muster `gui/recorder.py`).

**Tech Stack:** numpy, `bosdyn.api.graph_nav.map_pb2`, `bosdyn.client.frame_helpers`, `bosdyn.client.math_helpers.SE3Pose` — nur unter `maps/`; PySide6 im Tab; `array`/`struct` in `welt/pauspapier.py`.

**Spec:** `docs/superpowers/specs/2026-09-06-raumeditor-design.md` (Abschnitte 1 Ablage/Pauspapier, 6, 7, 8)

## Global Constraints

- Protobufs (`bosdyn.api`) nur unter `maps/` und `backends/`; die GUI bekommt `Raum`, Punkte, Bericht. Kein numpy unter `gui/` und `welt/` (ausser `welt/wahrnehmung.py`).
- Gemessen an `map_catacombs_01` (06.09.2026): Punktwolke `encoding 1` = XYZ float32, Quellrahmen `sensor_origin_generated`, Kette `seed_tform_waypoint · waypoint_tform_ko · odom_tform_cloud`; Boden = 5. Perzentil der z-Werte liegt 0.54 m unter dem Wegpunkt; die **z-Achse** des Fiducial-Rahmens (`seed_tform_object`) zeigt aus der Tag-Fläche zu den Beobachtern — sie ist die Blickrichtung.
- Pauspapier-Datei: `b"PAUS1"`, `uint32` Anzahl, `float32`-Paare (x, y); höchstens 200 000 Punkte.
- RANSAC mit festem Seed (`numpy.random.default_rng(0)`): dieselbe Karte gibt denselben Raum.
- Kommandos aus `D:\Users\janis\Documents\Matura\spotlab`; Commit-Trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## Dateiplan

| Datei | Aufgabe |
|---|---|
| `src/spotlab/welt/pauspapier.py` | `schreibe(pfad, punkte)`, `lies(pfad) -> list[(x, y)]`, `pfad_zu(raumpfad)` |
| `src/spotlab/maps/rekonstruktion.py` | `Einstellungen`, `Ergebnis`, `lade_karte`, `wolke_im_seed`, `boden_hoehe`, `belegte_zellen`, `linien_ransac`, `teile_an_luecken`, `verschmelze`, `ausrichten`, `tags_aus_anker`, `start_aus`, `schlauch`, `rekonstruiere` |
| `src/spotlab/gui/raumeditor/rekonstruktion_dialog.py` | Dialog + `RekonstruktionsArbeiter(QThread)` |
| `src/spotlab/gui/raumeditor/tab.py` | Knopf „Rekonstruieren…", Pauspapier laden/speichern/zeigen |
| `tests/test_welt_pauspapier.py`, `tests/test_maps_rekonstruktion.py`, `tests/test_gui_raumeditor_rekonstruktion.py` | Tests, synthetische Karte, Abnahmetest gegen die Katakomben (`skipif`) |
| `README.md`, `CLAUDE.md`, `docs/ABNAHME.md` (A24) | Doku |

---

### Task 1: `welt/pauspapier.py` — die Punktdatei

**Interfaces:** `schreibe(pfad, punkte)` (Iterable von (x, y), auf `MAX_PUNKTE = 200_000` gleichmässig gedünnt), `lies(pfad) -> list[tuple[float, float]]` (fehlende Datei → `[]`, falsche Kennung → `SpotlabError`), `pfad_zu(raumpfad) -> Path` (`<name>.pauspapier` neben der TOML).

- [ ] Tests (`tests/test_welt_pauspapier.py`): Rundreise 3 Punkte; 250 000 Punkte werden 200 000; fehlende Datei → `[]`; falsche Kennung → `SpotlabError`; `pfad_zu(Path("raeume/gang.toml")) == Path("raeume/gang.pauspapier")`; `welt/` importiert weiterhin nichts Verbotenes (bestehender Test).
- [ ] Implementierung mit `struct.pack("<5sI", b"PAUS1", n)` + `array("f")`; Dünnen über `punkte[::schritt]` mit `schritt = ceil(n / MAX_PUNKTE)`.
- [ ] Commit `feat(welt): pauspapier.py -- Punktdatei fuer den Raumeditor`.

### Task 2: `maps/rekonstruktion.py` — Kern, mit synthetischer Karte

**Interfaces:**

```python
@dataclass(frozen=True)
class Einstellungen:
    band: tuple = (0.3, 1.6); zelle: float = 0.05; mindestens_punkte: int = 3
    inlier: float = 0.06; min_laenge: float = 0.5; luecke: float = 0.4
    ausrichten: bool = True; schlauch_breite: float = 2.0; pauspapier_max: int = 200_000

@dataclass(frozen=True)
class Ergebnis:
    raum: Raum; pauspapier: list; bericht: dict

def lade_karte(ordner) -> (graph, {wp_id: WaypointSnapshot}, fehlend: int)
def posen(graph) -> ({wp_id: SE3Pose}, quelle: "anker" | "kette")
def wolke_im_seed(waypoint, snapshot, seed_tform_wp) -> ndarray (N, 3)
def boden_hoehe(z) -> float                     # 5. Perzentil
def belegte_zellen(xy, zelle, mindestens) -> ndarray (M, 2) Zellmitten
def linien_ransac(punkte, inlier, min_inlier=10, versuche=200, rng) -> list[(mittel, richtung, inlier_punkte)]
def teile_an_luecken(mittel, richtung, punkte, luecke, min_laenge) -> list[Wand]
def verschmelze(waende, winkel_grad=5.0, abstand=0.2) -> list[Wand]
def ausrichten(waende, tags, start, pauspapier) -> (waende, tags, start, pauspapier, winkel_grad)
def tags_aus_anker(graph, boden) -> list[RaumTag]   # Blick = atan2 der z-Achse
def start_aus(graph, posen) -> (x, y, grad)
def schlauch(graph, posen, breite) -> list[Wand]
def rekonstruiere(ordner, einstellungen=Einstellungen(), fortschritt=None) -> Ergebnis
```

- [ ] Tests (`tests/test_maps_rekonstruktion.py`): eine **synthetische Karte** als Fixture `synthetische_karte(tmp_path)`: Graph mit 6 Wegpunkten entlang x (0..5 m, y = 1), Anker `seed_tform_waypoint` = Pose, `waypoint_tform_ko` = Identität, je ein Schnappschuss mit `point_cloud` (encoding 1, float32 XYZ) im Rahmen `sensor` mit `transforms_snapshot` (`odom` → `sensor`, Identität) und `frame_name_sensor = "sensor"`; die Punkte sind Samples (alle 3 cm, z 0.3–1.5) der Wände `y = 0` und `y = 2` (Gang 6 × 2 m) mit einer **Tür** bei `x ∈ [2.5, 3.4]` in der oberen Wand, plus Bodenpunkte (z = 0) und Deckenpunkte (z = 2.4), die das Band verwerfen muss; ein verankertes Objekt Tag 7 bei (5.0, 2.0) mit z-Achse nach −y (Blick 270°), Höhe 0.9 m. Erwartet: `rekonstruiere` findet ≥ 3 Wände, die untere Wand als EIN Segment ≥ 5.5 m innerhalb 10 cm, die obere in zwei Stücke mit Lücke 0.9 ± 0.15 m; Tag 7 auf 10 cm und 10°; Start = Pose des ersten Wegpunkts; Bericht nennt `wegpunkte == 6`, `posen == "anker"`; ohne Wolken (Schnappschüsse ohne Punkte) → Schlauch mit 2 Wänden je Kante und Bericht `quelle == "schlauch"`; `ausrichten` dreht eine um 30° gedrehte Kopie derselben Karte zurück (häufigste Richtung → x). Abnahmetest gegen `D:\Users\janis\Documents\Spot Projects\maps\map_catacombs_01` (`skipif` fehlt): 31 Tags, ≥ 20 Wände, < 60 s.
- [ ] Implementierung. RANSAC: `rng.choice` zweier Zellmitten, Normale, Inlier ≤ `inlier`; beste von 200; Verfeinerung per Hauptachse (Eigenvektor der Kovarianz); Inlier entfernen; Abbruch bei < 20 Zellen oder < 10 Inliern. Teilen: Projektionen sortieren, an Sprüngen > `luecke` schneiden, Stücke < `min_laenge` verwerfen, Endpunkte auf 1 cm runden. Ausrichten: Winkel mod 90 (längengewichtetes Histogramm in 1°-Klassen) → Drehung um −Winkel um den Ursprung, danach Verschiebung, sodass die Hülle bei (0.5, 0.5) beginnt. Bericht: `wegpunkte, schnappschuesse, fehlend, punkte, im_band, zellen, linien, waende, verworfen, tags, ausricht_grad, posen, quelle, dauer_s, hinweise`.
- [ ] Commit `feat(maps): Rekonstruktion -- Waende aus der Punktwolke, Tags aus den Ankern, Schlauch ohne Wolken`.

### Task 3: Dialog, Arbeiter, Pauspapier im Tab, Doku

- [ ] `rekonstruktion_dialog.py`: `RekonstruktionsArbeiter(QThread)` mit Signalen `fortschritt(str)`, `fertig(object)`, `fehler(str)`; `run()` ruft `rekonstruiere(ordner, einstellungen, fortschritt=self.fortschritt.emit)`. `RekonstruktionsDialog(QDialog)`: Karte aus `karten(workspace)` (Combo) oder „Ordner wählen…" (`QFileDialog.getExistingDirectory`), Felder für Band (2 SpinBoxen), Zelle, Lücke, Mindestlänge, Schlauchbreite, Häkchen Ausrichten; Knopf „Vorschau" (sperrt sich, Fortschrittszeile), Bericht als Text; `ergebnis` nach Erfolg; „Übernehmen" = accept.
- [ ] Tab: Knopf „Rekonstruieren…" → Dialog; bei Accept `_setze(ergebnis.raum, "", False, True)` und `self._pauspapier = ergebnis.pauspapier` → beide Sichten `setze_pauspapier`. Beim Speichern eines Raums mit Pauspapier: `pauspapier.schreibe(pfad_zu(pfad), punkte)`; beim Laden (`waehle_raum`): `pauspapier.lies(pfad_zu(raum_pfad))`, wenn eigen. Der Bericht landet in `meldung`.
- [ ] Tests (`tests/test_gui_raumeditor_rekonstruktion.py`): Arbeiter mit synthetischer Karte liefert `fertig` mit einem `Ergebnis` (QSignalSpy / Ereignisschleife bis `wait()`), der Tab übernimmt das Ergebnis (Raum ohne Namen, Pauspapier in `sicht._pauspapier`), Speichern schreibt `.pauspapier` neben die TOML, `waehle_raum` liest es wieder.
- [ ] Doku: README-Absatz „Aus einer Karte" (Katakomben-Beispiel), CLAUDE.md (Protobufs nur in `maps/`; Fiducial-z-Achse ist die Blickrichtung — gemessen), ABNAHME A24 (Katakomben-Raum in 3D fahren, Tag-Blickrichtungen gegen die echten prüfen), Umsetzungsstand Etappe 3.
- [ ] Suite, ruff, Commit `feat(raumeditor): Rekonstruieren aus einer Karte -- Dialog, Arbeiter, Pauspapier`.
