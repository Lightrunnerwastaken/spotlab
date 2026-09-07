# Gelände, Etappe 2 „Sichten" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das Gelände ist in 2D (Relief mit Höhenlinien, Ebenen), in 3D (Dreiecksnetz), in MuJoCo (hfield, Puppe Fassung 5) und im Editor (Listenzeile, verschieben, heben, löschen) da; die 2D-Sicht kann Strecken markieren und offene Ränder zeigen.

**Architecture:** `theme.mische` mischt Palettenfarben; `raumzeichnung.gelaende_bild` rendert einmal je Raum ein `QImage`, `Sicht2D` zeichnet es skaliert; `geometrie3d.gelaende_dreiecke` liefert Dreiecke je Höhenband, `kaesten_aus_raum` hängt sie vor die Böden; die Puppe baut ein `hfield`; `bearbeitung` kennt den Schlüssel `("gelaende", 0)`.

**Tech Stack:** PySide6 (offscreen in Tests), OpenGL wie bisher, MuJoCo 3.9 `mjSpec` (matura-spot), numpy in `backends/`.

**Spec:** `docs/superpowers/specs/2026-09-07-korrigierer-gelaende-design.md` (§ 4, 5)

## Global Constraints

- Farben nur aus `gui/theme.py`; Mischen nur über `theme.mische`.
- Kein `mujoco`/`spotsim` unter `gui/`; nur `backends/mujoco.py` importiert `spotsim`.
- Puppe: `FASSUNG = 5` in matura-spot, `PUPPE_FASSUNG = 5` in spotlab; beide Repos im selben Schritt.
- `kaesten_fuer` bleibt die einzige Zerlegung der Böden; das Gelände kommt daneben als Dreiecke bzw. hfield.
- Tests: spotlab im Worktree `PYTHONPATH=src /c/Users/janis/miniconda3/python.exe -m pytest -q -p no:cacheprovider`; matura-spot im Hauptcheckout auf Branch `feat/puppe-fassung-5` mit demselben Interpreter (spotsim ist dort editierbar installiert).

---

### Task 1: `theme.mische` und das Geländebild

**Files:** Modify `src/spotlab/gui/theme.py`, `src/spotlab/gui/raumzeichnung.py`; Test `tests/test_gui_theme.py` (anlegen, falls es fehlt), `tests/test_gui_raumzeichnung.py`.

