# Agenten am Spot, Teil 2: Karten durch den Agenten

Entwurf vom 09.10.2026, im Gespräch abschnittsweise freigegeben. Zweiter von fünf Teilen
(1 sieht und fährt · **2 Karten** · 3 Glas und Gefahrenzonen · 4 Experimente · 5 virtuelle
Gehirne). Baut auf Teil 1 (`2026-10-09-agent-faehrt-design.md`, in `main` seit 5c22776) und auf
der Kartenarbeit der Steuerzentrale (Teil 3, `2026-09-27-steuerzentrale-karten-design.md`).

## Entscheidungen

- **Am echten Spot richtige GraphNav-Karten, im Übungsraum Merkorte.** GraphNav gibt es nur am
  echten Spot; eine nachgebaute Attrappe wurde verworfen — sie könnte sich anders verhalten als
  der echte Dienst. Merkorte heissen anders und tun nicht so, als wären sie Karten.
- **Merkorte bleiben im Übungsraum gespeichert** (der Raum hat feste Koordinaten), am echten Spot
  gelten sie nur für den Lauf (der Rahmen „vision“ setzt sich bei jedem Start neu; dort sind die
  Kartenwegpunkte das Dauerhafte).
- **Die Fahrt zu einem Merkort geht über den ganzen gesehenen Boden** — ohne die 5-m-Grenze
  eines Klicks, mit denselben Schranken unterwegs.
- **Karte → Raum** (Rekonstruktion wie im Raumeditor) gehört zu Teil 2, **ohne Korrigierer** —
  der bleibt Handarbeit im Editor.
- **Ein Klick auf einen Wegpunkt im Tab „Fahren“ fährt dorthin** — Mensch und Agent nehmen
  denselben Weg, und die Navigation lässt sich ohne Agent prüfen.
- **Weg A: Übergabe wie beim Folgen.** Die Zentrale übergibt an die EINE vorhandene Navigation
  (`api/navigation.navigate_to`, mit Tempodeckel); verworfen: eine eigene Schrittfahrt in der
  Zentrale (zweite Fassung der Navigation) und die Navigation im Faden der Kartenarbeit (zwei
  Fäden, die den Roboter steuern).

## 1. Aufbau und Sicherheit

**Neue Arten in `agent_befehl.json`** (`record/agent.ARTEN_BEFEHL`):

| Art | Werte | Was die Zentrale tut | Freigabe nötig |
|---|---|---|---|
| `karte_laden` | `name` | Kartenarbeit: hochladen, verorten | nein |
| `aufnahme_start` | `name` (wahlweise) | Kartenarbeit: weiterführen, wenn verortet, sonst neu | nein |
| `aufnahme_stopp` | — | Kartenarbeit: beenden, nachbearbeiten, unter freiem Namen speichern | nein |
| `wegpunkt_setzen` | `name` | Kartenarbeit, nur während einer Aufnahme | nein |
| `zum_wegpunkt` | `name` | GraphNav-Fahrt, nur verortet und ohne laufende Aufnahme | ja |
| `merkort_setzen` | `name`, wahlweise `x`, `y` | ohne x/y Spots jetziger Ort (Rahmen „vision“) | nein |
| `merkort_loeschen` | `name` | | nein |
| `zum_merkort` | `name` | Klickfahrt (Quelle „agent“) über den ganzen gesehenen Boden | ja |

Die Freigabe-Regel aus Teil 1 gilt unverändert: am echten Spot fahren `zum_wegpunkt` und
`zum_merkort` nur mit „🤖 Agent darf fahren“; alles andere geht immer.

**Kartenaufträge des Agenten** gehen an dieselbe Kartenarbeit wie die des Tabs
(`Kartenarbeit.auftrag`), mit einer **eigenen Nummernfolge** — sonst fiele eine Agentennummer mit
einer Tab-Nummer zusammen, und die Kartenarbeit hielte den Auftrag für erledigt. Es gilt dieselbe
Regel wie im Tab: eine Kartenarbeit zugleich, sonst Ablehnung mit Grund. Das Ergebnis meldet der
Agentenbefehl, wenn die Kartenarbeit fertig ist (`verortet`, `sucht_tag`, `nimmt_auf`,
gespeichert unter …, oder der Grund des Scheiterns).

