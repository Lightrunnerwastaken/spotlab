"""Syntaxfehler beim Tippen — auf Deutsch.

compile() aus der Standardbibliothek stellt exakt dieselbe Diagnose, die der
spaetere Lauf melden wuerde: keine Abhaengigkeit, kein Unterprozess. Nur ist
sie englisch, und genau daran scheitert ein Anfaenger. Uebersetzt wird die
Handvoll Meldungen, die Anfaenger wirklich treffen; alles andere bleibt im
Original stehen, mit deutschem Rahmen. Eine erfundene Erklaerung fuer einen
unbekannten Fehler schickt auf die falsche Faehrte und kostet mehr Zeit als
der englische Text.
"""

import warnings
from dataclasses import dataclass


@dataclass(frozen=True)
class Fehlerstelle:
    zeile: int      # 1-basiert; 1, wenn Python keine Zeile nennt
    spalte: int     # 1-basiert; 0, wenn unbekannt
    text: str       # deutsch


# GEORDNET: spezifisch vor allgemein. Das erste passende Fragment gewinnt.
UEBERSETZUNGEN = (
    ("Perhaps you forgot a comma", "Hier fehlt vermutlich ein Komma."),
    ("expected ':'", "Hier fehlt ein Doppelpunkt am Zeilenende."),
    ("was never closed", "Diese Klammer wurde nie geschlossen."),
    (
        "unterminated triple-quoted string literal",
        "Dieser mehrzeilige Text wurde nie geschlossen — es fehlen drei Anführungszeichen.",
    ),
    (
        "unterminated string literal",
        "Dieser Text wurde nie geschlossen — es fehlt ein Anführungszeichen.",
    ),
    (
        "expected an indented block",
        "Nach dem Doppelpunkt muss die nächste Zeile eingerückt sein.",
    ),
    ("unexpected indent", "Diese Zeile ist zu weit eingerückt."),
    ("unindent does not match", "Diese Einrückung passt zu keiner Zeile darüber."),
    (
        "inconsistent use of tabs",
        "Hier sind Tabulatoren und Leerzeichen gemischt. spotlab schreibt Leerzeichen.",
    ),
    ("cannot assign to", "Links vom = muss ein Name stehen."),
    (
        "invalid syntax",
        "Hier stimmt etwas nicht — häufig ein fehlender Doppelpunkt oder eine Klammer.",
    ),
)


def uebersetze(meldung):
    for fragment, text in UEBERSETZUNGEN:
        if fragment in meldung:
            return text
    return f"Python meldet: {meldung}"


def pruefe(quelltext, name="<editor>"):
    """Die erste Fehlerstelle — oder None, wenn der Text sich übersetzen lässt."""
    try:
        with warnings.catch_warnings():
            # Ohne das meldet compile() ab 3.12 bei JEDEM Tastendruck eine
            # SyntaxWarning fuer ungueltige Escape-Sequenzen wie "C:\daten".
            warnings.simplefilter("ignore")
            compile(quelltext, name, "exec")
    except SyntaxError as fehler:
        # Faengt auch IndentationError und TabError — beide sind Unterklassen.
        return Fehlerstelle(
            zeile=fehler.lineno or 1,
            spalte=fehler.offset or 0,
            text=uebersetze(fehler.msg or ""),
        )
    except ValueError as fehler:
        # Nullbytes im Text: compile() wirft ValueError, keinen SyntaxError.
        return Fehlerstelle(zeile=1, spalte=0, text=uebersetze(str(fehler)))
    return None
