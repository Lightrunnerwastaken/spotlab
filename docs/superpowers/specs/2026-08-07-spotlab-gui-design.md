# spotlab GUI — Beobachter und Starter

**Datum:** 2026-08-07
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 3 des Gesamtsystems. Setzt das freigegebene Fundament
(`2026-08-06-spotlab-fundament-design.md`) voraus.

---

## 1 Zweck

Eine Desktop-Oberfläche, mit der Schülerinnen und Schüler ihre Spot-Projekte anlegen,
starten, beim Laufen zusehen und im Notfall anhalten können — ohne Kommandozeile.

Die GUI erfindet **keine** Roboterfähigkeit. Sie ist eine Oberfläche über die in Stufe 1+2
gebauten und geprüften Operationen. Alles, was sie tut, kann man auch mit `spotlab …` im
Terminal tun; sie macht es sichtbar und zugänglich.

---

## 2 Entschiedene Grundsatzfragen

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| H1 | Was ist die GUI zur Laufzeit | **Beobachter und Starter.** Sie hält **nie** ein Lease. Live-Daten liest sie aus dem Lauf-Verzeichnis. | Das Lease ist exklusiv; eine dauerverbundene GUI würde entweder das Schülerskript aussperren oder in einem Klassenraum mit zwanzig offenen Fenstern um das Lease streiten. Zudem ist der stärkste verfügbare Stopp das Beenden des Skriptprozesses — er hängt an keiner gRPC-Verbindung, die im Störfall selbst das Problem sein könnte. Ein **Direktmodus** (GUI hält Lease und Not-Aus, Live-Kamera ohne Skript, Fahrtasten) bekommt später eine **eigene Spec mit eigener Abnahme** — er verdoppelt die Bedienzustände und ist der Modus, in dem jemand den Roboter versehentlich bewegt. |
| H2 | Womit gebaut | **PySide6/Qt**, als optionales Extra `spotlab[gui]`. | Das Aussehen zählt, weil die Arbeit vorgeführt wird. Der Kern bleibt schlank: ohne das Extra funktioniert alles Übrige unverändert. |
| H3 | Welche Läufe die GUI sieht | **Alle Läufe im `runs/`-Ordner des Projekts**, nicht nur selbst gestartete. | Dieselbe Begründung, aus der die Aufzeichnung schon an `connect()` hängt und nicht am CLI: die Läufe, die Schüler wirklich machen, starten mit F5 in VS Code. Eine Anzeige, die genau die verpasst, ist wertlos. |
| H4 | Was „Stopp" bedeutet | **Zwei getrennte Knöpfe.** Unauffälliger **Stopp** = freundlicher Abbruch, Spot setzt sich hin; er bietet nach 3 s ohne Reaktion an, hart nachzusetzen. Grosser roter **NOT-AUS** = Prozess töten, **ein Klick, keine Rückfrage**. | Nur hart wäre untauglich (jedes Programmende liesse den Spot umfallen); nur freundlich wäre wertlos, wenn ein Skript in einem blockierenden Aufruf hängt. Beim Not-Aus entfällt die Rückfrage bewusst: wer ihn drückt, hat keine Zeit für einen Dialog. |
| H5 | Aussehen | **Helle und dunkle Palette, der Windows-Einstellung folgend.** | Der Mehraufwand ist gering, wenn die Farben von Anfang an zwei benannte Paletten sind; nachträglich ist er hoch. Der Fall, den ein reiner Dunkelmodus schlecht bedient, kommt sicher: die Vorführung am Beamer im hellen Zimmer. |

---

## 3 Architektur

Die GUI ist **Klient** von `workshop/` und `record/`. Sie importiert **niemals** `bosdyn`
oder `spotlab.backends`. Das folgt zwingend aus H1: die GUI hält kein Lease, also hat sie in
der Backend-Schicht nichts zu suchen. Ein `import bosdyn` im GUI-Code bricht eine
Entwurfsentscheidung und ist als Fehler zu behandeln.

```
gui/            Widgets — dünne Hüllen, die Signale verdrahten
   │
workshop/       control.py · launcher.py · project.py · editor.py · doctor.py
record/         tail.py · read.py · run.py
config.py       Zugangsdaten und Grenzen (für die Ansicht „Spot")
   │
(api/, backends/, bosdyn — für die GUI unerreichbar)
```

**Tragendes Prinzip: so wenig Qt wie möglich.** Alles, was nicht Widget ist, liegt in
Qt-freien Modulen und wird normal mit pytest geprüft. Das betrifft namentlich das
inkrementelle Nachlesen der jsonl-Dateien, das Finden und Stoppen von Läufen und die
Palettenwahl.

