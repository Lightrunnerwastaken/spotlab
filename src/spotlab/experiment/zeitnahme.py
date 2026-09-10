"""Wer wann losgeht und ankommt — mehrere Uhren gleichzeitig.

Der Grund fuer das ganze Programm. Ein Mensch mit der Stoppuhr im Gang kann
immer nur EINE Gruppe messen; hier laeuft fuer jede erkannte Person eine eigene
Uhr, und am Ende steht je Person eine Querung mit Start, Ziel und Tempo.

DREI VERWERFUNGSREGELN, und alle drei schreiben eine Querung — verworfen heisst
protokolliert, nicht verschwiegen:

    gestoppt    Wer laenger als `stopp_dauer_s` steht, hat die Strecke nicht
                gegangen. Der ausdrueckliche Wunsch des Autors und der
                haeufigste Stoerfall im Gang: zwei bleiben stehen und reden.
    umgekehrt   Wer hinter die Startlinie zurueckfaellt, laeuft etwas anderes.
    verloren    Wer laenger als `verlust_s` nicht mehr zu sehen war. Ein halb
                gemessener Lauf, der stillschweigend verschwaende, waere die
                gefaehrlichste Variante: die Tabelle saehe vollstaendig aus.

Eine verworfene Querung hat `dauer_s = None` und `tempo_m_s = None`, nie 0 —
dieselbe Regel wie ueberall im Projekt: fehlende Messwerte sind None.

DIE UHR STARTET AUF DER LINIE, nicht beim naechsten Bild. Der Uebertritt wird
zwischen den beiden Abtastungen interpoliert; bei 5 Hz waeren es sonst bis zu
0.2 s Fehler auf jede Messung, und bei einer Laufzeit von 8 s sind das
zweieinhalb Prozent — mehr als der Unterschied, den der Versuch messen will.

Reine Standardbibliothek. Diese Datei weiss nichts von Kameras, Tags oder
Trackern: sie bekommt Zahlen und liefert Zahlen. Woher die Lage einer Person
kommt, entscheidet die QUELLE in `workshop/gehzeit.py` — dieselbe Trennung wie
zwischen Finder und Regler beim Folgen.
"""

from dataclasses import dataclass

# So weit seitlich der Strecke zaehlt jemand noch als Laeufer. Der Gang ist
# breiter als die Linie zwischen den Tags, aber der Rest des Raums gehoert nicht
# dazu.
KORRIDOR_M = 2.0
# Darunter gilt jemand als stehend ...
STOPP_TEMPO_M_S = 0.15
# ... und so lange darf er das, bevor der Lauf verworfen wird. Kuerzer waere
# Messrauschen: ein einzelnes Bild ohne Fortschritt ist kein Stehenbleiben.
STOPP_DAUER_S = 1.5
# So lange darf jemand unsichtbar sein, bevor sein Lauf verworfen wird.
VERLUST_S = 2.0
# So weit darf jemand hinter die Startlinie zuruecktreten, ohne dass es als
# Umkehr gilt — ein Schritt zur Seite verschiebt die Projektion.
UMKEHR_M = 0.5


@dataclass(frozen=True)
class Sicht:
    """Eine Person in einem Takt: wer, wo auf der Strecke, wie weit daneben."""

    kennung: str
    s_m: float          # Meter entlang der Strecke, ab dem Start-Tag
    quer_m: float       # Meter seitlich der Strecke, immer positiv


@dataclass(frozen=True)
class Querung:
    """Ein Lauf ueber die Strecke — gemessen oder verworfen."""

    kennung: str
    richtung: int            # +1 vom Start-Tag zum Ziel-Tag, -1 andersherum
    t_start: float
    t_ende: float
    dauer_s: float = None
    tempo_m_s: float = None
    verworfen: bool = False
    grund: str = None


class _Lauf:
    """Die offene Uhr einer Person. Nur innerhalb dieses Moduls sichtbar."""

    __slots__ = ("richtung", "t_start", "still_seit")

    def __init__(self, richtung, t_start):
        self.richtung = richtung
        self.t_start = t_start
        self.still_seit = None


def _kreuzung(t0, s0, t1, s1, linie):
    """Der Zeitpunkt, zu dem die Marke `linie` ueberschritten wurde."""
    if s1 == s0:
        return t1
    anteil = (linie - s0) / (s1 - s0)
    return t0 + anteil * (t1 - t0)


