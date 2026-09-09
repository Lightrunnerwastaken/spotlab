from spotlab.welt.korrektur import finde_luecken
from spotlab.welt.raum import Raum, Wand


def room(*walls):
    return Raum('Test', '', (0., 0., 0.), waende=walls)


def test_parallel_corridor_sides_are_not_a_gap():
    assert not finde_luecken(room(Wand(0, 0, 2, 0), Wand(0, .8, 2, .8)))


def test_overlapping_segments_do_not_move_backwards():
    assert not finde_luecken(room(Wand(0, 0, 2, 0), Wand(1, 0, 3, 0)))


def test_different_floors_are_not_joined():
    assert not finde_luecken(room(Wand(0, 0, 2, 0), Wand(2.5, 0, 4, 0, z=3)))


def test_upstairs_path_does_not_delete_downstairs_wall():
    assert not finde_luecken(room(Wand(0, 0, 4, 0)), weg=[(2, -1, 3), (2, 1, 3)])


def test_downstairs_path_does_not_delete_upstairs_wall():
    assert not finde_luecken(room(Wand(0, 0, 4, 0, z=3)), weg=[(2, -1, 0), (2, 1, 0)])


def test_path_height_is_interpolated_at_crossing():
    walls = room(Wand(0, 0, 4, 0, z=3))
    assert not finde_luecken(walls, weg=[(2, -1, 0), (2, 3, 4)])
    result = finde_luecken(walls, weg=[(2, -3, 0), (2, 1, 4)])
    assert result[0].vorschlag == 'loeschen'


def test_upstairs_crossing_is_not_door_evidence():
    walls = room(Wand(0, 0, 2, 0), Wand(3, 0, 5, 0))
    result = finde_luecken(walls, weg=[(2.5, -1, 3), (2.5, 1, 3)])
    assert len(result) == 1 and result[0].vorschlag == 'unklar'


def test_generator_path_has_same_evidence_as_list():
    walls = room(Wand(0, 0, 2, 0), Wand(3, 0, 5, 0))
    path = [(2.5, -1, 0), (2.5, 1, 0)]
    assert finde_luecken(walls, weg=iter(path)) == finde_luecken(walls, weg=path)


def test_upstairs_third_wall_does_not_block_gap():
    walls = room(Wand(0, 0, 2, 0), Wand(3, 0, 5, 0), Wand(2.5, -1, 2.5, 1, z=3))
    assert any(lk.waende == (0, 1) for lk in finde_luecken(walls))
