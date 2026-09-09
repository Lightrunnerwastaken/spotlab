# Physikmodus: erste Integration

Entscheidung des Autors im Chat: zusÃƒÂ¤tzlicher Physikmodus auf Basis des bestehenden
SpotSdkSim, zunÃƒÂ¤chst Stand/Gehen/Stopp, danach einzelne Stufen und Treppen.
Dies ergÃƒÂ¤nzt die Wiedergabe-Entscheidung vom 06.09.2026. Die bestehenden
Forschungsregler, Messreihen, Raumrekonstruktion und Wiedergabe bleiben unverÃƒÂ¤ndert.

## Start

Im Code-Fenster unter Ã¢â‚¬Å¾Wo lÃƒÂ¤uft es?Ã¢â‚¬Å“ **Physik 3D (experimentell)**
wÃƒÂ¤hlen. FÃƒÂ¼r ebenen Boden einen Raum ohne HÃƒÂ¶henflÃƒÂ¤chen/GelÃƒÂ¤nde/Sperrzonen verwenden.
Neu: Die Szene `physik_einzelstufe` unterstÃƒÂ¼tzt einen begrenzten 6-cm-Podestversuch.
Neue Vorlage: `physik_gehen.py` (erscheint beim nÃƒÂ¤chsten GUI-Start).

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
Motor-Elektronik. `stand()` prÃƒÂ¼ft das Zur-Ruhe-Kommen; es simuliert noch keinen
Aufstehvorgang vom Boden. Der KÃƒÂ¶rper bleibt physikalisch von den Beinen getragen.

## Was tatsÃƒÂ¤chlich anders ist

- Dynamik ÃƒÂ¼ber `mj_step`, Gewicht, TrÃƒÂ¤gheit, Aktuatoren und KontaktkrÃƒÂ¤fte.
- FuÃƒÅ¸aufsetzplanung durch den vorhandenen TrotController; keine abgespielten
  Gelenkkurven und keine gesetzte KÃƒÂ¶rperposition wÃƒÂ¤hrend des Laufs.
- Einmalige Startpose (GUI-Winkel in Grad); danach schreibt nur die Physik die Basis.
- Eigener Worker, unabhÃƒÂ¤ngig von GUI und Sensor-AbfragehÃƒÂ¤ufigkeit. Der Renderer
  verwendet private MjData und Kopien des berechneten Zustands.
- Fester MuJoCo-Zeitschritt. Ist der Rechner zu langsam, lÃƒÂ¤uft die Simulation
  langsamer; es werden keine Physikschritte ÃƒÂ¼bersprungen, um Echtzeit vorzutÃƒÂ¤uschen.
- Kommandofristen werden aus lokaler Zeit in Simulationszeit ÃƒÂ¼bersetzt und auch
  bei langsamer Simulation gegen die Wanduhr geprÃƒÂ¼ft.
- Gelenke, Geschwindigkeiten und FuÃƒÅ¸kontakte kommen aus dem Physikzustand.
- Sensorbilder und LocalGrid verwenden die bestehende Sensor-Pipeline. AuftrÃƒÂ¤ge
  werden im Physik-Worker verarbeitet; teure Bilder kÃƒÂ¶nnen Echtzeit verlangsamen.

## Grenzen dieser Version

**Kein realitÃƒÂ¤tsgetreuer Treppenlauf fertiggestellt.** Der vorhandene Regler plant
Schwungziele auf einer festen FuÃƒÅ¸bodenhÃƒÂ¶he. Ein separater TerrainStepper ergÃƒÂ¤nzt
jetzt kleine Podeste. Andere HÃƒÂ¶henflÃƒÂ¤chen und Treppen werden weiterhin abgelehnt.

