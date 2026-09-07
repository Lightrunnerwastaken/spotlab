# Echte Tiefenbilder vom Schul-Spot

Lauf `20260812T112135Z_b2cadb3f`, Beobachtungsfahrt Kantonsschule, 12.08.2026,
aufgezeichnet von `spotlab.beobachtung.bilder` (`kamera/*.raw` woertlich plus
`kamera/quellen.json`). Hier wieder zu genau der `bosdyn.api.ImageResponse`
zusammengesetzt, die der ImageService geliefert hat — Bytes, Intrinsik,
Tiefenskala, Sensorrahmen und Rahmenbaum unveraendert.

- `tischreihe_*`: Takt 428. Ueber dem Vorwaertskorridor haengt etwas 0.72 m
  voraus, 0.17 m ueber der Koerpermitte (also rund 0.69 m ueber dem Boden) —
  Tischhoehe. Das Hindernisgitter sieht davon nichts.
- `freier_gang_*`: Takt 5. Offener Gang, kein einziger Punkt im Hoehenband.

Format: 424x240, `PIXEL_FORMAT_DEPTH_U16`, `depth_scale` 999, Sensorrahmen
`frontleft`/`frontright` ueber `head` am `body`.

Gemessen ueber die ganze Fahrt (1181 Takte): 340 Takte mit Ueberhang im
Korridor, davon 70 naeher als 1 m; die Hoehen liegen zwischen 0.07 und 0.41 m
ueber der Koerpermitte. Der Boden landet bei -0.51 m, also auf der gemessenen
Standhoehe — die Rechnung stimmt gegen echte Daten.
