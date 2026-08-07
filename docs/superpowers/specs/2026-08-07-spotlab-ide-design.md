# spotlab IDE — Projekte in spotlab selbst bearbeiten

**Datum:** 2026-08-07
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 5. Setzt Fundament (Stufe 1+2), GUI (Stufe 3) und GraphNav (Stufe 4) voraus.
Die GUI-Spec führte „Editor in der GUI" ausdrücklich als Nicht-Ziel mit der Begründung
„VS Code bleibt der Editor". Diese Spec hebt das auf — **ohne VS Code abzuschaffen**.

---

## 1 Zweck

Ein Schüler soll ein Projekt in spotlab öffnen, den Code darin schreiben, ihn starten und
den Fehler sehen können, ohne das Fenster zu wechseln. Bisher endet spotlab an der Stelle,
an der es interessant wird: die Ansicht „Projekte" legt ein Projekt an und startet es, aber
zum Schreiben schickt sie in ein fremdes Programm.

Der Editor ist eine **Ergänzung**, kein Ersatz. `spotlab open` und der Knopf „In VS Code
öffnen" bleiben unverändert. Wer VS Code kann, verliert nichts; wer es nicht installiert
hat, ist nicht mehr ausgesperrt.

**Der Leitsatz für die Aufteilung im Fenster:**
> „Code" zeigt, was das Programm sagt. „Live-Lauf" zeigt, was der Roboter tut.

Zwei Orte, zwei Fragen, keine Doppelung von Telemetrie.

### Vorgefundener Stand

Geprüft in der vorhandenen Umgebung (Python 3.13.9):

| Bibliothek | Stand | Folge für den Entwurf |
|---|---|---|
| `pygments` 2.19.1 | vorhanden, **nicht deklariert** | Echtes Python-Lexing ohne neue fachliche Abhängigkeit. Muss ins Extra `[gui]` aufgenommen werden — „ist zufällig da" ist keine Abhängigkeitszusage. |
| `jedi` | fehlt | Optional, mit getestetem Rückfall. |
| `pyflakes` | fehlt | Nicht nötig: `compile()` aus der Standardbibliothek deckt Syntaxfehler ab, und mehr wollen wir nicht. |
| Qt-Bausteine | alle da | `QPlainTextEdit`, `QSyntaxHighlighter`, `QCompleter`, `QFileSystemModel`, `QTabWidget`, `QSplitter`, `QTreeView`. |

**Ein Befund aus dem eigenen Code bestimmt die Architektur.** `api/spot.py` zieht über
`api/motion.py` und `api/posture.py` den `RobotCommandBuilder` herein, über `api/state.py`
und `api/perception.py` zusätzlich `numpy` und `Pillow`:

```
api/spot.py → api/motion.py  → bosdyn.client.robot_command
            → api/state.py   → bosdyn.api.robot_state_pb2
            → api/perception.py → numpy, bosdyn.api.image_pb2
```

Ein `import spotlab.api.spot` in der GUI bräche damit die Schichtregel und würde den Editor
an das SDK ketten. **Die Vervollständigung darf die eigene API nicht importieren.**

**Zwei Befunde aus `gui/app.py`**, die den Entwurf in Abschnitt 4.8 und 5 verändern:

1. **Es gibt genau eine Ausgabe-Pipe und genau einen Leser.** `_lauf_gestartet` legt einen
   `OutputReader` an und hängt ihn an `live.zeige_ausgabe`. Ein zweiter Leser auf derselben
   Pipe würde die Zeilen zufällig unter beiden aufteilen.
2. **`_lauf_begonnen` schaltet bedingungslos auf „Live-Lauf".** Das war für F5-Läufe aus VS
   Code gewollt. Für einen Start aus dem Editor wäre es falsch — der Schüler würde beim
   Starten aus seiner eigenen Ansicht geworfen.

---

