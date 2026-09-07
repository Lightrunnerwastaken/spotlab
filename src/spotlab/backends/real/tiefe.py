"""Tiefenbilder als Punktwolke -- und was UEBER dem Roboter haengt.

Das Hindernisgitter beschreibt den BODEN. `obstacle_distance` ist eine flache
Karte: eine Tischplatte in 75 cm Hoehe kommt darin nicht vor, und unter einer
Tischreihe steht fuer jeden Planer freie Flaeche mit unerkundetem Raum
dahinter. Genau dort ist der Explorer am 07.09.2026 hineingefahren und musste
mit dem Not-Aus geholt werden. Die Tiefenkameras SEHEN die Unterseite der
Platte; sie landet nur in keinem Gitter.

Hier wird sie sichtbar: Tiefenbild → Punktwolke (Lochkamera) → Koerperrahmen
(Extrinsik aus dem Rahmenbaum der Aufnahme) → aufgerichtet (Roll und Nick
heraus, das Hoehenband haengt an der Schwerkraft) → was im Band ueber der
Koerpermitte liegt.

**Geprueft an einer echten Aufnahme** (12.08.2026, `tests/daten/tiefe_real_20260812/`):
der Boden landet bei −0.51 m, also auf der gemessenen Standhoehe; ein freier
Gang laesst das Band leer; eine Tischreihe erscheint 0.72 m voraus, 0.17 m
ueber der Koerpermitte. Ueber die ganze Fahrt (1181 Takte) hatten 341 Takte
Ueberhang im Korridor, davon 71 naeher als ein Meter — ein Tor bei 1 m spricht
also selten an, aber dann, wenn es zaehlt.

Die Rechnung kostet 5 ms je Takt fuer beide Frontkameras (`SCHRITT` 2, an den
Fixtures gemessen; mit jedem Pixel 20 ms, mit jedem vierten 1 ms — der Abstand
bleibt in allen dreien derselbe). Der Bildabruf ueber WLAN wiegt schwerer.

**Kein Ersatz fuer das Hindernisgitter, eine Ergaenzung.** Das Gitter kennt
Boden, Stufen und Kanten, diese Rechnung kennt Ueberhaenge. Glas sieht keine
von beiden — die Tiefenkameras schauen hindurch wie das Gitter.
"""

import math

import numpy as np

from spotlab.errors import SpotlabError

# Hoehenband ueber der KOERPERMITTE (im Stand rund 0.51 m ueber dem Boden).
# Unten knapp darueber: was tiefer haengt, steht auf dem Boden und gehoert dem
# Gitter. Oben 0.70 m: was hoeher ist, laesst den Roboter durch (Tuersturz,
# Zimmerdecke). Eine Tischplatte liegt bei +0.2 m mitten im Band.
KOPF_UNTEN_M = 0.05
KOPF_OBEN_M = 0.70

# Rumpf-Blindzone: die Kameras sehen den eigenen Ruecken und die eigenen Beine.
# Halbachsen wie die Blindzone des Tiefengitters (spotsim.local_grid).
RUMPF_A_M = 0.55
RUMPF_B_M = 0.35

# Vorwaertskorridor, in dem ein Ueberhang die Fahrt betrifft.
KORRIDOR_VON_M = 0.4
KORRIDOR_BIS_M = 2.0
KORRIDOR_HALB_M = 0.45

# So viele Punkte muss eine Flaeche haben. Ein einzelnes Pixel ist Rauschen;
# dieselbe Regel wie beim Gitter -- Freiraum ist billig, ein Hindernis braucht
# Belege. 20 Punkte sind bei jedem zweiten Pixel eine Handflaeche.
MIN_PUNKTE = 20
SCHRITT = 2                      # jeder zweite Pixel je Achse


