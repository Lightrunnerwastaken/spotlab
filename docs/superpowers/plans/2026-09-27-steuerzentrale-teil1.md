# Steuerzentrale Teil 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In diesem Projekt: inline ausführen, keine Sub-Agenten (Nutzerregel).

**Goal:** Der Tab „Fahren“ wird zur Steuerzentrale: Draufsicht mit wachsender Skizze (Boden, Wände, Tags, Spot), W A S D Q E, Klickfahrt mit Umweg, Licht und Ton — am echten Spot und im Übungsraum.

**Architecture:** EIN Programm `workshop/zentrale.py` (Paketcode, gestartet mit `--runs`) hält die Verbindung, liest `fahrt.json`, `klickziel.json`, `aktion.json` aus dem Lauf-Verzeichnis und schreibt `lagebild.json` + `lagebild.png`. Reine Rechenbausteine (`skizze`, `wegsuche`, `klickfahrt`) sind ohne Roboter prüfbar; der Tab zeichnet nur (`gui/lagebild.py`).

**Tech Stack:** Python 3.11+, numpy, Pillow (Programmseite), PySide6 (GUI), pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-steuerzentrale-design.md`

## Global Constraints

- Keine Sub-Agenten; TDD (Test zuerst rot); Worktree `.worktrees/zentrale`, Branch `feat/steuerzentrale`.
- Interpreter: `C:/Users/janis/miniconda3/python.exe`; Suite `-m pytest tests -q -p no:cacheprovider`; `-m ruff check .` grün.
- Unter `src/spotlab/gui/`: kein `bosdyn`, kein `spotlab.backends`, keine Farbliterale (Farben aus `gui/theme.py`).
- `record/zentrale.py`: nur Standardbibliothek (die GUI importiert es); jede Datei atomar über `record/atomar.schreibe_atomar`.
- Lage für Gitter und Skizze aus `folgen._lage_im_gitter` (Rahmen „vision“), nie `state.pose`.
- Totmann 0.5 s; Fahrkommandos `walk(..., stop=False)`; am Ende IMMER `spot.stop()` vor Licht aus.
- Vorgabe im Tab: Übungsraum. Echter Spot nur ausdrücklich. `--uebernehmen` nur am echten Spot.
- Meldungen deutsch, Bezeichner wie im Projekt (deutsch in workshop/record, Aufzeichnungsschlüssel deutsch).
- Commit-Nachrichten per `-F <Datei>`, deutsch mit transliterierten Umlauten, Absatz „Tests:“, Trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Dateiprotokoll `record/zentrale.py`

**Files:**
- Create: `src/spotlab/record/zentrale.py`
- Test: `tests/test_record_zentrale.py`

**Interfaces:**
- Produces: `KLICKZIEL, AKTION, LAGEBILD, LAGEBILD_BILD, TOTMANN_S=0.5, FARBEN, ZUSTAENDE, ALTERSSTUFEN=8`;
  `Klickziel(nummer:int, ziel:tuple|None, stufe:str, lebt:float)`;
  `schreibe_klickziel(lauf_dir, nummer, ziel, stufe, jetzt=time.time) -> bool`, `lies_klickziel(lauf_dir) -> Klickziel|None`, `lebt(kz, jetzt=time.time) -> bool`;
  `schreibe_aktion(lauf_dir, nummer, art, farbe=None) -> bool` (art ∈ {"licht","ton"}; ValueError sonst), `lies_aktion(lauf_dir) -> dict|None`;
  `schreibe_lagebild(lauf_dir, daten:dict, bild:bytes|None) -> bool` (Bild zuerst), `lies_lagebild(lauf_dir) -> dict|None`.

- [ ] **Step 1: Tests schreiben** — Rundreise Klickziel (mit/ohne Ziel), `lebt` bei 0.4 s ja / 0.6 s nein, kaputte/fehlende Datei → None, Aktion Licht/Ton, unbekannte Art/Farbe → ValueError, Lagebild: Bild liegt vor der JSON auf der Platte (Reihenfolge über eine Attrappe von `atomar.schreibe_atomar`), halb geschriebene JSON → None.

```python
def test_das_klickziel_kommt_heil_an_und_lebt_eine_halbe_sekunde(tmp_path):
    z.schreibe_klickziel(tmp_path, 3, (1.5, -2.0), "langsam", jetzt=lambda: 100.0)
    kz = z.lies_klickziel(tmp_path)
    assert kz == z.Klickziel(3, (1.5, -2.0), "langsam", 100.0)
    assert z.lebt(kz, jetzt=lambda: 100.4) and not z.lebt(kz, jetzt=lambda: 100.6)
    assert not z.lebt(None)