**Interfaces:** Produces `theme.mische(a: str, b: str, t: float) -> str` (Hex „#rrggbb"); `raumzeichnung.HOEHENLINIE_M = 0.25`, `raumzeichnung.EBENE_TOLERANZ_M = 0.3`, `raumzeichnung.gelaende_bild(gelaende, palette, ebene=None) -> QImage` (Breite `spalten`, Höhe `zeilen`, Zeile 0 oben = Knotenzeile `zeilen − 1`, Format ARGB32, Alpha 200, ohne Boden Alpha 0); `raumzeichnung.gelaende_rechteck(gelaende) -> (x_min, y_min, x_max, y_max)` = Knotengitter plus halbe Zelle.

- [ ] **Step 1: Tests**

```python
# test_gui_theme.py
def test_mische_liegt_dazwischen():
    assert mische("#000000", "#ffffff", 0.5) == "#808080"
    assert mische("#102030", "#102030", 0.7) == "#102030"

# test_gui_raumzeichnung.py
def _gelaende(f):
    from spotlab.welt import gelaende as g
    return g.gitter(0.0, 0.0, 0.2, 4, 6, f)


def test_das_bild_hat_die_knotenmasse_und_zeile_0_oben():
    bild = gelaende_bild(_gelaende(lambda x, y: y), DUNKEL)        # steigt nach +y
    assert (bild.width(), bild.height()) == (6, 4)
    oben, unten = QColor(bild.pixel(0, 0)), QColor(bild.pixel(0, 3))
    assert oben.lightness() > unten.lightness()                    # hoch = hell (gedaempft) oben


def test_ohne_boden_durchsichtig_und_hoehenlinie_gedaempft():
    bild = gelaende_bild(_gelaende(lambda x, y: None if x < 0.3 else (0.0 if x < 0.7 else 0.3)), DUNKEL)
    assert QColor(bild.pixel(0, 0)).alpha() == 0
    # Spalte 3 (x = 0.6, Hoehe 0.0) grenzt rechts an 0.3: floor(0/0.25)=0 != floor(0.3/0.25)=1
    assert QColor(bild.pixel(3, 0)).name() == DUNKEL.gedaempft


def test_ausserhalb_der_ebene_blass():
    bild = gelaende_bild(_gelaende(lambda x, y: 0.0 if x < 0.5 else 1.0), DUNKEL, ebene=0.0)
    assert QColor(bild.pixel(5, 0)).name() == DUNKEL.blass
    assert QColor(bild.pixel(0, 0)).name() != DUNKEL.blass


def test_das_rechteck_reicht_eine_halbe_zelle_ueber_die_knoten():
    assert gelaende_rechteck(_gelaende(lambda x, y: 0.0)) == pytest.approx((-0.1, -0.1, 1.1, 0.7))
```

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** wie Spec § 4 (Farbe `mische(flaeche, gedaempft, 0.15 + 0.45·t)`, `t` aus min/max der gültigen Knoten, bei gleicher Höhe `t = 0`; `setPixelColor(j, zeilen-1-i, farbe)`). - [ ] **Step 4: Grün.** Commit `feat(gui): Gelaendebild mit Hoehenlinien und Ebenen, theme.mische`.

### Task 2: `Sicht2D` zeichnet das Gelände, Markierungen, offene Ränder

**Files:** Modify `src/spotlab/gui/raumeditor/sicht2d.py`, `src/spotlab/gui/raumzeichnung.py` (`zeichne_strecken`, `zeichne_offen`); Test `tests/test_gui_raumeditor_sicht2d.py`.

**Interfaces:** Produces `Sicht2D.setze_markierung(strecken)`, `.setze_kandidaten(strecken)`, `.setze_offen(punkte)`; `raumzeichnung.zeichne_strecken(maler, strecken, meter_zu_schirm, farbe, breite, enden)`; `raumzeichnung.zeichne_offen(maler, punkte, meter_zu_schirm, palette)`.

- [ ] **Step 1: Tests** — `zeige(raum_mit_gelaende)` und `grab()` laufen ohne Fehler und das Pixel in der Geländemitte ist nicht die Hintergrundfarbe; nach `zeige` mit einem anderen Gelände wird das Bild neu gebaut (`sicht._gelaende_schluessel` ändert sich); `setze_markierung([(0, 0, 1, 1)])`, `setze_kandidaten`, `setze_offen([(0.5, 0.5)])` + `grab()` ohne Fehler; `tab._setze` leert alle drei (Test in `test_gui_raumeditor.py`).
- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren:** Bild-Cache `(id(gelaende), ebene)` mit Referenz auf das Gelände; `paintEvent`: nach `_raster`, vor Pauspapier `drawImage(QRectF(px_min, py_oben, breite, hoehe), bild)` mit Ecken aus `gelaende_rechteck` durch `meter_zu_schirm`; nach `zeichne_raum`: Kandidaten (gedaempft, 1 px, `Qt.DashLine`), Markierung (akzent, 2 px, Dash, Kreise r = 5 px an den Enden), offene Ränder (warnung, r = 3 px). - [ ] **Step 4: Grün.** Commit `feat(gui): 2D-Sicht mit Gelaende, Markierung und offenen Raendern`.

### Task 3: 3D-Dreiecke

**Files:** Modify `src/spotlab/gui/raumeditor/geometrie3d.py`, `src/spotlab/gui/raumeditor/sicht3d.py`; Test `tests/test_gui_raumeditor_geometrie3d.py`.

**Interfaces:** Produces `geometrie3d.gelaende_dreiecke(gelaende, band_m=0.25) -> [(band: int, vertices: list[float])]` (je Vertex x, y, z, nx, ny, nz; Bänder aufsteigend); `kaesten_aus_raum` liefert zuerst `(("gelaende", band), vertices)`; `Sicht3D._elementfarbe(("gelaende", k))` = `mische(rand, text, min(0.35, 0.05·k))`; `Sicht3D.treffer` gibt für Gelände-Schlüssel `None`.

- [ ] **Step 1: Tests**

```python
def test_zwei_dreiecke_je_voller_zelle_und_eins_bei_drei_knoten():
    from spotlab.welt import gelaende as g
    voll = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.0)
    assert sum(len(v) for _b, v in gelaende_dreiecke(voll)) == 2 * 3 * 6
    drei = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: None if (x, y) == (1.0, 1.0) else 0.0)
    assert sum(len(v) for _b, v in gelaende_dreiecke(drei)) == 1 * 3 * 6


def test_die_normale_zeigt_nach_oben_und_das_band_stimmt():
    from spotlab.welt import gelaende as g
    ge = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.6)
    (band, v), = gelaende_dreiecke(ge)
    assert band == 2 and v[5] > 0.99


def test_kaesten_aus_raum_beginnt_mit_dem_gelaende():
    from spotlab.welt import gelaende as g
    raum = Raum("G", "", (0.5, 0.5, 0.0), gelaende=g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.0))
    assert kaesten_aus_raum(raum, frozenset())[0][0] == ("gelaende", 0)
```

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** (Zelle a=(i,j), b=(i,j+1), c=(i+1,j+1), d=(i+1,j): (a,b,c),(a,c,d); drei gültige → das eine Dreieck gegen den Uhrzeigersinn; Normale = normiertes Kreuzprodukt, bei nz < 0 umdrehen; Band `floor(Mittelhöhe / band_m)`; `sicht3d.treffer`: Schlüssel `("gelaende", …)` → `None`). - [ ] **Step 4: Grün.** Commit `feat(gui): Gelaende als Dreiecksnetz in der 3D-Sicht`.

### Task 4: Bearbeitung, Steuerung, Tab

**Files:** Modify `src/spotlab/welt/bearbeitung.py`, `src/spotlab/gui/raumeditor/steuerung.py`, `src/spotlab/gui/raumeditor/tab.py`; Test `tests/test_welt_bearbeitung.py`, `tests/test_gui_raumeditor_steuerung.py`, `tests/test_gui_raumeditor.py`.

**Interfaces:** Produces `bearbeitung.GELAENDE = ("gelaende", 0)`, `FELDER["gelaende"] = ()`; `element`, `lage`, `verschiebe`, `hebe`, `loesche` kennen ihn; `drehe`, `skaliere`, `dupliziere`, `ziehe_ecke`, `treffer` übergehen ihn; `Steuerung.alle()` enthält ihn bei Gelände; `tab._beschrifte` → `zusammenfassung`; Eigenschaften: zwei `QLabel`.

- [ ] **Step 1: Tests**

```python
# test_welt_bearbeitung.py
def test_das_gelaende_verschiebt_hebt_und_loescht_sich():
    from spotlab.welt import gelaende as g
    raum = Raum("G", "", (0.5, 0.5, 0.0), gelaende=g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: 0.1))
    r2 = verschiebe(raum, {GELAENDE}, 1.0, 0.0)
    assert r2.gelaende.x0 == 1.0
    r3 = hebe(r2, {GELAENDE}, 0.5)
    assert r3.gelaende.knoten(0, 0) == pytest.approx(0.6)
    assert drehe(r3, {GELAENDE}, 90.0).gelaende == r3.gelaende
    assert loesche(r3, {GELAENDE})[0].gelaende is None
    assert treffer(r3, 1.5, 0.5) is None

# test_gui_raumeditor_steuerung.py
def test_alle_enthaelt_das_gelaende():
    ...  assert GELAENDE in st.alle()

# test_gui_raumeditor.py
def test_die_liste_zeigt_das_gelaende_und_entf_loescht_es(editor):
    ... "Gelände ·" in Listentexten; Auswahl + taste("Entf"/"delete" wie im Tab) -> raum.gelaende is None
```

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** (`_ersetze` für "gelaende" → `replace(raum, gelaende=neu)`; `lage` = Mitte des Umrisses; Tab `_fuelle_eigenschaften`: `if schluessel[0] == "gelaende": addRow(QLabel(zusammenfassung)); addRow(QLabel("gerechnet aus Wänden, Weg und Pauspapier — nicht von Hand zu ändern")); return`; `_zeige`: Klippen bei Böden oder Gelände). - [ ] **Step 4: Grün.** Commit `feat(editor): das Gelaende in Liste, Eigenschaften und Blender-Tasten`.

### Task 5: Puppe Fassung 5 (matura-spot)

**Files:** Modify `src/spotsim/puppe.py`; Test `tests/test_puppe.py`; `notes/` falls die Puppe dort beschrieben ist (Fassung nennen).

**Interfaces:** Produces `puppe.Gelaende(x0, y0, zelle, hoehen: np.ndarray)` (frozen dataclass, `eq=False`), `Welt.gelaende: Gelaende | None = None`, hfield `gelaende` in `bau_modell`, `BEGEHBAR += ("gelaende",)`, `FASSUNG = 5`.

- [ ] **Step 1: Tests**

```python
def _gelaende_nach_y():
    hoehen = np.array([[0.1 * i] * 5 for i in range(5)])      # steigt nach +y, 0..0.4
    return Gelaende(1.0, 2.0, 0.5, hoehen)


def _hoehe_per_strahl(model, data, x, y):
    geomid = np.zeros(1, dtype=np.int32)
    d = mujoco.mj_ray(model, data, np.array([x, y, 5.0]), np.array([0.0, 0.0, -1.0]), None, 1, -1, geomid)
    return 5.0 - d, mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(geomid[0]))


def test_das_hfield_liegt_richtig_herum():
    model, data = bau_modell(Welt(gelaende=_gelaende_nach_y()))
    mujoco.mj_forward(model, data)
    for (x, y), soll in (((1.0, 2.0), 0.0), ((2.0, 3.5), 0.3), ((3.0, 4.0), 0.4)):
        z, name = _hoehe_per_strahl(model, data, x, y)
        assert name == "gelaende" and z == pytest.approx(soll, abs=0.01)


def test_ein_ebenes_gelaende_braucht_kein_hfield():
    model, _ = bau_modell(Welt(gelaende=Gelaende(0.0, 0.0, 0.5, np.zeros((3, 3)))))
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "gelaende") == -1


def test_die_fassung_ist_5():
    assert FASSUNG == 5
```

Dazu den bestehenden Test `FASSUNG == 4` auf 5 heben und den Kontakt-Test (Berührung mit `gelaende` zählt nicht als Anstoss) neben dem Test für `BEGEHBAR` ergänzen.

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** wie Spec § 4 (`spec.add_hfield()`, `nrow`, `ncol`, `size = [rx, ry, z_max, 0.05]`, `userdata = (clip(hoehen − boden_z, 0) / z_max).ravel()`; Body `gelaende` bei `(x0 + rx, y0 + ry, boden_z)`, Geom `mjGEOM_HFIELD`, `hfieldname = "gelaende"`, `name = "gelaende"`). Stellt der Strahltest die Zeilen verkehrt fest, `hoehen[::-1]` schreiben und den Grund als Kommentar nennen. - [ ] **Step 4: Grün, ganze matura-spot-Suite grün, ruff.** Commit in matura-spot `feat(puppe): Fassung 5 -- Gelaende als hfield`.

### Task 6: MuJoCo-Backend mit Gelände

**Files:** Modify `src/spotlab/backends/mujoco.py` (`PUPPE_FASSUNG`, `welt_aus_raum`); Test `tests/test_backend_mujoco.py`.

- [ ] **Step 1: Tests** — `PUPPE_FASSUNG == 5`; `welt_aus_raum(raum_mit_gelaende, puppe)` liefert `welt.gelaende` mit `hoehen.shape == (zeilen, spalten)`, NaN wo `None`; ohne Gelände `None`. Die bestehenden Tests nutzen das echte `spotsim.puppe` oder einen Ersatz — nachlesen, gleich verfahren.
- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** wie Spec § 4. - [ ] **Step 4: Grün** (inklusive `tests/test_naht_spotsim.py`). Commit `feat(mujoco): Gelaende in die Puppenwelt, Fassung 5`.

### Task 7: Abschluss Etappe 2

- [ ] Ein Bild: Raum `treppe` plus ein synthetisches Gelände (Rampe 4°) in 2D und 3D aus dem Editor (offscreen, `grab()`), an den Autor. Suite und ruff beider Repos grün. `CLAUDE.md` Umsetzungsstand „Etappe 2". Commit `docs: Stufe 14 Etappe 2 -- Gelaende in allen Sichten`.
