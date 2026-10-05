"""Aufräumen nach Qt-Tests -- von `conftest.py` nach jedem Test gerufen."""

import sys


def halte_beobachter_an():
    """Stoppt den Lauf-Beobachter jedes noch lebenden Hauptfensters.

    Testfenster sterben nicht am Testende: Signalverbindungen und Lambdas halten
    sie in Referenzzyklen fest. Ihr `RunWatcher` lief dann in jedem späteren
    `processEvents()` mit -- am 05.10.2026 übernahm so ein altes Fenster einen
    Lauf und blockierte einen fremden Test bis zur 300-s-Grenze.

    Nur anhalten, nicht `close()`: `MainWindow.closeEvent` fragt bei
    ungespeicherten Reitern oder einem lebenden Lauf mit einem modalen Dialog --
    der hängt im Offscreen-Modus für immer.
    """
    # Aus sys.modules, nicht per `import`: läuft im Teardown, solange der Test
    # noch `builtins.__import__` ersetzt hat (`test_cli.py` spielt „PySide6 fehlt“).
    qtwidgets = sys.modules.get("PySide6.QtWidgets")
    if qtwidgets is None:
        return
    app = qtwidgets.QApplication.instance()
    if app is None:
        return
    for fenster in app.topLevelWidgets():
        beobachter = getattr(fenster, "_watcher", None)
        if beobachter is not None:
            beobachter.stop()
