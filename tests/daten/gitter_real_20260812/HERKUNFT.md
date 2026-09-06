# Echte LocalGrid-Protobufs vom Schul-Spot

Lauf `20260812T130813Z_8880c9de`, Beobachtungsfahrt Kantonsschule, 12.08.2026,
`out/beobachtung/<lauf>/gitter/000001_*.pb` — aufgezeichnet von
`spotlab.beobachtung.gitter` (serialisierte `bosdyn.api.LocalGridResponse`,
bitgleich wie vom `LocalGridService` geliefert).

Zweck: Gate G10 (`tests/test_gitterformat.py`) prüft das Sim-Gitter gegen das
ECHTE Format — Zellenzahl, Zellgrösse, Zellformat, Skala, Frame-Namensschema,
`unknown_cells`. Der Inhalt ist nicht vergleichbar (anderer Raum), das Format
schon.

Gemessen: 128×128 Zellen à 0.030 m, `CELL_FORMAT_INT16`, `cell_value_scale`
0.001, `ENCODING_RLE`, Frame `obstacle_distance_local_grid_corner`,
`unknown_cells` 16384 Bytes (nur bei obstacle_distance).
