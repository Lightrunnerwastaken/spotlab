"""Die Steuerzentrale: Lagebild und Fahren in EINEM Programm — der Kern des Tabs „Fahren“.

Der Tab startet diese Datei als PAKETCODE mit `--runs <Arbeitsordner>/Beispiele/runs`,
wie den Akku-Knopf (`workshop/lage.py`): der Knopf verspricht ein bestimmtes Verhalten,
und eine Kopie im Arbeitsordner könnte veraltet sein. Am echten Spot oder im Übungsraum
— welches, sagt `SPOTLAB_BACKEND` vom Startweg; die Vorgabe im Tab ist der Übungsraum.

Die Platte ist der einzige Kanal zum Tab, in beide Richtungen (`record/zentrale.py`):

    fahrt.json       Tab → hier  Tasten W A S D Q E, 20-mal je Sekunde gelesen
    klickziel.json   Tab → hier  Klick in die Draufsicht, mit Lebenszeichen
    aktion.json      Tab → hier  Licht, Ton und die Suchstufe, jede Nummer einmal
    kartenauftrag.json  Tab → hier  Karte laden, Aufnahme starten/beenden, Wegpunkt (Teil 3)
    lagebild.json    hier → Tab  Skizze, Spot, Tags, Menschen, Klickfahrt, Fähigkeiten (bis 4-mal je s)
    lagebild.png     hier → Tab  die Skizze (`workshop/skizze.py`)
    lagebild_karte.png  hier → Tab  die geladene Karte, gefärbt nach dem Abgleich (Teil 3)

**Folgen per Klick** (Teil 2): ein Klick auf einen Menschen (`klickziel.json` mit
`art = "mensch"`) übergibt an den Folgemodus (`folgen.folge` mit dem Körperfinder,
eingewickelt in `workshop/klickfolgen.py`, damit es DER Angeklickte ist). Er folgt, bis
Stopp, eine Taste, ein neuer Klick, ein fehlendes Lebenszeichen des Tabs — dasselbe wie bei
der Klickfahrt — oder bis der Angeklickte `START_FRIST_S` lang nicht zu finden war. Der
Grund steht im Lagebild. Die Suche pausiert so lange; was der Folgemodus sieht, steht im
Lagebild, der Gefolgte hervorgehoben. Die LEDs gehören dann dem Folgemodus, danach kommt
die im Tab gewählte Farbe zurück.

**Karten** (Teil 3, `workshop/kartenarbeit.py`): laden, verorten, aufnehmen, speichern —
das Langsame in einem eigenen Faden der Kartenarbeit; die Wahrnehmung fragt je Takt die
Verortung ab und gleicht die Kartenwände mit der Skizze ab (`workshop/kartenabgleich.py`).
Am Ende wird eine laufende Aufnahme gespeichert, NACHDEM Spot angehalten hat.

**Agenten** (Agenten am Spot, Teil 1, `docs/superpowers/specs/2026-10-09-agent-faehrt-design.md`):
ein dritter Eingang, `agent_befehl.json` (`record/agent.py`) mit Nummer, Art, Begründung und
Lebenszeichen. Ziele werden Ziele der Klickfahrt (Quelle „agent“), Drehen und Stösse rechnet
`workshop/agentfahrt.py`, Folgen geht an denselben Folgemodus wie ein Klick, die Tiefe misst
der Wahrnehmungsfaden. Ein neuer Befehl beendet den alten. Am echten Spot fährt der Agent
nur mit Freigabe (`freigabe.json` + frischer GUI-Puls), lesen darf er immer; jede Taste und
jeder Klick übernimmt, ein Lebenszeichen älter als `AGENT_TOTMANN_S` heisst Stopp. Der Stand
steht im Lagebild unter `agent`, Befehl und Ergebnis als Ereignis in der Aufzeichnung.

**Vorrang:** eine Taste vor der Klickfahrt vor dem Agenten vor dem Stillstand. Eine Taste
bricht die Klickfahrt ab. Die Klickfahrt fährt nur, solange das Lebenszeichen des Tabs frisch ist
(`record/zentrale.TOTMANN_S`), und nur mit den Schranken des Folgens (Gitter voraus aus
dem letzten Hindernisgitter, Kopfraum) — unlesbar heisst stehen. Die Tasten fahren wie
in `fahren.py` ohne diese Schranken: dort steuert der Mensch.

Die Wahrnehmung läuft in einem eigenen Faden (Gitter, Lage, Tags, Kopfraum dauern am
Roboter je 30–100 ms), der Fahrtakt hier. Sie wartet nur den REST von `WAHRNEHMUNG_S`
(`wahrnehmungs_pause`), mindestens `WAHRNEHMUNG_MIN_S`: bis zum 27.09.2026 wartete sie nach
der Arbeit immer volle 0.5 s — im 3D-Übungsraum (Gitterbau ~390 ms) kam so knapp ein Bild je
Sekunde, und die Draufsicht ruckelte. SPOTS PFEIL hängt nicht an diesem Takt: das Lagebild
trägt `vision_von_odom` (aus DEMSELBEN Rahmenbaum wie die Lage), und der Tab setzt damit die
Lage aus `zustand.jsonl` (odom, 10-mal je Sekunde) in die Skizze. Die MENSCHENSUCHE (Teil 2,
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

import numpy as np

from spotlab.backends.base import Capability
from spotlab.errors import SpotlabError
from spotlab.record import agent as agentdatei
from spotlab.record import fahrt
from spotlab.record import zentrale as protokoll
from spotlab.record.run import STOPP_DATEI
from spotlab.workshop import (
    agentfahrt,
    blick,
    folgen,
    kartenabgleich,
    klickfahrt,
    klickfolgen,
    menschensuche,
)
from spotlab.workshop import skizze as skizzenmodul

SKRIPT = Path(__file__)
TAKT_S = 0.05
WAHRNEHMUNG_S = 0.25        # der Takt der Wahrnehmung: so oft kommt ein Lagebild, wenn es geht
WAHRNEHMUNG_MIN_S = 0.05    # auch ein langsames Gitter lässt Fahrtakt und Simulation Luft
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
FAHR_ARTEN = ("ziel", "relativ", "drehen", "stoss", "folgen")   # brauchen am echten Spot Freigabe
KEINE_FREIGABE = ("keine Freigabe — ein Mensch muss im Tab „Fahren“ „🤖 Agent darf fahren“ "
                  "einschalten")
MENSCH_UEBERNIMMT = "ein Mensch hat übernommen"
AGENT_STILL = "kein Lebenszeichen vom Agenten — Spot steht"
ENDE_DER_KLICKFAHRT = ("angekommen", "abgelehnt", "versperrt", "abgebrochen")
TIEFE_KAMERAS = ("frontleft", "frontright")


def wahrnehmungs_pause(dauer_s):
    """Wie lange der Wahrnehmungsfaden nach einem Takt wartet: der Rest, nie weniger als das Minimum."""
    return max(WAHRNEHMUNG_MIN_S, WAHRNEHMUNG_S - dauer_s)


def lage_und_versatz(spot):
    """((x, y, gier) in „vision“, (tx, ty, dgier) von odom nach vision) aus EINEM Rahmenbaum.

    Der Versatz bildet einen odom-Punkt p auf R(dgier)·p + t in „vision“ ab. Zwei Abfragen
    gehörten zu zwei Augenblicken; aus einem Baum passen Lage und Versatz zusammen. Ohne
    „vision“ im Baum beides None, ohne „odom“ nur der Versatz.
    """
    from bosdyn.client.frame_helpers import (
        BODY_FRAME_NAME,
        ODOM_FRAME_NAME,
        VISION_FRAME_NAME,
        get_a_tform_b,
    )

    baum = spot.backend.frame_tree_snapshot()
    vision = get_a_tform_b(baum, VISION_FRAME_NAME, BODY_FRAME_NAME)
    if vision is None:
        return None, None
    lage = (float(vision.x), float(vision.y), float(vision.rot.to_yaw()))
    try:
        odom = get_a_tform_b(baum, ODOM_FRAME_NAME, BODY_FRAME_NAME)
    except Exception:
        odom = None
    if odom is None:
        return lage, None
    versatz = vision * odom.inverse()
    return lage, (float(versatz.x), float(versatz.y), float(versatz.rot.to_yaw()))


def _zahl(werte, name, vorgabe=None):
    """Eine endliche Zahl aus den Werten eines Agentenbefehls — sonst ValueError mit Namen."""
    wert = werte.get(name, vorgabe)
    if isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert):
        raise ValueError(f"{name} muss eine endliche Zahl sein, nicht {wert!r}")
    return float(wert)


def _im_hintergrund(arbeit):
    threading.Thread(target=arbeit, daemon=True, name="zentrale-ton").start()


class Zentrale:
    def __init__(self, spot, lauf_dir, jetzt=time.time, melde=print, licht=None,
                 hintergrund=_im_hintergrund, suche=None, folgen_mit=None,
                 koerper_finder=None, kartenarbeit=None, braucht_freigabe=False):
        self.spot = spot
        self.braucht_freigabe = bool(braucht_freigabe)   # True am echten Spot
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
        self._versatz = None       # vision_von_odom aus dem letzten Rahmenbaum
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
        self._karten = kartenarbeit          # None: kein Platz für Karten (Lagebild `karte` leer)
        self._agent_nummer = None
        self._agent_letzter = None   # der zuletzt LESBARE Agentenbefehl (wie `_klickziel`)
        self._agent_lauf = None      # der laufende Fahrbefehl des Agenten, sonst None
        self._agent = {"nummer": 0, "art": None, "zustand": "keiner", "grund": "", "warum": "",
                       "agent": "", "seit": None, "tiefe": None}
        self._freigabe = False
        self._tiefe_auftrag = None   # Nummer des Befehls `tiefe`, den der Wahrnehmungsfaden misst
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
        try:
            lage, versatz = lage_und_versatz(self.spot)
        except Exception:
            lage, versatz = None, None
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
        auftrag = self._tiefe_auftrag
        if auftrag is not None:
            ergebnis, grund = self._tiefe_messen()
            self._tiefe_fertig(auftrag, ergebnis, grund, kopf if kopf is not None else self._kopf)
        with self._sperre:
            if gitter is not None:
                self.skizze.aufnehmen(gitter, t)
                self._gitter, self._gitter_t = gitter, t
            if lage is not None:
                self._lage = lage
                self._versatz = versatz
            for tag in tags:
                if getattr(tag, "world_xy", None):
                    self._tags[int(tag.id)] = (float(tag.world_xy[0]), float(tag.world_xy[1]))
            if kopf is not None:
                self._kopf, self._kopf_t = kopf, t
            daten, bild = self._lagebild(t)
        kartenbild = None
        if self._karten is not None:
            # Die Skizze ändert nur dieser Faden: der Abgleich liest sie ohne Sperre.
            daten["karte"], kartenbild = self._karte(t, lage)
        protokoll.schreibe_lagebild(self.lauf_dir, daten, bild, kartenbild)

    def _karte(self, t, lage):
        """(Platz `karte`, PNG oder None) — eine Kartenarbeit, die stolpert, hält nichts an."""
        try:
            self._karten.beobachte(t)
            spot_xy = (lage[0], lage[1]) if lage is not None else None
            abgleich = (self._karten.abgleiche(self.skizze, spot_xy, t) if spot_xy is not None
                        else None)
            return (self._karten.daten(t, abgleich),
                    None if abgleich is None else kartenabgleich.png(abgleich))
        except Exception as fehler:
            self._einmal("karte", f"Die Kartenanzeige stolpert ({fehler}) — Spot fährt weiter.")
            return None, None

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
            "vision_von_odom": (None if self._versatz is None
                                else [round(v, 5) for v in self._versatz]),
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
            "agent": dict(self._agent, freigabe=self._freigabe,
                          braucht_freigabe=self.braucht_freigabe),
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
        """Ein Fahrtakt: Aktionen, Freigabe, Klickziel, Agentenbefehl, dann
        Taste > Klickfahrt > Agent > Stillstand."""
        t = self.jetzt() if t is None else t
        self._aktionen()
        self._kartenauftraege()
        self._freigabe_pruefen()
        befehl = fahrt.lies(self.lauf_dir, jetzt=self.jetzt)
        # Unter Windows liest der Takt die Datei manchmal genau beim Ersetzen (20-mal je
        # Sekunde gelesen, 5-mal geschrieben): dann gilt das zuletzt gelesene weiter. Sein
        # Lebenszeichen altert trotzdem -- der Totmann bleibt scharf. Ohne diese Zeile brach
        # ein einziger Lesekonflikt die Klickfahrt ab (Kette im Übungsraum, 27.09.2026).
        # Dasselbe gilt für den Befehl des Agenten.
        kz = protokoll.lies_klickziel(self.lauf_dir) or self._klickziel
        self._klickziel = kz
        ab = agentdatei.lies_befehl(self.lauf_dir) or self._agent_letzter
        self._agent_letzter = ab
        if kz is not None and kz.nummer != self._klick_nummer:
            self._agent_abbrechen(MENSCH_UEBERNIMMT)
            self._neues_klickziel(kz, t)
            if kz.art == "mensch" and kz.ziel is not None and befehl == fahrt.STILL \
                    and self._suche_kann:
                self._folge_mensch(kz.nummer, kz.ziel, "tab", self._klick_abloese(kz))
                return
        if ab is not None and ab.nummer != self._agent_nummer:
            if self._agent_neu(ab, t, taste=befehl != fahrt.STILL):
                return
        if befehl != fahrt.STILL:
            self._agent_abbrechen(MENSCH_UEBERNIMMT)
            with self._sperre:
                self.klick.abbrechen("eine Taste hat übernommen")
            vx, vy, wz = befehl
            self.spot.walk(vx=vx, vy=vy, wz=wz, stop=False)
            self._faehrt = True
            return
        if self.klick.unterwegs:
            if self.klick.stand.quelle == "agent":
                lebt, stufe = agentdatei.befehl_lebt(ab, jetzt=self.jetzt), "langsam"
                still = AGENT_STILL
            else:
                lebt, stufe = protokoll.lebt(kz, jetzt=self.jetzt), kz.stufe
                still = ("kein Lebenszeichen vom Tab (Reiter gewechselt oder Fenster nicht aktiv) "
                         "— Spot steht")
            if not lebt:
                with self._sperre:
                    self.klick.abbrechen(still)
            else:
                vx, wz = self._klickschritt(t, stufe)
                if (vx, wz) != (0.0, 0.0):
                    self.spot.walk(vx=vx, vy=0.0, wz=wz, stop=False)
                    self._faehrt = True
                    return
        if self._agent_lauf is not None and self._agent_schritt(t, ab):
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

    def _schranken(self, t, lage):
        """(Gitter oder None, frei voraus oder None, Kopfraum frei, Grund) — fail-closed:
        ein Gitter älter als `GITTER_GILT_S` ist keines, ein alter Kopfraum ist zu."""
        with self._sperre:
            gitter, frei = None, None
            if self._gitter is not None and t - self._gitter_t <= GITTER_GILT_S:
                gitter = self._gitter
                try:
                    frei = gitter.free_distance(lage[0], lage[1], math.degrees(lage[2]))
                except Exception:
                    frei = None
            kopf_frei, kopf_grund = self._kopf
            if self._kopf_t is None or t - self._kopf_t > KOPFRAUM_GILT_S:
                kopf_frei, kopf_grund = False, "Kopfraum nicht frisch geprüft"
        return gitter, frei, kopf_frei, kopf_grund

    def _klickschritt(self, t, stufe):
        try:
            faktor = fahrt.faktor_der_stufe(stufe)
        except ValueError:
            faktor = fahrt.faktor_der_stufe("langsam")
        lage = self._lage_jetzt()
        if lage is None:
            with self._sperre:
                self.klick.abbrechen("Spots Lage ist nicht lesbar")
            return 0.0, 0.0
        _gitter, frei, kopf_frei, kopf_grund = self._schranken(t, lage)
        with self._sperre:
            return self.klick.schritt(lage, self.skizze, t, frei, faktor,
                                      kopf_frei=kopf_frei, kopf_grund=kopf_grund)

    # ------------------------------------------------------------ Agent

    def _ereignis(self, name, **daten):
        """In die Aufzeichnung — eine stolpernde Aufzeichnung hält keinen Befehl auf. Die Art
        eines Agentenbefehls heisst dort `befehl`: `art` ist der Name des Ereignisses selbst."""
        recorder = getattr(self.spot, "recorder", None)
        if recorder is None:
            return
        try:
            recorder.event(name, **daten)
        except Exception as fehler:
            self._einmal("aufzeichnung", f"Die Aufzeichnung stolpert ({fehler}) — Spot fährt "
                                         f"weiter.")

    def _freigabe_pruefen(self):
        """Am echten Spot: gilt „🤖 Agent darf fahren“ noch? Jeder Wechsel kommt in die
        Aufzeichnung; geht sie aus, endet ein laufender Agentenbefehl."""
        if not self.braucht_freigabe:
            return
        frei = agentdatei.freigabe_gilt(self.lauf_dir, jetzt=self.jetzt)
        if frei == self._freigabe:
            return
        with self._sperre:
            self._freigabe = frei
        grund = ("ein Mensch hat sie eingeschaltet" if frei else
                 "ausgeschaltet, von einer menschlichen Eingabe zurückgenommen oder die "
                 "Oberfläche antwortet nicht")
        self.melde(f"🤖 Agent darf fahren: {'an' if frei else 'aus'}")
        self._ereignis("freigabe", an=frei, grund=grund)
        if not frei:
            self._agent_abbrechen(f"{MENSCH_UEBERNIMMT} — die Freigabe ist aus")

    def _agent_ende(self, zustand, grund="", nummer=None, **felder):
        """Der Agentenbefehl endet — mit `nummer` nur, wenn es noch derselbe ist."""
        with self._sperre:
            stand = self._agent
            if nummer is not None and stand["nummer"] != nummer:
                return
            self._agent_lauf = None
            stand.update(felder, zustand=zustand, grund=grund)
            nummer, art, seit = stand["nummer"], stand["art"], stand["seit"]
        dauer = None if seit is None else round(max(0.0, self.jetzt() - seit), 3)
        self._ereignis("agent_ergebnis", nummer=nummer, befehl=art, zustand=zustand, grund=grund,
                       dauer_s=dauer)

    def _agent_abbrechen(self, grund):
        lauf = self._agent_lauf
        if lauf is None:
            return
        if lauf["art"] in ("ziel", "relativ"):
            with self._sperre:
                if self.klick.stand.quelle == "agent":
                    self.klick.abbrechen(grund)
        self._agent_ende("abgebrochen", grund)

    def _agent_verbot(self, ab, taste):
        """Warum ein Fahrbefehl gar nicht erst fährt — oder None."""
        if self.braucht_freigabe and not self._freigabe:
            return KEINE_FREIGABE
        if not agentdatei.befehl_lebt(ab, jetzt=self.jetzt):
            return f"{AGENT_STILL} (der Befehl kam ohne frisches Lebenszeichen an)"
        if taste:
            return "ein Mensch fährt gerade mit den Tasten — warten, bis er loslässt"
        if self.klick.unterwegs and self.klick.stand.quelle == "tab":
            return "ein Mensch fährt gerade per Klick — warten, bis die Klickfahrt endet"
        return None

    def _agent_neu(self, ab, t, taste=False):
        """Einen neuen Agentenbefehl annehmen; er beendet den alten. True: der Takt ist vorbei
        (der Folgemodus lief)."""
        self._agent_nummer = ab.nummer
        self._agent_abbrechen("vom Agenten angehalten" if ab.art == "stopp" else
                              f"abgelöst durch den nächsten Befehl ({ab.art})")
        with self._sperre:
            self._agent = {"nummer": ab.nummer, "art": ab.art, "zustand": "unterwegs", "grund": "",
                           "warum": ab.warum, "agent": ab.agent, "seit": t, "tiefe": None}
            self._tiefe_auftrag = None
        self._ereignis("agent_befehl", nummer=ab.nummer, befehl=ab.art, werte=ab.werte,
                       warum=ab.warum, agent=ab.agent)
        if ab.art in FAHR_ARTEN:
            verbot = self._agent_verbot(ab, taste)
            if verbot:
                self._agent_ende("abgelehnt", verbot)
                return False
        arbeit = {"ziel": self._agent_ziel, "relativ": self._agent_relativ,
                  "drehen": self._agent_drehen, "stoss": self._agent_stoss,
                  "folgen": self._agent_folgen, "stopp": self._agent_stopp,
                  "tiefe": self._agent_tiefe, "licht": self._agent_licht,
                  "piep": self._agent_piep, "suche": self._agent_suche}[ab.art]
        try:
            return bool(arbeit(ab, t))
        except ValueError as fehler:
            self._agent_ende("abgelehnt", f"{fehler} — Befehl mit gültigen Werten neu schicken")
            return False

    def _agent_lage(self):
        lage = self._lage_jetzt()
        if lage is None:
            self._agent_ende("abgelehnt", "Spots Lage ist nicht lesbar")
        return lage

    def _agent_ziel(self, ab, t):
        self._agent_klickziel(ab, (_zahl(ab.werte, "x"), _zahl(ab.werte, "y")), t)

    def _agent_relativ(self, ab, t):
        vor, links = _zahl(ab.werte, "vor_m", 0.0), _zahl(ab.werte, "links_m", 0.0)
        lage = self._agent_lage()
        if lage is not None:
            self._agent_klickziel(ab, agentfahrt.relativ_ziel(lage, vor, links), t, lage)

    def _agent_klickziel(self, ab, ziel, t, lage=None):
        """Ein Ziel der Klickfahrt mit Quelle „agent“: dieselbe Wegsuche, dieselben Schranken."""
        lage = lage or self._agent_lage()
        if lage is None:
            return
        with self._sperre:
            self.klick.neues_ziel(ab.nummer, ziel, lage, self.skizze, t, quelle="agent")
            stand = self.klick.stand
        if stand.zustand == "abgelehnt":
            self._agent_ende("abgelehnt", stand.grund)
        else:
            self._agent_lauf = {"art": ab.art}

    def _agent_drehen(self, ab, t):
        grad = _zahl(ab.werte, "grad")
        lage = self._agent_lage()
        if lage is not None:
            self._agent_lauf = {"art": "drehen",
                                "drehung": agentfahrt.Drehung(lage[2] + math.radians(grad), t)}

    def _agent_stoss(self, ab, t):
        vx, vy, wz = (_zahl(ab.werte, k, 0.0) for k in ("vx", "vy", "wz"))
        dauer = _zahl(ab.werte, "dauer_s")
        lage = self._agent_lage()
        if lage is None:
            return
        vx, vy, wz, dauer, grund = self._stoss_pruefen(vx, vy, wz, dauer, lage, t)
        if grund:
            self._agent_ende("abgelehnt", grund)
        else:
            self._agent_lauf = {"art": "stoss", "werte": (vx, vy, wz), "ende": t + dauer}

    def _stoss_pruefen(self, vx, vy, wz, dauer, lage, t):
        gitter, frei, kopf_frei, kopf_grund = self._schranken(t, lage)
        return agentfahrt.stoss_pruefen(vx, vy, wz, dauer, lage, gitter, frei, kopf_frei,
                                        kopf_grund, max_v=fahrt.TEMPO_M_S, max_w=fahrt.DREH_RAD_S)

    def _agent_folgen(self, ab, t):
        ziel = (_zahl(ab.werte, "x"), _zahl(ab.werte, "y"))
        if not self._suche_kann:
            self._agent_ende("abgelehnt", KEINE_KAMERAS)
            return False
        self._agent_lauf = {"art": "folgen"}
        self._folge_mensch(ab.nummer, ziel, "agent", self._agent_abloese(ab))
        self._agent_ende("abgebrochen", self.klick.stand.grund)
        return True

    def _agent_abloese(self, ab):
        """Wann das Folgen für den Agenten endet: neuer Befehl, kein Lebenszeichen, ein Klick
        im Tab, oder die Freigabe ist aus. Den Wechsel der Freigabe schreibt der nächste Takt."""
        zuletzt = {"ab": ab}

        def abgeloest():
            neu = agentdatei.lies_befehl(self.lauf_dir) or zuletzt["ab"]
            zuletzt["ab"] = neu
            if neu.nummer != ab.nummer:
                return "ein neuer Befehl des Agenten"
            if not agentdatei.befehl_lebt(neu, jetzt=self.jetzt):
                return AGENT_STILL
            kz = protokoll.lies_klickziel(self.lauf_dir)
            if kz is not None and kz.nummer != self._klick_nummer:
                return MENSCH_UEBERNIMMT
            if self.braucht_freigabe and not agentdatei.freigabe_gilt(self.lauf_dir,
                                                                      jetzt=self.jetzt):
                return f"{MENSCH_UEBERNIMMT} — die Freigabe ist aus"
            return None

        return abgeloest

    def _agent_stopp(self, ab, t):
        self._agent_ende("erledigt", "Spot steht")

    def _agent_tiefe(self, ab, t):
        with self._sperre:
            self._tiefe_auftrag = ab.nummer      # misst der Wahrnehmungsfaden

    def _agent_licht(self, ab, t):
        farbe = ab.werte.get("farbe")
        if farbe not in (*LICHTFARBEN, "aus"):
            raise ValueError(f"farbe muss eine von {[*LICHTFARBEN, 'aus']} sein")
        self._agent_erledigt(self._licht_setzen(farbe))

    def _agent_piep(self, ab, t):
        self._agent_erledigt(self._piepen())

    def _agent_suche(self, ab, t):
        stufe = ab.werte.get("stufe")
        if stufe not in protokoll.SUCHSTUFEN:
            raise ValueError(f"stufe muss eine von {list(protokoll.SUCHSTUFEN)} sein")
        self._suche_setzen(stufe)
        self._agent_erledigt(None if self._suche_kann else KEINE_KAMERAS)

    def _agent_erledigt(self, grund):
        if grund:
            self._agent_ende("abgelehnt", grund)
        else:
            self._agent_ende("erledigt")

    def _agent_schritt(self, t, ab):
        """Ein Takt des laufenden Agentenbefehls. True: Spot fährt in diesem Takt."""
        lauf = self._agent_lauf
        if lauf["art"] in ("ziel", "relativ"):
            with self._sperre:
                stand = self.klick.stand
            if stand.quelle != "agent":
                self._agent_ende("abgebrochen", MENSCH_UEBERNIMMT)
            elif stand.zustand != "unterwegs":
                self._agent_ende(stand.zustand if stand.zustand in ENDE_DER_KLICKFAHRT
                                 else "abgebrochen", stand.grund)
            return False
        if not agentdatei.befehl_lebt(ab, jetzt=self.jetzt):
            self._agent_ende("abgebrochen", AGENT_STILL)
            return False
        lage = self._lage_jetzt()
        if lage is None:
            self._agent_ende("abgebrochen", "Spots Lage ist nicht lesbar")
            return False
        if lauf["art"] == "drehen":
            wz, zustand, grund = lauf["drehung"].schritt(lage[2], t)
            if zustand != "unterwegs":
                self._agent_ende(zustand, grund)
                return False
            self.spot.walk(vx=0.0, vy=0.0, wz=wz, stop=False)
        else:                                    # stoss
            rest = lauf["ende"] - t
            if rest <= 0.0:
                self._agent_ende("angekommen")
                return False
            vx, vy, wz = lauf["werte"]
            *_, grund = self._stoss_pruefen(vx, vy, wz, rest, lage, t)
            if grund:
                self._agent_ende("versperrt", grund)
                return False
            self.spot.walk(vx=vx, vy=vy, wz=wz, stop=False)
        self._faehrt = True
        return True

    def _tiefe_messen(self):
        """(Ergebnis, None) oder (None, Grund) — die Tiefenkameras vorne, im Körperrahmen.
        Ohne Tiefenkameras steht dort „nicht messbar“, nie eine Zahl."""
        try:
            kann = self.spot.backend.capabilities()
        except Exception:
            kann = Capability.NONE
        if not kann & Capability.DEPTH_CAMERAS:
            return None, "nicht messbar — dieses Backend hat keine Tiefenkameras (Übungsraum)"
        wolken, fehler = [], []
        for name in TIEFE_KAMERAS:
            try:
                punkte = self.spot.point_cloud(name, frame="body").points
                wolken.append(np.asarray(punkte, dtype=float).reshape(-1, 3))
            except Exception as grund:
                fehler.append(f"{name}: {grund}")
        if not wolken:
            return None, "nicht messbar — " + "; ".join(fehler)
        return {"sektoren": agentfahrt.tiefe_sektoren(np.vstack(wolken)), "fehler": fehler}, None

    def _tiefe_fertig(self, nummer, ergebnis, grund, kopf):
        with self._sperre:
            if self._tiefe_auftrag != nummer:
                return                           # inzwischen ein anderer Befehl
            self._tiefe_auftrag = None
        if ergebnis is None:
            self._agent_ende("abgelehnt", grund, nummer=nummer)
        else:
            tiefe = dict(ergebnis, kopfraum={"frei": bool(kopf[0]), "grund": kopf[1]})
            self._agent_ende("gemessen", "", nummer=nummer, tiefe=tiefe)

    # ------------------------------------------------------------ Folgen per Klick

    def _klick_abloese(self, kz):
        """Wann der Tab das Folgen beendet: ein neuer Klick oder kein Lebenszeichen mehr."""
        zuletzt = {"kz": kz}

        def abgeloest():
            neu = protokoll.lies_klickziel(self.lauf_dir) or zuletzt["kz"]
            zuletzt["kz"] = neu
            if neu.nummer != kz.nummer:
                return "ein neuer Klick"
            if not protokoll.lebt(neu, jetzt=self.jetzt):
                return ("kein Lebenszeichen vom Tab (Reiter gewechselt oder Fenster nicht aktiv) "
                        "— Spot steht")
            return None

        return abgeloest

    def _folge_mensch(self, nummer, ziel, quelle, abgeloest):
        """Der Folgemodus übernimmt, bis `laeuft` einen Grund hat aufzuhören. Blockiert.

        `abgeloest()` sagt, ob der Auftraggeber (Tab oder Agent) das Folgen beendet hat — ein
        Grund als Text, sonst None. Stopp, Tasten und die Startfrist gelten für beide."""
        anfang = self.jetzt()
        ende = {"grund": ""}

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

        finder = klickfolgen.KlickFinder(self._koerper_finder(), ziel, gesehen=gesehen)

        def stand(grund):
            with self._sperre:
                self.klick.stand = klickfahrt.Stand(nummer=nummer, zustand="folgt",
                                                    grund=grund, ziel=ziel, quelle=quelle)

        def laeuft():
            if not self._laeuft():
                ende["grund"] = "Stopp"
                return False
            self._aktionen()
            self._kartenauftraege()
            if fahrt.lies(self.lauf_dir, jetzt=self.jetzt) != fahrt.STILL:
                ende["grund"] = "eine Taste hat übernommen"
                return False
            grund = abgeloest()
            if grund:
                ende["grund"] = grund
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
                    nummer=nummer, zustand="abgebrochen", quelle=quelle,
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

    # ------------------------------------------------------------ Karten

    def _kartenauftraege(self):
        """Einen Kartenauftrag an die Kartenarbeit — sie nimmt jede Nummer nur einmal."""
        if self._karten is None:
            return
        auftrag = protokoll.lies_kartenauftrag(self.lauf_dir)
        if auftrag is not None:
            self._karten.auftrag(auftrag["nummer"], auftrag["was"], auftrag["name"])

    # ------------------------------------------------------------ Licht und Ton

    def _aktionen(self):
        aktion = protokoll.lies_aktion(self.lauf_dir)
        if aktion is None or aktion["nummer"] == self._aktion_nummer:
            return
        self._aktion_nummer = aktion["nummer"]
        if aktion["art"] == "licht":
            self._licht_setzen(aktion["farbe"])
        elif aktion["art"] == "suche":
            if aktion.get("stufe") in protokoll.SUCHSTUFEN:
                self._suche_setzen(aktion["stufe"])
        elif aktion["art"] == "ton":
            self._piepen()

    def _licht_setzen(self, farbe):
        """Die Farbe aus Tab oder Agent. Gibt den Grund zurück, wenn es nicht geht."""
        self._lichtwunsch = farbe
        if self._folgt:
            return None                      # die LEDs gehören gerade dem Folgemodus
        if self._licht is None:
            text = "Licht gibt es nur am echten Spot (Dienst audio-visual)."
            self._einmal("licht", text)
            return text
        try:
            if farbe == "aus":
                self._licht.aus()
            else:
                self._licht.setze(LICHTFARBEN.get(farbe, "blue"))
        except Exception as fehler:
            text = f"Das Licht geht nicht ({fehler}) — Spot fährt weiter."
            self._einmal("licht_fehler", text)
            return text
        return None

    def _suche_setzen(self, stufe):
        with self._sperre:
            self._suchstufe = stufe
            if stufe == "aus":
                self._menschen = []
                self._suche_grund = None

    def _piepen(self):
        """Ein Ton im Hintergrund. Gibt den Grund zurück, wenn es keinen gibt."""
        if not self.faehigkeiten["ton"]:
            text = "Ton gibt es nur am echten Spot (Dienst audio-visual)."
            self._einmal("ton", text)
            return text

        def piepen():
            try:
                self.spot.beep()
            except Exception as fehler:
                self._einmal("ton_fehler", f"Der Ton geht nicht ({fehler}).")

        self.hintergrund(piepen)
        return None

    # ------------------------------------------------------------ Schleife

    def _wahrnehmung_schleife(self, halt):
        while not halt.is_set():
            beginn = time.monotonic()
            try:
                self.wahrnehmen()
            except Exception as fehler:
                self._einmal("wahrnehmung", f"Die Wahrnehmung stolpert ({fehler}).")
            halt.wait(wahrnehmungs_pause(time.monotonic() - beginn))

    def _gui_weg(self):
        """Die Oberfläche ist abgestürzt oder hängt: enden wie beim Stopp-Knopf, nicht verwaist
        weiterlaufen. Befund 09.10.2026: sonst hielt die Zentrale den echten Spot stehend, mit
        Lease und Not-Aus-Eintrag, und niemand konnte sie mehr erreichen."""
        frist = protokoll.GUI_FRIST_S
        self.melde(f"Keine Verbindung zur Oberfläche seit {frist:.0f} s — Spot hält an und setzt "
                   f"sich, die Steuerzentrale endet. spotlab neu starten, dann neu verbinden.")
        recorder = getattr(self.spot, "recorder", None)
        if recorder is not None:
            try:
                recorder.event("gui_weg", frist_s=frist)
            except Exception:
                pass                 # die Aufzeichnung darf das Hinsetzen nicht aufhalten

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
                if protokoll.gui_weg(self.lauf_dir, self.jetzt):
                    self._gui_weg()
                    break
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
                if self._karten is not None:
                    # NACH dem Anhalten: das Speichern einer Aufnahme dauert, und Spot
                    # soll dabei stehen, nicht mit dem letzten Befehl weiterlaufen.
                    try:
                        self._karten.beenden()
                    except Exception as fehler:
                        self.melde(f"Die Kartenaufnahme liess sich nicht speichern ({fehler}) — "
                                   f"sie liegt noch auf dem Roboter.")


# ------------------------------------------------------------ Hauptprogramm


def argumente(argv):
    """(runs, uebernehmen, arbeitsordner) aus der Kommandozeile:
    `zentrale.py [--runs ORDNER] [--arbeitsordner ORDNER] [--uebernehmen]`."""
    rest, runs, uebernehmen, arbeitsordner = list(argv), None, False, None
    while rest:
        wort = rest.pop(0)
        if wort in ("--runs", "--arbeitsordner"):
            if not rest:
                raise SpotlabError(f"Nach {wort} fehlt der Ordner.")
            if wort == "--runs":
                runs = rest.pop(0)
            else:
                arbeitsordner = rest.pop(0)
        elif wort == "--uebernehmen":
            uebernehmen = True
        else:
            raise SpotlabError(f"Unbekannte Option {wort}.")
    return runs, uebernehmen, arbeitsordner


def freigabe_noetig(lauf_dir):
    """Braucht der Agent in diesem Lauf die Freigabe eines Menschen? Ja, ausser das Backend
    steht in `spotlab.OHNE_ROBOTER` -- ein unlesbares `lauf.json` heisst ebenfalls ja."""
    import spotlab
    from spotlab.record.read import read_run

    return read_run(lauf_dir, zaehlen=False).backend not in spotlab.OHNE_ROBOTER


def _hauptprogramm(argv=None):
    """Das Programm hinter dem Tab — PAKETCODE, siehe oben. Der Lauf landet unter `--runs`."""
    import os
    import sys

    import spotlab
    from spotlab.workshop.kartenarbeit import Kartenarbeit

    runs, uebernehmen, arbeitsordner = argumente(sys.argv[1:] if argv is None else argv)
    runs = runs or os.environ.get("SPOTLAB_RUNS_DIR") or str(Path.cwd() / "runs")
    with spotlab.connect(runs_dir=runs, script=__file__, take=uebernehmen) as spot:
        spot.power_on()
        spot.stand()
        print("Steuerzentrale: W/S vor und zurück · A/D seitwärts · Q/E drehen · "
              "Klick in die Draufsicht: dorthin gehen · Leertaste hält")
        lauf_dir = spot.recorder.dir
        stopp = lauf_dir / STOPP_DATEI
        karten = Kartenarbeit(spot, arbeitsordner)
        Zentrale(spot, lauf_dir, kartenarbeit=karten,
                 braucht_freigabe=freigabe_noetig(lauf_dir)).lauf(
            laeuft=lambda: not stopp.exists())
        spot.sit()


if __name__ == "__main__":
    _hauptprogramm()