UnterstÃƒÂ¼tzt: stand() in NeutralhÃƒÂ¶he, walk() mit HINT_AUTO/HINT_TROT, stop(), State,
Tiefen-/Graukameras, LocalGrid obstacle_distance und GUI-Livebild.
Noch nicht unterstÃƒÂ¼tzt: sit(), move()-Zieltrajektorien, KÃƒÂ¶rperpose, frei konfigurierbarer Kriechgang,
WorldObjects/Tags, GraphNav und Treppen. UnsupportedCapability benennt die Grenze.
Die grobe Capability POSTURE/LOCOMOTION garantiert nicht sÃƒÂ¤mtliche Einzelbefehle.

Die Adaptergrenzen betragen vorerst 0.30 m/s und 0.50 rad/s; Begrenzungen werden
protokolliert. Das sind Versuchsgrenzen dieses Reglers, keine Eigenschaften des
realen Spot. Geschwindigkeits-Tracking und Anfahren weichen ab. Ein Sturz stoppt
den Versuch mit Fehler. Der Modell-Massenwert steht im Laufbericht; er wird nicht
heimlich an reale Messwerte angepasst. Nicht als Sim-zu-Real-Nachweis verwenden.

Der ÃƒÅ“bergang vom Trab zum Stand benutzt den vorhandenen Brems-/Absetzablauf
(maximal 4 s Simulationszeit). Neue Bewegungsbefehle wÃƒÂ¤hrend dieses ÃƒÅ“bergangs
werden erst nach dem ÃƒÅ“bergang wirksam. Kein Echtzeitversprechen fÃƒÂ¼r die GUI.

## Validierung und nÃƒÂ¤chste Entwicklungsstufe

Automatische PrÃƒÂ¼fungen: Kontaktstand, Fortschritt beim Gehen, Stillstand nach
Stopp, Kommandoablauf bei langsamer Sim-Uhr, getrennte Zustandsabfragen, Startwinkel,
Worker-Abbau und ausdrÃƒÂ¼cklich abgelehnte Funktionen. ZusÃƒÂ¤tzlich gerenderte
Sequenz Stand Ã¢â€ â€™ Geradeaus Ã¢â€ â€™ Stopp visuell prÃƒÂ¼fen.

FÃƒÂ¼r die nÃƒÂ¤chste Stufe nÃƒÂ¶tig:
1. Lokale HÃƒÂ¶hen-/Kontaktabfrage pro FuÃƒÅ¸ und erreichbare AufsetzflÃƒÂ¤chen.
2. Schwungtrajektorie ÃƒÂ¼ber Stufenkanten sowie Landung anhand realer Sim-Kontakte.
3. StÃƒÂ¼tzbein-/KÃƒÂ¶rperplanung bei unterschiedlichen FuÃƒÅ¸hÃƒÂ¶hen.
4. Einzelstufe auf/ab, anschlieÃƒÅ¸end vollstÃƒÂ¤ndige Treppe; FuÃƒÅ¸durchdringung,
   Schlupf, Neigung, Sturz und Tracking messen, jeweils als Clip prÃƒÂ¼fen.
5. Abgleich mit denselben ManÃƒÂ¶vern aus realen Aufnahmen.

Diese Stufe verÃƒÂ¤ndert den Forschungsregler und braucht eigene Tests und ein
protokolliertes Validierungsergebnis. Die bisherige GUI-Wiedergabe heiÃƒÅ¸t nun
Ã¢â‚¬Å¾ÃƒÅ“bungsraum 3D (Wiedergabe)Ã¢â‚¬Å“, damit beide Modelle unterscheidbar bleiben.


## Neuer Einzelstufenversuch (08.09.2026)

Im GUI den Raum **physik_einzelstufe**, Start **(0, 0, 0)** und das Beispiel
**physik_einzelstufe.py** wÃƒÂ¤hlen. Mehrere Minuten einplanen. Die Vorlagen erscheinen
beim nÃƒÂ¤chsten GUI-Start. Das Beispiel fÃƒÂ¤hrt positionsabhÃƒÂ¤ngig vorwÃƒÂ¤rts auf das
6-cm-Podest und rÃƒÂ¼ckwÃƒÂ¤rts herunter.

