# Agenten am Spot, Teil 1 — Implementation Plan

> Inline ausgeführt (keine Sub-Agenten, Nutzerregel), TDD je Aufgabe, Worktree `.worktrees/agent`,
> Branch `feat/agent-faehrt` (abgezweigt von `feat/gui-puls`). Am Laptop nur die betroffenen
> Testdateien; die volle Suite läuft auf aicgolling (`cd ~/spotlab-X && …`), Vergleich gegen `main`.

**Goal:** Ein Agent (Claude, Codex) sieht über MCP, was die laufende Steuerzentrale sieht, und fährt
Spot über sie — im Übungsraum frei, am echten Spot nur mit Freigabe eines Menschen in der GUI.

**Spec:** `docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`

## Global Constraints

- `record/agent.py` nur Standardbibliothek, atomar über `record/atomar.py`, Leser werfen nie.
- GUI ohne `bosdyn`/`spotlab.backends`, Farben nur aus dem Thema. MCP-Prozess ohne Qt.
- Kein eigener Weg zum Roboter im MCP-Server: er schreibt nur Dateien und startet die Zentrale über
  `workshop/launcher.start_script`. Übungsraum IMMER mit `nur_trocken=True`. Nie `take`.
- Rangfolge im Fahrtakt: Taste > Klick im Tab > Agent. Jede menschliche Eingabe bricht den
  Agentenbefehl ab; am echten Spot schaltet sie zusätzlich die Freigabe aus.
- Neue Ereignisse stehen in `record/events.ARTEN` und werden gegen den echten `RunRecorder` geprüft.
- Meldungen deutsch, sagen was zu tun ist; Bezeichner englisch nur bei Ausnahmeklassen.
- Konstanten: `AGENT_TOTMANN_S = 0.5`, `AGENT_PULS_S = 0.2`, `FREIGABE_PULS_S = 3.0`,
  `STOSS_MAX_S = 2.0`, `STOSS_SEITE_MAX_M_S = 0.2`, `DREH_FERTIG_GRAD = 3.0`, `DREH_FRIST_S = 15.0`,
  `BEFEHL_WARTE_S = 30.0`, `BESTAETIGUNG_S = 2.0`, `LAGEBILD_ALT_S = 2.0`, `TIEFE_WARTE_S = 5.0`.

---

### Task 1: Protokoll (`record/agent.py`, `record/events.py`)
- `ARTEN_BEFEHL = ("ziel", "relativ", "drehen", "stoss", "folgen", "stopp", "tiefe", "licht",
  "piep", "suche")`; `Befehl(nummer, art, werte: dict, warum, agent, lebt)` (frozen dataclass).
- `schreibe_befehl(lauf_dir, nummer, art, werte, warum, agent, jetzt)`, `lies_befehl(lauf_dir)`
  (None bei fehlend/kaputt/unbekannter Art), `befehl_lebt(befehl, jetzt) -> bool` (≤ 0.5 s).
- `schreibe_freigabe(lauf_dir, an, nummer, jetzt)`, `lies_freigabe(lauf_dir) -> dict | None`,
  `freigabe_gilt(lauf_dir, jetzt) -> bool`: `an` UND `record/zentrale.lies_gui_puls` höchstens
  `FREIGABE_PULS_S` alt.
- `schreibe_besitz(lauf_dir, agent, pid, jetzt)`, `lies_besitz(lauf_dir)`.
- `ARTEN` += `agent_befehl`, `agent_ergebnis`, `freigabe`.
- Tests `tests/test_record_agent.py`: Rundreise, kaputt/fehlend/unbekannte Art → None, Lebenszeichen
  0.5 s, Freigabe gilt nur mit frischem Puls (ohne Puls, alter Puls, `an: false`).

### Task 2: Fahrbausteine ohne Roboter (`workshop/agentfahrt.py`)
- `relativ_ziel(lage, vor_m, links_m) -> (x, y)` (lage = (x, y, gier) im Rahmen der Skizze).
- `class Drehung(ziel_gier_rad, t0)`: `schritt(gier, t) -> (wz, zustand, grund)`, `zustand ∈
  unterwegs | angekommen | abgebrochen` (fertig bei 3°, Frist 15 s), `wz = klickfahrt.LENKUNG ×
  Abweichung`, gekappt auf die Drehgrenze, reines Drehen nie unter 0.15 rad/s (Drehschwelle des
  echten Spot, `docs/SIM_ANTWORT.md`).
- `stoss_pruefen(vx, vy, wz, dauer_s, lage, gitter, frei_m, kopf_frei, kopf_grund, max_v, max_w)
  -> (vx, vy, wz, dauer_s, grund | None)`: Dauer ≤ 2 s; Tempi gekappt; vorwärts nur mit
  `frei_m ≥ vx·dauer + klickfahrt.RAND_M` und `kopf_frei`; seitwärts/rückwärts ≤ 0.2 m/s und
  `gitter.is_free` an den Punkten der Strecke (alle 0.1 m bis Weg + RAND_M); unlesbares Gitter →
  Grund (fail-closed). Ein Grund heisst: gar nicht fahren.
