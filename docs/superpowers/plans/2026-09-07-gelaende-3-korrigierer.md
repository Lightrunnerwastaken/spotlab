# Gelände, Etappe 3 „Korrigierer" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** „Korrigieren…" im Editor: Wandlücken als Liste mit Vorschlag und Grund, Anwenden schliesst sie, baut das Gelände als Membran über dem Weg bis an die Wände, löst Rampen und Podeste auf, ein Verlaufsschritt; die Katakomben lassen sich danach entlang des Wegs abfahren.

**Architecture:** `welt/korrektur.py` (Standardbibliothek): Kandidaten, Vorschläge, Anwenden, Gelände übernehmen. `maps/gelaende_bau.py` (numpy): Sperren, Fluten, Membran. `gui/raumeditor/korrektur_dialog.py`: Tabelle, Einstellungen, Arbeiter-Thread; der Tab verdrahtet Markierung, Verlauf, Meldung.

**Tech Stack:** Standardbibliothek in `welt/`, numpy in `maps/`, PySide6.

**Spec:** `docs/superpowers/specs/2026-09-07-korrigierer-gelaende-design.md` (§ 6, 7, 8, 9)

## Global Constraints

- `welt/korrektur.py` ohne numpy; das Pauspapier wird über einen Zellenindex (dict) befragt.
- `maps/gelaende_bau.py` liest nur `Raum`, Punkte, Weg — keine Karte, kein bosdyn.
- Das Gelände wird nie von Hand gesetzt; es kommt nur aus `baue_gelaende`.
- Katakomben-Test mit `skipif`, Laufzeit unter 20 s.
- Vorgaben: `MAX_LUECKE_M = 1.5`, Winkel 15° (Lücke, Ecke), 25° (Anschluss), Probe 0.05 m, Zelle des Punktindex 0.1 m, 2 Punkte je Zelle, 60 % Proben; `Einstellungen(zelle=0.2, abstand=2.0, punkte_je_zelle=5, min_fleck=3, profil_toleranz=0.10, hoechstens_iterationen=3000, genau_m=0.001)`.

---

### Task 1: Kandidaten für Wandlücken

**Files:** Create `src/spotlab/welt/korrektur.py`; Test `tests/test_welt_korrektur.py`.

**Interfaces:** Produces `Luecke` (Spec § 6), `MAX_LUECKE_M`, `finde_luecken(raum, weg=(), pauspapier=(), max_luecke=MAX_LUECKE_M, winkel_grad=15.0) -> [Luecke]` (in diesem Task noch ohne Vorschläge: alle `unklar`), Helfer `_schnitt(a1, a2, b1, b2)` (Schnittpunkt zweier Geraden oder `None`), `_fusspunkt(p, a, b) -> (punkt, t)`, `_kreuzt(a1, a2, b1, b2)` (Strecken schneiden sich).

- [ ] **Step 1: Tests**

```python
from spotlab.welt import korrektur as k
from spotlab.welt.raum import Raum, Wand

def _raum(*waende):
    return Raum("K", "", (0.5, 0.5, 0.0), waende=[Wand(*w) for w in waende])


def test_zwei_kollineare_waende_mit_luecke():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0))
    (l,) = k.finde_luecken(raum)
    assert l.art == "luecke" and l.waende == (0, 1) and l.enden == (2, 1)
    assert l.ziel == pytest.approx((2.6, 0.0)) and l.laenge == pytest.approx(0.6)
    assert l.vorschlag == "unklar"


def test_eine_ecke_schliesst_auf_dem_schnittpunkt():
    raum = _raum((0, 0, 2.5, 0), (3, 0.5, 3, 3))
    (l,) = k.finde_luecken(raum)
    assert l.art == "ecke" and l.ziel == pytest.approx((3.0, 0.0))
    assert len(l.strecken) == 2 and l.laenge == pytest.approx(1.0)


def test_ein_anschluss_an_die_wandmitte():
    raum = _raum((0, 0, 6, 0), (3, 0.7, 3, 3))
    (l,) = k.finde_luecken(raum)
    assert l.art == "anschluss" and l.waende == (1, 0) and l.ziel == pytest.approx((3.0, 0.0))


def test_zu_weit_oder_beruehrend_ist_kein_kandidat():
    assert k.finde_luecken(_raum((0, 0, 2, 0), (4, 0, 6, 0))) == []
    assert k.finde_luecken(_raum((0, 0, 2, 0), (2, 0, 4, 0))) == []


def test_kein_kandidat_durch_eine_dritte_wand():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0), (2.5, -1, 2.5, 1))
    assert all(l.waende != (0, 1) for l in k.finde_luecken(raum))


def test_je_ende_der_kuerzeste_und_jedes_paar_einmal():
    raum = _raum((0, 0, 2, 0), (2.4, 0, 4, 0), (2.8, 0.05, 5, 0.05))
    luecken = k.finde_luecken(raum)
    assert [l.waende for l in luecken].count((0, 1)) == 1
    assert all(sorted(l.waende) != [0, 2] for l in luecken)
```

