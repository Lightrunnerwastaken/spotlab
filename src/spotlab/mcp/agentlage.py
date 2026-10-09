"""Was ein Agent über die Lage wissen muss — gelesen aus den Dateien der Zentrale.

Agenten am Spot, Teil 1 (`docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`). Die
Zentrale schreibt `lagebild.json` + `lagebild.png` (bis 4-mal je Sekunde) und `zustand.jsonl`
(10-mal je Sekunde); hier wird daraus, was ein Sprachmodell lesen kann: Pose, Tempo, Akku,
Motoren, Freigabe, die freie Strecke in acht Richtungen, Menschen und Tags mit Peilung und
Abstand ZU SPOT, und ein Bild der Skizze um Spot.

**Koordinaten:** Meter im Rahmen „vision“ — er gilt für diesen Lauf und driftet langsam. 0°
heisst +x, positive Grad nach links (gegen den Uhrzeiger). Richtungen und Peilungen sind
relativ zu Spots Blick: 0° voraus, +90° links, −90° rechts, 180° hinten.

Das Lagebild-PNG ist ein Indexbild: Zeile 0 ist OBEN (grösstes y, `skizze.bild_index`), 0
unbekannt, 1..ALTERSSTUFEN frei (frisch bis alt), danach Wand. Die Farben stehen hier fest —
der MCP-Server ist keine GUI und hat kein Thema.
"""

import io
import json
import math
import time
from pathlib import Path

import numpy as np

from spotlab.errors import SpotlabError
from spotlab.record import zentrale as protokoll
from spotlab.record.zentrale import ALTERSSTUFEN
from spotlab.workshop.wegsuche import KOERPER_M

LAGEBILD_ALT_S = 2.0
STRAHL_M = 5.0
RICHTUNGEN_GRAD = (0, 45, 90, 135, 180, -135, -90, -45)
SKIZZE_RADIUS_M = 5.0
PIXEL_JE_M = 60
ZUSTAND_LESEN_B = 64 * 1024          # vom Ende her: die letzte Zeile reicht
UNBEKANNT_FARBE = (128, 128, 128)
FREI_FARBEN = tuple((int(v), int(v), int(v)) for v in np.linspace(250, 205, ALTERSSTUFEN))
WAND_FARBEN = tuple((int(v), int(v), int(v)) for v in np.linspace(20, 100, ALTERSSTUFEN))
RASTER_FARBE = (150, 185, 225)
SPOT_FARBE = (220, 30, 30)
TAG_FARBE = (30, 90, 220)
MENSCH_FARBE = (240, 140, 0)
WEG_FARBE = (20, 160, 60)
MERKORT_FARBE = (150, 60, 200)
WEGPUNKT_FARBE = (0, 140, 140)
WEGPUNKTE_IN_LAGE = 20
RAHMEN = ("vision — Meter; gilt für diesen Lauf und driftet langsam. Weltwinkel: 0° = +x, "
          "positive Grad nach links. Richtungen und Peilungen relativ zu Spots Blick: 0° voraus, "
          "+90° links, −90° rechts.")
KEINE_ANTWORT = "Zentrale antwortet nicht"
LEGENDE = ("Ausschnitt ±{r:g} m um Spot im Rahmen „vision“: oben = +y, rechts = +x, Raster 1 m. "
           "Weiss frei (blasser = länger nicht gesehen), schwarz Wand, grau unbekannt. Roter Pfeil "
           "Spot mit Blickrichtung, blaue Quadrate AprilTags mit Nummer, orange Kreise Menschen "
           "(mit Ring: dem folgt Spot), grün der Weg der laufenden Fahrt, violette Rauten Merkorte, "
           "türkise Punkte die benannten Wegpunkte der verorteten Karte.")


def _wickle_grad(grad):
    return (grad + 180.0) % 360.0 - 180.0


def letzter_zustand(lauf_dir):
    """Die Daten der letzten lesbaren Zeile von `zustand.jsonl` — oder None."""
    pfad = Path(lauf_dir) / "zustand.jsonl"
    try:
        with pfad.open("rb") as datei:
            datei.seek(0, 2)
            groesse = datei.tell()
            datei.seek(max(0, groesse - ZUSTAND_LESEN_B))
            zeilen = datei.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for zeile in reversed(zeilen):
        try:
            satz = json.loads(zeile)
        except ValueError:
            continue                      # halb geschrieben oder der abgeschnittene Anfang
        if isinstance(satz, dict) and isinstance(satz.get("daten"), dict):
            return satz["daten"]
    return None


