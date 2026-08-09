# Beobachter-Modus — leaseloses Mitschreiben für die Kalibrierung

Stand 09.08.2026. Stufe 8.

## Zweck

Echte Kalibrierdaten vom Schul-Spot sammeln, **bevor** Abnahmepunkt A1
(Not-Aus-Koexistenz) durch ist.

Heute kann spotlab nur messen, während es selbst kommandiert — `gates_real.py`
fährt den Roboter und protokolliert dabei. Das setzt Lease und
E-Stop-Endpunkt voraus und steht damit hinter dem Sperrpunkt. Ein Beobachter,
der ausschliesslich `RobotState` liest, braucht beides nicht: er nimmt dem
Tablet nichts weg und kann den Roboter nicht bewegen. Die Kartenaufzeichnung
(`maps/session.py`) macht das seit Stufe 4 vor und begründet es aus dem
SDK-README.

Damit lässt sich die Messkampagne von der Not-Aus-Abnahme entkoppeln: ein
Mensch fährt mit dem Tablet, spotlab schreibt mit.

## Abgrenzung

**In diesem Entwurf:** die Aufzeichnung, der geführte Terminal-Ablauf und ein
Protokoll in demselben Format, das `gates_real.py` schreibt.

**Ausdrücklich danach, als eigener kleiner Schritt:** der Vergleich gegen den
Sim über die neue x-Achse. Er berührt nur `matura-spot/scripts/vergleich_real_sim.py`
und lässt sich sauber trennen. Das Protokollformat wird hier bereits so
entworfen, dass es passt.

**Nicht gebaut:** kein `spotlab beobachten`-Unterbefehl. Das Drehbuch lebt in
matura-spot, der Terminal-Ablauf ist dort ein Skript. Ein generischer Befehl
ohne Drehbuch hätte heute keinen Nutzer.

## Was der Beobachter NICHT leisten kann

Ehrlich vorweg, damit niemand später enttäuscht wird:

- **G5 und G7 fallen weg.** Bremsweg nach Kommando-Ablauf und Command-Timeout
  setzen zwingend voraus, dass spotlab selbst kommandiert. Leaselos unmöglich.
  Sie bleiben `gates_real.py` vorbehalten, also der Zeit nach A1.
- **Es gibt keinen Sollwert.** `tracking_prozent` ist für jede
  Beobachtungsmessung bedeutungslos. Siehe „Die neue x-Achse".
- **Die Reglerstellung ist nicht rücklesbar.** `swing_height` und
  `locomotion_hint` stehen nicht im `RobotState` (geprüft an bosdyn-client
  5.0.1.2). Was am Tablet eingestellt war, muss der Bediener ansagen.
- **Der Sim kann keine Treppe.** Nur ebener, homogener Untergrund — eine
  dokumentierte Grenze der Simulation. Treppendaten sind ein Realitätsprotokoll
  ohne Vergleichspartner.

## Architektur

spotlab misst, matura-spot entscheidet. Der Mechanismus ist
Produktinfrastruktur, das Drehbuch ist Forschung — dieselbe Trennung wie bei
den Realismus-Gates, und aus demselben Grund: die Wahl der Abschnitte und
Tempobänder sind RESEARCH DECISIONs und gehören dorthin, wo dieses Protokoll
gilt.

```
spotlab/src/spotlab/
  record/messfenster.py     NEU   Messfenster-Protokoll, aus api/spot.py herausgelöst
  record/sampler.py         ▲     Ringpuffer der letzten Abtastungen
  beobachtung/quelle.py     NEU   Nur-Lese-Zustandsquelle
  beobachtung/session.py    NEU   Beobachtung: verbinden, aufzeichnen, Tempo melden
  api/spot.py               ▲     messfenster delegiert an record/messfenster.py

matura-spot/scripts/
  beobachten_real.py        NEU   das Drehbuch
```

