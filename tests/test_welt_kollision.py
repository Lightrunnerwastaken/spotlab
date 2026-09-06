import pytest

from spotlab.welt.kollision import (
    MAX_SCHRITT_M,
    ROBOTER_RADIUS_M,
    bewege,
    frei,
    sicht_frei,
)
from spotlab.welt.raum import Block, Raum, raum_laden

# Ein 10 x 10 m grosser Kasten mit einer Kiste in der Mitte (5..6, 5..6).
RAUM = Raum(
    name="T", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
    waende=(
        (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
        (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
    ),
    bloecke=(Block("Kiste", 5.5, 5.5, 1.0, 1.0),),
    tags=(),
)


def test_mitte_ist_frei():
    assert frei(RAUM, 2.0, 2.0)


def test_der_kreis_passt_durch_alles_was_das_gitter_frei_nennt():
    """`ObstacleGrid.is_free` haelt eine Stelle mit dem Vorgabe-Rand Abstand
    fuer frei. Waere der Sim-Koerper groesser, bliebe ein Programm, das der
    freien Strecke folgt, an einer Tuerkante haengen -- so geschehen am
    06.09.2026 mit 0.35 m. Und eine Gitterzelle Luft muss bleiben: das Gitter
    kennt Abstaende nur je Zellmitte."""
    import inspect

    from spotlab.backends.base import ObstacleGrid
    from spotlab.welt.wahrnehmung import GITTER_ZELLE_M

    rand = inspect.signature(ObstacleGrid.is_free).parameters["margin"].default
    assert ROBOTER_RADIUS_M <= rand - GITTER_ZELLE_M


def test_zu_nah_an_der_wand_ist_nicht_frei():
    # Die Wand hat eine Dicke: der Kreis darf erst ab radius + dicke/2 stehen.
    halb = RAUM.wand_dicke / 2
    assert not frei(RAUM, ROBOTER_RADIUS_M + halb - 0.01, 5.0)
    assert frei(RAUM, ROBOTER_RADIUS_M + halb + 0.01, 5.0)


def test_im_hindernis_ist_nicht_frei():
    assert not frei(RAUM, 5.5, 5.5)


def test_knapp_neben_dem_hindernis_ist_nicht_frei():
    """Der Roboter ist ein Kreis -- der Rand zaehlt, nicht der Mittelpunkt."""
    assert not frei(RAUM, 5.0 - ROBOTER_RADIUS_M + 0.05, 5.5)
    assert frei(RAUM, 5.0 - ROBOTER_RADIUS_M - 0.05, 5.5)


def test_freie_fahrt_kommt_an():
    pose, angestossen = bewege(RAUM, (2.0, 2.0, 0.0), (2.5, 2.0, 0.0))
    assert pose[:2] == pytest.approx((2.5, 2.0))
    assert angestossen is None


def test_fahrt_in_die_wand_bleibt_stehen_und_nennt_das_hindernis():
    pose, angestossen = bewege(RAUM, (1.0, 5.0, 0.0), (0.1, 5.0, 0.0))
    assert angestossen == "Wand"
    assert pose[0] > 0.1, "darf nicht bis ins Ziel gefahren sein"
    assert frei(RAUM, pose[0], pose[1]), "muss an einer erlaubten Stelle stehen"


def test_fahrt_in_die_kiste_nennt_ihren_namen():
    _pose, angestossen = bewege(RAUM, (3.0, 5.5, 0.0), (5.5, 5.5, 0.0))
    assert angestossen == "Kiste"


def test_langer_schritt_wird_zerlegt():
    """Ohne Zerlegung springt ein Programm mit langem dt durch die Wand."""
    weit = 3.0
    assert weit > 2 * ROBOTER_RADIUS_M
    pose, angestossen = bewege(RAUM, (2.0, 5.0, 0.0), (2.0 - weit, 5.0, 0.0))
    assert angestossen == "Wand"
    assert pose[0] >= ROBOTER_RADIUS_M - 0.01, "durch die Wand gerutscht"


def test_drehen_in_der_ecke_bleibt_erlaubt():
    """Ein Kreis, der sich dreht, ueberstreicht keine neue Flaeche."""
    ecke = (ROBOTER_RADIUS_M + 0.01, ROBOTER_RADIUS_M + 0.01, 0.0)
    pose, angestossen = bewege(RAUM, ecke, (ecke[0], ecke[1], 3.14))
    assert angestossen is None
    assert pose[2] == pytest.approx(3.14)


def test_teilstrecke_bis_kurz_vor_das_hindernis():
    """Nicht am Startpunkt kleben bleiben: was frei ist, wird gefahren."""
    pose, _ = bewege(RAUM, (1.0, 5.0, 0.0), (0.0, 5.0, 0.0))
    assert pose[0] < 1.0 - MAX_SCHRITT_M


@pytest.mark.parametrize("name", ["leer", "moebliert", "durchgang"])
def test_jede_vorlage_hat_eine_freie_startpose(name):
    """Eine Vorlage mit Startpose in einer Wand waere im Unterricht ein Raetsel."""
    raum = raum_laden(name)
    x, y, _grad = raum.start
    assert frei(raum, x, y), "Start liegt in einer Wand oder einem Hindernis"


def test_durchgang_ist_breiter_als_der_roboter():
    """0.9 m Luecke gegen 0.70 m Durchmesser -- 10 cm Spiel je Seite."""
    raum = raum_laden("durchgang")
    senkrechte = [w for w in raum.waende if w.x1 == w.x2]
    auf_x = {}
    for x1, y1, _x2, y2 in senkrechte:
        auf_x.setdefault(x1, []).append((min(y1, y2), max(y1, y2)))
    luecken = []
    for stuecke in auf_x.values():
        stuecke.sort()
        for (_a1, a2), (b1, _b2) in zip(stuecke, stuecke[1:]):
            if b1 > a2:
                luecken.append(b1 - a2)
    assert luecken, "durchgang.toml hat keine Luecke"
    assert max(luecken) >= 2 * ROBOTER_RADIUS_M + 0.15


def test_sichtlinie_durch_den_freien_raum():
    assert sicht_frei(RAUM, (1.0, 1.0), (3.0, 1.0))


def test_sichtlinie_durch_ein_hindernis_ist_versperrt():
    assert not sicht_frei(RAUM, (3.0, 5.5), (8.0, 5.5))


def test_sichtlinie_knapp_am_hindernis_vorbei():
    assert sicht_frei(RAUM, (3.0, 4.5), (8.0, 4.5))


def test_beruehrende_und_parallele_strecken():
    """Grenzfaelle der Schnittpruefung -- hier entstehen die stillen Fehler."""
    parallel = Raum(
        name="P", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
        waende=((2.0, 0.0, 2.0, 10.0),), tags=(),
    )
    assert not sicht_frei(parallel, (1.0, 1.0), (3.0, 1.0))   # kreuzt
    assert sicht_frei(parallel, (3.0, 1.0), (5.0, 1.0))       # dahinter, kreuzt nicht
    assert sicht_frei(parallel, (0.5, 1.0), (1.5, 1.0))       # davor, kreuzt nicht


# ------------------------------------------------------- gedrehte Bloecke

GEDREHT = Raum(
    name="G", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0.0, 0.0, 10.0, 0.0),),
    # 2 m lang, 0.5 m tief, um 45 Grad gedreht: die Laengsachse zeigt nach Nordost.
    bloecke=(Block("Balken", 5.0, 5.0, 2.0, 0.5, drehung=45.0),),
)


