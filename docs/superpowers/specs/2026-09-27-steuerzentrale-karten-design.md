# Steuerzentrale, Teil 3: Karten aufnehmen, einblenden, wiedererkennen

Entwurf vom 27.09.2026, im Gespräch abschnittsweise freigegeben. Baut auf Teil 1
(`2026-09-27-steuerzentrale-design.md`) und Teil 2 (`2026-09-27-steuerzentrale-menschen-design.md`)
auf und füllt den leeren Platz `karte` im Lagebild.

## Entscheidungen

- **Umfang:** Karte aufnehmen, bekannte Karte einblenden, Wiedererkennung anzeigen. Zu Wegpunkten
  fahren bleibt im Tab „Karten“ (nicht Teil 3).
- **Anzeige der Wiedererkennung:** Zahl UND gefärbte Wände (erkannt grün, neu rot, fehlt gestrichelt).
- **Aufnahme:** neu UND weiterführen; eine weitergeführte Karte wird unter einem NEUEN Namen
  gespeichert, die alte bleibt unberührt.
- **Bauweg A:** alles im Programm der Zentrale (eine Verbindung, ein Lease — das Hochladen braucht
  eines). Verworfen: Aufnahme in der GUI (zwei Verbindungen, Zustand an zwei Orten) und ein eigenes
  Kartenprogramm (zweites Lease).

## 1. Bedienung im Tab

Unter dem Regler „👥 Menschen“ eine Zeile **„🗺 Karte“**:

- **Auswahl** der gespeicherten Karten des Arbeitsordners (`maps/store.karten`), **„Laden“**:
  hochladen und am AprilTag verorten; ohne Tag im Bild alle 2 s neu, mit dem Hinweis „Stell Spot so
  hin, dass ein Tag im Bild ist“.
- **„● Aufnahme“ / „■ Aufnahme beenden“** mit Namensfeld. Geladen und verortet → WEITERFÜHREN,
  Vorschlag „‹alter Name›-2“; sonst NEU, Vorschlag „karte-‹JJJJ-MM-TT›-‹HHMM›“.
- **„📍 Wegpunkt“** (nur während der Aufnahme): benannte Marke an Spots Ort, Name aus einem Dialog
  (Vorschlag „Punkt 1“, „Punkt 2“ …); grau, bis der vorige bestätigt ist.
- Gefahren wird während der Aufnahme wie immer (Tasten, Klick, Folgen) — die Aufnahme läuft mit.
- Nach „beenden“: Schleifen schliessen, Anker optimieren, speichern; die Zeile zeigt den Schritt.
  Danach ist die neue Karte die geladene, mit Wiedererkennung.
- **Statuszeile**, z. B. „Karte ‹flur2›: verortet · Roboter: 18 von 20 Abgleichen angenommen ·
  82 % der gesehenen Wände stehen in der Karte“ / „Aufnahme läuft: 14 Wegpunkte, 13 Kanten“ /
  „Speichern: Schleifen schliessen …“.
- **Ohne GraphNav** (Übungsraum) ist die Zeile grau: „Karten gibt es nur am echten Spot (GraphNav)“.
  Während der Aufnahme ist „Laden“ grau (es ersetzte die Karte auf dem Roboter).

## 2. Aufbau im Programm

- **`workshop/kartenarbeit.py`, Klasse `Kartenarbeit`** — Zustand `keine | laedt | sucht_tag |
  verortet | verloren | nimmt_auf | speichert`, dazu Name und Grund. Langsames (hochladen,
  verorten, beenden + nachbearbeiten + herunterladen) läuft in EINEM eigenen Faden, eine Arbeit
  zugleich; ein Auftrag währenddessen wird mit Grund abgelehnt. Der Fahrtakt wartet nie darauf.
- **`kartenauftrag.json`** (Tab → Programm, `record/zentrale.py`): `{nummer, was, name}` mit
  `was ∈ laden | aufnahme_start | aufnahme_stopp | wegpunkt`. Eine eigene Datei, damit ein
  Licht-Klick in `aktion.json` nie ein „beenden“ überschreibt. Das Lagebild meldet die zuletzt
  erledigte Nummer (`karte.auftrag`); fehlt sie nach 1.5 s, schreibt der Tab den Auftrag erneut.
- **Wiederverwendet:** die Aufnahme über `maps/session.RecordingSession` mit den Clients DIESER
  Verbindung (`start(graph_leeren=…)`, `waypoint`, `stop`, `nachbearbeiten`, `download`); Laden
  über `backend.upload_map(ordner)` und `backend.localize()` mit dem Ordner aus
  `maps/store.finde(arbeitsordner, name)`.
- **Arbeitsordner:** die App gibt ihn mit (`--arbeitsordner`); gespeichert wird unter
  `maps/store.karten_wurzel(arbeitsordner)`. Ein vorhandener Name wird nie überschrieben — dann
  „-2“, „-3“ …
