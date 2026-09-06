"""Das MuJoCo-Backend: der 2D-Sim mit einem 3D-Körper, Kameras und Kollision.

`MujocoBackend` ERBT von `SimBackend` und überschreibt genau das, was 3D besser
kann. Kommandos, Ziele, Gangphase, Körperantwort und Aufzeichnung bleiben dort
— es gibt keine zweite Fassung dieser Logik. Neu ist der Körper: die Puppe aus
`matura-spot` (`spotsim.puppe`), der Menagerie-Spot, kinematisch gesetzt, mit
den Sensoren der Physik-Sim.

    2D-Sim                       MujocoBackend
    Kreis 0.35 m gegen Segmente  Kontakte der Mesh-Geometrie
    Abstandsgitter aus Geometrie Tiefenbilder → LocalGrid → derselbe Entpacker
                                 wie am echten Spot (`gitter_aus`)
    Tags: Reichweite+Sichtlinie  dazu Kamerablickfeld, Ausrichtung, Strahl
    keine Kameras                fünf Tiefen- und fünf Graukameras
    Füsse bei -hoehe             Fusspositionen aus der Kinematik

Das ist die einzige Datei unter `src/spotlab/`, die `spotsim` importiert
(`tests/test_naht_spotsim.py`). Fehlt das Paket, sagt der Fehler, was zu tun ist.

Wie der 2D-Sim ist auch das eine Wiedergabe gemessener Verläufe, keine Physik
der Beine: nichts fällt um, nichts rutscht. `lauf.json` sagt `backend: "mujoco"`,
der Hinweis steht im `verbunden`-Ereignis.

THREADS. Der Abtaster ruft `robot_state()` aus seinem Thread; das Schülerskript
ruft `local_grid()`, `images()`, `world_objects()` aus dem Hauptthread. Die
Puppe führt ein Lock um ihren Zustand. Gerendert (OpenGL) wird nur im Thread,
der das Backend gebaut hat — Tiefe, Graubilder und die Ansicht; der Abtaster
setzt nur Posen. Ein GL-Kontext, den zwei Threads benutzen, ist ein Absturz
ohne Traceback.
"""

import math
import os
import threading
import time
from pathlib import Path

from spotlab.backends.base import Capability, Tag, richtung
from spotlab.backends.sim import SimBackend
from spotlab.errors import SpotlabError
from spotlab.welt.kollision import MAX_SCHRITT_M
from spotlab.welt.wahrnehmung import TAG_REICHWEITE_M

PUPPE_FASSUNG = 2      # 2: weltfestes Gitter

# Geometrie der Räume in 3D. Die TOML-Vorlagen kennen keine Höhen — das sind
# ANNAHMEN: Wände zimmerhoch, Hindernisse tischhoch, Tags auf Kniehöhe (so
# steht es auch in `backends/base.py::richtung`).
WAND_HOEHE_M = 1.0
WAND_DICKE_M = 0.06
HINDERNIS_HOEHE_M = 0.75
TAG_HOEHE_M = 0.30

# Höchstens so oft wird die Ansicht gerendert; ein Bild kostet einige
# Millisekunden, und die GUI liest ohnehin nur viermal je Sekunde.
ANSICHT_TAKT_S = 0.1
ANSICHT_BREITE, ANSICHT_HOEHE = 640, 360

HINWEIS = (
    "Dieser Lauf ist NICHT am Roboter erprobt. Das MuJoCo-Backend spielt die am "
    "12.08.2026 gemessenen Gangarten und die am 02.09.2026 gemessene Antwort auf "
    "Kommandos auf dem Menagerie-Spot ab — kinematisch gesetzt, keine Physik der "
    "Beine: nichts fällt um, nichts rutscht. Kameras, Hindernisgitter und "
    "Kollision kommen aus der 3D-Geometrie."
)


def _puppe_laden():
    try:
        from spotsim import puppe, spot_asset_available
    except ImportError as fehler:
        raise SpotlabError(
            "Das MuJoCo-Backend braucht das Paket `spotsim` aus matura-spot: "
            "pip install -e ../matura-spot  und  pip install -e .[sim]"
        ) from fehler
    if getattr(puppe, "FASSUNG", 0) != PUPPE_FASSUNG:
        raise SpotlabError(
            f"spotsim.puppe hat Fassung {getattr(puppe, 'FASSUNG', '?')}, spotlab erwartet "
            f"{PUPPE_FASSUNG}. Beide Repos auf denselben Stand bringen."
        )
    if not spot_asset_available():
        raise SpotlabError(
            "Das Menagerie-Modell des Spot fehlt: in matura-spot "
            "`python scripts/fetch_menagerie.py` ausführen."
        )
    return puppe