def punktwolke(tiefe, fx, fy, cx, cy, skala=1.0, schritt=1):
    """Nx3 im Kamerarahmen (x rechts, y unten, z aus der Linse).

    `skala` ist `ImageSource.depth_scale` (Rohwerte je Meter). Ein Rohwert 0
    heisst „nicht gemessen" und faellt heraus -- als 0 m stuende der Punkt
    mitten im Roboter.
    """
    bild = np.asarray(tiefe)[::schritt, ::schritt].astype(float)
    v, u = np.nonzero(bild)
    if v.size == 0:
        return np.zeros((0, 3))
    z = bild[v, u] / float(skala)
    u = u * schritt
    v = v * schritt
    return np.column_stack([(u - cx) * z / fx, (v - cy) * z / fy, z])


def umgerechnet(punkte, matrix):
    """Nx3 durch eine 4x4-Transformation (z. B. `body_tform_sensor`)."""
    punkte = np.asarray(punkte, dtype=float)
    if punkte.size == 0:
        return np.zeros((0, 3))
    matrix = np.asarray(matrix, dtype=float)
    return punkte @ matrix[:3, :3].T + matrix[:3, 3]


def aufgerichtet(punkte, roll, nick):
    """Roll und Nick herausdrehen -- das Band haengt an der Schwerkraft.

    Auf einer Rampe kippt der Koerperrahmen mit; ohne diese Drehung waere ein
    Stueck Boden voraus ploetzlich „ueber" dem Roboter. Nase hoch ist NEGATIV,
    dieselbe Konvention wie in `welt/hoehe.py`. Die Gierung bleibt: die
    x-Achse zeigt weiter nach vorn.
    """
    punkte = np.asarray(punkte, dtype=float)
    if punkte.size == 0:
        return np.zeros((0, 3))
    cr, sr = math.cos(roll), math.sin(roll)
    cn, sn = math.cos(nick), math.sin(nick)
    dreh_x = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    dreh_y = np.array([[cn, 0.0, sn], [0.0, 1.0, 0.0], [-sn, 0.0, cn]])
    return punkte @ (dreh_y @ dreh_x).T


def ueberhang(punkte, unten=KOPF_UNTEN_M, oben=KOPF_OBEN_M,
              rumpf_a=RUMPF_A_M, rumpf_b=RUMPF_B_M):
    """Die Punkte im Hoehenband ueber der Koerpermitte, ohne den eigenen Rumpf."""
    punkte = np.asarray(punkte, dtype=float)
    if punkte.size == 0:
        return np.zeros((0, 3))
    x, y, z = punkte[:, 0], punkte[:, 1], punkte[:, 2]
    im_band = (z > unten) & (z < oben)
    eigen = (x / rumpf_a) ** 2 + (y / rumpf_b) ** 2 < 1.0
    return punkte[im_band & ~eigen]


def kopfraum(punkte, von=KORRIDOR_VON_M, bis=KORRIDOR_BIS_M,
             halb=KORRIDOR_HALB_M, min_punkte=MIN_PUNKTE):
    """Abstand zum naechsten Ueberhang im Vorwaertskorridor -- oder None.

    None heisst „im Korridor haengt nichts", NICHT „keine Daten": ohne Bilder
    kommt man hier gar nicht erst her (`ueberhang_aus_bildern` wirft).
    """
    punkte = np.asarray(punkte, dtype=float)
    if punkte.size == 0:
        return None
    x, y = punkte[:, 0], punkte[:, 1]
    im_korridor = (x > von) & (x < bis) & (np.abs(y) < halb)
    if int(im_korridor.sum()) < min_punkte:
        return None
    return float(x[im_korridor].min())


# ------------------------------------------------------------- Protobuf-Ebene


def _lage(schnappschuss):
    """(roll, nick) des Koerpers gegen die Schwerkraft -- odom ist lotrecht."""
    from bosdyn.client import frame_helpers as fh

    try:
        pose = fh.get_a_tform_b(schnappschuss, fh.ODOM_FRAME_NAME, fh.BODY_FRAME_NAME)
    except Exception:
        return 0.0, 0.0
    if pose is None:
        return 0.0, 0.0
    return float(pose.rot.to_roll()), float(pose.rot.to_pitch())


