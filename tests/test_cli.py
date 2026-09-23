import pytest

from spotlab.cli import build_parser, main


def test_alle_kommandos_sind_erreichbar():
    parser = build_parser()
    for kommando in ("login", "doctor", "new", "open", "run", "runs", "lease"):
        argumente = [kommando] + (["x"] if kommando in ("new", "open", "run") else [])
        assert parser.parse_args(argumente)


def test_new_legt_projekt_an(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "mein-projekt"]) == 0
    assert (tmp_path / "mein-projekt" / "hallo_spot.py").exists()
    assert "mein-projekt" in capsys.readouterr().out


def test_new_meldet_bestehenden_ordner_als_fehler(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["new", "p"])
    assert main(["new", "p"]) == 1
    assert "gibt es schon" in capsys.readouterr().err


def test_runs_listet_laeufe(tmp_path, monkeypatch, capsys):
    from spotlab.record.run import RunRecorder

    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    rec = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    rec.finish("ok")
    assert main(["runs"]) == 0
    assert rec.id in capsys.readouterr().out


def test_runs_zeigt_details_eines_laufs(tmp_path, monkeypatch, capsys):
    from spotlab.record.run import RunRecorder

    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    rec = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    rec.event("verbunden", ip="1.2.3.4")
    rec.finish("ok")
    assert main(["runs", rec.id]) == 0
    ausgabe = capsys.readouterr().out
    assert "verbunden" in ausgabe and "Ereignisse" in ausgabe


def test_runs_ohne_laeufe_sagt_das_freundlich(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["runs"]) == 0
    assert "noch keine" in capsys.readouterr().out.lower()


def test_run_mit_dryrun_setzt_die_variable(tmp_path, monkeypatch):
    skript = tmp_path / "x.py"
    skript.write_text(
        "import spotlab\nwith spotlab.connect() as s:\n    pass\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["run", "x.py", "--dryrun"]) == 0


def test_run_dryrun_haelt_auch_ein_backend_im_skript_vom_roboter_fern(tmp_path, monkeypatch, capfd):
    """p06: ein aus einem Beispiel kopiertes `connect(backend="real")` fuhr unter
    `spotlab run --dryrun` den echten Spot -- das Argument schlaegt SPOTLAB_BACKEND.
    Echter Kindprozess: nur so zeigt sich, ob die Schranke dort ankommt."""
    skript = tmp_path / "x.py"
    skript.write_text(
        "import spotlab\nwith spotlab.connect(backend='real') as s:\n    print('FAEHRT')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    # Ein leeres Zuhause fuer den Kindprozess: OHNE Konfiguration kann er den
    # Roboter nie erreichen, auch nicht, wenn die Schranke einmal fehlt -- dann
    # scheitert er an „Keine Konfiguration“ statt im WLAN nach dem Spot zu suchen.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["run", "x.py", "--dryrun"]) != 0
    ausgabe = capfd.readouterr()
    assert "FAEHRT" not in ausgabe.out
    assert "ohne Roboter" in ausgabe.out + ausgabe.err


def test_doctor_gibt_stufen_aus(monkeypatch, capsys):
    from spotlab.workshop.doctor import Check

    monkeypatch.setattr(
        "spotlab.cli.diagnose",
        lambda *a, **k: [
            Check("Netz", True, "antwortet"),
            Check("Anmeldung", False, "falsch", "spotlab login"),
        ],
    )
    assert main(["doctor"]) == 1
    ausgabe = capsys.readouterr().out
    assert "Netz" in ausgabe and "spotlab login" in ausgabe


def test_unbekanntes_kommando_gibt_hilfe():
    with pytest.raises(SystemExit):
        main(["quatsch"])


def test_gui_kommando_existiert():
    assert build_parser().parse_args(["gui"])


def test_gui_ohne_pyside_nennt_den_befehl(monkeypatch, capsys):
    import builtins

    echt = builtins.__import__

    def ohne_pyside(name, *args, **kw):
        if name.startswith("spotlab.gui") or name.startswith("PySide6"):
            raise ImportError("No module named 'PySide6'")
        return echt(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", ohne_pyside)
    assert main(["gui"]) == 1
    assert "pip install" in capsys.readouterr().err


def test_maps_kommando_existiert():
    assert build_parser().parse_args(["maps"])


def test_record_map_braucht_einen_namen():
    assert build_parser().parse_args(["record-map", "turnhalle"])


def test_maps_ohne_arbeitsordner_sagt_das(monkeypatch, capsys, tmp_path):
    from spotlab.config import Config, Limits, save_config

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits()), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    assert main(["maps"]) == 1
    assert "Arbeitsordner" in capsys.readouterr().err


def test_maps_listet_die_karten(monkeypatch, capsys, tmp_path):
    from bosdyn.api.graph_nav import map_pb2

    from spotlab.config import Config, Limits, save_config
    from spotlab.maps.store import karten_wurzel, speichere_metadaten

    graph = map_pb2.Graph()
    graph.waypoints.add().id = "wp0"
    ordner = karten_wurzel(tmp_path) / "turnhalle"
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    speichere_metadaten(ordner, "turnhalle", "SN-1", graph)

    pfad = tmp_path / "config.toml"
    save_config(
        Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path)), pfad
    )
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    assert main(["maps"]) == 0
    assert "turnhalle" in capsys.readouterr().out


