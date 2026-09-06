# Höhe, Etappe 2 „Editor" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Böden im Raumeditor bauen (Werkzeug, Griffe, Felder, Heben mit Z-Sperre), Ebenen in der 2D-Sicht wählen (andere Ebenen blass), Böden, Stufen und Klippen zeichnen, in 3D dieselben Kästen wie in MuJoCo sehen; das Übungsfenster zeigt Böden und die Höhe des Laufs.

**Architecture:** Alle Operationen in `welt/bearbeitung.py` (ohne Qt), die `Steuerung` hält `ebene`, die Sichten zeichnen; die Kastenzerlegung kommt aus `welt/hoehe.py::kaesten_fuer`.

**Tech Stack:** stdlib, PySide6 (offscreen in Tests), OpenGL nur in `sicht3d.py`.

**Spec:** `docs/superpowers/specs/2026-09-06-hoehe-treppen-design.md` (§ 5)

## Global Constraints

- Farben nur aus `gui/theme.py` — neues Feld `Palette.blass` in DUNKEL und HELL.
- Der Editor arbeitet auf unveränderlichen Räumen; jede Operation gibt einen neuen `Raum`.
- Die Qt-Tests prüfen nur die Haut; jeder Bedienfall ist ein `Steuerung`-Test.

---

### Task 1: Bearbeitung — Boden-Operationen, `hebe`, Felder, Prüfungen

**Files:** Modify `src/spotlab/welt/bearbeitung.py`; Test `tests/test_welt_bearbeitung.py`.

**Interfaces:** `neuer_boden(raum, x, y, breite, tiefe, z=0.0, anstieg=0.0, stufen=0, name=None)`, `hebe(raum, auswahl, dz)`, Schlüssel `("boden", i)` in `element`, `lage`, `mitte`, `_ersetze`, `verschiebe`, `drehe`, `skaliere`, `dupliziere`, `loesche`, `treffer`, `im_rahmen`, `griffe`, `ziehe_ecke`, `drehring_lage`; `FELDER["boden"] = ("name", "x", "y", "breite", "tiefe", "z", "anstieg", "stufen", "drehung")`, `FELDER["wand"] += ("z",)`, Block/Tag `+= ("z",)`; `pruefe` mit Kante, Fläche, Stufenhöhe.

- [ ] **Tests** (Auszug):

```python
def test_ein_boden_wird_gesetzt_gehoben_und_gefunden():
    raum = b.neuer_boden(LEER, 2, 2, 2, 1, z=0.0)
    assert raum.boeden[0].name == "Boden 1" and b.treffer(raum, 2, 2) == ("boden", 0)
    raum = b.hebe(raum, {("boden", 0)}, 0.5)
    assert raum.boeden[0].z == 0.5
    raum = b.setze_feld(raum, ("boden", 0), "stufen", 4)
    raum = b.setze_feld(raum, ("boden", 0), "anstieg", 0.8)
    assert raum.boeden[0].art == "treppe"

def test_pruefe_nennt_kante_und_zu_hohe_stufe():
    raum = Raum(name="H", beschreibung="", start=(2.9, 0, 0),
                boeden=(Boden("P", 2, 0, 2, 2, z=1.0), Boden("T", 5, 0, 1, 1, anstieg=1.0, stufen=2)))
    hinweise = b.pruefe(raum)
    assert any("Kante" in h for h in hinweise) and any("0.50 m je Stufe" in h for h in hinweise)
```

- [ ] **Implement**; Rang `{"start": 0, "tag": 1, "block": 2, "boden": 3, "wand": 4}`; `hebe` lässt Start aus; `skaliere` skaliert `anstieg` nicht.
- [ ] **Commit** `feat(bearbeitung): Boeden bauen, heben, pruefen`.

### Task 2: Steuerung — Werkzeug „boden", Ebene, Z-Sperre

**Files:** Modify `src/spotlab/gui/raumeditor/steuerung.py`, `src/spotlab/welt/bearbeitung.py::Modus`; Test `tests/test_gui_raumeditor_steuerung.py`, `tests/test_welt_bearbeitung.py`.

- [ ] **Tests:** Werkzeug boden zieht ein Rechteck → `raum.boeden[0]` mit `z == steuerung.ebene`; `setze_ebene(1.2)`, dann Block → `z == 1.2`; `taste("g")`, `taste("z")`, `bewege(x, y+0.5)` → Vorschau hebt um 0.5 (Raster), `taste("return")` übernimmt; `hinweise()` enthält die Kante.
- [ ] **Implement:** `WERKZEUGE += ("boden",)`; `Steuerung.ebene = None`; `Modus.achse == "z"` in `vorschau` → `hebe(raum, auswahl, raste(dy))`.
- [ ] **Commit** `feat(raumeditor): Werkzeug Boden, Ebene, Heben mit Z-Sperre`.

### Task 3: Theme und Zeichnung — Ebene blass, Böden, Stufen, Klippen

