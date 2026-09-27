# Steuerzentrale, Teil 1: Lagebild und Fahren

Entwurf vom 27.09.2026, abschnittsweise freigegeben vom Menschen. Ziel ist EINE Ansicht, in der
man sieht, wo Spot ist und was um ihn herum ist (Boden, Wände, AprilTags, später Menschen), und
von der aus man ihn fährt: mit W A S D Q E oder mit einem Klick auf den Boden, dazu Licht und
Ton. Später docken Folgen, Karten und Wiedererkennung an dieselbe Ansicht an.

## 1. Aufteilung

| Teil | Inhalt | Ohne Roboter prüfbar |
|---|---|---|
| **1 Lagebild und Fahren** (dieses Dokument) | Draufsicht mit wachsender Skizze, Tags, Spot; Tasten; Klickfahrt mit Umweg; Licht, Ton | ja, im Übungsraum 2D und 3D |
| 2 Menschen | Personen im Lagebild, Regler für Rechenleistung, Mensch anklicken → folgen | nur am Gerät |
| 3 Karten | aufnehmen aus der Zentrale, bekannte Karte einblenden, Wiedererkennung | teils |

Teil 1 legt die Plätze für Teil 2 und 3 im Lagebild an (`menschen`, `karte`), füllt sie aber nicht.

## 2. Entscheidungen

- **Ort:** Der Tab „Fahren“ WIRD die Steuerzentrale. Kamerabild, Akku wechseln, Aufrichten und die
  Schalter Gesicht/Hand bleiben; keine neue Zeile in der vollen Seitenleiste.
- **Ansicht:** 2D-Draufsicht. Klicks auf den Boden sind eindeutig, es braucht kaum Rechenleistung.
- **Gedächtnis:** wachsende Skizze. Was Spot gesehen hat, bleibt; länger nicht Gesehenes wird
  blasser. Sie gilt für eine Fahrt und darf über lange Wege verziehen (Odometrie, Rahmen „vision“).
- **Bauweg A:** EIN Programm `workshop/zentrale.py` hält die Verbindung zum Roboter, liest Tasten,
  Klickziel und Knöpfe aus dem Lauf-Verzeichnis und schreibt das Lagebild zurück. Der Tab zeichnet
  nur. Verworfen: die Skizze in der GUI bauen (Rechnen im Fensterfaden) und zwei Programme
  (zwei Verbindungen, kein Nutzen).
- **Vorgabe Übungsraum:** Oben wählt man „Übungsraum“ (Vorgabe) oder „Echter Spot“. Wer nichts
  einstellt, fährt nicht den Roboter. Der Übungsraum nimmt den Raum aus dem Raumeditor, mit
  denselben Regeln wie jeder virtuelle Start (`RaumeditorView.bereit_fuer_lauf`).
- **Paketcode:** Der Tab startet `workshop/zentrale.py` aus dem Paket mit `--runs
  <Arbeitsordner>/Beispiele/runs`, wie der Akku-Knopf (`workshop/lage.py`) — nicht die Kopie im
  Arbeitsordner, die veraltet sein kann. `fahren.py` bleibt für den Raumeditor unverändert.

## 3. Ablauf und Dateien

```
Tab (GUI)                         Lauf-Verzeichnis                 zentrale.py (Lease)
 Tasten       ── schreibt ──▶     fahrt.json          ── liest 20 Hz ──▶ fahren
 Klick        ── schreibt ──▶     klickziel.json      ── liest 20 Hz ──▶ Klickfahrt
 Licht / Ton  ── schreibt ──▶     aktion.json         ── liest 20 Hz ──▶ Statuslicht / beep
 Draufsicht   ◀── liest ────      lagebild.png/.json  ◀── schreibt 2 Hz ── Skizze, Tags, Weg
 Kamerabild   ◀── liest ────      ansicht.jpg         ◀── wie heute (blick.py / MuJoCo)
```

Alle Dateien atomar (`record/atomar.py`), das Protokoll in `record/zentrale.py` (nur
Standardbibliothek — die GUI darf es importieren). `fahrt.json` bleibt, wie es ist.

