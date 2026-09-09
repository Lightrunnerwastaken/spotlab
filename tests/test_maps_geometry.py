from bosdyn.api.graph_nav import map_pb2

from spotlab.maps.geometry import grundriss


def _wegpunkt(graph, kennung, name=""):
    wp = graph.waypoints.add()
    wp.id = kennung
    wp.annotations.name = name
    wp.waypoint_tform_ko.rotation.w = 1.0
    return wp


def _kante(graph, von, nach, dx=1.0, dy=0.0):
    kante = graph.edges.add()
    kante.id.from_waypoint = von
    kante.id.to_waypoint = nach
    kante.from_tform_to.rotation.w = 1.0
    kante.from_tform_to.position.x = dx
    kante.from_tform_to.position.y = dy
    return kante


def _anker(graph, kennung, x, y):
    anker = graph.anchoring.anchors.add()
    anker.id = kennung
    anker.seed_tform_waypoint.rotation.w = 1.0
    anker.seed_tform_waypoint.position.x = x
    anker.seed_tform_waypoint.position.y = y


def test_anker_werden_bevorzugt():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a", "start")
    _wegpunkt(graph, "b", "kueche")
    _kante(graph, "a", "b")
    _anker(graph, "a", 0.0, 0.0)
    _anker(graph, "b", 3.0, 4.0)

    ergebnis = grundriss(graph)
    assert ergebnis.quelle == "anker"
    nach_id = {p.id: p for p in ergebnis.punkte}
    assert (nach_id["b"].x, nach_id["b"].y) == (3.0, 4.0)
    assert nach_id["b"].name == "kueche"
    assert ergebnis.kanten == [("a", "b")]


def test_ohne_anker_ueber_die_kantenkette():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _wegpunkt(graph, "c")
    _kante(graph, "a", "b", dx=1.0)
    _kante(graph, "b", "c", dx=1.0)

    ergebnis = grundriss(graph)
    assert ergebnis.quelle == "kette"
    nach_id = {p.id: p for p in ergebnis.punkte}
    assert abs(nach_id["a"].x - 0.0) < 1e-9
    assert abs(nach_id["b"].x - 1.0) < 1e-9
    assert abs(nach_id["c"].x - 2.0) < 1e-9


def test_kette_laeuft_auch_rueckwaerts():
    """Die Kante zeigt von b nach a — der Weg muss trotzdem gefunden werden."""
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "b", "a", dx=2.0)

    nach_id = {p.id: p for p in grundriss(graph).punkte}
    assert abs(abs(nach_id["a"].x - nach_id["b"].x) - 2.0) < 1e-9


def test_kette_traegt_den_hinweis_auf_rundungsfehler():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "a", "b")
    assert "Rundung" in grundriss(graph).hinweis


def test_leerer_graph():
    ergebnis = grundriss(map_pb2.Graph())
    assert ergebnis.quelle == "leer"
    assert ergebnis.punkte == []
    assert ergebnis.hinweis


def test_ein_wegpunkt_ohne_kanten_ist_zeichenbar():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a", "start")
    ergebnis = grundriss(graph)
    assert len(ergebnis.punkte) == 1
    assert ergebnis.punkte[0].x == 0.0


def test_mehrere_wegpunkte_ohne_kanten_sind_nicht_verortbar():
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    ergebnis = grundriss(graph)
    assert ergebnis.quelle == "leer"
    assert "Kanten" in ergebnis.hinweis


def test_unvollstaendige_anker_fallen_auf_die_kette_zurueck():
    """Anker nur für einen von zwei Wegpunkten — dann ist die Kette ehrlicher."""
    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "a", "b")
    _anker(graph, "a", 0.0, 0.0)

    assert grundriss(graph).quelle == "kette"


def _anker_gedreht(graph, kennung, x, y, grad):
    import math

    anker = graph.anchoring.anchors.add()
    anker.id = kennung
    anker.seed_tform_waypoint.rotation.w = math.cos(math.radians(grad) / 2)
    anker.seed_tform_waypoint.rotation.z = math.sin(math.radians(grad) / 2)
    anker.seed_tform_waypoint.position.x = x
    anker.seed_tform_waypoint.position.y = y


def test_punkte_tragen_die_blickrichtung_ihres_rahmens():
    """Aus Ankern wie aus der Kette: der Wegpunktrahmen hat eine Richtung, und
    die braucht, wer den Roboter relativ zum Wegpunkt einzeichnen will."""
    from spotlab.maps.geometry import lage_im_grundriss

    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    _kante(graph, "a", "b")
    _anker_gedreht(graph, "a", 0.0, 0.0, 0.0)
    _anker_gedreht(graph, "b", 3.0, 4.0, 90.0)
    riss = grundriss(graph)
    nach_id = {p.id: p for p in riss.punkte}
    assert abs(nach_id["b"].yaw - 90.0) < 1e-6 and nach_id["a"].yaw == 0.0

    # Ein Meter voraus im Rahmen von b (der nach +y zeigt) ist im Grundriss ein Meter +y.
    x, y, grad = lage_im_grundriss(riss, "b", (1.0, 0.0, 0.0))
    assert abs(x - 3.0) < 1e-6 and abs(y - 5.0) < 1e-6 and abs(grad - 90.0) < 1e-6
    # Und links davon (+y im Wegpunktrahmen) ist -x im Grundriss, gedreht um weitere 45 Grad.
    x, y, grad = lage_im_grundriss(riss, "b", (0.0, 1.0, 45.0))
    assert abs(x - 2.0) < 1e-6 and abs(y - 4.0) < 1e-6 and abs(grad - 135.0) < 1e-6
    assert lage_im_grundriss(riss, "gibtsnicht", (0.0, 0.0, 0.0)) is None
    assert lage_im_grundriss(riss, "b", None) is None


def test_die_kette_traegt_die_richtung_aus_den_kanten():
    import math

    graph = map_pb2.Graph()
    _wegpunkt(graph, "a")
    _wegpunkt(graph, "b")
    kante = _kante(graph, "a", "b", dx=2.0)
    kante.from_tform_to.rotation.w = math.cos(math.radians(90) / 2)
    kante.from_tform_to.rotation.z = math.sin(math.radians(90) / 2)
    riss = grundriss(graph)
    nach_id = {p.id: p for p in riss.punkte}
    assert riss.quelle == "kette" and abs(nach_id["b"].yaw - 90.0) < 1e-6
