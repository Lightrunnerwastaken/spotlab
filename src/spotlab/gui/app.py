"""Das Hauptfenster: Kopfleiste, Seitenleiste, vier Ansichten.

Hier wird verdrahtet und sonst nichts. Die einzige Stelle im Programm, die Qt
nach dem Farbschema fragt, ist system_ist_dunkel() — theme.py bleibt dadurch
Qt-frei und prüfbar.
"""

import math
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spotlab import ENV_RAUM, ENV_RAUM_START
from spotlab.config import load_config, save_config
from spotlab.errors import SpotlabError
from spotlab.gui.editor.view import EditorView, verfuegbare_backends
from spotlab.gui.header import Header
from spotlab.gui.raumeditor import RaumeditorView
from spotlab.gui.sidebar import Sidebar
from spotlab.gui.theme import palette_fuer, stylesheet
from spotlab.gui.uebungsfenster import Uebungsfenster
from spotlab.gui.views.anbindungen import AnbindungenView
from spotlab.gui.views.checkup import CheckupView
from spotlab.gui.views.live import LiveView
from spotlab.gui.views.maps import MapsView
from spotlab.gui.views.projects import ProjectsView
from spotlab.gui.views.runs import RunsView
from spotlab.gui.views.umwelt import UmweltView
from spotlab.gui.watcher import RunWatcher
from spotlab.gui.workers import DoctorWorker, OutputReader
from spotlab.record.read import read_run
from spotlab.workshop.control import ist_aktiv


def system_ist_dunkel(app=None):
    """Die einzige Stelle, die Qt nach dem Farbschema fragt."""
    app = app or QApplication.instance()
    if app is None:
        return True
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return True


class MainWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("spotlab")
        self.resize(1080, 720)

        try:
            self._config = load_config()
        except SpotlabError:
            self._config = None

        self._palette = palette_fuer(system_ist_dunkel())
        # Woher der letzte Start kam. Steuert nur eines: ob _lauf_begonnen die
        # Ansicht wechselt.
        self._start_aus = None
        # Genau EIN Lauf ist der, auf den Stopp und NOT-AUS zeigen. Weitere
        # warten, statt ihn zu verdrängen — sonst zeigt der Knopf auf einen
        # anderen Prozess als den, der gerade den Roboter hält.
        self._aktiver_lauf = None
        self._wartende_laeufe = []
        # Das Turtle-Fenster fuer virtuelle Laeufe. Erst beim ersten solchen
        # Lauf gebaut: ein Fenster, das bei jedem Start aufspringt, wird
        # weggeklickt und danach ignoriert.
        self.uebungsfenster = None
        self._film = None                  # laufender `spotlab film`-Unterprozess

        self.kopf = Header()
        self.leiste = Sidebar()
        self.statuszeile = QLabel("")
        self.statuszeile.setObjectName("Gedaempft")

        self.ansichten = {
            "projekte": ProjectsView(
                editor_command=self._config.editor_command if self._config else "code"
            ),
            "code": EditorView(self._palette),
            "live": LiveView(),
            "laeufe": RunsView(self._palette),
            "karten": MapsView(self._palette),
            "umwelt": UmweltView(),
            "raumeditor": RaumeditorView(self._palette),
            "anbindungen": AnbindungenView(self._palette),
            "spot": CheckupView(),
        }
        self.stapel = QStackedWidget()
        for schluessel in (
            "projekte", "code", "live", "laeufe", "karten", "umwelt",
            "raumeditor", "anbindungen", "spot",
        ):
            self.stapel.addWidget(self.ansichten[schluessel])

        unten = QHBoxLayout()
        unten.setContentsMargins(0, 0, 0, 0)
        unten.addWidget(self.leiste)
        unten.addWidget(self.stapel, 1)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(self.kopf)
        aussen.addLayout(unten, 1)
        aussen.addWidget(self.statuszeile)

        self._watcher = None
        self._leser = None
        self._doctor = None
        self._verdrahte()
        self._setze_arbeitsordner(self._config.workspace if self._config else "")
        self.kopf.zeige_config(self._config)
        self.ansichten["karten"].setze_config(self._config)

        if self._config is None:
            self._wechsle("spot")
            self.leiste.waehle("spot")

    # ------------------------------------------------------------- Aufbau

    def _verdrahte(self):
        self.leiste.gewaehlt.connect(self._wechsle)
        self.kopf.notaus.connect(lambda: self.ansichten["live"].notaus())
        self.ansichten["live"].meldung.connect(self._melde)
        self.ansichten["projekte"].lauf_gestartet.connect(self._lauf_gestartet)
        self.ansichten["projekte"].meldung.connect(self._melde)
        self.ansichten["projekte"].arbeitsordner_geaendert.connect(self._merke_arbeitsordner)
        self.ansichten["spot"].config_gespeichert.connect(self._config_gespeichert)
        self.ansichten["raumeditor"].meldung.connect(self._melde)
        self.ansichten["raumeditor"].config_gespeichert.connect(self._config_gespeichert)
        # Delegation, kein zweiter Startweg: genau EIN Lauf ist der, auf den
        # Stopp und NOT-AUS zeigen.
        # An den EDITOR, nicht an "Projekte": der Knopf soll die offene Datei
        # starten. Ueber "Projekte" haette er stillschweigend nichts getan,
        # solange dort nichts ausgewaehlt war.
        self.ansichten["raumeditor"].start_gewuenscht.connect(self._starte_virtuell)
        self.ansichten["raumeditor"].fahrt_gewuenscht.connect(self._starte_fahrt)
        self._fahrt_erwartet = False
        # Der Knopf im Raumeditor spiegelt den Laufzustand des Editors, statt
        # ihn ein zweites Mal zu fuehren. Die Methode gab es schon; sie war
        # nirgends verbunden und der Knopf blieb deshalb auf „Starten" stehen.
        self.ansichten["code"].laeuft_geaendert.connect(
            self.ansichten["raumeditor"].setze_laeuft
        )
        self.ansichten["spot"].pruefung_angefordert.connect(self._pruefe)
        self.ansichten["karten"].meldung.connect(self._melde)
        self.ansichten["karten"].aktive_karte_gewaehlt.connect(self._merke_aktive_karte)
        self.ansichten["code"].zusatz_umgebung = self._umgebung_fuer_lauf
        self.ansichten["laeufe"].video_gewuenscht.connect(self._starte_film)
        self.ansichten["code"].lauf_gestartet.connect(self._lauf_aus_code)
        self.ansichten["code"].meldung.connect(self._melde)
        self.ansichten["projekte"].projekt_oeffnen.connect(self._oeffne_in_code)
        self.ansichten["anbindungen"].meldung.connect(self._melde)
        self.ansichten["anbindungen"].lauf_gestartet.connect(self._lauf_aus_anbindungen)
        self.ansichten["anbindungen"].roboterlauf.connect(self._roboterlauf_aus_anbindungen)
        # An dieselbe LiveView, nicht an eine eigene Stopp-Funktion: der
        # freundliche Stopp haengt am Lauf-Verzeichnis, das nur sie kennt.
        self.ansichten["anbindungen"].stopp_gewuenscht.connect(
            self.ansichten["live"].stoppe
        )
        self._verdrahte_code_stopp()

    def _verdrahte_code_stopp(self):
        """Eigene Methode, damit Tests nach dem Austausch von stoppe() neu verdrahten.

        Der Stopp-Knopf im Editor ruft NICHT eine zweite Kopie der Logik: der
        freundliche Stopp hängt am Lauf-Verzeichnis, das nur die Live-Ansicht
        vom Watcher bekommt. Delegation heisst dasselbe Objekt mit demselben
        Zustand — und damit garantiert dasselbe Verhalten.
        """
        self.ansichten["code"].stopp_gewuenscht.connect(
            lambda: self.ansichten["live"].stoppe()
        )

    def _setze_arbeitsordner(self, pfad):
        if pfad:
            # Die Beispiele liegen als Projekt „Beispiele" im Arbeitsordner --
            # immer da, immer in der Liste. Kopiert wird nur, was fehlt.
            try:
                from spotlab.workshop.beispiele import bereitstellen

                bereitstellen(pfad)
            except OSError as fehler:
                self._melde(f"Beispiele konnten nicht angelegt werden: {fehler}")
        self.ansichten["projekte"].setze_arbeitsordner(pfad or None)
        self.ansichten["code"].setze_arbeitsordner(pfad or None)
        self.ansichten["anbindungen"].setze_arbeitsordner(pfad or None)
        self.ansichten["laeufe"].setze_arbeitsordner(pfad or None)
        self.ansichten["karten"].setze_arbeitsordner(pfad or None)
        self.ansichten["umwelt"].setze_arbeitsordner(pfad or None)
        self.ansichten["raumeditor"].setze_arbeitsordner(pfad or None)
        if self.uebungsfenster is not None:
            self.uebungsfenster.setze_arbeitsordner(pfad or None)
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if not pfad:
            return
        self._watcher = RunWatcher(Path(pfad))
        self._watcher.lauf_begonnen.connect(self._lauf_begonnen)
        self._watcher.zustand.connect(self._zustand)
        self._watcher.ereignis.connect(self._ereignis)
        self._watcher.bild.connect(self.ansichten["live"].zeige_bild)
        self._watcher.ansicht.connect(self._ansicht)
        self._watcher.lauf_beendet.connect(self._lauf_beendet)
        self._watcher.fehler.connect(self._melde)
        self._watcher.start()

    # ------------------------------------------------------------- Reaktionen

    def _wechsle(self, schluessel):
        self.stapel.setCurrentWidget(self.ansichten[schluessel])

    def _melde(self, text):
        self.statuszeile.setText(text)

    def _merke_arbeitsordner(self, pfad):
        self._setze_arbeitsordner(pfad)
        if self._config is None:
            return
        self._config = replace(self._config, workspace=pfad)
        save_config(self._config)

    def _merke_aktive_karte(self, name):
        if self._config is None:
            self._melde("Der Spot ist noch nicht eingerichtet — Ansicht 'Spot'.")
            return
        self._config = replace(self._config, active_map=name)
        save_config(self._config)
        self.ansichten["karten"].setze_config(self._config)

    def _config_gespeichert(self, cfg):
        self._config = cfg
        self.kopf.zeige_config(cfg)
        self.ansichten["karten"].setze_config(cfg)

    def _pruefe(self):
        self.ansichten["spot"].pruefen_knopf.setEnabled(False)
        self.ansichten["spot"].pruefen_knopf.setText("Prüfe…")
        self._doctor = DoctorWorker(self)
        self._doctor.fertig.connect(self._pruefung_fertig)
        self._doctor.fehler.connect(self._melde)
        self._doctor.finished.connect(self._pruefung_aufraeumen)
        self._doctor.start()

    def _pruefung_fertig(self, pruefungen):
        self.ansichten["spot"].zeige_pruefung(pruefungen)
        self.kopf.zeige_pruefung(pruefungen)

    def _pruefung_aufraeumen(self):
        self.ansichten["spot"].pruefen_knopf.setEnabled(True)
        self.ansichten["spot"].pruefen_knopf.setText("Spot prüfen")

    def _starte_leser(self, prozess):
        """EIN Leser, zwei Senken.

        Ein zweiter OutputReader auf derselben Pipe teilte sich die Zeilen
        zufällig mit dem ersten. Neue Ansichten hängen sich hier als weitere
        Senke an, nie mit einem eigenen Leser an den Prozess.
        """
        self._leser = OutputReader(prozess, self)
        self._leser.zeile.connect(self.ansichten["live"].zeige_ausgabe)
        self._leser.zeile.connect(self.ansichten["code"].zeige_ausgabe)
        self._leser.zeile.connect(self._zeile_ins_uebungsfenster)
        # Der Leser weiss als Erster, dass der Prozess weg ist. Ein Skript mit
        # Syntaxfehler stirbt, bevor es ein Lauf-Verzeichnis anlegt — der
        # Watcher meldet dann nie ein Ende, und der Stopp-Knopf im Editor bliebe
        # fuer immer haengen.
        self._leser.ende.connect(lambda _code: self.ansichten["code"].pruefe_lauf_lebt())
        self._leser.start()

    def _lauf_gestartet(self, prozess, skript):
        self._start_aus = "projekte"
        self._wechsle("live")
        self.leiste.waehle("live")
        self._starte_leser(prozess)

    def _lauf_aus_code(self, prozess, skript):
        # Kein Ansichtswechsel: wer aus „Code" startet, will dort bleiben.
        self._start_aus = "code"
        if self.ansichten["code"].gewaehltes_backend() in ("sim", "mujoco"):
            self._oeffne_uebungsfenster(Path(skript).name)
        self._starte_leser(prozess)

    # ------------------------------------------------------- Uebungsfenster

    def _umgebung_fuer_lauf(self):
        """Raum und Startpose fuer einen virtuellen Lauf.

        Direkt aus der Ansicht, NICHT ueber die Konfigurationsdatei: die bekam
        den Raum erst beim Klick in die Zeichnung. Wer nur startete, fuhr
        deshalb in gar keinem Raum -- Start (0, 0), quer durch die Waende
        (Lauf vom 04.09.2026 mit `"raum": null`). Und ein Laptop ohne
        eingerichteten Spot hat ueberhaupt keine Konfiguration.

        Und der Raum muss so auf der Platte liegen, wie die Ansicht ihn zeigt:
        `SPOTLAB_RAUM` ist ein Name. Der Start aus „Code" ging bis zum
        06.09.2026 am Raumeditor-Knopf vorbei, der vorher speichert -- die
        rekonstruierten Katakomben waren namenlos, der Name ging leer mit,
        MuJoCo fuhr auf leerem Boden, und das Uebungsfenster zeigte trotzdem
        die Waende. Ein `SpotlabError` hier verweigert den Start; der Editor
        faengt ihn wie einen Startfehler und zeigt den Grund.
        """
        if self.ansichten["code"].gewaehltes_backend() not in ("sim", "mujoco"):
            return {}
        ansicht = self.ansichten["raumeditor"]
        grund = ansicht.bereit_fuer_lauf()
        if grund:
            raise SpotlabError(grund)
        umgebung = {ENV_RAUM: ansicht.raumname()}
        pose = ansicht.startpose()
        if pose:
            umgebung[ENV_RAUM_START] = f"{pose[0]:.2f},{pose[1]:.2f},{pose[2]:.1f}"
        return umgebung

    def _starte_virtuell(self):
        """Der Knopf im Raumeditor ERZWINGT das virtuelle Backend.

        Er erbt NICHT, was im Editor eingestellt ist: sonst startete ein Knopf
        im Raumeditor den echten Spot. Gestartet wird trotzdem
        ueber den Editor -- genau EIN Lauf ist der, auf den Stopp und NOT-AUS
        zeigen.
        """
        # Nur beim START umstellen: laeuft schon etwas, heisst derselbe Knopf
        # „Stopp", und die Wahl im Editor darf dabei nicht umspringen.
        if not self.ansichten["code"].laeuft():
            # 3D, wenn es auf diesem Laptop laeuft, sonst die Zeichnung.
            namen = [name for _, name in verfuegbare_backends()]
            self.ansichten["code"].setze_backend("mujoco" if "mujoco" in namen else "sim")
        self.ansichten["code"].starte_aktuelles()

    def _starte_fahrt(self):
        """Der Fahrmodus: das mitgelieferte `fahren.py` als virtueller Lauf, W A S D Q E
        im Uebungsfenster. Derselbe Startweg und dieselben Regeln wie „Starten"."""
        from spotlab.workshop import fahren
        from spotlab.workshop.beispiele import bereitstellen

        if self.ansichten["code"].laeuft():
            self.ansichten["code"].starte_aktuelles()        # heisst dann Stopp
            return
        arbeitsordner = self._config.workspace if self._config else None
        if not arbeitsordner:
            self._melde("Zum Fahren zuerst einen Arbeitsordner wählen — das Programm "
                        "liegt im Projekt Beispiele dort.")
            return
        # Im Arbeitsordner, nicht im Paket: Laeufe landen neben dem Skript, und nur
        # dort findet der Watcher sie (sonst erfaehrt das Fenster das Verzeichnis nie).
        try:
            bereitstellen(arbeitsordner)
        except OSError as fehler:
            self._melde(f"Beispiele konnten nicht angelegt werden: {fehler}")
            return
        namen = [name for _, name in verfuegbare_backends()]
        self.ansichten["code"].setze_backend("mujoco" if "mujoco" in namen else "sim")
        self._fahrt_erwartet = True
        self.ansichten["code"].starte_skript(fahren.skript_in(arbeitsordner))

    def _oeffne_uebungsfenster(self, titel=""):
        if self.uebungsfenster is None:
            self.uebungsfenster = Uebungsfenster(self._palette)
            self.uebungsfenster.setze_arbeitsordner(
                self._config.workspace if self._config else None
            )
            # Delegation wie beim Stopp im Editor: dasselbe Objekt mit
            # demselben Zustand, nicht eine zweite Kopie der Logik.
            self.uebungsfenster.stopp_gewuenscht.connect(
                lambda: self.ansichten["live"].stoppe()
            )
            self.uebungsfenster.video_gewuenscht.connect(self._starte_film)
        raum = self.ansichten["raumeditor"].raum()
        # Vorbelegt aus der Ansicht, damit die Zeichnung nicht leer beginnt --
        # das `verbunden`-Ereignis zieht Sekundenbruchteile spaeter nach, und
        # DAS ist die Wahrheit ueber den Raum, in dem wirklich gefahren wird.
        self.uebungsfenster.beginne(
            raum, self.ansichten["raumeditor"].startpose(), titel, fahrt=self._fahrt_erwartet
        )
        self._fahrt_erwartet = False
        self.uebungsfenster.show()
        self.uebungsfenster.raise_()
        if self.uebungsfenster._fahrt:
            self.uebungsfenster.activateWindow()             # die Tasten sollen dort ankommen

    def _ansicht(self, pfad):
        """Das gerenderte Zimmer des MuJoCo-Backends -- ans offene Uebungsfenster."""
        if self.uebungsfenster is not None and self.uebungsfenster.isVisible():
            self.uebungsfenster.zeige_ansicht(pfad)

    # ---------------------------------------------------------------- Video

    def _starte_film(self, lauf):
        """`spotlab film <lauf>` als Unterprozess -- die GUI rendert nichts selbst."""
        if self._film is not None and self._film.state() != QProcess.NotRunning:
            self._melde("Es wird schon ein Video gerendert -- bitte warten.")
            return
        self._film = QProcess(self)
        self._film.setProcessChannelMode(QProcess.MergedChannels)
        self._film.finished.connect(
            lambda code, _status, lauf=lauf: self._film_fertig(
                lauf, code, bytes(self._film.readAllStandardOutput()).decode("utf-8", "replace")
            )
        )
        self._film.start(sys.executable, ["-m", "spotlab.cli", "film", str(lauf)])
        text = "Video wird gerendert…"
        self._melde(text)
        if self.uebungsfenster is not None:
            self.uebungsfenster.zeige_video_stand(text)

    def _film_fertig(self, lauf, code, ausgabe):
        pfad = None
        for zeile in ausgabe.splitlines():
            if zeile.startswith("Video: "):
                pfad = zeile[len("Video: "):].strip()
        if code == 0 and pfad:
            text = f"Video: {pfad}"
        else:
            grund = ausgabe.strip().splitlines()[-1] if ausgabe.strip() else f"Code {code}"
            text = f"Video nicht gerendert: {grund}"
            pfad = None
        self._melde(text)
        if self.uebungsfenster is not None:
            self.uebungsfenster.zeige_video_stand(text, pfad)

    def _zeile_ins_uebungsfenster(self, zeile):
        if self.uebungsfenster is not None and self.uebungsfenster.isVisible():
            self.uebungsfenster.zeige_ausgabe(zeile)

    def _ereignis(self, satz):
        """Ereignisse gehen an die Live-Ansicht UND -- wenn offen -- ans Fenster."""
        self.ansichten["live"].zeige_ereignis(satz)
        if self.uebungsfenster is None or not self.uebungsfenster.isVisible():
            return
        daten = satz.get("daten") or {}
        if satz.get("art") == "verbunden":
            # Auch OHNE Raum: dann kommt die Vorbelegung aus der Ansicht weg.
            self.uebungsfenster.setze_raum_name(daten.get("raum"))
        elif satz.get("art") == "angestossen":
            self.uebungsfenster.zeige_anstoss(daten.get("x", 0.0), daten.get("y", 0.0))

    def _lauf_aus_anbindungen(self, prozess, skript):
        # Aus demselben Grund: wer dort startet, will die Panels sehen, nicht
        # Telemetrie. Ein langer Experimentlauf schreibt seinen Fortschritt
        # genau in die Ansicht, aus der er gestartet wurde.
        self._start_aus = "anbindungen"
        self._starte_leser(prozess)

    def _roboterlauf_aus_anbindungen(self):
        """Fremder Code bewegt den echten Spot — der NOT-AUS gehört in Sicht."""
        self._start_aus = None
        self._wechsle("live")
        self.leiste.waehle("live")

    def _oeffne_in_code(self, projekt):
        self.ansichten["code"].setze_projekt(projekt)
        self._wechsle("code")
        self.leiste.waehle("code")

    def _lauf_begonnen(self, verzeichnis):
        # NIE bedingungslos umhängen: die Live-Ansicht ist das Ziel von Stopp
        # und NOT-AUS. Zeigt sie auf einen anderen Lauf als den, der gerade den
        # Roboter hält, trifft der Knopf den falschen Prozess. Zwei Läufe
        # gleichzeitig sind kein konstruierter Fall — aus „Projekte" starten,
        # dann aus „Code", oder zusätzlich F5 aus VS Code (A11 sieht das vor).
        if Path(verzeichnis) == self._aktiver_lauf:
            return
        if self._aktiver_lauf is not None and ist_aktiv(self._aktiver_lauf):
            self._wartende_laeufe.append(Path(verzeichnis))
            self.ansichten["live"].meldung.emit(
                f"Es läuft bereits ein Programm ({self._aktiver_lauf.name}). "
                f"Die Anzeige und der NOT-AUS bleiben bei diesem — der zweite "
                f"Lauf wird übernommen, sobald der erste fertig ist."
            )
            return
        self._uebernimm_lauf(verzeichnis)

    def _uebernimm_lauf(self, verzeichnis):
        self._aktiver_lauf = Path(verzeichnis)
        if self.uebungsfenster is not None and self.uebungsfenster.isVisible():
            self.uebungsfenster.setze_lauf_dir(verzeichnis)
        # Skriptnamen aus lauf.json holen: „hallo_spot.py" sagt mehr als eine
        # Zeitstempel-Kennung.
        skript = read_run(verzeichnis).skript
        name = Path(skript).name if skript else Path(verzeichnis).name
        self.ansichten["live"].setze_lauf(verzeichnis, name)
        # Auch bei einem von aussen gestarteten Lauf (F5 in VS Code) hinschalten —
        # sonst sieht der Schüler nicht, dass sein Programm läuft. Wer aber
        # gerade selbst aus „Code" gestartet hat, wird nicht aus seiner Ansicht
        # geworfen.
        if self._start_aus in ("code", "anbindungen"):
            return
        self._wechsle("live")
        self.leiste.waehle("live")

    def _zustand(self, satz):
        self.kopf.zeige_zustand(satz)
        self.ansichten["live"].zeige_zustand(satz)
        if self.uebungsfenster is None or not self.uebungsfenster.isVisible():
            return
        daten = satz.get("daten") or {}
        pose = daten.get("pose")
        if pose and len(pose) >= 3:
            # `zustand.jsonl` fuehrt yaw und Nick im BOGENMASS; gezeichnet wird in Grad.
            nick = daten.get("pitch")
            self.uebungsfenster.zeige_pose(
                pose[0], pose[1], math.degrees(pose[2]), z=daten.get("z"),
                nick=math.degrees(nick) if nick is not None else None,
            )

    def _lauf_beendet(self, verzeichnis):
        if self._aktiver_lauf is not None and Path(verzeichnis) != self._aktiver_lauf:
            # Ein Lauf, den wir gar nicht anzeigen, ist fertig geworden.
            self._wartende_laeufe = [
                p for p in self._wartende_laeufe if p != Path(verzeichnis)
            ]
            return
        self.ansichten["live"].lauf_beendet()
        self.ansichten["code"].lauf_beendet()
        # Die Ansicht zeigt danach die gefahrene Spur -- `lade()` gab es schon
        # und wurde nirgends gerufen, der Raum blieb nach jedem Lauf leer.
        self.ansichten["raumeditor"].lade(verzeichnis)
        if self.uebungsfenster is not None:
            self.uebungsfenster.beendet(lauf=verzeichnis)
        self.ansichten["anbindungen"].lauf_laeuft(False)
        self.ansichten["anbindungen"].aktualisiere()
        self.ansichten["laeufe"].aktualisiere()
        self.kopf.zeige_getrennt()
        self._start_aus = None
        self._aktiver_lauf = None
        # Jetzt darf ein wartender Lauf nachrücken — aber nur, wenn er noch lebt.
        while self._wartende_laeufe:
            naechster = self._wartende_laeufe.pop(0)
            if ist_aktiv(naechster):
                self._uebernimm_lauf(naechster)
                return

    def frage_beim_schliessen(self, pfade):
        """„speichern", „verwerfen" oder „abbrechen". Ersetzbar im Test."""
        namen = ", ".join(p.name for p in pfade)
        antwort = QMessageBox.question(
            self,
            "spotlab",
            f"Ungespeicherte Änderungen in {namen}. Vor dem Schliessen speichern?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        return {
            QMessageBox.Save: "speichern",
            QMessageBox.Discard: "verwerfen",
        }.get(antwort, "abbrechen")

    def closeEvent(self, ereignis):
        # Der X-Knopf verwarf Arbeit kommentarlos, obwohl das Schliessen eines
        # einzelnen Reiters längst fragt. Für einen Schüler ist beides derselbe
        # Vorgang — nur dass er beim Fenster mehr verliert.
        offen = self.ansichten["code"].ungespeicherte()
        if offen:
            wahl = self.frage_beim_schliessen(offen)
            if wahl == "abbrechen":
                ereignis.ignore()
                return
            if wahl == "speichern" and not self.ansichten["code"].speichere_alle_geaenderten():
                ereignis.ignore()
                return
        if self._watcher is not None:
            self._watcher.stop()
        # Sonst bliebe das Uebungsfenster ohne Hauptfenster offen stehen, und
        # die Anwendung liesse sich nicht mehr beenden.
        if self.uebungsfenster is not None:
            self.uebungsfenster.close()
        # Die Kartenaufnahme ist ein QThread mit einer OFFENEN Robotersitzung.
        # Ohne diesen Aufruf bliebe er als Kind eines zerstörten Widgets zurück —
        # dasselbe Absturzmuster wie beim JediWorker, hier aber mit einer
        # laufenden Verbindung zum Spot.
        try:
            self.ansichten["karten"]._beende_worker()
        except Exception as fehler:      # Schliessen darf nie hängen bleiben
            print(f"Kartenaufnahme liess sich nicht beenden: {fehler}", file=sys.stderr)
        super().closeEvent(ereignis)


def main(argv=None):
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("spotlab")
    app.setStyleSheet(stylesheet(palette_fuer(system_ist_dunkel(app))))
    fenster = MainWindow()
    fenster.show()
    return app.exec()
