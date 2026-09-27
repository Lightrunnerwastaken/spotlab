"""Welche Räume kann der Physikmodus? — EINE Regel für den Tab „Fahren“ und `backends/physics.py`.

Der Kraftregler aus matura-spot plant Schritte auf einer festen Bodenhöhe. Ebene Räume gehen
mit allem, was der Raumeditor hineinstellt: Wände, Blöcke, Tags und Sperrzonen (eine Zone ist
eine Regel, keine Geometrie — der Physik-Takt hält davor wie die anderen Übungsräume). Dazu
die zwei eigens validierten Szenen: ein waagerechtes Podest bis 6 cm (`physik_einzelstufe`) und
die Versuchstreppe 3 × 4 cm (`physik_treppe_3stufen`, nur vom Start (0, 0, 0)). Rampen,
Treppen und Gelände sind Stufe C der Physik — bis dahin sagt die Regel es, bevor etwas startet.

Reine Standardbibliothek: die GUI fragt dieselbe Regel.
"""

EBEN, EINZELSTUFE, TREPPE3 = "eben", "einzelstufe", "treppe3"
NICHT_EBEN = ("Der Physikmodus kann noch keine Rampen, Treppen und kein Gelände — nur ebene "
              "Räume (Wände, Blöcke, Tags, Sperrzonen gehen). Einen ebenen Raum wählen oder den "
              "Übungsraum 3D (Wiedergabe) nehmen.")
# Was der Physikmodus ist -- derselbe Text im Editor und im Tab „Fahren“.
ERKLAERUNG = ("Physik: Kontaktkräfte tragen den Körper, und ein eigener Kraftregler aus "
              "matura-spot setzt die Füsse — nicht der Regler von Boston Dynamics. An 60 echten "
              "Fahrten nachgespielt, ohne Sturz. Zeigt, wie ein Laufroboter wirklich geht; "
              "braucht mehr Rechenzeit und kann nur ebene Räume.")
OHNE_SIMULATION = ("Der Physikmodus braucht die Simulation — einrichten.cmd erneut ausführen "
                   "(Entwickler: matura-spot mit -MitSim einbinden).")
_TREPPE3 = ((.65, .4, .04), (1.05, .4, .08), (1.85, 1.2, .12))    # x, breite, z je Stufe


def tauglich(raum, start=None):
    """(ok, art, grund): art ist "eben", "einzelstufe" oder "treppe3" — oder None mit Grund."""
    if raum is None:
        return True, EBEN, ""
    if raum.gelaende is not None:
        return False, None, NICHT_EBEN
    if not raum.boeden:
        return True, EBEN, ""
    if _einzelstufe(raum):
        if start is not None and abs(start[2]) > .01:
            return False, None, "Die Physik-Einzelstufe ist nur mit Startwinkel 0 validiert."
        return True, EINZELSTUFE, ""
    if _treppe3(raum):
        if start is not None and (abs(start[0]) > 1e-6 or abs(start[1]) > 1e-6
                                  or abs(start[2]) > .01):
            return False, None, "Die Versuchstreppe ist nur mit Start (0, 0, 0) validiert."
        return True, TREPPE3, ""
    return False, None, NICHT_EBEN


def _einzelstufe(raum):
    if len(raum.boeden) != 1:
        return False
    b = raum.boeden[0]
    return (b.anstieg == 0 and 0 < b.z <= .060001 and b.drehung == 0
            and b.breite >= .8 and b.tiefe >= 1)


def _treppe3(raum):
    b = sorted(raum.boeden, key=lambda boden: boden.x)
    return len(b) == 3 and all(
        abs(boden.x - x) < 1e-6 and abs(boden.y) < 1e-6 and abs(boden.breite - breite) < 1e-6
        and abs(boden.tiefe - 2) < 1e-6 and abs(boden.z - z) < 1e-6
        and boden.anstieg == 0 and boden.drehung == 0
        for boden, (x, breite, z) in zip(b, _TREPPE3))
