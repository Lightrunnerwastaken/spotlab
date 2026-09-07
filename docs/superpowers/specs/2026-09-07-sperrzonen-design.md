# Sperrzonen — Gefahr, die kein Sensor sieht

**Stand 07.09.2026.** Anlass: zwei Not-Aus-Eingriffe im ersten kommandierten Explorationslauf
am Schul-Spot. Einmal fuhr der Roboter unter eine Tischreihe (behoben: Kopfraum-Tor aus den
Tiefenkameras, `backends/real/tiefe.py`), einmal sehr nah an eine **Glasfront**.

Glas ist der Fall, den kein Sensor des Spot löst. Die Stereokameras schauen hindurch, das
Hindernisgitter meldet dort freie Fläche, und die Firmware weicht nicht aus. Dasselbe gilt
für andere Gefahren, die der Roboter nicht kennen kann: eine Treppe hinter einer Ecke, ein
Bereich mit teurem Gerät, ein Kabelkanal, ein frisch gewischter Boden.

**Wer es weiss, ist der Mensch.** Also trägt der Mensch es ein — im Raumeditor, in dem der
Raum ohnehin schon steht.

---

## Was eine Sperrzone ist

Ein **Rechteck auf dem Boden**, gedreht wie ein Block, mit Namen und **Grund** („Glasfront",
„Treppenabgang"). Der Roboter darf nicht hinein.

Bewusst KEINE Höhe: die Gefahren, um die es geht, sind Flächen. Ein Volumen wäre eine
Scheingenauigkeit — hinter einer Glasfront ist der Boden auf jeder Höhe verboten.

**Eine Zone ist eine Regel, keine Geometrie.** Sie ist kein Hindernis: sie steht in keinem
Hindernisgitter, wirft keinen Schatten, verändert das Gelände nicht und taucht in keiner
Rekonstruktion auf. Wer eine Wand meint, zieht eine Wand. Der Unterschied zählt, denn eine
Zone soll auch dort halten, wo der Sensor „frei" sagt — das ist ihr ganzer Zweck.

## Wo sie wirkt

| Ort | Verhalten |
|---|---|
| 2D-Sim und MuJoCo | Der Roboter bleibt an der Zonengrenze stehen wie an einer Wand; Ereignis `angestossen` mit `hindernis = "Sperrzone <name>"` |
| Echter Roboter (Explorer) | Vorwärtsfahrt, die in eine Zone führte, wird aus dem Kommando genommen — wie beim Kopfraum-Tor; Drehen und Rückwärts bleiben frei |
| Rekonstruktion, Gelände, Gitter | gar nicht |

Im Sim wirkt sie, damit sie **prüfbar** ist: derselbe Raum, dieselbe Zone, ein Test ohne
Roboter. Ein Sicherheitsmerkmal, das nur am Gerät sichtbar wird, ist keines.

## Die Brücke zur Karte — sonst nützt es am Roboter nichts

Der Raum aus der Rekonstruktion ist gegen die GraphNav-Karte **gedreht und verschoben**:
`ausrichten()` legt die häufigste Wandrichtung auf die x-Achse und schiebt die Hülle nach
(0, 0); zusätzlich zieht `rekonstruiere` den tiefsten Boden auf z = 0. Bis heute wurde diese
Beziehung weggeworfen — der Raum wusste nicht mehr, aus welcher Karte er stammt.

Damit konnte ein Lauf am echten Roboter nicht sagen, **wo im Raum** er steht. Deshalb trägt
die Raumdatei jetzt:

```toml
[karte]
name    = "map_catacombs_01"
dreh    = -3.0        # Grad: Seed-Rahmen -> Raum
versatz = [16.4, 27.6]
z_min   = 1.83        # so viel wurde von z abgezogen
```

Und `welt/raum.py` bekommt die beiden Umrechnungen `aus_karte(raum, x, y, grad=None)` und
`nach_karte(...)`. Am Roboter liefert GraphNav nach dem Verorten `seed_tform_body`; das ist
derselbe Seed-Rahmen. `spot.map_pose()` gibt ihn als (x, y, grad) heraus — leaselos, ein
reiner Lesedienst wie die Sonde.

**Ohne Verortung keine Zone.** Wer den Zonenschutz will, muss die Karte laden und sich
verorten. Das ist keine Bequemlichkeitshürde: eine Zone an der falschen Stelle ist
gefährlicher als keine.

## Was das Format ändert

Fassung 5. `[[sperrzone]]` wie `[[block]]`, dazu `grund`; `[karte]` wie oben. Beides
optional — ein Raum ohne Zonen und ohne Kartenbezug bleibt Zeile für Zeile die alte Datei.
Ältere Fassungen werden weiter gelesen.

## Grenzen, ausdrücklich

- **Eine Zone schützt nur, wo die Verortung stimmt.** Driftet GraphNav, driftet die Zone.
  Deshalb ein Sicherheitsabstand (`RAND_M`) um jede Zone und die Abnahme am Gerät (A31).
- **Sie ersetzt die Aufsicht nicht.** Der Not-Aus am Tablet bleibt das Netz darunter.
- **Sie kennt nur, was jemand eingetragen hat.** Eine Glasfront, die niemand einzeichnet,
  ist weiter unsichtbar. Das ist der Preis dafür, dass die Regel vom Menschen kommt — und
  der Grund, warum darüber später ein Modell stehen soll, das den Raum selbst beurteilt.

## Etappen

1. **Zonen im Raum und im Sim.** Format v5, `welt/kollision.py`, Editor (Werkzeug, Liste,
   Felder, 2D), Tests.
2. **Die Brücke zur Karte.** `[karte]` aus der Rekonstruktion, `aus_karte`/`nach_karte`,
   `spot.map_pose()` aus GraphNav.
3. **Das Tor am echten Roboter.** `exploration_real.py --raum`, Zonen-Tor in `SpotSdkReal`
   neben dem Kopfraum-Tor, Abnahme A31.