### Verzeichnis

```
src/spotlab/
  record/tail.py            NEU — inkrementelles jsonl-Nachlesen, Qt-frei
  workshop/control.py       NEU — Läufe finden, freundlich stoppen, hart beenden, Qt-frei
  workshop/launcher.py      GEÄNDERT — start_script() nicht blockierend
  record/sampler.py         GEÄNDERT — prüft auf Stopp-Markierung
  record/run.py             GEÄNDERT — Prozess-ID in lauf.json
  cli.py                    GEÄNDERT — Unterkommando `gui`
  gui/
    __init__.py
    app.py                  QApplication, Hauptfenster, main()
    theme.py                zwei Paletten, Systemmodus lesen
    header.py               Kopfleiste: Status + NOT-AUS
    sidebar.py              Navigation
    watcher.py              Qt-Signale um record/tail.py
    workers.py              Prüf-Arbeiter, Ausgabe-Leser
    views/
      projects.py
      live.py
      runs.py
      checkup.py            Zugangsdaten + Prüfung
```

### Installation

```
pip install -e .[gui]
spotlab gui
```

Ohne das Extra meldet `spotlab gui` im Klartext, was zu installieren ist — kein
`ModuleNotFoundError`.

---

## 4 Nachträge am Fundament

Drei Ergänzungen an bestehendem Code. Sie sind Voraussetzung, nicht Beiwerk.

**a) Prozess-ID in `lauf.json`.** Neues Feld `pid`, gesetzt beim Anlegen des Laufs.
Ohne sie könnte der Not-Aus keinen Lauf beenden, den die GUI nicht selbst gestartet hat —
also keinen einzigen F5-Lauf aus VS Code. Er wäre für die Hälfte der Fälle eine Attrappe.

**b) Stopp-Markierung.** Die GUI legt die Datei `stopp` im Lauf-Verzeichnis an. Der
Abtaster-Thread prüft bei jedem Takt (10 Hz) auf ihre Existenz und löst mit
`_thread.interrupt_main()` einen `KeyboardInterrupt` im Hauptthread aus. Der Lauf landet
damit in dem Abbruchpfad, den `connect()` bereits behandelt: Ergebnis `abgebrochen`,
vollständiger Abbau, Spot setzt sich hin. **Kein neuer Sonderweg, sondern der vorhandene.**

Der Weg über eine Datei statt über ein Signal ist bewusst gewählt: er funktioniert für jeden
Lauf unabhängig davon, wer ihn gestartet hat, und umgeht die Windows-Eigenheiten beim
Zustellen von `SIGINT` an einen fremden Prozess.

**Grenze, die genau H4 begründet:** `_thread.interrupt_main()` wirkt erst, wenn der
Hauptthread wieder Python-Bytecode ausführt. Hängt er in einem blockierenden Aufruf der
gRPC-Bibliothek, kann der Abbruch verzögert oder gar nicht ankommen. Deshalb gibt es den
harten Knopf — und deshalb wäre ein nur-freundlicher Stopp keine Sicherheitsfunktion.

**c) `run_script` blockiert.** Die Funktion nutzt `subprocess.run` und kehrt erst zurück,
wenn das Skript fertig ist. Für das CLI korrekt, für die GUI untauglich — das Fenster wäre
für die ganze Laufdauer eingefroren. `launcher.py` wird aufgeteilt:

- `start_script(pfad, dryrun=False, starter=subprocess.Popen) -> Popen` — kehrt sofort zurück
- `run_script(pfad, dryrun=False, ...) -> int` — bleibt die blockierende CLI-Variante,
  **implementiert auf `start_script`**, damit es keinen zweiten Code-Pfad gibt

**d) Arbeitsordner in der Konfiguration.** `Config` bekommt das Feld `workspace: str = ""`,
`save_config` schreibt es als `[gui] workspace`, `load_config` liest es mit Vorgabe leer.
Damit merkt sich die GUI, wo die Projekte liegen, ohne einen zweiten Speicherort neben
`config.toml` einzuführen.

Die GUI liest die Ausgabe des Kindprozesses in einem Arbeits-Thread mit — sonst füllt sich
der Pipe-Puffer und der Kindprozess bleibt stehen. Die Zeilen erscheinen in der
Live-Ansicht und werden zusätzlich nach `ausgabe.log` des Laufs geschrieben, sobald der
Beobachter das Lauf-Verzeichnis kennt. Ein GUI-Lauf ist damit genauso vollständig
archiviert wie ein `spotlab run`.

