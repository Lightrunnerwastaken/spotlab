"""Kommandozeile — eine dünne Hülle.

Alles, was hier steht, ist Argumentauswertung und Ausgabe. Die Funktionalität
liegt in workshop/ und api/, damit die spätere GUI und der MCP-Server sich an
derselben Schicht bedienen können.
"""

import argparse
import getpass
import sys
from pathlib import Path

from spotlab import __version__
from spotlab.errors import SpotlabError
from spotlab.record.read import list_runs, read_jsonl, read_run
from spotlab.workshop.doctor import diagnose
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import run_script
from spotlab.workshop.project import create_project

GRUEN, ROT, GRAU, AUS = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="spotlab", description="Den Spot programmieren — Kantonsschule"
    )
    parser.add_argument("--version", action="version", version=f"spotlab {__version__}")
    unter = parser.add_subparsers(dest="kommando", required=True)

    unter.add_parser("login", help="IP, Benutzer und Passwort hinterlegen")
    unter.add_parser("doctor", help="Netz, Anmeldung, Not-Aus, Lease und Akku prüfen")

    neu = unter.add_parser("new", help="neues Projekt anlegen")
    neu.add_argument("name")

    oeffnen = unter.add_parser("open", help="Projekt in VS Code öffnen")
    oeffnen.add_argument("projekt", nargs="?", default=".")

    starten = unter.add_parser("run", help="Skript starten und aufzeichnen")
    starten.add_argument("datei")
    starten.add_argument(
        "--dryrun", action="store_true", help="ohne Roboter, nur Kommandos prüfen"
    )

    laeufe = unter.add_parser("runs", help="Läufe auflisten")
    laeufe.add_argument("show", nargs="?", help="Lauf-ID für Details")

    lease = unter.add_parser("lease", help="wer steuert den Spot")
    lease.add_argument("--take", action="store_true", help="Kontrolle bewusst übernehmen")

    unter.add_parser("maps", help="aufgezeichnete Karten auflisten")

    aufnahme = unter.add_parser("record-map", help="eine Karte aufzeichnen")
    aufnahme.add_argument("name")
    aufnahme.add_argument(
        "--leeren", action="store_true", help="Karte auf dem Roboter zuerst leeren"
    )

    unter.add_parser("gui", help="Fenster öffnen")
    unter.add_parser("mcp", help="MCP-Server über stdin/stdout starten (für Agenten)")
    return parser


def _utf8_ausgabe():
    """Ausgabe auf UTF-8 zwingen.

    Alle Meldungen dieser Bibliothek sind deutsch. Auf einer Windows-Konsole mit
    cp1252 als Vorgabe kommen Umlaute sonst als Buchstabensalat an, und eine
    Fehlermeldung, die man nicht lesen kann, ist keine.
    """
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # z. B. unter pytest, wo stdout ersetzt ist


def main(argv=None):
    _utf8_ausgabe()
    args = build_parser().parse_args(argv)
    try:
        return _fuehre_aus(args)
    except SpotlabError as fehler:
        print(f"{ROT}{fehler}{AUS}", file=sys.stderr)
        return 1
    except FileExistsError as fehler:
        print(f"{ROT}{fehler}{AUS}", file=sys.stderr)
        return 1


def _fuehre_aus(args):
    if args.kommando == "login":
        return _login()
    if args.kommando == "doctor":
        return _doctor()
    if args.kommando == "new":
        ordner = create_project(args.name)
        print(f"Projekt angelegt: {ordner}")
        print(f"Weiter mit:  spotlab open {ordner.name}")
        return 0
    if args.kommando == "open":
        from spotlab.config import load_config

        try:
            befehl = load_config().editor_command
        except SpotlabError:
            befehl = "code"
        open_in_editor(Path(args.projekt).resolve(), command=befehl)
        return 0
    if args.kommando == "run":
        return run_script(args.datei, dryrun=args.dryrun)
    if args.kommando == "runs":
        return _runs(args.show)
    if args.kommando == "lease":
        return _lease(args.take)
    if args.kommando == "maps":
        return _maps()
    if args.kommando == "record-map":
        return _record_map(args.name, args.leeren)
    if args.kommando == "gui":
        return _gui()
    if args.kommando == "mcp":
        return _mcp()
    return 1


