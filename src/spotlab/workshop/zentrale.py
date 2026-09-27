"""Die Steuerzentrale: Lagebild und Fahren in EINEM Programm — der Kern des Tabs „Fahren“.

Der Tab startet diese Datei als PAKETCODE mit `--runs <Arbeitsordner>/Beispiele/runs`,
wie den Akku-Knopf (`workshop/lage.py`): der Knopf verspricht ein bestimmtes Verhalten,
und eine Kopie im Arbeitsordner könnte veraltet sein. Am echten Spot oder im Übungsraum
— welches, sagt `SPOTLAB_BACKEND` vom Startweg; die Vorgabe im Tab ist der Übungsraum.

Die Platte ist der einzige Kanal zum Tab, in beide Richtungen (`record/zentrale.py`):

    fahrt.json       Tab → hier  Tasten W A S D Q E, 20-mal je Sekunde gelesen
    klickziel.json   Tab → hier  Klick in die Draufsicht, mit Lebenszeichen
    aktion.json      Tab → hier  Licht, Ton und die Suchstufe, jede Nummer einmal
    lagebild.json    hier → Tab  Skizze, Spot, Tags, Menschen, Klickfahrt, Fähigkeiten (2-mal je s)
    lagebild.png     hier → Tab  die Skizze (`workshop/skizze.py`)

**Folgen per Klick** (Teil 2): ein Klick auf einen Menschen (`klickziel.json` mit
`art = "mensch"`) übergibt an den Folgemodus (`folgen.folge` mit dem Körperfinder,
eingewickelt in `workshop/klickfolgen.py`, damit es DER Angeklickte ist). Er folgt, bis
Stopp, eine Taste, ein neuer Klick, ein fehlendes Lebenszeichen des Tabs — dasselbe wie bei
der Klickfahrt — oder bis der Angeklickte `START_FRIST_S` lang nicht zu finden war. Der
Grund steht im Lagebild. Die Suche pausiert so lange; was der Folgemodus sieht, steht im
Lagebild, der Gefolgte hervorgehoben. Die LEDs gehören dann dem Folgemodus, danach kommt
die im Tab gewählte Farbe zurück.

**Vorrang:** eine Taste vor der Klickfahrt vor dem Stillstand. Eine Taste bricht die
Klickfahrt ab. Die Klickfahrt fährt nur, solange das Lebenszeichen des Tabs frisch ist
(`record/zentrale.TOTMANN_S`), und nur mit den Schranken des Folgens (Gitter voraus aus
dem letzten Hindernisgitter, Kopfraum) — unlesbar heisst stehen. Die Tasten fahren wie
in `fahren.py` ohne diese Schranken: dort steuert der Mensch.

Die Wahrnehmung läuft in einem eigenen Faden (Gitter, Lage, Tags, Kopfraum dauern am
Roboter je 30–100 ms), der Fahrtakt hier. Die MENSCHENSUCHE (Teil 2,
`workshop/menschensuche.py`) hat einen dritten Faden: eine Runde kostet vorne rund 0.3 s,
rundum über eine Sekunde, und sie darf weder den Fahrtakt noch das Lagebild aufhalten.
Wie viel sie rechnet, sagt die Stufe aus dem Tab (Vorgabe hier: aus). Ein Mensch steht
bis `MENSCH_ALTER_S` im Lagebild und wird blasser; ein neuer Fund in `GLEICH_M` ersetzt
ihn. Am Ende hält Spot IMMER — erst anhalten, dann Licht aus, dann die Fäden abbauen.
"""

import math
import threading
import time
from pathlib import Path

from spotlab.backends.base import Capability
from spotlab.errors import SpotlabError
from spotlab.record import fahrt
from spotlab.record import zentrale as protokoll
from spotlab.record.run import STOPP_DATEI
from spotlab.workshop import blick, folgen, klickfahrt, klickfolgen, menschensuche
from spotlab.workshop import skizze as skizzenmodul