## 2 Entschiedene Grundsatzfragen

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| I1 | Ersatz oder Ergänzung | **Ergänzung.** VS Code bleibt eine gleichwertige Option. | Der Editor muss nicht mit VS Code konkurrieren, sondern die Lücke schliessen, dass spotlab ohne Fremdprogramm nicht zum Schreiben taugt. Sobald er als Ersatz gedacht wäre, bräuchte er Debugger, git und Erweiterungen — Arbeit ohne Ende und ohne Bezug zum Roboter. |
| I2 | Wo im Fenster | **Eigene Ansicht „Code"** als sechster Eintrag, drei Spalten: Dateibaum · Reiter · Ausgabe. | Der Editor in der Live-Ansicht bedient beide Fälle schlecht: beim Schreiben will man Platz und die Telemetrie lenkt ab, beim Zuschauen will man das Kamerabild gross und der Code lenkt ab. Ein Telemetrie-Streifen unter dem Editor sieht gut aus, zeigt aber nur, **solange ein Lauf läuft** — also die meiste Zeit nichts, bei dauerhaftem Platzverbrauch. |
| I3 | Hervorhebung | **`pygments`**, über das ganze Dokument lexen, nicht pro Zeile. | Zeilenweise Regex-Hervorhebung scheitert an dreifach zitierten Zeichenketten — ein Fehler, den man erst bemerkt, wenn ein Schüler einen mehrzeiligen Docstring schreibt und der halbe Rest der Datei grün wird. Ein Schülerskript hat 50–300 Zeilen; das ganze Dokument zu lexen kostet dabei nichts. |
| I4 | Syntaxprüfung | **`compile()` aus der Standardbibliothek**, plus eine deutsche Übersetzungstabelle. | Keine Abhängigkeit, kein Unterprozess, exakt dieselbe Diagnose, die der spätere Lauf melden würde. Roh ist die Meldung aber englisch — und genau daran scheitert ein Anfänger. Die Tabelle ist derselbe Ansatz wie `errors/translate.py`. |
| I5 | Vervollständigung | **Eigene Verbliste als Unterbau, `jedi` optional obendrauf, in einem eigenen Thread.** | Die eigene Liste ist sofort da, geprüft und garantiert: „nach `spot.` muss `navigate_to` vorkommen" ist eine Aussage über unseren eigenen Code. Ob `jedi` durch `with spotlab.connect() as spot:` hindurch auf `Spot` schliesst, hängt an fremder Inferenz durch einen `@contextmanager`, die wir nicht garantieren können. `jedi` deckt dafür ab, was wir nicht wissen: lokale Variablen, `math.`, `np.`, Importnamen. |
| I6 | Wie die Verbliste entsteht | **`ast` liest `api/spot.py` als Text**, kein Import. | Siehe Befund oben: ein Import zöge `bosdyn`, `numpy` und `Pillow` in die GUI. Mit `ast` funktioniert die Vervollständigung auch dort, wo das SDK gar nicht installiert ist, und hat keine Seiteneffekte. |
| I7 | Umfang des Dateibaums | **Ein Projekt auf einmal, `runs/` ausgeblendet.** | Ein `QFileSystemModel` über `runs/` horcht auf `zustand.jsonl`, in die der Sampler mit **10 Hz** schreibt — Änderungssignale im Zehntelsekundentakt für Dateien, die niemand im Editor öffnet. Und der Baum bleibt kurz genug, um ihn zu überblicken. |
| I8 | Starten | **Über `workshop/launcher.py::start_script`**, wie „Projekte" und `spotlab run`. | Kein zweiter Startweg. Ein eigener Start müsste `PYTHONUTF8`, `PYTHONPATH` und die Backend-Wahl erneut richtig setzen — drei Gelegenheiten, es anders falsch zu machen als das Original. |
| I9 | Stoppen | **Der „Stopp"-Knopf ruft `LiveView.stoppe()`** — nicht eine eigene Kopie derselben Logik. | Dieselbe Funktion aufzurufen genügt nicht; der freundliche Stopp hängt am Lauf-Verzeichnis, das die Live-Ansicht vom Watcher bekommt. Delegation heisst: **dasselbe Objekt mit demselben Zustand**, und damit garantiert dasselbe Verhalten. Das ist die Antwort auf das grösste Risiko dieser Stufe (siehe A17). |
| I10 | Fremde Änderungen an derselben Datei | **Änderungszeit und Grösse beim Laden merken, beim Speichern vergleichen.** | Folgt direkt aus I1: weil VS Code eine Option bleibt, werden beide Editoren regelmässig dieselbe Datei offen haben. Stillschweigendes Überschreiben ist der Fehler, den man erst bemerkt, wenn die Arbeit weg ist. |

---

## 3 Architektur

```
gui/editor/view.py                       Ansicht „Code" (Baum · Reiter · Ausgabe)
   │   tree.py · codeedit.py · highlighter.py · completer.py      Qt
   ↓
editor/    syntax.py · traceback.py · verbs.py                    Qt-frei, SDK-frei
   ↓
(nichts)
```

`editor/` benutzt **ausschliesslich die Standardbibliothek**. Das ist keine Sparsamkeit,
sondern die Bedingung dafür, dass die vier Stellen, an denen tatsächlich Fehler stecken
können, ohne Fenster und ohne Roboter prüfbar sind.

