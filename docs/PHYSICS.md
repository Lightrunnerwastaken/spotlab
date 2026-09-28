# Physikmodus: erste Integration

Entscheidung des Autors im Chat: zusätzlicher Physikmodus auf Basis des bestehenden
SpotSdkSim, zunächst Stand/Gehen/Stopp, danach einzelne Stufen und Treppen.
Dies ergänzt die Wiedergabe-Entscheidung vom 06.09.2026. Die bestehenden
Forschungsregler, Messreihen, Raumrekonstruktion und Wiedergabe bleiben unverändert.

## Start

Im Code-Fenster unter „Wo läuft es?“ **Physik 3D** wählen, oder im Tab „Fahren“ den Ort
**⚙ 3D-Physik**. Ebene Räume mit Wänden, Blöcken, Tags und Sperrzonen gehen; welche Räume,
entscheidet `welt/physik.py::tauglich` — vor dem Start, im Tab und im Backend dieselbe Regel.
Neu: Die Szene `physik_einzelstufe` unterstützt einen begrenzten 6-cm-Podestversuch.
Neue Vorlage: `physik_gehen.py` (erscheint beim nächsten GUI-Start).

```python
from spotlab import connect

with connect(backend="physics") as spot:
    spot.power_on()
    spot.stand()
    spot.walk(vx=0.15, duration=8)
    spot.stop()
```

Der Simulator beginnt in der bereits stehenden home-Pose. `power_on/off` schaltet
in dieser ersten Version die virtuelle Kommandofreigabe, nicht eine simulierte
Motor-Elektronik. `stand()` prüft das Zur-Ruhe-Kommen; es simuliert noch keinen
Aufstehvorgang vom Boden. Der Körper bleibt physikalisch von den Beinen getragen.

## Was tatsächlich anders ist

- Dynamik über `mj_step`, Gewicht, Trägheit, Aktuatoren und Kontaktkräfte.
- Fußaufsetzplanung durch den vorhandenen TrotController; keine abgespielten
  Gelenkkurven und keine gesetzte Körperposition während des Laufs.
- Einmalige Startpose (GUI-Winkel in Grad); danach schreibt nur die Physik die Basis.
- Eigener Worker, unabhängig von GUI und Sensor-Abfragehäufigkeit. Der Renderer
  verwendet private MjData und Kopien des berechneten Zustands.
- Fester MuJoCo-Zeitschritt. Ist der Rechner zu langsam, läuft die Simulation
  langsamer; es werden keine Physikschritte übersprungen, um Echtzeit vorzutäuschen.
- Kommandofristen laufen auf `backend.uhr()`: in Echtzeit (GUI, `connect()`) die
  Wanduhr — die Frist wird in Simulationszeit übersetzt und auch bei langsamer
  Simulation gegen die Wanduhr geprüft, wie am Roboter. Ohne Echtzeit
  (`realtime=False`, `advance()`) die Sim-Zeit ab `SIM_UHR_NULL` (1 000 000 s): eine
  Wanduhr mäße dort die Rechnerlast — dieselbe Tastaturfahrt stürzte unter Last bei
  115 s und lief einzeln durch (24.09.2026). `motion.walk`/`move` nehmen diese Uhr
  von selbst; eine Endzeit aus `time.time()` wird ohne Echtzeit abgewiesen.
- Gelenke, Geschwindigkeiten und Fußkontakte kommen aus dem Physikzustand.
- Sensorbilder und LocalGrid verwenden die bestehende Sensor-Pipeline. Aufträge
  werden im Physik-Worker verarbeitet; teure Bilder können Echtzeit verlangsamen.

## Grenzen dieser Version

**Kein realitätsgetreuer Treppenlauf fertiggestellt.** Der vorhandene Regler plant
Schwungziele auf einer festen Fußbodenhöhe. Ein separater TerrainStepper ergänzt
jetzt kleine Podeste. Andere Höhenflächen und Treppen werden weiterhin abgelehnt.

