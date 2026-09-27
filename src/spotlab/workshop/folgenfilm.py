"""Folgen als Video: was Spot sah, was er daraus machte — in Echtzeit, mit Markierungen.

    python -m spotlab.workshop.folgenfilm <lauf> [--fps 10] [--breite 1280] [--ohne-gesicht]

Liest die Folge-Aufnahme (`workshop/folgeaufnahme.py`, `<lauf>/folgen/`) und
schreibt `<lauf>/folgen.mp4` und daneben `folgen_bericht.txt`.

IM BILD, auf dem Panorama, das der Finder in diesem Takt sah:
    Körper      Skelett grün, wenn genommen; orange, wenn verworfen — mit Grund
    Gesicht     Kasten blau, wenn genommen; grau, wenn verworfen — mit Grund
    offline     Gesichter türkis: YuNet NACHTRÄGLICH auf jeder Körper-Sicht. Die
                Staffel fragt das Gesicht nur, wenn der Körper nichts fand; hier
                sieht man, wann es auch getragen hätte (braucht OpenCV und das
                Modell, sonst fällt es mit Meldung weg)
    Linien      weiss dünn = geradeaus, gelb = das Ziel nachgeführt, gelb dünn = roh
UNTEN: Zustand in der Farbe der Kopf-LEDs (blau folgt, gelb sucht, rot angehalten,
grau Nachlauf, lila Kreissperre), Ziel, Abstand gegen den Wunsch, Befehl samt
bremsender Schranke, ein Balken, der die Arbeit des Takts in ihre Schritte teilt
(volle Breite = 1 s), und der Zeitstrahl des ganzen Laufs.

ECHTZEIT. Jedes Bild steht, bis das nächste kam: ein Film, der jedes Bild gleich
lang zeigte, verschwiege genau das Stocken, das er zeigen soll.

EIN ALTER LAUF ohne Aufnahme hat nur die Ereignisse `ziel`: dann gibt es Leiste
und Zeitstrahl, aber kein Bild — das Video sagt es.
"""

import argparse
import bisect
import collections
import json
import math
import os
import statistics
import sys
from pathlib import Path

from spotlab.errors import SpotlabError
from spotlab.workshop import folgeaufnahme

FPS = 10
BREITE = 1280
DATEI = "folgen.mp4"
BERICHT = "folgen_bericht.txt"   # neben dem Video
LUECKE_S = 2.0              # so lange ohne gesehenes Ziel zählt als Lücke im Bericht
BALKEN_S = 1.0              # volle Breite des Zeitbalkens

HINTERGRUND = (18, 20, 24)
TEXT = (235, 235, 235)
GEDAEMPFT = (150, 155, 165)
GRUEN = (40, 200, 90)
ORANGE = (255, 150, 30)
BLAU = (70, 140, 255)
GRAU = (150, 150, 150)
TUERKIS = (0, 215, 225)
GELB = (245, 205, 30)
ROT = (230, 55, 55)
LILA = (175, 95, 225)

# `haelt` (seit 27.09.2026): der Merkpunkt haelt den Menschen, Spot dreht nur noch mit.
HELLGRAU = (205, 205, 205)
ZUSTAND_FARBE = {"folgt": BLAU, "sucht": GELB, "angehalten": ROT, "nachlauf": GRAU,
                 "haelt": HELLGRAU, "gesperrt": LILA, "abbruch": GRAU}

# Gruppen der Schritte im Zeitbalken — Reihenfolge wie im Takt.
GRUPPEN = (
    ("Bilder", ("bilder", "kameras", "tiefe"), (80, 130, 255)),
    ("Panorama", ("panorama", "punkte"), (110, 200, 225)),
    ("Zustand", ("lage", "gier"), (150, 150, 150)),
    ("Körper", ("koerper", "koerper_probe"), GRUEN),
    ("Gesicht", ("yunet", "gesicht_probe"), LILA),
    ("Gesten", ("gesten",), GELB),
    ("Schranken", ("gitter", "kopfraum", "zone"), ORANGE),
    ("Fahren", ("walk", "stop"), ROT),
)

LEGENDE = ("Zeitstrahl oben: blau folgt · grau Nachlauf · hellgrau hält (dreht nur) · gelb sucht · "
           "rot angehalten · lila Kreissperre — unten: grün Körper, türkis Gesicht · "
           "Balken: volle Breite 1 s")