**Abhängigkeitsrichtung.** `beobachtung/` benutzt `backends/real/verbindung.py`,
`record/` und `errors/`. **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb
von `beobachtung/`** — dieselbe harte Regel wie bei `maps/`, und sie ist der
ganze Grund, warum das Werkzeug vor A1 benutzbar ist. Ein Test hält sie über die
Importzeilen fest (nicht über Docstrings — das war schon zweimal ein Fehlalarm).

## Bausteine

### `record/messfenster.py`

Herausgelöst aus `api/spot.py::messfenster`. Die Logik hängt nur an Recorder und
Abtaster, nicht am Roboter: Ereignis „start" schreiben, Rate hochsetzen,
`try/finally`, Rate zurücksetzen, Ereignis „ende", Verschachtelung verbieten.

```python
RESERVIERT = ("phase", "hz_soll")

class Messfenster:
    def __init__(self, recorder, sampler): ...

    @contextlib.contextmanager
    def oeffne(self, name, hz=50.0, reich=True, **felder): ...
```

`recorder` und `sampler` dürfen `None` sein — bestehende Tests bauen `Spot` so.

`Spot.messfenster(name, hz=50.0, **felder)` behält seine Signatur und delegiert.
**Die 735 bestehenden Tests dürfen von der Verschiebung nichts merken.** Eine
Definition, damit `messung/fenster.py` nicht bald zwei leicht verschiedene
Fensterprotokolle lesen muss.

### `beobachtung/quelle.py`

Der Kern der Sicherheitsaussage.

```python
class Zustandsquelle:
    def __init__(self, state_client): ...
    def robot_state(self):
        return self._state.get_robot_state()
```

Mehr nicht. `StateSampler` braucht nichts anderes. Es gibt **keine
Kommando-Methode, die man versehentlich aufrufen könnte** — stärker als eine
Capability-Prüfung, die erst zur Laufzeit wirft. Ein Test prüft die öffentliche
Oberfläche der Klasse gegen eine Sperrliste (`send_command`, `power_on`,
`walk`, …).

### `record/sampler.py` — Ringpuffer

`StateSampler` bekommt einen begrenzten Ring der zuletzt geschriebenen
Abtastungen (`maxlen=512`) und eine Methode `verlauf()`, die eine Kopie liefert.

Warum im Abtaster und nicht daneben: er hat den Datenstrom ohnehin. Ein zweiter
Abfragestrom nebenher würde die Messung stören und wäre eine zweite Wahrheit
über denselben Roboter.

Der Ring ist nach ANZAHL begrenzt, ausgewertet wird nach ZEIT (siehe unten).
Sonst hinge die Fensterlänge an der gerade eingestellten Rate.

### `beobachtung/session.py`

```python
with Beobachtung.connect(cfg, runs_dir) as b:
    with b.messfenster("B2-Fahrt", hz=50.0, ziel_m_s=0.12, regler="MEDIUM"):
        ...
    b.tempo()        # float m/s oder None
    b.drehrate()     # float rad/s oder None
    b.zustand()      # letzte Abtastung als dict oder None
```

`connect(cfg, runs_dir=None, verbinder=None)` macht `verbinde()` →
`RobotStateClient` → `Zustandsquelle` → `RunRecorder` → `StateSampler`.

`trocken(runs_dir=None)` nimmt `DryRunBackend` als Zustandsquelle — die hat
`robot_state()` bereits und liefert plausible Kalibrierfelder. Damit läuft das
ganze Drehbuch ohne Roboter durch.

Der Austritt stoppt garantiert den Abtaster und schliesst den Lauf ab, in
derselben verschachtelten `finally`-Kette wie `spotlab.connect()` seit S1.6:

```python
recorder.abbau_beginnt()
try:
    sampler.stop()
finally:
    recorder.finish(ergebnis, fehlertext)
```

Ein Strg-C mitten in der Sitzung hinterlässt damit keinen halben Lauf.

