"""Wo Laeufe liegen — der EINE Ort, an dem das entschieden wird.

Laeufe liegen an zwei Stellen: unter <arbeitsordner>/<projekt>/runs/ und, bei
angebundenen fremden Projekten, unter <skriptordner>/runs/. Der zweite Ort
liegt AUSSERHALB des Arbeitsordners; ohne ihn bliebe „Live-Lauf" bei fremden
Projekten leer, obwohl der Lauf laeuft — derselbe Fehler wie in Stufe 3.

Abgeleitet statt gesucht: nur die Ordner, die im Manifest stehen. Kein
rekursives Absuchen fremder Repos.

Qt-frei, damit GUI und MCP-Server dieselbe Funktion benutzen. Zwei Suchen mit
verschiedenen Ergebnissen waeren der alte Fehler in neuem Gewand.
"""

from pathlib import Path

from spotlab.anbindung.speicher import anbindungen, lauf_verzeichnisse_von


def _laeufe_in(runs):
    try:
        return sorted((p for p in Path(runs).iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        return []


def _runs_wurzeln(workspace):
    """Alle runs/-Ordner: die der Werkstattprojekte und die der Anbindungen."""
    wurzel = Path(workspace)
    wurzeln = []
    try:
        projekte = sorted((p for p in wurzel.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        projekte = []
    for projekt in projekte:
        runs = projekt / "runs"
        if runs.is_dir():
            wurzeln.append(runs)
    for anbindung in anbindungen(workspace):
        wurzeln.extend(lauf_verzeichnisse_von(anbindung))
    return wurzeln


def lauf_verzeichnisse(workspace):
    """Alle Lauf-Verzeichnisse, ohne Doppelte, in stabiler Reihenfolge."""
    gefunden = {}
    for runs in _runs_wurzeln(workspace):
        for lauf in _laeufe_in(runs):
            gefunden[str(lauf)] = lauf
    return list(gefunden.values())


def finde_lauf(workspace, lauf_id):
    """Das Verzeichnis zu einer Lauf-Kennung — oder None."""
    for lauf in lauf_verzeichnisse(workspace):
        if lauf.name == lauf_id:
            return lauf
    return None