def _spot_lage(daten, zustand):
    """(x, y, gier_rad) in „vision“: die odom-Pose aus `zustand.jsonl` über `vision_von_odom`
    (frischer, 10-mal je s), sonst die Lage aus dem Lagebild — oder None."""
    versatz = daten.get("vision_von_odom")
    pose = (zustand or {}).get("pose")
    if versatz and pose and len(pose) == 3:
        tx, ty, dg = versatz
        c, s = math.cos(dg), math.sin(dg)
        return (c * pose[0] - s * pose[1] + tx, s * pose[0] + c * pose[1] + ty, pose[2] + dg)
    spot = daten.get("spot")
    if not spot:
        return None
    return float(spot["x"]), float(spot["y"]), math.radians(float(spot["gier_grad"]))


class _Skizze:
    """Das Indexbild des Lagebilds mit seinem Rahmen."""

    def __init__(self, index, ursprung, zelle_m):
        self.index = index
        self.ux, self.uy = float(ursprung[0]), float(ursprung[1])
        self.zelle = float(zelle_m)
        self.hoehe, self.breite = index.shape

    def wert(self, x, y):
        """Farbnummer am Weltpunkt; ausserhalb 0 (unbekannt)."""
        spalte = math.floor((x - self.ux) / self.zelle)
        zeile = self.hoehe - 1 - math.floor((y - self.uy) / self.zelle)
        if 0 <= zeile < self.hoehe and 0 <= spalte < self.breite:
            return int(self.index[zeile, spalte])
        return 0


def _skizze(lauf_dir, daten):
    if not daten.get("ursprung") or not daten.get("breite"):
        return None
    from PIL import Image

    try:
        roh = (Path(lauf_dir) / protokoll.LAGEBILD_BILD).read_bytes()
        index = np.array(Image.open(io.BytesIO(roh)))
    except (OSError, ValueError):
        return None
    if index.ndim != 2:
        return None
    return _Skizze(index, daten["ursprung"], daten["zelle_m"])


def strahl(skizze, x, y, welt_rad, bis_m=STRAHL_M):
    """Wie weit ist es in Richtung `welt_rad` frei? -> (ende, bei_m), ende ∈ wand | unbekannt |
    frei. Unbekanntes zählt erst ab `KOERPER_M`: dicht um sich sieht Spot nie etwas."""
    schritt = skizze.zelle / 2.0
    c, s = math.cos(welt_rad), math.sin(welt_rad)
    d = schritt
    while d <= bis_m:
        wert = skizze.wert(x + d * c, y + d * s)
        if wert > ALTERSSTUFEN:
            return "wand", round(d, 2)
        if wert == 0 and d > KOERPER_M:
            return "unbekannt", round(d, 2)
        d += schritt
    return "frei", round(bis_m, 2)


def _richtung(skizze, lage, grad):
    ende, bei = strahl(skizze, lage[0], lage[1], lage[2] + math.radians(grad))
    text = {"wand": f"frei bis {bei:.1f} m, dann Wand",
            "unbekannt": f"frei bis {bei:.1f} m, dahinter unbekannt",
            "frei": f"frei bis mindestens {bei:.0f} m"}[ende]
    return {"richtung_grad": grad, "ende": ende, "bei_m": bei, "text": text}


def _bezug(lage, x, y):
    """(Peilung in Grad relativ zu Spots Blick, Abstand in m)."""
    dx, dy = x - lage[0], y - lage[1]
    peilung = _wickle_grad(math.degrees(math.atan2(dy, dx) - lage[2]))
    return round(peilung, 1), round(math.hypot(dx, dy), 2)


