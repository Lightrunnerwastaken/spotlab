"""Eine GUI startet erst nach Prozessende das naechste Schuelerprogramm."""
from pathlib import Path
from threading import Lock

from spotlab.errors import SpotlabError
from spotlab.workshop.launcher import start_script as _start_script

_sperre = Lock()
_prozess = None
_skript = None


def laufender_prozess():
    """Der Prozess des letzten Starts, solange er lebt -- sonst None.

    Fuer Stopp und NOT-AUS in der Anlaufphase, bevor der Lauf ein Verzeichnis hat.
    """
    with _sperre:
        if _prozess is not None and _prozess.poll() is None:
            return _prozess
        return None


def start_script(pfad, **kwargs):
    global _prozess, _skript
    # Prozessstatus statt Telemetrie-Alter: Start und Abbau gehoeren zum Lauf.
    with _sperre:
        if _prozess is not None and _prozess.poll() is None:
            raise SpotlabError(
                f"{_skript} laeuft noch oder wird gerade beendet. "
                "Stoppe den Lauf und warte auf sein vollstaendiges Ende, "
                "bevor du ein neues Programm startest."
            )
        _prozess = _start_script(pfad, **kwargs)
        _skript = Path(pfad).name
        return _prozess
