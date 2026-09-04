"""Das Sim-Backend: bewegt sich nach Messdaten, behauptet nichts darüber hinaus.

Zwei Sorten Aussagen. Die eine: es rechnet richtig — Strecke, Drehung, Gang.
Die andere, wichtigere: es ERFINDET NICHTS. Wo keine Messung ist, steht null
oder gar nichts, und die Aufzeichnung sagt, dass hier kein Roboter war.
"""

import json
import math

import pytest

from spotlab.backends.base import Capability
from spotlab.backends.sim import SimBackend
from spotlab.errors import CommandRejected, NotPowered, UnsupportedCapability
from spotlab.kalibrierung.modell import Gangmodell, integriere, lade_modell


class Uhr:
    """Eine Uhr, die nur vorgeht, wenn der Test es sagt."""

    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def weiter(self, sekunden):
        self.t += sekunden


def _fahre(backend, uhr, vx=0.0, wz=0.0, sekunden=1.0, schritt=0.05):
    """Wie `api/motion.walk`: laufend nachsenden, sonst verfällt das Kommando."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    ende = uhr.t + sekunden
    while uhr.t < ende:
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=vx, v_y=0.0, v_rot=wz),
            end_time_secs=uhr.t + 1.0,
        )
        uhr.weiter(schritt)
    backend.robot_state()


def _sim(uhr):
    b = SimBackend(jetzt=uhr)
    b.power_on()
    return b


@pytest.fixture
def uhr():
    return Uhr()


# --------------------------------------------------------------- Bewegung


def test_die_strecke_stimmt(uhr):
    backend = _sim(uhr)
    _fahre(backend, uhr, vx=0.3, sekunden=4.0)
    from bosdyn.client.frame_helpers import (
        BODY_FRAME_NAME,
        ODOM_FRAME_NAME,
        get_a_tform_b,
    )

    pose = get_a_tform_b(backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME)
    assert pose.position.x == pytest.approx(1.2, abs=0.05)
    assert pose.position.y == pytest.approx(0.0, abs=0.01)


def test_die_drehung_stimmt(uhr):
    backend = _sim(uhr)
    _fahre(backend, uhr, wz=0.5, sekunden=3.0)
    from bosdyn.client.frame_helpers import (
        BODY_FRAME_NAME,
        ODOM_FRAME_NAME,
        get_a_tform_b,
    )

    pose = get_a_tform_b(backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME)
    yaw = 2 * math.atan2(pose.rotation.z, pose.rotation.w)
    assert yaw == pytest.approx(1.5, abs=0.1)      # 0.5 rad/s mal 3 s


def test_beim_kurvenfahren_geht_es_nicht_geradeaus():
    """Die Geschwindigkeit steht im KOERPERframe, die Pose im odom-Frame."""
    pose = (0.0, 0.0, 0.0)
    for _ in range(100):
        pose = integriere(pose, 0.3, 0.0, 0.5, 0.02)
    assert pose[1] > 0.1, "eine Linkskurve muss nach links fuehren"
    assert pose[2] == pytest.approx(1.0, abs=0.05)


def test_die_gelenke_bewegen_sich_beim_gehen(uhr):
    backend = _sim(uhr)
    winkel = []
    for _ in range(40):
        _fahre(backend, uhr, vx=0.3, sekunden=0.05, schritt=0.05)
        zustand = backend.robot_state()
        winkel.append(
            next(g.position.value for g in zustand.kinematic_state.joint_states
                 if g.name == "fl.kn")
        )
    assert max(winkel) - min(winkel) > 0.05, "der Gang steht still"


def test_im_stand_liegen_alle_vier_fuesse_auf(uhr):
    from bosdyn.api import robot_state_pb2

    backend = _sim(uhr)
    uhr.weiter(1.0)
    zustand = backend.robot_state()
    kontakte = [f.contact for f in zustand.foot_state]
    assert kontakte == [robot_state_pb2.FootState.CONTACT_MADE] * 4


def test_beim_gehen_heben_fuesse_ab(uhr):
    from bosdyn.api import robot_state_pb2

    backend = _sim(uhr)
    gesehen = set()
    for _ in range(40):
        _fahre(backend, uhr, vx=0.3, sekunden=0.05, schritt=0.05)
        zustand = backend.robot_state()
        gesehen.add(tuple(f.contact for f in zustand.foot_state))
    assert len(gesehen) > 1, "die Fusskontakte aendern sich nie"
    assert any(
        robot_state_pb2.FootState.CONTACT_LOST in muster for muster in gesehen
    ), "kein Fuss hebt je ab"


# --------------------------------------------------------------- Wie der echte Spot


def test_ohne_nachschub_bleibt_er_stehen(uhr):
    """Geschwindigkeitskommandos verfallen — beim echten Spot ist das eine
    Sicherheitseigenschaft. Ein Sim, der weiterliefe, verstecke sie."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    backend.send_command(
        RobotCommandBuilder.synchro_velocity_command(v_x=0.3, v_y=0.0, v_rot=0.0),
        end_time_secs=uhr.t + 1.0,
    )
    uhr.weiter(1.0)
    backend.robot_state()
    from bosdyn.client.frame_helpers import (
        BODY_FRAME_NAME,
        ODOM_FRAME_NAME,
        get_a_tform_b,
    )

    nach_einer_sekunde = get_a_tform_b(
        backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME
    ).position.x
    uhr.weiter(10.0)
    backend.robot_state()
    danach = get_a_tform_b(
        backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME
    ).position.x
    assert danach == pytest.approx(nach_einer_sekunde, abs=0.01)


