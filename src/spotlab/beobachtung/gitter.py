"""LocalGrid-Mitschnitt während einer Beobachtungsfahrt.

Zweck: eine echte Karte über eine echte Trajektorie. Wer Karte und Pose
aufzeichnet, kann eine Entscheidungslogik danach am Schreibtisch gegen ECHTE
Sensordaten laufen lassen, beliebig oft und ohne dass der Roboter je kommandiert
wird. Die Ansicht „Umwelt" und `workshop/sonde.py` sind die Verbraucher hier;
`matura-spot` nutzt dasselbe Modul für sein Karten-Replay.

Umgezogen aus `matura-spot: spotsim/gitter_mitschnitt.py` (02.09.2026). Es war
dort bereits nach dem Vorbild von `beobachtung/bilder.py` gebaut — gleicher
Thread-Aufbau, gleiches Indexblatt — und gehört deshalb hierher.

**Gespeichert wird die serialisierte `LocalGridResponse`, nicht ein eigenes
Format.** Das Replay ruft damit exakt denselben `OccupancyMap.update_from_proto()`
auf wie die Simulation — die Auswertung kann also nicht dadurch abweichen, dass
irgendwo anders dekodiert wird. Der Preis (ein paar Kilobyte je Abtastung) ist
gegen diese Garantie keiner.

Eigener Thread neben Zustands- und Bildmitschnitt, aus demselben Grund wie dort:
ein hängender Abruf im WLAN darf die Hauptmessung nicht ausbremsen. Wirft nie
nach aussen — Fehler werden gezählt und sind über `zaehler()` sichtbar, denn ein
Mitschnitt, der still nichts aufnimmt, fällt erst auf, wenn der Roboter weg ist.

Kein Lease, kein Kommando: `LocalGridClient` ist ein reiner Lesedienst.
"""

import json
import threading
import time

TYPEN = ("obstacle_distance", "no_step")
VORSCHAU_MAX_M = 2.0    # ab hier ist im Vorschaubild alles gleich hell
ABRUF_FRIST_S = 5.0


def _sekunden(zeitstempel):
    return zeitstempel.seconds + zeitstempel.nanos * 1e-9


def _koerperpose(schnappschuss):
    """odom→body zum AUFNAHMEZEITPUNKT, oder None.

    Aus dem Schnappschuss des Gitters selbst, nicht aus einer benachbarten
    Zustandsabtastung: bei 0.5 m/s und 10 Hz Zustandstakt lägen sonst bis zu
    5 cm zwischen Karte und Pose. None heisst „nicht gemessen" — ein Ursprung
    wäre eine erfundene Pose und mittelte sich durch jede spätere Auswertung.
    """
    from bosdyn.client.frame_helpers import (
        BODY_FRAME_NAME,
        ODOM_FRAME_NAME,
        get_a_tform_b,
    )

    try:
        pose = get_a_tform_b(schnappschuss, ODOM_FRAME_NAME, BODY_FRAME_NAME)
    except Exception:
        return None
    if pose is None:
        return None
    return [pose.position.x, pose.position.y, pose.position.z,
            pose.rotation.w, pose.rotation.x, pose.rotation.y, pose.rotation.z]


def _typenblatt(resp):
    """Das Unveränderliche eines Gitter-Typs — einmal je Fahrt statt je Abtastung."""
    g = resp.local_grid
    return {
        "typ": g.local_grid_type_name,
        "zellgroesse_m": g.extent.cell_size,
        "zellen": [g.extent.num_cells_x, g.extent.num_cells_y],
        "kantenlaenge_m": [g.extent.num_cells_x * g.extent.cell_size,
                           g.extent.num_cells_y * g.extent.cell_size],
        "cell_format": int(g.cell_format),
        "encoding": int(g.encoding),
        "cell_value_scale": g.cell_value_scale,
        "cell_value_offset": g.cell_value_offset,
        "hat_unknown_cells": bool(g.unknown_cells),
        "frame_name_local_grid_data": g.frame_name_local_grid_data,
    }