- **Neue Abfrage am Roboter** `graphnav.verortung(robot)` → Datenklasse `Verortung`: Wegpunkt,
  Lage des Körpers im Seed-Rahmen der Karte und im Rahmen „vision“ (aus `robot_kinematics` DERSELBEN
  `GetLocalizationStateResponse`), `verloren`, Zähler angenommen/abgelehnt. `None`, solange nicht
  verortet (leere `waypoint_id`). Protobufs bleiben unter `backends/`.
- **Programmende während der Aufnahme:** erst beenden, nachbearbeiten, unter dem eingegebenen Namen
  speichern, dann setzt sich Spot. Der NOT-AUS tötet hart — dann bleibt die Aufnahme nur auf dem
  Roboter, bis dort etwas anderes geladen wird (so steht es im Hinweistext).

## 3. Einblenden und Wiedererkennung

- **Deckungsgleich:** aus einer `Verortung` `vision_T_seed = vision_T_körper · (seed_T_körper)⁻¹`
  (eben: x, y, Gier). Alle 0.5 s im Wahrnehmungsfaden neu; korrigiert der Roboter seine
  Verortung, rutscht die Karte mit.
- **Kartenwände** (`workshop/kartenabgleich.py`): beim Laden EINMAL die Punktwolken aller Wegpunkte
  in den Seed-Rahmen (`maps/rekonstruktion.lade_karte`, `posen`, `wolke_im_seed`), davon das Band
  0.3–1.6 m über dem Boden je Schnappschuss (dieselben Zahlen wie `rekonstruktion.Einstellungen`),
  als 5-cm-Zellen mit mindestens 3 Punkten. Dazu Wegpunkte mit Namen und Kanten.
- **Raster wie die Skizze:** Ursprung auf Vielfache von 0.05 m, damit Karten- und Skizzenzellen
  deckungsgleich sind; ein eigenes Bild `lagebild_karte.png` (Farbnummern, die Farben legt die GUI
  aus dem Thema darüber) mit eigener Ausdehnung — die Karte darf über die Skizze hinausreichen.
- **Vergleich im Blickfeld** (Skizzenzellen, die ≤ 5 s alt und ≤ 4 m von Spot sind):

  | Nummer | Farbe | Bedeutung |
  |---|---|---|
  | 1 | blass | Kartenwand ausserhalb des Blickfelds — nicht geprüft |
  | 2 | grün | Kartenwand, an der Spot jetzt eine Wand sieht (≤ 0.15 m daneben) — erkannt |
  | 3 | gestrichelt | Kartenwand, wo Spot jetzt freien Boden sieht — fehlt |
  | 4 | rot | Wand, die Spot sieht, ohne Kartenwand in 0.15 m — neu (Kiste, Tür zu, auch ein Mensch) |

- **Zahl:** erkannt ÷ (erkannt + neu), erst ab 20 gesehenen Wandzellen, sonst „zu wenig Wand im
  Blick“. **Urteil des Roboters:** angenommene und abgelehnte Abgleiche der letzten 30 s (Differenz
  der Zähler) oder „verloren — Spot findet sich in der Karte nicht mehr“. Verloren: die Karte bleibt
  an der letzten Stelle, alles blass, keine Zahl.
- **Lagebild** `karte`: `{name, zustand, grund, auftrag, aufnahme: {wegpunkte, kanten} | null,
  wegpunkte: [{x, y, name}], kanten: [[i, j]], raster: {ursprung, breite, hoehe} | null,
  wiedererkennung: {anteil, wandzellen, angenommen, abgelehnt, verloren} | null, kann}`, Koordinaten
  im Rahmen „vision“.
- **Grenzen im Text:** Glas sieht Spot nicht; die Karte kennt nur, was bei der Aufnahme im Blick war.

## 4. Fehler und Prüfung

- **Ein Fehler setzt den Zustand zurück:** gescheitertes Laden → Zeile wieder frei; gescheiterter
  Aufnahmestart (z. B. nicht in der alten Karte verortet) → „● Aufnahme“ bleibt bedienbar; der Grund
  steht in der Zeile.
- **Speichern wirft nie** (`nachbearbeiten` tut es schon nicht); scheitert das Herunterladen:
  „nicht gespeichert — nochmal versuchen“, „■ Aufnahme beenden“ bleibt aktiv, die Aufnahme liegt
  noch auf dem Roboter.
- **Fahren bleibt unberührt:** keine Kartenarbeit hält den Fahrtakt an, die Karte gibt keine Fahrt
  frei, die Schranken bleiben dieselben.
- **Prüfung ohne Roboter:** `Kartenarbeit` mit Attrappen (Aufnahme, Laden, Verorten, Abfrage):
  Zustände, Weiterführen, abgelehnter zweiter Auftrag, Speichern am Programmende; das Kartenraster
  an der echten Katakomben-Karte (Wände wie in der Rekonstruktion); der Vergleich an gebauten
  Gittern; der Tab (Knöpfe, Nachschicken, grau im Übungsraum).
- **Am Gerät: A40** — neue Karte aufnehmen und speichern; laden und verorten; Kiste hinstellen →
  rot, Tür öffnen → gestrichelt; weiterführen; Stopp mitten in der Aufnahme.
