# Echte Frontbilder vom Schul-Spot

Lauf `20260812T130813Z_8880c9de`, Beobachtungsfahrt Kantonsschule, 12.08.2026,
aufgezeichnet von `spotlab.beobachtung.bilder` (`kamera/*.jpg` woertlich, JPEG
Guete 90, plus `kamera/quellen.json`). `quellen.json` hier: nur die beiden
Frontkameras, und vom Rahmenbaum nur die Kette Sensor -> Kopf -> Koerper.
Format: 640x480, `PIXEL_FORMAT_GREYSCALE_U8` (der Beobachter hat kein RGB
erbeten), Intrinsik `pinhole`, Sensorrahmen `frontleft_fisheye` bzw.
`frontright_fisheye`.

- `takt90_*`: leerer Gang, keine Person. In der Ueberlappung der beiden
  Bilder weichen sie im Mittel um 8 Graustufen ab (mittelwertfrei); mit
  vertauschter Kalibrierung um 23. Daran haengt `test_backend_panorama.py`.
- `takt60_*`: Tischreihe links, keine Person. Die Kameras haben getrennt
  belichtet: 112 gegen 64 im Mittel derselben Szene -- der Fall fuer den
  Helligkeitsausgleich.

Aus der Kalibrierung: die rechte Kamera blickt 34 Grad nach LINKS, die linke
34 Grad nach rechts (ueber Kreuz), beide rund 20 Grad nach unten, 7 cm
auseinander, 38 cm vor der Koerpermitte.
