"""Konfiguration in ~/.spotlab/config.toml, Passwort in der Anmeldeinformationsverwaltung.

Kein Passwort im Klartext auf zwanzig Schullaptops: das Passwort geht über
keyring in den Windows-Tresor, die Konfigurationsdatei enthält es nie.
"""

import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import keyring

from spotlab.errors import ConfigBroken, ConfigMissing

CONFIG_PATH = Path.home() / ".spotlab" / "config.toml"
KEYRING_SERVICE = "spotlab"
BACKENDS = ("real", "dryrun", "sim")
ENV_PASSWORD = "BOSDYN_CLIENT_PASSWORD"
ENV_USERNAME = "BOSDYN_CLIENT_USERNAME"


@dataclass(frozen=True)
class Limits:
    max_speed: float = 0.6  # m/s
    max_turn_rate: float = 0.8  # rad/s


@dataclass(frozen=True)
class Config:
    ip: str
    username: str
    nickname: str = "Spot"
    limits: Limits = field(default_factory=Limits)
    editor_command: str = "code"
    default_backend: str = "real"
    workspace: str = ""  # Arbeitsordner der GUI; leer = noch nicht gewählt
    active_map: str = ""  # in der GUI gewählte Karte; leer = keine


def _toml_string(wert):
    """Minimaler TOML-Basic-String — vermeidet eine Schreibabhängigkeit."""
    gesichert = str(wert).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{gesichert}"'


def save_config(cfg, path=None):
    # Pfad erst zur Aufrufzeit auflösen: als Vorgabewert wäre CONFIG_PATH beim
    # Import gebunden und in Tests nicht mehr umzubiegen.
    path = Path(path) if path else CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# von spotlab geschrieben — das Passwort steht NICHT hier, sondern im Windows-Tresor\n"
        "[robot]\n"
        f"ip = {_toml_string(cfg.ip)}\n"
        f"username = {_toml_string(cfg.username)}\n"
        f"nickname = {_toml_string(cfg.nickname)}\n"
        "\n[limits]\n"
        f"max_speed = {float(cfg.limits.max_speed)}\n"
        f"max_turn_rate = {float(cfg.limits.max_turn_rate)}\n"
        "\n[editor]\n"
        f"command = {_toml_string(cfg.editor_command)}\n"
        "\n[defaults]\n"
        f"backend = {_toml_string(cfg.default_backend)}\n"
        "\n[gui]\n"
        f"workspace = {_toml_string(cfg.workspace)}\n"
        "\n[maps]\n"
        f"active = {_toml_string(cfg.active_map)}\n"
    )
    path.write_text(text, encoding="utf-8")


def _grenze(roh, schluessel, vorgabe, pfad):
    """Ein Sicherheitswert. Muss endlich und echt positiv sein.

    Warum so streng: `max_speed = inf` macht den Deckel wirkungslos, und ein
    NEGATIVER Wert ist schlimmer als gar keiner — `motion.clamp()` rechnet dann
    `max(0.8, min(-0.8, wz))` und liefert für ein kommandiertes wz = 0 eine
    Dauerdrehung. Ein Tippfehler in dieser Datei darf den Roboter nicht bewegen.
    """
    wert = roh.get(schluessel, vorgabe)
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        raise ConfigBroken(
            f"In {pfad} ist `{schluessel} = {wert!r}` keine Zahl. Korrigieren oder "
            f"die Zeile löschen — dann gilt die Vorgabe {vorgabe}."
        ) from None
    if not math.isfinite(zahl) or zahl <= 0.0:
        raise ConfigBroken(
            f"In {pfad} ist `{schluessel} = {wert}` unbrauchbar. Der Wert ist eine "
            f"Sicherheitsgrenze und muss eine endliche Zahl über 0 sein "
            f"(Vorgabe: {vorgabe})."
        )
    return zahl


def load_config(path=None):
    path = Path(path) if path else CONFIG_PATH
    if not path.exists():
        raise ConfigMissing(
            f"Keine Konfiguration unter {path}. Einmalig einrichten mit `spotlab login`."
        )
    try:
        with path.open("rb") as datei:
            roh = tomllib.load(datei)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as fehler:
        # Ohne diesen Fang sperrt eine halb geschriebene Datei die GUI, das CLI
        # und den Reparaturweg `spotlab login` gleichzeitig — mit rohem Traceback.
        raise ConfigBroken(
            f"{path} ist nicht lesbar ({fehler.__class__.__name__}). Datei "
            f"korrigieren oder löschen und neu einrichten mit `spotlab login`."
        ) from fehler
    robot = roh.get("robot", {})
    if "ip" not in robot or "username" not in robot:
        raise ConfigMissing(
            f"In {path} fehlen IP oder Benutzername. Neu einrichten mit `spotlab login`."
        )
    limits = roh.get("limits", {})
    backend = roh.get("defaults", {}).get("backend", "real")
    if backend not in BACKENDS:
        raise ConfigBroken(
            f"In {path} ist `backend = {backend!r}` unbekannt. Erlaubt: "
            + ", ".join(sorted(BACKENDS))
            + "."
        )
    return Config(
        ip=robot["ip"],
        username=robot["username"],
        nickname=robot.get("nickname", "Spot"),
        limits=Limits(
            max_speed=_grenze(limits, "max_speed", Limits.max_speed, path),
            max_turn_rate=_grenze(limits, "max_turn_rate", Limits.max_turn_rate, path),
        ),
        editor_command=roh.get("editor", {}).get("command", "code"),
        default_backend=backend,
        workspace=roh.get("gui", {}).get("workspace", ""),
        active_map=roh.get("maps", {}).get("active", ""),
    )


def save_password(username, password):
    keyring.set_password(KEYRING_SERVICE, username, password)


def load_password(username):
    gespeichert = keyring.get_password(KEYRING_SERVICE, username)
    if gespeichert:
        return gespeichert
    aus_umgebung = os.environ.get(ENV_PASSWORD)
    if aus_umgebung:
        return aus_umgebung
    raise ConfigMissing(
        f"Für '{username}' ist kein Passwort hinterlegt. Einmalig setzen mit `spotlab login`."
    )