# Die Knochen des MediaPipe-Skeletts (33 Punkte), ohne Gesicht und Finger.
KNOCHEN = ((11, 12), (11, 23), (12, 24), (23, 24), (11, 13), (13, 15), (12, 14), (14, 16),
           (23, 25), (25, 27), (24, 26), (26, 28), (27, 31), (28, 32), (0, 11), (0, 12))
PRAESENZ = 0.5
# Die Suchwege des Koerpererkenners in Worten (`koerper.Koerpererkenner.letzter_weg`).
WEGE = {"spur": "Spur", "suche": "Suche", "yolox": "YOLOX", "yolox-kasten": "YOLOX ohne Skelett"}
# Bildabrufe hiessen bis zum 25.09.2026 `kameras` + `tiefe`, seither EIN Schritt `bilder`.
ABRUFE = ("bilder", "kameras")


def _finder_der(sicht):
    """Die Finder einer Sicht — seit die Staffel die Bilder teilt, auch `koerper+gesicht`."""
    return set((sicht.get("finder") or "").split("+"))


# ------------------------------------------------------------------ Laden


def takte_laden(lauf_dir):
    """(Takte, Quelle): aus der Folge-Aufnahme — oder, bei alten Läufen, aus den Ereignissen."""
    lauf = Path(lauf_dir)
    datei = lauf / folgeaufnahme.ORDNER / folgeaufnahme.INDEX
    if datei.is_file():
        takte = [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines() if z.strip()]
        if takte:
            return takte, "aufnahme"
    takte = takte_aus_ereignissen(lauf)
    if takte:
        return takte, "ereignisse"
    raise SpotlabError(
        f"In {lauf} gibt es keine Folge-Aufnahme ({folgeaufnahme.ORDNER}/{folgeaufnahme.INDEX} "
        f"fehlt) und keine Ziel-Ereignisse. Aufnehmen mit Beispiele/folgen_aufnahme.py "
        f"(oder `folge(..., aufnahme=True)`).")


def takte_aus_ereignissen(lauf_dir):
    """Die Takte eines Laufs ohne Aufnahme — aus `ziel` in `ereignisse.jsonl`. Ohne Bilder."""
    datei = Path(lauf_dir) / "ereignisse.jsonl"
    if not datei.is_file():
        return []
    takte = []
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if satz.get("art") != "ziel":
            continue
        d = satz.get("daten") or {}
        takt = {"takt": len(takte) + 1, "t": float(satz["t"]), "arbeit_s": None,
                "takt_s": d.get("takt_s"), "zeiten": [], "sichten": [], "koerper": [],
                "gesichter": [], "ziel": None, "befehl": None, "geste": None, "zustand": "sucht"}
        if not d.get("weg"):
            takt["ziel"] = {"name": d.get("finder"), "peilung": d.get("peilung"),
                            "peilung_jetzt": d.get("peilung_jetzt"), "abstand": d.get("abstand"),
                            "bild_oben": d.get("bild_oben"), "echt": bool(d.get("echt"))}
            takt["befehl"] = {"vx": d.get("vx"), "wz_grad": d.get("wz_grad"), "nick_grad": None,
                              "schranke": "", "gesperrt": bool(d.get("gesperrt")), "angehalten": False}
            takt["zustand"] = ("gesperrt" if d.get("gesperrt") else "folgt" if d.get("echt")
                               else "nachlauf")
        takte.append(takt)
    return takte


def _dauer(takt):
    for schluessel in ("arbeit_s", "takt_s"):
        wert = takt.get(schluessel)
        if wert:
            return float(wert)
    return 0.5


def _bild_laden(lauf, pfad):
    import numpy as np
    from PIL import Image

    with Image.open(Path(lauf) / folgeaufnahme.ORDNER / pfad) as bild:
        return np.asarray(bild.convert("RGB") if bild.mode not in ("RGB", "L") else bild.copy())


# ------------------------------------------------------------------ Zeitplan


def zeitplan(takte, fps=FPS):
    """[(t, Takt-Index, (Takt-Index, Sicht-Nr) oder None)] — ein Eintrag je Videobild.

    Das Bild zeigt die LETZTE Sicht mit t ≤ Bildzeit, die Leiste den letzten Takt.
    """
    if not takte:
        return []
    t0 = float(takte[0]["t"])
    ende = float(takte[-1]["t"]) + _dauer(takte[-1])
    takt_zeiten = [float(t["t"]) for t in takte]
    sichten = sorted(
        (float(s["t"] if s.get("t") is not None else takt["t"]), i, int(s.get("nr", 0)))
        for i, takt in enumerate(takte) for s in takt.get("sichten") or [] if s.get("bild"))
    sicht_zeiten = [s[0] for s in sichten]
    plan = []
    for k in range(int(math.floor((ende - t0) * fps + 1e-9)) + 1):
        t = t0 + k / fps
        ti = max(0, bisect.bisect_right(takt_zeiten, t + 1e-9) - 1)
        si = bisect.bisect_right(sicht_zeiten, t + 1e-9) - 1
        plan.append((t, ti, (sichten[si][1], sichten[si][2]) if si >= 0 else None))
    return plan


