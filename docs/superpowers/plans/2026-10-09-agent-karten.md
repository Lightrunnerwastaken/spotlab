# Agenten am Spot, Teil 2: Karten — Implementation Plan

> Inline ausgeführt (keine Sub-Agenten, Nutzerregel), TDD je Aufgabe, Worktree `.worktrees/karten`,
> Branch `feat/agent-karten` (von `main` 5c22776). Am Laptop nur die betroffenen Testdateien; die
> volle Suite läuft auf aicgolling (`cd ~/spotlab-X && …`), Vergleich gegen `main`.

**Goal:** Ein Agent arbeitet mit Karten — am echten Spot GraphNav (laden, verorten, aufnehmen,
Wegpunkte, hinfahren), im Übungsraum mit Merkorten —, ein Mensch fährt per Klick auf einen
Wegpunkt, und aus einer Karte wird ein Übungsraum.

**Spec:** `docs/superpowers/specs/2026-10-09-agent-karten-design.md`

## Global Constraints

- Alles aus Teil 1 gilt weiter: kein eigener Weg des MCP-Servers zum Roboter, Übungsraum mit
  `nur_trocken`, Rangfolge Taste > Klick > Agent, Freigabe nur am echten Spot und nur für Fahrten,
  Totmann 0.5 s, Meldungen deutsch mit dem, was zu tun ist, `{"fehler": …}` statt Ausnahme.
- Fahr-Arten mit Freigabe: `zum_wegpunkt`, `zum_merkort` (dazu die aus Teil 1).
- Die EINE Navigation ist `api/navigation.navigate_to` (Tempodeckel); keine zweite Fassung.
- `Kartenarbeit.erledigt` bleibt die Nummer des TABS (der Tab vergleicht sie als Zahl, `<`);
  Agentenaufträge zählen getrennt.
- Merkorte: Rahmen „vision“; Datei nur im Übungsraum (`<Arbeitsordner>/raeume/<raum>.merkorte.json`,
  atomar), am echten Spot nur im Speicher. Die Raumdatei wird nie angefasst.
- Gespeichert wird nie über Vorhandenes (Karten: `freier_name`, Räume: freier Name).
- GUI ohne `bosdyn`/`spotlab.backends`, Farben nur aus dem Thema.
- Konstanten: `NAVI_TAKT_S = 0.2` (Zentrale), `WEGPUNKT_KLICK_M = 0.5`, `KARTE_WARTE_S = 30.0`,
  `SPEICHERN_WARTE_S = 120.0`, `WEGPUNKTE_IN_LAGE = 20`.

---

### Task 1: Kartenarbeit für zwei Auftraggeber (`workshop/kartenarbeit.py`)
- `auftrag(nummer, was, name=None, quelle="tab") -> str | None`: Nummern je Quelle getrennt
  (`self._nummern = {}`); nur `quelle == "tab"` setzt `self.erledigt`. Rückgabe: Grund einer
  Ablehnung (auch in `self.grund`), sonst None. Bestehende Aufrufer ignorieren die Rückgabe.
- `arbeitet` (Eigenschaft, liest `_arbeitet`).
- `navigationskarte() -> api.navigation.Map`: aus `store.finde(arbeitsordner, name)` und
  `store.lade_graph`, beim Laden einmal gebaut und gemerkt; wirft `SpotlabError` mit Grund: keine
  Karte („erst `karte_laden`“), nicht verortet („einen Tag der Karte ins Bild drehen“), Aufnahme
  läuft („erst `aufnahme_beenden`“), beschäftigt.
- `gespeichert_als` (Name nach dem letzten erfolgreichen Speichern, sonst None).
- Tests `tests/test_workshop_kartenarbeit.py`: Tab 3 und Agent 3 werden beide angenommen; `erledigt`
  bleibt bei der Tab-Nummer; Ablehnung gibt den Grund zurück; `navigationskarte` je Fall.

### Task 2: Nachfragetakt der Navigation (`api/navigation.py`)
- `navigate_to(..., takt_s=NACHSENDE_INTERVALL_S)`: `schlaf(takt_s)` statt der Konstante.
- Test `tests/test_api_navigation.py`: mit `takt_s=0.2` schläft die Schleife 0.2; die bisherigen
  Tests bleiben unverändert grün.

### Task 3: Merkorte und Klickfahrt ohne Weitengrenze
- `workshop/merkorte.py`: `Merkorte(pfad=None)`: `setze(name, x, y) -> name` (getrimmt, 1–40
  Zeichen, sonst `ValueError`; gleicher Name = verschieben), `loesche(name) -> bool`,
  `hole(name) -> (x, y) | None`, `namen()`, `als_daten() -> [{name, x, y}]`; mit `pfad` lesen beim
  Bau (kaputt/fehlend = leer) und nach jeder Änderung atomar schreiben (`record/atomar.py`).
  `pfad_fuer(arbeitsordner, raum) -> Path` (`welt.raum.raum_pfad(...).with_suffix(".merkorte.json")`).