def punkte_aus_bild(antwort, schritt=SCHRITT):
    """Nx3 im aufgerichteten Koerperrahmen aus einer Tiefen-`ImageResponse`.

    Intrinsik, Tiefenskala und Sensorrahmen kommen aus derselben Nachricht wie
    die Bytes; die Extrinsik aus ihrem Rahmenbaum. Nichts davon wird angenommen.
    """
    from bosdyn.api import image_pb2
    from bosdyn.client import frame_helpers as fh

    quelle, aufnahme = antwort.source, antwort.shot
    if quelle.image_type != image_pb2.ImageSource.IMAGE_TYPE_DEPTH:
        raise SpotlabError(
            f"'{quelle.name or 'unbenannt'}' ist kein Tiefenbild — der Kopfraum "
            f"braucht die Tiefenkameras (…_depth).")
    if aufnahme.image.pixel_format != image_pb2.Image.PIXEL_FORMAT_DEPTH_U16:
        raise SpotlabError(
            f"'{quelle.name}' kommt als {image_pb2.Image.PixelFormat.Name(aufnahme.image.pixel_format)}, "
            f"erwartet PIXEL_FORMAT_DEPTH_U16 — ein anderes Format falsch zu deuten "
            f"waere schlimmer als keine Messung.")
    roh = np.frombuffer(aufnahme.image.data, dtype="<u2")
    zeilen, spalten = aufnahme.image.rows, aufnahme.image.cols
    if roh.size != zeilen * spalten:
        raise SpotlabError(
            f"'{quelle.name}' hat {roh.size} Werte, erwartet {zeilen}×{spalten}.")
    innen = quelle.pinhole.intrinsics
    punkte = punktwolke(
        roh.reshape(zeilen, spalten),
        fx=innen.focal_length.x, fy=innen.focal_length.y,
        cx=innen.principal_point.x, cy=innen.principal_point.y,
        skala=quelle.depth_scale or 1.0, schritt=schritt,
    )
    rahmen = aufnahme.frame_name_image_sensor
    lage = fh.get_a_tform_b(aufnahme.transforms_snapshot, fh.BODY_FRAME_NAME, rahmen)
    if lage is None:
        raise SpotlabError(
            f"Im Rahmenbaum von '{quelle.name}' fehlt die Kante body→{rahmen}; "
            f"ohne Extrinsik ist die Punktwolke wertlos.")
    roll, nick = _lage(aufnahme.transforms_snapshot)
    return aufgerichtet(umgerechnet(punkte, np.asarray(lage.to_matrix())), roll, nick)


def ueberhang_aus_bildern(antworten, schritt=SCHRITT,
                          unten=KOPF_UNTEN_M, oben=KOPF_OBEN_M):
    """Die Ueberhangpunkte aus mehreren Tiefenbildern, im Koerperrahmen.

    Wirft, wenn kein einziges Tiefenbild dabei ist: fehlende Daten sind kein
    freier Weg, und der Aufrufer muss den Unterschied sehen koennen.
    """
    from bosdyn.api import image_pb2

    tiefenbilder = [a for a in antworten
                    if a.source.image_type == image_pb2.ImageSource.IMAGE_TYPE_DEPTH]
    if not tiefenbilder:
        raise SpotlabError(
            "Kein Tiefenbild dabei — ohne die Tiefenkameras gibt es keine Aussage "
            "ueber den Kopfraum. (Quellen: frontleft_depth, frontright_depth, …)")
    wolken = [ueberhang(punkte_aus_bild(a, schritt=schritt), unten=unten, oben=oben)
              for a in tiefenbilder]
    vorhanden = [w for w in wolken if len(w)]
    return np.vstack(vorhanden) if vorhanden else np.zeros((0, 3))