- `tiefe_sektoren(punkte_body) -> {"links","mitte","rechts": {"abstand_m"|None, "punkte", "grund"}}`:
  Punkte über Bodenhöhe (z > −0.40 m im Körperrahmen) vor Spot, Sektorgrenzen ±10°, Abstand =
  5. Perzentil der waagrechten Entfernung, unter 20 Punkten `None` + „zu wenig Punkte“.
- Tests `tests/test_workshop_agentfahrt.py` (je Funktion, inkl. Gitter-Attrappe und NaN-freie Punkte).

### Task 3: Klickfahrt mit Quelle, Folgen mit Ablöse-Prüfung (`workshop/klickfahrt.py`, `workshop/zentrale.py`)
- `Stand.quelle = "tab"` (neu, in `als_daten`), `Klickfahrt.neues_ziel(..., quelle="tab")`.
- `Zentrale._folge_mensch(nummer, ziel, quelle, abgeloest)`; `abgeloest() -> str | None` ersetzt die
  fest verdrahtete Klickziel-Prüfung. Der Klick-Weg übergibt die bisherige Prüfung (neuer Klick,
  Lebenszeichen) unverändert; Verhalten und Meldungen bleiben gleich.
- Tests: die bestehenden `test_workshop_zentrale.py` bleiben grün; neu: `quelle` steht im Lagebild.

### Task 4: Agent im Fahrtakt (`workshop/zentrale.py`)
- `Zentrale(..., braucht_freigabe=False)`. Im Hauptprogramm: `True`, wenn das Backend des Laufs
  (`read_run(lauf_dir).backend`) NICHT in `spotlab.OHNE_ROBOTER` steht.
- `takt()`: nach Taste und Klick der Agent (`_agent(t, befehl_taste, kz)`):
  - neue Nummer → `agent_befehl`-Ereignis; ohne gültige Freigabe (wenn `braucht_freigabe`) jede
    Fahrt-Art `abgelehnt: keine Freigabe — …`; `stopp`, `tiefe`, `licht`, `piep`, `suche` immer.
  - `ziel`/`relativ` → `klick.neues_ziel(..., quelle="agent")` (Tempostufe „langsam“), Schritte wie
    die Klickfahrt (`_klickschritt`), aber mit `befehl_lebt` statt Klick-Lebenszeichen.
  - `drehen` → `Drehung`; `stoss` → `stoss_pruefen`, dann `walk(stop=False)` bis Dauerende;
    `folgen` → `_folge_mensch(..., quelle="agent", abgeloest=…)`; `stopp` → anhalten.
  - Taste oder neuer Klick während eines Agentenbefehls → `abgebrochen: ein Mensch hat übernommen`.
  - Lebenszeichen älter als 0.5 s → Stopp, `abgebrochen: kein Lebenszeichen vom Agenten`.
  - Freigabe-Wechsel → Ereignis `freigabe`; Freigabe aus während einer Fahrt → Abbruch.
  - Ende jedes Befehls → `agent_ergebnis` (zustand, grund, dauer_s).
- Lagebild-Platz `agent`: `{nummer, art, zustand, grund, warum, seit, freigabe, braucht_freigabe,
  tiefe}`.
- `licht`/`piep`/`suche` laufen über dieselben Funktionen wie `aktion.json` (eigene Nummernfolge).
- `tiefe`: im Wahrnehmungsfaden `point_cloud("frontleft"|"frontright", frame="body")`, beide
  zusammen in `tiefe_sektoren`, dazu `kopfraum`; `UnsupportedCapability`/Fehler → „nicht messbar“.
- Tests (`test_workshop_zentrale.py`, Attrappen-Spot): Rangfolge; echt ohne Freigabe abgelehnt,
  mit Freigabe gefahren, Übungsraum ohne; Totmann; Abbruch durch Taste; Stoss gekappt; Drehung;
  `tiefe` ohne Kameras „nicht messbar“; Ereignisse gegen den echten `RunRecorder`.

### Task 5: Warten auf die Freigabe (`workshop/zentrale.py`)
- `argumente()` kennt `--auf-freigabe-warten`. Hauptprogramm: mit der Option kein `power_on()`/
  `stand()` vor `lauf()`; `Zentrale(..., warte_auf_freigabe=True)`: der Fahrtakt fährt nicht, bis
  `freigabe_gilt`, dann EINMAL `power_on()` + `stand()` (Ereignis `freigabe`), danach normal.
  Wahrnehmung und Lagebild laufen von Anfang an; das Lagebild sagt `motoren: "aus — wartet auf
  Freigabe"`.
- Tests: Attrappe ohne Freigabe → kein `power_on`; Freigabe kommt → `power_on`, `stand`, dann fährt
  ein Agentenbefehl.

### Task 6: GUI — Schalter und Zeile (`gui/views/fahren.py`)
- Schalter „🤖 Agent darf fahren“ (QCheckBox) und eine `Kurztext`-Zeile „Agent: ‹Art› — ‹warum› —
  ‹Zustand›“ aus `lagebild["agent"]`. Aktiv nur, wenn `lagebild["agent"]["braucht_freigabe"]`; sonst
  grau mit „im Übungsraum fährt der Agent ohne Freigabe“.
