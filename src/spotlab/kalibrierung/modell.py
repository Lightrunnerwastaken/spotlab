"""Das Gangmodell: aus der Kennlinie wird eine Bewegung.

Interpolation zwischen gemessenen Stützstellen, sonst nichts. Kein Regler,
keine Kontaktrechnung, keine Massen.

WAS DAS MODELL BEANTWORTET
    „Wenn sich der Roboter mit v vorwärts und w um die Hochachse bewegt —
    wie stehen dann seine zwölf Gelenke zur Gangphase p?"

WAS ES NICHT BEANTWORTET
    „Wie schnell fährt er, wenn ich v kommandiere?" Diese Kurve gibt es
    nicht. Im Beobachter-Modus hat niemand kommandiert; `ziel_m_s` ist die
    ABSICHT des Bedieners, und er hat mit der Live-Anzeige darauf hin
    gesteuert. Die Abweichung zwischen Absicht und Erreichtem misst also, wie
    gut ein Mensch ein Tablet bedient, nicht wie gut der Roboter folgt. Wer sie
    als Schleppfehler ausgäbe, verkaufte Bedienfehler als Robotereigenschaft.

    Deshalb gilt hier: kommandiert IST erreicht. Der Schleppfehler des echten
    Spot bleibt unbekannt, bis jemand mit `gates_real.py` kommandiert misst —
    und das steht hinter Sperrpunkt A1.

AUSSERHALB DER MESSUNG
    Unter der langsamsten und über der schnellsten gemessenen Gangart gibt es
    keine Daten. Das Modell nimmt dann die nächstgelegene gemessene Gangart und
    meldet das über `rand`. Es erfindet keine Zwischenform.
"""

import math

# Stützstellen mit weniger Absicht als das gelten als „stand herum" und
# tragen keine Gangaussage. Der Rundgang (B7) und die Treppe (B6) fallen
# damit heraus: dort wollte niemand ein Tempo halten, und die Punkte lägen
# alle am langsamen Ende und zögen die Interpolation dorthin.
NUR_MIT_ABSICHT = True

# Ab welchem Anteil eine Bewegung als „dreht" statt „fährt" gilt. Gemessen
# wurde beides getrennt: die B2-Fenster haben Drehraten um 0.000, die
# B3-Fenster Tempi um 0.005. Eine kombinierte Bewegung wurde NIE vermessen.
DREH_SCHWELLE = 0.15        # rad/s je m/s