- [ ] **Step 2: Scheitern.**

- [ ] **Step 3: Implementieren**

```python
MAX_LUECKE_M = 1.5


@dataclass(frozen=True)
class Luecke:
    art: str
    waende: tuple
    enden: tuple
    ziel: tuple
    strecken: tuple
    laenge: float
    vorschlag: str
    grund: str


def _ende(wand, nummer):
    return (wand.x1, wand.y1) if nummer == 1 else (wand.x2, wand.y2)


def _winkel_diff(a, b):
    return abs(((a - b) + 90.0) % 180.0 - 90.0)


def _schnitt(a1, a2, b1, b2):
    d = (a2[0] - a1[0]) * (b2[1] - b1[1]) - (a2[1] - a1[1]) * (b2[0] - b1[0])
    if abs(d) < 1e-9:
        return None
    t = ((b1[0] - a1[0]) * (b2[1] - b1[1]) - (b1[1] - a1[1]) * (b2[0] - b1[0])) / d
    return (a1[0] + t * (a2[0] - a1[0]), a1[1] + t * (a2[1] - a1[1]))


def _fusspunkt(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
    return (a[0] + t * dx, a[1] + t * dy), t


def _kreuzt(a1, a2, b1, b2):
    def seite(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    s1, s2 = seite(a1, a2, b1), seite(a1, a2, b2)
    s3, s4 = seite(b1, b2, a1), seite(b1, b2, a2)
    return (s1 * s2 < 0) and (s3 * s4 < 0)


def _abstand(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _durch_dritte(raum, strecke, ausser):
    a, b = (strecke[0], strecke[1]), (strecke[2], strecke[3])
    return any(i not in ausser and _kreuzt(a, b, (w.x1, w.y1), (w.x2, w.y2))
               for i, w in enumerate(raum.waende))


def _kandidaten_fuer_ende(raum, i, ende, max_luecke, winkel_grad):
    wand = raum.waende[i]
    e = _ende(wand, ende)
    treffer = []
    for j, andere in enumerate(raum.waende):
        if j == i or andere.laenge <= 0:
            continue
        diff = _winkel_diff(wand.winkel, andere.winkel)
        f_nummer = min((1, 2), key=lambda n: _abstand(e, _ende(andere, n)))
        f = _ende(andere, f_nummer)
        if diff <= winkel_grad:
            d = _abstand(e, f)
            if 0.02 < d <= max_luecke:
                treffer.append(Luecke("luecke", (i, j), (ende, f_nummer), f, ((*e, *f),), d, "unklar", ""))
        elif abs(diff - 90.0) <= winkel_grad:
            s = _schnitt((wand.x1, wand.y1), (wand.x2, wand.y2), (andere.x1, andere.y1), (andere.x2, andere.y2))
            if s is not None:
                d_e, d_f = _abstand(e, s), _abstand(f, s)
                if 0.02 < d_e <= max_luecke and d_f <= max_luecke:
                    strecken = tuple(st for st in ((*e, *s), (*f, *s)) if _abstand(st[:2], st[2:]) > 0.02)
                    treffer.append(Luecke("ecke", (i, j), (ende, f_nummer), s, strecken, d_e + d_f, "unklar", ""))
        if abs(diff - 90.0) <= 25.0:
            p, t = _fusspunkt(e, (andere.x1, andere.y1), (andere.x2, andere.y2))
            d = _abstand(e, p)
            if 0.05 <= t <= 0.95 and 0.02 < d <= max_luecke:
                treffer.append(Luecke("anschluss", (i, j), (ende,), p, ((*e, *p),), d, "unklar", ""))
    treffer = [t for t in treffer if not any(_durch_dritte(raum, st, set(t.waende)) for st in t.strecken)]
    return min(treffer, key=lambda t: t.laenge) if treffer else None


def finde_luecken(raum, weg=(), pauspapier=(), max_luecke=MAX_LUECKE_M, winkel_grad=15.0):
    gefunden, paare = [], set()
    for i, wand in enumerate(raum.waende):
        if wand.laenge <= 0:
            continue
        for ende in (1, 2):
            l = _kandidaten_fuer_ende(raum, i, ende, max_luecke, winkel_grad)
            if l is None:
                continue
            paar = (frozenset(l.waende), l.ziel if l.art != "luecke" else None, l.art)
            schluessel = (frozenset(l.waende), l.art, tuple(round(v, 3) for v in l.ziel))
            if schluessel in paare:
                continue
            paare.add(schluessel)
            gefunden.append(l)
    gefunden += _kreuzende(raum, weg)          # Task 2
    gefunden = [_mit_vorschlag(l, weg, pauspapier) for l in gefunden]   # Task 2
    return sorted(gefunden, key=lambda l: l.laenge)
```