def test_ohne_ziel_heisst_abbrechen(tmp_path):
    z.schreibe_klickziel(tmp_path, 4, None, "normal", jetzt=lambda: 1.0)
    assert z.lies_klickziel(tmp_path).ziel is None

def test_kaputt_oder_fehlend_ist_nichts(tmp_path):
    assert z.lies_klickziel(tmp_path) is None
    (tmp_path / z.KLICKZIEL).write_text("{halb", encoding="utf-8")
    assert z.lies_klickziel(tmp_path) is None

def test_aktionen_licht_und_ton(tmp_path):
    z.schreibe_aktion(tmp_path, 1, "licht", "gruen")
    assert z.lies_aktion(tmp_path) == {"nummer": 1, "art": "licht", "farbe": "gruen"}
    z.schreibe_aktion(tmp_path, 2, "ton")
    assert z.lies_aktion(tmp_path)["art"] == "ton"
    with pytest.raises(ValueError): z.schreibe_aktion(tmp_path, 3, "tanz")
    with pytest.raises(ValueError): z.schreibe_aktion(tmp_path, 3, "licht", "pink")

def test_das_bild_liegt_vor_der_beschreibung(tmp_path, monkeypatch):
    reihe = []
    echt = atomar.schreibe_atomar
    monkeypatch.setattr(atomar, "schreibe_atomar", lambda p, i, **kw: reihe.append(Path(p).name) or echt(p, i, **kw))
    z.schreibe_lagebild(tmp_path, {"t": 1.0}, b"PNG")
    assert reihe == [z.LAGEBILD_BILD, z.LAGEBILD]
    assert z.lies_lagebild(tmp_path) == {"t": 1.0}