SKRIPT = Path(__file__)
TAKT_S = 0.05
WAHRNEHMUNG_S = 0.5
KOPFRAUM_S = 1.0
KOPFRAUM_GILT_S = 3.0      # älter oder nie gemessen: die Klickfahrt steht (fail-closed)
GITTER_GILT_S = 1.5        # ebenso für das Hindernisgitter
LICHTFARBEN = {"blau": "blue", "gruen": "green", "gelb": "yellow", "rot": "red"}
SUCHE_LEERLAUF_S = 0.2     # aus, ohne Kameras oder beim Folgen: so oft schaut der Faden nach
SUCHE_MIN_S = 0.02         # auch „so oft es geht“ lässt den anderen Fäden Luft
MENSCH_ALTER_S = 3.0       # so lange steht ein Mensch ohne neuen Fund im Lagebild
GLEICH_M = 1.0             # ein neuer Fund so nah an einem alten ist derselbe Mensch
START_FRIST_S = 5.0        # so lange sucht der Folgemodus den Angeklickten, dann gibt er auf
KEINE_KAMERAS = ("Keine Bild- und Tiefenkameras (Übungsraum) — Menschen sucht nur der "
                 "echte Spot.")


def _im_hintergrund(arbeit):
    threading.Thread(target=arbeit, daemon=True, name="zentrale-ton").start()