---

## 5 Komponenten

### 5.1 `record/tail.py` — inkrementelles Nachlesen

```python
class JsonlTail:
    def __init__(self, path): ...
    def neue_saetze(self) -> list[dict]:
        """Alle vollständigen Zeilen seit dem letzten Aufruf."""
```

Der heikle Punkt und der Grund, warum das ein eigenes, geprüftes Modul ist: **eine halb
geschriebene letzte Zeile darf nicht verschluckt werden.** Der Stand wird nur bis zum
letzten vollständigen Zeilenumbruch fortgeschrieben; der Rest wird beim nächsten Aufruf
gelesen, wenn er vollständig ist. Ein naiver Ansatz verliert hier still Messwerte.

Weitere Fälle: Datei existiert noch nicht (leere Liste, kein Fehler) · Datei ist kürzer als
der gemerkte Stand (neu begonnen ⇒ Stand zurücksetzen) · unlesbare Zeile wird übersprungen,
wie in `read_jsonl`.

### 5.2 `workshop/control.py` — Läufe finden und anhalten

```python
LEBENSZEICHEN_S = 2.0
STOPP_DATEI = "stopp"

def ist_aktiv(run_dir, grenze_s=LEBENSZEICHEN_S) -> bool
def aktive_laeufe(runs_dir, grenze_s=LEBENSZEICHEN_S) -> list[Path]
def stoppe_freundlich(run_dir) -> None
def beende_hart(run_dir, killer=None) -> bool
```

**Lebendigkeit über den Änderungszeitpunkt von `zustand.jsonl`**, nicht über die Prozess-ID:
der Abtaster schreibt mit 10 Hz, liegt die letzte Änderung mehr als zwei Sekunden zurück,
läuft nichts mehr. Das ist plattformneutral — unter Windows ist `os.kill(pid, 0)` kein Test,
sondern beendet den Prozess.

**`beende_hart` tötet nur einen Lauf, der nach diesem Kriterium noch lebt.** Prozess-IDs
werden vom Betriebssystem wiederverwendet; eine gespeicherte ID blind zu töten könnte einen
fremden Prozess treffen. Die Lebendigkeitsprüfung bindet das Zeitfenster auf zwei Sekunden
und macht die Verwechslung praktisch unmöglich. Gibt `False` zurück, wenn der Lauf nicht
mehr aktiv ist.

Plattformabhängig ist nur das Töten selbst: unter Windows `taskkill /PID <pid> /T /F`,
sonst `os.kill(pid, SIGKILL)`. Der `killer`-Parameter ist die Testnaht.

### 5.3 `gui/theme.py` — Paletten

Zwei benannte Paletten als Datenstruktur, keine Farbliterale im Widget-Code:

```python
@dataclass(frozen=True)
class Palette:
    hintergrund: str; flaeche: str; rand: str
    text: str; gedaempft: str
    akzent: str; ok: str; warnung: str; gefahr: str

DUNKEL: Palette
HELL: Palette

def palette_fuer(dunkel: bool) -> Palette
def stylesheet(palette: Palette) -> str
```

`theme.py` ist **vollständig Qt-frei** und damit ohne Fenster testbar. Das Auslesen der
Windows-Einstellung braucht Qt und liegt deshalb in `app.py`, das `palette_fuer(dunkel)` nur
noch das fertige Ja/Nein übergibt. Die Farbwerte sind die aus dem Entwurf abgenommenen.

### 5.4 `gui/watcher.py` und `gui/workers.py`

**`RunWatcher`** — Thread, 250-ms-Takt. Sucht neue Lauf-Verzeichnisse, liest `zustand.jsonl`
und `ereignisse.jsonl` über `JsonlTail` nach, bemerkt neue Dateien in `bilder/`. Signale:
`lauf_begonnen(Path)`, `zustand(dict)`, `ereignis(dict)`, `bild(Path)`, `lauf_beendet(RunSummary)`.

Abgefragt statt `QFileSystemWatcher`: Anfügungen an eine offene Datei lösen unter Windows
keine verlässliche Verzeichnisbenachrichtigung aus, und 10 Hz Anfügungen würden einen
Ereignis-Beobachter überschwemmen. Ein 250-ms-Takt, der nur die neuen Bytes liest, kostet
praktisch nichts und verhält sich vorhersehbar.

**`DoctorWorker`** — führt `diagnose()` einmalig aus, Signal `fertig(list[Check])`. Während
er läuft, ist der Prüfknopf gesperrt und beschriftet sich um.