```

- [ ] **Step 2: rot laufen lassen** — `-m pytest tests/test_record_zentrale.py -q` → ImportError.
- [ ] **Step 3: Implementieren** (Code wie im Entwurf; `lies_*` fangen `OSError, ValueError, TypeError, KeyError, IndexError` und geben None).
- [ ] **Step 4: grün** — dieselbe Zeile.
- [ ] **Step 5: Commit** `feat(zentrale): Dateiprotokoll zwischen Tab und Programm`.

### Task 2: Die Skizze `workshop/skizze.py`

**Files:**
- Create: `src/spotlab/workshop/skizze.py`
- Test: `tests/test_workshop_skizze.py`

**Interfaces:**
- Consumes: `backends.base.ObstacleGrid` (cells, cell_size, origin, known).
- Produces: Konstanten `ZELLE_M=0.05, WAND_BIS_M=0.05, ANBAU_M=2.0, MAX_M=60.0, UNBEKANNT=0, FREI=1, WAND=2, FRISCH_S=5.0, ALT_S=60.0`;
  `class Skizze`: `leer` (bool), `ursprung` ((x,y) unten links), `zustand` (uint8 [zeile=y, spalte=x]), `zeit` (float), `zelle_m`;
  `zelle(x, y) -> (zeile, spalte)|None`, `welt(zeile, spalte) -> (x, y)` (Zellmitte), `aufnehmen(gitter, t)`,
  `bild_index(t) -> np.ndarray uint8` (Zeile 0 = oben, Codes wie `record/zentrale.ALTERSSTUFEN`), `png(t) -> bytes` (PIL Modus „P“).

- [ ] **Step 1: Tests** — künstliches `ObstacleGrid` (3 cm, 40×40, Ursprung (0,0), Wandreihe bei y≈0.6 mit Wert 0.0, sonst 1.0, `known` alles wahr ausser einer Ecke):
  - nach `aufnehmen`: Zelle bei (0.5, 0.3) FREI, bei (0.5, 0.6) WAND, unbekannte Ecke UNBEKANNT;
  - zweites Gitter weit weg (Ursprung (10, 10)) → Skizze wächst, alte Zellen bleiben (Zustand an (0.5,0.3) unverändert);
  - dieselbe Stelle später frei gesehen → FREI (neueste gewinnt);
  - `bild_index`: frische Zelle Code 1, 60 s alte Code `ALTERSSTUFEN`, Wand frisch `ALTERSSTUFEN+1`, oben im Bild ist grosses y;
  - Deckel: Gitter 70 m auseinander → Breite ≤ `MAX_M/ZELLE_M` Zellen, das NEUE ist drin;
  - `png()` lässt sich mit PIL öffnen, Modus „P“, Grösse = (breite, hoehe).
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren:**

```python
class Skizze:
    def __init__(self, zelle_m=ZELLE_M):
        self.zelle_m = float(zelle_m)
        self.ursprung = None
        self.zustand = np.zeros((0, 0), np.uint8)
        self.zeit = np.zeros((0, 0), np.float64)

    @property
    def leer(self):
        return self.ursprung is None

    def zelle(self, x, y):
        if self.leer: return None
        s = int(math.floor((x - self.ursprung[0]) / self.zelle_m))
        z = int(math.floor((y - self.ursprung[1]) / self.zelle_m))
        h, b = self.zustand.shape
        return (z, s) if 0 <= z < h and 0 <= s < b else None

    def welt(self, zeile, spalte):
        return (self.ursprung[0] + (spalte + 0.5) * self.zelle_m,
                self.ursprung[1] + (zeile + 0.5) * self.zelle_m)

    def aufnehmen(self, gitter, t):
        werte = np.asarray(gitter.cells, dtype=float)
        bekannt = (np.ones(werte.shape, bool) if gitter.known is None
                   else np.asarray(gitter.known, bool)) & np.isfinite(werte)
        zeilen, spalten = np.nonzero(bekannt)
        if not len(zeilen): return
        xs = gitter.origin[0] + spalten * gitter.cell_size
        ys = gitter.origin[1] + zeilen * gitter.cell_size
        self._decke(xs.min(), ys.min(), xs.max(), ys.max())
        z = np.floor((ys - self.ursprung[1]) / self.zelle_m).astype(int)
        s = np.floor((xs - self.ursprung[0]) / self.zelle_m).astype(int)
        h, b = self.zustand.shape
        drin = (z >= 0) & (z < h) & (s >= 0) & (s < b)
        kleinster = np.full((h, b), np.inf)
        np.minimum.at(kleinster, (z[drin], s[drin]), werte[zeilen[drin], spalten[drin]])
        getroffen = np.isfinite(kleinster)
        self.zustand[getroffen] = np.where(kleinster[getroffen] <= WAND_BIS_M, WAND, FREI)
        self.zeit[getroffen] = t