### Die Schichtregel, erweitert

Bisher gilt: kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `gui/`.
Das bleibt. **Neu kommt dazu:**

> **`editor/` darf nichts aus `api/`, `backends/` oder `maps/` importieren.**
> `api/spot.py` ist für `editor/verbs.py` **Text, keine Schnittstelle** — sonst zieht die
> Vervollständigung `bosdyn`, `numpy` und `Pillow` in die GUI.

Ein Test hält das fest, indem er `editor/` in einem Unterprozess ohne die Möglichkeit
importiert, `bosdyn` zu laden. **Die Regel gehört als nicht verhandelbarer Punkt in
CLAUDE.md** — sonst holt der nächste Umbau die bequeme Introspektion per Import zurück.

`gui/editor/` darf `spotlab.editor`, `spotlab.workshop` und `spotlab.gui.theme` benutzen —
dieselbe Menge, die die übrigen Ansichten schon benutzen.

### Keine neue Fähigkeit

Der Editor ist keine Roboterfähigkeit. Es kommt **kein neuer Eintrag in `Capability`** und
kein `require()`. Ein Abnahmepunkt kommt trotzdem dazu (A17) — nicht wegen einer neuen
Fähigkeit, sondern wegen eines neuen Wegs zu einer alten.

---

## 4 Komponenten

### 4.1 `editor/syntax.py` — Syntaxfehler auf Deutsch

```python
@dataclass(frozen=True)
class Fehlerstelle:
    zeile: int      # 1-basiert; 1, wenn Python keine Zeile nennt
    spalte: int     # 1-basiert; 0, wenn unbekannt
    text: str       # deutsch

UEBERSETZUNGEN: tuple[tuple[str, str], ...]   # (englisches Fragment, deutscher Text)

def uebersetze(meldung: str) -> str
def pruefe(quelltext: str, name: str = "<editor>") -> Fehlerstelle | None
```

`pruefe` ruft `compile(quelltext, name, "exec")` und fängt `SyntaxError` (damit auch
`IndentationError` und `TabError`) sowie `ValueError` (Nullbytes im Text). Alles andere
fliegt weiter — eine Prüffunktion, die jeden Fehler schluckt, verbirgt Programmfehler.

**Warnungen müssen unterdrückt werden.** `compile()` meldet ab Python 3.12 eine
`SyntaxWarning` für ungültige Escape-Sequenzen — und `"C:\Users\..."` ist genau das, was ein
Schüler auf Windows als Erstes tippt. Ohne `warnings.catch_warnings()` um den Aufruf herum
füllt sich die Konsole **bei jedem Tastendruck**.

`SyntaxError.lineno` und `.offset` dürfen `None` sein; beide werden abgefangen.

**Die Tabelle ist geordnet, das erste passende Fragment gewinnt.** Spezifisch vor allgemein:

| Fragment in der englischen Meldung | Deutscher Text |
|---|---|
| `Perhaps you forgot a comma` | Hier fehlt vermutlich ein Komma. |
| `expected ':'` | Hier fehlt ein Doppelpunkt am Zeilenende. |
| `was never closed` | Diese Klammer wurde nie geschlossen. |
| `unterminated triple-quoted string literal` | Dieser mehrzeilige Text wurde nie geschlossen — es fehlen drei Anführungszeichen. |
| `unterminated string literal` | Dieser Text wurde nie geschlossen — es fehlt ein Anführungszeichen. |
| `expected an indented block` | Nach dem Doppelpunkt muss die nächste Zeile eingerückt sein. |
| `unexpected indent` | Diese Zeile ist zu weit eingerückt. |
| `unindent does not match` | Diese Einrückung passt zu keiner Zeile darüber. |
| `inconsistent use of tabs` | Hier sind Tabulatoren und Leerzeichen gemischt. spotlab schreibt Leerzeichen. |
| `cannot assign to` | Links vom `=` muss ein Name stehen. |
| `invalid syntax` | Hier stimmt etwas nicht — häufig ein fehlender Doppelpunkt oder eine Klammer. |

Passt nichts, lautet der Text **`Python meldet: <Originalmeldung>`**. Das ist die Regel aus
CLAUDE.md: keine Ursache behaupten, die nicht geprüft ist. Eine erfundene deutsche Erklärung
für einen unbekannten Fehler schickt auf die falsche Fährte und kostet mehr Zeit als der
englische Originaltext.

