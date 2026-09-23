"""Die Konfiguration frisch von der Platte -- vor jedem Speichern aus der GUI.

Die Ansichten halten eine Kopie, die sie beim Start geladen haben. Wer sie
ergänzt und zurückschreibt, überschreibt alles, was inzwischen anderswo
gesetzt wurde: auf der Kommandozeile, in einer zweiten Ansicht, von Hand.
Am 23.09.2026 kam so `treppen = "auto"` zurück, obwohl „aus“ gesetzt war --
ein Sicherheitswert (`mobility.mit_grenze`). Deshalb: frisch laden, nur die
eigenen Felder ersetzen, schreiben.
"""

from spotlab.config import load_config
from spotlab.errors import SpotlabError


def frisch(ersatz=None):
    """Die Konfiguration, wie sie JETZT auf der Platte steht; fehlt oder bricht sie,
    `ersatz` (die Kopie der Ansicht, oder None)."""
    try:
        return load_config()
    except SpotlabError:
        return ersatz


def unberuehrt(feldwert, beim_laden_gezeigt, gespeichert):
    """Der gespeicherte Wert, wenn das Feld noch zeigt, was es beim Laden zeigte --
    sonst der Feldwert. Ein QDoubleSpinBox mit zwei Stellen zeigt 0.125 m/s als
    0.13 und machte daraus beim nächsten Speichern still 0.13. Verglichen wird mit
    der Anzeige des Feldes selbst, nicht mit `round()`: Python rundet 0.125 auf
    0.12, Qt auf 0.13."""
    if gespeichert is not None and feldwert == beim_laden_gezeigt:
        return gespeichert
    return feldwert