`lauf.json` trägt `backend: "beobachter"`. Jede spätere Auswertung muss sehen
können, dass hier **niemand kommandiert hat**.

**`SPOTLAB_NUR_TROCKEN` gilt automatisch**, weil die Schranke seit S1.4 in
`verbinde()` sitzt. Ein Agent kann keinen Beobachter auf den echten Roboter
loslassen. `trocken()` ist davon nicht betroffen und soll es auch nicht sein.

## Die neue x-Achse: erreichtes statt kommandiertes Tempo

G2/G3/G4 sind heute Kennlinien über den **kommandierten** Sollwert. Bei
Tablet-Fahrt gibt es keinen.

Der Ersatz macht den Vergleich sogar besser: statt `v_cmd → v_ach` vergleichen
wir `v_ach → Schrittgeometrie`. Also: *wenn der echte Spot 0.17 m/s fährt, macht
er dann dieselben Schritte wie der Sim bei 0.17 m/s?* Der Sollwert fällt heraus
— und mit ihm der bekannte 20-%-Tracking-Rückstand, der jeden Vergleich über
`v_cmd` verzerrt. Genau diese Frage sollte der Schritt-Block beantworten.

### Definition der Live-Zahl

Drei Festlegungen, damit die Anzeige und die Auswertung dieselbe Grösse meinen:

1. **Zeitbasis `t_robot`**, nicht die Empfangszeit. Projektregel: für Abstände
   innerhalb eines Laufs zählt die Roboteruhr; die Latenz gehört nicht in eine
   Geschwindigkeit hinein.
2. **Zeitfenster 2,0 s**, aus dem Ring nach Zeitstempel ausgewählt — damit ist
   die Zahl unabhängig von der eingestellten Abtastrate. Unter 4 Abtastungen im
   Fenster: `None` statt einer Zahl.
3. **Betrag, nicht x-Komponente:** `hypot(dx, dy) / dt`. Der Sim misst
   `dp[0]/dt` entlang seiner Fahrtrichtung; beim Tablet-Fahren liegt die
   Fahrtrichtung nicht auf der odom-x-Achse.

Aus (3) folgt eine Anforderung an das Drehbuch: **beide Zahlen sind nur bei
Geradeausfahrt dasselbe.** „Geradeaus, nicht lenken" steht deshalb ausdrücklich
in jedem Fahrt-Abschnitt.

`drehrate()` rechnet aus dem **aufsummierten** Gierwinkel über denselben Ring.
Eine Endwert-Differenz mit ±π-Umschlag wäre derselbe Fehler, den matura-spot
bei `_Monitor` schon einmal gemacht hat: eine Drehung von 2π+x erschiene als x.

## Das Drehbuch

`matura-spot/scripts/beobachten_real.py`, aufgebaut wie `gates_real.py`:
Konstanten oben als RESEARCH DECISION markiert, `_frage()` vor jedem Abschnitt,
Trockenprobe mit Zeitraffer eingebaut.

**Bedienung: zwei Personen.** Eine am Tablet, eine am Laptop. Der
Laptop-Mensch liest vor, drückt Enter und beobachtet die Live-Anzeige. Kein
Countdown, kein nicht-blockierendes `stdin` — der Hauptthread wartet auf Enter,
ein Hintergrund-Thread schreibt zweimal pro Sekunde die Live-Zeile.

| Abschnitt | spiegelt | Bediener | Freiraum |
|---|---|---|---|
| B1 Stand, 30 s | G1 | nur Laptop | keiner |
| B2 Fahrt, 4 Bänder | G2/G3 | Tablet, geradeaus | siehe unten |
| B3 Drehen, 2 Bänder | G4 | Tablet, auf der Stelle | ringsum |
| B4 Stoss lateral + longitudinal | G6 | Hand, Impuls eintippen | keiner |
| B5 Sensorik im Stand | Teil von G8 | nur Laptop | keiner |
| B6 Treppe *(optional)* | **nichts** | Tablet | Treppe |