```
  `_decke(x0, y0, x1, y1)`: Grenzen auf Vielfache von `ANBAU_M`, Vereinigung mit dem Bestehenden, je Achse höchstens `MAX_M` (die Seite fern vom neuen Stück fällt weg), neue Felder anlegen und die Überlappung kopieren. `bild_index`: `stufe = clip((alter-FRISCH_S)/(ALT_S-FRISCH_S)*(ALTERSSTUFEN-1), 0, ALTERSSTUFEN-1)`, Code `FREI→1+stufe`, `WAND→1+ALTERSSTUFEN+stufe`, dann `np.flipud`. `png`: `Image.fromarray(index, "P")`, Graupalette, `PNG` in `BytesIO`.
- [ ] **Step 4: grün.**
- [ ] **Step 5: Commit** `feat(zentrale): wachsende Skizze aus dem Hindernisgitter`.

### Task 3: Wegsuche `workshop/wegsuche.py`

**Files:**
- Create: `src/spotlab/workshop/wegsuche.py`
- Test: `tests/test_workshop_wegsuche.py`

**Interfaces:**
- Consumes: `Skizze` (Task 2).
- Produces: `PLAN_FAKTOR=2`, `KOERPER_M=0.6`; `aufdicken(maske, r) -> bool`, `suche(frei, start, ziel) -> list[(z,s)]|None` (A*, 8 Nachbarn, keine Ecke schneiden), `weg(skizze, start_xy, ziel_xy, rand_m=0.3) -> list[(x,y)]|None` (vereinfacht, letzter Punkt = Ziel genau, Startpunkt nicht enthalten), `pruefe_ziel(skizze, start_xy, ziel_xy, rand_m, max_weite_m) -> str` ("" = gut; sonst „zu weit …“, „unbekannt …“, „in der Wand …“).

- [ ] **Step 1: Tests** — Skizze direkt befüllen (Hilfsfunktion setzt `ursprung=(0,0)`, `zustand` 100×100 FREI, eine Wand x=2.5 von y=0 bis 3.5, Durchgang darüber):
  - `weg((1,1),(4,1))` existiert, jeder Punkt ≥ 0.3 m von der Wand, der Weg geht über y > 3.5;
  - geschlossene Wand → None;
  - `pruefe_ziel`: Ziel in der Wand → „in der Wand“, Ziel unbekannt → „unbekannt“, 6 m weit → „zu weit“, gut → "";
  - Start im Körperschatten (Zellen um den Start UNBEKANNT) → Weg trotzdem;
  - `vereinfacht`: freie Gerade → genau ein Punkt (das Ziel).
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren** — vergröbern um `PLAN_FAKTOR` (Block WAND, wenn eine Wand; FREI, wenn frei und keine Wand; sonst UNBEKANNT), Wände um `ceil(rand/zelle)` aufdicken (Scheibe, gepolstert, keine Umlaufverschiebung), passierbar = FREI & ¬aufgedickt, plus im Umkreis `KOERPER_M` um den Start alles ausser echter Wand; A* mit `heapq`, Kosten 1/√2, Oktil-Heuristik; Sichtlinien-Vereinfachung (Bresenham über passierbar).
- [ ] **Step 4: grün.**
- [ ] **Step 5: Commit** `feat(zentrale): Wegsuche auf der Skizze`.

### Task 4: Klickfahrt `workshop/klickfahrt.py`

**Files:**
- Create: `src/spotlab/workshop/klickfahrt.py`
- Test: `tests/test_workshop_klickfahrt.py`

**Interfaces:**
- Consumes: `wegsuche.weg`, `wegsuche.pruefe_ziel`, `record/fahrt.TEMPO_M_S`, `DREH_RAD_S`.
- Produces: `MAX_WEITE_M=5.0, RAND_M=0.3, ANKUNFT_M=0.25, ZWISCHEN_M=0.3, DREH_AB_GRAD=30.0, LENKUNG=1.5, FREIRAUM_M=0.8, NEU_PLANEN_S=2.0, VERSPERRT_NACH_S=6.0`;
  `Stand(nummer, zustand, grund, ziel, weg)` mit `als_daten() -> dict`;
  `Klickfahrt`: `stand`, `unterwegs` (bool), `neues_ziel(nummer, ziel, lage, skizze, t)`, `abbrechen(grund)`, `schritt(lage, skizze, t, frei_m, faktor=1.0, kopf_frei=True, kopf_grund="") -> (vx, wz)`.

- [ ] **Step 1: Tests** (Skizze aus Task 3):
  - gutes Ziel → `unterwegs`, Weg im Stand; schlechtes → `abgelehnt` mit Grund;
  - Ziel 60° links → erster Schritt vx=0, wz>0; geradeaus → vx>0, wz≈0;
  - Lage auf dem Ziel → `angekommen`, (0,0);
  - `frei_m=0.4` weit vor dem Ziel → (0,0), nach `NEU_PLANEN_S` wird neu geplant, nach `VERSPERRT_NACH_S` → `versperrt`;
  - `frei_m=None` → steht (fail-closed); `kopf_frei=False` → steht, Grund im Stand bei `versperrt`;
  - nah am Ziel langsamer (0.2 m Rest → vx ≤ 0.16); Faktor 0.5 halbiert Höchsttempo;
  - `abbrechen` nur wenn unterwegs.
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren** wie im Entwurf (§5); Restweg entlang der Wegpunkte; nötige Freistrecke `min(FREIRAUM_M, rest + 0.15)`.
- [ ] **Step 4: grün.**
- [ ] **Step 5: Commit** `feat(zentrale): Klickfahrt als reine Rechnung`.

### Task 5: Das Programm `workshop/zentrale.py`

**Files:**
- Create: `src/spotlab/workshop/zentrale.py`
- Test: `tests/test_workshop_zentrale.py`

**Interfaces:**
- Consumes: Tasks 1–4, `folgen._lage_im_gitter`, `folgen.kopfraum_frei`, `record/fahrt.lies/STILL/faktor_der_stufe`, `workshop/blick.starte`, `api/signals.Statuslicht`.
- Produces: `SKRIPT` (Path dieser Datei), `TAKT_S=0.05, WAHRNEHMUNG_S=0.5, KOPFRAUM_S=1.0, GITTER_GILT_S=1.5`, `LICHTFARBEN={"blau":"blue","gruen":"green","gelb":"yellow","rot":"red"}`;
  `class Zentrale(spot, lauf_dir, jetzt=time.time, melde=print)` mit `wahrnehmen(t=None)`, `takt(t=None)`, `lauf(laeuft, schlaf=time.sleep, takt_s=TAKT_S, mit_blick=True)`, `faehigkeiten` (dict licht/ton/kamera);
  `argumente(argv) -> (runs, uebernehmen)`, `_hauptprogramm(argv=None)`.

- [ ] **Step 1: Tests** mit Attrappen-Spot (walk/stop merken, `obstacles()` liefert ein Gitter, `backend.frame_tree_snapshot` wie `test_workshop_folgen._baum`, `tags()`, `supports()`):
  - `wahrnehmen` schreibt `lagebild.json` + `lagebild.png` mit `spot`, `tags` (Weltlage), `faehigkeiten`, `klickfahrt.zustand == "keine"`, `menschen == []`, `karte is None`;
  - ohne Gitter (`obstacles` wirft) → Lagebild ohne Bild, `breite == 0`, einmal gemeldet;
  - Taste in `fahrt.json` → `walk`; eine laufende Klickfahrt wird `abgebrochen`;
  - Klickziel mit frischem `lebt` → Weg, `walk` mit vx>0 nach Drehung; `lebt` alt → `abgebrochen`, `stop`;
  - Aktion Licht bei `supports("lights")` falsch → nichts gesendet, einmal gemeldet; mit Licht-Attrappe → `setze("green")`; neue Nummer genau einmal;
  - `lauf()` hält am Ende an (`stop` vor Licht aus);
  - `argumente(["--runs","X","--uebernehmen"]) == ("X", True)`, unbekannte Option → `SpotlabError`;
  - Kette im 2D-Übungsraum in-process: `spotlab.connect(backend="sim", raum="durchgang", runs_dir=tmp)`, erst Klick nach (3.3, 2.0) (sichtbar), nach Ankunft Klick nach (5.3, 3.0) (hinter der Wand x=4.5, Tür bei y 1.5–2.4) → `angekommen`, keine `angestossen`-Ereignisse; Stufe „schnell“, Abbruch über `TEST_TIMEOUT_S`.
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren** wie im Entwurf (§3, §6, §7): Wahrnehmung im Faden unter einer Sperre (Skizze, Gitter, Lage, Tags als `{id: (x, y)}` — gemerkt über die Fahrt, Kopfraum alle `KOPFRAUM_S`), `takt` mit Vorrang Taste > Klickfahrt > Stillstand, Klickschritt unter der Sperre mit `frei_m = gitter.free_distance(x, y, grad)` aus dem letzten Gitter (älter als `GITTER_GILT_S` → None), Kopfraum nie gemessen oder älter als 3 s → `kopf_frei=False`. `_hauptprogramm`: `--runs`, `--uebernehmen`, `spotlab.connect(runs_dir=runs, script=__file__, take=uebernehmen)`, `power_on()`, `stand()`, Ausgabezeile mit den Tasten, `Zentrale(...).lauf(laeuft=Stoppdatei)`, `sit()`.
- [ ] **Step 4: grün** (die Kette dauert einige Sekunden Echtzeit).
- [ ] **Step 5: Commit** `feat(zentrale): das Programm -- Wahrnehmung, Tasten, Klickfahrt, Licht und Ton`.

### Task 6: Das Draufsicht-Widget `gui/lagebild.py`

**Files:**
- Create: `src/spotlab/gui/lagebild.py`
- Test: `tests/test_gui_lagebild.py`

**Interfaces:**
- Consumes: `record/zentrale.ALTERSSTUFEN`, `gui/theme` (Palette, `mische`).
- Produces: `class Lagebild(QWidget)` mit Signal `klick(float, float)`, `setze_palette(p)`, `zeige(daten:dict, bilddaten:bytes|None)`, `leeren()`, `mitte()`, `welt_zu_schirm(x,y) -> QPointF`, `schirm_zu_welt(px,py) -> (x,y)`, `folgt` (bool: Ansicht folgt Spot).

- [ ] **Step 1: Tests** (offscreen, Widget 400×400 festhalten):
  - `zeige` mit Spot bei (2,3) → `welt_zu_schirm(2,3)` ist die Mitte;
  - Linksklick ohne Ziehen an der Stelle von (2.5, 3.0) → `klick` mit (2.5, 3.0) ±Zelle;
  - Ziehen verschiebt (kein Klick-Signal), `folgt` wird falsch; `mitte()` → wieder wahr;
  - Mausrad zoomt um den Zeiger (der Weltpunkt unter dem Zeiger bleibt);
  - `zeige` mit PNG (aus `Skizze.png`) → `grab()` wirft nicht, das Bild hat eine Farbtabelle aus der Palette (Pixel an einer Wandzelle ≠ Hintergrund);
  - keine Farbliterale: `test_gui_theme`-Muster (Quelltext enthält kein `#` gefolgt von Hex und kein `QColor(<zahl>`).
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren** — Transformation aus `_mitte` (Welt) und `_px_je_m`; Bild über `QImage.loadFromData` → `setColorTable` (Index 0 durchsichtig, frei = `mische(flaeche, text, 0.18)` mit Alpha 255→110 über die Stufen, Wand = `text`), gezeichnet in das Weltrechteck aus `ursprung`, `zelle_m`, `breite`, `hoehe`; darüber Weg (`warnung`), Ziel (`akzent`, bei `abgelehnt` `gefahr`), Tags (`akzent`, Nummer), Spot-Pfeil (`ok`). Klick vs. Ziehen: Bewegung > 4 px heisst Ziehen.
- [ ] **Step 4: grün.**
- [ ] **Step 5: Commit** `feat(zentrale): Draufsicht-Widget`.