class Gittermitschnitt:
    """Holt in festem Takt LocalGrids und legt sie neben die Aufzeichnung.

    Ablage im Laufverzeichnis:
        gitter/gitter.jsonl        ein Satz je Abtastung (Zeit, Pose, Datei)
        gitter/typen.json          das Unveränderliche je Typ
        gitter/<nummer>_<typ>.pb   serialisierte LocalGridResponse
        gitter/<nummer>_<typ>.png  Graustufen-Vorschau für die GUI
    """

    def __init__(self, client, verzeichnis, hz=2.0, typen=TYPEN):
        self._client = client
        self._dir = verzeichnis / "gitter"
        self._typen = tuple(typen)
        self._hz = float(hz)
        self._periode = 1.0 / self._hz if self._hz > 0 else 0.0
        self._stopp = threading.Event()
        self._thread = None
        self._sperre = threading.Lock()
        self._takt = 0
        self._gitter = 0
        self._bytes = 0
        self._fehler = 0
        self._letzter_fehler = None
        self._typenblatt = {}
        self._t0 = None
        self._index = None

    # ------------------------------------------------------------ Steuerung

    def start(self):
        if self._thread is not None or self._periode <= 0:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index = (self._dir / "gitter.jsonl").open("a", encoding="utf-8",
                                                        newline="\n")
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._schleife,
                                        name="spotlab-gitter", daemon=True)
        self._thread.start()

    def stop(self, timeout=ABRUF_FRIST_S + 2.0):
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._schreibe_typenblatt()
        if self._index is not None:
            self._index.close()
            self._index = None

    def zaehler(self):
        with self._sperre:
            dauer = (time.monotonic() - self._t0) if self._t0 else 0.0
            return {
                "saetze": self._takt,
                "gitter": self._gitter,
                "bytes": self._bytes,
                "fehler": self._fehler,
                "letzter_fehler": self._letzter_fehler,
                "hz_soll": self._hz,
                "hz_ist": round(self._takt / dauer, 2) if dauer > 0 else None,
            }

    # ----------------------------------------------------------- Innenleben

    def _schleife(self):
        naechste = time.monotonic()
        while not self._stopp.is_set():
            self._einmal()
            naechste += self._periode
            rest = naechste - time.monotonic()
            if rest > 0:
                self._stopp.wait(rest)
            else:
                # Nicht nachholen: ein langsamer Abruf soll den Takt strecken,
                # nicht einen Schwall gestauter Abrufe auslösen (dieselbe Regel
                # wie im Zustands- und Bildmitschnitt).
                naechste = time.monotonic()

    def _einmal(self):
        try:
            antworten = self._client.get_local_grids(list(self._typen))
        except Exception as fehler:
            with self._sperre:
                self._fehler += 1
                self._letzter_fehler = f"{type(fehler).__name__}: {fehler}"
            return
        with self._sperre:
            self._takt += 1
            nummer = self._takt
        for resp in antworten:
            try:
                self._lege_ab(nummer, resp)
            except Exception as fehler:          # ein Typ, nicht die ganze Fahrt
                with self._sperre:
                    self._fehler += 1
                    self._letzter_fehler = f"{type(fehler).__name__}: {fehler}"

    def _vorschau(self, pfad, resp):
        """Graustufen-PNG neben das Protobuf — die Anzeigetür für die GUI.

        Die GUI darf weder `bosdyn` noch `spotlab.backends` importieren und kann
        das Gitter deshalb nicht selbst dekodieren. Sie bekommt ein Bild, so wie
        sie Kamerabilder bekommt; das Protobuf bleibt die Wahrheit für Replay und
        Auswertung.

        Unbekannte Zellen werden schwarz, nicht „sehr frei" — eine erfundene
        Freiheit im Bild wäre derselbe Fehler wie eine erfundene Zahl in der API.
        """
        import numpy as np
        from PIL import Image

        from spotlab.backends.real.wahrnehmung import gitter_aus

        gitter = gitter_aus(resp)
        werte = np.clip(np.asarray(gitter.cells) / VORSCHAU_MAX_M, 0.0, 1.0)
        if gitter.known is not None:
            werte = np.where(gitter.known, werte, 0.0)
        Image.fromarray((werte * 255).astype(np.uint8), mode="L").save(pfad)

    def _lege_ab(self, nummer, resp):
        g = resp.local_grid
        typ = g.local_grid_type_name or "unbenannt"
        if typ not in self._typenblatt:
            self._typenblatt[typ] = _typenblatt(resp)
        roh = resp.SerializeToString()
        datei = f"{nummer:06d}_{typ}.pb"
        (self._dir / datei).write_bytes(roh)
        satz = {
            # Roboteruhr, nicht umgerechnet — dieselbe Zeitbasis wie
            # zustand.jsonl und kamera.jsonl, damit sich alles zusammenführen lässt.
            "t_robot": _sekunden(g.acquisition_time),
            "nummer": nummer,
            "typ": typ,
            "datei": datei,
            "bytes": len(roh),
            "pose": _koerperpose(g.transforms_snapshot),
        }
        try:
            self._vorschau(self._dir / f"{datei[:-3]}.png", resp)
        except Exception:
            # Die Vorschau ist Komfort, die Rohdaten sind die Messung. Ein
            # Fehler hier darf weder den Satz noch die Fahrt kosten.
            pass
        self._index.write(json.dumps(satz, ensure_ascii=False) + "\n")
        self._index.flush()          # nach jedem Satz: ein Absturz darf höchstens
                                     # die letzte Abtastung kosten, nicht die Fahrt
        with self._sperre:
            self._gitter += 1
            self._bytes += len(roh)

    def _schreibe_typenblatt(self):
        if not self._typenblatt:
            return
        try:
            (self._dir / "typen.json").write_text(
                json.dumps(list(self._typenblatt.values()), ensure_ascii=False,
                           indent=2),
                encoding="utf-8", newline="\n")
        except OSError:
            pass


def lies_mitschnitt(lauf_verzeichnis, typ="obstacle_distance"):
    """Aufgezeichnete Gitter in Aufnahmereihenfolge zurücklesen.

    Liefert (satz, LocalGridResponse) — das Protobuf ist bitgleich das, was der
    Roboter geschickt hat, und geht unverändert in `OccupancyMap.update_from_proto`.
    """
    from bosdyn.api import local_grid_pb2

    verzeichnis = lauf_verzeichnis / "gitter"
    index = verzeichnis / "gitter.jsonl"
    if not index.is_file():
        return
    for zeile in index.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        satz = json.loads(zeile)
        if typ is not None and satz.get("typ") != typ:
            continue
        pfad = verzeichnis / satz["datei"]
        if not pfad.is_file():
            continue
        resp = local_grid_pb2.LocalGridResponse()
        resp.ParseFromString(pfad.read_bytes())
        yield satz, resp
