import subprocess

import pytest

from spotlab.errors import SpotlabError
from spotlab.gui.editor import view
from spotlab.gui.theme import DUNKEL
from spotlab.gui.views import projects


@pytest.fixture
def warteskript(tmp_path):
    skript = tmp_path / 'wartet.py'
    skript.write_text("import sys\nprint('bereit', flush=True)\nsys.stdin.read()\n")
    return skript


def starte(start, skript):
    # Eigener harmloser Prozess, explizite Pipe statt geerbter Konsole.
    return start(skript, starter=lambda *a, **kw: subprocess.Popen(
        *a, stdin=subprocess.PIPE, **kw))


def beende(p):
    p.stdin.close()
    p.wait(timeout=10)
    p.stdout.close()


def test_projekte_und_code_starten_nicht_gleichzeitig(warteskript):
    erster = starte(projects.start_script, warteskript)
    zweiter = None
    try:
        assert erster.stdout.readline().strip() == 'bereit'
        with pytest.raises(SpotlabError):
            zweiter = starte(view.start_script, warteskript)
    finally:
        beende(erster)
        if zweiter is not None:
            beende(zweiter)
    # Freigabe erst nach echtem Prozessende, danach sofort wieder startbar.
    neuer = starte(view.start_script, warteskript)
    beende(neuer)


def test_watcher_ende_gibt_lebenden_prozess_nicht_frei(qapp, warteskript):
    editor = view.EditorView(DUNKEL)
    p = starte(view.start_script, warteskript)
    try:
        assert p.stdout.readline().strip() == 'bereit'
        editor._prozess = p
        editor._setze_laeuft(True)
        editor.lauf_beendet()
        assert editor._laeuft
        assert editor._prozess is p
    finally:
        beende(p)
    editor.pruefe_lauf_lebt()
    assert not editor._laeuft
    editor.close()