### Task 7: Der Tab wird zur Steuerzentrale (`gui/views/fahren.py`)

**Files:**
- Modify: `src/spotlab/gui/views/fahren.py`
- Test: `tests/test_gui_fahren.py` (neue Tests + Anpassungen)

**Interfaces:**
- Consumes: Task 1 (`schreibe_klickziel`, `schreibe_aktion`, `lies_lagebild`, `LAGEBILD_BILD`), Task 6 (`Lagebild`).
- Produces: `FahrenView(palette=None)`; `ort() -> "uebungsraum"|"real"`; `HERZSCHLAG_MS=200`; bestehende Signale unverändert (`fahrt_gewuenscht(bool)`, `stopp_gewuenscht`, `lage_gewuenscht`, `meldung`).

- [ ] **Step 1: Tests:**
  - Vorgabe `ort() == "uebungsraum"`; die Sicherheitszeile „Echter Spot“ steht nur bei „Echter Spot“;
  - im Lauf: Klick im Lagebild → `klickziel.json` mit Nummer 1, Ziel, Stufe; der Herzschlag frischt `lebt` auf (Timer von Hand auslösen: `tab._herzschlag()`), nicht bei unsichtbarem Tab;
  - Taste W nach einem Klick → neues Klickziel mit `ziel: null`;
  - Licht-Wahl „grün“ → `aktion.json` licht/gruen; „Piep“ → ton; beide grau, bis `lagebild.json` `faehigkeiten` wahr meldet;
  - `lagebild.json` + PNG im Lauf-Verzeichnis → `tab._lade_lagebild()` zeigt es, die Zeile „Klickfahrt: …“ spricht den Zustand;
  - `lauf_beendet` leert Lagebild und Herzschlag.
  - Bestehende Tests: Titel/Knopftexte anpassen, wo sie „fahren.py“ oder „Den echten Spot…“ erwarten.
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren** — Auswahl `ort` oben (Übungsraum Vorgabe), links `Lagebild` (Stretch 3) mit Knopf „⌖ Mitte“, rechts Kamerabild, Tastenfeld, Befehlszeile, Gruppe „Licht und Ton“ (Farbwahl + „🔔 Piep“), Zeile Klickfahrt; `QTimer` `HERZSCHLAG_MS`: Herzschlag (nur Lauf + sichtbar + App aktiv + Nummer>0) und `_lade_lagebild` (nur bei neuer Änderungszeit von `lagebild.json`); `keyPressEvent`: nach einer gefahrenen Taste laufende Klickfahrt abbrechen (`ziel=None`, neue Nummer).
- [ ] **Step 4: grün** (`tests/test_gui_fahren.py`).
- [ ] **Step 5: Commit** `feat(zentrale): der Tab Fahren wird zur Steuerzentrale`.