Der separate TerrainStepper verlagert das Gewicht auf drei StÃƒÂ¼tzbeine, sucht
FuÃƒÅ¸flÃƒÂ¤chen, hebt das Schwungbein ÃƒÂ¼ber die Kante und bestÃƒÂ¤tigt die Landung durch
Sim-Kontakte. WÃƒÂ¤hrend der Bewegung werden nur Gelenkziele gesetzt; die freie
Basis wird durch MuJoCo integriert. Die bisherigen Forschungsregler bleiben erhalten.

Grenzen: eine horizontale, ungedrehte Plattform bis 6 cm, mindestens 0.8 Ãƒâ€” 1 m;
validiert ist die mitgelieferte Szene. Start-Yaw 0, reine x-Bewegung, maximal
0.02 m/s Sollgeschwindigkeit. Drehen, SeitwÃƒÂ¤rtsfahrt, hÃƒÂ¶here Stufen, Rampen,
mehrere Ebenen und VorwÃƒÂ¤rtsabstieg sind gesperrt. `stairs()` bleibt unsupported.
**Stopp und Kommandoablauf beenden zuerst den laufenden FuÃƒÅ¸schritt**, was mehrere
Sekunden dauern kann. Der Kriechgang erreicht die Sollgeschwindigkeit nicht
verlÃƒÂ¤sslich. Die FuÃƒÅ¸planung kennt die statische Szene direkt (**scene oracle**);
sie arbeitet noch nicht aus Tiefenbildern oder LocalGrid-Rekonstruktionen.

56 Schritte mit allen vier FÃƒÂ¼ÃƒÅ¸en hinauf und rÃƒÂ¼ckwÃƒÂ¤rts herunter bestanden ohne
Sturz in 215.91 s Simulationszeit. Max. Roll/Nick: 9.61Ã‚Â°/3.67Ã‚Â°, Aufsetzfehler
5.93 mm, kleinster gemessener StÃƒÂ¼tzrandabstand 31.85 mm. Keine gemessene
Beindurchdringung wÃƒÂ¤hrend der mittleren 25Ã¢â‚¬â€œ75 % des Schwungs.
**Unter Last bleiben bis zu 13.55 mm FuÃƒÅ¸penetration und 29.26 mm StÃƒÂ¼tzfuÃƒÅ¸schlupf.**
Das sind offene Modell-/Reglerprobleme, keine realistischen Toleranzen.
Die Robotermasse im Bericht betrÃƒÂ¤gt 50.34 kg ohne statische Raumobjekte.

Tests prÃƒÂ¼fen HÃƒÂ¶henabfragen ohne ZustandsÃƒÂ¤nderung, StÃƒÂ¼tzflÃƒÂ¤chenplanung, den ganzen
Auf-/Abstieg, die SDK-Anbindung, Stopp und abgelehnte Bewegungen. Kein Nachweis
fÃƒÂ¼r vollstÃƒÂ¤ndige Treppen oder Sim-zu-Real. NÃƒÂ¤chster Schritt: Kontaktpenetration
und Schlupf reduzieren, weitere Geometrien prÃƒÂ¼fen, dann mehrere Stufen und
sensorbasierte FuÃƒÅ¸planung. RealitÃƒÂ¤tsaussagen brauchen reale Vergleichsfahrten.


### Aktualisierung: kÃ¼rzere Wartephasen

Der gleiche 56-Schritt-Versuch benÃ¶tigt jetzt 195.08 statt 215.91 Sekunden
(9.65 % kÃ¼rzer). Nur die Pause nach Gewichtsverlagerungen wurde von 0.4 auf
0.2 s verkÃ¼rzt. Eine schnellere Verlagerung wurde wegen negativer StÃ¼tzreserve
verworfen. Neue Werte: StÃ¼tzrand mindestens 30.27 mm, Schlupf maximal 30.47 mm,
FuÃŸpenetration maximal 13.37 mm. Weiterhin ein langsamer experimenteller
Kriechgang. Keine allgemeine Verbesserung der KontaktqualitÃ¤t nachgewiesen.


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