class Zeitnahme:
    """Haelt je Person eine Uhr und liefert fertige Querungen.

    `beobachte(t, sichten)` wird in jedem Takt gerufen und gibt die Querungen
    zurueck, die IN DIESEM Takt fertig geworden sind — gemessen oder verworfen.
    Zustand haelt nur diese Klasse; das Programm darum herum bleibt eine
    Schleife ohne Gedaechtnis.
    """

    def __init__(self, strecke, korridor_m=KORRIDOR_M,
                 stopp_tempo_m_s=STOPP_TEMPO_M_S, stopp_dauer_s=STOPP_DAUER_S,
                 verlust_s=VERLUST_S, umkehr_m=UMKEHR_M):
        self._strecke = strecke
        self._korridor = float(korridor_m)
        self._stopp_tempo = float(stopp_tempo_m_s)
        self._stopp_dauer = float(stopp_dauer_s)
        self._verlust = float(verlust_s)
        self._umkehr = float(umkehr_m)
        self._letzte = {}        # kennung -> (t, s)
        self._laeufe = {}        # kennung -> _Lauf

    # ----------------------------------------------------------- Abfragen

    def laufende(self):
        """Wie viele Uhren gerade laufen. Daran haengt der Bildmitschnitt."""
        return len(self._laeufe)

    # --------------------------------------------------------------- Takt

    def beobachte(self, t, sichten):
        fertig = []
        gesehen = set()
        for sicht in sichten:
            if abs(sicht.quer_m) > self._korridor:
                # Wer danebensteht, laeuft die Strecke nicht. Auch seine letzte
                # Lage wird nicht gemerkt: sonst entstuende beim Wiedereintritt
                # eine Geschwindigkeit aus zwei Orten, die nichts miteinander zu
                # tun haben.
                continue
            gesehen.add(sicht.kennung)
            ende = self._eine_sicht(t, sicht)
            if ende is not None:
                fertig.append(ende)
        fertig += self._verlorene(t, gesehen)
        return fertig

    # ------------------------------------------------------------- Intern

    def _eine_sicht(self, t, sicht):
        vorher = self._letzte.get(sicht.kennung)
        self._letzte[sicht.kennung] = (t, sicht.s_m)
        if vorher is None or t <= vorher[0]:
            # Ohne zwei Punkte gibt es keine Richtung und keine Geschwindigkeit.
            return None
        t0, s0 = vorher
        lauf = self._laeufe.get(sicht.kennung)
        if lauf is None:
            self._vielleicht_starten(sicht.kennung, t0, s0, t, sicht.s_m)
            return None
        return self._weiterlaufen(sicht.kennung, lauf, t0, s0, t, sicht.s_m)

    def _vielleicht_starten(self, kennung, t0, s0, t1, s1):
        """Eine Uhr startet NUR beim Uebertritt einer der beiden Linien.

        Wer mitten auf der Strecke auftaucht, bekommt keine Zeit: eine geratene
        Startzeit waere schlimmer als gar keine Messung.
        """
        laenge = self._strecke.laenge_m
        if s0 < 0.0 <= s1:
            self._laeufe[kennung] = _Lauf(+1, _kreuzung(t0, s0, t1, s1, 0.0))
        elif s0 > laenge >= s1:
            self._laeufe[kennung] = _Lauf(-1, _kreuzung(t0, s0, t1, s1, laenge))

    def _weiterlaufen(self, kennung, lauf, t0, s0, t1, s1):
        laenge = self._strecke.laenge_m
        tempo = (s1 - s0) / (t1 - t0)

        # Umkehr zuerst: wer zurueckfaellt, steht dabei oft auch still, und
        # "umgekehrt" ist die genauere Auskunft.
        zurueck = s1 if lauf.richtung > 0 else laenge - s1
        if zurueck < -self._umkehr:
            return self._verwerfen(kennung, lauf, t1, "umgekehrt")

        if abs(tempo) < self._stopp_tempo:
            lauf.still_seit = t0 if lauf.still_seit is None else lauf.still_seit
            if t1 - lauf.still_seit >= self._stopp_dauer:
                return self._verwerfen(kennung, lauf, t1, "gestoppt")
        else:
            lauf.still_seit = None

        ziel = laenge if lauf.richtung > 0 else 0.0
        angekommen = (s0 < ziel <= s1) if lauf.richtung > 0 else (s0 > ziel >= s1)
        if angekommen:
            t_ende = _kreuzung(t0, s0, t1, s1, ziel)
            dauer = t_ende - lauf.t_start
            del self._laeufe[kennung]
            return Querung(
                kennung=kennung, richtung=lauf.richtung, t_start=lauf.t_start,
                t_ende=t_ende, dauer_s=dauer,
                tempo_m_s=(laenge / dauer) if dauer > 0 else None,
            )
        return None

    def _verwerfen(self, kennung, lauf, t, grund):
        del self._laeufe[kennung]
        return Querung(
            kennung=kennung, richtung=lauf.richtung, t_start=lauf.t_start,
            t_ende=t, verworfen=True, grund=grund,
        )

    def _verlorene(self, t, gesehen):
        fertig = []
        for kennung, lauf in list(self._laeufe.items()):
            zuletzt = self._letzte.get(kennung)
            if kennung in gesehen or zuletzt is None:
                continue
            if t - zuletzt[0] > self._verlust:
                fertig.append(self._verwerfen(kennung, lauf, t, "verloren"))
        return fertig