Unterstützt: Sitzen und Aufstehen, stand() mit Körperhaltung (pose), walk() mit
HINT_AUTO/HINT_TROT, move(), stop(), State, Tiefen-/Graukameras, LocalGrid
obstacle_distance, AprilTags über world_objects()/tags(), Sperrzonen und GUI-Livebild
(Stufen A und B, 28.09.2026, siehe unten; ohne spotsim-Haltung hält sit() nur an).
Noch nicht unterstützt: frei konfigurierbarer Kriechgang, GraphNav, Rampen, Gelände und
Treppen. UnsupportedCapability benennt die Grenze.
Die grobe Capability POSTURE/LOCOMOTION garantiert nicht sämtliche Einzelbefehle.

Die Tempogrenzen kommen aus `spotsim.tempo_grenzen()` (Kraftregler 0.85 m/s und
1.0 rad/s, Trab 0.3 / 0.5); Begrenzungen werden protokolliert. Das sind Grenzen dieses
Reglers, keine Eigenschaften des realen Spot. Geschwindigkeits-Tracking und Anfahren weichen ab. Ein Sturz stoppt
den Versuch mit Fehler. Der Modell-Massenwert steht im Laufbericht; der Adapter passt ihn nie an.
Seit 0.2.0b5 ist das Modell aus matura-spot das GEMESSENE (33.2 kg statt 50.34 kg,
offen entschieden, siehe unten „Gemessenes Modell“). Nicht als Sim-zu-Real-Nachweis
verwenden.

Der Übergang vom Trab zum Stand benutzt den vorhandenen Brems-/Absetzablauf
(maximal 4 s Simulationszeit). Neue Bewegungsbefehle während dieses Übergangs
werden erst nach dem Übergang wirksam. Kein Echtzeitversprechen für die GUI.

## Validierung und nächste Entwicklungsstufe

Automatische Prüfungen: Kontaktstand, Fortschritt beim Gehen, Stillstand nach
Stopp, Kommandoablauf bei langsamer Sim-Uhr, getrennte Zustandsabfragen, Startwinkel,
Worker-Abbau und ausdrücklich abgelehnte Funktionen. Zusätzlich gerenderte
Sequenz Stand → Geradeaus → Stopp visuell prüfen.

Für die nächste Stufe nötig:
1. Lokale Höhen-/Kontaktabfrage pro Fuß und erreichbare Aufsetzflächen.
2. Schwungtrajektorie über Stufenkanten sowie Landung anhand realer Sim-Kontakte.
3. Stützbein-/Körperplanung bei unterschiedlichen Fußhöhen.
4. Einzelstufe auf/ab, anschließend vollständige Treppe; Fußdurchdringung,
   Schlupf, Neigung, Sturz und Tracking messen, jeweils als Clip prüfen.
5. Abgleich mit denselben Manövern aus realen Aufnahmen.

Diese Stufe verändert den Forschungsregler und braucht eigene Tests und ein
protokolliertes Validierungsergebnis. Die bisherige GUI-Wiedergabe heißt nun
„Übungsraum 3D (Wiedergabe)“, damit beide Modelle unterscheidbar bleiben.


## Neuer Einzelstufenversuch (08.09.2026)

Im GUI den Raum **physik_einzelstufe**, Start **(0, 0, 0)** und das Beispiel
**physik_einzelstufe.py** wählen. Mehrere Minuten einplanen. Die Vorlagen erscheinen
beim nächsten GUI-Start. Das Beispiel fährt positionsabhängig vorwärts auf das
6-cm-Podest und rückwärts herunter.

Der separate TerrainStepper verlagert das Gewicht auf drei Stützbeine, sucht
Fußflächen, hebt das Schwungbein über die Kante und bestätigt die Landung durch
Sim-Kontakte. Während der Bewegung werden nur Gelenkziele gesetzt; die freie
Basis wird durch MuJoCo integriert. Die bisherigen Forschungsregler bleiben erhalten.

Grenzen: eine horizontale, ungedrehte Plattform bis 6 cm, mindestens 0.8 × 1 m;
validiert ist die mitgelieferte Szene. Start-Yaw 0, reine x-Bewegung, maximal
0.02 m/s Sollgeschwindigkeit. Drehen, Seitwärtsfahrt, höhere Stufen, Rampen,
mehrere Ebenen und Vorwärtsabstieg sind gesperrt. `stairs()` bleibt unsupported.
**Stopp und Kommandoablauf beenden zuerst den laufenden Fußschritt**, was mehrere
Sekunden dauern kann. Der Kriechgang erreicht die Sollgeschwindigkeit nicht
verlässlich. Die Fußplanung kennt die statische Szene direkt (**scene oracle**);
sie arbeitet noch nicht aus Tiefenbildern oder LocalGrid-Rekonstruktionen.

