"""Einrueckung als Textarbeit.

Im Widget bleibt damit nur noch das Einfuegen uebrig — die Regeln selbst
werden hier ohne Fenster geprueft.
"""

EINRUECKUNG = "    "


def einrueckung_von(zeile):
    """Die führenden Leerzeichen UND Tabs einer Zeile.

    Tabs zählen mit: `lstrip(" ")` sah sie nicht, und eine mit Tabs eingerückte
    Datei — aus VS Code oder aus fremdem Code — verlor bei jedem Zeilenumbruch
    ihre Ebene. Der Schüler tippt dann weiter und wundert sich über einen
    IndentationError in einer Datei, die vorher lief.
    """
    return zeile[: len(zeile) - len(zeile.lstrip(" \t"))]


def _ohne_kommentar_und_text(zeile):
    """Die Zeile ohne Zeichenketten und ohne Kommentar.

    Nur so lässt sich sagen, ob der Doppelpunkt am Ende ein BLOCK ist:
    `x = 1  # und dann:` endet auf einem Doppelpunkt und ist trotzdem keiner,
    und `s = "gilt hier:"` erst recht nicht. Kein Parser, nur ein Durchlauf —
    für die Frage „öffnet diese Zeile einen Block" genügt das.
    """
    ergebnis = []
    zeichen = None
    for stelle in zeile:
        if zeichen:
            if stelle == zeichen:
                zeichen = None
            continue
        if stelle in "\"'":
            zeichen = stelle
            continue
        if stelle == "#":
            break
        ergebnis.append(stelle)
    return "".join(ergebnis)


def naechste_einrueckung(zeile):
    """Womit die Folgezeile beginnt: gleich viel, nach einem Block eine Ebene mehr."""
    tiefe = einrueckung_von(zeile)
    if _ohne_kommentar_und_text(zeile).rstrip().endswith(":"):
        return tiefe + EINRUECKUNG
    return tiefe


def ausruecken(zeile):
    """Wie viel führender Leerraum bei Shift+Tab wegfällt (höchstens eine Ebene).

    Ein Tab ist EINE Ebene, egal wie breit er dargestellt wird — sonst risse
    Shift+Tab in einer Tab-Datei nur ein Zeichen von vieren weg.
    """
    tiefe = einrueckung_von(zeile)
    if tiefe.startswith("\t"):
        return 1
    return min(len(tiefe), len(EINRUECKUNG))