**Fahrt zu einem Wegpunkt (Weg A):** der Fahrtakt übergibt an `navigate_to` — wie
`_folge_mensch` an `folgen.folge` — mit der Karte, die die Kartenarbeit geladen hat (`Map` aus
Name, Ordner und Graph). `navigate_to` bekommt einen Parameter für den Nachfragetakt
(`takt_s`, Vorgabe wie bisher 0.5 s); die Zentrale nimmt 0.2 s, damit Spot nach dem Ende des
Agenten so schnell hält wie bei jeder anderen Agentenfahrt. `abbruch()` prüft und erledigt wie
`laeuft()` beim Folgen: Stopp, Aktionen und Kartenaufträge, Taste, neuer Klick, neuer
Agentenbefehl, Lebenszeichen (0.5 s), Freigabe aus, und „verloren“ aus der Kartenarbeit. Ergebnis
`angekommen` oder `abgebrochen` mit Grund; ein `NavigationError` des Roboters steht mit seinem
Text im Grund. Abgelehnt wird ohne geladene Karte, ohne Verortung, während einer Aufnahme und bei
unbekanntem Wegpunkt (mit der Liste der vorhandenen Namen).

**Klick auf einen Wegpunkt im Tab:** liegt der Klick in `WEGPUNKT_KLICK_M` um einen eingeblendeten
Wegpunkt, schreibt der Tab ein Klickziel der Art `wegpunkt` mit dessen Namen (oder Kennung). Es
führt in dieselbe Übergabe, mit dem Lebenszeichen des Tabs wie die Klickfahrt; Vorrang Taste >
Klick > Agent. Ein Wegpunkt-Klick nimmt — wie jeder Klick — die Freigabe des Agenten zurück.

**Merkorte** (`workshop/merkorte.py`, rein rechnerisch): Name → (x, y) im Rahmen „vision“, Namen
eindeutig (bereinigt wie Wegpunktnamen). Die Zentrale hält sie. Im Übungsraum (Backend in
`OHNE_ROBOTER` und ein Raum im Lauf) liest sie beim Start `<Arbeitsordner>/raeume/<raum>.merkorte.json`
und schreibt die Datei bei jeder Änderung atomar neu — eine eigene Datei, damit der Raumeditor
sie beim Speichern nicht verliert; sie geht auch bei Vorlagen, die im Paket liegen. Am echten
Spot gibt es keine Datei. `zum_merkort` wird ein Ziel der Klickfahrt mit Quelle „agent“ und ohne
Weitengrenze (die Wegsuche plant über die ganze Skizze); die Schranken unterwegs sind die der
Klickfahrt. Das Lagebild trägt die Merkorte (`merkorte: [{name, x, y}]`); der Tab zeichnet sie
als Punkte mit Namen.

**Karte → Raum** macht der MCP-Server selbst, ohne Zentrale und ohne Roboter:
`maps/rekonstruktion.rekonstruiere(ordner)` wie der Dialog im Raumeditor, dann `raum_speichern`
und `pauspapier.schreibe` (mit Weg) unter `raeume/` — unter einem freien Namen, nie über einen
vorhandenen.

## 2. Werkzeuge (`mcp/karten.py`)

Dieselben Hilfen wie in `mcp/fahren.py` (Befehl mit Bestätigung und Lebenszeichen, Besitz,
Aufzeichnung in `agent.jsonl`, `{"fehler": …}` statt Ausnahme).

**Karten** — nur am echten Spot; im Übungsraum antworten sie „Karten gibt es nur am echten Spot —
im Übungsraum `merkort_setzen` und `zum_merkort`“:

| Werkzeug | Verhalten |
|---|---|
| `karten_auflisten()` | gibt es schon (`werkzeuge.py`), bleibt |
| `karte_laden(name)` | wartet ≤ 30 s: `verortet`, `sucht_tag` (Hinweis: einen Tag der Karte ins Bild drehen, dann erneut) oder `gescheitert` mit Grund |
| `aufnahme_starten(name)` | weiterführen, wenn verortet, sonst neu |
| `aufnahme_beenden()` | wartet aufs Speichern (≤ 120 s) und nennt den freien Namen |
| `wegpunkt_setzen(name)` | nur während einer Aufnahme |
| `zum_wegpunkt(name, warum)` | GraphNav-Fahrt; Antworten wie `fahre_zu` (≤ 30 s, sonst „läuft noch“) |