def _mcp_vorhanden():
    import importlib.util

    return importlib.util.find_spec("mcp") is not None


def _mcp():
    if not _mcp_vorhanden():
        print(
            "Der MCP-Server braucht das Extra `mcp`. Installieren mit:\n"
            '  pip install "spotlab[mcp]"',
            file=sys.stderr,
        )
        return 1
    from spotlab.mcp.server import main as server_main

    return server_main()


def _arbeitsordner():
    from spotlab.config import load_config

    cfg = load_config()
    if not cfg.workspace:
        raise SpotlabError(
            "Es ist kein Arbeitsordner gesetzt. Wähle einen in der Oberfläche "
            "(`spotlab gui`, Ansicht 'Projekte')."
        )
    return cfg, Path(cfg.workspace)


def _maps():
    from spotlab.maps.store import karten

    cfg, ordner = _arbeitsordner()
    liste = karten(ordner)
    if not liste:
        print(
            f"In {ordner} gibt es noch keine Karten. "
            f"Aufzeichnen mit:  spotlab record-map <name>"
        )
        return 0
    aktiv = cfg.active_map
    for eintrag in liste:
        marke = "*" if eintrag.name == aktiv else " "
        print(
            f"{marke} {eintrag.name:<24} {eintrag.wegpunkte:>4} Wegpunkte, "
            f"{eintrag.kanten:>4} Kanten   {eintrag.aufgezeichnet or ''}"
        )
    if aktiv:
        print("\n* = aktive Karte; im Skript reicht spot.load_map()")
    return 0


def _record_map(name, leeren):
    """Interaktiv wie das SDK-Beispiel: gefahren wird mit dem Tablet."""
    from spotlab.maps.session import RecordingSession
    from spotlab.maps.store import karten_wurzel

    cfg, ordner = _arbeitsordner()
    print(
        f"{GRAU}Der Spot muss ein Fiducial sehen. Gefahren wird mit dem TABLET — "
        f"spotlab zeichnet nur mit.{AUS}"
    )
    sitzung = RecordingSession.connect(cfg)
    try:
        sitzung.start(graph_leeren=leeren)
        print(
            f"{GRUEN}Aufnahme läuft.{AUS} Befehle: <Name> = Wegpunkt setzen · "
            f"s = Status · f = fertig"
        )
        while True:
            eingabe = input("> ").strip()
            if eingabe == "f":
                break
            if eingabe == "s":
                zustand = sitzung.status()
                print(
                    f"  {zustand.meldung} · {zustand.wegpunkte} Wegpunkte, "
                    f"{zustand.kanten} Kanten"
                )
                continue
            if eingabe:
                print(f"  Wegpunkt gesetzt: {sitzung.waypoint(eingabe)}")
        sitzung.stop()
        ziel = sitzung.download(karten_wurzel(ordner), name, roboter=cfg.nickname)
        print(f"{GRUEN}Karte gespeichert:{AUS} {ziel}")
    finally:
        sitzung.close()
    return 0


def _gui():
    try:
        from spotlab.gui.app import main as gui_main
    except ImportError:
        print(
            f"{ROT}Die Oberfläche braucht PySide6.{AUS}\n"
            "Einmalig installieren mit:\n"
            "    pip install -e .[gui]",
            file=sys.stderr,
        )
        return 1
    return int(gui_main([]) or 0)