In diesem Task sind `_kreuzende` und `_mit_vorschlag` Platzhalter, die die Liste bzw. die Lücke unverändert zurückgeben; Task 2 füllt sie. (Der Eintrag `paar` in der Schleife ist zu streichen — nur `schluessel` zählt.)

- [ ] **Step 4: Grün.** Commit `feat(welt): Kandidaten fuer Wandluecken -- Luecke, Ecke, Anschluss`.

### Task 2: Vorschläge aus Weg und Pauspapier, kreuzende Wände

**Files:** Modify `src/spotlab/welt/korrektur.py`; Test `tests/test_welt_korrektur.py`.

**Interfaces:** Produces `punktindex(pauspapier, zelle=0.1) -> dict[(int, int), int]`, `_punkte_entlang(strecken, index, zelle=0.1, schritt=0.05, mindestens=2) -> float` (Anteil Proben mit Punkten), `_weg_kreuzt(strecken, weg) -> bool`, `_kreuzende(raum, weg) -> [Luecke]`, `_mit_vorschlag(luecke, weg, index) -> Luecke`; `finde_luecken` baut den Index einmal.

- [ ] **Step 1: Tests**

```python
def _punkte_auf(x1, y1, x2, y2, n=40):
    return [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n + 1)]


def test_der_weg_durch_die_luecke_macht_einen_durchgang():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0))
    (l,) = k.finde_luecken(raum, weg=[(2.5, -1.0, 0.0), (2.5, 1.0, 0.0)])
    assert l.vorschlag == "durchgang" and "lief hindurch" in l.grund


def test_punkte_in_der_luecke_machen_eine_wand():
    raum = _raum((0, 0, 2, 0), (3, 0, 5, 0))
    (l,) = k.finde_luecken(raum, pauspapier=_punkte_auf(2.0, 0.0, 3.0, 0.0))
    assert l.vorschlag == "wand" and "Punkte" in l.grund


def test_ohne_beides_unklar():
    (l,) = k.finde_luecken(_raum((0, 0, 2, 0), (3, 0, 5, 0)))
    assert l.vorschlag == "unklar" and "entscheiden" in l.grund


def test_eine_wand_quer_ueber_den_weg_soll_weg():
    raum = _raum((0, 0, 6, 0), (3, -1, 3, 1))
    luecken = k.finde_luecken(raum, weg=[(1.0, 0.5, 0.0), (5.0, 0.5, 0.0)])
    (kreuzt,) = [l for l in luecken if l.art == "kreuzt"]
    assert kreuzt.waende == (1,) and kreuzt.vorschlag == "loeschen"


def test_das_u_mit_tuer():
    # U: unten 0..6, links 0..4 in zwei Stuecken mit Bruch, rechts mit Tuer; Weg durch die Tuer.
    raum = _raum((0, 0, 6, 0), (0, 0, 0, 1.8), (0, 2.2, 0, 4), (6, 0.5, 6, 1.5), (6, 2.6, 6, 4))
    punkte = _punkte_auf(0, 1.8, 0, 2.2) + _punkte_auf(6, 0, 6, 0.5)
    weg = [(5.0, 2.0, 0.0), (7.0, 2.0, 0.0)]
    luecken = k.finde_luecken(raum, weg=weg, pauspapier=punkte)
    arten = {(l.waende, l.art): l.vorschlag for l in luecken}
    assert arten[((1, 2), "luecke")] == "wand"
    assert arten[((3, 4), "luecke")] == "durchgang"
    assert arten[((0, 3), "ecke")] == "wand"
```

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren:** Index `dict` über `(floor(x/zelle), floor(y/zelle))`; Proben alle 0.05 m entlang jeder Strecke, Probe zählt, wenn eine der 3×3 Zellen ≥ `mindestens` Punkte hat; `_weg_kreuzt` prüft jede Wegstrecke gegen jede Lückenstrecke mit `_kreuzt`; `_kreuzende` prüft jede Wand gegen jede Wegstrecke; `_mit_vorschlag`: Weg → `durchgang`/„der Roboter lief hindurch"; ≥ 0.6 → `wand`/„Punkte in der Lücke"; sonst `unklar`/„kein Weg, keine Punkte — bitte entscheiden"; `kreuzt` behält `loeschen`/„kreuzt den Weg des Roboters". - [ ] **Step 4: Grün.** Commit `feat(welt): Vorschlaege aus Weg und Pauspapier, kreuzende Waende`.