- Schalten schreibt `freigabe.json` (Nummer zählt hoch). Jede Fahrtaste, jeder Klick in die
  Draufsicht, „Stopp“ und `lauf_beendet` → Schalter aus + `an: false`.
- Tests (`test_gui_fahren.py`): Schalter schreibt; Taste und Klick schalten aus; Zeile zeigt
  `warum`; grau im Übungsraum.

### Task 7: GUI — eine vom Agenten gestartete Zentrale (`gui/app.py`)
- `_uebernimm_lauf`: endet `lauf.json → skript` auf `workshop/zentrale.py` und wird keine andere
  Fahrt erwartet, gilt der Lauf als Zentrale (Tab „Fahren“ `lauf_beginnt`, Reiter nach vorn) —
  sonst gäbe es weder Puls noch Freigabe. „Genau ein Lauf“ bleibt (`_lauf_begonnen` unverändert).
- Test (`test_gui_app.py`): ein Lauf mit diesem Skript hängt den Tab an.

### Task 8: Lage und Skizze für den Agenten (`mcp/agentlage.py`)
- `lage_aus(lauf_dir, jetzt) -> dict`: aus `lagebild.json`, `lagebild.png` (Indexbild, Zeile 0 =
  kleinstes y; 0 unbekannt, 1..8 frei, 9..16 Wand) und der letzten Zeile von `zustand.jsonl`:
  Pose, Tempo, Akku, Motoren, Freigabe, freie Strecke in 8 Richtungen (Strahl auf der Skizze bis
  5 m: `frei bis` / `Wand bei` / `unbekannt ab`), Kopfraum, Menschen/Tags mit Peilung und Abstand
  zu Spot und in Weltkoordinaten, Platz `agent`. Lagebild älter als 2 s → `{"fehler": …}`.
- `skizze_bild(lauf_dir, radius_m) -> (png_bytes, legende)`: Ausschnitt um Spot, senkrecht
  gespiegelt (+y oben), Farben fest im Modul (MCP ist keine GUI: kein Thema), 1-m-Raster, Pfeil,
  Menschen/Tags/Agentenweg.
- Tests (`tests/test_mcp_agentlage.py`) mit einem fest gebauten Lagebild: Richtungen, Peilungen,
  altes Lagebild, Bildgrösse und Spiegelung.

### Task 9: Die Werkzeuge (`mcp/fahren.py`, `mcp/server.py`)
- Funktionen wie in Spec § 2, alle mit `_antwortet` (kein Werfen). Lauf finden: der jüngste aktive
  Lauf unter `<Arbeitsordner>/Beispiele/runs`, dessen Skript `workshop/zentrale.py` ist.
- `zentrale_starten`: Raumregel (`welt/physik.tauglich` für physik), Backend, `nur_trocken=True` im
  Übungsraum, echt mit `--auf-freigabe-warten`; Ausgabe nach `mcp-ausgabe/`; wartet ≤ 30 s auf
  Lauf und Lagebild; legt `agent_besitz.json` an.
- Fahrbefehle: Nummer hochzählen, `schreibe_befehl`, Hintergrundfaden frischt `lebt` alle 0.2 s,
  solange der Befehl `unterwegs` ist; Bestätigung ≤ 2 s; warten ≤ 30 s; Antwort aus Platz `agent`.
- Besitz: lebt der eingetragene Prozess (`lease.lebt`-Prüfung über `tasklist`), „belegt von …“.
- Aufzeichnung: jede Funktion schreibt eine Zeile nach `<lauf>/agent.jsonl`; `skizze`/
  `kamerabild` legen ihr Bild unter `<lauf>/agent/` ab.
- `server.py`: die neuen Werkzeuge mit Beschreibungen (Koordinatenrahmen, Einheiten, Regeln);
  Bilder als `mcp.server.mcpserver.Image`.
- Tests (`tests/test_mcp_fahren.py`): ohne Zentrale; zweiter Agent; Befehl wird geschrieben und
  Lebenszeichen gefrischt; Antwort aus einem gesetzten Lagebild; `agent.jsonl`; Bildablage.

### Task 10: Kette und Doku
- Kette (`tests/test_mcp_fahren.py`, echter Prozess, 2D): `zentrale_starten("2d", "durchgang")` →
  `lage()` → `fahre_relativ(1.0, 0, …)` → „angekommen“ → `stopp()` → `zentrale_beenden()`; im Lauf
  `agent_befehl`, `agent_ergebnis`, `agent.jsonl`. Echt-Weg mit Trockenlauf statt Roboter:
  `--auf-freigabe-warten` → kein `power_on` bis `schreibe_freigabe` + Puls.
- Doku: `docs/AGENTEN.md`, CLAUDE.md (Regel und Absatz), `docs/ABNAHME.md` A43, Verweis in
  `docs/ANBINDUNG.md`. ruff; volle Suite auf aicgolling gegen `main`.