Ein Test hält die Ordnung fest: `Perhaps you forgot a comma` muss vor `invalid syntax`
stehen, sonst schluckt das allgemeine Fragment das spezifische (die echte Meldung lautet
`invalid syntax. Perhaps you forgot a comma?`).

### 4.2 `editor/traceback.py` — anklickbare Stellen

```python
@dataclass(frozen=True)
class Stelle:
    pfad: Path
    zeile: int
    von: int        # Zeichenoffset im übergebenen Text
    bis: int

MUSTER = re.compile(r'File "(?P<pfad>[^"]+)", line (?P<zeile>\d+)')

def finde_stellen(text: str, wurzel: Path) -> list[Stelle]
```

Aufgenommen wird eine Fundstelle nur, wenn der Pfad **existiert und unterhalb von `wurzel`
liegt** (`Path.resolve().is_relative_to(wurzel.resolve())`). Damit fallen `<string>`,
`<stdin>`, gelöschte temporäre Dateien und — wichtig — alles unter `site-packages` und im
SDK heraus.

**Das ist kein Detail, sondern Absicht:** ein Traceback zeigt fast immer mehr Rahmen aus
fremdem Code als aus dem eigenen. Wäre alles anklickbar, landete ein Schüler mit einem Klick
in `bosdyn/client/robot_command.py` und änderte es. Der Rest der Zeile bleibt normaler Text.

`von`/`bis` sind Offsets **relativ zum übergebenen Text**. Die Ansicht ruft die Funktion pro
angehängter Ausgabezeile auf; die Tests rufen sie über ganze Tracebacks auf. Beides
funktioniert, weil die Funktion über den Text nichts annimmt.

### 4.3 `editor/verbs.py` — die eigene API als Vorschlagsliste

```python
@dataclass(frozen=True)
class Vorschlag:
    name: str
    signatur: str   # "move(forward=0.0, side=0.0, turn=0.0)"
    hilfe: str      # erste Docstring-Zeile, deutsch; "" wenn keine

def methoden(quelltext: str, klasse: str) -> list[Vorschlag]
def funktionen(quelltext: str) -> list[Vorschlag]          # Modulebene
def praefix(text_vor_cursor: str) -> str | None            # "spot" | "spotlab" | None
def spot_verben() -> list[Vorschlag]                       # gecacht
def spotlab_verben() -> list[Vorschlag]                    # gecacht
```

`methoden` parst mit `ast.parse`, sucht die `ClassDef`, nimmt jede `FunctionDef`, deren Name
nicht mit `_` beginnt. Die Signatur entsteht aus `ast.unparse(node.args)`; das führende
`self` wird abgeschnitten. Die Hilfe ist die erste Zeile von `ast.get_docstring(node)`.

Die Quelldateien werden über **reine Pfadarithmetik** gefunden — `editor/` und `api/` sind
Geschwister unter `src/spotlab/`:

```python
WURZEL = Path(__file__).resolve().parent.parent      # src/spotlab
SPOT_QUELLE = WURZEL / "api" / "spot.py"
PAKET_QUELLE = WURZEL / "__init__.py"
```

Kein Import, kein `__file__` eines fremden Moduls, keine Ladereihenfolge.

**Lässt sich eine Datei nicht lesen oder nicht parsen, ist das Ergebnis `[]`.** Der Editor
darf daran nie scheitern; im schlimmsten Fall gibt es keine Vorschläge.

Ergebnis für den Schüler — die Vorschlagsliste ist zugleich die Dokumentation, weil unsere
Docstrings deutsch sind:

```
spot.
  ▸ move(forward=0.0, side=0.0, turn=0.0)   Geht eine Strecke und dreht sich dabei.
  ▸ navigate_to(waypoint)                   Fährt autonom zu einem Wegpunkt der aktiven Karte.
  ▸ cameras()                               Nennt die verfügbaren Kameras.
```

Für jemanden, der nicht weiss, was es überhaupt gibt, ist das der grösste Einzelnutzen des
Editors — und er hängt an keiner fremden Bibliothek.

`praefix` ist bewusst hier und nicht im Widget: „welches Ziel steht links vom Punkt" ist
Textarbeit und wird als Textarbeit geprüft, samt der Fälle `spot.mo`, `x = spot.`,
`spot.move(spot.` und `# spot.` (im Kommentar: kein Vorschlag).

