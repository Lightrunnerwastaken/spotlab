# Agenten am Spot

Ein Agent — Claude Code, Codex oder ein anderer MCP-Klient — kann Spot über spotlab **sehen und
fahren**: im Übungsraum frei, am echten Spot nur, solange ein Mensch es erlaubt — und er kann
**Karten** nutzen und sich **Orte merken**. Teile 1 und 2 von fünf (Entwürfe
`docs/superpowers/specs/2026-10-09-agent-faehrt-design.md` und
`docs/superpowers/specs/2026-10-09-agent-karten-design.md`); Glas und Gefahrenzonen, Experimente
und virtuelle Gehirne folgen als eigene Teile.

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
| `zentrale_status()` | läuft sie, wo, antwortet sie, Motoren, Freigabe, wer steuert, geladene Karte |
| `zentrale_beenden()` | freundlicher Stopp: Spot hält und setzt sich |
| `lage()` | Pose, Tempo, Akku, Motoren, Freigabe, freie Strecke in 8 Richtungen, Kopfraum, Menschen, Tags, letzter Befehl, Karte und Merkorte |
| `skizze(radius_m)` | die Draufsicht als Bild: +y oben, Raster 1 m, weiss frei, schwarz Wand, grau unbekannt, violette Rauten Merkorte, türkise Punkte Wegpunkte |
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

## Karten und Merkorte (Teil 2)

**Karten gibt es nur am echten Spot** — es sind GraphNav-Karten, dieselben wie im Tab „Karten“
(`<Arbeitsordner>/karten/`). Im Übungsraum antworten die Karten-Werkzeuge mit dem Hinweis auf
Merkorte, ohne einen Befehl zu schicken. Die Zentrale gibt jeden Kartenauftrag an DIESELBE
Kartenarbeit wie der Tab; eine Kartenarbeit läuft im Hintergrund und lässt sich nicht anhalten.

| Werkzeug | Was es tut |
|---|---|
| `karten_auflisten()` | die gespeicherten Karten (gab es schon) |
| `karte_laden(name)` | lädt die Karte auf den Roboter und verortet Spot, ≤ 30 s; `karte.zustand` ist `verortet` oder `sucht_tag` (dann einen AprilTag der Karte ins Bild drehen — Spot versucht es von selbst wieder) |
| `aufnahme_starten(name)` | verortet in einer geladenen Karte: weiterführen, sonst neu |
| `aufnahme_beenden()` | beendet, bearbeitet nach (Schleifenschluss) und speichert unter einem FREIEN Namen, ≤ 120 s; `karte.gespeichert_als` nennt ihn |
| `wegpunkt_setzen(name)` | nur während einer Aufnahme: ein benannter Wegpunkt an Spots Ort |
| `zum_wegpunkt(name, warum)` | GraphNav-Fahrt zum benannten Wegpunkt, mit Tempodeckel und Freigabe; Antworten wie `fahre_zu` |
| `merkort_setzen(name, x, y)` | merkt sich einen Ort — ohne `x`/`y` Spots jetzigen |
| `merkort_loeschen(name)` | vergisst ihn |
| `zum_merkort(name, warum)` | Wegsuche über den ganzen gesehenen Boden, ohne die 5-m-Grenze von `fahre_zu` |
| `raum_aus_karte(karte, name)` | baut aus einer Karte einen Raum für den Übungsraum — ohne Zentrale |

**Nur BENANNTE Wegpunkte sind Ziele.** GraphNav legt beim Aufnehmen alle paar Meter selbst einen
Wegpunkt an; die haben keinen Namen und erscheinen weder in `lage()` noch in `skizze()`. `lage()`
nennt verortet die 20 nächsten benannten mit Peilung und Abstand. Wer eigene Ziele will, setzt sie
in der Aufnahme mit `wegpunkt_setzen` oder benennt sie im Tab „Karten“ nachträglich.

**Ablauf am echten Spot:** `zentrale_starten("echt")`, Freigabe durch den Menschen,
`karte_laden("flur")`, bei `sucht_tag` einen Tag ins Bild drehen (`drehe`), bis `lage()` die Karte
`verortet` nennt, dann `zum_wegpunkt("Küche", warum=…)`. Spot fährt dabei nicht weiter, als er sich
in der Karte findet: wird er `verloren`, bricht die Fahrt ab. Ein Klick des Menschen auf einen
benannten Wegpunkt im Tab „Fahren“ fährt ebenso hin.

**Merkorte** gibt es überall — im Übungsraum fahren sie die Wegsuche statt GraphNav. Sie liegen im
Rahmen „vision“: im Übungsraum ist der bei jedem Start gleich, und die Merkorte bleiben neben dem
Raum gespeichert (`<Arbeitsordner>/raeume/<raum>.merkorte.json`, auch für eine Vorlage); am echten
Spot setzt sich „vision“ bei jedem Start neu, dort leben sie nur bis zum Ende der Zentrale. Der
Mensch sieht sie im Tab „Fahren“ als Rauten mit Namen.

**Rekonstruktion:** `raum_aus_karte("flur")` baut aus der gespeicherten Karte Wände, Treppen,
Rampen und Tags (dieselbe Rechnung wie im Raumeditor, ohne Korrigierer) und speichert den Raum
samt Pauspapier unter einem freien Namen — nie über einen vorhandenen Raum und nie unter dem Namen
einer Vorlage. Danach im Raumeditor korrigieren (Lücken schliessen, Gelände bauen) und dort üben:
`zentrale_starten("3d", raum="flur")`.

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

Am Gerät geprüft wird das mit den Abnahmepunkten **A43** (fahren) und **A45** (Karten)
(`docs/ABNAHME.md`).