def lage_aus(lauf_dir, jetzt=time.time):
    """Die Lage für den Agenten — oder `{"fehler": …}`, wenn die Zentrale nicht antwortet."""
    lauf_dir = Path(lauf_dir)
    daten = protokoll.lies_lagebild(lauf_dir)
    if daten is None:
        return {"fehler": f"{KEINE_ANTWORT} — es gibt (noch) kein Lagebild. zentrale_status() "
                          f"prüfen; läuft keine, zentrale_starten(…)."}
    alter = jetzt() - float(daten.get("t") or 0.0)
    if alter > LAGEBILD_ALT_S:
        return {"fehler": f"{KEINE_ANTWORT} — das Lagebild ist {alter:.1f} s alt. "
                          f"zentrale_status() prüfen; läuft keine, zentrale_starten(…)."}
    zustand = letzter_zustand(lauf_dir)
    lage = _spot_lage(daten, zustand)
    agent = daten.get("agent") or {}
    ergebnis = {"lauf": lauf_dir.name, "alter_s": round(max(0.0, alter), 2), "rahmen": RAHMEN,
                "spot": None, "tempo_m_s": None, "akku_prozent": None, "motoren": None,
                "freigabe": {"noetig": bool(agent.get("braucht_freigabe")),
                             "an": bool(agent.get("freigabe"))},
                "richtungen": [], "kopfraum": daten.get("kopfraum"), "menschen": [], "tags": [],
                "klickfahrt": _klickfahrt(daten.get("klickfahrt")), "agent": agent,
                "karte": _karte(daten.get("karte")), "merkorte": []}
    if zustand:
        tempo = zustand.get("velocity") or ()
        if len(tempo) >= 2:
            ergebnis["tempo_m_s"] = round(math.hypot(tempo[0], tempo[1]), 2)
        ergebnis["akku_prozent"] = zustand.get("battery")
        if zustand.get("powered") is not None:
            ergebnis["motoren"] = "an" if zustand["powered"] else "aus"
    if daten.get("motoren"):
        ergebnis["motoren"] = daten["motoren"]
    if lage is None:
        ergebnis["spot"] = "Lage nicht lesbar"
        return ergebnis
    ergebnis["spot"] = {"x": round(lage[0], 2), "y": round(lage[1], 2),
                        "blick_grad": round(_wickle_grad(math.degrees(lage[2])), 1)}
    skizze = _skizze(lauf_dir, daten)
    if skizze is None:
        ergebnis["richtungen"] = "Skizze noch leer — Spot hat noch kein Hindernisgitter gesehen"
    else:
        ergebnis["richtungen"] = [_richtung(skizze, lage, g) for g in RICHTUNGEN_GRAD]
    for mensch in daten.get("menschen") or ():
        peilung, abstand = _bezug(lage, mensch["x"], mensch["y"])
        ergebnis["menschen"].append({"x": mensch["x"], "y": mensch["y"], "peilung_grad": peilung,
                                     "abstand_m": abstand, "alter_s": mensch.get("alter_s"),
                                     "gefolgt": bool(mensch.get("gefolgt"))})
    for tag in daten.get("tags") or ():
        peilung, abstand = _bezug(lage, tag["x"], tag["y"])
        ergebnis["tags"].append({"id": tag["id"], "x": tag["x"], "y": tag["y"],
                                 "peilung_grad": peilung, "abstand_m": abstand})
    for ort in daten.get("merkorte") or ():
        peilung, abstand = _bezug(lage, ort["x"], ort["y"])
        ergebnis["merkorte"].append({"name": ort["name"], "x": ort["x"], "y": ort["y"],
                                     "peilung_grad": peilung, "abstand_m": abstand})
    karte = daten.get("karte") or {}
    if ergebnis["karte"] is not None and karte.get("zustand") == "verortet":
        benannt = []
        for w in karte.get("wegpunkte") or ():
            if w.get("name"):
                peilung, abstand = _bezug(lage, w["x"], w["y"])
                benannt.append({"name": w["name"], "x": w["x"], "y": w["y"],
                                "peilung_grad": peilung, "abstand_m": abstand})
        benannt.sort(key=lambda w: w["abstand_m"])
        ergebnis["karte"]["wegpunkte"] = benannt[:WEGPUNKTE_IN_LAGE]
    return ergebnis


def _karte(karte):
    """Die Karte der Zentrale in Kürze — None, wo es keine Kartenarbeit gibt (Übungsraum)."""
    if not karte or not karte.get("kann", True):
        return None
    return {"name": karte.get("name"), "zustand": karte.get("zustand"),
            "grund": karte.get("grund"), "aufnahme": karte.get("aufnahme"), "wegpunkte": []}


def _klickfahrt(stand):
    """Die laufende Fahrt ohne den ganzen Weg — der steht im Bild."""
    if not stand:
        return None
    return {"zustand": stand.get("zustand"), "grund": stand.get("grund"),
            "ziel": stand.get("ziel"), "quelle": stand.get("quelle"),
            "wegpunkte": len(stand.get("weg") or ())}