**Das ist eine Namensregel, keine Inferenz**, und das soll es auch sein: `praefix` erkennt
die Namen `spot` und `spotlab`, weil unsere Vorlage `with spotlab.connect() as spot:`
schreibt und praktisch jedes Schülerskript das übernimmt. Wer die Variable `roboter` nennt,
bekommt von uns keine Vorschläge — und genau dort greift `jedi`, das den Typ tatsächlich
herleiten kann. Die beiden Schichten decken bewusst verschiedene Fälle ab.

### 4.4 `gui/editor/highlighter.py` — Hervorhebung

Ein `QSyntaxHighlighter`, der **nicht selbst lext**. Das Lexen läuft über
`PythonLexer().get_tokens_unprocessed(text)` einmal über das ganze Dokument und füllt eine
Abbildung `Blocknummer → [(spalte, länge, format)]`; `highlightBlock` schlägt darin nur nach.

Neu gelext wird über **denselben entprellten Zeitgeber wie die Syntaxprüfung** (150 ms nach
dem letzten Tastendruck). Der Zeitgeber liegt in `codeedit.py` und löst ein Signal
`ruhe` aus; Hervorhebung und Syntaxprüfung hängen beide daran. Ein Zeitgeber, zwei
Verbraucher — und kein `rehighlight()` aus einem Änderungssignal heraus, das sich selbst
wieder auslösen würde.

Zuordnung Token → Palette (`token in Token.Keyword` prüft in pygments auch Untertypen):

| Token | Farbe |
|---|---|
| `Token.Keyword` | `schluesselwort` |
| `Token.String` | `zeichenkette` |
| `Token.Comment` | `kommentar` |
| `Token.Number` | `zahl` |
| `Token.Name.Function`, `Token.Name.Class`, `Token.Name.Builtin` | `funktion` |
| alles andere | `text` |

### 4.5 `gui/theme.py` — fünf neue Farben

`Palette` bekommt `schluesselwort`, `zeichenkette`, `kommentar`, `zahl`, `funktion`.

| Feld | DUNKEL | HELL |
|---|---|---|
| `schluesselwort` | `#c678dd` | `#a626a4` |
| `zeichenkette` | `#98c379` | `#2a7d3f` |
| `kommentar` | `#7f848e` | `#8a9099` |
| `zahl` | `#d19a66` | `#97600a` |
| `funktion` | `#61afef` | `#2f5fd0` |

Der bestehende Test, dass im Stylesheet kein Farbwert ausserhalb der Palette vorkommt, gilt
unverändert. Die Werte sind ein Ausgangspunkt; **beurteilt wird das Aussehen nur auf einem
echten Desktop**, weil der Offscreen-Modus keine Schriften hat.

### 4.6 `gui/editor/codeedit.py` — das Textfeld

Ein `QPlainTextEdit` mit:

- **Zeilenleiste** als eigenes Widget links, Breite aus der Stellenzahl der Zeilenzahl.
- **Aktuelle Zeile** hervorgehoben über `setExtraSelections`.
- **Fehlerkringel**: `QTextCharFormat.SpellCheckUnderline` mit `gefahr` als Unterstrichfarbe
  auf der Zeile aus `syntax.pruefe`. Die Meldung erscheint als Kurzhinweis (`setToolTip`)
  und in der Statuszeile.
- **Einrückung**: Tab schreibt vier Leerzeichen, Shift+Tab nimmt vier weg, Enter behält die
  Einrückung und rückt nach einem `:` am Zeilenende eine Ebene ein.
- **Ctrl+S** löst das Signal `speichern_gewuenscht` aus, **Ctrl+F** die Suchleiste,
  **Ctrl+Space** erzwingt Vorschläge.
- **Suchen und Ersetzen** in der offenen Datei: eine einblendbare Leiste mit Suchfeld,
  Ersetzungsfeld, Weiter/Zurück, Ersetzen, Alle ersetzen.

Die Einrückungsregeln sind Textarbeit und werden über die Hilfsfunktionen aus `editor/` und
über simulierte Tastendrücke geprüft.

### 4.7 `gui/editor/completer.py` — Vorschläge

```python
def zusammenfuehren(eigene, fremde) -> list[Vorschlag]   # Qt-frei geprüft
```

Ein `QCompleter` über ein Modell mit zwei Rollen: `Qt.DisplayRole` zeigt
`signatur  —  hilfe`, ein eigener `completionRole` enthält den blossen Namen. Nur so passt
die Präfixsuche auf `mov`, während in der Liste die volle Signatur steht.

Ausgelöst wird nach einem `.` oder ab einem Bezeichnerzeichen; das Ziel bestimmt
`verbs.praefix`.