**Merkorte** — Übungsraum und echter Spot:

| Werkzeug | Verhalten |
|---|---|
| `merkort_setzen(name, x=None, y=None)` | ohne x/y Spots jetziger Ort |
| `merkort_loeschen(name)` | |
| `zum_merkort(name, warum)` | Wegsuche über den ganzen gesehenen Boden; Antworten wie `fahre_zu` |

**Rekonstruktion** — ohne Zentrale:

| Werkzeug | Verhalten |
|---|---|
| `raum_aus_karte(karte, name=None)` | Raum und Pauspapier unter freiem Namen; Antwort: Name, Pfad, Wände, Treppen, Rampen, Tags, Dauer, Hinweis „im Raumeditor korrigieren, dann `zentrale_starten("3d", raum=…)`“ |

**Erweiterungen aus Teil 1:** `lage()` bekommt `karte` (Name, Zustand, Grund; verortet: die
nächsten 20 Wegpunkte mit Peilung und Abstand zu Spot) und `merkorte` (mit Peilung und Abstand);
`skizze()` zeichnet Merkorte (Raute mit Namen) und, verortet, die Kartenwegpunkte;
`zentrale_status()` nennt die geladene Karte.

## 3. Aufzeichnung, Fehler, Prüfung

**Aufzeichnung** wie in Teil 1 (`agent_befehl`, `agent_ergebnis`, `agent.jsonl`, `agent/`);
`navigate_to` schreibt seine Rückmeldungen wie bisher; der gespeicherte Raum steht mit Pfad in der
Antwort von `raum_aus_karte` und damit in `agent.jsonl`.

**Fehler:** kein Werkzeug wirft, jede Meldung sagt, was zu tun ist — „nicht verortet — einen Tag
der Karte ins Bild drehen, dann `karte_laden` erneut“, „während einer Aufnahme fährt Spot keine
Wegpunkte an — erst `aufnahme_beenden`“, „Merkort ‹Tür› gibt es nicht — vorhanden: …“.

**Prüfung** (Laptop nur die betroffenen Dateien, volle Suite auf aicgolling gegen `main`):

- Wegpunktfahrt mit einer GraphNav-Attrappe: kommt an; bricht ab bei Taste, neuem Klick, neuem
  Agentenbefehl, Lebenszeichen, Freigabe aus, „verloren“; abgelehnt ohne Karte, ohne Verortung,
  während einer Aufnahme, bei unbekanntem Wegpunkt.
- `navigate_to(takt_s=…)`; die bisherigen Navigationstests bleiben grün.
- Kartenaufträge des Agenten mit eigener Nummernfolge, kein Zusammenstoss mit dem Tab.
- Merkorte: setzen (Spots Ort), löschen, eindeutige Namen; Datei im Übungsraum und beim nächsten
  Start wieder da; am echten Spot nichts auf der Platte; `zum_merkort` weiter als 5 m.
- Tab: Klick auf einen Wegpunkt schreibt das Klickziel `wegpunkt`; Merkorte werden gezeichnet.
- MCP: Karten-Werkzeuge im Übungsraum geben den Hinweis; `lage()` und `skizze()` mit Merkorten
  und Wegpunkten; `raum_aus_karte` an der Katakomben-Karte (übersprungen, wo sie fehlt) und mit
  freiem Namen.
- **Kette mit dem echten Programm im 2D-Übungsraum:** `zentrale_starten("2d", "durchgang")` →
  `merkort_setzen("start")` → `fahre_relativ` → `zum_merkort("start")` → angekommen; die
  Merkort-Datei liegt im Arbeitsordner.

**Abnahme am Gerät — A45:** (1) der Agent lädt eine Karte und wird verortet; (2) mit Freigabe
fährt er zu einem Wegpunkt; (3) eine Taste bricht die Fahrt ab; (4) Aufnahme mit zwei Wegpunkten,
gespeichert unter neuem Namen; (5) ein Klick auf einen Wegpunkt im Tab fährt dorthin;
(6) Merkort setzen, wegfahren, zurück.

## Nicht in Teil 2

Sperrzonen und Glas auf dem Roboter (Teil 3), der Korrigierer für den Agenten, Experimente und
Auswertung (Teil 4), virtuelle Gehirne (Teil 5), eine GraphNav-Attrappe im Übungsraum.