**`OutputReader`** — liest die Pipe des Skriptprozesses zeilenweise, Signal `zeile(str)`.

Alle drei melden unerwartete Ausnahmen über ein Signal `fehler(str)` ans Fenster.
**Eine GUI, die still nichts mehr tut, ist schlimmer als eine, die abstürzt.**

### 5.5 Kopfleiste

Immer sichtbar, in jeder Ansicht: Ampel · Robotername · IP · Akku · Lease-Halter ·
Not-Aus-Zustand — rechts der rote **NOT-AUS**.

Die Werte stammen aus der letzten Prüfung. **Läuft ein Skript, kommen Akku und
Bewegungszustand live aus `zustand.jsonl`**, ohne dass die GUI den Roboter befragen müsste.

Unter dem Knopf steht dauerhaft im Klartext: er beendet das laufende Programm sofort,
woraufhin der Spot die Motoren abschaltet und absackt; er wirkt nur auf das laufende
spotlab-Programm; **das primäre Sicherheitsmittel bleibt der physische Not-Aus.**

### 5.6 Ansicht „Projekte"

Liste der Projektordner im gemerkten Arbeitsordner (erkannt an einem `runs/`-Unterordner).
Knöpfe *Neu* (`create_project`) und *In VS Code öffnen* (`open_in_editor`). Darunter die
`.py`-Dateien des gewählten Projekts mit *Starten* und einem Häkchen **Trockenlauf** —
damit Üben ohne Roboter ein sichtbarer Schalter ist statt einer Kommandozeilenoption, die
niemand findet.

Der Arbeitsordner wird in `config.toml` unter `[gui] workspace` gemerkt.

### 5.7 Ansicht „Live-Lauf"

Skriptname, Laufzeit, Ereignisliste, Telemetrie-Kacheln (Pose, Tempo, Füsse, Akku), das
neueste Bild aus `bilder/`, die `print`-Ausgabe des Skripts, und der unauffällige **Stopp**.

Läuft nichts, steht hier kein leeres Gitter, sondern der Satz, was als Nächstes zu tun ist.

Der Stopp schreibt die Markierung und wartet. Ist der Lauf nach **3 Sekunden** noch aktiv,
erscheint der Hinweis „reagiert nicht" mit dem Angebot, hart zu beenden.

### 5.8 Ansicht „Läufe"

Tabelle der vergangenen Läufe aus `list_runs`, Ergebnis eingefärbt. Detailansicht mit den
Ereignissen und **einer Kurve: kommandiertes gegen gemessenes Tempo über die Zeit.**

Das ist bewusst die einzige Auswertung dieser Stufe. Sie ist genau die Grösse, auf die die
spätere Real→Sim-Kalibrierung hinausläuft, und sie macht aus `zustand.jsonl` etwas
Ansehbares statt nur Archiviertes. Das kommandierte Tempo stammt aus den
`kommando`-Ereignissen (`walk` mit `vx`), das gemessene aus `zustand.jsonl`.

### 5.9 Ansicht „Spot"

Zwei Teile.

**Zugangsdaten.** Felder für IP, Benutzer, Spitzname, Passwort sowie die
Geschwindigkeitsgrenzen; gespeichert über `save_config` und `save_password` — kein zweiter
Speicherweg, nur eine zweite Eingabemaske.

Dieser Teil schliesst eine **Lücke, die beim Entwerfen der GUI aufgefallen ist**:
`spotlab login` fragt über `input()` und `getpass()` im Terminal. Ein Schüler, der nur die
GUI benutzt, könnte sich damit nie einrichten. Die Geschwindigkeitsgrenzen sind editierbar,
damit eine Lehrperson sie für Anfängerstunden herunterdrehen kann, ohne eine TOML-Datei zu
suchen.

**Prüfung.** `diagnose()` hinter einem Knopf, die sieben Stufen untereinander, grün oder
rot, mit dem Klartext-Rat darunter.

---

## 6 Datenfluss

```
Schülerskript (eigener Prozess, besitzt Lease und Not-Aus)
   │  schreibt
   ▼
runs/<id>/  lauf.json · ereignisse.jsonl · zustand.jsonl · bilder/
   │  liest, 250-ms-Takt, inkrementell
   ▼
RunWatcher (Thread)  ──Qt-Signale──►  Kopfleiste · Live-Ansicht
   ▲
   │  stoppe_freundlich() schreibt runs/<id>/stopp
   │  beende_hart() liest pid aus lauf.json
workshop/control.py  ◄── Stopp / NOT-AUS
```

