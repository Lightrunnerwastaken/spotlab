# Steuerzentrale, Teil 2: Menschen sehen und ihnen folgen

Entwurf vom 27.09.2026, im Gespräch abschnittsweise freigegeben. Baut auf Teil 1
(`2026-09-27-steuerzentrale-design.md`) auf und füllt dessen leeren Platz `menschen`.

## Entscheidungen

- **Regler mit 4 Stufen:** Aus · Sparsam (vorne, eine Runde alle 2 s) · Normal (vorne, so oft
  es geht) · Rundum (vorne plus links, rechts, hinten). Unter dem Regler steht die Dauer einer
  Runde. Ohne Kameras (2D-Übungsraum) ist er grau und sagt warum.
- **Folgen nur mit sichtbarem Tab:** dasselbe Lebenszeichen wie die Klickfahrt (0.5 s);
  Taste, neuer Klick, Stopp oder fehlendes Lebenszeichen beenden das Folgen.
- **Bauweg:** die Suche ist ein Faden IM Programm der Zentrale (kein zweiter Prozess, keine
  Erkennung in der GUI). Zum Folgen übergibt die Zentrale an den bestehenden Folgemodus
  (`folgen.folge`) — kein zweites Folgen.

## Suche (2a, 2c) — `workshop/menschensuche.py`

- Dieselbe Kette wie beim Folgen: Bild → `Koerpererkenner` (YOLOX, Pose, Spur) →
  `koerper.beurteile` (Tiefe, Höhenprobe). Je Quelle ein eigener Erkenner (die Spur gehört zu
  EINER Bildfolge).
- Vorne: `folgen.bildaufnahme` (Frontpanorama). Rundum zusätzlich die Seiten- und Rückkamera
  (`left/right/back_fisheye_image` mit `…_depth`) über eine **Einzelsicht**
  (`backends/real/panorama.py::Einzelsicht`): dieselbe Zylinderprojektion wie das Panorama,
  eine Kamera, `winkel()` gibt die Peilung im KÖRPERrahmen. Das Frontpanorama bleibt unberührt.
- Jeder genommene Körper wird mit Spots Lage im Rahmen „vision“ zum Zeitpunkt des Bildes in die
  Draufsicht gerechnet (`merkpunkt.in_raum`). Eine Quelle, die scheitert, hält die anderen nicht
  auf.
- Im Lagebild: `menschen` = `[{x, y, alter_s, quelle, gefolgt}]`, höchstens 3 s alt;
  `suche` = `{stufe, runde_s, kann, grund}`. Der Tab zeichnet Kreise, blasser mit dem Alter.

## Folgen aus der Draufsicht (2b)

- Ein Klick bis 0.5 m neben einen Menschen schreibt ein Klickziel der Art `mensch`
  (`klickziel.json` bekommt `art`, Vorgabe `ort`).
- Das Programm ruft `folgen.folge()` mit dem Körperfinder, eingewickelt: in den ersten zwei
  Treffern nimmt es nur den Kandidaten, der dem Klick am nächsten steht (höchstens 1 m daneben,
  im Körperrahmen verglichen); danach hält der Merkpunkt ihn. `laeuft` endet bei Stopp, Taste,
  neuem Klick oder fehlendem Lebenszeichen, der Grund steht im Lagebild.
- Während des Folgens: Zustand `folgt`, die Suche pausiert, was der Folgemodus sieht, erscheint
  in der Draufsicht (der Gefolgte hervorgehoben). Die LEDs gehören dem Folgemodus; danach wird
  die zuletzt gewählte Farbe wieder gesetzt.

## Prüfung

Einzelsicht an einer nachgebauten Seiten- und Rückkamera; Suche mit Attrappen (Weltlage, Stufen,
Quellen, Fehler einer Quelle); Zentrale: Regler, Lagebild, Folgen mit Attrappe (Auswahl des
Angeklickten unter zweien, Ende bei Taste/Klick/Totmann); Tab: Regler, Kreise, Klick auf Mensch.
Am Gerät: A39. Echte Menschen gibt es im Übungsraum nicht.
