# Agenten am Spot

Ein Agent — Claude Code, Codex oder ein anderer MCP-Klient — kann Spot über spotlab **sehen und
fahren**: im Übungsraum frei, am echten Spot nur, solange ein Mensch es erlaubt. Teil 1 von fünf
(Entwurf `docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`); Karten durch den Agenten,
Glas und Gefahrenzonen, Experimente und virtuelle Gehirne folgen als eigene Teile.

**Der Agent hat keinen eigenen Weg zum Roboter.** Er startet die Steuerzentrale (dasselbe
Programm wie der Tab „Fahren“, `workshop/zentrale.py`) und spricht mit ihr über Dateien im
Lauf-Verzeichnis. Jede Fahrt geht durch dieselben Schranken wie ein Klick in die Draufsicht:
Wegsuche über gesehenen Boden, Hindernisgitter, Kopfraum, langsame Stufe.

## Einrichten

```bash
pip install "spotlab[mcp]"
```

spotlab braucht einen **Arbeitsordner** (im Fenster unter „Projekte“ oder mit `spotlab login`) —
dort landen die Läufe, unter `<Arbeitsordner>/Beispiele/runs/`.

**Claude Code:**

```bash
claude mcp add spotlab --env SPOTLAB_AGENT=claude -- spotlab mcp
```

**Codex** (`~/.codex/config.toml`):

```toml
[mcp_servers.spotlab]
command = "spotlab"
args = ["mcp"]
env = { SPOTLAB_AGENT = "codex" }
```

`SPOTLAB_AGENT` ist der Name, unter dem der Agent in der Aufzeichnung und im Tab „Fahren“
erscheint (ohne ihn: „agent“).

## Ablauf

**Übungsraum** — der Agent darf alles selbst:

1. `zentrale_starten("2d", raum="durchgang")` (oder `"3d"`, `"physik"`) — ohne Roboter, der
   Prozess kann gar keinen erreichen (`SPOTLAB_NUR_TROCKEN=1`).
2. `lage()` und `skizze()` lesen, dann `fahre_zu`, `drehe`, `stoss` …
3. `zentrale_beenden()`.

**Echter Spot** — ein Mensch sitzt vor spotlab:

1. Ein Mensch öffnet spotlab (das Fenster muss laufen: nur dort gibt es den Schalter).
2. Der Agent ruft `zentrale_starten("echt")`. Die Zentrale verbindet (Lease, Not-Aus-Eintrag),
   die **Motoren bleiben aus**. spotlab erkennt den Lauf und hängt den Tab „Fahren“ daran.
3. Der Mensch schaltet im Tab „Fahren“ **„🤖 Agent darf fahren“** ein. Erst jetzt schaltet die
   Zentrale die Motoren ein und Spot steht auf.
4. **Jede menschliche Eingabe nimmt die Freigabe zurück:** eine Fahrtaste, ein Klick in die
   Draufsicht, „■ Stopp“, der NOT-AUS. Der laufende Agentenbefehl endet sofort
   („ein Mensch hat übernommen“), der nächste wird abgelehnt, bis der Schalter wieder an ist.
5. Am Ende `zentrale_beenden()` — oder der Mensch beendet die Fahrt im Tab.

Ohne Freigabe darf der Agent **lesen** (`lage`, `skizze`, `kamerabild`, `tiefe_messen`), aber
nicht fahren.

## Werkzeuge