def test_abgelaufene_endzeit_wird_abgewiesen(uhr):
    """Dieselbe Pruefung wie im Trockenlauf, aus demselben Grund: `end_time_secs`
    ist ein ZEITPUNKT. Ein Sim, der das durchliesse, verstecke den Fehler, an
    dem der echte Spot sich nie bewegt haette."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    with pytest.raises(CommandRejected, match="Zeitpunkt"):
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=0.3, v_y=0.0, v_rot=0.0),
            end_time_secs=1.0,
        )


def test_ohne_strom_geht_nichts(uhr):
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = SimBackend(jetzt=uhr)
    with pytest.raises(NotPowered):
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=0.3, v_y=0.0, v_rot=0.0)
        )


def test_sitzen_haelt_an(uhr):
    from bosdyn.api import robot_state_pb2
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    _fahre(backend, uhr, vx=0.3, sekunden=1.0)
    backend.send_command(RobotCommandBuilder.synchro_sit_command())
    uhr.weiter(2.0)
    zustand = backend.robot_state()
    # Der Enum kennt kein Sitzen -- NOT_READY ist die Deutung, und sie ist
    # als solche gekennzeichnet.
    assert zustand.behavior_state.state == robot_state_pb2.BehaviorState.STATE_NOT_READY
    assert zustand.kinematic_state.velocity_of_body_in_odom.linear.x == 0.0


# --------------------------------------------------------------- Es erfindet nichts


def test_es_gibt_keine_kameras(uhr):
    backend = _sim(uhr)
    assert backend.image_sources() == []
    assert not (backend.capabilities() & Capability.CAMERAS)
    with pytest.raises(UnsupportedCapability, match="erfundene Bilder"):
        backend.images(["frontleft"])


def test_es_gibt_kein_graphnav(uhr):
    assert not (_sim(uhr).capabilities() & Capability.GRAPH_NAV)


def test_gelenkmomente_bleiben_null_und_das_ist_absicht(uhr):
    """Die Kennlinie traegt nur WINKEL. Erfundene Momente saehen aus wie
    Messwerte und liefen in jede Auswertung."""
    backend = _sim(uhr)
    _fahre(backend, uhr, vx=0.3, sekunden=1.0)
    for gelenk in backend.robot_state().kinematic_state.joint_states:
        assert gelenk.load.value == 0.0
        assert gelenk.velocity.value == 0.0
        assert gelenk.acceleration.value == 0.0


def test_es_gibt_keinen_erfundenen_reibwert(uhr):
    """Ein erfundenes ground_mu_est = 0.6 mittelte sich durch jede
    Kalibrierauswertung — dieselbe Regel wie in api/state.py."""
    backend = _sim(uhr)
    _fahre(backend, uhr, vx=0.3, sekunden=1.0)
    for fuss in backend.robot_state().foot_state:
        assert not fuss.HasField("terrain")


def test_ausserhalb_der_messung_wird_gezaehlt(uhr):
    """Unter der langsamsten gemessenen Gangart gibt es keine Daten. Das
    Backend nimmt dann die naechstgelegene und ZAEHLT das mit."""
    backend = _sim(uhr)
    assert backend.ausserhalb_der_messung == 0
    _fahre(backend, uhr, vx=0.01, sekunden=1.0)
    assert backend.ausserhalb_der_messung > 0


def test_eine_zieltrajektorie_wird_nicht_erfunden(uhr):
    """`move()` schickt eine Zieltrajektorie; der echte Spot waehlt sein Tempo
    selbst. Das wurde NIE vermessen — im Beobachter-Modus hat niemand
    kommandiert. Statt eine Fahrt zu erfinden, wird es gezaehlt."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    backend.send_command(
        RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
            1.0, 0.0, 0.0, backend.frame_tree_snapshot()
        ),
        end_time_secs=uhr.t + 10.0,
    )
    assert backend.ausserhalb_der_messung > 0


