"""Das MuJoCo-Backend: der 2D-Sim mit einem 3D-Koerper, Kameras und Kollision.

Uebersprungen ohne `spotsim` (pip install -e ../matura-spot) oder ohne das
Menagerie-Asset. Alles, was hier geprueft wird, laeuft gegen die echte Puppe --
keine Attrappe: Kollision an der Mesh-Geometrie, Gitter aus gerenderter Tiefe,
Tags per Strahl.
"""


import pytest

spotsim = pytest.importorskip("spotsim")

from spotlab.backends.base import Capability  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402

needs_asset = pytest.mark.skipif(
    not spotsim.spot_asset_available(),
    reason="Menagerie-Asset fehlt -- python scripts/fetch_menagerie.py in matura-spot",
)
pytestmark = needs_asset


class Uhr:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def weiter(self, sekunden):
        self.t += sekunden


class Schreiber:
    """Sammelt Ereignisse wie der RunRecorder -- ohne Platte."""

    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))


def _backend(uhr, start, raum="durchgang", schreiber=None, **kw):
    from spotlab.backends.mujoco import MujocoBackend

    b = MujocoBackend(recorder=schreiber, jetzt=uhr, raum=raum_laden(raum), start=start, **kw)
    b.power_on()
    return b


def _fahre(backend, uhr, vx=0.0, wz=0.0, sekunden=1.0, schritt=0.05):
    from bosdyn.client.robot_command import RobotCommandBuilder

    ende = uhr.t + sekunden
    while uhr.t < ende:
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=vx, v_y=0.0, v_rot=wz),
            end_time_secs=uhr.t + 1.0,
        )
        uhr.weiter(schritt)
    backend.robot_state()


def _move(backend, uhr, vor=0.0, links=0.0, drehen=0.0, geduld=30.0, schritt=0.05):
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


@pytest.fixture
def uhr():
    return Uhr()


# ----------------------------------------------------------------- Bewegung


def test_move_kommt_im_3d_raum_an(uhr):
    backend = _backend(uhr, (1.0, 2.0, 0.0))
    assert _move(backend, uhr, vor=1.0)
    x, y, _yaw, z = backend.puppe.pose()
    assert x == pytest.approx(2.0, abs=0.05)
    assert y == pytest.approx(2.0, abs=0.05)
    assert 0.45 < z < 0.56, "Koerperhoehe aus der Kinematik der gemessenen Winkel"


def test_an_der_wand_bleibt_spot_stehen_und_sagt_es(uhr):
    """Die Zwischenwand bei x=4.5 hat ihre Tuer bei y 1.5-2.4. Wer bei y=0.7
    geradeaus faehrt, trifft sie -- mit dem Koerper aus dem Menagerie-Modell,
    nicht mit einem Kreis von 0.35 m."""
    schreiber = Schreiber()
    backend = _backend(uhr, (3.0, 0.7, 0.0), schreiber=schreiber)
    _fahre(backend, uhr, vx=0.5, sekunden=8.0)
    x = backend.puppe.pose()[0]
    assert x < 4.5, "durch die Wand gefahren"
    assert x > 3.6, "viel zu frueh stehengeblieben"
    anstoesse = [d for art, d in schreiber.ereignisse if art == "angestossen"]
    assert anstoesse and anstoesse[0]["hindernis"] == "Wand"
    assert len(anstoesse) == 1, "die Flanke wird einmal gemeldet, nicht je Takt"


def test_die_kiste_heisst_beim_anstossen_kiste(uhr):
    schreiber = Schreiber()
    backend = _backend(uhr, (0.8, 3.15, 0.0), schreiber=schreiber)   # Kiste: x 2.0-2.7, y 2.8-3.5
    _fahre(backend, uhr, vx=0.5, sekunden=6.0)
    assert backend.puppe.pose()[0] < 2.0
    anstoesse = [d for art, d in schreiber.ereignisse if art == "angestossen"]
    assert anstoesse and anstoesse[0]["hindernis"] == "Kiste"