- `wegsuche.pruefe_ziel(..., max_weite_m)`: `None` heisst ohne Grenze. `Klickfahrt.neues_ziel(...,
  max_weite_m=MAX_WEITE_M)` reicht es durch.
- Tests `tests/test_workshop_merkorte.py` (Rundreise über die Datei, kaputte Datei, Namen) und je
  ein Test in `test_workshop_wegsuche.py` / `test_workshop_klickfahrt.py` (12 m weit mit `None`).

### Task 4: Protokoll (`record/agent.py`, `record/zentrale.py`)
- `ARTEN_BEFEHL` += `karte_laden`, `aufnahme_start`, `aufnahme_stopp`, `wegpunkt_setzen`,
  `zum_wegpunkt`, `merkort_setzen`, `merkort_loeschen`, `zum_merkort`.
- `KLICKARTEN` += `"wegpunkt"`; `Klickziel.name: str | None = None`;
  `schreibe_klickziel(..., art=..., name=None)` schreibt `name`, `lies_klickziel` liest es.
- Tests: Rundreise des Wegpunkt-Klickziels; ein altes Klickziel ohne `name` bleibt lesbar.

### Task 5: Zentrale — Kartenbefehle und Merkorte des Agenten (`workshop/zentrale.py`)
- `FAHR_ARTEN` += `zum_wegpunkt`, `zum_merkort`. `Zentrale(..., merkorte=None)` (eine
  `Merkorte`; ohne Angabe eine im Speicher).
- `karte_laden`/`aufnahme_start`/`aufnahme_stopp`/`wegpunkt_setzen`: ohne Kartenarbeit oder ohne
  `kann` → abgelehnt („Karten gibt es nur am echten Spot — im Übungsraum Merkorte“);
  `self._karten.auftrag(nummer, was, name, quelle="agent")`; Ablehnung → `abgelehnt` mit Grund;
  sonst `_agent_lauf = {"art": "karte", "was": was}`. Je Takt: wenn `not self._karten.arbeitet`,
  Ende mit `erledigt` (Laden: verortet oder sucht_tag; Start: nimmt_auf; Stopp: gespeichert;
  Wegpunkt: gesetzt) oder `abgebrochen` mit `self._karten.grund`; dazu Feld `karte` =
  `{zustand, name, grund, gespeichert_als}`. Kein Lebenszeichen nötig (Spot fährt nicht).
- `merkort_setzen` (ohne x/y: `_lage_jetzt()`), `merkort_loeschen` → `erledigt`/`abgelehnt`.
  `zum_merkort` → `klick.neues_ziel(..., quelle="agent", max_weite_m=None)`, weiter wie `ziel`.
- Lagebild: `merkorte: self._merkorte.als_daten()`.
- Hauptprogramm: im Übungsraum (Backend in `OHNE_ROBOTER`, Raum aus `SPOTLAB_RAUM` oder der
  Konfiguration, Arbeitsordner gesetzt) `Merkorte(merkorte.pfad_fuer(arbeitsordner, raum))`.
- Tests `tests/test_workshop_zentrale_agent.py`: Kartenbefehl mit Attrappe-Kartenarbeit (Ende und
  Feld `karte`; Ablehnung mit Grund; im Übungsraum abgelehnt); Merkort an Spots Ort, mit x/y,
  löschen, unbekannt mit Liste; `zum_merkort` 12 m weit fährt los; Merkorte im Lagebild; die Datei
  aus dem Hauptprogramm (Funktion `merkorte_fuer(lauf_dir, arbeitsordner, raum)` testbar machen).

### Task 6: Zentrale — Fahrt zu einem Wegpunkt (`workshop/zentrale.py`)
- `_zum_wegpunkt(nummer, name, quelle, abgeloest)`: `karte = self._karten.navigationskarte()`
  (Fehler → abgelehnt); Übergabe an `navigation.navigate_to(spot.backend, spot.recorder, karte,
  name, spot.limits, abbruch=…, takt_s=NAVI_TAKT_S)`; `abbruch()` wie `laeuft()` beim Folgen
  (Stopp, Aktionen, Kartenaufträge, Taste, `abgeloest()`, und `self._karten.zustand == "verloren"`).
  `True` → `angekommen`; `False` → `abgebrochen` mit Grund; `NavigationError`/`SpotlabError` →
  `abgebrochen` mit Text. Danach `self._faehrt = False`. Der Stand steht in `klick.stand`
  (`zustand="navigiert"`, Quelle) und — beim Agenten — im Platz `agent`.
