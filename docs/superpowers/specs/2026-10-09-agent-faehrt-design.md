# Agenten am Spot, Teil 1: der Agent sieht und fährt

Entwurf vom 09.10.2026, im Gespräch abschnittsweise freigegeben. Erster von fünf Teilen
(1 sieht und fährt · 2 Karten durch den Agenten · 3 Glas und Gefahrenzonen · 4 Experimente ·
5 virtuelle Gehirne); jeder Teil bekommt einen eigenen Entwurf, Plan und Abnahmepunkt. Baut auf
der Steuerzentrale (Teile 1–3, `2026-09-27-steuerzentrale-*-design.md`) und dem GUI-Puls vom
09.10.2026 (`record/zentrale.GUI_PULS`, Zweig `feat/gui-puls`) auf.

## Entscheidungen

- **Weg A: der Agent dockt an die laufende Zentrale an** — über Dateien im Lauf-Verzeichnis, wie
  der Tab „Fahren“. Jede Agentenfahrt geht durch dieselben Schranken wie die Klickfahrt; der
  MCP-Server bekommt KEINEN eigenen Weg zum Roboter. Verworfen: der MCP-Server verbindet selbst
  (zweiter Weg, Lease und Not-Aus im Agentenprozess, ein hartes Ende hinterliesse ein verwaistes
  Lease) und der Agent schreibt Programme (ungeprüfter Code am Roboter, niemand hält die Lage).
- **Der Agent darf die Zentrale auch selbst starten.**
- **Freigabe:** im Übungsraum (2D, 3D, Physik) fährt der Agent ohne Freigabe; am echten Spot nur,
  solange ein Mensch in der GUI „🤖 Agent darf fahren“ eingeschaltet hat.
- **Start am echten Spot:** verbinden ja, aufstehen erst mit Freigabe. Die Zentrale hält Lease und
  Not-Aus, die Motoren bleiben aus, bis die Freigabe kommt.
- **Befehle:** Ziele (Wegsuche wie die Klickfahrt, drehen, relativ, folgen, stopp) und kurze
  Fahrstösse (höchstens 2 s), alles durch dieselben Schranken.

## 1. Aufbau und Sicherheit

**Neue Dateien im Lauf-Verzeichnis** (`record/agent.py`, nur Standardbibliothek, atomar über
`record/atomar.py`, ein kaputter oder halb geschriebener Inhalt gilt als „nichts da“ — dasselbe
Muster wie `record/zentrale.py`):

| Datei | Richtung | Inhalt |
|---|---|---|
| `agent_befehl.json` | Agent → Zentrale | `nummer`, `art`, `werte`, `warum`, `agent` (Name des Klienten), `lebt` (Wanduhr) |
| `freigabe.json` | GUI → Zentrale | `an` (bool), `nummer`, `t` — schreibt NUR die GUI |
| `agent_besitz.json` | MCP → MCP | `agent`, `pid`, `seit` — wer die Zentrale gerade steuert |

Die Antwort steht im vorhandenen `lagebild.json` unter dem neuen Platz **`agent`**:
`{nummer, art, zustand, grund, seit, freigabe, tiefe}` mit `zustand ∈ keiner | unterwegs |
angekommen | abgelehnt | versperrt | abgebrochen | gemessen`.

**Arten von `agent_befehl.json`:** `ziel` (x, y), `relativ` (vor_m, links_m), `drehen` (grad),
`stoss` (vx, vy, wz, dauer_s), `folgen` (x, y), `stopp`, `tiefe`, `licht` (farbe), `piep`,
`suche` (stufe). Licht, Ton und Suchstufe gehen absichtlich NICHT über `aktion.json`: dort
zählt der Tab seine eigene Nummer, zwei Schreiber verwürfelten sie.

**Zentrale (`workshop/zentrale.py`):**

- Ein dritter Eingang im Fahrtakt. Rangfolge **Taste > Klick im Tab > Agent**.
- `ziel` und `relativ` werden ein Ziel der vorhandenen Klickfahrt (`klickfahrt.neues_ziel`,
  Wegsuche, Gitter, Kopfraum, Sperrzonen, Tempostufe „langsam“).