### Task 3: Anwenden und Gelände übernehmen

**Files:** Modify `src/spotlab/welt/korrektur.py`; Test `tests/test_welt_korrektur.py`.

**Interfaces:** Produces `wende_an(raum, luecken, entscheide: dict[int, str]) -> Raum`, `uebernimm_gelaende(raum, gelaende, boeden_aufloesen) -> Raum`.

- [ ] **Step 1: Tests**

```python
def test_wende_an_rueckt_enden_und_loescht():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0), (3, -1, 3, 1))
    luecken = k.finde_luecken(raum, weg=[(1.0, 0.5, 0.0), (4.0, 0.5, 0.0)])
    entscheide = {i: ("wand" if l.art == "luecke" else "loeschen") for i, l in enumerate(luecken)}
    neu = k.wende_an(raum, luecken, entscheide)
    assert len(neu.waende) == 2 and (neu.waende[0].x2, neu.waende[0].y2) == pytest.approx((2.6, 0.0))


def test_durchgang_und_lassen_aendern_nichts():
    raum = _raum((0, 0, 2, 0), (2.6, 0, 5, 0))
    luecken = k.finde_luecken(raum)
    assert k.wende_an(raum, luecken, {0: "durchgang"}) == raum
    assert k.wende_an(raum, luecken, {0: "lassen"}) == raum


def test_eine_ecke_rueckt_beide_enden():
    raum = _raum((0, 0, 2.5, 0), (3, 0.5, 3, 3))
    neu = k.wende_an(raum, k.finde_luecken(raum), {0: "wand"})
    assert (neu.waende[0].x2, neu.waende[0].y2) == pytest.approx((3.0, 0.0))
    assert (neu.waende[1].x1, neu.waende[1].y1) == pytest.approx((3.0, 0.0))


def test_uebernimm_gelaende_loest_rampen_auf_und_setzt_z():
    from spotlab.welt import gelaende as g
    ge = g.gitter(0.0, 0.0, 0.5, 5, 9, lambda x, y: 0.1 * x)
    raum = Raum("K", "", (0.5, 0.5, 0.0), waende=[Wand(0, 0, 4, 0)],
                boeden=(Boden("Rampe 1", 2, 1, 2, 1, anstieg=0.2), Boden("Podest 1", 3, 1, 1, 1, z=0.3),
                        Boden("Treppe", 1, 1, 1, 1, z=0.1, anstieg=0.5, stufen=3)),
                tags=(RaumTag(1, 4.0, 1.0, 0.0),))
    neu = k.uebernimm_gelaende(raum, ge, True)
    assert [b.name for b in neu.boeden] == ["Treppe"]
    assert neu.waende[0].z == pytest.approx(0.2) and neu.tags[0].z == pytest.approx(0.4)
    assert k.uebernimm_gelaende(raum, ge, False).boeden == raum.boeden
```

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** wie Spec § 6 (Wände als Liste, `replace` der Enden nach `enden`, Löschliste am Ende; `uebernimm_gelaende` rundet `z` auf 3 Stellen). - [ ] **Step 4: Grün.** Commit `feat(welt): Luecken anwenden, Gelaende uebernehmen`.

### Task 4: Geländebau — Gitter, Sperren, Weg, Region, offene Ränder