def _login():
    from dataclasses import replace

    from spotlab.config import Config, load_config, save_config, save_password

    try:
        alt = load_config()
    except SpotlabError:
        alt = None
    ip = input(f"IP des Spot [{alt.ip if alt else '192.168.80.3'}]: ").strip() or (
        alt.ip if alt else "192.168.80.3"
    )
    benutzer = input(f"Benutzername [{alt.username if alt else 'user'}]: ").strip() or (
        alt.username if alt else "user"
    )
    spitzname = input(f"Spitzname [{alt.nickname if alt else 'Spot'}]: ").strip() or (
        alt.nickname if alt else "Spot"
    )
    passwort = getpass.getpass("Passwort (wird im Windows-Tresor gespeichert): ")

    # replace() statt Neubau: bei einem Neubau muss man an JEDES Feld denken,
    # und genau das ging schief — `workspace` und `active_map` fehlten, also
    # verlor jedes Passwort-Erneuern kommentarlos den Arbeitsordner und die
    # aktive Karte. Dasselbe Muster benutzt gui/app.py schon.
    neu = Config(ip=ip, username=benutzer, nickname=spitzname) if alt is None else replace(
        alt, ip=ip, username=benutzer, nickname=spitzname
    )
    save_config(neu)
    if passwort:
        save_password(benutzer, passwort)
    print("Gespeichert. Prüfen mit:  spotlab doctor")
    return 0


def _doctor():
    alles_gut = True
    for pruefung in diagnose():
        zeichen = f"{GRUEN}OK  {AUS}" if pruefung.ok else f"{ROT}FEHL{AUS}"
        print(f"{zeichen} {pruefung.name:<14} {pruefung.detail}")
        if pruefung.rat:
            print(f"     {GRAU}→ {pruefung.rat}{AUS}")
        alles_gut = alles_gut and pruefung.ok
    return 0 if alles_gut else 1


def _runs(kennung):
    wurzel = Path.cwd() / "runs"
    if kennung:
        verzeichnis = wurzel / kennung
        if not verzeichnis.is_dir():
            raise SpotlabError(f"Den Lauf {kennung} gibt es in {wurzel} nicht.")
        lauf = read_run(verzeichnis)
        print(f"Lauf     {lauf.id}")
        print(f"Ergebnis {lauf.ergebnis}" + (f" — {lauf.fehler}" if lauf.fehler else ""))
        print(f"Backend  {lauf.backend}")
        print(f"Dauer    {lauf.dauer_s:.1f} s")
        print(f"Skript   {lauf.skript or '(interaktiv)'}")
        print(f"Daten    {lauf.ereignisse_n} Ereignisse, {lauf.abtastungen_n} Abtastungen")
        print()
        for satz in read_jsonl(verzeichnis / "ereignisse.jsonl"):
            print(
                f"  {satz.get('t', 0.0):7.2f}s  {satz.get('art'):<16} {satz.get('daten')}"
            )
        return 0

    laeufe = list_runs(wurzel)
    if not laeufe:
        print(f"In {wurzel} gibt es noch keine Läufe. Starte einen mit:  spotlab run <datei>")
        return 0
    for lauf in laeufe:
        farbe = GRUEN if lauf.ergebnis == "ok" else ROT
        name = Path(lauf.skript).name if lauf.skript else ""
        print(
            f"{lauf.id}  {farbe}{lauf.ergebnis:<14}{AUS} "
            f"{lauf.dauer_s:6.1f}s  {lauf.backend:<7} {name}"
        )
    return 0


def _lease(uebernehmen):
    from bosdyn.client.lease import LeaseClient

    from spotlab.backends.real.lease import client_name, holder_of
    from spotlab.backends.real.session import _standard_robot
    from spotlab.config import load_config, load_password

    cfg = load_config()
    robot = _standard_robot(cfg)
    robot.authenticate(cfg.username, load_password(cfg.username))
    robot.time_sync.wait_for_sync()
    client = robot.ensure_client(LeaseClient.default_service_name)

    halter = holder_of(client)
    if not uebernehmen:
        print(f"Lease: {halter or 'frei'}")
        print(f"Du wärst: {client_name()}")
        return 0

    if halter:
        print(f"{ROT}Achtung:{AUS} {halter} steuert den Spot gerade.")
        print("Ein laufendes Skript dort bricht sofort ab.")
        if input("Wirklich übernehmen? [ja/nein] ").strip().lower() not in ("ja", "j"):
            print("Abgebrochen.")
            return 1
    client.take()
    print(f"Übernommen als {client_name()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