- `drehen` dreht auf der Stelle gegen die GEMESSENE Gierrichtung, fertig bei 3°, Frist 15 s.
- `stoss`: höchstens `STOSS_MAX_S` = 2 s. Vorwärts gelten alle Schranken der Klickfahrt.
  Seitwärts und rückwärts nur bis 0.2 m/s und nur, wenn das Hindernisgitter in Fahrtrichtung
  frei ist — nach hinten sieht Spot schlechter. Tempo und Drehrate gekappt wie `walk()`.
- `folgen` übergibt an den vorhandenen Folgemodus (`klickfolgen`), wie ein Klick auf einen Menschen.
- `tiefe` misst im Wahrnehmungsfaden mit den **Tiefenkameras vorne** (`spot.depth`, Meter,
  ungültige Punkte NaN — NICHT `look()`, das nur das Hindernisgitter liest, eine Bodenkarte):
  je Sektor links / mitte / rechts den nächsten Abstand als 5. Perzentil der gültigen Punkte
  (mindestens 20, sonst „zu wenig Punkte“), dazu den Kopfraum (`tiefe.kopfraum`). Jede Messung
  bleibt als NPZ unter `sensoren/` liegen (so arbeitet `depth()` ohnehin). Wo das Backend keine
  Tiefenkameras hat (2D), steht im Ergebnis ausdrücklich „nicht messbar“, nie eine Zahl.
- **Totmann des Agenten:** `lebt` älter als `AGENT_TOTMANN_S` = 0.5 s heisst Stopp, wie bei
  der Klickfahrt.
- Jeder angenommene Befehl schreibt das Ereignis `agent_befehl`, jedes Ende `agent_ergebnis`
  (beide neu in `record/events.ARTEN`).

**Freigabe (nur echter Spot):**

- Ohne Freigabe antwortet jeder Fahr-Befehl `abgelehnt: keine Freigabe — ein Mensch muss im Tab
  „Fahren“ „🤖 Agent darf fahren“ einschalten`. Lesen (`lage`, Bilder, `tiefe`) geht immer.
- Die Freigabe gilt nur mit frischem GUI-Puls (`gui_lebt.json` höchstens `FREIGABE_PULS_S` = 3 s
  alt): stürzt die GUI ab, erlischt sie, und nach `GUI_FRIST_S` endet die Zentrale ohnehin.
- **Jede menschliche Eingabe nimmt sie zurück:** Taste, Klick in die Draufsicht, Stopp, NOT-AUS.
  Die GUI schreibt dann `an: false`, die Zentrale bricht den Agentenbefehl ab
  („abgebrochen: ein Mensch hat übernommen — die Freigabe ist aus“) und schreibt `freigabe`.
- Start durch den Agenten (`--auf-freigabe-warten`): verbinden, Lease (nie `take`), Not-Aus,
  Wahrnehmung und Lagebild laufen, **Motoren aus**. Erst mit Freigabe `power_on()` und `stand()`.
  Wird die Freigabe später ausgeschaltet, bleibt Spot stehen und gehört wieder dem Menschen.

**Übungsraum:** der Agent startet die Zentrale immer mit `SPOTLAB_NUR_TROCKEN=1` und einem
virtuellen Backend — dieser Prozess kann gar keinen Roboter erreichen. Freigabe braucht es dort
nicht; eine menschliche Eingabe bricht den laufenden Agentenbefehl trotzdem ab.

**Ein Agent zugleich:** der MCP-Server legt `agent_besitz.json` an; lebt der eingetragene Prozess
noch (geprüft wie `lease.lebt`, über `tasklist`, im Zweifel „lebt“), lehnt ein zweiter Agent mit
„belegt von ‹Name› seit ‹Zeit›“ ab.

**MCP-Server (`mcp/fahren.py`, neue Werkzeuge; die bisherigen 12 bleiben):** solange ein Befehl
unterwegs ist, frischt ein Hintergrundfaden `lebt` alle `AGENT_PULS_S` = 0.2 s auf. Stirbt der
Agent, schliesst der Klient die Verbindung, der MCP-Prozess endet, das Lebenszeichen bleibt aus.

**GUI (Tab „Fahren“):** Schalter „🤖 Agent darf fahren“ (nur am echten Spot aktiv; im Übungsraum
grau mit „im Übungsraum fährt der Agent ohne Freigabe“), darunter eine Zeile mit dem letzten
Agentenbefehl und seinem `warum`. Die GUI erkennt auch eine Zentrale, die der Agent gestartet hat
(`lauf.json` → `skript` endet auf `workshop/zentrale.py`), und hängt den Tab daran — sonst gäbe
es weder Puls noch Freigabe. Es gilt weiter „genau ein Lauf“: läuft schon etwas, wartet der neue.

