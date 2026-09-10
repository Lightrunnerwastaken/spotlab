"""Welche Querungen zeitlich zusammengehoeren — als VORSCHLAG, nicht als Urteil.

Ob drei Leute eine Gruppe sind oder drei Einzelne, die zufaellig gleichzeitig
losgehen, kann Spot nicht wissen. Er kann sagen, wer GLEICHZEITIG unterwegs war;
den Rest entscheidet der Mensch, nachdem er den Abschnitt angesehen hat. Genau
dafuer ist der Versuch so gebaut: Spot misst die Zeiten (das kann er besser als
ein Mensch mit einer Stoppuhr, weil er mehrere gleichzeitig nimmt), der Mensch
traegt die Gruppengroesse nach (das kann er besser, weil er sieht, ob die drei
miteinander reden).

`personen` ist deshalb ein Vorschlag, kein Ergebnis. `gruppengroesse` steht in
der Tabelle und ist leer, bis jemand sie eintraegt.

DIE LAUFZEIT EINER GRUPPE ist der Median der Mitgliederzeiten, nicht ihr
Mittelwert: ein Mitglied, dessen Tag einmal springt, zoege den Mittelwert mit.
Die `spanne_s` steht daneben — weit auseinanderliegende Zeiten sind der Hinweis,
dass es gar keine Gruppe war, und der gehoert dem Menschen vorgelegt, nicht
weggemittelt.

Reine Standardbibliothek.
"""

import statistics
from dataclasses import dataclass

# So lange darf zwischen zwei Querungen Ruhe sein, bevor ein neuer Durchgang
# beginnt. Der Nachzuegler einer Gruppe geht ein paar Sekunden spaeter los; die
# naechste Klasse kommt erst nach der Pause.
LUECKE_S = 5.0


@dataclass(frozen=True)
class Durchgang:
    """Alles, was in einem Zeitfenster ueber die Strecke ging."""

    nummer: int
    t_start: float
    t_ende: float
    querungen: tuple
    personen: int            # so viele hat Spot gesehen — der Vorschlag
    gemessen: int            # so viele haben die Strecke sauber durchlaufen
    verworfen: int           # so viele wurden verworfen (Grund je Querung)
    gruende: tuple
    laufzeit_s: float = None
    spanne_s: float = None

    @property
    def gueltig(self):
        """Der Wunsch des Autors: 'wenn die zB stoppen wird das ergebnis
        verworfen'. Ein Abbruch in der Gruppe kippt den ganzen Durchgang —
        die Zahlen bleiben trotzdem in der Tabelle, mit Grund.
        """
        return self.gemessen > 0 and self.verworfen == 0


def durchgaenge_aus(querungen, luecke_s=LUECKE_S):
    """Querungen nach Zeit gruppieren, aeltester Durchgang zuerst."""
    geordnet = sorted(querungen, key=lambda q: (q.t_start, str(q.kennung)))
    gruppen = []
    for querung in geordnet:
        if gruppen and querung.t_start - max(q.t_ende for q in gruppen[-1]) <= luecke_s:
            gruppen[-1].append(querung)
        else:
            gruppen.append([querung])
    return [_baue(nummer, gruppe) for nummer, gruppe in enumerate(gruppen, start=1)]


def _baue(nummer, gruppe):
    gueltige = [q for q in gruppe if not q.verworfen and q.dauer_s is not None]
    dauern = [q.dauer_s for q in gueltige]
    return Durchgang(
        nummer=nummer,
        t_start=min(q.t_start for q in gruppe),
        t_ende=max(q.t_ende for q in gruppe),
        querungen=tuple(gruppe),
        personen=len({q.kennung for q in gruppe}),
        gemessen=len(gueltige),
        verworfen=sum(1 for q in gruppe if q.verworfen),
        gruende=tuple(sorted({q.grund for q in gruppe if q.grund})),
        laufzeit_s=statistics.median(dauern) if dauern else None,
        spanne_s=(max(dauern) - min(dauern)) if dauern else None,
    )
