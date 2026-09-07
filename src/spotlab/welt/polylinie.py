"""Polylinien vereinfachen -- Douglas-Peucker, reine Standardbibliothek.

Die Rekonstruktion glaettet damit das Hoehenprofil des Wegs, der Gelaendebau
legt dasselbe geglaettete Profil auf die Wegzellen.
"""

import math


def douglas_peucker(punkte, toleranz):
    """Indizes der Stuetzpunkte einer Polylinie [(x, y), ...] -- Douglas-Peucker."""
    if len(punkte) < 2:
        return list(range(len(punkte)))

    def teile(a, b):
        if b <= a + 1:
            return []
        ax, ay = punkte[a]
        bx, by = punkte[b]
        dx, dy = bx - ax, by - ay
        laenge = math.hypot(dx, dy)
        bester, abstand = -1, 0.0
        for i in range(a + 1, b):
            px, py = punkte[i]
            d = (abs(dx * (ay - py) - (ax - px) * dy) / laenge if laenge > 1e-12
                 else math.hypot(px - ax, py - ay))
            if d > abstand:
                bester, abstand = i, d
        if abstand > toleranz:
            return teile(a, bester) + [bester] + teile(bester, b)
        return []

    return [0] + teile(0, len(punkte) - 1) + [len(punkte) - 1]