## 2. Werkzeuge

Alle antworten mit kurzem JSON (`{"fehler": …}` statt einer Ausnahme, wie die bisherigen),
Bilder als MCP-Bild (`mcp.server.mcpserver.Image`). Koordinaten: Meter im Rahmen „vision“ — er
gilt für diesen Lauf und driftet langsam; 0° heisst geradeaus nach +x, positive Grad nach
links. So steht es in der Beschreibung jedes Werkzeugs.

**Starten und Beenden**

| Werkzeug | Verhalten |
|---|---|
| `zentrale_starten(ort, raum=None)` | `ort ∈ 2d, 3d, physik, echt`. Übungsraum: Backend sim/mujoco/physics, Raum aus dem Argument oder der Konfiguration, Raumregel wie im Tab (`welt/physik.tauglich`). Echt: Backend real mit `--auf-freigabe-warten`. Gestartet über `workshop/launcher.start_script` (Paketcode, Lauf unter `<Arbeitsordner>/Beispiele/runs`, Ausgabe in `mcp-ausgabe/`). Wartet höchstens 30 s auf Lauf-Verzeichnis und erstes Lagebild. Läuft schon eine Zentrale oder ein anderer Lauf: Ablehnung mit Kennung. |
| `zentrale_status()` | läuft sie, `ort`, Lauf-Kennung, Motoren, Freigabe, wer steuert |
| `zentrale_beenden()` | freundlicher Stopp (`stoppe_freundlich`), wartet bis zum Ende |

**Sehen**

| Werkzeug | Verhalten |
|---|---|
| `lage()` | aus `lagebild.json` und dem letzten `zustand.jsonl`: Pose (x, y, Blick°), Tempo, Akku, Motoren, Haltung, Freigabe; freie Strecke in 8 Richtungen (0°, ±45°, ±90°, ±135°, 180°), gelesen aus der Skizze als „frei bis X m / Wand bei X m / unbekannt ab X m“; Kopfraum; Menschen und Tags mit Peilung und Abstand ZU SPOT und in Weltkoordinaten; nahe Sperrzonen; Zustand des letzten Agentenbefehls. Lagebild älter als 2 s: „Zentrale antwortet nicht“. |
| `skizze(radius_m=5)` | das Lagebild-PNG in Farben (PIL, im MCP-Prozess), Ausschnitt um Spot, Spot als Pfeil, 1-m-Raster, Legende im Bild und im Text |
| `kamerabild()` | `ansicht.jpg`: echter Spot = Frontpanorama, 3D = gerendertes Zimmer von aussen (so benannt), 2D = „kein Bild in diesem Übungsraum“ |
| `tiefe_messen()` | Befehl `tiefe`, wartet auf das Ergebnis (höchstens 5 s) |

**Fahren** — jeder Befehl verlangt `warum` (Text, wird aufgezeichnet)

| Werkzeug | Verhalten |
|---|---|
| `fahre_zu(x, y, warum)` | Befehl `ziel` |
| `fahre_relativ(vor_m, links_m, warum)` | Befehl `relativ` |
| `drehe(grad, warum)` | Befehl `drehen` |
| `stoss(vx, vy, wz, dauer_s, warum)` | Befehl `stoss`, `dauer_s ≤ 2` |
| `folge_mensch(x, y, warum)` | Befehl `folgen` |
| `stopp()` | Befehl `stopp`, sofort |
| `warten(sekunden ≤ 10)` | wartet auf das Ende des laufenden Befehls oder die Zeit, gibt `lage()` zurück |

Fahr-Werkzeuge warten selbst höchstens `BEFEHL_WARTE_S` = 30 s und antworten mit `angekommen`,
`abgelehnt + Grund`, `versperrt + Grund`, `abgebrochen + Grund` oder `läuft noch` (dann fährt
der Befehl weiter, solange der MCP-Prozess lebt). Bestätigt die Zentrale die Nummer nicht
innerhalb von 2 s: „Zentrale antwortet nicht“, das Lebenszeichen hört auf.

