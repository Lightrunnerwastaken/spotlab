# Steuerzentrale Teil 3 — Implementation Plan

> Inline ausgeführt (keine Sub-Agenten, Nutzerregel), TDD je Aufgabe, Worktree `.worktrees/karten`,
> Branch `feat/zentrale-karten`.

**Goal:** In der Zentrale Karten aufnehmen (neu und weiterführen), eine bekannte Karte deckungsgleich
einblenden und zeigen, wie viel Spot davon wiedererkennt.

**Spec:** `docs/superpowers/specs/2026-09-27-steuerzentrale-karten-design.md`

## Global Constraints

- Wie Teil 1/2: `record/zentrale.py` nur Standardbibliothek, atomar; GUI ohne `bosdyn`/`spotlab.backends`
  (Kartenliste über `maps/store` nur in einer Methode importiert), Farben nur aus dem Thema.
- Protobufs nur unter `backends/` und `maps/`. Der Fahrtakt wartet nie auf Kartenarbeit.
- Eine gespeicherte Karte wird nie überschrieben (neuer Name mit „-2“, „-3“ …).
- Koordinaten im Lagebild im Rahmen „vision“, Raster mit Ursprung auf Vielfachen von 0.05 m.

---

### Task 1: Verortung am Roboter (`backends/base.py`, `backends/real/graphnav.py`, `backends/real/session.py`)
- `@dataclass(frozen=True) Verortung(wegpunkt, seed, vision, verloren, angenommen, abgelehnt)`;
  `seed`/`vision` = `(x, y, gier_rad)` oder `vision=None`, wenn der Rahmenbaum der Antwort kein
  „vision“ hat.
- `graphnav.verortung(robot) -> Verortung | None` aus EINER `get_localization_state()`-Antwort:
  `localization.seed_tform_body`, `robot_kinematics.transforms_snapshot` → vision_tform_body,
  `lost_detector_state`. `None` bei leerer `waypoint_id`. `RealSpot.verortung()` delegiert.
- Tests (`tests/test_backend_verortung.py`): echte Protobufs in einer Client-Attrappe (verortet,
  nicht verortet, verloren, ohne vision).

### Task 2: Protokoll (`record/zentrale.py`)
- `KARTENAUFTRAG = "kartenauftrag.json"`, `KARTENAUFTRAEGE = ("laden", "aufnahme_start",
  "aufnahme_stopp", "wegpunkt")`, `schreibe_kartenauftrag(lauf_dir, nummer, was, name=None)`
  (unbekanntes `was` → ValueError), `lies_kartenauftrag(lauf_dir) -> dict | None`.
- `LAGEBILD_KARTE = "lagebild_karte.png"`, `KARTE_UNGEPRUEFT, KARTE_ERKANNT, KARTE_FEHLT, KARTE_NEU
  = 1, 2, 3, 4`; `schreibe_lagebild(lauf_dir, daten, bild, kartenbild=None)` schreibt beide Bilder vor
  der Beschreibung.
- Tests in `tests/test_record_zentrale.py`.

### Task 3: Kartenwände und Abgleich (`workshop/kartenabgleich.py`)
- `Kartenwaende.aus_ordner(ordner)`: Zellen (5 cm, ≥ 3 Punkte, Band 0.3–1.6 m über dem Boden je
  Schnappschuss) als Nx2-Mitten im Seed-Rahmen, `wegpunkte [(x, y, name)]`, `kanten [(i, j)]`.
- `vision_von_seed(verortung) -> (tx, ty, dgier)`; `in_vision(punkte, trafo)`.
- `abgleich(skizze, waende_vision, spot_xy, t) -> Abgleich(raster, ursprung, breite, hoehe,
  erkannt, neu, fehlt, anteil)`; Blickfeld = Skizzenzellen ≤ `FRISCH_S` alt und ≤ `BLICK_M` (4 m)
  von Spot; Toleranz `NAH_M` 0.15; `anteil` None unter `MIN_WANDZELLEN` (20); `verloren=True` →
  alles UNGEPRUEFT, anteil None. `png(raster)` als Indexbild wie `Skizze.png`.
- Tests (`tests/test_workshop_kartenabgleich.py`): gebaute Skizzen (erkannt, neu, fehlt, ausserhalb
  des Blickfelds, zu wenig Wand, verloren), Transformation (gedreht), Katakomben-Karte (skipif fehlt).

### Task 4: Kartenarbeit (`workshop/kartenarbeit.py`)
- `Kartenarbeit(spot, arbeitsordner, jetzt, melde, sitzung_bauen=None, ausfuehren=None)`;
  Zustände `keine | laedt | sucht_tag | verortet | verloren | nimmt_auf | speichert`.
- `auftrag(nummer, was, name)`: je Nummer einmal; langsame Arbeit über `ausfuehren` (Vorgabe:
  EIN Faden, eine Arbeit zugleich; zweiter Auftrag → abgelehnt mit Grund); `erledigt` = Nummer.
- `laden`: `store.finde` → `backend.upload_map` → `backend.localize` (alle 2 s neu, bis Erfolg oder
  neuer Auftrag) → `Kartenwaende.aus_ordner`.
- `aufnahme_start(name)`: verortet → weiterführen (`start(graph_leeren=False)`), sonst neu
  (`start(graph_leeren=True)`); `wegpunkt(name)`; `aufnahme_stopp`: `stop`, `nachbearbeiten`,
  `download` unter freiem Namen (`freier_name(wurzel, name)`), dann als geladene Karte übernehmen;
  Herunterladen gescheitert → Zustand `nimmt_auf` mit Grund „nicht gespeichert — nochmal versuchen“.
- `beobachte(t)`: `backend.verortung()`, Zähler-Historie 30 s, `verloren`; `daten(t, abgleich)` →
  Lagebild-`karte`. `beenden()`: läuft eine Aufnahme, erst speichern.
- Tests (`tests/test_workshop_kartenarbeit.py`) mit Attrappen, `ausfuehren=lambda f: f()`.

### Task 5: Zentrale (`workshop/zentrale.py`, `gui/app.py`)
- `Zentrale(..., kartenarbeit=None)`; `takt` liest `kartenauftrag.json` und reicht neue Nummern an
  `kartenarbeit.auftrag`; Wahrnehmung: `beobachte`, `abgleich`, `karte`-Daten und `lagebild_karte.png`.
- `argumente`: `--arbeitsordner`; `_hauptprogramm` baut die Kartenarbeit, am Ende `beenden()` vor `sit()`.
- `app.py::_starte_zentrale` gibt `--arbeitsordner` mit.
- Tests in `tests/test_workshop_zentrale.py` (Auftrag kommt an, Lagebild `karte`, Ende speichert),
  `tests/test_gui_app.py` (Argument).

### Task 6: Tab und Draufsicht (`gui/lagebild.py`, `gui/views/fahren.py`)
- Lagebild: Kartenraster (Farben aus dem Thema, „fehlt“ als Schachbrett), Wegpunkte mit Namen, Kanten.
- Tab: Zeile „🗺 Karte“ (Auswahl, Laden, ● Aufnahme / ■ beenden, Namensfeld mit Vorschlag,
  📍 Wegpunkt mit Dialog), Statuszeile, Nachschicken nach 1.5 s, grau ohne `kann`.
- Tests in `tests/test_gui_lagebild.py`, `tests/test_gui_fahren.py`; Bild hell/dunkel ansehen.

### Task 7: Doku, A40, Suite, Merge
- `CLAUDE.md`, `docs/ABNAHME.md` (A40), volle Suite, ruff, ff-merge, Worktree weg, Gedächtnis.