# --------------------------------------------------------------- Das Modell


def test_das_modell_nimmt_nur_fenster_mit_absicht():
    """Der Rundgang und die Treppe haben kein Ziel — dort wollte niemand ein
    Tempo halten, und die Punkte laegen alle am langsamen Ende."""
    modell = lade_modell()
    fenster = [s["herkunft"]["fenster"] for s in modell.fahren + modell.drehen]
    assert fenster, "keine Stuetzstellen"
    assert all(f.startswith(("B2", "B3")) for f in fenster), sorted(set(fenster))


def test_zwischen_zwei_stuetzstellen_wird_interpoliert():
    modell = lade_modell()
    langsam, schnell = modell.fahren[0], modell.fahren[-1]
    mitte = (langsam["tempo_m_s"] + schnell["tempo_m_s"]) / 2
    dauer = modell.zyklusdauer(mitte, 0.0)
    dauern = sorted(s["zyklusdauer_s"] for s in modell.fahren)
    assert dauern[0] <= dauer <= dauern[-1]


def test_ausserhalb_meldet_das_modell_rand():
    modell = lade_modell()
    unten, oben = modell.tempo_bereich
    assert modell.rand(unten * 0.5, 0.0) is True
    assert modell.rand(oben * 2.0, 0.0) is True
    assert modell.rand((unten + oben) / 2, 0.0) is False


def test_die_beschreibung_nennt_die_quelle():
    """Wer eine Sim-Bewegung nachschlagen will, muss zu den Messfenstern
    zurueckfinden, aus denen sie stammt."""
    modell = lade_modell()
    beschreibung = modell.beschreibung(0.2, 0.0)
    assert beschreibung["art"] == "fahrt"
    assert len(beschreibung["zwischen"]) == 2
    assert all(f.startswith("B") for f in beschreibung["zwischen"])


def test_drehen_und_fahren_werden_getrennt_bedient():
    """Eine KOMBINIERTE Bewegung wurde nie vermessen. Zwischen zwei Messreihen
    zu mischen, die nichts miteinander zu tun haben, waere eine Erfindung."""
    modell = lade_modell()
    assert modell.beschreibung(0.3, 0.0)["art"] == "fahrt"
    assert modell.beschreibung(0.0, 0.5)["art"] == "drehung"


def test_eine_kennlinie_ohne_fahrt_wird_abgewiesen():
    with pytest.raises(ValueError, match="Fahrt"):
        Gangmodell({"phasenpunkte": 25, "stuetzstellen": []})


# --------------------------------------------------------------- Die Ehrlichkeit