def test_ein_gedrehter_block_trifft_dort_wo_seine_ecke_ist():
    from spotlab.welt.kollision import abstand_block, hindernis_bei

    balken = GEDREHT.bloecke[0]
    # Auf der Laengsachse, 0.9 m von der Mitte: im Block (halbe Laenge 1.0).
    auf_achse = (5.0 + 0.9 * 0.7071, 5.0 + 0.9 * 0.7071)
    assert abstand_block(balken, *auf_achse) == 0.0
    assert hindernis_bei(GEDREHT, *auf_achse, radius=0.05) == "Balken"
    # In der Huelle des ungedrehten Blocks, aber neben dem gedrehten: frei.
    neben = (5.6, 5.0)
    assert abstand_block(balken, *neben) == pytest.approx(0.174, abs=0.01)
    assert hindernis_bei(GEDREHT, *neben, radius=0.05) is None


def test_die_sichtlinie_kennt_die_gedrehten_kanten():
    # Von Suedwest nach Nordost durch den Balken: versperrt.
    assert not sicht_frei(GEDREHT, (4.0, 4.0), (6.0, 6.0))
    # Quer dazu, knapp an der schmalen Seite vorbei: frei.
    assert sicht_frei(GEDREHT, (6.0, 4.0), (6.5, 4.5))
