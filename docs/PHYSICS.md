# Physikmodus: erste Integration

Entscheidung des Autors im Chat: zusätzlicher Physikmodus auf Basis des bestehenden
SpotSdkSim, zunächst Stand/Gehen/Stopp, danach einzelne Stufen und Treppen.
Dies ergänzt die Wiedergabe-Entscheidung vom 06.09.2026. Die bestehenden
Forschungsregler, Messreihen, Raumrekonstruktion und Wiedergabe bleiben unverändert.

## Start

Im Code-Fenster unter „Wo läuft es?“ **Physik 3D (experimentell)**
wählen. Für ebenen Boden einen Raum ohne Höhenflächen/Gelände/Sperrzonen verwenden.
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
- Kommandofristen werden aus lokaler Zeit in Simulationszeit übersetzt und auch
  bei langsamer Simulation gegen die Wanduhr geprüft.
- Gelenke, Geschwindigkeiten und Fußkontakte kommen aus dem Physikzustand.
- Sensorbilder und LocalGrid verwenden die bestehende Sensor-Pipeline. Aufträge
  werden im Physik-Worker verarbeitet; teure Bilder können Echtzeit verlangsamen.

## Grenzen dieser Version

**Kein realitätsgetreuer Treppenlauf fertiggestellt.** Der vorhandene Regler plant
Schwungziele auf einer festen Fußbodenhöhe. Ein separater TerrainStepper ergänzt
jetzt kleine Podeste. Andere Höhenflächen und Treppen werden weiterhin abgelehnt.

Unterstützt: stand() in Neutralhöhe, walk() mit HINT_AUTO/HINT_TROT, stop(), State,
Tiefen-/Graukameras, LocalGrid obstacle_distance und GUI-Livebild.
Noch nicht unterstützt: sit(), move()-Zieltrajektorien, Körperpose, frei konfigurierbarer Kriechgang,
WorldObjects/Tags, GraphNav und Treppen. UnsupportedCapability benennt die Grenze.
Die grobe Capability POSTURE/LOCOMOTION garantiert nicht sämtliche Einzelbefehle.

Die Adaptergrenzen betragen vorerst 0.30 m/s und 0.50 rad/s; Begrenzungen werden
protokolliert. Das sind Versuchsgrenzen dieses Reglers, keine Eigenschaften des
realen Spot. Geschwindigkeits-Tracking und Anfahren weichen ab. Ein Sturz stoppt
den Versuch mit Fehler. Der Modell-Massenwert steht im Laufbericht; er wird nicht
heimlich an reale Messwerte angepasst. Nicht als Sim-zu-Real-Nachweis verwenden.

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