def test_der_lauf_sagt_dass_er_nicht_erprobt_ist(tmp_path):
    """Ein Skript, das hier durchlaeuft, ist NICHT erprobt. Wer den Lauf
    spaeter ansieht, muss das sehen — nicht nur wer den Docstring liest."""
    import spotlab

    with spotlab.connect(backend="sim", runs_dir=tmp_path) as spot:
        spot.power_on()
        spot.stand()
        verzeichnis = spot.recorder.dir

    lauf = json.loads((verzeichnis / "lauf.json").read_text(encoding="utf-8"))
    assert lauf["backend"] == "sim"

    zeilen = (verzeichnis / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    verbunden = next(
        json.loads(z) for z in zeilen if json.loads(z)["art"] == "verbunden"
    )
    assert "NICHT am Roboter erprobt" in verbunden["daten"]["hinweis"]


# --------------------------------------------------------------- move()


def _pose(backend):
    from bosdyn.client.frame_helpers import (
        BODY_FRAME_NAME,
        ODOM_FRAME_NAME,
        get_a_tform_b,
    )

    p = get_a_tform_b(backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME)
    return p.position.x, p.position.y, 2 * math.atan2(p.rotation.z, p.rotation.w)


def _move(backend, uhr, vor=0.0, links=0.0, drehen=0.0, geduld=60.0, schritt=0.05):
    """Wie `api/motion.move`: Ziel schicken, dann auf die Rueckmeldung warten."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    kennung = backend.send_command(
        RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
            vor, links, drehen, backend.frame_tree_snapshot()
        ),
        end_time_secs=uhr.t + geduld,
    )
    ende = uhr.t + geduld
    while uhr.t < ende:
        if backend.command_feedback(kennung).done:
            return True
        uhr.weiter(schritt)
    return False


def test_move_kommt_wirklich_an(uhr):
    """Vorher tat `move()` im Sim GAR NICHTS -- das Skript lief durch und der
    Schueler lernte nichts daraus. Ein stilles Nichtstun ist die schlechteste
    Antwort."""
    backend = _sim(uhr)
    assert _move(backend, uhr, vor=1.0), "nicht angekommen"
    x, y, _ = _pose(backend)
    assert x == pytest.approx(1.0, abs=0.05)
    assert y == pytest.approx(0.0, abs=0.05)


def test_move_dreht_auf_den_zielwinkel(uhr):
    backend = _sim(uhr)
    assert _move(backend, uhr, drehen=math.pi / 2)
    _, _, yaw = _pose(backend)
    assert yaw == pytest.approx(math.pi / 2, abs=0.05)


def test_move_faehrt_im_koerperframe(uhr):
    """Nach einer Vierteldrehung muss „vorwaerts" nach +y zeigen, nicht +x.
    Die Geschwindigkeit ist koerperfest, das Ziel steht in odom."""
    backend = _sim(uhr)
    assert _move(backend, uhr, drehen=math.pi / 2)
    assert _move(backend, uhr, vor=1.0)
    x, y, _ = _pose(backend)
    assert y == pytest.approx(1.0, abs=0.05)
    assert x == pytest.approx(0.0, abs=0.05)


def test_move_meldet_erst_bei_ankunft_fertig(uhr):
    """Sonst kehrte `move()` zurueck, waehrend der Roboter noch unterwegs ist."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    kennung = backend.send_command(
        RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
            2.0, 0.0, 0.0, backend.frame_tree_snapshot()
        ),
        end_time_secs=uhr.t + 60.0,
    )
    assert backend.command_feedback(kennung).done is False
    uhr.weiter(0.2)
    assert backend.command_feedback(kennung).done is False, "zu frueh fertig"
    assert _pose(backend)[0] < 2.0


def test_ein_verfallenes_ziel_haelt_an(uhr):
    """`api/motion.move()` setzt die Endzeit auf genau seine Geduld. Laeuft sie
    ab, muss der Roboter stehen -- nicht weiterfahren, waehrend das Skript
    laengst mit einer Ausnahme abgebrochen hat."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    backend.send_command(
        RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
            50.0, 0.0, 0.0, backend.frame_tree_snapshot()
        ),
        end_time_secs=uhr.t + 2.0,
    )
    uhr.weiter(2.5)
    backend.robot_state()
    stand = _pose(backend)[0]
    uhr.weiter(30.0)
    backend.robot_state()
    assert _pose(backend)[0] == pytest.approx(stand, abs=0.01)
    assert stand < 50.0, "das Ziel haette gar nicht erreicht werden duerfen"


def test_ein_walk_hebt_ein_laufendes_ziel_auf(uhr):
    """Sonst schrieben Zielregler und Fahrkommando abwechselnd in dieselbe
    Sollgeschwindigkeit."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    backend = _sim(uhr)
    backend.send_command(
        RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
            10.0, 0.0, 0.0, backend.frame_tree_snapshot()
        ),
        end_time_secs=uhr.t + 60.0,
    )
    uhr.weiter(0.5)
    backend.send_command(
        RobotCommandBuilder.synchro_velocity_command(v_x=0.0, v_y=0.0, v_rot=0.0),
        end_time_secs=uhr.t + 1.0,
    )
    uhr.weiter(0.1)
    backend.robot_state()
    stand = _pose(backend)[0]
    uhr.weiter(20.0)
    backend.robot_state()
    assert _pose(backend)[0] == pytest.approx(stand, abs=0.01)


def test_das_tempo_fuer_ein_ziel_ist_ein_gemessenes(uhr):
    """Der echte Spot waehlt bei einer Zieltrajektorie sein Tempo selbst, und
    das wurde nie vermessen. Gewaehlt wird deshalb eine Zahl, fuer die es eine
    GANGART gibt -- keine erfundene."""
    modell = lade_modell()
    unten, oben = modell.tempo_bereich
    assert unten <= modell.tempo_vorschlag <= oben
    assert modell.tempo_vorschlag in [s["tempo_m_s"] for s in modell.fahren]