class Gangmodell:
    """Interpoliert zwischen den gemessenen Gangarten."""

    def __init__(self, kennlinie, nur_mit_absicht=NUR_MIT_ABSICHT):
        stellen = kennlinie["stuetzstellen"]
        if nur_mit_absicht:
            stellen = [s for s in stellen if s.get("absicht")]
        self.phasenpunkte = kennlinie["phasenpunkte"]
        self.fahren = sorted(
            (s for s in stellen if "ziel_m_s" in s.get("absicht", {})),
            key=lambda s: s["tempo_m_s"],
        )
        self.drehen = sorted(
            (s for s in stellen if "ziel_rad_s" in s.get("absicht", {})),
            key=lambda s: abs(s["drehrate_rad_s"]),
        )
        if not self.fahren:
            raise ValueError("Die Kennlinie enthält keine Fahrt-Stützstellen.")
        self.gelenknamen = sorted(self.fahren[0]["gelenke"])
        self.hoehe_m = sum(s["hoehe_m"] for s in stellen) / len(stellen)

    # ------------------------------------------------------------- Auswahl

    @property
    def tempo_bereich(self):
        return self.fahren[0]["tempo_m_s"], self.fahren[-1]["tempo_m_s"]

    @property
    def tempo_vorschlag(self):
        """Ein Tempo aus der Mitte des VERMESSENEN Bereichs.

        VORSCHLAG, keine Messung: für eine Zieltrajektorie wählt der echte Spot
        sein Tempo selbst, und das wurde nie aufgezeichnet. Statt eine Zahl zu
        erfinden, wird eine genommen, für die es eine Gangart gibt — die Mitte,
        damit sie von beiden Rändern weit weg liegt.
        """
        return self.fahren[len(self.fahren) // 2]["tempo_m_s"]

    @property
    def drehrate_vorschlag(self):
        """Dasselbe für die Drehung. Ohne Dreh-Stützstellen: 0.0."""
        if not self.drehen:
            return 0.0
        return abs(self.drehen[len(self.drehen) // 2]["drehrate_rad_s"])

    @property
    def dreh_bereich(self):
        if not self.drehen:
            return 0.0, 0.0
        return abs(self.drehen[0]["drehrate_rad_s"]), abs(self.drehen[-1]["drehrate_rad_s"])

    def _nachbarn(self, stellen, wert, schluessel):
        """(links, rechts, anteil, rand) — rand sagt, ob extrapoliert würde."""
        werte = [abs(s[schluessel]) for s in stellen]
        if wert <= werte[0]:
            return stellen[0], stellen[0], 0.0, wert < werte[0]
        if wert >= werte[-1]:
            return stellen[-1], stellen[-1], 0.0, wert > werte[-1]
        for i in range(len(werte) - 1):
            if werte[i] <= wert <= werte[i + 1]:
                spanne = werte[i + 1] - werte[i]
                anteil = 0.0 if spanne <= 0 else (wert - werte[i]) / spanne
                return stellen[i], stellen[i + 1], anteil, False
        return stellen[-1], stellen[-1], 0.0, True

    def gangart(self, tempo_m_s, drehrate_rad_s):
        """Welche Gangart gilt bei dieser Bewegung?

        Gibt (links, rechts, anteil, rand, art) zurück. `art` ist "fahrt" oder
        "drehung"; eine KOMBINIERTE Bewegung wurde nie vermessen, deshalb wird
        die dominierende Achse gewählt statt zwischen zwei Messreihen zu
        mischen, die nichts miteinander zu tun haben.
        """
        tempo, dreh = abs(tempo_m_s), abs(drehrate_rad_s)
        dreht = self.drehen and dreh > DREH_SCHWELLE * max(tempo, 1e-6)
        if dreht:
            links, rechts, anteil, rand = self._nachbarn(
                self.drehen, dreh, "drehrate_rad_s"
            )
            return links, rechts, anteil, rand, "drehung"
        links, rechts, anteil, rand = self._nachbarn(self.fahren, tempo, "tempo_m_s")
        return links, rechts, anteil, rand, "fahrt"

    # ------------------------------------------------------------- Auswertung

    @staticmethod
    def _misch(a, b, anteil):
        return a + (b - a) * anteil

    def zyklusdauer(self, tempo_m_s, drehrate_rad_s):
        links, rechts, anteil, _, _ = self.gangart(tempo_m_s, drehrate_rad_s)
        return self._misch(links["zyklusdauer_s"], rechts["zyklusdauer_s"], anteil)

    def gelenke(self, tempo_m_s, drehrate_rad_s, phase):
        """Die zwölf Gelenkwinkel bei dieser Bewegung und Gangphase."""
        links, rechts, anteil, _, _ = self.gangart(tempo_m_s, drehrate_rad_s)
        stelle = (phase % 1.0) * self.phasenpunkte
        k0 = int(stelle) % self.phasenpunkte
        k1 = (k0 + 1) % self.phasenpunkte
        rest = stelle - int(stelle)
        winkel = {}
        for name in self.gelenknamen:
            a = self._misch(links["gelenke"][name][k0], links["gelenke"][name][k1], rest)
            b = self._misch(rechts["gelenke"][name][k0], rechts["gelenke"][name][k1], rest)
            winkel[name] = self._misch(a, b, anteil)
        return winkel

    def fusskontakte(self, tempo_m_s, drehrate_rad_s, phase):
        """Welche Füsse stehen? Aus gemessener Duty und Phasenlage.

        Bein i setzt bei seiner Phase auf und steht `duty` lang. Beides ist
        gemessen; die Rechteckform dazwischen ist die Vereinfachung — ein Fuss
        ist entweder unten oder oben, ein Zwischending gibt es im Protobuf auch
        nicht.
        """
        links, rechts, anteil, _, _ = self.gangart(tempo_m_s, drehrate_rad_s)
        p = phase % 1.0
        kontakte = []
        for i in range(4):
            duty = self._misch(links["duty"][i], rechts["duty"][i], anteil)
            versatz = links["phasen"][i] if i < len(links["phasen"]) else 0.0
            versatz = 0.0 if versatz is None else versatz
            seit = (p - versatz) % 1.0
            kontakte.append(seit < duty)
        return kontakte

    def rand(self, tempo_m_s, drehrate_rad_s):
        """True, wenn ausserhalb des vermessenen Bereichs gefragt wird."""
        return self.gangart(tempo_m_s, drehrate_rad_s)[3]

    def beschreibung(self, tempo_m_s, drehrate_rad_s):
        links, rechts, anteil, rand, art = self.gangart(tempo_m_s, drehrate_rad_s)
        return {
            "art": art,
            "muster": links["muster"] if anteil < 0.5 else rechts["muster"],
            "zwischen": [links["herkunft"]["fenster"], rechts["herkunft"]["fenster"]],
            "anteil": round(anteil, 3),
            "ausserhalb_der_messung": rand,
        }


def lade_modell(pfad=None):
    from spotlab.kalibrierung import gang

    return Gangmodell(gang.lade(pfad) if pfad else gang.lade())


def integriere(pose, vx, vy, wz, dt):
    """Körperpose im odom-Frame fortschreiben. (x, y, yaw) -> (x, y, yaw).

    Die Geschwindigkeit steht im KÖRPERframe, die Pose im odom-Frame — ohne
    die Drehung wanderte der Roboter beim Kurvenfahren geradeaus weiter.
    """
    x, y, yaw = pose
    yaw_neu = yaw + wz * dt
    mitte = yaw + wz * dt / 2.0        # Mittelwert über den Schritt
    x += (vx * math.cos(mitte) - vy * math.sin(mitte)) * dt
    y += (vx * math.sin(mitte) + vy * math.cos(mitte)) * dt
    return x, y, (yaw_neu + math.pi) % (2 * math.pi) - math.pi
