"""Die Kartenarbeit der Steuerzentrale (Teil 3): laden, verorten, aufnehmen, speichern.

Das Programm der Zentrale hält die EINE Verbindung und das Lease — und nur mit Lease darf eine
Karte hochgeladen werden. Diese Klasse kennt den Kartenzustand

    keine · laedt · sucht_tag · verortet · verloren · nimmt_auf · speichert · nicht_gespeichert

und macht alles Langsame (hochladen, verorten, beenden + nachbearbeiten + herunterladen) in
EINEM eigenen Faden, eine Arbeit zugleich; ein Auftrag währenddessen wird mit Grund abgelehnt.
Der Fahrtakt wartet nie darauf, und die Karte gibt keine Fahrt frei.

Aufträge kommen aus `kartenauftrag.json` (`record/zentrale.py`), jede Nummer einmal; `erledigt`
ist die zuletzt angenommene Nummer — das Lagebild meldet sie, damit der Tab einen verlorenen
Auftrag nachschicken kann. `beobachte(t)` läuft im Wahrnehmungsfaden: Verortung, das Urteil des
Roboters über `FENSTER_S`, der Stand der Aufnahme, ein neuer Verortungsversuch alle `VERSUCH_S`.

**Aufnehmen:** verortet in einer geladenen Karte → WEITERFÜHREN (die neuen Wegpunkte hängen an
der alten Karte); sonst NEU (die Karte auf dem Roboter wird geleert). Gespeichert wird immer
unter einem freien Namen (`freier_name`) — eine vorhandene Karte wird nie überschrieben.
Scheitert das Herunterladen, bleibt die Aufnahme auf dem Roboter, und „beenden“ versucht es
unter DEMSELBEN Namen noch einmal. `beenden()` am Programmende speichert eine laufende Aufnahme,
bevor Spot sich setzt; nach einem NOT-AUS bleibt sie nur auf dem Roboter.
"""

import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from spotlab.backends.base import Capability
from spotlab.pfade import sicherer_name
from spotlab.workshop import kartenabgleich

VERSUCH_S = 2.0              # so oft wird ohne Tag im Bild neu verortet
FENSTER_S = 30.0             # das Urteil des Roboters: angenommene/abgelehnte Abgleiche darin
BEENDEN_WARTE_S = 120.0      # so lange wartet das Programmende auf eine laufende Arbeit
KEIN_GRAPHNAV = "Karten gibt es nur am echten Spot (GraphNav)."
TAG_HINWEIS = ("Stell Spot so hin, dass ein AprilTag der Karte im Bild ist — neuer Versuch "
               "alle 2 s.")
AUFNAHME_ZUSTAENDE = ("nimmt_auf", "speichert", "nicht_gespeichert")


def freier_name(wurzel, name):
    """`name` (bereinigt), oder mit „-2“, „-3“ … — nie der Name einer vorhandenen Karte."""
    basis = sicherer_name(name, ersatz="karte")
    wurzel = Path(wurzel)
    if not (wurzel / basis).exists():
        return basis
    k = 2
    while (wurzel / f"{basis}-{k}").exists():
        k += 1
    return f"{basis}-{k}"


def namensvorschlag(jetzt=None):
    return f"karte-{(jetzt or datetime.now()):%Y-%m-%d-%H%M}"