**`klickziel.json`** — `{"nummer": int, "ziel": [x, y] | null, "stufe": "langsam"|"normal"|"schnell",
"lebt": float}`. Ziel in Metern im Rahmen der Skizze („vision“). `lebt` ist die Wanduhr des Tabs,
alle 200 ms aufgefrischt, solange die Klickfahrt läuft und der Tab sichtbar ist. `ziel: null`
bricht ab. Eine neue `nummer` ersetzt das alte Ziel.

**`aktion.json`** — `{"nummer": int, "art": "licht"|"ton", "farbe": "aus"|"blau"|"gruen"|"gelb"|"rot"}`.
Jede neue Nummer wird genau einmal ausgeführt.

**`lagebild.json`** — geschrieben mit dem Bild:
`{"t", "rahmen": "vision", "zelle_m", "ursprung": [x, y], "breite", "hoehe",
"spot": {"x", "y", "gier_grad"}, "tags": [{"id", "x", "y"}],
"klickfahrt": {"nummer", "zustand", "grund", "ziel": [x, y], "weg": [[x, y], ...]},
"faehigkeiten": {"licht": bool, "ton": bool, "kamera": bool}, "menschen": [], "karte": null}`.
`zustand` ist eines von `keine`, `unterwegs`, `angekommen`, `abgelehnt`, `versperrt`,
`abgebrochen`; `grund` in Worten.

**`lagebild.png`** — ein Pixel je Zelle. Pixel (Spalte s, Zeile z) liegt bei
`x = ursprung_x + s·zelle`, `y = ursprung_y + (hoehe − 1 − z)·zelle` (oben ist +y). Boden hell,
Wand dunkel, Unbekanntes durchsichtig (der Tab zeigt dort Grau); das Alter macht die Farbe blasser. Die GUI liest es über
`read_bytes` + `loadFromData`, nie `QPixmap(pfad)` (Qts Dateicache).

## 4. Die Skizze (`workshop/skizze.py`)

- Zellen zu 0.05 m, je Zelle Zustand (unbekannt / frei / Wand) und Zeit der letzten Beobachtung.
- Jedes Hindernisgitter (`spot.obstacles()`, Rahmen „vision“, 3-cm-Zellen mit `known`-Maske) wird
  auf 5-cm-Zellen gebracht: der kleinste Abstand in der Zelle zählt; ≤ halbe Zelle heisst Wand,
  darüber frei, unbeobachtet ändert nichts. **Die neueste Beobachtung gewinnt** — ein Mensch, der
  weggeht, hinterlässt keine Wand.
- Die Skizze wächst mit der Fahrt (Ränder werden erweitert), höchstens 60 × 60 m.
- Die Lage von Spot kommt aus demselben Rahmen wie das Gitter (`folgen._lage_im_gitter`), nie
  aus `state.pose` (odom) — die Regel aus p16.
- Ohne Hindernisgitter (Trockenlauf, Übungsraum ohne Raum) bleibt die Skizze leer; Tasten gehen,
  die Klickfahrt lehnt mit „unbekannt“ ab.

## 5. Klickfahrt (`workshop/wegsuche.py`, `workshop/klickfahrt.py`)

- **Prüfen:** höchstens 5 m Luftlinie, Ziel auf bekanntem freiem Boden mit 0.3 m Abstand zur
  Wand. Sonst `abgelehnt` mit Grund („in der Wand“, „unbekannt“, „zu weit“).
- **Weg:** A* auf der Skizze, 8 Nachbarn, Wände um 0.3 m aufgedickt, Unbekanntes gesperrt; der Weg
  wird auf Wegpunkte mit freier Sicht vereinfacht und steht im Lagebild.
- **Fahren:** Zum nächsten Wegpunkt; über 30° Abweichung dreht Spot auf der Stelle, sonst geht er
  und lenkt. Tempo `fahrt.TEMPO_M_S × Stufenfaktor`, Drehen `fahrt.DREH_RAD_S × Stufenfaktor`, nah
  am Ziel langsamer, auf 0.25 m angekommen.
