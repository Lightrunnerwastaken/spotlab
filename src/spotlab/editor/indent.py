"""Einrueckung als Textarbeit.

Im Widget bleibt damit nur noch das Einfuegen uebrig — die Regeln selbst
werden hier ohne Fenster geprueft.
"""

EINRUECKUNG = "    "


def einrueckung_von(zeile):
    """Die fuehrenden Leerzeichen einer Zeile."""
    return zeile[: len(zeile) - len(zeile.lstrip(" "))]


def naechste_einrueckung(zeile):
    """Womit die Folgezeile beginnt: gleich viel, nach ':' eine Ebene mehr."""
    tiefe = einrueckung_von(zeile)
    return tiefe + EINRUECKUNG if zeile.rstrip().endswith(":") else tiefe


def ausruecken(zeile):
    """Wie viele fuehrende Leerzeichen bei Shift+Tab wegfallen (hoechstens eine Ebene)."""
    return min(len(einrueckung_von(zeile)), len(EINRUECKUNG))
