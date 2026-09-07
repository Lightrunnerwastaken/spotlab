"""Die Katakomben, korrigiert: Luecken mit den Vorschlaegen, Gelaende, dann den Weg abfahren."""

import time
from pathlib import Path

import pytest

pytest.importorskip("bosdyn.api")

from spotlab.maps import gelaende_bau as gb  # noqa: E402
from spotlab.maps import rekonstruktion as rk  # noqa: E402
from spotlab.welt import korrektur as k  # noqa: E402
from spotlab.welt.hoehe import boden_bei  # noqa: E402
from spotlab.welt.kollision import bewege_mit_hoehe, klippen_von  # noqa: E402

KATAKOMBEN = Path(r"D:\Users\janis\Documents\Spot Projects\maps\map_catacombs_01")


@pytest.fixture(scope="module")
def katakomben():
    if not (KATAKOMBEN / "graph").is_file():
        pytest.skip("Katakomben-Karte fehlt auf diesem Rechner")
    return rk.rekonstruiere(KATAKOMBEN)


def test_die_vorschlaege_decken_die_meisten_kandidaten(katakomben):
    luecken = k.finde_luecken(katakomben.raum, katakomben.weg, katakomben.pauspapier)
    assert luecken
    mit = [lk for lk in luecken if lk.vorschlag != "unklar"]
    assert len(mit) >= 0.6 * len(luecken), (len(mit), len(luecken))


def test_korrigiert_laesst_sich_der_weg_abfahren(katakomben):
    raum, weg, punkte = katakomben.raum, katakomben.weg, katakomben.pauspapier
    t0 = time.monotonic()
    luecken = k.finde_luecken(raum, weg, punkte)
    entscheide = {i: (lk.vorschlag if lk.vorschlag != "unklar" else "lassen")
                  for i, lk in enumerate(luecken)}
    korrigiert = k.wende_an(raum, luecken, entscheide)
    erg = gb.baue_gelaende(korrigiert, weg, punkte)
    fertig = k.uebernimm_gelaende(korrigiert, erg.gelaende, True)
    dauer = time.monotonic() - t0
    assert dauer < 20.0, dauer
    assert all(fertig.gelaende.hoehe_bei(x, y) is not None for x, y, _z in weg)
    assert [b for b in fertig.boeden if b.stufen > 0]           # die Treppe bleibt
    assert not [b for b in fertig.boeden if b.stufen == 0]      # Rampen und Podeste sind Gelaende

    klippen = klippen_von(fertig)
    z, _ = boden_bei(fertig, weg[0][0], weg[0][1])
    pose = (weg[0][0], weg[0][1], 0.0)
    anstoesse = []
    for p, q in zip(weg, weg[1:]):
        pose, z, getroffen = bewege_mit_hoehe(fertig, pose, (q[0], q[1], 0.0), z, klippen)
        if getroffen is not None:
            anstoesse.append((round(p[0], 2), round(p[1], 2), getroffen))
            pose, z = (q[0], q[1], 0.0), boden_bei(fertig, q[0], q[1], z_nahe=z)[0]
    assert anstoesse == [], anstoesse


def test_der_kartenbezug_fuehrt_zurueck_in_den_seed_rahmen(katakomben):
    """Die Probe aufs Exempel fuer die Bruecke: ein Tag des rekonstruierten Raums,
    ueber `nach_karte` zurueckgerechnet, muss dort liegen, wo ihn die KARTE hat.
    Stimmt das nicht, steht am echten Roboter jede Sperrzone am falschen Ort."""
    from bosdyn.api.graph_nav import map_pb2
    from bosdyn.client.math_helpers import SE3Pose

    from spotlab.welt.raum import nach_karte

    raum = katakomben.raum
    assert raum.karte is not None and raum.karte.name == KATAKOMBEN.name

    graph = map_pb2.Graph()
    graph.ParseFromString((KATAKOMBEN / "graph").read_bytes())
    anker = {int(a.id.split("_")[-1]) if a.id.split("_")[-1].isdigit() else None:
             SE3Pose.from_proto(a.seed_tform_object)
             for a in graph.anchoring.objects}
    gemeinsam = [t for t in raum.tags if t.id in anker]
    assert gemeinsam, "kein Tag mit Ankerlage in der Karte"
    for tag in gemeinsam[:5]:
        zurueck = nach_karte(raum, tag.x, tag.y)
        soll = anker[tag.id]
        assert zurueck[0] == pytest.approx(soll.x, abs=0.05), tag.id
        assert zurueck[1] == pytest.approx(soll.y, abs=0.05), tag.id
