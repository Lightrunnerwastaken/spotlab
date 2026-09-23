# Die Antwort des Sim auf `walk()` — gemessen am Schul-Spot

Seit dem 23.09.2026 antworten `SimBackend` und die Puppe (`backend="mujoco"`, auch
flyspots `koerper="kinematik"`) auf Geschwindigkeitskommandos so, wie der echte Spot
es tut. Vorher galt: kommandiert IST erreicht, sofort — ohne Verzug, ohne Auslaufen,
und jede noch so kleine Drehung wurde gedreht.

## Messung

60 kommandierte Läufe am Schul-Spot (`fahren.py`, `folgen.py`, 07.–21.09.2026),
`walk`-Kommandos alle ~0.1 s, Zustand mit 10 Hz. Gemessen am Tempo, das der Roboter
selbst meldet. Neu bauen: `python -m spotlab.kalibrierung.tempoantwort <runs> [...]`.

| Grösse | Wert | Belegt durch |
|---|---|---|
| Latenz (jedes Kommando) | 0.10 s | 92 Stopps |
| Anlauf aus dem Stand (zusätzlich) | 0.15 s | 45 Anfahrten |
| Zeitkonstante Gehen an / ab | 0.20 / 0.12 s | dieselben Sprünge |
| Zeitkonstante Drehen an / ab | 0.025 / 0.07 s | dieselben Sprünge |
| Drehschwelle (reines Drehen) | 0.125 rad/s | 4434 Takte; ≤ 0.12: Anteil ±0.01, ≥ 0.13: 0.94–0.99 |
| Tempoanteil Gehen 0.2 / 0.4 / 0.8 m/s | 0.87 / 0.98 / 1.01 | 184 Haltephasen |
| Tempoanteil Drehen 0.39 / 0.79 / 1.1 rad/s | 0.99 / 1.00 / 1.00 | dieselben |

Die Zeiten zählen vom Kommando-Ereignis des Laptops bis zum gemeldeten Tempo — die
Übertragung steckt drin, genau wie in einer Programmschleife am Roboter.

## Prüfung ausserhalb der Stichprobe

Kennlinie nur aus den Läufen bis 16.09. (`--bis 20260917`), nachgespielt die 26 Läufe
vom 17.–21.09. (`python -m spotlab.kalibrierung.nachspiel <runs> --ab 20260917
--tempoantwort <kennlinie>`). Median über die Läufe:

| | Verzug vx | Anteil vx | Verzug wz | Anteil wz | Nachlauf nach Stopp | Drehen unter der Schwelle |
|---|---|---|---|---|---|---|
| echter Spot | 0.24 s | 0.87 | 0.24 s | 0.82 | 0.091 m / 0.134 rad | 0.00 |
| Sim, gemessen | 0.24 s | 0.88 | 0.14 s | 0.91 | 0.084 m / 0.130 rad | 0.00 |
| Sim, vorher | 0 | 1.00 | 0 | 1.00 | 0 / 0 | 1.00 |

## Offen

- **Umsteuern der Drehung im Gehen mit Tastensprüngen**: echt 0.25 s, Sim 0.16 s.
  Bei stetigem Lenken (Folgen — flyspots Fall) stimmt es: 0.14 gegen 0.14 s.
- **Unter 0.15 m/s** gibt es keine Kommandos in den Daten; ob Spot dort überhaupt
  losgeht, ist unbekannt. `bericht()["tempoantwort"]` zählt solche Kommandos.
- Ob die Drehschwelle direkt nach dem Gehen gilt (24 Takte, uneinheitlich); das
  Modell wendet sie immer an.
- Bewusst weggelassen: Gierzittern im Gang (0.02 rad/s bei 3–5 Hz, als Winkel 0.06° —
  ein Drittel Pixel bei 330 px Brennweite). Seitwärtsfahrt: nur 5 Haltephasen.
- `Tempoantwort.sofort()` ist die alte Annahme; nur für Prüfungen, die etwas anderes
  messen (G11, Zeitintegration).
