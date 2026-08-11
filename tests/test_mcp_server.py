import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spotlab.mcp.server import WERKZEUGE
from tests_zeitgrenzen import zeile_mit_frist

QUELLE = str(Path(__file__).resolve().parents[1] / "src")
HAT_MCP = importlib.util.find_spec("mcp") is not None


def test_alle_dreizehn_werkzeuge_sind_angemeldet():
    assert {f.__name__ for f, _ in WERKZEUGE} == {
        "projekt_anbinden",
        "projekt_loesen",
        "anbindungen_auflisten",
        "panel_setzen",
        "panel_entfernen",
        "skript_starten",
        "lauf_stoppen",
        "laeufe_auflisten",
        "lauf_lesen",
        "zustand_zusammenfassen",
        "karten_auflisten",
        "karte_lesen",
        "spot_pruefen",
    }


def test_jedes_werkzeug_hat_eine_deutsche_beschreibung():
    for funktion, beschreibung in WERKZEUGE:
        assert beschreibung.strip(), funktion.__name__
        assert len(beschreibung) > 20, funktion.__name__


def test_werkzeugliste_ist_ohne_das_extra_lesbar():
    """WERKZEUGE darf nicht am mcp-Paket hängen — der Import steht in baue_server."""
    import pathlib
    import re

    import spotlab.mcp.server as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    kopf = quelle.split("def baue_server", 1)[0]
    assert re.search(r"^\s*(from|import)\s+mcp\b", kopf, re.M) is None


def test_ohne_mcp_paket_meldet_die_cli_den_installationsbefehl(monkeypatch, capsys):
    import spotlab.cli as cli

    monkeypatch.setattr(cli, "_mcp_vorhanden", lambda: False)
    code = cli.main(["mcp"])
    ausgabe = capsys.readouterr()
    assert code == 1
    assert "pip install" in (ausgabe.out + ausgabe.err)


@pytest.mark.skipif(not HAT_MCP, reason="Extra [mcp] nicht installiert")
def test_server_laesst_sich_bauen_und_kennt_alle_werkzeuge():
    import asyncio

    from spotlab.mcp.server import baue_server

    server = baue_server()
    angemeldet = {t.name for t in asyncio.run(server.list_tools())}
    assert {f.__name__ for f, _ in WERKZEUGE} <= angemeldet


@pytest.mark.skipif(not HAT_MCP, reason="Extra [mcp] nicht installiert")
def test_server_startet_wirklich_und_antwortet():
    """Ein echter Unterprozess mit echtem Handshake.

    Attrappen pruefen nur, dass die richtigen Argumente gebaut werden — nicht,
    dass das Betriebssystem und das Protokoll damit etwas anfangen koennen.
    """
    prozess = subprocess.Popen(
        [sys.executable, "-m", "spotlab.cli", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env={**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1"},
    )
    try:
        anfrage = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        prozess.stdin.write(json.dumps(anfrage) + "\n")
        prozess.stdin.flush()
        zeile = zeile_mit_frist(prozess.stdout)
        if not zeile:
            # Erst abraeumen, dann lesen: stderr.read() wartet sonst auf einen
            # Prozess, der vielleicht noch laeuft und nur nichts sagt.
            prozess.kill()
            raise AssertionError(f"keine Antwort; stderr: {prozess.stderr.read()}")
        antwort = json.loads(zeile)
        assert antwort["id"] == 1
        assert antwort["result"]["serverInfo"]["name"] == "spotlab"
    finally:
        prozess.kill()
        prozess.wait(timeout=10)


def test_die_fassung_steht_nur_an_einer_stelle():
    """S4.7 -- drei Kopien einer Zahl sind zwei Kopien zu viel.

    `version="0.1.0"` stand im MCP-Server fest und in pyproject.toml noch
    einmal. Beide waeren beim naechsten Sprung stumm falsch geworden: kein
    Test schlaegt fehl, wenn eine Fassungsnummer luegt.
    """
    import importlib.metadata

    import spotlab

    assert importlib.metadata.version("spotlab") == spotlab.__version__

    quelle = (Path(__file__).resolve().parents[1] / "src/spotlab/mcp/server.py").read_text(
        encoding="utf-8"
    )
    assert 'version="' not in quelle, "Der Server schreibt die Fassung wieder selbst hin"