def welt_aus_raum(raum, puppe):
    """Ein `Raum` (Segmente, Rechtecke, Tags) als `puppe.Welt` (Quader, Tags).

    Wandsegmente werden zu dünnen Quadern, die Rechtecke der Hindernisse zu
    tischhohen Kästen, Tags zu Marken auf Kniehöhe mit der Blickrichtung aus
    der Vorlage (Grad → Bogenmass, wie überall an der Naht zu `welt/`).
    """
    if raum is None:
        return puppe.Welt()
    quader = []
    for i, (x1, y1, x2, y2) in enumerate(raum.waende):
        laenge = math.hypot(x2 - x1, y2 - y1)
        if laenge <= 0:
            continue
        # Achsparallel wie alle Vorlagen; eine schräge Wand bekäme hier eine
        # Drehung — die Quader der Puppe sind achsparallel, deshalb wird sie
        # als Kasten über ihrer Bounding-Box gebaut (bewusst grob).
        hx = max(abs(x2 - x1) / 2, WAND_DICKE_M / 2)
        hy = max(abs(y2 - y1) / 2, WAND_DICKE_M / 2)
        quader.append(puppe.Quader(
            f"wand_{i}", (x1 + x2) / 2, (y1 + y2) / 2, WAND_HOEHE_M / 2, hx, hy, WAND_HOEHE_M / 2,
        ))
    for h in raum.hindernisse:
        x, y, breite, hoehe = h.rechteck
        quader.append(puppe.Quader(
            h.name, x + breite / 2, y + hoehe / 2, HINDERNIS_HOEHE_M / 2,
            breite / 2, hoehe / 2, HINDERNIS_HOEHE_M / 2,
        ))
    tags = tuple(
        puppe.TagMarke(t.id, t.x, t.y, TAG_HOEHE_M, math.radians(t.grad)) for t in raum.tags
    )
    return puppe.Welt(quader=tuple(quader), tags=tags)