class Zentrale:
    def __init__(self, spot, lauf_dir, jetzt=time.time, melde=print, licht=None,
                 hintergrund=_im_hintergrund, suche=None, folgen_mit=None,
                 koerper_finder=None):
        self.spot = spot
        self.lauf_dir = Path(lauf_dir)
        self.jetzt = jetzt
        self.melde = melde
        self.hintergrund = hintergrund
        self.skizze = skizzenmodul.Skizze()
        self.klick = klickfahrt.Klickfahrt()
        self._sperre = threading.Lock()
        self._gitter = None
        self._gitter_t = None
        self._lage = None
        self._tags = {}
        self._kopf = (False, "Kopfraum noch nicht geprüft")
        self._kopf_t = None
        self._klick_nummer = None
        self._klickziel = None     # das zuletzt LESBARE Klickziel (siehe `takt`)
        self._aktion_nummer = None
        self._faehrt = False
        self._gesagt = set()
        self._suchstufe = "aus"
        self._menschen = []
        self._runde_s = None
        self._suche_grund = None
        self._folgt = False
        self._gefolgt = None       # der Mensch, dem Spot gerade folgt (für das Lagebild)
        self._lichtwunsch = None   # die zuletzt im Tab gewählte Farbe
        self._laeuft = lambda: True
        self._folgen_mit = folgen_mit or folgen.folge
        self._koerper_finder = koerper_finder or folgen.koerper_finder
        self.faehigkeiten = self._faehigkeiten()
        self._suche_kann = self._kann_suchen()
        if suche is None and self._suche_kann:
            suche = menschensuche.Menschensuche(spot)
        self._suche = suche
        if licht is None and self.faehigkeiten["licht"]:
            from spotlab.api.signals import Statuslicht

            licht = Statuslicht(spot)
        self._licht = licht

    def _faehigkeiten(self):
        def gefragt(merkmal):
            try:
                return bool(self.spot.supports(merkmal))
            except Exception:
                return False

        try:
            kann = self.spot.backend.capabilities()
        except Exception:
            kann = Capability.NONE
        return {"licht": gefragt("lights"), "ton": gefragt("beep"),
                "kamera": bool(kann & Capability.CAMERAS)}

    def _kann_suchen(self):
        """Bild- UND Tiefenkameras: ohne Tiefe gäbe es keinen Abstand, also keinen Ort."""
        try:
            kann = self.spot.backend.capabilities()
        except Exception:
            return False
        bilder = Capability.GRAY_CAMERAS | Capability.COLOR_CAMERAS
        return bool(kann & Capability.DEPTH_CAMERAS) and bool(kann & bilder)

    def _einmal(self, schluessel, text):
        if schluessel not in self._gesagt:
            self._gesagt.add(schluessel)
            self.melde(text)

    # ------------------------------------------------------------ Wahrnehmung

    def wahrnehmen(self, t=None):
        """Gitter, Lage, Tags (und alle KOPFRAUM_S den Kopfraum) holen, Skizze nachführen,
        Lagebild schreiben. Ein Fehler an einer Quelle lässt die anderen weiterlaufen."""
        t = self.jetzt() if t is None else t
        try:
            gitter = self.spot.obstacles()
        except Exception as fehler:
            gitter = None
            self._einmal("gitter", f"Kein Hindernisgitter ({fehler}) — die Skizze bleibt leer; "
                                   f"die Tasten fahren, die Klickfahrt lehnt ab.")
        lage = self._lage_jetzt()
        try:
            tags = self.spot.tags()
        except Exception:
            tags = []
        kopf = None
        if self._kopf_t is None or t - self._kopf_t >= KOPFRAUM_S:
            try:
                kopf = folgen.kopfraum_frei(self.spot)
            except Exception as fehler:
                kopf = (False, f"Kopfraum nicht lesbar ({fehler})")
        with self._sperre:
            if gitter is not None:
                self.skizze.aufnehmen(gitter, t)
                self._gitter, self._gitter_t = gitter, t
            if lage is not None:
                self._lage = lage
            for tag in tags:
                if getattr(tag, "world_xy", None):
                    self._tags[int(tag.id)] = (float(tag.world_xy[0]), float(tag.world_xy[1]))
            if kopf is not None:
                self._kopf, self._kopf_t = kopf, t
            daten, bild = self._lagebild(t)
        protokoll.schreibe_lagebild(self.lauf_dir, daten, bild)

    def _lagebild(self, t):
        """(Beschreibung, PNG-Bytes oder None) — unter der Sperre gerufen."""
        skizze = self.skizze
        leer = skizze.leer
        hoehe, breite = (0, 0) if leer else skizze.zustand.shape
        spot = None
        if self._lage is not None:
            x, y, gier = self._lage
            spot = {"x": round(x, 3), "y": round(y, 3), "gier_grad": round(math.degrees(gier), 1)}
        daten = {
            "t": t,
            "rahmen": "vision",
            "zelle_m": skizze.zelle_m,
            "ursprung": None if leer else [skizze.ursprung[0], skizze.ursprung[1]],
            "breite": breite,
            "hoehe": hoehe,
            "spot": spot,
            "tags": [{"id": i, "x": xy[0], "y": xy[1]} for i, xy in sorted(self._tags.items())],
            "klickfahrt": self.klick.stand.als_daten(),
            "faehigkeiten": dict(self.faehigkeiten),
            "menschen": [{"x": round(m.x, 3), "y": round(m.y, 3),
                          "alter_s": round(max(0.0, t - m.t), 2), "quelle": m.quelle,
                          "gefolgt": m is self._gefolgt}
                         for m in self._menschen if t - m.t <= MENSCH_ALTER_S],
            "suche": {"stufe": self._suchstufe, "runde_s": self._runde_s,
                      "kann": self._suche_kann,
                      "grund": self._suche_grund if self._suche_kann else KEINE_KAMERAS},
            "karte": None,            # Teil 3
        }
        return daten, (None if leer else skizze.png(t))

    # ------------------------------------------------------------ Menschensuche

    def suchen(self, t=None):
        """Eine Runde der Menschensuche — oder keine (aus, ohne Kameras, beim Folgen).
        Gibt zurück, wie lange der Faden danach wartet. Wirft nie."""
        stufe = self._suchstufe
        if stufe == "aus" or not self._suche_kann or self._folgt or self._suche is None:
            return SUCHE_LEERLAUF_S
        anfang = self.jetzt()
        t = anfang if t is None else t
        try:
            menschen, gruende = self._suche.runde(stufe, t)
        except Exception as fehler:
            menschen, gruende = [], {"Suche": f"{type(fehler).__name__}: {fehler}"}
            self._einmal("suche_fehler", f"Die Menschensuche stolpert ({fehler}) — Spot fährt "
                                         f"weiter, nur ohne Menschen im Lagebild.")
        dauer = max(0.0, self.jetzt() - anfang)
        with self._sperre:
            if self._suchstufe == stufe:       # inzwischen aus? dann nichts eintragen
                self._merke_menschen(menschen, t)
            self._runde_s = round(dauer, 2)
            self._suche_grund = "; ".join(f"{q}: {g}" for q, g in gruende.items()) or None
        return menschensuche.pause_s(stufe)

    def _merke_menschen(self, neu, t):
        """Neue Funde ersetzen alte in `GLEICH_M`; die übrigen bleiben bis `MENSCH_ALTER_S`."""
        bleiben = [m for m in self._menschen
                   if t - m.t <= MENSCH_ALTER_S
                   and all(math.hypot(m.x - n.x, m.y - n.y) > GLEICH_M for n in neu)]
        self._menschen = bleiben + list(neu)

    def _suche_schleife(self, halt):
        while not halt.is_set():
            halt.wait(max(self.suchen(), SUCHE_MIN_S))

    def _lage_jetzt(self):
        try:
            return folgen._lage_im_gitter(self.spot)
        except Exception:
            return None

    # ------------------------------------------------------------ Takt

    def takt(self, t=None):
        """Ein Fahrtakt: Aktionen, Klickziel, dann Taste > Klickfahrt > Stillstand."""
        t = self.jetzt() if t is None else t
        self._aktionen()
        befehl = fahrt.lies(self.lauf_dir, jetzt=self.jetzt)
        # Unter Windows liest der Takt die Datei manchmal genau beim Ersetzen (20-mal je
        # Sekunde gelesen, 5-mal geschrieben): dann gilt das zuletzt gelesene weiter. Sein
        # Lebenszeichen altert trotzdem -- der Totmann bleibt scharf. Ohne diese Zeile brach
        # ein einziger Lesekonflikt die Klickfahrt ab (Kette im Übungsraum, 27.09.2026).
        kz = protokoll.lies_klickziel(self.lauf_dir) or self._klickziel
        self._klickziel = kz
        if kz is not None and kz.nummer != self._klick_nummer:
            self._neues_klickziel(kz, t)
            if kz.art == "mensch" and kz.ziel is not None and befehl == fahrt.STILL \
                    and self._suche_kann:
                self._folge_mensch(kz)
                return
        if befehl != fahrt.STILL:
            with self._sperre:
                self.klick.abbrechen("eine Taste hat übernommen")
            vx, vy, wz = befehl
            self.spot.walk(vx=vx, vy=vy, wz=wz, stop=False)
            self._faehrt = True
            return
        if self.klick.unterwegs:
            if not protokoll.lebt(kz, jetzt=self.jetzt):
                with self._sperre:
                    self.klick.abbrechen("kein Lebenszeichen vom Tab (Reiter gewechselt oder "
                                         "Fenster nicht aktiv) — Spot steht")
            else:
                vx, wz = self._klickschritt(t, kz.stufe)
                if (vx, wz) != (0.0, 0.0):
                    self.spot.walk(vx=vx, vy=0.0, wz=wz, stop=False)
                    self._faehrt = True
                    return
        if self._faehrt:
            self.spot.stop()
            self._faehrt = False

    def _neues_klickziel(self, kz, t):
        self._klick_nummer = kz.nummer
        if kz.ziel is None:
            with self._sperre:
                self.klick.abbrechen("im Tab abgebrochen")
            return
        if kz.art == "mensch":
            with self._sperre:
                self.klick.abbrechen("jetzt folgt Spot einem Menschen")
                if not self._suche_kann:
                    self.klick.stand = klickfahrt.Stand(nummer=kz.nummer, zustand="abgelehnt",
                                                        grund=KEINE_KAMERAS, ziel=kz.ziel)
            return                       # `takt` übergibt an den Folgemodus
        lage = self._lage_jetzt()
        with self._sperre:
            if lage is None:
                self.klick.stand = klickfahrt.Stand(nummer=kz.nummer, zustand="abgelehnt",
                                                    grund="Spots Lage ist nicht lesbar",
                                                    ziel=kz.ziel)
                return
            self.klick.neues_ziel(kz.nummer, kz.ziel, lage, self.skizze, t)

    def _klickschritt(self, t, stufe):
        try:
            faktor = fahrt.faktor_der_stufe(stufe)
        except ValueError:
            faktor = fahrt.faktor_der_stufe("langsam")
        lage = self._lage_jetzt()
        with self._sperre:
            if lage is None:
                self.klick.abbrechen("Spots Lage ist nicht lesbar")
                return 0.0, 0.0
            frei = None
            if self._gitter is not None and t - self._gitter_t <= GITTER_GILT_S:
                try:
                    frei = self._gitter.free_distance(lage[0], lage[1], math.degrees(lage[2]))
                except Exception:
                    frei = None
            kopf_frei, kopf_grund = self._kopf
            if self._kopf_t is None or t - self._kopf_t > KOPFRAUM_GILT_S:
                kopf_frei, kopf_grund = False, "Kopfraum nicht frisch geprüft"
            return self.klick.schritt(lage, self.skizze, t, frei, faktor,
                                      kopf_frei=kopf_frei, kopf_grund=kopf_grund)

    # ------------------------------------------------------------ Folgen per Klick

    def _folge_mensch(self, kz):
        """Der Folgemodus übernimmt, bis `laeuft` einen Grund hat aufzuhören. Blockiert."""
        anfang = self.jetzt()
        ende = {"grund": ""}
        zuletzt = {"kz": kz}

        def gesehen(punkte, gewaehlt):
            t = self.jetzt()
            menschen = [menschensuche.Mensch(x, y, d, b, "vorne", t) for x, y, d, b in punkte]
            gefolgt = None
            if gewaehlt is not None:
                gefolgt = min(menschen, key=lambda m: math.hypot(m.x - gewaehlt[0],
                                                                 m.y - gewaehlt[1]))
            with self._sperre:
                self._merke_menschen(menschen, t)
                if gefolgt is not None:
                    self._gefolgt = gefolgt

        finder = klickfolgen.KlickFinder(self._koerper_finder(), kz.ziel, gesehen=gesehen)

        def stand(grund):
            with self._sperre:
                self.klick.stand = klickfahrt.Stand(nummer=kz.nummer, zustand="folgt",
                                                    grund=grund, ziel=kz.ziel)

        def laeuft():
            if not self._laeuft():
                ende["grund"] = "Stopp"
                return False
            self._aktionen()
            if fahrt.lies(self.lauf_dir, jetzt=self.jetzt) != fahrt.STILL:
                ende["grund"] = "eine Taste hat übernommen"
                return False
            neu = protokoll.lies_klickziel(self.lauf_dir) or zuletzt["kz"]
            zuletzt["kz"] = neu
            if neu.nummer != kz.nummer:
                ende["grund"] = "ein neuer Klick"
                return False
            if not protokoll.lebt(neu, jetzt=self.jetzt):
                ende["grund"] = ("kein Lebenszeichen vom Tab (Reiter gewechselt oder Fenster "
                                 "nicht aktiv) — Spot steht")
                return False
            if finder.treffer == 0 and self.jetzt() - anfang > START_FRIST_S:
                ende["grund"] = (f"der angeklickte Mensch war {START_FRIST_S:.0f} s lang nicht "
                                 f"zu finden")
                return False
            stand("folgt dem angeklickten Menschen" if finder.treffer
                  else "sucht den angeklickten Menschen")
            return True

        stand("sucht den angeklickten Menschen")
        with self._sperre:
            self._folgt = True
            self._menschen = []
        try:
            gesten = folgen.gesten_leser(finder)
        except Exception:
            gesten = None
        try:
            self._folgen_mit(self.spot, finder=finder, melde=self.melde, laeuft=laeuft,
                             gesten=gesten, licht=self._licht if self._licht is not None else False)
        except Exception as fehler:
            ende["grund"] = f"der Folgemodus ist gescheitert ({fehler})"
        finally:
            self._faehrt = False             # `folge()` hält am Ende immer an
            with self._sperre:
                self._folgt = False
                self._gefolgt = None
                self.klick.stand = klickfahrt.Stand(
                    nummer=kz.nummer, zustand="abgebrochen",
                    grund=f"Folgen beendet: {ende['grund'] or 'der Folgemodus hat aufgehört'}")
            self._licht_zurueck()

    def _licht_zurueck(self):
        """Nach dem Folgen die im Tab gewählte Farbe wieder setzen (`folge()` löscht die LEDs)."""
        if self._licht is None or self._lichtwunsch in (None, "aus"):
            return
        try:
            self._licht.setze(LICHTFARBEN.get(self._lichtwunsch, "blue"))
        except Exception as fehler:
            self._einmal("licht_fehler", f"Das Licht geht nicht ({fehler}) — Spot fährt weiter.")

    # ------------------------------------------------------------ Licht und Ton

    def _aktionen(self):
        aktion = protokoll.lies_aktion(self.lauf_dir)
        if aktion is None or aktion["nummer"] == self._aktion_nummer:
            return
        self._aktion_nummer = aktion["nummer"]
        if aktion["art"] == "licht":
            self._lichtwunsch = aktion["farbe"]
            if self._folgt:
                return                       # die LEDs gehören gerade dem Folgemodus
            if self._licht is None:
                self._einmal("licht", "Licht gibt es nur am echten Spot (Dienst audio-visual).")
                return
            try:
                if aktion["farbe"] == "aus":
                    self._licht.aus()
                else:
                    self._licht.setze(LICHTFARBEN.get(aktion["farbe"], "blue"))
            except Exception as fehler:
                self._einmal("licht_fehler", f"Das Licht geht nicht ({fehler}) — Spot fährt weiter.")
        elif aktion["art"] == "suche":
            stufe = aktion.get("stufe")
            if stufe in protokoll.SUCHSTUFEN:
                with self._sperre:
                    self._suchstufe = stufe
                    if stufe == "aus":
                        self._menschen = []
                        self._suche_grund = None
        elif aktion["art"] == "ton":
            if not self.faehigkeiten["ton"]:
                self._einmal("ton", "Ton gibt es nur am echten Spot (Dienst audio-visual).")
                return

            def piepen():
                try:
                    self.spot.beep()
                except Exception as fehler:
                    self._einmal("ton_fehler", f"Der Ton geht nicht ({fehler}).")

            self.hintergrund(piepen)

    # ------------------------------------------------------------ Schleife

    def _wahrnehmung_schleife(self, halt):
        while not halt.is_set():
            try:
                self.wahrnehmen()
            except Exception as fehler:
                self._einmal("wahrnehmung", f"Die Wahrnehmung stolpert ({fehler}).")
            halt.wait(WAHRNEHMUNG_S)

    def lauf(self, laeuft, schlaf=time.sleep, takt_s=TAKT_S, mit_blick=True):
        """Fahrtakt hier, Wahrnehmung im Faden, bis `laeuft()` falsch ist. Am Ende hält Spot."""
        self._laeuft = laeuft
        seher = blick.starte(self.spot, self.lauf_dir) if mit_blick else None
        halt = threading.Event()
        faden = threading.Thread(target=self._wahrnehmung_schleife, args=(halt,), daemon=True,
                                 name="zentrale-wahrnehmung")
        faden.start()
        sucher = threading.Thread(target=self._suche_schleife, args=(halt,), daemon=True,
                                  name="zentrale-menschensuche")
        sucher.start()
        try:
            while laeuft():
                self.takt()
                schlaf(takt_s)
        finally:
            try:
                self.spot.stop()                  # ZUERST anhalten
            finally:
                if self._licht is not None:
                    try:
                        self._licht.aus()
                    except Exception:
                        pass
                halt.set()
                faden.join(timeout=2.0)
                sucher.join(timeout=2.0)
                if seher is not None:
                    seher.beenden()


