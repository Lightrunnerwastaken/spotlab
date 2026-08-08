# Ein fremdes Projekt an spotlab anbinden

Für Projekte mit eigenem Repo und eigenem Zweck — Forschungscode, Simulationen,
Auswertungen —, die in spotlab etwas zeigen, dort startbar sein oder echte Lauf-Daten
auslesen wollen.

Entwurf und Begründungen: `docs/superpowers/specs/2026-08-07-spotlab-anbindung-design.md`.

---

## 1 · `spotlab.toml` anlegen

Die Datei liegt **in deinem Repo**, neben `pyproject.toml`. Dort gehört sie hin: sie liegt in
deinem git, reist mit, und wer dein Repo klont, bekommt die Anbindung mit.

```toml
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation des Spot für die Maturaarbeit"

[[skript]]
name = "Baseline, 20 Episoden"
datei = "scripts/experiment_baseline.py"
argumente = ["--episoden", "20", "--archiv"]
roboter = false
beschreibung = "Frontier-Exploration, schreibt ergebnisse.json"

[[skript]]
name = "Fahrt auf dem echten Spot"
datei = "scripts/sdk_drive.py"
roboter = true
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `projekt.name` | ja | Name in der Seitenleiste und in allen Werkzeugen |
| `projekt.beschreibung` | nein | ein Satz |
| `skript.name` | ja | Beschriftung des Knopfes |
| `skript.datei` | ja | relativ zum Projektordner |
| `skript.argumente` | nein | Liste aus **Texten**, auch für Zahlen: `["--episoden", "20"]` |
| `skript.roboter` | nein, Vorgabe `false` | `true`, wenn das Skript den echten Spot fährt |
| `skript.beschreibung` | nein | erscheint als Kurzhinweis am Knopf |

**`roboter = true` setzen, wenn das Skript den Spot bewegt.** Ein Agent darf solche Skripte
dann gar nicht erst starten. Die Sicherheit hängt aber nicht daran — siehe Abschnitt 5.

## 2 · Anbinden

Im Fenster: `spotlab gui` → **Anbindungen** → *Projekt anbinden…* → den Ordner mit der
`spotlab.toml` wählen.

Über einen Agenten: `projekt_anbinden("D:/…/matura-spot")`.

Beides legt `<arbeitsordner>/anbindungen/<name>/` an. Erneutes Anbinden erneuert nur die
Kopie des Manifests und lässt die Panels stehen — nach jeder Manifeständerung neu anzubinden
kostet also nichts.

Verschwindet dein Projektordner später, bleiben die Panels sichtbar; nur die Skript-Knöpfe
gehen aus, mit einem Hinweis auf den alten Pfad.

## 3 · Panels schreiben

Ein Panel ist eine JSON-Datei unter `anbindungen/<name>/panels/`. Aus deinem eigenen Code:

```python
from spotlab.anbindung import panel, speicher

anbindung = speicher.finde(r"D:\Pfad\zur\werkstatt", "matura-spot")
panel.schreibe(
    anbindung, "baseline", "kennzahlen", "Baseline, 20 Episoden",
    [
        {"name": "success", "wert": "95 %", "hinweis": "19 von 20"},
        {"name": "SPL", "wert": "0.71"},
    ],
)
```

**Überschreiben ist der Weg, ein Panel zu aktualisieren.** Ein Experimentlauf über zwanzig
Episoden schreibt dieselbe Datei nach jeder Episode neu; die Ansicht zieht nach. Geschrieben
wird atomar, ein Leser sieht nie eine halbe Datei.

**Die Reihenfolge im Fenster ist die des Dateinamens.** Wer sie steuern will, benennt die
Panels `01_baseline`, `02_strata` und so weiter.

### Die fünf Arten

```python
# kennzahlen — Kacheln
[{"name": "success", "wert": "95 %", "hinweis": "19 von 20"}]

# tabelle
{"spalten": ["Stratum", "n", "success"],
 "zeilen": [["sichtbar", "5", "100 %"], ["verdeckt", "15", "93 %"]]}

# reihe — Linie
{"x": [0, 1, 2], "y": [0.30, 0.34, 0.41], "x_name": "Episode", "y_name": "Coverage"}

# bild
{"pfad": "D:/…/matura-spot/out/vergleich.png"}