- Agent: `zum_wegpunkt` → `_zum_wegpunkt(..., "agent", self._agent_abloese(ab))` (blockiert,
  `_agent_neu` gibt True zurück). Tab: Klickziel `art="wegpunkt"` → `_zum_wegpunkt(kz.nummer,
  kz.name, "tab", self._klick_abloese(kz))`.
- Tests mit einer GraphNav-Attrappe (`navigate_step`/`navigation_status`, `capabilities` mit
  `GRAPH_NAV`, `travel_params`): kommt an; Abbruch durch Taste, neuen Klick, neuen Befehl,
  Lebenszeichen, Freigabe aus, „verloren“; abgelehnt ohne Karte / unverortet / in Aufnahme /
  unbekannter Wegpunkt (Liste der Namen); Tab-Klick auf einen Wegpunkt fährt.

### Task 7: GUI — Wegpunkt-Klick und Merkorte (`gui/lagebild.py`, `gui/views/fahren.py`)
- `Lagebild.wegpunkt_bei(x, y, umkreis_m) -> dict | None` (aus `daten["karte"]["wegpunkte"]`,
  nur wenn die Karte `verortet` ist). `FahrenView._klick`: Mensch vor Wegpunkt vor Ort; ein Wegpunkt
  schreibt `art="wegpunkt"`, `name` = Name (sonst Kennung), Zeile „Klick auf Wegpunkt ‹…› — Spot
  fährt mit der Karte hin …“. `_klick_text` kennt `navigiert`.
- `Lagebild` zeichnet `daten["merkorte"]` als Raute mit Namen (Farben aus der Palette).
- Tests `tests/test_gui_fahren.py`: Klick neben einen Wegpunkt schreibt das Klickziel; ohne
  Verortung bleibt es ein Ort-Klick; Merkorte kommen ins Bild (ein gezeichnetes Lagebild mit
  `merkorte` wirft nicht und ändert Pixel an der Stelle).

### Task 8: Lage, Skizze und Werkzeuge (`mcp/agentlage.py`, `mcp/karten.py`, `mcp/server.py`)
- `agentlage.lage_aus`: `karte` (`name`, `zustand`, `grund`; verortet: die nächsten
  `WEGPUNKTE_IN_LAGE` Wegpunkte mit Peilung und Abstand) und `merkorte` (mit Peilung und Abstand).
  `skizze_bild` zeichnet Merkorte (Raute + Name) und verortete Wegpunkte (kleiner Ring + Name).
- `mcp/karten.py` mit `fahren._werkzeug`, `fahren._befehl`, `fahren._zentrale`, `fahren._warum`,
  `fahren._zahl`: `karte_laden(name)`, `aufnahme_starten(name=None)`, `aufnahme_beenden()`,
  `wegpunkt_setzen(name)`, `zum_wegpunkt(name, warum)`, `merkort_setzen(name, x=None, y=None)`,
  `merkort_loeschen(name)`, `zum_merkort(name, warum)`, `raum_aus_karte(karte, name=None)`.
  Karten-Werkzeuge prüfen zuerst das Backend des Laufs (in `OHNE_ROBOTER` → Hinweis auf Merkorte).
  Wartezeiten: Laden `KARTE_WARTE_S`, Beenden `SPEICHERN_WARTE_S`, Fahrten `BEFEHL_WARTE_S`.
- `raum_aus_karte`: `rekonstruktion.rekonstruiere(store.finde(ws, karte).dir)`, freier Name unter
  `raeume/`, `raum_speichern` + `pauspapier.schreibe(…, weg=…)`; Antwort mit Name, Pfad, Zahlen aus
  `bericht`, Dauer, Hinweis.
- `zentrale_status()` nennt die geladene Karte. `server.py`: die neun Werkzeuge mit Beschreibungen.
- Tests `tests/test_mcp_karten.py` (Attrappe der Zentrale aus `test_mcp_fahren`): Hinweis im
  Übungsraum; Laden wartet aufs Ende; Merkort-Befehle; `raum_aus_karte` an der Katakomben-Karte
  (`skipif` ohne sie) und freier Name; `test_mcp_agentlage.py`: Merkorte und Wegpunkte in `lage`;
  `test_mcp_server.py`: Liste der Werkzeuge.

### Task 9: Kette und Doku
- Kette (`tests/test_mcp_karten.py`, echter Prozess, 2D, „durchgang“): `zentrale_starten` →
  `merkort_setzen("start")` → `fahre_relativ(1.0, 0, …)` → `zum_merkort("start", …)` →
  „angekommen“ → `zentrale_beenden`; die Merkort-Datei liegt unter `raeume/`; ein zweiter Start
  kennt „start“ wieder.
- Doku: `docs/AGENTEN.md` (Karten, Merkorte, Rekonstruktion), CLAUDE.md-Absatz, `docs/ABNAHME.md`
  A45. ruff; volle Suite auf aicgolling gegen `main`.