# ------------------------------------------------------------ Gesicht offline


def _gesichtserkenner(pano):
    from spotlab.backends.real import gesicht

    return gesicht.erkenner(pano.breite, pano.hoehe)


def gesicht_offline(lauf_dir, takte, pano, erkenner_=None, kaesten_holen=None):
    """YuNet und Gegenprobe auf JEDER Körper-Sicht — `takt["gesichter_offline"]`. Gibt die Anzahl.

    Dieselbe Rechnung wie im Lauf (`gesicht.beurteile`), auf dem gespeicherten
    Panorama und den gespeicherten Tiefenpunkten, mit dem gemessenen Nick.
    """
    import numpy as np

    from spotlab.backends.real import gesicht

    lauf = Path(lauf_dir)
    anzahl = 0
    for takt in takte:
        offline = []
        for sicht in takt.get("sichten") or []:
            if "koerper" not in _finder_der(sicht) or "gesicht" in _finder_der(sicht) \
                    or not sicht.get("bild"):
                continue          # das Gesicht lief darauf schon im Lauf
            feld = _bild_laden(lauf, sicht["bild"])
            punkte = None
            if sicht.get("tiefe"):
                punkte = np.load(lauf / folgeaufnahme.ORDNER / sicht["tiefe"])["punkte"].astype(float)
            nick = float(sicht.get("nick_grad") or 0.0)
            befunde = gesicht.beurteile(feld, pano, erkenner_, punkte, pano.kamerahoehe(nick),
                                        blick_grad=nick, kaesten_holen=kaesten_holen)
            offline.extend(folgeaufnahme.gesicht_als_daten(sicht.get("nr", 0), b) for b in befunde)
            anzahl += 1
        takt["gesichter_offline"] = offline
    return anzahl


# ------------------------------------------------------------------ Bericht


def _zeiten_je_takt(takt):
    summe = collections.defaultdict(float)
    for name, dauer in takt.get("zeiten") or []:
        summe[name] += float(dauer or 0.0)
    return summe


def _quantil(werte, anteil):
    werte = sorted(werte)
    return werte[min(len(werte) - 1, int(anteil * len(werte)))]