**Files:** Create `src/spotlab/maps/gelaende_bau.py`; Test `tests/test_maps_gelaende_bau.py`.

**Interfaces:** Produces `Einstellungen`, `Ergebnis(gelaende, offene_raender, bericht)`, `baue_gelaende(raum, weg, pauspapier, einstellungen=None, fortschritt=None) -> Ergebnis`; intern `_gitter(raum, weg, pauspapier, e) -> (x0, y0, zeilen, spalten)`, `_gesperrt(raum, pauspapier, x0, y0, zeilen, spalten, e) -> bool[zeilen, spalten]`, `_wegzellen(weg, x0, y0, zeilen, spalten, e) -> (fest: bool[...], werte: float[...])`, `_region(gesperrt, fest, abstand_zum_weg, e) -> bool[...]`, `_offene_raender(region, gesperrt) -> (punkte, laeufe)`. In diesem Task gibt `baue_gelaende` die Höhe der nächsten Wegzelle (Startwert), Task 5 legt die Membran darüber.

- [ ] **Step 1: Tests**

```python
import numpy as np
from spotlab.maps import gelaende_bau as gb
from spotlab.welt.raum import Raum, Wand, Block


def _l_gang():
    """Gang 2 m breit: Schenkel A entlang x (0..8, y 0..2), Schenkel B entlang y (x 6..8, y 2..8).
    Die Aussenwand rechts hat eine 1-m-Luecke bei y 4..5 (ohne Punkte)."""
    waende = [Wand(0, 0, 8, 0), Wand(0, 0, 0, 2), Wand(0, 2, 6, 2), Wand(6, 2, 6, 8),
              Wand(8, 0, 8, 4), Wand(8, 5, 8, 8), Wand(6, 8, 8, 8)]
    weg = [(1.0, 1.0, 0.0), (7.0, 1.0, 0.42), (7.0, 7.0, 0.42)]      # 4 Grad ueber 6 m in A
    return Raum("L", "", (1.0, 1.0, 0.0), waende=waende), weg


def test_das_gelaende_reicht_bis_an_die_waende():
    raum, weg = _l_gang()
    erg = gb.baue_gelaende(raum, weg, [])
    ge = erg.gelaende
    assert ge.hoehe_bei(0.3, 0.3) is not None and ge.hoehe_bei(7.7, 7.7) is not None
    assert ge.hoehe_bei(3.0, 5.0) is None              # ausserhalb des L


def test_genau_ein_offener_rand_an_der_luecke():
    raum, weg = _l_gang()
    erg = gb.baue_gelaende(raum, weg, [])
    assert erg.bericht["offen"] == 1
    assert all(7.5 < x < 8.5 and 3.5 < y < 5.5 for x, y in erg.offene_raender)


def test_punkte_sperren_und_rauschen_nicht():
    raum, weg = _l_gang()
    dicht = [(8.0, 4.5)] * 6                      # eine Zelle, 6 Punkte: sperrt
    erg = gb.baue_gelaende(raum, weg, dicht)
    assert erg.bericht["offen"] == 1 and erg.gelaende.hoehe_bei(8.4, 4.5) is None or erg.bericht["offen"] == 0
    rauschen = [(3.0, 1.0)] * 6 + [(3.2, 1.0)] * 6   # zwei Zellen mitten im Gang: Rauschen
    erg = gb.baue_gelaende(raum, weg, rauschen)
    assert erg.gelaende.hoehe_bei(3.0, 1.0) is not None


def test_der_weg_bleibt_frei_und_loecher_werden_gefuellt():
    raum, weg = _l_gang()
    quer = Raum("L", "", (1, 1, 0), waende=list(raum.waende) + [Wand(4, 0, 4, 2)])
    erg = gb.baue_gelaende(quer, weg, [])
    assert erg.gelaende.hoehe_bei(4.0, 1.0) is not None
    insel = Raum("L", "", (1, 1, 0), waende=list(raum.waende) + [Wand(2, 0.5, 3, 0.5), Wand(3, 0.5, 3, 1.5), Wand(3, 1.5, 2, 1.5), Wand(2, 1.5, 2, 0.5)])
    assert gb.baue_gelaende(insel, weg, []).gelaende.hoehe_bei(2.5, 1.0) is not None


def test_ohne_weg_ein_klarer_fehler():
    raum, _ = _l_gang()
    with pytest.raises(SpotlabError, match="Weg"):
        gb.baue_gelaende(raum, [(1.0, 1.0, 0.0)], [])
```