- **Neu planen:** Sperrt die Skizze den Weg neu oder hält eine Schranke, plant er neu (höchstens
  alle 2 s). Kein Weg mehr → `versperrt`, Spot steht.
- **Vorrang:** Jede Taste (`fahrt.json` nicht still) bricht die Klickfahrt ab (`abgebrochen`).

## 6. Sicherheit

- **Totmann:** Ist `lebt` älter als 0.5 s, steht Spot; die Klickfahrt ist dann `abgebrochen`.
  Jedes Kommando verfällt ohnehin nach rund 1 s (`walk(stop=False)`).
- **Schranken** wie beim Folgen, fail-closed: Hindernisgitter voraus (`frei_voraus`), Kopfraum
  (`kopfraum_frei`, wo Tiefenkameras sind). Unlesbar heisst stehen. **Zu prüfen im Plan:** ob
  die Tiefenbilder der 3D-Puppe von `tiefe.ueberhang_aus_bildern` gelesen werden — sonst stünde
  Spot im 3D-Übungsraum immer; dann gilt dort die Schranke wie im 2D-Sim (keine Tiefe, kein
  Kopfraum), und das steht im Lagebild.
- **Tempo:** die Stufe gilt, am echten Spot ist „langsam“ vorgewählt; `config.toml` deckelt immer.
- **Stopp und NOT-AUS** wie bisher über die Live-Ansicht und den Kopf. Am Ende hält Spot immer,
  ERST anhalten, DANN Licht aus.

## 7. Licht und Ton

Licht über `api/signals.Statuslicht` (blockiert nie). Ton über `spot.beep()` in einem eigenen Faden.
Das Programm fragt `spot.supports()` und meldet es in `faehigkeiten`; im Übungsraum sind die
Knöpfe grau mit „nur am echten Spot“. Ein Fehler daran wird einmal gesagt und hält nichts an.

## 8. Der Tab (`gui/views/fahren.py`, `gui/lagebild.py`)

- Links gross die Draufsicht (`gui/lagebild.py`): Bild plus Spot-Pfeil, Tags, Weg, Ziel;
  Mausrad zoomt, Ziehen verschiebt, „Mitte“ holt Spot ins Bild. Klick → Weltkoordinate →
  `klickziel.json`. Keine Rechnung ausser Umrechnen und Zeichnen.
- Rechts: Kamerabild, Tempo 1/2/3, Licht (Farbwahl), „Piep“, Akku, Aufrichten, Gesicht/Hand.
- Oben: Übungsraum / Echter Spot, Start, Stopp, Kontrolle übernehmen (nur echt).
- Die Tastaturregeln bleiben: Tastatur nur, solange Tab sichtbar und Lauf lebt; Reiterwechsel und
  Fokusverlust lassen alles los — auch das Lebenszeichen der Klickfahrt hört dann auf.
- Keine Farbliterale im Widget-Code (`gui/theme.py`), kein `bosdyn`, kein `spotlab.backends`.

## 9. Prüfung

- **Rechnung:** Skizze aus künstlichen Gittern (wächst, neueste gewinnt, Alter); Wegsuche um eine
  Wand, kein Weg, Randabstand; Klickfahrt: abgelehnte Ziele, Ankunft, Neuplanung, Totmann,
  Tastenvorrang.
- **Dateien:** gegen echte Dateien, halb geschrieben, veraltet.
- **Widget:** offscreen; ein Klick an bekannter Stelle ergibt die richtige Weltkoordinate.
- **Kette:** Tab → `zentrale.py` im 2D-Übungsraum mit einer Wand → Klick hinter die Wand → Spot
  geht drumherum und kommt an, ohne Anstoss (wie die Kettenprobe des Fahrmodus).
- **Am Gerät:** neuer Abnahmepunkt A38 (Skizze im echten Gang, Klickfahrt, Licht, Ton).

## 10. Bewusst nicht in Teil 1

Die Skizze wird nicht gespeichert (Karte ist Teil 3). Treppen und Rampen plant die Wegsuche
nicht (dort „unbekannt“). Keine Zielrichtung beim Klicken (nur Ort). Menschen erst in Teil 2.