def skizze_bild(lauf_dir, radius_m=SKIZZE_RADIUS_M):
    """(PNG-Bytes, Legende): die Skizze im Ausschnitt ±`radius_m` um Spot, +y oben.

    Wirft `SpotlabError` mit dem, was zu tun ist, wenn es nichts zu zeigen gibt."""
    from PIL import Image, ImageDraw

    lauf_dir = Path(lauf_dir)
    daten = protokoll.lies_lagebild(lauf_dir)
    if daten is None:
        raise SpotlabError(f"{KEINE_ANTWORT} — es gibt kein Lagebild. zentrale_status() prüfen.")
    skizze = _skizze(lauf_dir, daten)
    if skizze is None:
        raise SpotlabError("Die Skizze ist noch leer — Spot hat noch kein Hindernisgitter "
                           "gesehen. Kurz warten oder drehen lassen.")
    lage = _spot_lage(daten, letzter_zustand(lauf_dir))
    if lage is None:
        raise SpotlabError("Spots Lage ist nicht lesbar — kurz warten und noch einmal fragen.")
    r = float(radius_m)
    links, oben = lage[0] - r, lage[1] + r
    seite = int(round(2 * r * PIXEL_JE_M))
    mitten = (np.arange(seite) + 0.5) / PIXEL_JE_M
    spalten = np.floor((links + mitten - skizze.ux) / skizze.zelle).astype(int)
    zeilen = skizze.hoehe - 1 - np.floor((oben - mitten - skizze.uy) / skizze.zelle).astype(int)
    gilt_s = (spalten >= 0) & (spalten < skizze.breite)
    gilt_z = (zeilen >= 0) & (zeilen < skizze.hoehe)
    werte = skizze.index[np.clip(zeilen, 0, skizze.hoehe - 1)[:, None],
                         np.clip(spalten, 0, skizze.breite - 1)[None, :]]
    werte = np.where(gilt_z[:, None] & gilt_s[None, :], werte, 0)
    farben = np.array([UNBEKANNT_FARBE] * 256, dtype=np.uint8)
    farben[1:1 + ALTERSSTUFEN] = FREI_FARBEN
    farben[1 + ALTERSSTUFEN:1 + 2 * ALTERSSTUFEN] = WAND_FARBEN
    bild = Image.fromarray(farben[werte], "RGB")
    zeichner = ImageDraw.Draw(bild)

    def px(x, y):
        return ((x - links) * PIXEL_JE_M, (oben - y) * PIXEL_JE_M)

    for meter in range(math.floor(links), math.ceil(links + 2 * r) + 1):
        zeichner.line([px(meter, oben), px(meter, oben - 2 * r)], fill=RASTER_FARBE)
    for meter in range(math.floor(oben - 2 * r), math.ceil(oben) + 1):
        zeichner.line([px(links, meter), px(links + 2 * r, meter)], fill=RASTER_FARBE)
    fahrt = daten.get("klickfahrt") or {}
    if fahrt.get("zustand") in ("unterwegs", "folgt") and fahrt.get("weg"):
        punkte = [px(lage[0], lage[1])] + [px(*p) for p in fahrt["weg"]]
        zeichner.line(punkte, fill=WEG_FARBE, width=3)
    for tag in daten.get("tags") or ():
        u, v = px(tag["x"], tag["y"])
        zeichner.rectangle([u - 6, v - 6, u + 6, v + 6], fill=TAG_FARBE)
        zeichner.text((u + 8, v - 6), str(tag["id"]), fill=TAG_FARBE)
    karte = daten.get("karte") or {}
    if karte.get("zustand") == "verortet":
        for w in karte.get("wegpunkte") or ():
            if w.get("name"):
                u, v = px(w["x"], w["y"])
                zeichner.ellipse([u - 5, v - 5, u + 5, v + 5], fill=WEGPUNKT_FARBE)
                zeichner.text((u + 7, v - 6), str(w["name"]), fill=WEGPUNKT_FARBE)
    for ort in daten.get("merkorte") or ():
        u, v = px(ort["x"], ort["y"])
        zeichner.polygon([(u, v - 8), (u + 8, v), (u, v + 8), (u - 8, v)], fill=MERKORT_FARBE)
        zeichner.text((u + 10, v - 6), str(ort["name"]), fill=MERKORT_FARBE)
    for mensch in daten.get("menschen") or ():
        u, v = px(mensch["x"], mensch["y"])
        zeichner.ellipse([u - 8, v - 8, u + 8, v + 8], fill=MENSCH_FARBE)
        if mensch.get("gefolgt"):
            zeichner.ellipse([u - 13, v - 13, u + 13, v + 13], outline=MENSCH_FARBE, width=2)
    _pfeil(zeichner, px(lage[0], lage[1]), lage[2])
    zeichner.rectangle([0, 0, seite, 14], fill=(255, 255, 255))
    zeichner.text((3, 2), "Raster 1 m | +y oben | rot Spot | blau Tag | orange Mensch | gruen Weg | "
                  "violett Merkort | tuerkis Wegpunkt",
                  fill=(0, 0, 0))
    puffer = io.BytesIO()
    bild.save(puffer, format="PNG")
    return puffer.getvalue(), LEGENDE.format(r=r)


def _pfeil(zeichner, mitte, gier):
    """Ein Dreieck, Spitze in Blickrichtung (Bildkoordinaten: y nach unten)."""
    u, v = mitte
    lang, breit = 0.45 * PIXEL_JE_M, 0.2 * PIXEL_JE_M
    c, s = math.cos(gier), -math.sin(gier)
    spitze = (u + c * lang, v + s * lang)
    hinten = (u - c * lang * 0.5, v - s * lang * 0.5)
    links = (hinten[0] - s * breit, hinten[1] + c * breit)
    rechts = (hinten[0] + s * breit, hinten[1] - c * breit)
    zeichner.polygon([spitze, links, rechts], fill=SPOT_FARBE)