56 Schritte mit allen vier Füßen hinauf und rückwärts herunter bestanden ohne
Sturz in 215.91 s Simulationszeit. Max. Roll/Nick: 9.61°/3.67°, Aufsetzfehler
5.93 mm, kleinster gemessener Stützrandabstand 31.85 mm. Keine gemessene
Beindurchdringung während der mittleren 25–75 % des Schwungs.
**Unter Last bleiben bis zu 13.55 mm Fußpenetration und 29.26 mm Stützfußschlupf.**
Das sind offene Modell-/Reglerprobleme, keine realistischen Toleranzen.
Die Robotermasse im Bericht beträgt 50.34 kg ohne statische Raumobjekte.

Tests prüfen Höhenabfragen ohne Zustandsänderung, Stützflächenplanung, den ganzen
Auf-/Abstieg, die SDK-Anbindung, Stopp und abgelehnte Bewegungen. Kein Nachweis
für vollständige Treppen oder Sim-zu-Real. Nächster Schritt: Kontaktpenetration
und Schlupf reduzieren, weitere Geometrien prüfen, dann mehrere Stufen und
sensorbasierte Fußplanung. Realitätsaussagen brauchen reale Vergleichsfahrten.


### Aktualisierung: kürzere Wartephasen

Der gleiche 56-Schritt-Versuch benötigt jetzt 195.08 statt 215.91 Sekunden
(9.65 % kürzer). Nur die Pause nach Gewichtsverlagerungen wurde von 0.4 auf
0.2 s verkürzt. Eine schnellere Verlagerung wurde wegen negativer Stützreserve
verworfen. Neue Werte: Stützrand mindestens 30.27 mm, Schlupf maximal 30.47 mm,
Fußpenetration maximal 13.37 mm. Weiterhin ein langsamer experimenteller
Kriechgang. Keine allgemeine Verbesserung der Kontaktqualität nachgewiesen.


## Kontakt-Diagnostik und Korrektur der Interpretation

Die bisherige `max_stance_slip_m` misst den planaren Versatz eines Fusszentrums,
nicht reines Gleiten am Kontaktpunkt. Bei kugelförmigen Füssen kann darin Rollen
enthalten sein. `max_loaded_foot_penetration_m` erfasste zudem nur das jeweils
bewegte Bein während dessen Schwung und ist KEIN Maximum über alle Füsse/Phasen.
Beide historischen Felder bleiben für den Vergleich unverändert.

Neu: `contact_diagnostics` im Forschungsbericht bzw. `kontakt_diagnostik` in
Spotlabs `lauf.json`, getrennt nach Verlagern, Warten und Schwingen:
- Eindringtiefe aller Füsse gegen statische, tragende Flächen;
- maximale Normalkraft;
- maximale tangentiale Geschwindigkeit am Kontaktpunkt bei mindestens 5 N Last.
Die Kontaktpunktgeschwindigkeit berücksichtigt Translation UND Rotation des
Fusskörpers. Eine ideal rollende Kugel hat damit null Gleitgeschwindigkeit.
Abtastung am Regeltakt (hier 10 ms), keine lückenlose Kontinuums-Messung.
Geschwindigkeitsspitzen können vom Aufsetzen kommen und sind keine mittlere
Gleitgeschwindigkeit oder kumulierte Gleitstrecke.

Gleicher 195.08-s-Versuch, exakt identischer gespeicherter qpos-/Zeit-Verlauf:
max. Penetration Verlagern 17.34 mm, Warten 16.45 mm, Schwung 16.18 mm;
max. belastete Tangentialgeschwindigkeit 0.297 / 0.0185 / 0.136 m/s.
Die neue Messung deckt bisher nicht erfasste Spitzen auf. Sie verbessert weder
Geschwindigkeit noch Kontaktmodell und wird nicht als Realismusgewinn verkauft.

