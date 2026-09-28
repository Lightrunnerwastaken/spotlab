# Physikmodus Stufe B — Sitzen, Aufstehen, Körperhaltung

Entwurf vom 28.09.2026, im Gespräch in drei Abschnitten freigegeben. Baut auf Stufe A
(`2026-09-28-physik-normal-design.md`). Stufe C (Rampen, Treppen, Gelände) bleibt offen.
Betrifft zwei Repos: matura-spot (Regler, `spotsim`) und spotlab (Adapter, Messprogramm).

## Gemessen (echte Läufe in `spotProjects/Beispiele/runs`, 264 am Gerät)

| Grösse | Wert |
|---|---|
| Aufstehen aus dem Sitzen | 142 Fälle; Hub 0.41 m (0.34–0.45); Beginn 0.28 s nach dem Kommando; Dauer 0.9 s (0.77–1.02) |
| Sitzhaltung (Median) | hx 0.52 / 0.57 rad (vorn / hinten), hy 1.40, kn −2.80 (Modellgrenze −2.793: gekappt) |
| Standhaltung (Median) | hx 0.02, hy 0.85 / 0.87, kn −1.50 / −1.61 |
| Hinsetzen | nicht aufgezeichnet: nach `sit()` endet jeder Lauf nach höchstens 0.4 s |
| `pose()` | nie am Gerät befohlen |

## Entscheidungen

| # | Frage | Entscheid |
|---|---|---|
| — | Start eines Physik-Laufs | im Sitzen, wie der echte Spot (ebene Räume; die zwei Stufenszenen bleiben im Stand) |
| H1 | Aufstehen | gemessene mittlere Gelenkbahn als Positions-Sollwert (Software-PD, Motorgrenzen R1); die Kontaktphysik trägt den Körper; im Stand übernimmt der Kraftregler |
| H2 | Hinsetzen | **Annahme:** dieselbe Bahn rückwärts, gleiche Dauer; ersetzt durch Messung (A41) |
| H3 | Pose-Übergang | **Annahme:** jede Haltungsänderung in 1 s; ersetzt durch Messung (A41) |
| H4 | Gates und Nachspielen | starten weiter im Stand (`haltung="stehend"`, bitgleich) |
| — | `power_off()` | erst hinsetzen, dann Motoren aus (wie `power_off(safe=True)` am echten Spot) |
| — | Gehen im Sitzen | abgewiesen mit „zuerst stand()“ |

## matura-spot

1. `spotsim/daten/haltung.json`: wörtliche Kopie von spotlab `kalibrierung/daten/haltung.json`
   (Gelenkbahn Aufstehen, Sitz- und Standhaltung, Verzug, Dauer); Vergleichstest wie bei
   `gang.json`.
2. `spotsim/haltung.py`: `Haltungswechsel` (Bahn vorwärts = aufstehen, rückwärts = hinsetzen,
   Positions-Sollwerte je Physiktakt), `setze_sitzend()` (Startzustand: Sitzgelenke, Rumpf am
   Boden, einschwingen).
3. `SpotSdkSim(haltung="stehend"|"sitzend")`; SIT: Kraftregler anhalten, hinsetzen, sitzen
   halten; STAND oder Gehen im Sitzen: aufstehen, dann Kraftregler; neue Befehle warten, bis
   ein Wechsel fertig ist; `motoren(an)` (aus = null Drehmoment).
4. Interpreter: `stand_request` liefert auch Roll/Nick/Gier aus `footprint_R_body`; der
   Kraftregler nimmt sie im Stand als MPC-Ziel (Rampe 1 s), beim Gehen neutral.
5. Höhe: heute auf −0.12…+0.06 m gekappt, die API erlaubt ±0.15 m — gemessen wird, was der
   Kraftregler hält; darüber gekappt und gemeldet.
6. `spotsim.HALTUNG_FASSUNG = 1`; `notes/ENTWURF_haltung.md` mit H1–H4.
7. Neues Realismus-Gate „Haltung“: Aufstehen (Hub 0.41 ± 0.05 m, Dauer 0.9 ± 0.2 s, kein
   Sturz, Standgelenke ± 0.1 rad), Hinsetzen (Sitzgelenke ± 0.1 rad, Rumpf liegt auf,
   Roll/Nick < 10°), Posen (acht Messposen nach 1.5 s auf ± 2° / ± 1 cm, Fussrutschen ≤ 2 cm).

## spotlab

1. `kalibrierung/haltung.py`: zieht die Daten oben aus den echten Läufen → `haltung.json`.
2. `PhysicsBackend`: Start sitzend (ebene Räume); `power_on` Motoren an, Spot sitzt;
   `power_off` hinsetzen + aus, `robot_state` meldet es; `sit()` Rückmeldung „sitzt“ nach
   Sitzhaltung und 0.3 s Ruhe; `stand()` „steht“ mit dem Kraftregler; Stehkommando mit Haltung
   in den API-Grenzen (Roll/Nick ±20°, Gier ±30°, Höhe ±0.15 m), Kappung als `physik_grenze`;
   Gehen im Sitzen abgewiesen. `kann_sitzen` und neues `kann_pose` nur mit
   `HALTUNG_FASSUNG ≥ 1`, sonst Verhalten aus Stufe A. `api/features.supports('pose')` fragt
   `kann_pose`.
3. `tools/schueler_release.py`: `haltung` und `daten/haltung.json` in die Erlaubnisliste.
4. `Beispiele/haltung_messen.py` (echter Spot): aufstehen, Posen je 3 s (Roll ± 15°, Nick
   ± 15°, Gier ± 20°, Höhe ± 0.1 m), hinsetzen, 5 s weiter aufzeichnen; Abnahme A41.
5. Doku: CLAUDE.md, `docs/PHYSICS.md`, `docs/API.md`, `docs/ABNAHME.md`.

## Prüfung

matura-spot: Gate „Haltung“; G1–G10 und die 60 nachgespielten Fahrten mit `haltung="stehend"`
unverändert; Sitzen/Aufstehen/Posen als Video gerendert und angesehen. spotlab: Start sitzend,
`stand`/`sit`/`power_off`/`pose`, Gehen im Sitzen abgewiesen, alte spotsim-Fassung → Stufe A,
Zentrale als echter Prozess, Echtzeitfaktor ≥ 1 beim Aufstehen; beide Suiten grün.

Ablauf: spotlab-Messung → matura-spot (eigene Arbeitskopie; fremde, nicht committete Dateien
dort bleiben unberührt) → spotlab-Adapter; zuerst matura-spot mergen, dann spotlab.

## Stand nach dem Bau (28.09.2026)

Gebaut wie oben. Abweichungen und Befunde: die Aufstehbahn zählt von der letzten ruhigen Probe
(Dauer 1.00 s, Verzug 0.18 s statt der Schnellmessung 0.9 / 0.28); das Gate prüft die Posen
2.5 s nach dem Befehl (die Gier läuft langsamer ein); die Gier hält nur 20° (API 30°); die
SDK-Höhe meint den Rumpf (Umrechnung gegen den Schwerpunkt, vorher 10 % zu weit); sitzend und
nach dem Abschalten gilt der Sollwert SIT (sonst stand Spot von selbst auf); das Gate heisst
G12. Nebenbefund: das Schüler-Release konnte seit dem Kraftregler nicht gebaut werden — mit
behoben.