# text
{"absaetze": ["Erster Absatz.", "Zweiter Absatz."]}
```

**Ein Panel bestimmt keine Farben.** spotlab zeichnet mit den eigenen; sonst gäbe es einen
Hell/Dunkel-Modus, in dem deine Daten unlesbar sind.

**Bildpfade dürfen nur ins Projekt oder in den Anbindungsordner zeigen.** Alles andere wird
nicht geladen, mit einem Hinweis statt einem leeren Rahmen.

Ein kaputtes oder halb geschriebenes Panel zeigt eine Fehlerkarte — die anderen bleiben
stehen.

## 4 · Der MCP-Server

```bash
pip install "spotlab[mcp]"
```

Gestartet wird er über stdin/stdout:

```bash
spotlab mcp
```

Er braucht **weder GUI noch Roboter**, nur einen eingerichteten Arbeitsordner.

| Werkzeug | Was es tut |
|---|---|
| `projekt_anbinden(pfad)` | liest die `spotlab.toml` und bindet an |
| `anbindungen_auflisten()` | alle Projekte mit Skripten und Panelnamen |
| `panel_setzen(projekt, name, art, titel, inhalt)` | Panel schreiben oder ersetzen |
| `panel_entfernen(projekt, name)` | Panel löschen |
| `skript_starten(projekt, name)` | startet — **immer im Trockenlauf** |
| `lauf_stoppen(lauf_id)` | freundlicher Stopp, der Spot setzt sich hin |
| `laeufe_auflisten(projekt, anzahl)` | die neuesten Läufe |
| `lauf_lesen(lauf_id)` | Metadaten, Ergebnis und **Dateipfade** |
| `zustand_zusammenfassen(lauf_id)` | Dauer, Strecke, Tempo, Akku, **Abtastlücken** |
| `karten_auflisten()` · `karte_lesen(name)` | GraphNav-Karten und ihr Grundriss |
| `spot_pruefen()` | wie `spotlab doctor` |

**Die Lese-Werkzeuge geben keine Massendaten heraus.** `zustand.jsonl` läuft mit 10 Hz —
fünf Minuten sind 3000 Zeilen, und ein Werkzeug, das die zurückgibt, füllt den Kontext des
Agenten mit einem Aufruf. `lauf_lesen` nennt stattdessen die Pfade; die Reihen liest der
Agent mit seinen eigenen Dateiwerkzeugen und kann dabei filtern.

`zustand_zusammenfassen` ist die Ausnahme, und die Abtastlücken sind ihr eigentlicher Zweck:
für den Vergleich eines echten Laufs mit einer Simulation macht eine unbemerkte Lücke in der
Messreihe den Vergleich still ungültig. Sie muss vor der ersten Zahl sichtbar sein, nicht
nach der letzten.

**Der Server schreibt nie in dein Projekt.** Er liest dein Manifest und schreibt
ausschliesslich unter `anbindungen/`.

## 5 · Was ein Agent nicht darf

**Ein über MCP gestarteter Lauf kommt nie an den Roboter.** Zwei Lagen sorgen dafür:

1. `skript_starten` weigert sich bei `roboter = true`, bevor etwas läuft.
2. Der Start setzt `SPOTLAB_NUR_TROCKEN=1`, und `spotlab.connect()` liest das als **Verbot**.
   Auch ein `spotlab.connect(backend="real")` mitten im Skript wird abgewiesen.

Die zweite Lage ist die eigentliche Sicherung: sie hängt an nichts, was jemand falsch
aufgeschrieben haben könnte. **Ein veraltetes Manifest kann den Roboter nicht bewegen.**

Abgewiesen, nicht stillschweigend heruntergestuft — ein Skript, das glaubt, es fahre den
echten Spot, während es im Trockenlauf steckt, meldet Unsinn, und niemand merkt es.

**Im Fenster gilt das nicht.** Wer dort auf einen Skript-Knopf drückt, sitzt vor dem NOT-AUS.

## 6 · Wo die Läufe landen

Ein Skript deines Projekts wird mit `cwd=<skriptordner>` gestartet, und `spotlab.connect()`
legt seine Aufzeichnung unter `<skriptordner>/runs/<lauf-id>/` an — also **in deinem Repo**,
nicht im Arbeitsordner. Das gehört in dein `.gitignore`.

spotlab findet diese Läufe trotzdem: die Verzeichnisse werden aus den Skriptpfaden im
Manifest abgeleitet. Sie erscheinen in „Live-Lauf", in „Läufe" und in `laeufe_auflisten`.

## 7 · Messfahrt für die Sim-Kalibrierung

```python
import spotlab

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
        spot.walk(vx=0.30, duration=8.0)
```

Innerhalb des Blocks tastet spotlab mit 50 Hz und vollem Umfang ab — Gelenke mit
Drehmoment, Fusskontakte mit Reibwert und Schlupf, Körperhöhe, Neigung, Roboterzeit.
Ausserhalb bleibt es bei 10 Hz und schlank; der Sampler pollt über WLAN, und 50 RPCs je
Sekunde in jedem Lauf wären Funklast für Daten, die niemand ansieht.

Verschachtelte Fenster sind verboten — sie wären in der Auswertung nicht
auseinanderzuhalten. Wirft der Block eine Ausnahme, wird das Fenster trotzdem geschlossen
und die Rate zurückgestellt.

Danach:

```python
from spotlab.messung.fenster import schreibe

schreibe(r"D:\…\demo\runs\20260808T120000Z")     # legt messfenster.json an
```

`messfenster.json` enthält je Fenster die **Messwerte, nicht das Urteil**: Dauer, Ist-Rate
und Lücken zuerst, dann Körperhöhe (Mittel/Min/Max/Drift), Roll- und Pitch-Spitze,
Geschwindigkeiten, Strecke, fortlaufend aufsummierter Gierwinkel, kommandiert gegen
erreicht als `tracking_prozent`, je Gelenk Spitzenrate und Spitzenlast, je Fuss
Duty-Cycle und Schrittfrequenz, mittlerer Reibwert und Schlupf.

Die Gate-Kriterien liegen in deinem Repo. spotlab misst, du bewertest.

**Was nicht ableitbar ist, ist `None` — nie 0.** Ein schlank aufgezeichnetes Fenster hat
keinen Reibwert, und ein erfundener 0.0 würde sich durch jede Auswertung mitteln.

**Was ein Agent nicht darf, gilt auch hier:** ein über MCP gestarteter Lauf läuft im
Trockenlauf. Eine Messfahrt am echten Spot startet ein Mensch.