Die GUI spricht nie mit dem Roboter, ausser über `diagnose()` — und das braucht kein Lease.

---

## 7 Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| PySide6 fehlt | `spotlab gui` nennt den Installationsbefehl, kein `ModuleNotFoundError` |
| Keine Konfiguration | GUI öffnet die Ansicht „Spot" zuerst, statt leere Anzeigen zu zeigen |
| Kein Arbeitsordner gewählt | Beim ersten Start wird danach gefragt |
| `diagnose()` wirft | Als roter Eintrag in der Liste; die GUI läuft weiter |
| Skript stürzt sofort ab | Traceback in der Ausgabe, Lauf erscheint als `fehler` |
| Lauf-Ordner verschwindet | Beobachter überlebt und meldet den Lauf als beendet |
| Ausnahme in einem Arbeits-Thread | Signal `fehler(str)` ans Fenster, sichtbar gemeldet |
| Hartes Beenden bei totem Lauf | `beende_hart` gibt `False`, GUI meldet „läuft nicht mehr" |

---

## 8 Prüfung

**Ohne Roboter und ohne Fenster** (der grösste Teil):

- `record/tail.py`: halbe letzte Zeile wird beim nächsten Aufruf vollständig gelesen ·
  wachsende Datei · fehlende Datei · verkürzte Datei · unlesbare Zeile
- `workshop/control.py`: aktive Läufe erkennen · Stopp-Markierung schreiben · hartes Beenden
  gegen eine Attrappe · **Weigerung, einen toten Lauf zu töten**
- `record/sampler.py`: Stopp-Markierung löst `KeyboardInterrupt` im Hauptthread aus
- `record/run.py`: `pid` steht in `lauf.json`
- `workshop/launcher.py`: `start_script` kehrt sofort zurück; `run_script` verhält sich
  unverändert
- `gui/theme.py`: `palette_fuer` liefert die richtige Palette, `stylesheet` enthält keine
  Farbliterale ausserhalb der Palette
- `config.py`: `workspace` überlebt Schreiben und Lesen

**Mit Fenster, ohne Bildschirm** — `QT_QPA_PLATFORM=offscreen`, keine zusätzliche
Testabhängigkeit: Fenster baut sich · vier Ansichten vorhanden · NOT-AUS ist verdrahtet ·
ein eingespeistes `zustand`-Signal ändert die Anzeige.

**Die ganze Kette** (der wichtigste Test): ein Trockenlauf-Skript starten, prüfen dass der
Beobachter den Lauf aufgreift und Telemetrie erscheint, dann freundlich stoppen und prüfen,
dass der Lauf als `abgebrochen` endet. Läuft ohne Roboter und deckt genau die Naht ab, an
der GUI und Fundament zusammenstossen.

---

## 9 Abnahme am Gerät

Ergänzt `docs/ABNAHME.md` um drei Punkte:

| # | Prüfung | Erwartung |
|---|---|---|
| **A9** | Freundlicher Stopp aus der GUI während `walk()` | Spot bremst, setzt sich hin, Motoren aus, Lease frei; Lauf endet als `abgebrochen` |
| **A10** | NOT-AUS aus der GUI während der Spot steht | Motoren gehen aus, Spot sackt ab; Lauf bleibt auf `läuft` stehen (Prozess getötet), Roboter danach wieder verbindbar |
| **A11** | Lauf mit F5 aus VS Code starten, GUI daneben offen | GUI greift den Lauf innerhalb einer Sekunde auf, zeigt Telemetrie, und **beide Stopp-Knöpfe wirken** |

A11 ist der Punkt, der H3 und Nachtrag (a) zusammen abnimmt. Fällt er durch, ist die GUI
für den Unterrichtsalltag wertlos.

---

## 10 Nicht-Ziele

Direktmodus mit Lease in der GUI · Live-Kamerabild ohne laufendes Skript · Fernsteuerung per
Tastatur · Editor in der GUI (VS Code bleibt der Editor) · Mehrbenutzer-Ansicht ·
MCP-Server · NN-Anbindung · Auswertungen über die eine Tempo-Kurve hinaus.

---

## 11 Abhängigkeiten

| Paket | Zweck |
|---|---|
| `PySide6>=6.6` | nur im Extra `[gui]` |

Keine weiteren. Diagramme werden auf einem `QPainter`-Widget gezeichnet statt mit einer
Diagrammbibliothek — eine Kurve rechtfertigt keine zusätzliche Abhängigkeit auf zwanzig
Schullaptops.