**`jedi` läuft in einem eigenen Thread.** Die eigene Liste erscheint sofort; jedis Antwort
wird ergänzt, sobald sie eintrifft. Jede Anfrage trägt eine laufende Nummer — trifft eine
Antwort ein, die nicht zur aktuellen Nummer gehört, wird sie verworfen, sonst überschreibt
eine langsame alte Antwort eine schnelle neue.

**Bei Namensgleichheit gewinnt der eigene Eintrag**, weil nur er Signatur und deutsche
Erklärung trägt. `zusammenfuehren` ist dafür Qt-frei und geprüft.

Fehlt `jedi` oder wirft es, bleibt es bei der eigenen Liste — **ohne Hinweis und ohne
Fehler**. Ein Editor, der sich über eine fehlende Vervollständigung beschwert, ist lästiger
als einer, der leise weniger kann.

> Ehrlich zum Umfang: mit `pip install -e .[gui]` ist `jedi` normalerweise da. Der Rückfall
> ist deshalb keine Alltagslage, sondern eine Robustheitszusage — und die Bedingung dafür,
> dass die ganze Testsuite ohne `jedi` grün ist.

### 4.8 `gui/editor/tree.py` — der Dateibaum

`QFileSystemModel` auf dem Projektordner, `setNameFilters(["*.py", "*.md", "*.txt",
"*.json"])` mit `setNameFilterDisables(False)`.

`runs/` verschwindet über einen `QSortFilterProxyModel`, der ein Verzeichnis dieses Namens
**auf der obersten Ebene** ablehnt — Namensfilter greifen in Qt nur auf Dateien, nicht auf
Verzeichnisse. Doppelklick löst `datei_gewaehlt(Path)` aus.

### 4.9 `gui/editor/view.py` — die Ansicht „Code"

Ein `QSplitter` mit drei Spalten. Links oben ein Auswahlfeld mit den Projekten des
Arbeitsordners (dieselbe Erkennung wie in `views/projects.py::projekte_in`), darunter der
Baum. In der Mitte die Werkzeugleiste und die Reiter. Rechts die Ausgabe.

**Reiter.** Je Reiter: `pfad`, das Textfeld, `mtime` und `groesse` beim Laden, ein
Verschmutzt-Merker. Der Titel trägt `●`, solange ungespeichert. Schliessen fragt nach.

**Lesen und Schreiben.** Gelesen wird mit `encoding="utf-8"`; ein `UnicodeDecodeError`
führt zu einer Meldung statt zu einem halb geladenen Reiter. Geschrieben wird mit
`encoding="utf-8", newline="\n"`. Ohne das schreibt Python auf Windows CRLF, und jede Datei,
die einmal durch unseren Editor läuft, sieht danach in git vollständig geändert aus.

**Fremde Änderung.** Weichen `mtime` oder `groesse` beim Speichern von den gemerkten Werten
ab, fragt ein Dialog mit drei Wegen: *Überschreiben*, *Neu laden* (verwirft die eigenen
Änderungen), *Abbrechen*.

**Starten.** `▶ Starten` speichert zuerst — wer auf Starten drückt, meint den Code, den er
sieht — und ruft `start_script(pfad, dryrun=…)`. Ein Häkchen „Trockenlauf" wie in
„Projekte". Die Ansicht meldet den Prozess als Signal
`lauf_gestartet(prozess, skript)` nach oben; sie legt **keinen eigenen `OutputReader` an**.

**Stoppen.** Läuft ein Lauf, wird der Knopf zu `■ Stopp` und löst
`stopp_gewuenscht` aus. Das Fenster verbindet es mit `LiveView.stoppe()` — siehe I9.

**Ausgabe.** Ein `QPlainTextEdit`, schreibgeschützt. Jede angehängte Zeile läuft durch
`finde_stellen(zeile, arbeitsordner)`; Fundstellen bekommen `akzent` und Unterstreichung.
Ein Klick öffnet die Datei im Reiter, springt zur Zeile und markiert sie.

Unter der Ausgabe steht ein `QLabel` mit `objectName="Gedaempft"`: „Pose, Tempo und
Kamerabild zeigt die Ansicht Live-Lauf." Nur Text, kein Klickziel — der Leitsatz aus
Abschnitt 1, sichtbar gemacht statt nur eingehalten.

### 4.10 Anpassungen am bestehenden Fenster

**Ein Leser, zwei Senken.** `_lauf_gestartet` verbindet dieselbe `zeile`-Signalquelle
zusätzlich mit `code.zeige_ausgabe`. Ein zweiter `OutputReader` käme nicht in Frage: beide
läsen aus derselben Pipe und teilten sich die Zeilen zufällig auf.

