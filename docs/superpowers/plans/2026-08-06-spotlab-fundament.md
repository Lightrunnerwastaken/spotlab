# spotlab Fundament — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein installierbares Python-Paket `spotlab`, mit dem Schülerinnen und Schüler den echten Boston Dynamics Spot programmieren — Verbindung, Lease und Not-Aus verwaltet, jeder Lauf aufgezeichnet, alles über Kommandozeile bedienbar.

**Architecture:** Fünf Schichten mit einer Abhängigkeitsrichtung: `cli → workshop → api → backends → bosdyn`, dazu die querliegenden, abhängigkeitsfreien Module `config`, `errors`, `record`. Kommandos werden ausschliesslich mit `RobotCommandBuilder` gebaut. Das `dryrun`-Backend ist Testdouble und zugleich ausgeliefertes Feature.

**Tech Stack:** Python 3.13, `bosdyn-client`/`bosdyn-api` 5.0.1.2, `keyring` (WinVaultKeyring), `numpy`, `Pillow`, `pytest`, `argparse` (stdlib), `tomllib` (stdlib).

## Global Constraints

- Python ≥ 3.11, entwickelt und geprüft auf 3.13.9.
- `bosdyn-client` und `bosdyn-api` exakt 5.0.1.2 (installiert und verifiziert).
- **Python-Bezeichner englisch, alle Meldungen an Nutzer deutsch.** Ausnahmeklassen englisch benannt, Meldungstext deutsch.
- **Datei- und Feldnamen der Aufzeichnung deutsch** (`lauf.json`, `ereignisse.jsonl`, `zustand.jsonl`, Schlüssel `t`/`art`/`daten`). Eingebettete SDK-Nutzlasten behalten englische Feldnamen.
- Kommandos ausschliesslich über `bosdyn.client.robot_command.RobotCommandBuilder`. Keine parallele Eigen-API.
- Keine zusätzlichen Laufzeitabhängigkeiten ausser den im Tech Stack genannten.
- Testgetrieben: erst der fehlschlagende Test, dann die Implementierung. Commit pro Task.
- Jeder Test läuft ohne Roboter und ohne Netz.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `src/spotlab/__init__.py` | `connect()`, `__version__`, Re-Exports |
| `src/spotlab/config.py` | `config.toml` lesen/schreiben, Passwort über keyring |
| `src/spotlab/errors/__init__.py` | Ausnahmehierarchie mit deutschen Meldungen |
| `src/spotlab/errors/translate.py` | bosdyn-Ausnahme → `SpotlabError` |
| `src/spotlab/backends/base.py` | `Capability`, `Feedback`, `SafetyStatus`, `SpotBackend`-Protokoll |
| `src/spotlab/backends/dryrun.py` | Trockenlauf-Backend |
| `src/spotlab/backends/real/__init__.py` | `RealSpot` |
| `src/spotlab/backends/real/session.py` | Aufbau-/Abbausequenz |
| `src/spotlab/backends/real/estop.py` | Koexistenz-Registrierung + Keepalive |
| `src/spotlab/backends/real/lease.py` | Erwerb, Keepalive, Verlusterkennung |
| `src/spotlab/backends/real/power.py` | An/Aus, sicheres Hinsetzen |
| `src/spotlab/backends/real/feedback.py` | Rückmeldungs-Protobuf → `Feedback` |
| `src/spotlab/api/spot.py` | `Spot`-Fassade |
| `src/spotlab/api/posture.py` | `stand`, `sit` |
| `src/spotlab/api/motion.py` | `move`, `walk`, `stop` |
| `src/spotlab/api/perception.py` | `cameras`, `camera`, `Image` |
| `src/spotlab/api/state.py` | `State`-Schnappschuss |
| `src/spotlab/record/events.py` | Ereignistypen |
| `src/spotlab/record/run.py` | `RunRecorder` |
| `src/spotlab/record/read.py` | Leser, absturztolerant |
| `src/spotlab/record/sampler.py` | 10-Hz-Hintergrundabtaster |
| `src/spotlab/workshop/project.py` | `new` |
| `src/spotlab/workshop/editor.py` | `open` |
| `src/spotlab/workshop/launcher.py` | `run` |
| `src/spotlab/workshop/doctor.py` | `doctor` |
| `src/spotlab/workshop/templates/hallo_spot.py` | Projektvorlage |
| `src/spotlab/cli.py` | Argumente → Aufrufe |