class MujocoBackend(SimBackend):
    """Bewegt sich nach Gangkennlinie und Antwortmodell — in einem 3D-Zimmer."""

    def __init__(self, recorder=None, jetzt=time.time, modell=None, raum=None,
                 start=None, antwort=None, ansicht_ziel=None):
        super().__init__(recorder=recorder, jetzt=jetzt, modell=modell,
                         raum=raum, start=start, antwort=antwort)
        puppe = _puppe_laden()
        self.puppe = puppe.SpotPuppe(welt_aus_raum(raum, puppe))
        self._fassung = puppe.FASSUNG
        self._thread = threading.get_ident()
        self._ansicht_ziel = Path(ansicht_ziel) if ansicht_ziel else None
        self._ansicht_zuletzt = -math.inf
        self._synchronisiere()

    # ------------------------------------------------------------- Auskunft

    def capabilities(self):
        # Die Puppe hat immer Kameras und Geometrie — auch ohne Raum sieht sie
        # den Boden. Ein leerer Raum liefert leere Tags, das ist die Wahrheit.
        return (Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
                | Capability.DEPTH_CAMERAS | Capability.GRAY_CAMERAS
                | Capability.WORLD_OBJECTS | Capability.LOCAL_GRID)

    @staticmethod
    def hinweis_zur_gueltigkeit():
        return HINWEIS

    def bericht(self):
        bericht = super().bericht()
        bericht["hinweis"] = HINWEIS
        winkel = self._modell.gelenke(0.0, 0.0, 0.0)
        bericht["puppe"] = {
            "fassung": self._fassung,
            "modell": "mujoco_menagerie/boston_dynamics_spot",
            # Die Höhe aus der Kinematik neben der gemessenen: ihre Differenz
            # sagt, wie gut das Modell zum Schul-Spot passt (06.09.2026: 2-8 mm).
            "standhoehe_kinematik_m": round(self.puppe.standhoehe(winkel), 4),
            "standhoehe_gemessen_m": round(self._modell.hoehe_m, 4),
            "annahmen": {
                "wand_hoehe_m": WAND_HOEHE_M, "hindernis_hoehe_m": HINDERNIS_HOEHE_M,
                "tag_hoehe_m": TAG_HOEHE_M, "tag_reichweite_m": TAG_REICHWEITE_M,
            },
        }
        return bericht

    # ---------------------------------------------------------- Bewegung

    def _winkel(self):
        vx, vy, wz = self._soll
        return self._modell.gelenke(math.hypot(vx, vy), wz, self._phase)

    def _synchronisiere(self):
        """Die Puppe auf den Stand des 2D-Sim bringen: Pose und Winkel."""
        x, y, yaw = self._pose
        self.puppe.setze(x, y, yaw, self._winkel())

    def _fortschreiben(self):
        super()._fortschreiben()
        self._synchronisiere()
        self._ansicht_schreiben()

    def _bewege_gegen_welt(self, von, nach):
        """An Wänden und Kisten bleibt Spot stehen — an seiner echten Geometrie.

        In Teilschritten von höchstens MAX_SCHRITT_M wie `welt/kollision.bewege`,
        damit die Zusicherung nicht an der Abfragehäufigkeit hängt. Die DREHUNG
        wird immer übernommen (dieselbe Regel wie in 2D). Gemeldet wird die
        Flanke, nicht jeder Takt.
        """
        winkel = self._winkel()
        strecke = math.hypot(nach[0] - von[0], nach[1] - von[1])
        schritte = max(1, math.ceil(strecke / MAX_SCHRITT_M))
        frei, getroffen = (von[0], von[1], nach[2]), None
        for i in range(1, schritte + 1):
            anteil = i / schritte
            probe = (von[0] + (nach[0] - von[0]) * anteil,
                     von[1] + (nach[1] - von[1]) * anteil, nach[2])
            self.puppe.setze(probe[0], probe[1], probe[2], winkel)
            beruehrt = self.puppe.kollisionen()
            if beruehrt:
                getroffen = beruehrt[0]
                break
            frei = probe
        if getroffen is None:
            self._angestossen = False
            return frei
        # Wände heissen in der Vorlage nicht; die Puppe nennt sie `wand_<i>`.
        # Für das Protokoll ist das dieselbe Aussage wie in 2D: "Wand".
        name = "Wand" if getroffen.startswith("wand_") else getroffen
        if not self._angestossen:
            self._angestossen = True
            if self._recorder is not None:
                self._recorder.event(
                    "angestossen", x=round(frei[0], 3), y=round(frei[1], 3), hindernis=name,
                )
        return frei

    # ---------------------------------------------------------- Wahrnehmung

    def world_objects(self, kinds=None):
        if kinds is not None and "apriltag" not in kinds:
            return []
        self._fortschreiben()
        gefunden = []
        for marke, (dx, dy) in self.puppe.sichtbare_tags(TAG_REICHWEITE_M):
            peilung, distanz = richtung(dx, dy)
            gefunden.append(Tag(
                name=f"world_obj_apriltag_{marke.id:03d}", kind="apriltag",
                bearing=peilung, distance=distanz, world_xy=(marke.x, marke.y),
                time=self._jetzt(), id=marke.id, filtered=False,
            ))
        return gefunden

    def local_grid(self):
        """Aus den fünf Tiefenbildern — durch denselben Entpacker wie am Roboter.

        Das Gitter kommt weltfest (spotsim ab Puppe-Fassung 2, RESEARCH DECISION
        06.09.2026 in matura-spot), so wie der echte Dienst es liefert und wie
        `ObstacleGrid` rechnet. Nichts wird umgetastet.
        """
        from spotlab.backends.real.wahrnehmung import gitter_aus

        self._fortschreiben()
        return gitter_aus(self.puppe.local_grid("obstacle_distance"))

    def image_sources(self):
        from spotsim.sensors import CAMERAS

        return [f"{n}_depth" for n in CAMERAS] + [f"{n}_fisheye_image" for n in CAMERAS]

    def images(self, sources):
        self._fortschreiben()
        antworten = []
        for quelle in sources:
            if quelle.endswith("_depth"):
                antworten.append(self.puppe.depth_image(quelle[: -len("_depth")]))
            elif quelle.endswith("_fisheye_image"):
                antworten.append(self.puppe.gray_image(quelle[: -len("_fisheye_image")]))
            else:
                raise SpotlabError(
                    f"Unbekannte Bildquelle '{quelle}'. Vorhanden: "
                    + ", ".join(self.image_sources())
                )
        return antworten

    def robot_state(self):
        """Kopf (Akku, Motoren, Verhalten) vom 2D-Sim, Kinematik von der Puppe.

        Die Puppe liefert Gelenke aus qpos (dieselben Winkel), Fusspositionen
        aus der Kinematik und den Frame-Baum samt Kamera-Frames. Kontakte und
        Tempo kommen vom Gangmodell — die Puppe hat keine Physik.
        """
        zustand = super().robot_state()          # ruft _fortschreiben, synchronisiert
        vx, vy, wz = self._soll if self._powered and not self._sitzt else (0.0, 0.0, 0.0)
        steht_still = math.hypot(vx, vy) <= 1e-6 and abs(wz) <= 1e-6
        kontakte = ([True] * 4 if steht_still
                    else self._modell.fusskontakte(math.hypot(vx, vy), wz, self._phase))
        puppe_zustand = self.puppe.robot_state(
            fusskontakte=dict(zip(("fl", "fr", "hl", "hr"), kontakte)), v_body=(vx, vy, wz),
        )
        zustand.kinematic_state.CopyFrom(puppe_zustand.kinematic_state)
        zustand.kinematic_state.acquisition_timestamp.seconds = int(self._t)
        zustand.kinematic_state.acquisition_timestamp.nanos = int((self._t % 1) * 1e9)
        del zustand.foot_state[:]
        for fuss in puppe_zustand.foot_state:
            zustand.foot_state.add().CopyFrom(fuss)
        return zustand

    def frame_tree_snapshot(self):
        self._synchronisiere()
        return self.puppe.frame_tree_snapshot()

    # -------------------------------------------------------------- Ansicht

    def _ansicht_schreiben(self):
        """Ein Bild der Zimmeransicht, atomar, höchstens zehnmal je Sekunde.

        Nur im Thread, der das Backend gebaut hat (siehe Kopf der Datei).
        Eine Datei, die ersetzt wird — kein Strom: ein Zehn-Minuten-Lauf
        hinterliesse sonst 180 MB, und die GUI will nur das neueste Bild.
        """
        if self._ansicht_ziel is None or threading.get_ident() != self._thread:
            return
        jetzt = self._jetzt()
        if jetzt - self._ansicht_zuletzt < ANSICHT_TAKT_S:
            return
        self._ansicht_zuletzt = jetzt
        try:
            from PIL import Image

            bild = self.puppe.ansicht(ANSICHT_BREITE, ANSICHT_HOEHE)
            temporaer = self._ansicht_ziel.with_suffix(".tmp")
            Image.fromarray(bild).save(temporaer, format="JPEG", quality=82)
            os.replace(temporaer, self._ansicht_ziel)
        except Exception as fehler:          # die Ansicht darf den Lauf nie anhalten
            from spotlab import protokoll

            protokoll.notiere(f"Ansicht nicht geschrieben: {fehler}")
            self._ansicht_ziel = None