**Nicht wegschalten, wenn aus dem Editor gestartet wurde.** Das Fenster merkt sich die
Herkunft des letzten Starts (`self._start_aus`). `_lauf_begonnen` schaltet nur dann auf
„Live-Lauf", wenn die Herkunft nicht `"code"` ist. **Der F5-Fall aus VS Code bleibt
unverändert** — er hat gar keine Herkunft und schaltet weiterhin um, und das war Absicht.

`views/projects.py` bekommt einen Knopf „In spotlab öffnen", der `projekt_oeffnen(Path)`
auslöst; das Fenster schaltet auf „Code" und setzt dort das Projekt.

---

## 5 Datenfluss

**Tippen:**

```
Tastendruck → Zeitgeber (150 ms)
                ├→ pygments lext das Dokument → Tokenkarte → rehighlight()
                └→ syntax.pruefe(text) → Fehlerstelle | None → Kringel + Statuszeile
```

**Vorschlag:**

```
"spot." → verbs.praefix() → "spot" → verbs.spot_verben()   [sofort, aus dem Cache]
                                   ↘ jedi im Thread → zusammenfuehren() [wenn rechtzeitig]
```

**Starten und Fehler:**

```
▶ Starten → speichern → start_script() → Signal lauf_gestartet
                                            ↓
                        app.py: OutputReader (einer) ─┬→ live.zeige_ausgabe
                                                      └→ code.zeige_ausgabe
                                                            ↓
                                          finde_stellen(zeile, arbeitsordner)
                                                            ↓
                                              Klick → Reiter öffnen, Zeile markieren
```

Parallel und unverändert: `connect()` im Kindprozess legt das Lauf-Verzeichnis an, der
`RunWatcher` sieht es, „Live-Lauf" und „Läufe" füllen sich von selbst. **Der Editor macht
dafür nichts** — er benutzt nur denselben Starter.

---

## 6 Fehlerbehandlung

| Lage | Verhalten |
|---|---|
| Datei ist nicht UTF-8 | Meldung „Diese Datei ist nicht UTF-8 und lässt sich hier nicht öffnen." Kein halb geladener Reiter. |
| Datei ist seit dem Laden fremd geändert | Dialog mit Überschreiben / Neu laden / Abbrechen. |
| Datei beim Speichern schreibgeschützt oder weg | `OSError` als Meldung, Reiter bleibt verschmutzt. Nichts geht verloren. |
| Syntaxfehler beim Starten | Der Start wird **nicht verhindert.** Der Kringel ist ein Hinweis, kein Riegel — Python meldet denselben Fehler gleich darauf in der Ausgabe, mit derselben Zeilennummer, und dort ist er anklickbar. Ein Riegel würde nur die eine Lage abdecken, in der unsere Prüfung recht hat. |
| `jedi` fehlt oder wirft | Stillschweigend nur die eigene Liste. |
| `api/spot.py` unlesbar oder unparsbar | Leere Vorschlagsliste, kein Fehler. |
| Projektordner verschwindet | Baum leert sich, Reiter bleiben offen und lassen sich speichern. |
| Start scheitert (`SpotlabError`) | Meldung wie in „Projekte", Knopf bleibt auf `▶ Starten`. |

---

## 7 Prüfung

**Qt-frei, ohne Fenster** — die vier Stellen, an denen Fehler tatsächlich stecken:

- `syntax.pruefe`: erkennt fehlenden Doppelpunkt, offene Klammer, offene Zeichenkette,
  falsche Einrückung; liefert die richtige Zeile; gibt bei gültigem Code `None`;
  **unbekannte Meldung bleibt englisch mit deutschem Rahmen**; die Tabellenordnung
  spezifisch-vor-allgemein ist festgehalten; `"C:\Users"` erzeugt keine Warnung auf stderr.
- `traceback.finde_stellen`: findet die Stelle im eigenen Projekt; **lässt `site-packages`
  und `<string>` aus**; kommt mit Windows-Pfaden samt Doppelpunkt und Rückstrichen zurecht;
  Offsets stimmen.
- `verbs`: `spot_verben()` enthält `navigate_to`, `move`, `cameras`; die Signatur enthält
  kein `self`; die Hilfe ist die erste Docstring-Zeile; `praefix` in allen Fällen aus 4.3;
  unparsbarer Text ergibt `[]`.
- `zusammenfuehren`: eigener Eintrag gewinnt bei Namensgleichheit; Reihenfolge stabil.