def test_maps_markiert_die_aktive_karte(monkeypatch, capsys, tmp_path):
    from bosdyn.api.graph_nav import map_pb2

    from spotlab.config import Config, Limits, save_config
    from spotlab.maps.store import karten_wurzel, speichere_metadaten

    graph = map_pb2.Graph()
    graph.waypoints.add().id = "wp0"
    ordner = karten_wurzel(tmp_path) / "turnhalle"
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    speichere_metadaten(ordner, "turnhalle", "SN-1", graph)

    pfad = tmp_path / "config.toml"
    save_config(
        Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path),
               active_map="turnhalle"),
        pfad,
    )
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    main(["maps"])
    ausgabe = capsys.readouterr().out
    assert "* turnhalle" in ausgabe
    assert "load_map()" in ausgabe


def test_login_behaelt_arbeitsordner_und_karte(tmp_path, monkeypatch):
    """S2.3: Passwort erneuern verlor kommentarlos Arbeitsordner und aktive
    Karte -- beide werden in _login() einfach nicht mitgeschrieben."""
    from spotlab.config import Config, Limits, load_config, save_config

    pfad = tmp_path / "config.toml"
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    save_config(
        Config(ip="1.2.3.4", username="u", nickname="Spot", limits=Limits(0.25, 0.4),
               workspace=str(tmp_path / "werkstatt"), active_map="halle"),
        pfad,
    )
    eingaben = iter(["", "", ""])
    monkeypatch.setattr("builtins.input", lambda *a: next(eingaben))
    monkeypatch.setattr("getpass.getpass", lambda *a: "")

    from spotlab.cli import _login

    _login()
    neu = load_config(pfad)
    assert neu.workspace == str(tmp_path / "werkstatt")
    assert neu.active_map == "halle"
    assert neu.limits.max_speed == 0.25


def _login_mit_enter(monkeypatch):
    """`spotlab login`, bei jeder Frage Enter -- die Vorgaben bleiben."""
    monkeypatch.setattr("builtins.input", lambda *a: "")
    monkeypatch.setattr("getpass.getpass", lambda *a: "")
    from spotlab.cli import _login

    return _login()


VERSTELLT = (
    '[robot]\nip = "192.168.80.3"\nusername = "lehrer"\nnickname = "Schulspot"\n'
    '[limits]\nmax_speed = 0.3\nmax_turn_rate = 0.5\ntreppen = "aus"\n'
    '[defaults]\nbackend = "Mujoco"\n'
    '[gui]\nworkspace = "D:/spotProjects"\n[maps]\nactive = "flur"\n'
    '[uebungsraum]\nraum = "moebliert"\nstart = "1,1,0"\n'
)