def test_drehen_geht_auch_an_der_wand(uhr):
    """Wie im 2D-Raum: die Drehung wird immer uebernommen."""
    backend = _backend(uhr, (3.0, 0.7, 0.0))
    _fahre(backend, uhr, vx=0.5, sekunden=8.0)
    yaw_vorher = backend.puppe.pose()[2]
    _fahre(backend, uhr, wz=0.5, sekunden=1.0)
    assert backend.puppe.pose()[2] - yaw_vorher == pytest.approx(0.5, abs=0.1)


# --------------------------------------------------------------- Wahrnehmung


def test_das_gitter_kommt_aus_der_tiefe(uhr):
    """128x128 x 3 cm mit `known` -- durch denselben Entpacker wie am Roboter.
    Was keine Kamera sieht, ist unbekannt: hinter der Kiste und unter dem
    eigenen Koerper."""
    backend = _backend(uhr, (1.0, 2.0, 0.0))
    gitter = backend.local_grid()
    assert gitter.cells.shape == (128, 128)
    assert gitter.cell_size == pytest.approx(0.03)
    assert gitter.known is not None and (~gitter.known).any()
    # WELTkoordinaten, wie ObstacleGrid sie fuehrt: einen Meter vor Spot
    # (Start 1,2) liegt freier Boden, die Kiste beginnt erst bei y=2.8.
    assert gitter.is_free(2.0, 2.0), "der freie Boden vor Spot muss frei sein"
    assert not gitter.is_free(2.3, 3.1), "mitten in der Kiste ist nichts frei"


def test_tags_werden_erst_durch_die_tuer_gesehen(uhr):
    backend = _backend(uhr, (1.0, 2.0, 0.0))
    assert backend.world_objects() == [], "Tag 3 liegt 7.9 m weit weg"

    backend = _backend(uhr, (6.5, 2.0, 0.0))
    gefunden = backend.world_objects()
    assert [t.id for t in gefunden] == [3]
    assert gefunden[0].distance == pytest.approx(2.4, abs=0.1)
    assert gefunden[0].bearing == pytest.approx(0.0, abs=2.0)
    assert gefunden[0].kind == "apriltag"


def test_ein_tag_hinter_der_wand_bleibt_unsichtbar(uhr):
    """Bei (7.0, 0.7) ist Tag 3 nur 2.3 m weit weg, aber der Strahl aus keiner
    Kamera trifft ihn frei? Doch -- die Wand steht bei 4.5, nicht dazwischen.
    Deshalb der Gegentest: hinter der Zwischenwand, bei (4.0, 2.0) mit Blick
    durch die Tuer, ist der Tag 4.9 m weit weg -- ausser Reichweite."""
    backend = _backend(uhr, (4.0, 2.0, 0.0))
    assert backend.world_objects() == []


def test_bilder_kommen_von_zehn_quellen(uhr):
    backend = _backend(uhr, (1.0, 2.0, 0.0))
    quellen = backend.image_sources()
    assert len(quellen) == 10
    assert "frontleft_depth" in quellen and "back_fisheye_image" in quellen
    tiefe, grau = backend.images(["frontleft_depth", "frontleft_fisheye_image"])
    assert (tiefe.shot.image.rows, tiefe.shot.image.cols) == (240, 424)
    assert (grau.shot.image.rows, grau.shot.image.cols) == (480, 640)


def test_der_zustand_traegt_kinematik_und_kameras(uhr):
    backend = _backend(uhr, (1.0, 2.0, 0.0))
    zustand = backend.robot_state()
    assert len(zustand.kinematic_state.joint_states) == 12
    assert zustand.battery_states[0].charge_percentage.value > 0
    fuesse = zustand.foot_state
    assert len(fuesse) == 4 and abs(fuesse[0].foot_position_rt_body.x) > 0.1
    baum = zustand.kinematic_state.transforms_snapshot.child_to_parent_edge_map
    assert "frontleft" in baum and "odom" in baum


