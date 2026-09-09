"""Wo steht der Cursor: im Code, in einer Zeichenkette oder in einem Kommentar?

Der Editor fragt jedi bei jedem Tastendruck. Ohne diese Frage schlägt er auch
dort vor, wo nichts vorzuschlagen ist — gemessen am 09.09.2026: in einem
Kommentar liefert jedi 158 globale Namen, und in einer offenen Zeichenkette
Verzeichnisse des Laptops (`All Users\\`, `Default\\`, …). Das erste ist Lärm,
das zweite eine Überraschung: der Editor zeigte plötzlich den Inhalt der
Festplatte, weil jemand einen Pfad tippte.

Standardbibliothek und nichts sonst — dieselbe Regel wie für `verbs.py`, und
der Grund, warum das hier steht und nicht in `gui/`: so ist jeder Fall ohne
Fenster prüfbar.

Kein Tokenizer: `tokenize` wirft auf halb geschriebenem Code, und genau der
liegt beim Tippen vor. Der Zustandsautomat unten liest den Text VOR dem Cursor
einmal durch und merkt sich, ob er offen in einer Zeichenkette oder hinter
einem `#` steht. Dreifache Anführungszeichen zählen mit — sonst schlüge der
Editor mitten im Docstring Namen vor, und das ist die Stelle, an der ein
Schüler am längsten Prosa schreibt.
"""

from spotlab.editor.verbs import teilwort

CODE = "code"
ZEICHENKETTE = "zeichenkette"
KOMMENTAR = "kommentar"

# So viele Zeichen braucht ein angefangenes Wort, bevor die Liste aufgeht.
# Nach einem Punkt gilt das nicht: dort ist die leere Eingabe der Normalfall
# (`spot.`), und die Liste ist genau dann am nützlichsten.
MINDESTZEICHEN = 2

ANFUEHRUNG = "\"'"


def ort(text_bis_cursor):
    """`CODE`, `ZEICHENKETTE` oder `KOMMENTAR` — für den Text VOR dem Cursor."""
    text = str(text_bis_cursor)
    laenge = len(text)
    i = 0
    while i < laenge:
        zeichen = text[i]
        if zeichen == "#":
            zeilenende = text.find("\n", i)
            if zeilenende == -1:
                return KOMMENTAR            # der Kommentar reicht bis zum Cursor
            i = zeilenende + 1
            continue
        if zeichen in ANFUEHRUNG:
            marke = text[i:i + 3] if text[i:i + 3] in ('"""', "'''") else zeichen
            i += len(marke)
            geschlossen = False
            while i < laenge:
                if text[i] == "\\":
                    i += 2                  # das nächste Zeichen ist maskiert
                    continue
                if text.startswith(marke, i):
                    i += len(marke)
                    geschlossen = True
                    break
                if text[i] == "\n" and len(marke) == 1:
                    # Einzeilige Zeichenkette ohne Schluss: für Python ein
                    # Fehler, für den Editor endet sie an der Zeile. Sonst
                    # gälte der ganze Rest der Datei als Zeichenkette.
                    geschlossen = True
                    break
                i += 1
            if not geschlossen:
                return ZEICHENKETTE         # der Cursor steht mittendrin
            continue
        i += 1
    return CODE


def im_code(text_bis_cursor):
    return ort(text_bis_cursor) == CODE


def stelle_passt(zeile_vor_cursor, mindestzeichen=MINDESTZEICHEN):
    """Lohnt sich an dieser Stelle überhaupt eine Anfrage? Nur die Zeile, billig.

    Die günstige Hälfte der Entscheidung: sie braucht kein `toPlainText()` und
    steht deshalb vor `im_code`. Ein einzelner Buchstabe öffnet keine Liste —
    sonst springt sie beim Tippen jedes Wortes auf; nach einem Punkt schon,
    denn dort will man sie.
    """
    zeile = str(zeile_vor_cursor).rsplit("\n", 1)[-1]
    wort = teilwort(zeile)
    davor = zeile[: len(zeile) - len(wort)]
    if davor.endswith("."):
        return True
    return len(wort) >= mindestzeichen