### Die Tempobänder sind gemessen, nicht geraten

Der Sim erreicht bei den Sollwerten 0.1/0.2/0.3/0.4/0.5 m/s tatsächlich
**0.051 / 0.115 / 0.165 / 0.213 / 0.213** m/s (Trab, 8-s-Fenster nach 10 s
Warmlauf). Die Bänder liegen deshalb bei **0.05 / 0.12 / 0.17 / 0.21 m/s**,
Toleranz ±0.02. Ausserhalb davon hat die reale Zahl keinen Sim-Partner.

Das ist der eigentliche Gewinn der neuen x-Achse: wir wissen **vorher**, welche
Fragen der Sim überhaupt beantworten kann.

Für B3 analog: der Sim trackt 111 % bzw. 103 % bei 0.2/0.3 rad/s, erreicht also
rund **0.22 und 0.31 rad/s**.

Die Zahlen stammen aus einem Lauf auf uncommittetem Stand (Lauf-ID trug
`-dirty`) und sind damit **nicht zitierfähig**. Vor der ersten echten
Messfahrt gehört ein Baseline-Lauf gefahren und die Bänder daran bestätigt.

### Pro Abschnitt

- **Reglerstellung abfragen** (Gangart, `swing_height`), vorbelegt mit der
  letzten Antwort, Enter übernimmt. Ohne das wüsste hinterher niemand, unter
  welcher Einstellung eine Schrittlänge entstanden ist.
- **Freiraum ansagen**, wie `gates_real.py` es für die Gates tut.
- **Messfenster öffnen**, Live-Anzeige starten, auf Enter warten, Fenster
  schliessen.
- Bei B4 zusätzlich den Impuls in N·s abfragen — das Skript erfindet ihn nicht.

## Protokollformat

`out/beobachtung/<lauf-id>/protokoll_beobachtung.json`. Fensterebene und
Messwerte sind **identisch** zu `protokoll_real.json` — dieselben Schlüssel
`hz_soll`, `hz_ist`, `abtastungen`, `zeitquelle`, `messwerte`, weil beide aus
`messung/fenster.py::als_json` kommen.

Die oberste Ebene heisst bewusst **`abschnitte` statt `gates`**: ein
Beobachtungsabschnitt IST kein Gate, er spiegelt nur eines. Welches, steht in
`spiegelt`. Der spätere Vergleich bildet darüber ab; ihn zu täuschen, indem man
den Schlüssel gleich benennt, wäre die schlechtere Lösung — dann läse
`vergleiche()` Beobachtungsdaten als kommandierte Messung.

Zweiter Unterschied, den der Vergleich später auflösen muss: `gates_real.py`
legt die Fensterfelder unter `stuetzstelle` ab und findet dort einen echten
Sollwert (`stuetzstelle["stuetzstelle"]`). Hier steht an derselben Stelle
`ziel_m_s` — eine Absicht. Der Vergleich muss die Zuordnung deshalb über das
ERREICHTE Tempo machen, nicht über diesen Wert.

```json
{
  "lauf_id": "...",
  "umgebung": {"quelle": "beobachtung", "kommandiert": false, "spotlab_version": "..."},
  "abschnitte": [
    {"id": "B2", "spiegelt": "G3", "titel": "Fahrt",
     "fenster": [{"stuetzstelle": {"ziel_m_s": "0.12", "regler": "MEDIUM"},
                  "hz_soll": 50.0, "hz_ist": 49.7, "abtastungen": 400,
                  "zeitquelle": "robot", "messwerte": { ... }}]}
  ]
}
```

`kommandiert: false` ist das entscheidende Feld. `ziel_m_s` ist eine **Absicht,
kein Sollwert** — der Name sagt das, und die Auswertung darf daraus kein
Tracking rechnen.