def test_die_faehigkeiten_nennen_die_kameras(uhr):
    koennen = _backend(uhr, (1.0, 2.0, 0.0)).capabilities()
    for c in (Capability.DEPTH_CAMERAS, Capability.GRAY_CAMERAS,
              Capability.WORLD_OBJECTS, Capability.LOCAL_GRID, Capability.LOCOMOTION):
        assert koennen & c


# -------------------------------------------------------------------- Ansicht


def test_die_ansicht_wird_als_jpeg_geschrieben(uhr, tmp_path):
    """Aus einem eigenen Thread -- der Aufrufer wartet nicht darauf."""
    import time

    ziel = tmp_path / "ansicht.jpg"
    backend = _backend(uhr, (1.0, 2.0, 0.0), ansicht_ziel=ziel)
    frist = time.monotonic() + 15.0
    while not ziel.is_file() and time.monotonic() < frist:
        time.sleep(0.05)
    assert ziel.is_file(), "keine Ansicht geschrieben"
    assert ziel.read_bytes()[:2] == b"\xff\xd8", "kein JPEG"
    backend.close()
    assert not backend._ansicht.is_alive(), "der Ansichtsthread muss mit close() enden"
    assert not list(tmp_path.glob("*.tmp")), "temporaere Datei liegen geblieben"


def test_die_wahrnehmung_rendert_keine_ansicht_mehr_nebenbei(uhr, tmp_path, monkeypatch):
    """Gemessen 06.09.2026: spot.state und spot.tags() kosteten je 160 ms,
    weil jeder Aufruf aus dem Hauptthread das Ansichtsbild rendertete."""
    backend = _backend(uhr, (1.0, 2.0, 0.0), ansicht_ziel=tmp_path / "ansicht.jpg")

    def verboten(*_a, **_k):
        raise AssertionError("Ansicht im Hauptthread gerendert")

    monkeypatch.setattr(backend.puppe, "ansicht", verboten)
    backend.robot_state()
    backend.world_objects()
    backend.close()


# ------------------------------------------------------------------ Bericht


def test_der_bericht_nennt_die_standhoehe_der_kinematik(uhr):
    bericht = _backend(uhr, (1.0, 2.0, 0.0)).bericht()
    puppe = bericht["puppe"]
    assert puppe["fassung"] >= 1
    assert abs(puppe["standhoehe_kinematik_m"] - puppe["standhoehe_gemessen_m"]) < 0.02


# ------------------------------------------------------------- Ende zu Ende