### Task 8: Start über die App (`gui/app.py`)

**Files:**
- Modify: `src/spotlab/gui/app.py`
- Test: `tests/test_gui_app.py`

**Interfaces:**
- Consumes: Task 5 (`zentrale.SKRIPT`), Task 7 (`ort()`).
- Produces: `MainWindow._starte_zentrale(uebernehmen)`; Merker `_fahrt_erwartet == "zentrale"` (ersetzt `"real"`).

- [ ] **Step 1: Tests:**
  - Knopf mit `ort=real` → `starte_skript(zentrale.SKRIPT, "real", ["--runs", <ws>/Beispiele/runs, ...])`, `--uebernehmen` nur mit Häkchen;
  - `ort=uebungsraum` → Backend `_virtuelles_backend()`, nie `--uebernehmen`, KEIN Übungsfenster;
  - der Lauf landet im Tab (`lauf_beginnt`), Startfehler im Tab;
  - Kette (wie `test_der_tab_fahren_faehrt_wirklich_ueber_knopf_watcher_und_tasten`): `ort=real` mit `FAHREN_BACKEND="dryrun"` → W wird `walk`;
  - Kette im 2D-Übungsraum: Raum „durchgang“ im Raumeditor, Knopf, Lauf, Klick im Lagebild nach (2.5, 2.0) → `lagebild.json` meldet `angekommen`.
  - Bestehende Tests auf `zentrale.SKRIPT` und `"zentrale"` umstellen.