class Kartenarbeit:
    def __init__(self, spot, arbeitsordner, jetzt=time.time, melde=print, sitzung_bauen=None,
                 ausfuehren=None, waende_laden=None):
        self.spot = spot
        self.arbeitsordner = Path(arbeitsordner) if arbeitsordner else None
        self.jetzt = jetzt
        self.melde = melde
        self._sitzung_bauen = sitzung_bauen or (lambda: spot.backend.aufnahme_sitzung())
        self._ausfuehren = ausfuehren or self._im_faden
        self._waende_laden = waende_laden or kartenabgleich.Kartenwaende.aus_ordner
        self._sperre = threading.Lock()
        self._faden = None
        self._arbeitet = False
        self._taetigkeit = ""
        self.zustand = "keine"
        self.name = None
        self.grund = ""
        self.erledigt = None
        self._nummer = None
        self.waende = None
        self.weiter = False
        self._trafo = None
        self._verortung = None
        self._zaehler = deque()
        self._naechster_versuch = 0.0
        self._sitzung = None
        self._aufnahme_name = None
        self._ziel_name = None
        self._aufnahme_stand = (0, 0)
        self._wegpunkte_gesetzt = 0
        self.kann = self._kann()

    def _kann(self):
        backend = getattr(self.spot, "backend", None)
        try:
            kann = backend.capabilities()
        except Exception:
            return False
        return bool(kann & Capability.GRAPH_NAV) and hasattr(backend, "verortung")

    # ------------------------------------------------------------ Aufträge

    def auftrag(self, nummer, was, name=None):
        """Einen Auftrag annehmen (je Nummer einmal) oder mit Grund ablehnen."""
        if nummer == self._nummer:
            return
        self._nummer = nummer
        self.erledigt = nummer
        if not self.kann:
            self.grund = KEIN_GRAPHNAV
            return
        if self._arbeitet:
            self.grund = (f"Spot ist noch beschäftigt ({self._taetigkeit}) — bitte warten und "
                          f"nochmal klicken.")
            return
        z = self.zustand
        if was == "laden":
            if z in AUFNAHME_ZUSTAENDE:
                self.grund = ("Während einer Aufnahme lädt Spot keine andere Karte — erst "
                              "„■ Aufnahme beenden“.")
            elif not name:
                self.grund = "Keine Karte gewählt."
            else:
                self._starte(lambda: self._laden(name), "Karte laden")
        elif was == "aufnahme_start":
            if z in AUFNAHME_ZUSTAENDE:
                self.grund = "Es läuft schon eine Aufnahme."
            else:
                self._starte(lambda: self._aufnahme_start(name), "Aufnahme starten")
        elif was == "aufnahme_stopp":
            if z not in ("nimmt_auf", "nicht_gespeichert"):
                self.grund = "Es läuft keine Aufnahme."
            else:
                self._starte(lambda: self._stoppen(name), "Karte speichern")
        elif was == "wegpunkt":
            if z != "nimmt_auf":
                self.grund = "Wegpunkte gibt es nur während einer Aufnahme."
            else:
                self._starte(lambda: self._wegpunkt(name), "Wegpunkt setzen")

    def _starte(self, arbeit, taetigkeit):
        self._arbeitet, self._taetigkeit = True, taetigkeit

        def lauf():
            try:
                arbeit()
            except Exception as fehler:          # eine Arbeit wirft nie bis in den Faden
                self.grund = f"{taetigkeit}: {fehler}"
            finally:
                self._arbeitet = False

        self._ausfuehren(lauf)

    def _im_faden(self, lauf):
        self._faden = threading.Thread(target=lauf, daemon=True, name="zentrale-karte")
        self._faden.start()

    def _setze(self, **felder):
        with self._sperre:
            for schluessel, wert in felder.items():
                setattr(self, schluessel, wert)

    # ------------------------------------------------------------ Laden und Verorten

    def _laden(self, name):
        from spotlab.maps import store

        self._setze(zustand="laedt", grund=f"Karte ‹{name}› wird hochgeladen …", weiter=False)
        try:
            if self.arbeitsordner is None:
                raise ValueError("Es ist kein Arbeitsordner gesetzt.")
            ordner = store.finde(self.arbeitsordner, name)
            self.spot.backend.upload_map(ordner)
            waende = self._waende_laden(ordner)
        except Exception as fehler:
            self._setze(zustand="keine", name=None, waende=None, _trafo=None, _verortung=None,
                        grund=f"Laden gescheitert: {fehler}")
            return
        with self._sperre:
            self.name, self.waende = ordner.name, waende
            self._trafo, self._verortung = None, None
            self._zaehler.clear()
        self._verorten()

    def _verorten(self):
        try:
            self.spot.backend.localize()
        except Exception:
            self._setze(zustand="sucht_tag", grund=TAG_HINWEIS,
                        _naechster_versuch=self.jetzt() + VERSUCH_S)
            return
        self._setze(zustand="verortet", grund="")

    def beobachte(self, t):
        """Im Wahrnehmungsfaden: Verortung, Urteil, Aufnahmestand, neuer Versuch ohne Tag."""
        if not self.kann:
            return
        z = self.zustand
        if z in AUFNAHME_ZUSTAENDE and self._sitzung is not None:
            try:
                stand = self._sitzung.status()
                self._aufnahme_stand = (int(stand.wegpunkte), int(stand.kanten))
            except Exception:
                pass
        if self.waende is None:
            return
        try:
            v = self.spot.backend.verortung()
        except Exception:
            v = None
        with self._sperre:
            if v is not None:
                self._verortung = v
                trafo = kartenabgleich.vision_von_seed(v)
                if trafo is not None and not v.verloren:
                    self._trafo = trafo             # verloren: die Karte bleibt, wo sie war
                self._zaehler.append((t, v.angenommen, v.abgelehnt))
                while len(self._zaehler) > 2 and self._zaehler[1][0] < t - FENSTER_S:
                    self._zaehler.popleft()
            if self._arbeitet or z not in ("sucht_tag", "verortet", "verloren"):
                return
            if v is None:
                self.zustand = "sucht_tag"
                if not self.grund:
                    self.grund = TAG_HINWEIS
            else:
                self.zustand = "verloren" if v.verloren else "verortet"
                self.grund = ("Spot findet sich in der Karte nicht mehr" if v.verloren else "")
            neuer_versuch = self.zustand == "sucht_tag" and t >= self._naechster_versuch
        if neuer_versuch:
            self._starte(self._verorten, "verorten")

    # ------------------------------------------------------------ Aufnahme

    def _aufnahme_start(self, name):
        weiter = self.zustand == "verortet" and self.waende is not None
        try:
            sitzung = self._sitzung_bauen()
            sitzung.start(graph_leeren=not weiter)
        except Exception as fehler:
            self._setze(grund=f"Aufnahme nicht gestartet: {fehler}")
            return
        with self._sperre:
            self._sitzung, self.weiter = sitzung, weiter
            self._aufnahme_name = name or namensvorschlag()
            self._ziel_name, self._aufnahme_stand, self._wegpunkte_gesetzt = None, (0, 0), 0
            if not weiter:          # die Karte auf dem Roboter ist leer: nichts mehr einblenden
                self.name, self.waende, self._trafo, self._verortung = None, None, None, None
            self.zustand = "nimmt_auf"
            self.grund = ""
        self.melde(f"Kartenaufnahme läuft ({'weitergeführt' if weiter else 'neu'}): "
                   f"{self._aufnahme_name}")

    def _wegpunkt(self, name):
        name = name or f"Punkt {self._wegpunkte_gesetzt + 1}"
        try:
            self._sitzung.waypoint(name)
        except Exception as fehler:
            self._setze(grund=f"Wegpunkt nicht gesetzt: {fehler}")
            return
        self._wegpunkte_gesetzt += 1
        self._setze(grund=f"Wegpunkt ‹{name}› gesetzt")

    def _stoppen(self, name):
        from spotlab.maps import store

        sitzung = self._sitzung
        if self.zustand == "nimmt_auf":
            self._setze(zustand="speichert", grund="Aufnahme beenden …")
            try:
                sitzung.stop()
            except Exception as fehler:
                self.melde(f"Aufnahme beenden: {fehler} — es wird trotzdem gespeichert.")
            sitzung.nachbearbeiten(melde=lambda text: self._setze(grund=f"Speichern: {text}"))
        self._setze(zustand="speichert", grund="Speichern: herunterladen …")
        wurzel = store.karten_wurzel(self.arbeitsordner)
        if self._ziel_name is None:
            self._ziel_name = freier_name(wurzel, name or self._aufnahme_name)
        try:
            ordner = Path(sitzung.download(wurzel, self._ziel_name))
            waende = self._waende_laden(ordner)
        except Exception as fehler:
            self._setze(zustand="nicht_gespeichert",
                        grund=f"nicht gespeichert — nochmal versuchen ({fehler})")
            return
        try:
            v = self.spot.backend.verortung()
        except Exception:
            v = None
        with self._sperre:
            self._sitzung = None
            self.name, self.waende, self.weiter = ordner.name, waende, False
            self._trafo, self._verortung = None, None
            self._zaehler.clear()
            self.zustand = "verortet" if v is not None else "sucht_tag"
            self.grund = f"gespeichert als ‹{ordner.name}›"
        self.melde(f"Karte gespeichert: {ordner}")

    def beenden(self, warte_s=BEENDEN_WARTE_S):
        """Am Programmende: eine laufende Aufnahme noch speichern, bevor Spot sich setzt."""
        if self._faden is not None:
            self._faden.join(timeout=warte_s)
        if self.zustand in ("nimmt_auf", "nicht_gespeichert") and self._sitzung is not None:
            self.melde("Die Kartenaufnahme wird noch gespeichert …")
            self._stoppen(None)

    # ------------------------------------------------------------ Lagebild

    def abgleiche(self, skizze, spot_xy, t):
        """Der `kartenabgleich.Abgleich` zur Skizze — oder None ohne Karte oder Lage."""
        with self._sperre:
            waende, trafo, verloren = self.waende, self._trafo, self.zustand == "verloren"
        if waende is None or trafo is None:
            return None
        punkte = kartenabgleich.in_vision(waende.zellen, trafo)
        return kartenabgleich.abgleich(skizze, punkte, spot_xy, t, verloren=verloren)

    def _urteil(self, t):
        drin = [e for e in self._zaehler if e[0] >= t - FENSTER_S] or list(self._zaehler)[-1:]
        if len(drin) < 2:
            return 0, 0
        return max(0, drin[-1][1] - drin[0][1]), max(0, drin[-1][2] - drin[0][2])

    def daten(self, t, abgleich):
        """Der Platz `karte` im Lagebild (Rahmen „vision“)."""
        with self._sperre:
            waende, trafo = self.waende, self._trafo
            wegpunkte = []
            if waende is not None and trafo is not None and waende.wegpunkte:
                orte = kartenabgleich.in_vision([(x, y) for x, y, _ in waende.wegpunkte], trafo)
                wegpunkte = [{"x": round(float(x), 3), "y": round(float(y), 3), "name": n}
                             for (x, y), (_, _, n) in zip(orte, waende.wegpunkte)]
            wieder = None
            if waende is not None and self._verortung is not None:
                angenommen, abgelehnt = self._urteil(t)
                wieder = {"verloren": self.zustand == "verloren", "angenommen": angenommen,
                          "abgelehnt": abgelehnt,
                          "anteil": None if abgleich is None else abgleich.anteil,
                          "wandzellen": 0 if abgleich is None else abgleich.erkannt + abgleich.neu,
                          "erkannt": 0 if abgleich is None else abgleich.erkannt,
                          "neu": 0 if abgleich is None else abgleich.neu,
                          "fehlt": 0 if abgleich is None else abgleich.fehlt}
            aufnahme = None
            if self.zustand in AUFNAHME_ZUSTAENDE:
                aufnahme = {"wegpunkte": self._aufnahme_stand[0],
                            "kanten": self._aufnahme_stand[1],
                            "name": self._aufnahme_name, "weiter": self.weiter}
            return {
                "kann": self.kann,
                "name": self.name,
                "zustand": self.zustand,
                "grund": self.grund,
                "auftrag": self.erledigt,
                "quelle": None if waende is None else waende.quelle,
                "aufnahme": aufnahme,
                "wegpunkte": wegpunkte,
                "kanten": [] if not wegpunkte else [[int(i), int(j)] for i, j in waende.kanten],
                "raster": None if abgleich is None else {
                    "ursprung": [abgleich.ursprung[0], abgleich.ursprung[1]],
                    "breite": abgleich.breite, "hoehe": abgleich.hoehe},
                "wiedererkennung": wieder,
            }
