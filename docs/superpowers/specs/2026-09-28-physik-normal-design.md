# Physikmodus als normaler Übungsraum — Stufe A

Entwurf vom 27./28.09.2026, im Gespräch freigegeben. Stufe B (Sitzen, Aufstehen, Körperpose im
Regler) und C (Rampen, Gelände, Treppen) ändern den Forschungsregler in matura-spot und werden
einzeln entschieden.

## Stand vorher (gemessen 27.09.2026)

Geht: stand/walk/stop, Tiefe, Grau, Hindernisgitter, Zentrale (2.2 Lagebilder/s), Echtzeit
(9.9 s Sim in 11.6 s). 60 echte Fahrten nachgespielt: 0 Stürze, Höchsttempo 98/91 %.
Abgelehnt: sit, move, pose, Tags, Sperrzonen-Räume, Rampen/Treppen/Gelände (ausser zwei
validierten Mini-Szenen), GraphNav.

## Entscheidungen

- Tab „Fahren“: drei Orte — „🧪 Übungsraum 3D (Wiedergabe)“ (Vorgabe), „⚙ Übungsraum Physik“,
  „🐕 Echter Spot“. Editor: „Physik 3D“ ohne „(experimentell)“; der Tooltip sagt: eigener Regler
  aus matura-spot, auf 60 echte Fahrten abgestimmt, nicht der Regler von Boston Dynamics.
- `spot.sit()` im Physikmodus: anhalten, einmal „Sitzen kann der Physikmodus noch nicht — Spot
  bleibt stehen“, normal zurückkehren; der Zustand bleibt „steht“ (Merkmal `kann_sitzen = False`
  am Backend, gefragt in `api/posture.sit`).

## Umsetzung

1. **Raumregel** `welt/physik.py::tauglich(raum, start)` → `(ok, art, grund)`, art ∈ eben |
   einzelstufe | treppe3. Ebene Räume mit Wänden, Blöcken, Tags, Sperrzonen; die zwei validierten
   Szenen wie bisher; alles andere mit Grund. Das Backend und der Tab fragen dieselbe Funktion.
2. **Tags**: `PhysicsBackend.world_objects()` + `Capability.WORLD_OBJECTS`, Sichtprüfung über
   `SpotPuppe.sichtbare_tags` (unverändert, im Physik-Faden auf dessen Modell/Zustand).
3. **Sperrzonen**: im Physik-Takt `welt.kollision.zone_bei` auf die Körperlage; beim Hineinfahren
   Stopp und Ereignis `angestossen` mit „Sperrzone ‹Name›“ wie in den Sims.
4. **`move()`**: das odom-Ziel aus `se2_trajectory_request` (wie `SimBackend._ziel_aus`); der
   Physik-Takt schickt alle 0.1 s Sim-Zeit einen geregelten Gehbefehl (Tempogrenzen des Reglers,
   langsamer nahe am Ziel); fertig bei ≤ 5 cm und ≤ 3°, sonst endet es an der Frist mit Grund.
   Der Kraftregler bleibt unverändert.
5. **`sit()`**: siehe Entscheidungen.
6. **GUI**: drei Orte, Start mit Backend `physics`, Raumregel vor dem Start (Meldung statt Start).

## Prüfung

Raumregel; Tag sichtbar/verdeckt; Stopp an einer Sperrzone; `move()` 1 m und 90° ohne Sturz
(`realtime=False`, Sim-Uhr); `sit()` bleibt stehen mit Hinweis; Tab mit drei Orten und Ablehnung
eines Treppenraums; die Zentrale im Physikmodus als echter Prozess.