**Files:** Modify `src/spotlab/gui/theme.py`, `src/spotlab/gui/raumzeichnung.py`, `src/spotlab/gui/raumplot.py`; Tests `tests/test_gui_raumzeichnung.py`, `tests/test_gui_theme.py` (falls vorhanden, sonst in raumzeichnung).

- [ ] **Tests:** `zeichne_raum(..., ebene=1.2)` zeichnet die Wand bei z=0 mit `palette.blass` (Attrappen-Maler sammelt Stiftfarben); Boden mit Stufen erzeugt `stufen` Linien; Klippen kommen als Kammlinie in `warnung`; `raumplot.grab()` mit Böden stürzt nicht.
- [ ] **Implement:** `Palette.blass` (dunkel: `#3a3f4a`, hell: `#d0d4da` — Farbe ins Theme, nicht in den Maler); `zeichne_raum(maler, raum, meter_zu_schirm, skala, palette, auswahl=frozenset(), ebene=None, klippen_=())`; Böden zuerst (unter allem), Pfeil und Beschriftung; Stufenlinien.
- [ ] **Commit** `feat(gui): Boeden, Stufen und Klippen zeichnen, andere Ebenen blass`.

### Task 4: 2D-Sicht und Tab — Ebenenwahl

**Files:** Modify `src/spotlab/gui/raumeditor/sicht2d.py`, `src/spotlab/gui/raumeditor/tab.py`; Tests `tests/test_gui_raumeditor_sicht2d.py`, `tests/test_gui_raumeditor.py`.

- [ ] **Tests:** `tab.ebenenwahl` listet „alle", „0.00 m", „1.20 m" für einen Raum mit Podest; Wahl „1.20 m" → `steuerung.ebene == 1.2`; Werkzeug Block danach → `z == 1.2`; Eigenschaften zeigen Feld `feld_z` und für Böden `feld_anstieg`, `feld_stufen`.
- [ ] **Implement:** `Sicht2D.zeige(..., ebene=None, klippen_=())`; `RaumeditorView.ebenenwahl: QComboBox` im Kopf neben dem Umschalter, gespeist in `_zeige()` aus `ebenen(raum)` (Sperre gegen Rückkopplung wie `_liste_sperre`); Zahlenfelder aus `FELDER`.
- [ ] **Commit** `feat(raumeditor): Ebenenwahl in der 2D-Sicht, Felder fuer Hoehe`.

### Task 5: 3D — Kästen mit Neigung, Raster auf `boden_z`

**Files:** Modify `src/spotlab/gui/raumeditor/geometrie3d.py`, `src/spotlab/gui/raumeditor/sicht3d.py` (Aufrufe); Test `tests/test_gui_raumeditor_geometrie3d.py`.

- [ ] **Tests:** `kasten(..., pitch_grad=30)` hebt das +x-Ende; `kaesten_aus_raum` enthält `("boden", i)`-Schlüssel je Kasten eines Bodens (mehrere Kästen, ein Schlüssel) mit denselben Mitten wie `kaesten_fuer`; `bodenraster(huelle, z=-1.0)` liegt bei z=−1; Spot am Start steht auf `boden_bei(start)`.
- [ ] **Implement:** `kasten(x, y, z, hx, hy, hz, yaw_grad=0.0, pitch_grad=0.0)` (erst Nick um y, dann Yaw); `kaesten_aus_raum` nutzt `kaesten_fuer(boden, boden_z(raum))`; Farb-ID-Auswahl: ein Boden hat mehrere Kästen, alle mit seinem Index — `Sicht3D` mappt Vertex-Gruppen auf Schlüssel wie bisher.
- [ ] **Commit** `feat(raumeditor): 3D mit Boeden, Stufen, Rampen und Raster auf der tiefsten Ebene`.

### Task 6: Übungsfenster — Böden und Höhe des Laufs

**Files:** Modify `src/spotlab/gui/uebungsfenster.py`, `src/spotlab/gui/raumplot.py`, `src/spotlab/gui/app.py::_zustand` (wo `zeige_pose` gerufen wird); Test `tests/test_gui_uebungsfenster.py`.

- [ ] **Tests:** `zeige_pose(x, y, grad, z=1.2, nick=12.0)` → Zeile enthält „Höhe 1.20 m" und „Neigung 12°"; Plot mit Böden `grab()`.
- [ ] **Implement:** `zeige_pose(..., z=None, nick=None)`; app.py reicht `daten.get("z")`, `daten.get("pitch")` (Bogenmass → Grad) durch.
- [ ] **Commit** `feat(uebungsfenster): Boeden zeichnen, Hoehe und Neigung des Laufs zeigen`.

### Task 7: Abschluss

- [ ] Suite und ruff; `CLAUDE.md` Umsetzungsstand „Etappe 2"; README-Abschnitt Raumeditor um Böden und Ebenen ergänzen (Bedienung: Werkzeug Boden, Zahlenfelder z/anstieg/stufen, Ebenenwahl, G dann Z). Commit `docs: Stufe 13 Etappe 2 -- Editor mit Ebenen`.