**Schichtregel als Test:** ein Unterprozess importiert `spotlab.editor.*` und prüft, dass
danach weder `bosdyn` noch `numpy` noch `PySide6` in `sys.modules` steht.

**Ohne `jedi` muss die ganze Suite grün sein.** Ein Test erzwingt zusätzlich den
Import-Fehlschlag und prüft, dass Vorschläge trotzdem kommen. Ist `jedi` installiert, prüft
ein `skipif`-Test den Zusammenführungsweg mit echten jedi-Ergebnissen.

**Qt, offscreen** wie bisher, Widgets in Variablen festgehalten: Reiter öffnen und
schliessen, Verschmutzt-Merker, Speichern schreibt UTF-8 mit `\n`, fremde Änderung erkannt,
`runs/` ist im Baum nicht sichtbar, Klick in der Ausgabe öffnet den Reiter an der richtigen
Zeile.

**Ein Test startet wirklich einen Prozess** aus der Ansicht heraus (Trockenlauf), liest die
Ausgabe und prüft, dass eine Traceback-Zeile anklickbar wird. Das ist die Regel, an der „In
VS Code öffnen" durch die ganze Suite gerutscht ist: Attrappen prüfen nur, dass die richtigen
Argumente gebaut werden — nicht, dass das Betriebssystem damit etwas anfangen kann.

**Zwei Regressionstests für 4.10**, beide echte Fehlerquellen und beide ohne Roboter
prüfbar: ein aus „Code" gestarteter Lauf schaltet die Ansicht **nicht** um; ein von aussen
gestarteter Lauf schaltet **weiterhin** um.

---

## 8 Abnahme am Gerät

### A17 — Ein aus dem Editor gestarteter Lauf lässt sich genauso stoppen

**Prozedur** Ein Programm aus der Ansicht „Code" starten. Erst „Stopp" drücken, im zweiten
Durchgang den NOT-AUS.

**Erwartung** „Stopp" setzt Spot hin wie bei einem Lauf aus „Projekte". Der NOT-AUS schaltet
die Motoren ab. Der Lauf erscheint in „Läufe".

**Warum das trotz Delegation am Gerät geprüft wird:** ein zweiter Startweg, der beim
Anhalten anders reagiert, wäre die gefährlichste Art, diese Stufe falsch zu bauen. Dass der
Knopf dieselbe Methode desselben Objekts ruft, steht im Code — dass die Kette aus Watcher,
Lauf-Verzeichnis und Stopp-Markierung auch bei diesem Startweg vollständig geschlossen ist,
zeigt erst der Roboter.

---

## 9 Nicht-Ziele

- **Debugger mit Haltepunkten.** Der Wert für ein Schülerskript ist gering, der Aufwand
  gross, und ein angehaltener Prozess mit gehaltenem Lease ist sicherheitstechnisch das
  Gegenteil dessen, was Stufe 1 aufgebaut hat: dort bedeutet Prozessende sicherer Zustand.
- **git-Integration, Erweiterungen, Mehrfachcursor, Umbenennen über Dateien hinweg,
  eingebautes Terminal, projektweite Suche.** Gesucht wird in der offenen Datei.
- **Typinferenz über fremde Bibliotheken** aus eigener Kraft. Das ist genau die Arbeit, die
  `jedi` macht, und wir garantieren sie nicht.
- **Ersatz für VS Code.** Siehe I1.

---

## 10 Offene Annahmen

1. **Die Docstrings in `api/` sind deutsch und einzeilig genug**, dass die erste Zeile als
   Hilfe taugt. Trifft das für einzelne Methoden nicht zu, werden die Docstrings angepasst —
   nicht die Vervollständigung.
2. **`ast.unparse(node.args)` liefert lesbare Signaturen** für unsere Methoden. Falls eine
   Signatur unbrauchbar aussieht, kommt der Name allein in die Liste.
3. **`jedi` löst `spotlab` in der Umgebung der GUI auf.** Falls nicht, bleibt es beim
   Unterbau — genau dafür ist er da.

---

## 11 Abhängigkeiten

| Paket | Wo | Pflicht |
|---|---|---|
| `pygments>=2.17` | Extra `[gui]` | ja, für die Hervorhebung |
| `jedi>=0.19` | Extra `[gui]` | nein, Rückfall vorhanden und geprüft |

Der Kern (`pip install spotlab` ohne Extras) bekommt **keine neue Abhängigkeit**.
`spotlab.editor` benutzt nur die Standardbibliothek.