---

## Task 1: Projektgerüst

**Files:**
- Create: `pyproject.toml`, `src/spotlab/__init__.py`, `tests/conftest.py`, `tests/test_paket.py`

**Interfaces:**
- Consumes: nichts
- Produces: `spotlab.__version__: str`; installierbares Paket; `pytest` läuft

- [ ] **Step 1: Test schreiben** — `tests/test_paket.py`

```python
def test_version_ist_gesetzt():
    import spotlab
    assert spotlab.__version__ == "0.1.0"
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_paket.py -v`, erwartet `ModuleNotFoundError: spotlab`

- [ ] **Step 3: `pyproject.toml` schreiben**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "spotlab"
version = "0.1.0"
description = "Spot programmieren an der Kantonsschule"
requires-python = ">=3.11"
dependencies = [
    "bosdyn-client==5.0.1.2",
    "bosdyn-api==5.0.1.2",
    "keyring>=24",
    "numpy>=1.26",
    "Pillow>=10",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
spotlab = "spotlab.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"spotlab.workshop" = ["templates/*.py"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: `src/spotlab/__init__.py`**

```python
"""spotlab — den Spot programmieren, ohne vorher SDK-Betriebsmechanik zu lernen."""

__version__ = "0.1.0"
```

- [ ] **Step 5: `tests/conftest.py`**

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

- [ ] **Step 6: Test läuft** — `pytest -v`, erwartet PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src tests && git commit -m "chore: Projektgerüst mit pytest"
```

---

## Task 2: Ausnahmehierarchie und Fehlerübersetzung

**Files:**
- Create: `src/spotlab/errors/__init__.py`, `src/spotlab/errors/translate.py`, `tests/test_errors.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `SpotlabError(Exception)` — Basis, `str(e)` ist deutscher Klartext
  - `NotReachable`, `BadCredentials`, `TimeSyncFailed`, `EstopEngaged`, `BatteryEmpty`, `CommandRejected`, `NotPowered`, `UnsupportedCapability`, `ConfigMissing`
  - `LeaseBusy(SpotlabError)` mit Attribut `holder: str | None`
  - `LeaseLost(SpotlabError)`
  - `translate(exc: Exception, *, ip: str | None = None) -> SpotlabError | None`

- [ ] **Step 1: Test schreiben** — `tests/test_errors.py`

```python
import pytest
from bosdyn.client.auth import InvalidLoginError
from bosdyn.client.exceptions import UnableToConnectToRobotError
from bosdyn.client.lease import ResourceAlreadyClaimedError

from spotlab.errors import BadCredentials, LeaseBusy, NotReachable, SpotlabError, translate


def test_netzfehler_nennt_die_ip():
    fehler = translate(UnableToConnectToRobotError("weg"), ip="192.168.80.3")
    assert isinstance(fehler, NotReachable)
    assert "192.168.80.3" in str(fehler)
    assert "WLAN" in str(fehler)


def test_login_fehler_verweist_auf_login_kommando():
    fehler = translate(InvalidLoginError(response=None))
    assert isinstance(fehler, BadCredentials)
    assert "spotlab login" in str(fehler)


def test_lease_belegt_nennt_den_halter():
    fehler = translate(ResourceAlreadyClaimedError(response=None), ip=None)
    assert isinstance(fehler, LeaseBusy)
    assert "spotlab lease --take" in str(fehler)


def test_originalausnahme_bleibt_als_cause():
    ursprung = UnableToConnectToRobotError("weg")
    fehler = translate(ursprung, ip="1.2.3.4")
    assert fehler.__cause__ is ursprung


def test_unbekannte_ausnahme_wird_nicht_uebersetzt():
    assert translate(ValueError("irgendwas")) is None


def test_alle_spotlab_fehler_haben_deutschen_text():
    assert issubclass(BadCredentials, SpotlabError)
    with pytest.raises(SpotlabError):
        raise BadCredentials("Benutzername oder Passwort stimmt nicht.")
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_errors.py -v`, erwartet `ModuleNotFoundError: spotlab.errors`

- [ ] **Step 3: `errors/__init__.py` implementieren**

```python
"""Ausnahmen von spotlab. Klassennamen englisch, Meldungen deutsch (Vorgabe G6)."""


class SpotlabError(Exception):
    """Basis aller spotlab-Fehler. Die Meldung ist Klartext für Schüler."""


class ConfigMissing(SpotlabError):
    """Keine Konfiguration hinterlegt."""


class NotReachable(SpotlabError):
    """Der Roboter ist im Netz nicht erreichbar."""


class BadCredentials(SpotlabError):
    """Benutzername oder Passwort falsch."""


class TimeSyncFailed(SpotlabError):
    """Zeitsynchronisierung mit dem Roboter fehlgeschlagen."""


class LeaseBusy(SpotlabError):
    """Jemand anders hält die Kontrolle."""

    def __init__(self, message, holder=None):
        super().__init__(message)
        self.holder = holder


class LeaseLost(SpotlabError):
    """Die Kontrolle wurde während des Laufs entzogen."""


class EstopEngaged(SpotlabError):
    """Der Not-Aus ist ausgelöst."""


class BatteryEmpty(SpotlabError):
    """Der Akku reicht nicht mehr."""


class CommandRejected(SpotlabError):
    """Der Roboter hat ein Kommando abgelehnt."""


class NotPowered(SpotlabError):
    """Die Motoren sind aus."""


class UnsupportedCapability(SpotlabError):
    """Das aktive Backend kann das nicht."""


from spotlab.errors.translate import translate  # noqa: E402  (zyklusfrei, translate importiert nur Namen von oben)

__all__ = [
    "SpotlabError", "ConfigMissing", "NotReachable", "BadCredentials",
    "TimeSyncFailed", "LeaseBusy", "LeaseLost", "EstopEngaged", "BatteryEmpty",
    "CommandRejected", "NotPowered", "UnsupportedCapability", "translate",
]
```

- [ ] **Step 4: `errors/translate.py` implementieren**

```python
"""bosdyn-Ausnahmen in deutschen Klartext übersetzen.

Jede übersetzte Ausnahme behält die originale als __cause__: für die Schüler
Klartext, für die Entwicklung die volle Wahrheit.
"""

from bosdyn.client.auth import InvalidLoginError, TemporarilyLockedOutError
from bosdyn.client.exceptions import (
    LeaseUseError,
    ProxyConnectionError,
    RetryableUnavailableError,
    RpcError,
    TimedOutError,
    UnableToConnectToRobotError,
    UnauthenticatedError,
    UnknownDnsNameError,
)
from bosdyn.client.lease import DisplacedLeaseError, ResourceAlreadyClaimedError


def _mit_ursache(fehler, ursprung):
    fehler.__cause__ = ursprung
    return fehler


def translate(exc, *, ip=None):
    """bosdyn-Ausnahme → SpotlabError, oder None wenn nicht übersetzbar."""
    from spotlab import errors as E

    ziel = ip or "dem Roboter"

    if isinstance(exc, (UnableToConnectToRobotError, UnknownDnsNameError,
                        ProxyConnectionError, RetryableUnavailableError, TimedOutError)):
        return _mit_ursache(E.NotReachable(
            f"Ich erreiche {ziel} nicht. Bist du im WLAN des Spot?"), exc)

    if isinstance(exc, InvalidLoginError):
        return _mit_ursache(E.BadCredentials(
            "Benutzername oder Passwort stimmt nicht — neu hinterlegen mit `spotlab login`."), exc)

    if isinstance(exc, TemporarilyLockedOutError):
        return _mit_ursache(E.BadCredentials(
            "Zu viele Fehlversuche. Der Roboter sperrt den Login kurz — in einer "
            "Minute erneut versuchen, danach `spotlab login`."), exc)

    if isinstance(exc, UnauthenticatedError):
        return _mit_ursache(E.BadCredentials(
            "Nicht angemeldet. Zugangsdaten hinterlegen mit `spotlab login`."), exc)

    if isinstance(exc, ResourceAlreadyClaimedError):
        halter = _halter_aus(exc)
        wer = halter or "Jemand anders"
        return _mit_ursache(E.LeaseBusy(
            f"{wer} steuert den Spot gerade. Mit `spotlab lease --take` übernehmen "
            f"— aber erst absprechen.", holder=halter), exc)

    if isinstance(exc, (DisplacedLeaseError, LeaseUseError)):
        return _mit_ursache(E.LeaseLost(
            "Kontrolle verloren — jemand anders hat übernommen. Lauf abgebrochen."), exc)

    if isinstance(exc, RpcError):
        return _mit_ursache(E.NotReachable(
            f"Die Verbindung zu {ziel} ist abgebrochen."), exc)

    return None


def _halter_aus(exc):
    """Halternamen aus der Lease-Antwort ziehen, wenn vorhanden."""
    antwort = getattr(exc, "response", None)
    besitzer = getattr(antwort, "lease_owner", None)
    if besitzer is None:
        return None
    name = besitzer.client_name or besitzer.user_name
    return name or None
```

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_errors.py -v`, erwartet 6 PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/errors tests/test_errors.py && git commit -m "feat(errors): Ausnahmehierarchie und bosdyn-Fehlerübersetzung"
```

---

## Task 3: Konfiguration und Zugangsdaten

**Files:**
- Create: `src/spotlab/config.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `spotlab.errors.ConfigMissing`
- Produces:
  - `Limits(max_speed: float = 0.6, max_turn_rate: float = 0.8)` — frozen dataclass
  - `Config(ip, username, nickname, limits, editor_command="code", default_backend="real")` — frozen dataclass
  - `CONFIG_PATH: Path` (`~/.spotlab/config.toml`)
  - `load_config(path=CONFIG_PATH) -> Config` (wirft `ConfigMissing`)
  - `save_config(cfg, path=CONFIG_PATH) -> None`
  - `save_password(username, password) -> None`
  - `load_password(username) -> str` (keyring, dann `BOSDYN_CLIENT_PASSWORD`)
  - `KEYRING_SERVICE = "spotlab"`

- [ ] **Step 1: Test schreiben** — `tests/test_config.py`

```python
import pytest

from spotlab.config import Config, Limits, load_config, load_password, save_config
from spotlab.errors import ConfigMissing


def test_speichern_und_lesen_ist_verlustfrei(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="192.168.80.3", username="student", nickname="Spot der Kanti",
                 limits=Limits(max_speed=0.4, max_turn_rate=0.5),
                 editor_command="code", default_backend="dryrun")
    save_config(cfg, pfad)
    assert load_config(pfad) == cfg


def test_fehlende_datei_meldet_klartext(tmp_path):
    with pytest.raises(ConfigMissing) as info:
        load_config(tmp_path / "gibtsnicht.toml")
    assert "spotlab login" in str(info.value)


def test_vorgabewerte_wenn_abschnitte_fehlen(tmp_path):
    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot]\nip = "10.0.0.1"\nusername = "u"\n', encoding="utf-8")
    cfg = load_config(pfad)
    assert cfg.limits == Limits()
    assert cfg.editor_command == "code"
    assert cfg.default_backend == "real"
    assert cfg.nickname == "Spot"


def test_passwort_faellt_auf_umgebungsvariable_zurueck(monkeypatch):
    monkeypatch.setattr("spotlab.config.keyring.get_password", lambda *_: None)
    monkeypatch.setenv("BOSDYN_CLIENT_PASSWORD", "geheim")
    assert load_password("student") == "geheim"


def test_ohne_passwort_klare_meldung(monkeypatch):
    monkeypatch.setattr("spotlab.config.keyring.get_password", lambda *_: None)
    monkeypatch.delenv("BOSDYN_CLIENT_PASSWORD", raising=False)
    with pytest.raises(ConfigMissing) as info:
        load_password("student")
    assert "spotlab login" in str(info.value)


def test_umlaute_im_spitznamen_ueberleben(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="1.2.3.4", username="u", nickname='Spot "Grüezi" \\ Kanti',
                 limits=Limits())
    save_config(cfg, pfad)
    assert load_config(pfad).nickname == 'Spot "Grüezi" \\ Kanti'
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_config.py -v`, erwartet `ModuleNotFoundError: spotlab.config`

- [ ] **Step 3: `config.py` implementieren**

```python
"""Konfiguration in ~/.spotlab/config.toml, Passwort in der Anmeldeinformationsverwaltung.

Kein Passwort im Klartext auf zwanzig Schullaptops: das Passwort geht über
keyring in den Windows-Tresor, die Konfigurationsdatei enthält es nie.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import keyring

from spotlab.errors import ConfigMissing

CONFIG_PATH = Path.home() / ".spotlab" / "config.toml"
KEYRING_SERVICE = "spotlab"
ENV_PASSWORD = "BOSDYN_CLIENT_PASSWORD"
ENV_USERNAME = "BOSDYN_CLIENT_USERNAME"


@dataclass(frozen=True)
class Limits:
    max_speed: float = 0.6          # m/s
    max_turn_rate: float = 0.8      # rad/s


@dataclass(frozen=True)
class Config:
    ip: str
    username: str
    nickname: str = "Spot"
    limits: Limits = field(default_factory=Limits)
    editor_command: str = "code"
    default_backend: str = "real"


def _toml_string(wert):
    """Minimaler TOML-Basic-String — vermeidet eine Schreibabhängigkeit."""
    gesichert = str(wert).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{gesichert}"'


def save_config(cfg, path=CONFIG_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# von spotlab geschrieben — Passwort steht NICHT hier, sondern im Windows-Tresor\n"
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
    )
    path.write_text(text, encoding="utf-8")


def load_config(path=CONFIG_PATH):
    path = Path(path)
    if not path.exists():
        raise ConfigMissing(
            f"Keine Konfiguration unter {path}. Einmalig einrichten mit `spotlab login`.")
    with path.open("rb") as datei:
        roh = tomllib.load(datei)
    robot = roh.get("robot", {})
    if "ip" not in robot or "username" not in robot:
        raise ConfigMissing(
            f"In {path} fehlen IP oder Benutzername. Neu einrichten mit `spotlab login`.")
    limits = roh.get("limits", {})
    return Config(
        ip=robot["ip"],
        username=robot["username"],
        nickname=robot.get("nickname", "Spot"),
        limits=Limits(
            max_speed=float(limits.get("max_speed", Limits.max_speed)),
            max_turn_rate=float(limits.get("max_turn_rate", Limits.max_turn_rate)),
        ),
        editor_command=roh.get("editor", {}).get("command", "code"),
        default_backend=roh.get("defaults", {}).get("backend", "real"),
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
        f"Für '{username}' ist kein Passwort hinterlegt. Einmalig setzen mit `spotlab login`.")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_config.py -v`, erwartet 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/config.py tests/test_config.py && git commit -m "feat(config): config.toml und Passwort im Windows-Tresor"
```

---

## Task 4: Ereignisse und Lauf-Schreiber

**Files:**
- Create: `src/spotlab/record/__init__.py`, `src/spotlab/record/events.py`, `src/spotlab/record/run.py`, `tests/test_record_run.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `ARTEN: frozenset[str]` = `{"verbunden","power_on","power_off","kommando","rückmeldung","bild","fehler","lease_verloren","lease_übernommen","ende"}`
  - `ERGEBNISSE: frozenset[str]` = `{"ok","fehler","abgebrochen","lease_verloren","läuft"}`
  - `run_id(script_path: Path | None, now: datetime) -> str` → `YYYYMMDDTHHMMSSZ_<8 hex>`
  - `RunRecorder(runs_dir: Path, script_path: Path | None, backend: str, nickname: str = "", user: str = "")`
    - `.dir -> Path`, `.id -> str`
    - `.event(art: str, **daten) -> None`
    - `.sample(daten: dict) -> None`
    - `.image(name: str, roh: bytes, meta: dict) -> Path`
    - `.finish(ergebnis: str, fehler: str | None = None) -> None`
    - `.set_robot_info(**felder) -> None`

- [ ] **Step 1: Test schreiben** — `tests/test_record_run.py`

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spotlab.record.run import RunRecorder, run_id


def test_lauf_id_hat_zeitstempel_und_skript_hash(tmp_path):
    skript = tmp_path / "hallo.py"
    skript.write_text("print('hi')", encoding="utf-8")
    kennung = run_id(skript, datetime(2026, 8, 6, 14, 3, 27, tzinfo=UTC))
    zeit, _, kurz = kennung.partition("_")
    assert zeit == "20260806T140327Z"
    assert len(kurz) == 8 and all(c in "0123456789abcdef" for c in kurz)


def test_gleiches_skript_gleicher_hash(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1", encoding="utf-8")
    b.write_text("x = 1", encoding="utf-8")
    jetzt = datetime(2026, 8, 6, tzinfo=UTC)
    assert run_id(a, jetzt).split("_")[1] == run_id(b, jetzt).split("_")[1]


def test_ereignisse_landen_als_jsonl(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("verbunden", ip="1.2.3.4")
    rec.event("kommando", name="stand")
    rec.finish("ok")

    zeilen = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8").strip().split("\n")
    arten = [json.loads(z)["art"] for z in zeilen]
    assert arten == ["verbunden", "kommando", "ende"]
    assert json.loads(zeilen[0])["daten"] == {"ip": "1.2.3.4"}
    assert json.loads(zeilen[0])["t"] >= 0.0


def test_unbekannte_ereignisart_wird_abgelehnt(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    with pytest.raises(ValueError, match="Unbekannte Ereignisart"):
        rec.event("quatsch")


def test_lauf_json_traegt_ergebnis_und_dauer(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun", nickname="Spot der Kanti")
    rec.finish("fehler", "Akku leer")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["ergebnis"] == "fehler"
    assert daten["fehler"] == "Akku leer"
    assert daten["backend"] == "dryrun"
    assert daten["nickname"] == "Spot der Kanti"
    assert daten["dauer_s"] >= 0.0


def test_lauf_json_existiert_schon_waehrend_des_laufs(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["ergebnis"] == "läuft"


def test_skript_hash_und_pfad_stehen_in_lauf_json(tmp_path):
    skript = tmp_path / "hallo.py"
    skript.write_text("print('hi')", encoding="utf-8")
    rec = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    rec.finish("ok")
    daten = json.loads((rec.dir / "lauf.json").read_text(encoding="utf-8"))
    assert daten["skript"] == str(skript)
    assert len(daten["skript_sha256"]) == 64


def test_abtastungen_landen_in_zustand_jsonl(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 91.0})
    rec.sample({"battery": 90.5})
    rec.finish("ok")
    zeilen = (rec.dir / "zustand.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(zeilen) == 2
    assert json.loads(zeilen[1])["daten"]["battery"] == 90.5


def test_bild_wird_abgelegt_und_verzeichnet(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    ziel = rec.image("frontleft", b"\x89PNG-attrappe", {"source": "frontleft_fisheye_image"})
    rec.finish("ok")
    assert ziel.exists() and ziel.parent.name == "bilder"
    verzeichnis = json.loads((rec.dir / "bilder" / "bilder.json").read_text(encoding="utf-8"))
    assert verzeichnis[0]["source"] == "frontleft_fisheye_image"
    assert verzeichnis[0]["datei"] == ziel.name


def test_jede_zeile_wird_sofort_geschrieben(tmp_path):
    """Absturzfestigkeit: was geschrieben ist, ist auf der Platte."""
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("verbunden")
    inhalt = (rec.dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert inhalt.endswith("\n")
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_record_run.py -v`, erwartet `ModuleNotFoundError`

- [ ] **Step 3: `record/events.py` implementieren**

```python
"""Erlaubte Ereignis- und Ergebnisarten der Aufzeichnung.

Die Schlüssel sind bewusst deutsch (t/art/daten), die eingebetteten
SDK-Nutzlasten behalten ihre englischen Feldnamen.
"""

ARTEN = frozenset({
    "verbunden",
    "power_on",
    "power_off",
    "kommando",
    "rückmeldung",
    "bild",
    "fehler",
    "lease_verloren",
    "lease_übernommen",
    "ende",
})

ERGEBNISSE = frozenset({"läuft", "ok", "fehler", "abgebrochen", "lease_verloren"})
```

- [ ] **Step 4: `record/run.py` implementieren**

```python
"""Ein Lauf = ein Verzeichnis mit Metadaten, Ereignisstrom, Zustandsabtastung, Bildern.

jsonl statt Datenbank: mitlesbar während der Lauf läuft, ein Absturz kostet
höchstens die letzte Zeile, ohne Werkzeug lesbar.
"""

import getpass
import hashlib
import json
import os
import platform
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from spotlab.record.events import ARTEN, ERGEBNISSE

ZEITFORMAT = "%Y%m%dT%H%M%SZ"


def _sha256(pfad):
    hasher = hashlib.sha256()
    with Path(pfad).open("rb") as datei:
        for block in iter(lambda: datei.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()


def run_id(script_path, now):
    zeit = now.astimezone(UTC).strftime(ZEITFORMAT)
    if script_path is None:
        kurz = "interakt"
    else:
        kurz = _sha256(script_path)[:8]
    return f"{zeit}_{kurz}"


class RunRecorder:
    """Schreibt einen Lauf nach runs_dir/<id>/. Threadsicher."""

    def __init__(self, runs_dir, script_path, backend, nickname="", user=None):
        self._t0 = time.monotonic()
        self._sperre = threading.Lock()
        jetzt = datetime.now(UTC)
        self.id = run_id(script_path, jetzt)
        self.dir = Path(runs_dir) / self.id
        (self.dir / "bilder").mkdir(parents=True, exist_ok=True)
        self._script_path = Path(script_path) if script_path else None
        self._bilder = []
        self._meta = {
            "id": self.id,
            "gestartet": jetzt.isoformat(),
            "dauer_s": 0.0,
            "backend": backend,
            "nickname": nickname,
            "spotlab_version": _version(),
            "benutzer": user or f"{getpass.getuser()}@{socket.gethostname()}",
            "python": platform.python_version(),
            "skript": str(self._script_path) if self._script_path else None,
            "skript_sha256": _sha256(self._script_path) if self._script_path else None,
            "ergebnis": "läuft",
            "fehler": None,
            "uebernommen": False,
        }
        self._schreibe_meta()

    # ---------------------------------------------------------------- schreiben

    def event(self, art, **daten):
        if art not in ARTEN:
            raise ValueError(f"Unbekannte Ereignisart: {art!r}")
        self._zeile("ereignisse.jsonl", {"t": self._t(), "art": art, "daten": daten})

    def sample(self, daten):
        self._zeile("zustand.jsonl", {"t": self._t(), "daten": daten})

    def image(self, name, roh, meta):
        endung = meta.get("endung", "png")
        datei = f"{len(self._bilder):04d}_{name}.{endung}"
        ziel = self.dir / "bilder" / datei
        ziel.write_bytes(roh)
        eintrag = {"t": self._t(), "datei": datei, **meta}
        eintrag.pop("endung", None)
        self._bilder.append(eintrag)
        with self._sperre:
            (self.dir / "bilder" / "bilder.json").write_text(
                json.dumps(self._bilder, ensure_ascii=False, indent=2), encoding="utf-8")
        self.event("bild", datei=datei, source=meta.get("source"))
        return ziel

    def set_robot_info(self, **felder):
        with self._sperre:
            self._meta.update(felder)
        self._schreibe_meta()

    def finish(self, ergebnis, fehler=None):
        if ergebnis not in ERGEBNISSE:
            raise ValueError(f"Unbekanntes Ergebnis: {ergebnis!r}")
        self.event("ende", ergebnis=ergebnis, fehler=fehler)
        with self._sperre:
            self._meta["ergebnis"] = ergebnis
            self._meta["fehler"] = fehler
            self._meta["dauer_s"] = round(self._t(), 3)
        self._schreibe_meta()

    # ---------------------------------------------------------------- intern

    def _t(self):
        return time.monotonic() - self._t0

    def _zeile(self, datei, satz):
        text = json.dumps(satz, ensure_ascii=False, default=str) + "\n"
        with self._sperre, (self.dir / datei).open("a", encoding="utf-8") as ziel:
            ziel.write(text)
            ziel.flush()
            os.fsync(ziel.fileno())

    def _schreibe_meta(self):
        with self._sperre:
            (self.dir / "lauf.json").write_text(
                json.dumps(self._meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _version():
    from spotlab import __version__
    return __version__
```

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_record_run.py -v`, erwartet 10 PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/record tests/test_record_run.py && git commit -m "feat(record): Lauf-Verzeichnis mit Ereignis- und Zustandsstrom"
```

---

## Task 5: Absturztoleranter Leser

**Files:**
- Create: `src/spotlab/record/read.py`, `tests/test_record_read.py`

**Interfaces:**
- Consumes: `RunRecorder` (nur im Test)
- Produces:
  - `read_jsonl(path: Path) -> list[dict]` — ignoriert eine abgeschnittene letzte Zeile
  - `RunSummary` dataclass: `id, dir, gestartet, dauer_s, backend, nickname, ergebnis, fehler, skript, benutzer, ereignisse_n, abtastungen_n`
  - `read_run(run_dir: Path) -> RunSummary`
  - `list_runs(runs_dir: Path) -> list[RunSummary]` — neueste zuerst

- [ ] **Step 1: Test schreiben** — `tests/test_record_read.py`

```python
import json

from spotlab.record.read import list_runs, read_jsonl, read_run
from spotlab.record.run import RunRecorder


def test_abgeschnittene_letzte_zeile_wird_uebersprungen(tmp_path):
    datei = tmp_path / "ereignisse.jsonl"
    datei.write_text('{"t": 0.1, "art": "verbunden", "daten": {}}\n{"t": 0.2, "art": "komm',
                     encoding="utf-8")
    saetze = read_jsonl(datei)
    assert len(saetze) == 1
    assert saetze[0]["art"] == "verbunden"


def test_fehlende_datei_ergibt_leere_liste(tmp_path):
    assert read_jsonl(tmp_path / "gibtsnicht.jsonl") == []


def test_lauf_wird_zusammengefasst(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun", nickname="Spot")
    rec.event("verbunden")
    rec.sample({"battery": 90.0})
    rec.finish("ok")

    zusammenfassung = read_run(rec.dir)
    assert zusammenfassung.ergebnis == "ok"
    assert zusammenfassung.backend == "dryrun"
    assert zusammenfassung.ereignisse_n == 2      # verbunden + ende
    assert zusammenfassung.abtastungen_n == 1


def test_abgestuerzter_lauf_bleibt_lesbar(tmp_path):
    """lauf.json steht auf 'läuft', ereignisse.jsonl endet mitten in einer Zeile."""
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.event("verbunden")
    with (rec.dir / "ereignisse.jsonl").open("a", encoding="utf-8") as datei:
        datei.write('{"t": 1.0, "art": "komm')

    zusammenfassung = read_run(rec.dir)
    assert zusammenfassung.ergebnis == "läuft"
    assert zusammenfassung.ereignisse_n == 1


def test_laeufe_kommen_neueste_zuerst(tmp_path):
    ersteres = RunRecorder(tmp_path, None, backend="dryrun")
    ersteres.finish("ok")
    (tmp_path / "20260806T999999Z_abcdef12").mkdir()
    (tmp_path / "20260806T999999Z_abcdef12" / "lauf.json").write_text(
        json.dumps({"id": "20260806T999999Z_abcdef12", "ergebnis": "ok"}), encoding="utf-8")

    ids = [z.id for z in list_runs(tmp_path)]
    assert ids[0] == "20260806T999999Z_abcdef12"


def test_leeres_runs_verzeichnis(tmp_path):
    assert list_runs(tmp_path / "gibtsnicht") == []
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_record_read.py -v`

- [ ] **Step 3: `record/read.py` implementieren**

```python
"""Läufe lesen — absturztolerant.

Ein Lauf, dessen Prozess getötet wurde, hat eine halbe letzte jsonl-Zeile und
ein lauf.json, das noch auf "läuft" steht. Beides muss lesbar bleiben, sonst
verliert man genau die Läufe, die man untersuchen will.
"""

import json
from dataclasses import dataclass
from pathlib import Path


def read_jsonl(path):
    pfad = Path(path)
    if not pfad.exists():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8", errors="replace").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue          # abgeschnittene Zeile eines getöteten Prozesses
    return saetze


@dataclass(frozen=True)
class RunSummary:
    id: str
    dir: Path
    gestartet: str | None
    dauer_s: float
    backend: str
    nickname: str
    ergebnis: str
    fehler: str | None
    skript: str | None
    benutzer: str | None
    ereignisse_n: int
    abtastungen_n: int


def read_run(run_dir):
    verzeichnis = Path(run_dir)
    meta = {}
    lauf = verzeichnis / "lauf.json"
    if lauf.exists():
        try:
            meta = json.loads(lauf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    return RunSummary(
        id=meta.get("id", verzeichnis.name),
        dir=verzeichnis,
        gestartet=meta.get("gestartet"),
        dauer_s=float(meta.get("dauer_s", 0.0)),
        backend=meta.get("backend", "?"),
        nickname=meta.get("nickname", ""),
        ergebnis=meta.get("ergebnis", "unbekannt"),
        fehler=meta.get("fehler"),
        skript=meta.get("skript"),
        benutzer=meta.get("benutzer"),
        ereignisse_n=len(read_jsonl(verzeichnis / "ereignisse.jsonl")),
        abtastungen_n=len(read_jsonl(verzeichnis / "zustand.jsonl")),
    )


def list_runs(runs_dir):
    wurzel = Path(runs_dir)
    if not wurzel.is_dir():
        return []
    verzeichnisse = [p for p in wurzel.iterdir() if p.is_dir()]
    verzeichnisse.sort(key=lambda p: p.name, reverse=True)
    return [read_run(p) for p in verzeichnisse]
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_record_read.py -v`, erwartet 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/record/read.py tests/test_record_read.py && git commit -m "feat(record): absturztoleranter Leser für Läufe"
```

---

*Die Tasks 6–21 folgen im zweiten Teil dieses Plans (`...-fundament-teil2.md`), damit jede Datei überschaubar bleibt.*