def test_connect_mit_mujoco_ende_zu_ende(tmp_path):
    """Dasselbe Schuelerprogramm, unveraendert -- nur backend='mujoco'."""
    import json

    import spotlab

    with spotlab.connect(backend="mujoco", raum="leer", runs_dir=tmp_path) as spot:
        spot.power_on()
        spot.stand()
        spot.move(forward=0.3)
        lauf = spot.run_dir if hasattr(spot, "run_dir") else None
    laeufe = sorted(p for p in tmp_path.iterdir() if p.is_dir())
    assert laeufe, "kein Lauf-Verzeichnis"
    lauf = laeufe[-1]
    meta = json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))
    assert meta["backend"] == "mujoco"
    assert meta["ergebnis"] == "ok"
    verbunden = json.loads((lauf / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert verbunden["daten"]["raum"] == "leer"
    assert "Menagerie" in verbunden["daten"]["hinweis"]
    assert (lauf / "ansicht.jpg").is_file()


# ------------------------------------------------------- gedrehte Raeume


def test_welt_aus_raum_dreht_waende_und_bloecke():
    import math

    import spotsim.puppe as puppe

    from spotlab.backends.mujoco import welt_aus_raum
    from spotlab.welt.raum import Block, Raum, RaumTag

    raum = Raum(name="G", beschreibung="", start=(0, 0, 0),
                waende=((1.0, 1.0, 1.0, 4.0),), wand_dicke=0.1, wand_hoehe=2.0,
                bloecke=(Block("Regal", 3.0, 2.0, 1.0, 0.4, 1.8, drehung=30.0),),
                tags=(RaumTag(5, 2.0, 2.0, 0.0, hoehe=0.5),))
    welt = welt_aus_raum(raum, puppe)
    wand = welt.quader[0]
    assert (wand.x, wand.y, wand.z) == (1.0, 2.5, 1.0)
    assert (wand.hx, wand.hy, wand.hz) == (pytest.approx(1.5), 0.05, 1.0)
    assert wand.yaw == pytest.approx(math.pi / 2)
    regal = welt.quader[1]
    assert regal.name == "Regal" and regal.yaw == pytest.approx(math.radians(30))
    assert (regal.hx, regal.hy, regal.hz) == (0.5, 0.2, 0.9)
    assert welt.tags[0].z == 0.5


# ----------------------------------------------------------------- Hoehe (Fassung 4)


def _raum_mit_rampe_und_treppe():
    from spotlab.welt.raum import Boden, Raum, Wand

    return Raum(name="H", beschreibung="", start=(1, 0, 0), wand_hoehe=1.0,
                waende=(Wand(0, 3, 14, 3, z=1.0),),
                boeden=(Boden("T", 3, 0, 2, 2, anstieg=1.0, stufen=5),        # x 2..4
                        Boden("P", 5, 0, 2, 2, z=1.0),                         # x 4..6
                        Boden("R", 8, 0, 2, 2, anstieg=0.5),                   # x 7..9: 0 -> 0.5
                        Boden("G", 12, 0, 2, 2, z=0.5)))                       # x 11..13


def test_welt_aus_raum_baut_boeden_stufen_und_rampen_wie_kaesten_fuer():
    import math

    import spotsim.puppe as puppe

    from spotlab.backends.mujoco import welt_aus_raum
    from spotlab.welt.hoehe import kaesten_fuer

    raum = _raum_mit_rampe_und_treppe()
    welt = welt_aus_raum(raum, puppe)
    assert welt.boden_z == 0.0                                                  # der Grundboden ist die Ebene
    namen = [q.name for q in welt.quader]
    assert namen[0] == "wand_0" and welt.quader[0].z == pytest.approx(1.5)     # 1.0 .. 2.0
    assert [n for n in namen if n.startswith("stufe_T_")] == [f"stufe_T_{i}" for i in range(5)]
    assert "boden_P" in namen and "rampe_R" in namen and "boden_G" in namen
    rampe = next(q for q in welt.quader if q.name == "rampe_R")
    assert rampe.pitch == pytest.approx(-math.atan2(0.5, 2.0))
    erwartet = {k[0]: k for b in raum.boeden for k in kaesten_fuer(b, 0.0)}
    getroffen = 0
    for q in welt.quader:
        if q.name in erwartet:
            k = erwartet[q.name]
            assert (q.x, q.y, q.z, q.hx, q.hy, q.hz) == pytest.approx((k[1], k[2], k[3], k[4], k[5], k[6]))
            assert q.yaw == pytest.approx(math.radians(k[7])) and q.pitch == pytest.approx(math.radians(k[8]))
            getroffen += 1
    assert getroffen == len(erwartet) == 8                                     # 5 Stufen, 2 Podeste, Rampe (fusst auf 0)


def test_fassung_und_stufenhoehe_sind_die_der_puppe():
    import spotsim.puppe as puppe
    from spotsim.local_grid import MAX_STUFE_M as PUPPE_STUFE

    from spotlab.backends.mujoco import PUPPE_FASSUNG
    from spotlab.welt.raum import MAX_STUFE_M

    assert PUPPE_FASSUNG == puppe.FASSUNG == 5
    assert PUPPE_STUFE == MAX_STUFE_M


@needs_asset
def test_der_koerper_steigt_die_treppe_und_haelt_an_der_kante(uhr):
    from spotlab.backends.mujoco import MujocoBackend

    schreiber = Schreiber()
    b = MujocoBackend(recorder=schreiber, jetzt=uhr, raum=_raum_mit_rampe_und_treppe(), start=(1.0, 0.0, 0.0))
    b.power_on()
    try:
        _fahre(b, uhr, vx=0.3, sekunden=12)
        assert 4.2 < b._pose[0] < 6.0 and b._z == pytest.approx(1.0), (b._pose, b._z)
        assert b.puppe.qpos()[2] == pytest.approx(1.0 + b.puppe.standhoehe(b._winkel()), abs=0.02)
        _fahre(b, uhr, vx=0.3, sekunden=8)                                     # bis zur Podestkante bei x = 6
        assert b._pose[0] < 6.0 and b._z == pytest.approx(1.0)
        arten = [art for art, _ in schreiber.ereignisse]
        assert "treppe_verweigert" not in arten
        assert any(d.get("hindernis") == "Kante" for art, d in schreiber.ereignisse if art == "angestossen")
    finally:
        b.close()


@needs_asset
def test_vorwaerts_abwaerts_wird_auch_in_3d_verweigert(uhr):
    from spotlab.backends.mujoco import MujocoBackend

    schreiber = Schreiber()
    b = MujocoBackend(recorder=schreiber, jetzt=uhr, raum=_raum_mit_rampe_und_treppe(), start=(5.5, 0.0, 180.0))
    b.power_on()
    try:
        _fahre(b, uhr, vx=0.3, sekunden=6)
        assert b._pose[0] > 3.9 and b._z == pytest.approx(1.0)
        assert [d["verlangt"] for art, d in schreiber.ereignisse if art == "treppe_verweigert"] == ["rückwärts runter"]
        assert b.bericht()["puppe"]["treppengang"] == "nicht gemessen"
    finally:
        b.close()


@needs_asset
def test_das_tiefengitter_misst_vom_boden_unter_dem_koerper(uhr):
    """Auf dem Podest ist das Podest frei; von unten ist seine Kante belegt."""
    import math

    from spotlab.backends.mujoco import MujocoBackend

    oben = MujocoBackend(jetzt=uhr, raum=_raum_mit_rampe_und_treppe(), start=(5.0, 0.0, 0.0))
    try:
        assert oben._z == pytest.approx(1.0)
        gitter = oben.local_grid()
        assert gitter.free_distance(5.0, 0.0, 90.0) > 0.5                      # quer ueber das Podest frei (Grad)
    finally:
        oben.close()
    unten = MujocoBackend(jetzt=uhr, raum=_raum_mit_rampe_und_treppe(), start=(6.8, 0.0, math.degrees(math.pi)))
    try:
        assert unten._z == pytest.approx(0.0)
        gitter = unten.local_grid()
        assert gitter.free_distance(6.8, 0.0, 180.0) < 0.9                     # die Podestkante bei x = 6 (Grad)
    finally:
        unten.close()


# ----------------------------------------------------------------- Gelaende (Fassung 5)


def test_welt_aus_raum_uebergibt_das_gelaende_als_feld():
    import numpy as np
    import spotsim.puppe as puppe

    from spotlab.backends.mujoco import welt_aus_raum
    from spotlab.welt import gelaende as g
    from spotlab.welt.raum import Raum

    ge = g.gitter(1.0, 2.0, 0.5, 3, 4, lambda x, y: None if x > 2.2 else 0.1 * y)
    welt = welt_aus_raum(Raum(name="G", beschreibung="", start=(1, 2, 0), gelaende=ge), puppe)
    assert isinstance(welt.gelaende, puppe.Gelaende)
    assert (welt.gelaende.x0, welt.gelaende.y0, welt.gelaende.zelle) == (1.0, 2.0, 0.5)
    assert welt.gelaende.hoehen.shape == (3, 4)
    assert np.isnan(welt.gelaende.hoehen[0, 3]) and welt.gelaende.hoehen[2, 0] == pytest.approx(0.3)
    assert welt_aus_raum(Raum(name="G", beschreibung="", start=(1, 2, 0)), puppe).gelaende is None