def test_login_nach_einem_tippfehler_behaelt_die_sicherheitswerte(tmp_path, monkeypatch, capsys):
    """p14: EIN Tippfehler (`backend = "Mujoco"`) machte die Datei zu
    ConfigBroken, die Meldung schickte zu `spotlab login` -- und login baute
    alles neu: Treppen wieder „auto“, Tempo 0.6 statt 0.3, Arbeitsordner,
    Karte und Raum weg. `treppen` ist ein SICHERHEITSWERT (CLAUDE.md)."""
    from spotlab.config import load_config

    pfad = tmp_path / "config.toml"
    pfad.write_text(VERSTELLT, encoding="utf-8")
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    assert _login_mit_enter(monkeypatch) == 0
    neu = load_config(pfad)
    assert neu.limits.treppen == "aus"
    assert neu.limits.max_speed == 0.3 and neu.limits.max_turn_rate == 0.5
    assert (neu.ip, neu.username, neu.nickname) == ("192.168.80.3", "lehrer", "Schulspot")
    assert neu.workspace == "D:/spotProjects" and neu.active_map == "flur"
    assert neu.raum == "moebliert" and neu.raum_start == "1,1,0"
    assert neu.default_backend == "mujoco"                   # der Tippfehler, ersetzt ...
    assert "Mujoco" in capsys.readouterr().out               # ... und gesagt


@pytest.mark.parametrize("kaputt", [
    VERSTELLT.replace('treppen = "aus"', 'treppen = "vielleicht"'),
    VERSTELLT.replace("max_speed = 0.3", "max_speed = -0.3"),
    VERSTELLT.replace("[limits]", "[limits"),                 # gar nicht lesbar
], ids=["treppen", "tempo_negativ", "unlesbar"])
def test_login_setzt_einen_kaputten_sicherheitswert_nicht_still_zurueck(tmp_path, monkeypatch, kaputt):
    """Was login nicht sicher uebernehmen kann, lehnt es ab -- die Datei bleibt,
    wie sie ist, und die Meldung sagt, welche Zeile zu korrigieren ist."""
    from spotlab.errors import ConfigBroken

    pfad = tmp_path / "config.toml"
    pfad.write_text(kaputt, encoding="utf-8")
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    with pytest.raises(ConfigBroken) as fehler:
        _login_mit_enter(monkeypatch)
    assert "spotlab login" in str(fehler.value)
    assert pfad.read_text(encoding="utf-8") == kaputt


# ================ S4.5 auch die Wege am connect() vorbei sprechen deutsch


def test_eine_sdk_ausnahme_wird_uebersetzt_statt_zu_stuerzen(monkeypatch, capsys):
    """`spotlab lease` baut die Sitzung selbst auf.

    Ohne Uebersetzung sah ein Schueler, der nicht im WLAN des Spot war, eine
    Python-Rueckverfolgung mit `UnableToConnectToRobotError` — statt der Zeile,
    die ihm sagt, was zu tun ist.
    """
    from bosdyn.client.exceptions import UnableToConnectToRobotError

    from spotlab import cli

    def wirf(args):
        raise UnableToConnectToRobotError(None)

    monkeypatch.setattr(cli, "_fuehre_aus", wirf)
    assert cli.main(["lease"]) == 1
    assert "WLAN" in capsys.readouterr().err


def test_ein_programmfehler_bleibt_sichtbar(monkeypatch):
    """Die Gegenprobe: was translate() nicht kennt, wird NICHT verschluckt.

    Ein KeyError in spotlab freundlich zu formulieren hiesse, ihn zu verstecken.
    """
    from spotlab import cli

    def wirf(args):
        raise KeyError("ein Programmfehler")

    monkeypatch.setattr(cli, "_fuehre_aus", wirf)
    with pytest.raises(KeyError):
        cli.main(["runs"])


def test_neues_projekt_bringt_ein_uebungsprogramm(tmp_path):
    """Wer `spotlab new` macht, soll etwas haben, das ohne Roboter laeuft."""
    from spotlab.workshop.project import create_project

    ordner = create_project("probe", wurzel=tmp_path)
    beispiel = ordner / "uebungsraum.py"
    assert beispiel.is_file()
    quelle = beispiel.read_text(encoding="utf-8")
    assert 'backend="sim"' in quelle
    assert "spot.tags()" in quelle