# --------------------------------------------------------------- Der Bericht


def test_der_bericht_zaehlt_takte_und_ziele_getrennt(uhr):
    """Takte sind Zeitschritte, Ziele sind Kommandos. In einer Zahl addiert
    haenge das Verhaeltnis an der Abtastrate."""
    backend = _sim(uhr)
    _fahre(backend, uhr, vx=0.3, sekunden=1.0)
    _move(backend, uhr, vor=0.3)
    bericht = backend.bericht()
    assert bericht["takte_in_bewegung"] > 0
    assert bericht["zieltrajektorien"] == 1
    assert 0.0 <= bericht["anteil_ausserhalb"] <= 1.0


def test_der_bericht_nennt_den_bereich_der_kennlinie(uhr):
    """Wer einen Sim-Lauf auswertet, muss sehen, WORAUF er kalibriert war."""
    bericht = _sim(uhr).bericht()
    kennlinie = bericht["kennlinie"]
    assert kennlinie["stuetzstellen_fahrt"] >= 3
    von, bis = kennlinie["tempo_bereich_m_s"]
    assert 0 < von < bis
    assert kennlinie["standhoehe_m"] == pytest.approx(0.51, abs=0.02)


def test_ohne_bewegung_gibt_es_keinen_anteil(uhr):
    """Fehlende Messwerte sind None, nie 0 -- „nichts bewegt" und „nichts lag
    ausserhalb" sind zweierlei."""
    assert _sim(uhr).bericht()["anteil_ausserhalb"] is None


def test_langsamer_als_gemessen_faellt_im_bericht_auf(uhr):
    backend = _sim(uhr)
    unten, _ = backend._modell.tempo_bereich
    _fahre(backend, uhr, vx=unten / 5, sekunden=1.0)
    assert backend.bericht()["anteil_ausserhalb"] == pytest.approx(1.0)


def test_der_bericht_steht_am_ende_in_lauf_json(tmp_path):
    """Ohne diese Zahlen sieht ein Sim-Lauf aus wie jeder andere."""
    import spotlab

    with spotlab.connect(backend="sim", runs_dir=tmp_path) as spot:
        spot.power_on()
        spot.stand()
        spot.walk(0.3, 0.0, 0.0, duration=0.3)
        verzeichnis = spot.recorder.dir

    lauf = json.loads((verzeichnis / "lauf.json").read_text(encoding="utf-8"))
    assert "sim" in lauf, sorted(lauf)
    bericht = lauf["sim"]
    assert bericht["takte_in_bewegung"] > 0
    assert "NICHT am Roboter erprobt" in bericht["hinweis"]
    assert bericht["kennlinie"]["stuetzstellen_fahrt"] >= 3
    assert lauf["ergebnis"] == "ok"


def test_ein_trockenlauf_bekommt_keinen_sim_bericht(tmp_path):
    """`hasattr(unten, "bericht")` darf nicht versehentlich andere Backends
    treffen -- ein dryrun-Lauf hat nichts zu berichten."""
    import spotlab

    with spotlab.connect(backend="dryrun", runs_dir=tmp_path) as spot:
        spot.power_on()
        verzeichnis = spot.recorder.dir

    lauf = json.loads((verzeichnis / "lauf.json").read_text(encoding="utf-8"))
    assert "sim" not in lauf


# ------------------------------------------------------- Uebungsraum (Stufe 10)


def _uebungsraum():
    from spotlab.welt.raum import Hindernis, Raum, RaumTag

    return Raum(
        name="T", beschreibung="", groesse=(10.0, 10.0), start=(5.0, 5.0, 0.0),
        waende=(
            (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
            (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
        ),
        hindernisse=(Hindernis("Kiste", (7.0, 4.5, 0.5, 1.0)),),
        tags=(RaumTag(1, 6.0, 5.0, 180.0),),
    )


class _Mitschreiber:
    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))

    def sample(self, daten):
        pass


def test_ohne_raum_bleibt_alles_wie_vorher():
    """Die wichtigste Zusicherung: kein bestehender Lauf aendert sich."""
    from spotlab.backends.base import Capability
    from spotlab.backends.sim import SimBackend

    backend = SimBackend()
    assert not backend.capabilities() & Capability.WORLD_OBJECTS
    assert not backend.capabilities() & Capability.LOCAL_GRID
    assert backend.world_objects() == []