def bericht(takte, name=""):
    """Der Kurzbericht zur Aufnahme — Text, eine Zahl je Zeile."""
    n = len(takte)
    if not n:
        return "Keine Takte."
    t0 = float(takte[0]["t"])
    dauer = float(takte[-1]["t"]) + _dauer(takte[-1]) - t0
    z = [f"Folge-Aufnahme {name}".rstrip() + f": {n} Takte in {dauer:.0f} s "
         f"({n / max(dauer, 1e-9):.1f} je Sekunde)"]

    abstaende = [b["t"] - a["t"] for a, b in zip(takte, takte[1:])]
    if abstaende:
        z.append(f"Takt zu Takt: Median {statistics.median(abstaende):.2f} s, "
                 f"p90 {_quantil(abstaende, 0.9):.2f} s, höchstens {max(abstaende):.2f} s")
    arbeit = [float(t["arbeit_s"]) for t in takte if t.get("arbeit_s")]
    if arbeit:
        z.append(f"Arbeit je Takt: Median {statistics.median(arbeit) * 1000:.0f} ms, "
                 f"p90 {_quantil(arbeit, 0.9) * 1000:.0f} ms")

    je_schritt = collections.defaultdict(list)
    for takt in takte:
        for schritt, dauer_s in _zeiten_je_takt(takt).items():
            je_schritt[schritt].append(dauer_s)
    gesamt = sum(sum(v) for v in je_schritt.values())
    if je_schritt:
        z.append("")
        z.append("Zeit je Schritt (Median in den Takten, in denen er lief · Anteil an aller Arbeit):")
        for schritt, werte in sorted(je_schritt.items(), key=lambda p: -sum(p[1])):
            z.append(f"  {schritt:<14}{statistics.median(werte) * 1000:6.0f} ms  "
                     f"{100 * sum(werte) / max(gesamt, 1e-9):4.0f} %  ({len(werte)} Takte)")
    doppelt = sum(1 for t in takte
                  if sum(1 for name_, _ in t.get("zeiten") or [] if name_ in ABRUFE) >= 2)
    if doppelt:
        z.append(f"Zwei Bildabrufe in einem Takt: {doppelt} (der Körper fand nichts, "
                 f"das Gesicht holte eigene Bilder)")

    z.append("")
    zustaende = collections.Counter(t.get("zustand") or "?" for t in takte)
    z.append("Zustand: " + ", ".join(f"{k} {round(100 * v / n)} %"
                                     for k, v in zustaende.most_common()))
    finder = collections.Counter((t["ziel"]["name"] or "?").split(" ")[0].rstrip(",")
                                 for t in takte if t.get("ziel") and t["ziel"].get("echt"))
    if finder:
        z.append("Gesehen von: " + ", ".join(f"{k} {v}" for k, v in finder.most_common()))

    koerper = [k for t in takte for k in t.get("koerper") or []]
    if koerper:
        wege = collections.Counter(k.get("weg") for k in koerper)
        verworfen = collections.Counter(k["grund"] for k in koerper if not k.get("genommen"))
        z.append(f"Körper: {len(koerper)} erkannt, {sum(1 for k in koerper if k.get('genommen'))} "
                 f"genommen · " + ", ".join(f"{WEGE.get(w, w)} {n}" for w, n in wege.most_common() if w)
                 + (" · verworfen: " + ", ".join(f"{v}× {k}" for k, v in verworfen.most_common())
                    if verworfen else ""))
    gesicht_sichten = sum(1 for t in takte for s in t.get("sichten") or [] if "gesicht" in _finder_der(s))
    gesichter = [g for t in takte for g in t.get("gesichter") or []]
    if gesicht_sichten:
        verworfen = collections.Counter(g["grund"] for g in gesichter if not g.get("genommen"))
        z.append(f"Gesicht (im Lauf): {gesicht_sichten} Sichten, {len(gesichter)} Kästen, "
                 f"{sum(1 for g in gesichter if g.get('genommen'))} genommen"
                 + (" · verworfen: " + ", ".join(f"{v}× {k}" for k, v in verworfen.most_common())
                    if verworfen else ""))
    if any("gesichter_offline" in t for t in takte):
        koerper_sichten = [(t, s) for t in takte for s in t.get("sichten") or []
                           if "koerper" in _finder_der(s) and s.get("bild")]
        mit_gesicht = [(t, s) for t, s in koerper_sichten
                       if any(g["sicht"] == s.get("nr") and g.get("genommen")
                              for g in t.get("gesichter_offline") or [])]
        ohne_koerper = [1 for t, s in mit_gesicht
                        if not any(k.get("sicht") == s.get("nr") and k.get("genommen")
                                   for k in t.get("koerper") or [])]
        z.append(f"Gesicht offline auf den Körper-Sichten: in {len(mit_gesicht)} von "
                 f"{len(koerper_sichten)} ein genommenes Gesicht, davon {len(ohne_koerper)} dort, "
                 f"wo der Körper nichts hatte")

    schranken = collections.Counter((t.get("befehl") or {}).get("schranke") for t in takte)
    schranken.pop("", None)
    schranken.pop(None, None)
    if schranken:
        z.append("Gebremst von: " + ", ".join(f"{v}× {k}" for k, v in schranken.most_common()))

    luecken, beginn = [], None
    for takt in takte:
        gesehen = bool(takt.get("ziel") and takt["ziel"].get("echt"))
        if not gesehen and beginn is None:
            beginn = float(takt["t"])
        elif gesehen and beginn is not None:
            luecken.append((beginn, float(takt["t"]) - beginn))
            beginn = None
    if beginn is not None:
        luecken.append((beginn, float(takte[-1]["t"]) + _dauer(takte[-1]) - beginn))
    lang = [lk for lk in luecken if lk[1] >= LUECKE_S]
    if lang:
        laengste = max(lang, key=lambda lk: lk[1])
        z.append(f"Lücken ohne gesehenes Ziel ab {LUECKE_S:.0f} s: {len(lang)}, zusammen "
                 f"{sum(lk[1] for lk in lang):.0f} s, die längste {laengste[1]:.1f} s ab "
                 f"t = {laengste[0]:.1f} s")
    return "\n".join(z) + "\n"


# ------------------------------------------------------------------ Malen


def _schrift(groesse):
    from PIL import ImageFont

    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, groesse)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=groesse)
    except TypeError:
        return ImageFont.load_default()