# ======================================================================
# Das Video eines Laufs -- nachträglich aus der Aufzeichnung gerendert.
#
# Nicht während des Laufs: `zustand.jsonl` trägt Pose und zwölf Gelenke mit
# 10 Hz. Daraus wird auf `fps` interpoliert und auf der Puppe abgespielt. Das
# kostet den Lauf nichts, ist flüssig — und es funktioniert für alte Läufe,
# für 2D-Läufe (die bekommen nachträglich ihr 3D-Bild) und für ECHTE Läufe:
# die aufgezeichneten Gelenkwinkel des Schul-Spot im Menagerie-Modell.
# ======================================================================

FILM_DATEI = "film.mp4"
FILM_FPS = 30


def _zeilen_jsonl(pfad):
    import json

    saetze = []
    if not pfad.is_file():
        return saetze
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue                          # halbe letzte Zeile
    return saetze


def _interpoliere_pose(a, b, anteil):
    """(x, y, yaw) zwischen zwei Posen; das Gieren auf dem kürzeren Bogen."""
    dyaw = (b[2] - a[2] + math.pi) % (2 * math.pi) - math.pi
    yaw = a[2] + dyaw * anteil
    yaw = (yaw + math.pi) % (2 * math.pi) - math.pi
    return (a[0] + (b[0] - a[0]) * anteil, a[1] + (b[1] - a[1]) * anteil, yaw)


def _raum_des_laufs(lauf_dir):
    """(Name, Raum) aus dem `verbunden`-Ereignis -- oder (None, None).

    Eigene Räume liegen unter <arbeitsordner>/raeume; der Lauf liegt unter
    <arbeitsordner>/<projekt>/runs/<id>. Ist er woanders, bleiben die
    mitgelieferten Vorlagen.
    """
    from spotlab.welt.raum import raum_laden

    name = None
    for satz in _zeilen_jsonl(Path(lauf_dir) / "ereignisse.jsonl"):
        if satz.get("art") == "verbunden":
            name = (satz.get("daten") or {}).get("raum")
            break
    if not name:
        return None, None
    arbeitsordner = Path(lauf_dir).resolve().parents[2] if len(Path(lauf_dir).resolve().parents) > 2 else None
    try:
        return name, raum_laden(name, workspace=arbeitsordner)
    except SpotlabError:
        try:
            return name, raum_laden(name)
        except SpotlabError:
            return name, None