def test_mit_raum_kommen_die_faehigkeiten_dazu():
    from spotlab.backends.base import Capability
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(5.0, 5.0, 0.0))
    assert backend.capabilities() & Capability.WORLD_OBJECTS
    assert backend.capabilities() & Capability.LOCAL_GRID


def test_start_setzt_die_pose():
    import math as _math

    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(3.0, 2.0, 90.0))
    assert backend._pose[0] == pytest.approx(3.0)
    assert backend._pose[1] == pytest.approx(2.0)
    assert backend._pose[2] == pytest.approx(_math.radians(90.0))


def test_tags_kommen_in_grad_und_metern():
    from spotlab.backends.base import Tag
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(5.0, 5.0, 0.0))
    gefunden = backend.world_objects(kinds=["apriltag"])
    assert len(gefunden) == 1
    tag = gefunden[0]
    assert isinstance(tag, Tag)
    assert tag.id == 1
    assert tag.distance == pytest.approx(1.0, abs=0.01)
    assert tag.bearing == pytest.approx(0.0, abs=1.0)


def test_gitter_traegt_die_bekannt_maske():
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(5.0, 5.0, 0.0))
    gitter = backend.local_grid()
    assert gitter.cell_size == pytest.approx(0.03)
    assert gitter.known is not None
    assert gitter.cells.shape == gitter.known.shape


def test_anstossen_wird_genau_einmal_gemeldet():
    """Ein Programm, das zehn Sekunden gegen eine Wand drueckt, darf das
    Protokoll nicht mit hundert gleichen Zeilen fluten."""
    from spotlab.backends.sim import SimBackend

    schreiber = _Mitschreiber()
    backend = SimBackend(recorder=schreiber, raum=_uebungsraum(), start=(0.5, 5.0, 0.0))
    for _ in range(5):
        backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.2, 5.0, 0.0))
    anstoesse = [e for e in schreiber.ereignisse if e[0] == "angestossen"]
    assert len(anstoesse) == 1
    assert anstoesse[0][1]["hindernis"] == "Wand"


def test_nach_freier_fahrt_wird_wieder_gemeldet():
    from spotlab.backends.sim import SimBackend

    schreiber = _Mitschreiber()
    backend = SimBackend(recorder=schreiber, raum=_uebungsraum(), start=(0.5, 5.0, 0.0))
    backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.2, 5.0, 0.0))
    backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.6, 5.0, 0.0))   # frei
    backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.2, 5.0, 0.0))
    assert len([e for e in schreiber.ereignisse if e[0] == "angestossen"]) == 2


# ------------------------------------------------- Raum aus der Umgebung


def test_connect_nimmt_den_raum_aus_der_umgebung(tmp_path, monkeypatch):
    """Die GUI reicht durch, was auf dem BILDSCHIRM steht.

    Ueber `cfg.raum` allein ging das schief: die Konfiguration bekam den Raum
    erst beim Klick in die Zeichnung, und wer nur startete, fuhr in gar keinem
    Raum -- Start (0, 0), quer durch die Waende (Lauf vom 04.09.2026,
    `"raum": null`).
    """
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    monkeypatch.setenv("SPOTLAB_RAUM", "durchgang")
    with spotlab.connect(runs_dir=tmp_path) as spot:
        assert spot.backend._raum is not None
        assert spot.backend._pose[:2] == (1.0, 2.0)      # Start der Vorlage


def test_connect_nimmt_die_startpose_aus_der_umgebung(tmp_path, monkeypatch):
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    monkeypatch.setenv("SPOTLAB_RAUM", "leer")
    monkeypatch.setenv("SPOTLAB_RAUM_START", "3.00,2.50,90.0")
    with spotlab.connect(runs_dir=tmp_path) as spot:
        assert spot.backend._pose[:2] == (3.0, 2.5)


def test_ein_ausdrueckliches_argument_schlaegt_die_umgebung(tmp_path, monkeypatch):
    """Ein Skript, das seinen Raum nennt, haengt nicht davon ab, was in der
    GUI stand."""
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    monkeypatch.setenv("SPOTLAB_RAUM", "leer")
    with spotlab.connect(runs_dir=tmp_path, raum="durchgang") as spot:
        assert spot.backend._pose[:2] == (1.0, 2.0)