def _gerade(zahl):
    zahl = int(round(zahl))
    return zahl + (zahl % 2)


def _zahl(wert, muster, sonst="—"):
    return sonst if wert is None else muster.format(wert)


class _Maler:
    """Baut die Videobilder. Das bemalte Panorama je Sicht wird einmal gemacht."""

    def __init__(self, lauf, takte, pano, breite, quelle):
        self.lauf, self.takte, self.pano, self.quelle = Path(lauf), takte, pano, quelle
        self.breite = _gerade(breite)
        form = next(((s["breite"], s["hoehe"]) for t in takte for s in t.get("sichten") or []
                     if s.get("breite") and s.get("hoehe")), None)
        if form is None and pano is not None and getattr(pano, "breite", None):
            form = (pano.breite, pano.hoehe)
        self.pano_breite, self.pano_hoehe = form or (16, 9)
        self.massstab = self.breite / float(self.pano_breite)
        self.bild_hoehe = _gerade(self.pano_hoehe * self.massstab)
        self.gross = _schrift(max(11, round(self.breite / 70)))
        self.klein = _schrift(max(10, round(self.breite / 95)))
        self.zeile = max(14, round(self.breite / 70 * 1.45))
        self.rand = max(6, round(self.breite / 160))
        self.hud_hoehe = _gerade(self.zeile * 6.4 + 2 * self.rand)
        self.hoehe = self.bild_hoehe + self.hud_hoehe
        self._zwischen = (None, None)
        self.t0 = float(takte[0]["t"])
        self.ende = float(takte[-1]["t"]) + _dauer(takte[-1])
        self._strahl = self._zeitstrahl()

    # -------------------------------------------------------- Panorama

    def _panorama(self, sicht):
        from PIL import Image, ImageDraw

        if self._zwischen[0] == sicht and self._zwischen[1] is not None:
            return self._zwischen[1]
        if sicht is None:
            bild = Image.new("RGB", (self.breite, self.bild_hoehe), (8, 8, 10))
            maler = ImageDraw.Draw(bild)
            text = ("kein Bild aufgenommen — alter Lauf ohne Folge-Aufnahme"
                    if self.quelle == "ereignisse" else "noch kein Bild")
            maler.text((self.rand * 2, self.bild_hoehe // 2), text, fill=GEDAEMPFT, font=self.gross)
        else:
            ti, nr = sicht
            takt = self.takte[ti]
            eintrag = next(s for s in takt["sichten"] if s.get("nr") == nr)
            roh = Image.open(self.lauf / folgeaufnahme.ORDNER / eintrag["bild"]).convert("RGB")
            bild = roh.resize((self.breite, self.bild_hoehe))
            roh.close()
            self._markiere(ImageDraw.Draw(bild), takt, nr)
        self._zwischen = (sicht, bild)
        return bild

    def _xy(self, x, y):
        return x * self.massstab, y * self.massstab

    def _etikett(self, maler, x, y, text, farbe):
        links, oben, rechts, unten = maler.textbbox((x, y), text, font=self.klein)
        maler.rectangle((links - 3, oben - 2, rechts + 3, unten + 2), fill=(0, 0, 0))
        maler.text((x, y), text, fill=farbe, font=self.klein)

    def _markiere(self, maler, takt, nr):
        spalte = getattr(self.pano, "spalte", None)
        if callable(spalte):
            x = spalte(0.0) * self.massstab
            maler.line((x, 0, x, self.bild_hoehe), fill=(200, 200, 200), width=1)
            ziel = takt.get("ziel")
            if ziel and ziel.get("peilung") is not None:
                roh_x = spalte(ziel["peilung"]) * self.massstab
                jetzt_x = spalte(ziel.get("peilung_jetzt", ziel["peilung"])) * self.massstab
                maler.line((roh_x, 0, roh_x, self.bild_hoehe), fill=GELB, width=1)
                maler.line((jetzt_x, 0, jetzt_x, self.bild_hoehe), fill=GELB, width=3)
                self._etikett(maler, jetzt_x + 4, 4, "Ziel nachgeführt", GELB)
        for g in takt.get("gesichter_offline") or []:
            if g.get("sicht") == nr:
                self._gesicht(maler, g, offline=True)
        for g in takt.get("gesichter") or []:
            if g.get("sicht") == nr:
                self._gesicht(maler, g, offline=False)
        for k in takt.get("koerper") or []:
            if k.get("sicht") == nr:
                self._koerper(maler, k)

    def _gesicht(self, maler, g, offline):
        x, y, b, h = g["kasten"]
        x1, y1 = self._xy(x, y)
        x2, y2 = self._xy(x + b, y + h)
        if offline:
            farbe = TUERKIS if g.get("genommen") else (0, 120, 130)
        else:
            farbe = BLAU if g.get("genommen") else GRAU
        maler.rectangle((x1, y1, x2, y2), outline=farbe, width=2 if offline else 3)
        vorn = "offline " if offline else ""
        if g.get("genommen"):
            text = (f"{vorn}Gesicht {g['score']:.2f} · {_zahl(g.get('abstand'), '{:.1f} m')} · "
                    f"{_zahl(g.get('hoehe'), '{:.2f} m hoch')}")
        else:
            text = (f"{vorn}Gesicht {g['score']:.2f} verworfen: {g.get('grund')} "
                    f"({_zahl(g.get('hoehe'), '{:.2f} m')})")
        self._etikett(maler, x1, max(0, y1 - self.zeile), text, farbe)

    def _koerper(self, maler, k):
        farbe = GRUEN if k.get("genommen") else ORANGE
        lm = k.get("landmarken")
        if lm:
            for a, b in KNOCHEN:
                if lm[a][2] is not None and lm[b][2] is not None and min(lm[a][2], lm[b][2]) > PRAESENZ:
                    maler.line((*self._xy(lm[a][0], lm[a][1]), *self._xy(lm[b][0], lm[b][1])),
                               fill=farbe, width=3)
        else:
            x1, y1, x2, y2 = k["kasten"]
            maler.rectangle((*self._xy(x1, y1), *self._xy(x2, y2)), outline=farbe, width=2)
        for punkt in (k.get("huefte"), k.get("schulter")):
            if punkt:
                px, py = self._xy(*punkt)
                maler.ellipse((px - 5, py - 5, px + 5, py + 5), outline=farbe, width=3)
        teil = "Hüfte" if k.get("punkt") == "huefte" else "Schulter"
        weg = f" · {WEGE[k['weg']]}" if k.get("weg") in WEGE else ""
        if k.get("genommen"):
            text = (f"Körper {k['conf']:.2f} · {_zahl(k.get('abstand'), '{:.2f} m')} · {teil} "
                    f"{_zahl(k.get('hoehe'), '{:.2f} m hoch')}{weg}")
        else:
            text = (f"Körper {k['conf']:.2f} verworfen: {k.get('grund')} "
                    f"({teil} {_zahl(k.get('hoehe'), '{:.2f} m')}){weg}")
        # UNTER den Körper: darüber steht das Gesicht mit seinem eigenen Etikett.
        x1, y2 = self._xy(k["kasten"][0], k["kasten"][3])
        self._etikett(maler, x1, min(y2 + 4, self.bild_hoehe - self.zeile), text, farbe)

    # -------------------------------------------------------- Leiste

    def _zeitstrahl(self):
        """Der ganze Lauf als Streifen: oben der Zustand, unten wer das Ziel lieferte."""
        from PIL import Image, ImageDraw

        breite = self.breite - 2 * self.rand
        hoehe = max(10, self.zeile - 4)
        streifen = Image.new("RGB", (breite, hoehe), (40, 42, 48))
        maler = ImageDraw.Draw(streifen)
        spanne = max(self.ende - self.t0, 1e-9)
        for i, takt in enumerate(self.takte):
            a = float(takt["t"])
            b = float(self.takte[i + 1]["t"]) if i + 1 < len(self.takte) else self.ende
            x1 = int((a - self.t0) / spanne * breite)
            x2 = max(x1 + 1, int((b - self.t0) / spanne * breite))
            maler.rectangle((x1, 0, x2, hoehe // 2), fill=ZUSTAND_FARBE.get(takt.get("zustand"), GRAU))
            ziel = takt.get("ziel")
            if ziel and ziel.get("echt"):
                farbe = GRUEN if (ziel.get("name") or "").startswith("Körper") else TUERKIS
                maler.rectangle((x1, hoehe // 2 + 1, x2, hoehe), fill=farbe)
        return streifen

    def _balken(self, maler, x, y, takt):
        breite = self.breite - 2 * self.rand - x
        hoehe = max(8, self.zeile - 6)
        maler.rectangle((x, y, x + breite, y + hoehe), fill=(40, 42, 48))
        zeiten = _zeiten_je_takt(takt)
        teile = []
        for name, schritte, farbe in GRUPPEN:
            dauer = sum(zeiten.pop(s, 0.0) for s in schritte)
            if dauer > 0:
                teile.append((name, dauer, farbe))
        rest = sum(zeiten.values())
        if rest > 0:
            teile.append(("anderes", rest, GRAU))
        if not teile and _dauer(takt):
            teile.append(("ganzer Takt, keine Aufteilung", _dauer(takt), GRAU))
        links = x
        for _name, dauer, farbe in teile:
            rechts = min(links + dauer / BALKEN_S * breite, x + breite)
            if rechts > links:         # ueber 1 s endet der Balken am Rand, der Text sagt den Rest
                maler.rectangle((links, y, rechts, y + hoehe), fill=farbe)
            links = rechts
        summe = sum(d for _, d, _ in teile)
        text = f"{summe * 1000:.0f} ms: " + " · ".join(f"{n} {d * 1000:.0f}" for n, d, _ in teile)
        return text

    def bild(self, t, ti, sicht):
        import numpy as np
        from PIL import Image, ImageDraw

        leinwand = Image.new("RGB", (self.breite, self.hoehe), HINTERGRUND)
        leinwand.paste(self._panorama(sicht), (0, 0))
        maler = ImageDraw.Draw(leinwand)
        takt = self.takte[ti]
        x, y = self.rand, self.bild_hoehe + self.rand

        zustand = takt.get("zustand") or "?"
        kopf = f"t = {t:6.1f} s   Takt {takt.get('takt', ti + 1)}   "
        maler.text((x, y), kopf, fill=TEXT, font=self.gross)
        bx = x + maler.textlength(kopf, font=self.gross)
        breite = maler.textlength(f" {zustand} ", font=self.gross)
        maler.rectangle((bx, y, bx + breite, y + self.zeile - 2),
                        fill=ZUSTAND_FARBE.get(zustand, GRAU))
        maler.text((bx, y), f" {zustand} ", fill=(0, 0, 0), font=self.gross)
        ziel = takt.get("ziel")
        maler.text((bx + breite + 12, y), (ziel or {}).get("name") or "kein Ziel",
                   fill=TEXT, font=self.gross)

        from spotlab.workshop.folgen import MIN_ABSTAND_M, WUNSCH_ABSTAND_M

        y += self.zeile
        if ziel:
            text = (f"Abstand {_zahl(ziel.get('abstand'), '{:.2f} m')} (Wunsch {WUNSCH_ABSTAND_M:.1f}, "
                    f"nie unter {MIN_ABSTAND_M:.1f})   Peilung {_zahl(ziel.get('peilung'), '{:+.0f}°')} "
                    f"→ nachgeführt {_zahl(ziel.get('peilung_jetzt'), '{:+.0f}°')}   Oberkante "
                    f"{_zahl(ziel.get('bild_oben'), '{:.0f}°')}")
        else:
            text = "kein Ziel — Spot steht und sucht"
        maler.text((x, y), text, fill=TEXT, font=self.gross)

        y += self.zeile
        befehl = takt.get("befehl") or {}
        nick = befehl.get("nick_grad")
        text = (f"Befehl  vx {_zahl(befehl.get('vx'), '{:.2f} m/s')}   wz "
                f"{_zahl(befehl.get('wz_grad'), '{:+.0f}°/s')}   Nase "
                f"{_zahl(None if nick is None else -nick, '{:.0f}° hoch')}")
        if befehl.get("schranke"):
            text += f"   gebremst: {befehl['schranke']}"
        if takt.get("geste"):
            text += f"   Geste: {takt['geste']}"
        maler.text((x, y), text, fill=ORANGE if befehl.get("schranke") else TEXT, font=self.gross)

        y += self.zeile
        etikett = "Arbeit "
        maler.text((x, y), etikett, fill=GEDAEMPFT, font=self.klein)
        balken_x = x + int(maler.textlength("Arbeit ", font=self.klein)) + 4
        text = self._balken(maler, balken_x, y + 2, takt)
        maler.text((balken_x + 4, y + 1), text, fill=TEXT, font=self.klein,
                   stroke_width=2, stroke_fill=(0, 0, 0))

        y += self.zeile
        leinwand.paste(self._strahl, (x, y))
        spanne = max(self.ende - self.t0, 1e-9)
        px = x + int((t - self.t0) / spanne * self._strahl.width)
        maler.line((px, y - 2, px, y + self._strahl.height + 2), fill=(255, 255, 255), width=2)
        maler.text((x, y + self._strahl.height + 3), LEGENDE, fill=GEDAEMPFT, font=self.klein)
        return np.asarray(leinwand)


# ------------------------------------------------------------------ Film


def _imageio():
    try:
        import imageio.v2 as imageio
    except ImportError:
        return None
    return imageio


def _ffmpeg_schreiber(pfad, fps):
    imageio = _imageio()
    if imageio is None:
        raise SpotlabError("Für das Video fehlt imageio mit ffmpeg: pip install \"imageio[ffmpeg]\"")
    # macro_block_size=1: sonst skaliert ffmpeg auf ein Vielfaches von 16, mit einer
    # Warnung, die niemand liest. Die Masse sind gerade, das genügt libx264.
    return imageio.get_writer(str(pfad), fps=fps, codec="libx264", quality=8,
                              macro_block_size=1, pixelformat="yuv420p")


def film(lauf_dir, ziel=None, fps=FPS, breite=BREITE, gesicht=True, schreiber=None,
         melde=print, fortschritt=None, kaesten_holen=None):
    """Das Video und den Bericht schreiben. Rückgabe {pfad, bilder, dauer_s, bericht, quelle}."""
    lauf = Path(lauf_dir)
    takte, quelle = takte_laden(lauf)
    pano = None
    if quelle == "aufnahme":
        try:
            pano = folgeaufnahme.panorama_laden(lauf)
        except Exception as fehler:
            melde(f"Die Kalibrierung liess sich nicht laden ({fehler}) — ohne Peilungslinien.")
        if gesicht and pano is None:
            melde("Ohne Kalibrierung (folgen/kameras.json) kein Gesicht offline.")
        elif gesicht:
            try:
                erkenner_ = None if kaesten_holen else _gesichtserkenner(pano)
                anzahl = gesicht_offline(lauf, takte, pano, erkenner_, kaesten_holen)
                melde(f"Gesicht offline auf {anzahl} Körper-Sichten gerechnet.")
            except SpotlabError as fehler:
                melde(f"Gesicht offline übersprungen: {fehler}")
    text = bericht(takte, lauf.name)
    if quelle == "ereignisse":
        text = ("Alter Lauf ohne Folge-Aufnahme: nur die Takte mit Ziel und das Wegbleiben stehen "
                "darin — ohne Bilder, ohne Zeiten je Schritt, 'Takt zu Takt' misst auch die Lücken.\n"
                + text)
    ziel = Path(ziel) if ziel else lauf / DATEI
    (ziel.parent / BERICHT).write_text(text, encoding="utf-8")
    temporaer = ziel.with_name(ziel.stem + ".tmp" + ziel.suffix)
    plan = zeitplan(takte, fps)
    maler = _Maler(lauf, takte, pano, breite, quelle)
    with (schreiber or _ffmpeg_schreiber)(temporaer, fps) as ausgabe:
        for nummer, (t, ti, sicht) in enumerate(plan):
            ausgabe.append_data(maler.bild(t, ti, sicht))
            if fortschritt is not None and nummer % 100 == 0:
                fortschritt(nummer, len(plan))
    if temporaer.exists():
        os.replace(temporaer, ziel)
    return {"pfad": ziel, "bilder": len(plan), "dauer_s": round(len(plan) / fps, 2),
            "bericht": text, "quelle": quelle}


def main(argv=None):
    teiler = argparse.ArgumentParser(prog="python -m spotlab.workshop.folgenfilm",
                                     description="Die Folge-Aufnahme eines Laufs als Video und Bericht.")
    teiler.add_argument("lauf", help="Lauf-Verzeichnis (…/runs/<id>)")
    teiler.add_argument("--fps", type=int, default=FPS)
    teiler.add_argument("--breite", type=int, default=BREITE)
    teiler.add_argument("--ohne-gesicht", action="store_true",
                        help="YuNet nicht nachträglich auf den Körper-Sichten laufen lassen")
    teiler.add_argument("--out", default=None, help=f"Zieldatei (Vorgabe: <lauf>/{DATEI})")
    args = teiler.parse_args(argv)

    def fortschritt(nummer, gesamt):
        print(f"  Bild {nummer}/{gesamt}", flush=True)

    try:
        ergebnis = film(args.lauf, ziel=args.out, fps=args.fps, breite=args.breite,
                        gesicht=not args.ohne_gesicht, fortschritt=fortschritt)
    except SpotlabError as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1
    print(ergebnis["bericht"])
    print(f"Video: {ergebnis['pfad']} ({ergebnis['bilder']} Bilder, {ergebnis['dauer_s']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