| Werkzeug | Was es tut |
|---|---|
| `zentrale_starten(ort, raum)` | `ort`: `2d`, `3d`, `physik`, `echt`; wartet ≤ 30 s auf das erste Lagebild |
| `zentrale_status()` | läuft sie, wo, antwortet sie, Motoren, Freigabe, wer steuert |
| `zentrale_beenden()` | freundlicher Stopp: Spot hält und setzt sich |
| `lage()` | Pose, Tempo, Akku, Motoren, Freigabe, freie Strecke in 8 Richtungen, Kopfraum, Menschen, Tags, letzter Befehl |
| `skizze(radius_m)` | die Draufsicht als Bild: +y oben, Raster 1 m, weiss frei, schwarz Wand, grau unbekannt |
| `kamerabild()` | echter Spot: Frontkameras; 3D: das Zimmer von aussen; 2D: keines |
| `tiefe_messen()` | Tiefenkameras vorne: Abstand links / mitte (±10°) / rechts und Kopfraum |
| `fahre_zu(x, y, warum)` | zum Punkt, wie ein Klick (Wegsuche, höchstens 5 m, langsam) |
| `fahre_relativ(vor_m, links_m, warum)` | ein Stück relativ zu Spot |
| `drehe(grad, warum)` | auf der Stelle, positiv = links, auf 3° genau |
| `stoss(vx, vy, wz, dauer_s, warum)` | ein kurzer Fahrstoss, höchstens 2 s |
| `folge_mensch(x, y, warum)` | folgt dem Menschen bei (x, y) — braucht Kameras |
| `stopp()` | hält sofort an — darf jeder Agent |
| `warten(sekunden)` | ≤ 10 s auf das Ende des Befehls, dann `lage()` |
| `licht(farbe)` · `piep()` · `suche(stufe)` | wie im Tab, Licht und Ton nur am echten Spot |

Fahrbefehle warten höchstens 30 s und antworten mit `angekommen`, `abgelehnt`, `versperrt`,
`abgebrochen` (immer mit Grund) oder `läuft noch` — dann fährt der Befehl weiter, und
`warten()` holt das Ergebnis. **`warum` ist Pflicht** und landet in der Aufzeichnung.

**Koordinaten:** Meter im Rahmen „vision“. Er gilt für diesen Lauf und driftet über lange Wege
langsam. Weltwinkel: 0° = +x, positive Grad nach links. Richtungen und Peilungen in `lage()`
sind **relativ zu Spots Blick**: 0° voraus, +90° links, −90° rechts, 180° hinten.

## Regeln

- **Totmann:** solange ein Befehl läuft, frischt der MCP-Server sein Lebenszeichen alle 0.2 s
  auf. Endet der Agent, endet der MCP-Prozess — nach 0.5 s ohne Lebenszeichen hält Spot.
- **Vorrang:** Taste vor Klick vor Agent. Fährt ein Mensch gerade, wird ein Fahrbefehl abgelehnt.
- **Ein neuer Befehl beendet den alten** — auch `tiefe_messen` während einer Fahrt.
- **Stösse:** vorwärts mit allen Schranken der Klickfahrt; seitwärts und rückwärts höchstens
  0.2 m/s und nur über gesehenen Boden (hinten sieht Spot schlechter).
- **Ein Agent zugleich:** wer die Zentrale gestartet oder zuerst befohlen hat, steuert
  (`agent_besitz.json`); ein zweiter Agent bekommt „belegt von …“, solange der erste lebt.
  Anhalten (`stopp`) darf jeder.
- **Glas sieht Spot nicht** — weder das Hindernisgitter noch die Tiefenkameras. Bis Teil 3
  (Glas und Gefahrenzonen) gilt: am echten Spot nie ohne Aufsicht in die Nähe von Glas.

## Aufzeichnung

Alles liegt im Lauf der Zentrale (`<Arbeitsordner>/Beispiele/runs/<lauf>/`):

- `agent.jsonl` — jeder Werkzeugaufruf mit Zeit, Agent, Argumenten und kurzer Antwort.
- `agent/` — jedes Bild, das der Agent bekam (Skizze, Kamerabild), mit Zeit im Namen: so bleibt
  sichtbar, was er sah, als er entschied.
- `ereignisse.jsonl` — `agent_befehl` (Befehl, Werte, warum, Agent), `agent_ergebnis` (Zustand,
  Grund, Dauer) und `freigabe` (an/aus) bei jedem Wechsel.
- `zustand.jsonl` — Pose und Zustand wie in jedem Lauf, 10-mal je Sekunde.

Die Ausgabe des Programms steht unter `<Arbeitsordner>/mcp-ausgabe/`.

Am Gerät geprüft wird das mit Abnahmepunkt **A43** (`docs/ABNAHME.md`).