Kontrollmessung im ruhigen Stand: 14.56 mm Penetration, ca. 124 N maximale
Normalkraft je Kontakt. Das Asset verwendet `solimp=[0.015,1,0.036,0.5,2]`.
MuJoCo erlaubt damit weiche Kontaktlagen; Eindringtiefe allein beweist keinen
Solverfehler. Siehe [MuJoCo-Kontaktmodell](https://mujoco.readthedocs.io/en/3.6.0/modeling.html#solver-parameters).
Ohne Messung der realen Fussnachgiebigkeit ist ein härterer Kontakt noch kein
belegter realistischerer Kontakt. Masse, Reibung und Solverparameter unverändert.

Die Landeprüfung akzeptiert jetzt nur tragende Kontakte zur statischen Welt,
keine Selbstkontakte zu anderen Roboterbeinen. Tests prüfen Rollen vs. Gleiten,
Selbstkontakt-/Wand-Ausschluss und unveränderten Physikzustand bei Diagnose.
Eine versuchte Beibehaltung horizontaler Fussanker statt Neumessung wurde wegen
Sturz beim Abstieg nach 127.92 s verworfen. Der funktionierende Regler bleibt.


## Koordinierte Schrittfolge und Versuchstreppe

Neu: **physik_treppe_3stufen.py** mit Raum **physik_treppe_3stufen** im Modus
**Physik 3D**, Start **(0,0,0)**. Drei Stufen à 4 cm, Auftritt 40 cm, dann ein
Podest. Etwa 7–12 Minuten einplanen; alle 5 s erscheint der Positionsfortschritt.
Der Regler verlagert nach einer Landung nur noch zu 90 % zurück zur Mitte.
Im alten Podesttest sinkt dadurch die Dauer von 195.08 auf 191.25 s, der
Stützfußversatz von 30.47 auf 28.73 mm und die maximale Verlagerungs-Kontaktkraft
von 306.59 auf 278.45 N. Das bleibt ein langsamer Gang mit einzelnen Schritten.

Der Drei-Stufen-Versuch besteht 120 Schritte in 411.10 s, alle vier Füße hinauf
und rückwärts herunter, kein Sturz, mindestens 31.61 mm Stützrand. Zwei 3-cm-
Stufen funktionieren ebenfalls im Forschungsversuch. Bereits 2 cm Startversatz
verfehlen dort aber knapp die 30-mm-Schwelle (29.95 mm). Deshalb nur die genaue
Drei-Stufen-Vorlage zusätzlich freigegeben; normale Treppen bleiben gesperrt.
Weiterhin Geometrie-Oracle, keine Wahrnehmungsplanung oder Realismusfreigabe.


## Gemessenes Modell (23.09.2026, ab 0.2.0b5)

Das Menagerie-Modell trug im Rumpf die Masse des ganzen Roboters: **50.34 kg**
statt rund 33 kg, dazu eine Platzhalter-Trägheit und eine zu tiefe Standhaltung.
Gemessen am Schul-Spot (Gelenkmomente im ruhigen Stand, 5045 Proben aus 62 Läufen):
**33.2 kg**, Schwerpunkt 3.8 cm hinter dem Rumpfursprung, Standhöhe 0.5145 m über
dem Fussaufstand. matura-spot hat das Modell mit diesen Werten zur Vorgabe gemacht
(RESEARCH DECISION A, `matura-spot/notes/REALISMUS_GATES.md`, Runde 4); spotlab
übernimmt es mit dem Sim-Wheel, am Adapter ändert sich nichts. Der Laufbericht
nennt weiter `modell_masse_kg` — daran ist zu erkennen, welches Modell lief.

Folgen für die Stufenversuche: der Regler darf den Schwerpunkt jetzt bis 15 statt
13 cm verlagern (mit dem gemessenen Schwerpunkt braucht ein Hinterbein 13.0 cm).
Forschungsversuche in matura-spot mit dem gemessenen Modell: Einzelstufe 56 Schritte
in 194.8 s, Stützrand mindestens 53.1 mm, Stützfussversatz höchstens 11.0 mm
(vorher 33.2 mm und 28.7 mm); drei Stufen 120 Schritte in 417.5 s, Stützrand
54.2 mm, Versatz 11.9 mm (vorher 31.6 und 35.3 mm). Kein Sturz. Der echte Spot
rutscht je Standphase im Median 0.24 mm, höchstens 17 mm (seine eigene Schätzung).

Weiterhin OFFEN und nicht gemessen: Momentgrenzen und Gelenktempo der Aktuatoren,
ihre Steifigkeit, die Fussnachgiebigkeit und die Reibung. Eine Realismusfreigabe
ist das nicht.


## Trab nach Start-Stopp und Gier (24.09.2026)

Geprüft am echten Spot: die `walk`-Folgen von 60 Läufen (Fahren, Folgen) im
Physikkörper nachgespielt (`python -m spotlab.kalibrierung.nachspiel`, dort mit dem
Kinematik-Sim; für die Physik dasselbe Verfahren). Zwei Fehler im Trab von
matura-spot, beide behoben (Runde 5 in `matura-spot/notes/REALISMUS_GATES.md`):
jeder neue Trab-Regler nach einem Stopp erbte ein verdrehtes Fußmuster (Stürze),
und die Standbeine hielten die Gier nicht (Zittern im Gangtakt).

| | echter Spot | vorher | jetzt |
|---|---|---|---|
| Stürze in 15 Folge-Läufen / 37 schnellen Fahrten | 0 / 0 | 8 / 15 | 0 / 0 |
| Gierzittern geradeaus | 0.020 rad/s | 0.184 | 0.022 |
| Verzug Drehen | 0.20 s | 0.40 s | 0.30 s |

Weiter offen: der Trab kappt bei 0.4 m/s und 0.3 rad/s (dieser Adapter bei 0.3 m/s
und 0.5 rad/s) — der echte Spot fährt 0.8 m/s und 1.1 rad/s voll.



## Kraftregler als Vorgabe (24.09.2026)

Der Physikkörper geht seit dem 24.09.2026 mit dem Kraftregler aus matura-spot
(vorausgeplante Fusskräfte, Drehmoment-Aktuatoren mit den Motorgrenzen R1; Entscheid
des Autors, `matura-spot/notes/ENTWURF_kraftregler.md`). Dieser Adapter kappt
Kommandos auf `spotsim.tempo_grenzen()`: 0.85 m/s und 1.0 rad/s, der gemessene
Bereich des echten Spot. `SPOTSIM_REGLER=trab` holt den alten Trab (0.3 m/s,
0.5 rad/s) zurück; ältere gepinnte spotsim-Fassungen behalten 0.3 / 0.5.

Dieselben 60 Läufe nachgespielt, Befehlsfristen auf der Sim-Uhr:

| | echter Spot | Trab | Kraftregler |
|---|---|---|---|
| Stürze | – | 0 | 0 |
| Endwert bei 0.8 m/s / 1.1 rad/s | 101 / 100 % | 31 / 32 % | 98 / 91 % |
| Gierzittern geradeaus | 0.020 rad/s | 0.022 | 0.016 |
| Verzug vx / wz | 0.30 / 0.20 s | 0.30 / 0.30 | 0.20 / 0.20 |
| Nachlauf beim Drehen, 2 s | 0.036 rad | 0.004 | 0.041 |

Echtzeitfaktor in diesem Adapter (`realtime=False`, gemischte Tastaturfolge): Trab
3.1, Kraftregler 2.1 — die GUI kommt mit. Das Gleiten nach innen im schnellen Bogen
(0.12 m/s quer, echt 0.00) ist behoben: das Tempo-Soll steht über den Horizont fest wie
im MIT-Regler (matura-spot `6125cde`; nachgespielt −0.015 statt +0.036 m/s, echt ±0).
Offen: geradeaus 0.04 m/s seitliches Driften (echt 0), und passiv steht er kleinere
Stösse aus als der Trab (G6 22.5 / 45 statt 30 / 60 N·s).

## Normaler Übungsort — Stufe A (28.09.2026)

Entwurf `docs/superpowers/specs/2026-09-28-physik-normal-design.md`. Der Kraftregler aus
matura-spot bleibt unverändert; alles Neue sitzt im Adapter und in `welt/`.

| Was | Wie | Gemessen (`realtime=False`, Sim-Uhr) |
|---|---|---|
| Räume | `welt/physik.py::tauglich` — ebene Räume mit Wänden, Blöcken, Tags, Sperrzonen, dazu die zwei Stufenszenen; sonst ein Grund vor dem Start | Tab, Editor und Backend fragen dieselbe Regel |
| Tags | `SpotPuppe.sichtbare_tags` auf Modell und Zustand der Physik, im Physik-Faden | Tag 2 m voraus gefunden, hinter einer Wand nicht |
| Sperrzonen | `welt.kollision.zone_im_weg` auf den Punkt nach 0.5 s (Bremsweg); nur wenn gemessene UND befohlene Richtung auf die Zone zeigen | Zone ab x = 2.00: Körpermitte hält bei 1.49 (0.3 m/s) bzw. 1.57 (0.85 m/s); rückwärts heraus frei |
| move() | der Takt regelt alle 0.1 s Sim-Zeit zum odom-Ziel (Gehbefehle mit Mindesttempo); angekommen bei 5 cm und 3°, gezählt wenn er steht, bis zu zwei Nachsetzer | 1 m: 4.9 s, 1 Anlauf · 90°: 10.7 s, 3 Anläufe · 0.5 m links + 45°: 9.2 s, 2 Anläufe |
| „steht“ | `RUHE_S` = 0.3 s ohne Bewegung | vorher zählte ein ruhiger Takt mitten im Absetzen; danach rutschte er noch 5 cm |
| sit() | anhalten, einmal „Sitzen kann der Physikmodus noch nicht — Spot bleibt stehen“, Rückmeldung „steht“ | — |

Beim Anhalten setzt der Regler noch Schritte ab und verschiebt den Körper um 2–7 cm; deshalb
zählt bei move() die Lage im Stand, und Drehen auf der Stelle braucht oft alle drei Anläufe.
Das ist eine Eigenschaft dieses Reglers, nicht gemessen am echten Spot. Offen (Stufe B, C):
Sitzen und Aufstehen im Regler, Körperpose, Rampen, Gelände, Treppen.

## Sitzen, Aufstehen, Körperhaltung — Stufe B (28.09.2026)

Entwurf `docs/superpowers/specs/2026-09-28-physik-haltung-design.md`, in matura-spot
`notes/ENTWURF_haltung.md` (H1–H4) und Gate G12. Braucht spotsim mit `HALTUNG_FASSUNG ≥ 1`.

| Was | Wie | Gemessen / Sim |
|---|---|---|
| Start | ebene Räume sitzend, Motoren aus bis `power_on()`; die Stufenszenen stehend | sitzt bei z 0.10 m, Rumpf liegt auf |
| Aufstehen | mittlere Gelenkbahn aus 142 echten `stand()` (spotlab `kalibrierung/haltung.py`), Positions-Sollwert mit Motorgrenzen R1, danach Kraftregler | echt: Hub 0.410 m in 1.00 s; Sim (G12): 0.409 m in 1.12 s; Knie ≤ 47 von 104 Nm |
| Hinsetzen | dieselbe Bahn rückwärts — **Annahme H2** | nicht aufgezeichnet (A41) |
| `power_off()` | erst hinsetzen, dann Motoren aus | wie `power_off(safe=True)` |
| `pose()` | Roll/Nick/Gier und Höhe im Stand als MPC-Ziel, Rampe 1 s — **Annahme H3**; gekappt auf Höhe ±0.15 m, Winkel ±20° (`physik_grenze`) | acht Messposen ≤ 0.7° / 0.25 cm, Rutschen 1 cm; Gier läuft langsamer ein (19.4° nach 2.5 s) |
| Gehen im Sitzen | abgewiesen: „zuerst stand()“ | — |
| Echtzeit | Worker in Echtzeit | Aufstehen 1.37 s Sim in 1.36 s Wanduhr |

Das Schüler-Release trägt seit diesem Tag den Kraftregler, die Haltung und die Messdaten im
Sim-Wheel (`tools/schueler_release.py`); vorher brach sein Bau seit dem 24.09.2026 ab.