# ------------------------------------------------------------ Hauptprogramm


def argumente(argv):
    """(runs, uebernehmen) aus der Kommandozeile: `zentrale.py [--runs ORDNER] [--uebernehmen]`."""
    rest, runs, uebernehmen = list(argv), None, False
    while rest:
        wort = rest.pop(0)
        if wort == "--runs":
            if not rest:
                raise SpotlabError("Nach --runs fehlt der Ordner.")
            runs = rest.pop(0)
        elif wort == "--uebernehmen":
            uebernehmen = True
        else:
            raise SpotlabError(f"Unbekannte Option {wort}.")
    return runs, uebernehmen


def _hauptprogramm(argv=None):
    """Das Programm hinter dem Tab — PAKETCODE, siehe oben. Der Lauf landet unter `--runs`."""
    import os
    import sys

    import spotlab

    runs, uebernehmen = argumente(sys.argv[1:] if argv is None else argv)
    runs = runs or os.environ.get("SPOTLAB_RUNS_DIR") or str(Path.cwd() / "runs")
    with spotlab.connect(runs_dir=runs, script=__file__, take=uebernehmen) as spot:
        spot.power_on()
        spot.stand()
        print("Steuerzentrale: W/S vor und zurück · A/D seitwärts · Q/E drehen · "
              "Klick in die Draufsicht: dorthin gehen · Leertaste hält")
        lauf_dir = spot.recorder.dir
        stopp = lauf_dir / STOPP_DATEI
        Zentrale(spot, lauf_dir).lauf(laeuft=lambda: not stopp.exists())
        spot.sit()


if __name__ == "__main__":
    _hauptprogramm()