(Der dritte Test wird beim Schreiben entschärft: eine gesperrte Zelle in der Lücke halbiert den offenen Rand — es reicht zu prüfen, dass `hoehe_bei(8.0, 4.5)` `None` ist.)

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** nach Spec § 7 Schritte 1–5 und 8: Gitter über `huelle(raum)` ∪ Weg ∪ Pauspapier + 1 m; Sperren per Abstand jeder Knotenmitte zu jeder Wand (vektorisiert wie `wahrnehmung._zur_strecke`, Schwelle `max(wand_dicke, zelle)/2`), Blöcke per `lokal`-Rechnung, Punkte per `np.add.at` auf Zellindizes; Rauschflecken über eine Flutfüllung auf den nur-Pauspapier-gesperrten Zellen; Wegzellen per Abtastung alle `zelle/2` mit linear interpoliertem Profil (Douglas-Peucker aus `maps/rekonstruktion.py` importieren); Abstand zum Weg = min über die Strecken; Region per BFS (`collections.deque`) über freie Zellen mit Abstand ≤ `abstand`, Startwert = Höhe der Wegzelle, von der die Flut kam; Löcher: BFS vom Gitterrand über Nicht-Regionszellen, der Rest der freien Zellen kommt dazu (Startwert von der nächsten Regionszelle, BFS); offene Ränder wie Spec § 7 Schritt 5, Läufe per BFS über Randzellen. - [ ] **Step 4: Grün.** Commit `feat(maps): Gelaendebau -- Sperren, Fluten, offene Raender`.

### Task 5: Die Membran

**Files:** Modify `src/spotlab/maps/gelaende_bau.py`; Test `tests/test_maps_gelaende_bau.py`.

**Interfaces:** Produces `_membran(hoehen, fest, region, e) -> (hoehen, iterationen)`.

- [ ] **Step 1: Tests**

```python
def test_quer_eben_laengs_das_gefaelle():
    raum, weg = _l_gang()
    ge = gb.baue_gelaende(raum, weg, []).gelaende
    for x in (2.0, 4.0, 6.0):
        quer = [ge.hoehe_bei(x, y) for y in np.arange(0.3, 1.8, 0.1)]
        assert max(quer) - min(quer) < 0.01
    steigung = (ge.hoehe_bei(6.0, 1.0) - ge.hoehe_bei(2.0, 1.0)) / 4.0
    assert math.degrees(math.atan(steigung)) == pytest.approx(4.0, abs=0.5)


def test_keine_klippe_entlang_des_wegs_und_der_tiefste_knoten_ist_null():
    from spotlab.welt.gelaende import klippen
    raum, weg = _l_gang()
    erg = gb.baue_gelaende(raum, weg, [])
    assert min(h for h in erg.gelaende.hoehen if h is not None) == pytest.approx(0.0, abs=1e-6)
    assert not [k for k in klippen(erg.gelaende) if 0.5 < k[0] < 7.5 and 0.5 < k[1] < 1.5]
    assert erg.bericht["iterationen"] < 3000 and erg.bericht["dauer_s"] < 5.0
```

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren:** Rot-Schwarz-SOR wie Spec § 7 Schritt 6: Nachbarsummen mit `np.roll` unter Maske `region` (Nachbar zählt nur, wenn in der Region; Mittel = Summe / Anzahl), `ω = 2 / (1 + sin(π / N))`, Wegzellen nach jedem Halbschritt zurücksetzen, Abbruch bei `max|Δ| < genau_m`; danach `hoehen -= min(region)`, `bericht["verschiebung"]`. - [ ] **Step 4: Grün.** Commit `feat(maps): Membran ueber dem Weg`.

### Task 6: Dialog und Arbeiter

**Files:** Create `src/spotlab/gui/raumeditor/korrektur_dialog.py`; Test `tests/test_gui_raumeditor_korrektur.py`.

**Interfaces:** Produces `Korrektur(raum, offene_raender, bericht)`, `GelaendeArbeiter(QThread)` mit Signalen `fortschritt(str)`, `fertig(object)`, `fehler(str)`; `KorrekturDialog(eltern, raum, weg, pauspapier)` mit Signalen `markiere(object)`, `kandidaten(object)`, `angewendet(object)`; Attribute `tabelle: QTableWidget`, `gelaende_bauen: QCheckBox`, `abstand: QDoubleSpinBox`, `boeden_aufloesen: QCheckBox`, `anwenden: QPushButton`, `fortschritt: QLabel`; Methode `entscheide() -> dict`.