**Nebenbei:** `licht(farbe)`, `piep()`, `suche(stufe)` — wie im Tab.

## 3. Aufzeichnung, Fehler, Prüfung

**Aufzeichnung:**

- Ereignisse `agent_befehl` (Art, Werte, `warum`, Agent) und `agent_ergebnis` (Zustand, Grund,
  Dauer) in `ereignisse.jsonl`; `freigabe` (an/aus, Grund) bei jedem Wechsel.
- **Jeder Werkzeugaufruf** — auch `lage` und `skizze` — als Zeile in `<lauf>/agent.jsonl`
  (Zeit, Werkzeug, Argumente, Kurzantwort).
- **Jedes Bild, das der Agent bekam**, unter `<lauf>/agent/` (Name mit Zeit und Werkzeug), damit
  sichtbar bleibt, was er sah, als er entschied.
- Pose und Zustand wie immer in `zustand.jsonl` (10 je Sekunde).

**Fehler:** kein Werkzeug wirft; jede Meldung sagt, was zu tun ist („keine Zentrale —
`zentrale_starten(…)`“, „abgelehnt: keine Freigabe — …“, „Zentrale antwortet nicht — …“,
„belegt von …“). Eine stolpernde Aufzeichnung hält keinen Befehl auf.

**Prüfung** (Laptop nur die betroffenen Dateien, volle Suite auf aicgolling gegen `main`):

- `record/agent.py`: lesen, schreiben, kaputt, Lebenszeichen, Freigabe nur mit frischem Puls.
- Zentrale: Rangfolge Taste > Klick > Agent; echt ohne Freigabe → abgelehnt, Übungsraum ohne;
  Agent-Totmann 0.5 s; Stoss gekappt und durch die Schranken (seitwärts/rückwärts 0.2 m/s, Gitter);
  `drehen` gegen die gemessene Gier; `tiefe` im 2D „nicht messbar“; `--auf-freigabe-warten`:
  Motoren aus bis zur Freigabe, dann `power_on` + `stand`; Ereignisse gegen den echten `RunRecorder`.
- GUI: Schalter schreibt `freigabe.json`; Taste und Klick nehmen sie zurück; Zeile zeigt `warum`;
  eine vom Agenten gestartete Zentrale wird erkannt.
- MCP: jedes Werkzeug ohne Zentrale gibt die richtige Meldung; zweiter Agent → „belegt“;
  `skizze` und `lage` aus einem festen Lagebild (Richtungen, Peilungen).
- **Kette mit dem echten Programm im 2D-Übungsraum über die MCP-Funktionen:** `zentrale_starten`
  → `lage` → `fahre_zu` → „angekommen“ → `stopp` → `zentrale_beenden`, dazu `agent.jsonl` und
  die Ereignisse im Lauf.
- Der Weg „echt“ läuft im Test mit dem Trockenlauf statt des Roboters (wie `FAHREN_BACKEND`).

**Abnahme am Gerät — A43:** (1) Agent startet „echt“: Motoren bleiben aus. (2) Freigabe ein:
Spot steht auf, `fahre_zu` über 2 m kommt an. (3) Eine Taste: Spot hält, Freigabe aus, der
nächste Agentenbefehl wird abgelehnt. (4) Agentenprozess beenden: Spot hält binnen 0.5 s.

**Doku:** `docs/AGENTEN.md` (einrichten in Claude Code und Codex über `spotlab mcp`, die Werkzeuge,
die Regeln); CLAUDE.md: „ein Agent darf den Roboter nicht bewegen“ wird zu „nur über die Zentrale,
der echte Spot nur mit Freigabe eines Menschen“; `docs/ANBINDUNG.md` verweist darauf.

## Nicht in Teil 1

Karten laden, verorten, navigieren und aufnehmen (Teil 2), Rekonstruktion zum Raum (Teil 2),
Sperrzonen als No-Go-Regionen im Roboter (SDK `user_nogo_regions`) und Glaserkennung (Teil 3;
`hazard_detection_mode` braucht laut SDK 5.0.1.1 eine CORE I/O), Experiment-Protokoll und
Auswertung (Teil 4), Anschluss virtueller Gehirne (Teil 5), Rohdaten der Tiefenkameras an den
Agenten (Punktwolken), mehrere Agenten zugleich.