- [ ] **Step 2: rot.**
- [ ] **Step 3: Implementieren** — `_starte_zentrale`, `_lauf_aus_code` ohne Übungsfenster bei `"zentrale"`, `_uebernimm_lauf` und Startfehler auf `"zentrale"`, `FahrenView(self._palette)`; `_starte_fahrt` nur noch virtuell (Raumeditor).
- [ ] **Step 4: grün** (`tests/test_gui_app.py`, `tests/test_gui_fahren.py`).
- [ ] **Step 5: Commit** `feat(zentrale): Start aus dem Tab, Uebungsraum als Vorgabe`.

### Task 9: Doku, Abnahme, ganze Suite, Merge

**Files:**
- Modify: `CLAUDE.md` (neuer Punkt „Die Steuerzentrale …“ bei den Fahren-Regeln), `docs/ABNAHME.md` (A38)

- [ ] **Step 1:** `CLAUDE.md`: Programm/Protokoll/Skizze/Klickfahrt in fünf Sätzen samt Totmann, Vorgabe Übungsraum, Paketcode. `docs/ABNAHME.md`: A38 (Skizze im echten Gang, Klick in freien Boden, Klick hinter eine Ecke, Klick in die Wand → abgelehnt, Taste bricht ab, Reiterwechsel hält an, Licht, Piep).
- [ ] **Step 2:** `-m ruff check .` und volle Suite grün.
- [ ] **Step 3:** Commit, ff-merge nach `main`, Worktree entfernen.