def _bilder_aus_lauf(lauf_dir, fps=FILM_FPS):
    """(t, (x, y, yaw), gelenke) je Bild — auf `fps` interpoliert."""
    from spotlab.kalibrierung.modell import lade_modell

    proben = []
    for satz in _zeilen_jsonl(Path(lauf_dir) / "zustand.jsonl"):
        daten = satz.get("daten") or {}
        pose = daten.get("pose")
        if not pose or len(pose) < 3:
            continue
        gelenke = daten.get("joints") or {}
        winkel = {name: float(g.get("position", 0.0)) for name, g in gelenke.items()
                  if isinstance(g, dict)}
        proben.append((float(satz["t"]), (float(pose[0]), float(pose[1]), float(pose[2])),
                       winkel if len(winkel) == 12 else None))
    if len(proben) < 2:
        raise SpotlabError(
            f"{Path(lauf_dir).name}: zustand.jsonl hat {len(proben)} brauchbare Proben -- "
            "für ein Video braucht es mindestens zwei. Ist der Lauf durchgelaufen?"
        )
    # Ohne Gelenke (alter Lauf, Trockenlauf): die Standhaltung der Kennlinie.
    ruhe = lade_modell().gelenke(0.0, 0.0, 0.0)
    letzte = ruhe
    gefuellt = []
    for t, pose, winkel in proben:
        if winkel is not None:
            letzte = winkel
        gefuellt.append((t, pose, letzte))

    t0, t_ende = gefuellt[0][0], gefuellt[-1][0]
    k, i = 0, 0
    while True:
        t = t0 + k / fps
        if t > t_ende + 1e-9:
            break
        while i + 1 < len(gefuellt) - 1 and gefuellt[i + 1][0] <= t:
            i += 1
        ta, pa, ga = gefuellt[i]
        tb, pb, gb = gefuellt[i + 1]
        anteil = 0.0 if tb <= ta else min(1.0, max(0.0, (t - ta) / (tb - ta)))
        pose = _interpoliere_pose(pa, pb, anteil)
        gelenke = {name: ga[name] + (gb[name] - ga[name]) * anteil for name in ga}
        yield t, pose, gelenke
        k += 1


def film_aus_lauf(lauf_dir, ziel=None, fps=FILM_FPS, breite=ANSICHT_BREITE,
                  hoehe=ANSICHT_HOEHE, fortschritt=None):
    """Den Lauf als MP4 rendern. Rückgabe {pfad, bilder, dauer_s, raum}.

    `fortschritt(bild, gesamt)` wird alle 30 Bilder gerufen -- für die
    Kommandozeile und die GUI, die den Unterprozess mitliest.
    """
    try:
        import imageio.v2 as imageio
    except ImportError as fehler:
        raise SpotlabError(
            "Für das Video fehlt imageio mit ffmpeg: pip install -e .[sim]"
        ) from fehler

    lauf_dir = Path(lauf_dir)
    ziel = Path(ziel) if ziel else lauf_dir / FILM_DATEI
    bilder = list(_bilder_aus_lauf(lauf_dir, fps))
    name, raum = _raum_des_laufs(lauf_dir)
    puppe = _puppe_laden()
    figur = puppe.SpotPuppe(welt_aus_raum(raum, puppe))

    temporaer = ziel.with_suffix(".tmp.mp4")
    # macro_block_size=1: sonst skaliert ffmpeg 360 Zeilen auf 368 hoch, mit
    # einer Warnung, die niemand liest. 640x360 ist gerade, das genügt libx264.
    with imageio.get_writer(str(temporaer), fps=fps, codec="libx264", quality=8,
                            macro_block_size=1, pixelformat="yuv420p") as schreiber:
        for nummer, (_t, (x, y, yaw), gelenke) in enumerate(bilder):
            figur.setze(x, y, yaw, gelenke)
            schreiber.append_data(figur.ansicht(breite, hoehe))
            if fortschritt is not None and nummer % 30 == 0:
                fortschritt(nummer, len(bilder))
    os.replace(temporaer, ziel)
    return {"pfad": ziel, "bilder": len(bilder), "dauer_s": round(len(bilder) / fps, 2),
            "raum": name}