- [ ] **Step 1: Tests** (Qt offscreen wie `test_gui_raumeditor_rekonstruktion.py`): Tabelle hat je Lücke eine Zeile mit Art, Länge, Vorschlag (Combo-Text „Wand"/„Durchgang"/„lassen"/„Löschen") und Grund; Zeilenwahl sendet `markiere` mit den Strecken; `kandidaten` wird beim Öffnen gesendet; ohne Weg ist `gelaende_bauen` aus und deaktiviert, der Text nennt „Kein Weg"; `anwenden` ohne Gelände sendet `angewendet` mit dem korrigierten Raum sofort; mit Gelände (Arbeiter mit `wait()` im Test) hat `korrektur.raum.gelaende` Knoten und `bericht["gelaende"]["knoten"] > 0`; das Häkchen `boeden_aufloesen` nennt die Zahl der Rampen und Podeste.
- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** nach Spec § 8. - [ ] **Step 4: Grün.** Commit `feat(gui): Dialog Korrigieren -- Luecken, Vorschlaege, Gelaende im Arbeiter`.

### Task 7: Der Tab verdrahtet den Korrigierer

**Files:** Modify `src/spotlab/gui/raumeditor/tab.py`, `src/spotlab/gui/raumeditor/steuerung.py`; Test `tests/test_gui_raumeditor.py`.

**Interfaces:** Produces `Steuerung.uebernimm(raum)` (öffentlich, ersetzt `_uebernimm` an allen Aufrufstellen), Knopf „Korrigieren…", `tab._korrigieren()`, `tab.uebernimm_korrektur(korrektur)`.

- [ ] **Step 1: Tests:** der Knopf existiert (Objektname `knopf_korrigieren`); `uebernimm_korrektur` mit einem `Korrektur` setzt den Raum, markiert geändert, `steuerung.rueckgaengig()` stellt den alten Raum her, `sicht._offen` trägt die Punkte, die Meldung beginnt mit „Korrigiert:".
- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren:** `_korrigieren` öffnet den Dialog (`show()`), verbindet `markiere` → `sicht.setze_markierung` + `update()`, `kandidaten` → `setze_kandidaten`, `angewendet` → `uebernimm_korrektur`; `uebernimm_korrektur`: `steuerung.uebernimm(k.raum)`, `setze_offen`, Markierungen leeren, `_zeige`, Meldung nach Spec § 8. - [ ] **Step 4: Grün.** Commit `feat(editor): Korrigieren im Raumeditor`.

### Task 8: Katakomben

**Files:** Test `tests/test_maps_gelaende_bau.py` (oder `tests/test_katakomben_korrektur.py`).

- [ ] **Test** (skipif ohne `D:\Users\janis\Documents\Spot Projects\maps\map_catacombs_01`): `rekonstruiere` → `finde_luecken(raum, ergebnis.weg, ergebnis.pauspapier)` → mindestens 60 % mit Vorschlag ≠ unklar → `wende_an` mit den Vorschlägen → `baue_gelaende` → `uebernimm_gelaende` → jede Wegzelle hat Boden (`hoehe_bei` nicht `None` für alle Wegpunkte) → `bewege_mit_hoehe` in 0.1-m-Schritten entlang des Wegs mit `z_nahe` mitgeführt: kein Treffer; Laufzeit < 20 s. Läuft er nicht durch, ist das ein Befund: Ursache in den Bericht der Etappe, nicht den Test aufweichen.
- [ ] Commit `test(katakomben): korrigiert und abgefahren`.

### Task 9: Doku und Abschluss

- [ ] README: Absatz „Korrigieren" (Lücken, Gelände) und das Gelände in der Elementliste; `docs/ABNAHME.md` A28; `CLAUDE.md`: Regeln aus Spec § 13 und Umsetzungsstand „Stufe 14 … alle drei Etappen"; Erinnerung `spotlab-project.md`. Suite und ruff beider Repos grün. Bild der korrigierten Katakomben (2D und 3D) an den Autor. Commit `docs: Stufe 14 Etappe 3 -- Korrigierer, Abnahme A28, Regeln`.
