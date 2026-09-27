# Steuerzentrale Teil 2 — Implementation Plan

> Inline ausgeführt (keine Sub-Agenten, Nutzerregel), TDD je Aufgabe, Worktree `.worktrees/menschen`,
> Branch `feat/zentrale-menschen`.

**Goal:** Menschen in der Draufsicht (Regler Aus/Sparsam/Normal/Rundum) und Folgen per Klick auf einen Menschen.

**Spec:** `docs/superpowers/specs/2026-09-27-steuerzentrale-menschen-design.md`

## Global Constraints

- Wie Teil 1: `record/zentrale.py` nur Standardbibliothek; GUI ohne `bosdyn`/`spotlab.backends`,
  Farben nur aus dem Thema; Lage für die Draufsicht aus `folgen._lage_im_gitter` (vision).
- Das Frontpanorama (`Panorama`) wird nicht verändert; die bestehenden Tests bleiben unverändert grün.
- Folgen nur mit frischem Lebenszeichen des Tabs; `folge()` selbst bleibt unverändert.

---

### Task 1: Einzelsicht (`backends/real/panorama.py`)
- `Einzelsicht(kamera, ebene_m=EBENE_M, brennweite_px=BRENNWEITE_PX)`: `gier_grad`, `breite`, `hoehe`,
  `winkel(spalte, zeile) -> (peilung_koerper, hoehenwinkel)`, `spalte(peilung)`, `kamerahoehe(blick_grad)`,
  `zusammensetzen([bild])`.
- Tests (`tests/test_backend_einzelsicht.py`): nachgebaute Links- und Rückkamera (`panorama.Kamera`
  mit Lage-Matrix): Mitte ≈ +90° bzw. 180°, Spalte nach rechts heisst links nach vorn (kleinere Peilung),
  `spalte(winkel)` zurück, ein heller Fleck in der Bildmitte landet bei `spalte(gier)`, Grau und Farbe.

### Task 2: Protokoll (`record/zentrale.py`)
- `Klickziel.art` (Vorgabe `"ort"`, auch `"mensch"`), `schreibe_klickziel(..., art="ort")`;
  `ZUSTAENDE` + `"folgt"`; `SUCHSTUFEN = ("aus", "sparsam", "normal", "rundum")`;
  `schreibe_aktion(lauf_dir, nummer, "suche", stufe=…)`, `lies_aktion` liefert `stufe`.
- Tests in `tests/test_record_zentrale.py`.

### Task 3: Suche (`workshop/menschensuche.py`)
- `Mensch(x, y, abstand, peilung, quelle, t)`; `SEITEN`; `SPARSAM_PAUSE_S = 2.0`;
  `Menschensuche(spot, erkenner_bauen=None, vorne_holen=None, seite_holen=None, lage_holen=None)`,
  `runde(stufe, t) -> (menschen, gruende)`.
- Tests mit Attrappen (`tests/test_workshop_menschensuche.py`): Weltlage aus Peilung/Abstand und Lage
  (auch gedreht), „aus“ ruft nichts, „rundum“ fragt drei Seiten, eine scheiternde Seite hält die
  anderen nicht auf, verworfene Körper zählen nicht, je Quelle ein eigener Erkenner.

### Task 4: Suche in der Zentrale (`workshop/zentrale.py`)
- Faden `_suche_schleife`; Aktion `suche`; Lagebild `menschen` (≤ 3 s) und `suche` (`kann` =
  Tiefen- UND Bildkameras); Pause während des Folgens.
- Tests in `tests/test_workshop_zentrale.py` mit einer Such-Attrappe.

### Task 5: Folgen aus der Zentrale (`workshop/zentrale.py`)
- Klickziel `art="mensch"` → `_folge_mensch`: `folgen.folge()` mit eingewickeltem Körperfinder
  (Start: nur der Kandidat nahe dem Klick, ≤ 1 m, zwei Treffer), `laeuft` = Stopp/Taste/Klick/Totmann,
  Grund ins Lagebild, danach Lichtwunsch wieder setzen.
- Tests: Auswahl unter zwei Kandidaten, Ende bei Taste, bei neuem Klick, bei altem Lebenszeichen;
  Zustand `folgt` im Lagebild.

### Task 6: Tab und Draufsicht
- `gui/lagebild.py`: Menschen als Kreise (Alter → Blässe, Gefolgter mit Ring), `mensch_bei(x, y, r)`.
- `gui/views/fahren.py`: Regler (4 Stufen) + Rundenzeit, grau ohne `kann`; Klick nahe Mensch →
  Klickziel `mensch`; Zeile für `folgt`.
- Tests in `tests/test_gui_lagebild.py`, `tests/test_gui_fahren.py`.

### Task 7: Doku, A39, Suite, Merge
- `CLAUDE.md`, `docs/ABNAHME.md` (A39), volle Suite, ruff, ff-merge.
