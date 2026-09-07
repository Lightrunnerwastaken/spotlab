"""`kamera.json` im Lauf-Verzeichnis: der Kamerawunsch fuer die Zimmeransicht.

Das Uebungsfenster schreibt ihn (Knopf „Verfolgen", Mausrad ueber dem Bild),
der Ansichtsthread des MuJoCo-Backends liest ihn je Bild -- ueber dieselbe
Platte, ueber die auch alle Live-Daten laufen; die GUI haelt keinen Draht in
den Lauf. Reine Standardbibliothek. Was nicht stimmt (kaputte Datei,
unbekannter Modus, kein Zahl als Zoom), ist die Vorgabe -- ein Kamerawunsch
darf einen Lauf nie anhalten.
"""

import json
from pathlib import Path

from spotlab.record import atomar

DATEI = "kamera.json"
MODI = ("raum", "verfolgen")        # dieselben Namen wie spotsim.puppe.ANSICHT_MODI
VORGABE_MODUS = "raum"
VORGABE_ZOOM = 1.0
ZOOM_BEREICH = (0.5, 8.0)


def _begrenzt(zoom):
    return min(ZOOM_BEREICH[1], max(ZOOM_BEREICH[0], float(zoom)))


def schreibe(lauf_dir, modus, zoom):
    """Atomar: erst `.tmp`, dann ersetzen -- der Leser sieht nie eine halbe Datei."""
    if modus not in MODI:
        raise ValueError(f"Kameramodus {modus!r} -- erwartet einen von {MODI}.")
    atomar.schreibe_atomar(Path(lauf_dir) / DATEI, json.dumps({"modus": modus, "zoom": _begrenzt(zoom)}))


def lies(lauf_dir):
    """(modus, zoom) -- oder die Vorgabe, wenn die Datei fehlt oder nicht stimmt."""
    pfad = Path(lauf_dir) / DATEI
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return VORGABE_MODUS, VORGABE_ZOOM
    if not isinstance(roh, dict):
        return VORGABE_MODUS, VORGABE_ZOOM
    modus = roh.get("modus")
    if modus not in MODI:
        modus = VORGABE_MODUS
    try:
        zoom = _begrenzt(roh.get("zoom", VORGABE_ZOOM))
    except (TypeError, ValueError):
        zoom = VORGABE_ZOOM
    return modus, zoom


def stand(lauf_dir):
    """(mtime_ns, Groesse) der Datei oder None -- billig zu vergleichen, je Bild."""
    try:
        st = (Path(lauf_dir) / DATEI).stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)