## Fehlerbehandlung

- Netzabbruch während einer Sitzung: der Abtaster fängt Ausnahmen bereits ab und
  läuft weiter (`sampler.py:82`). Die Live-Anzeige zeigt dann `—` statt einer
  Zahl, statt eine alte Zahl stehenzulassen.
- Abbruch mit Strg-C: geht durch die `finally`-Kette, Lauf wird abgeschlossen.
- Ein Abschnitt lässt sich mit `n` überspringen, die ganze Sitzung mit `x`
  abbrechen — wie bei `gates_real.py`. Das Protokoll wird trotzdem geschrieben,
  mit den bis dahin gefahrenen Abschnitten.
- Das Protokoll wird **nach jedem Abschnitt** zwischengespeichert, nicht erst am
  Ende. Ein Abbruch darf die von Hand eingetippten Impulse nicht vernichten —
  derselbe Fehler steckt heute noch in `gates_real.py` (Befund S3.1).

## Tests

- **Regression:** die bestehenden `messfenster`-Tests bleiben unverändert grün;
  ein neuer Test prüft, dass `Spot.messfenster` an `record/messfenster.py`
  delegiert.
- **Sicherheit:** `Zustandsquelle` hat keine Methode aus der Sperrliste
  (Introspektion). Schichtregel: kein Lease-/E-Stop-Import unter `beobachtung/`,
  geprüft über Importzeilen.
- **Lebenszyklus:** Abtaster gestoppt und Lauf abgeschlossen — auch bei
  Ausnahme und bei `KeyboardInterrupt`.
- **`tempo()`:** synthetische Abtastungen mit bekanntem Weg ergeben die bekannte
  Zahl; Auswahl nach Zeit ist ratenunabhängig; `None` bei zu wenigen Punkten;
  Betrag statt x-Komponente bei Schrägfahrt.
- **`drehrate()`:** 2,5 Umdrehungen ergeben 2,5 Umdrehungen, nicht den Rest
  modulo 2π.
- **Trockenprobe:** ein Unterprozess-Test startet `beobachten_real.py`
  tatsächlich und fährt das ganze Drehbuch im Zeitraffer durch. Attrappen-Tests
  prüfen nur, dass die richtigen Argumente gebaut werden.

## Abnahme

Neuer Punkt **A19 — Beobachtungssitzung** in `docs/ABNAHME.md`:

1. Sitzung starten, ohne dass ein Lease geholt wird — `spotlab lease` von einem
   zweiten Rechner muss weiterhin `frei` melden, und `spotlab doctor` darf
   **keinen** `spotlab`-Endpunkt finden. Das ist der Beweis der Leaselosigkeit.
2. Mit dem Tablet fahren; die Live-Anzeige muss aus zwei Metern lesbar sein und
   der Zahl folgen, die hinterher im Protokoll steht.
3. Ein Band gezielt treffen: Anzeige 0.17 ± 0.02 halten, danach prüfen, ob
   `messwerte` denselben Wert ausweist.
4. Strg-C mitten in einem Abschnitt: Lauf sauber abgeschlossen, Protokoll
   vorhanden.

Die **Lesbarkeit der Live-Anzeige** kann offscreen nicht beurteilt werden und
ist deshalb Abnahmestoff, kein Test.

## Offene RESEARCH DECISIONs (für matura-spot)

1. **Bänder bestätigen.** Die vier Tempobänder stammen aus einem nicht
   zitierfähigen Lauf. Vor der Messfahrt einen Baseline-Lauf fahren.
2. **B6 Treppe: ja oder nein?** Sie liefert kein Vergleichspaar. Aufwand null,
   Aussagewert für den Abschnitt „bekannte Grenzen der Simulation".
3. **Wiederholungen je Band.** Eine Fahrt je Band reicht für einen Mittelwert,
   nicht für eine Streuung. Drei verdreifachen die Hallenzeit.
