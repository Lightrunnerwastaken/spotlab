"""Ansicht „Karten": aufzeichnen, ansehen, auswählen.

Aufzeichnen braucht kein Lease — deshalb darf die GUI es. Hochladen und
Fahren gehören ins Skript, deshalb setzt der Auswählen-Knopf nur die aktive
Karte in der Konfiguration.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.errors import SpotlabError
from spotlab.gui.mapplot import MapPlot
from spotlab.gui.theme import DUNKEL
from spotlab.maps.geometry import grundriss, lage_im_grundriss
from spotlab.maps.store import (
    benenne_wegpunkt,
    karten,
    karten_wurzel,
    lade_graph,
    loesche,
    wegpunkt_name,
)
from spotlab.record import navigation as navigation_datei

HINWEIS = (
    "Zum Aufzeichnen muss der Spot ein Fiducial sehen. Fahre ihn während der "
    "Aufnahme mit dem TABLET durch den Raum — spotlab zeichnet nur mit und "
    "übernimmt die Steuerung nicht. Fahre Runden und komm an bekannten Stellen "
    "vorbei: beim Speichern sucht spotlab die Schleifen und verbindet sie, sonst "
    "bleibt die Karte eine Kette und Spot fährt nur die aufgezeichnete Strecke ab."
)


KEINE_NAVIGATION = "Keine Navigation."
HINWEIS_NAVIGATION = (
    "Einen Wegpunkt in der Zeichnung anklicken — Spot fährt autonom hin, auf der Karte, die "
    "in der Liste gewählt ist. Dazu muss er sich verorten: ein AprilTag dieser Karte muss im "
    'Kamerabild sein. Der Lauf ist das Programm „navigieren.py" aus Beispiele am ECHTEN Spot, '
    "mit Lease, Not-Aus-Endpunkt und dem Tempodeckel aus der Konfiguration, aufgezeichnet wie "
    'jeder Lauf. Ein Klick während der Fahrt wechselt das Ziel; „■ Stopp" hält an und beendet. '
    "Freifläche, Aufsicht, Tablet mit Not-Aus in Reichweite — vor dem ersten Mal A1 und A32."
)
STAND_TEXTE = {
    "lade_karte": 'Karte „{karte}" wird auf den Spot geladen…',
    "verorte": "Spot verortet sich — ein AprilTag der Karte muss im Kamerabild sein. {text}",
    "bereit": "Verortet bei {standort}. Wegpunkt anklicken, Spot fährt hin. {text}",
    "unterwegs": "Unterwegs nach {ziel}…",
    "angekommen": "Angekommen bei {ziel}. Nächsten Wegpunkt anklicken.",
    "gescheitert": "Nicht geschafft: {text}",
    "beendet": "Navigation beendet.",
}


class MapsView(QWidget):
    aktive_karte_gewaehlt = Signal(str)
    navigation_gewuenscht = Signal()   # beginnen oder beenden -- die App entscheidet (ein Lauf)
    stopp_gewuenscht = Signal()
    meldung = Signal(str)

    def __init__(self, palette=DUNKEL, parent=None):
        super().__init__(parent)
        # Palette durchreichen wie bei den anderen Ansichten: der Grundriss
        # malte seine Beschriftungen sonst immer in Dunkelmodus-Farben, auch
        # auf hellem Grund.
        self._palette = palette
        self._ordner = None
        self._config = None
        self._worker = None
        self._karten = []
        self._lauf_dir = None              # das Verzeichnis des Navigationslaufs, wenn einer laeuft
        self._ziel_nr = 0

        self.hinweis = QLabel(HINWEIS)
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        self.graph_leeren = QCheckBox("Karte auf dem Roboter zuerst leeren")
        self.start_knopf = QPushButton("Aufnahme starten")
        self.start_knopf.clicked.connect(self._starte_aufnahme)
        self.wegpunkt_knopf = QPushButton("Wegpunkt setzen")
        self.wegpunkt_knopf.clicked.connect(self._setze_wegpunkt)
        self.speichern_knopf = QPushButton("Beenden und speichern")
        self.speichern_knopf.clicked.connect(self._beende_und_speichere)
        self.aufnahme_status = QLabel("Keine Aufnahme")
        self.aufnahme_status.setObjectName("Gedaempft")
        for knopf in (self.wegpunkt_knopf, self.speichern_knopf):
            knopf.setEnabled(False)

        self.liste = QListWidget()
        self.liste.currentRowChanged.connect(self._zeige_karte)
        self.aktiv_knopf = QPushButton("Als aktive Karte setzen")
        self.aktiv_knopf.clicked.connect(self._setze_aktiv)
        self.loeschen_knopf = QPushButton("Löschen")
        self.loeschen_knopf.clicked.connect(self._loesche)
        # Nachtraeglich benennen: ein Wegpunkt in der Zeichnung anklicken, dann der
        # Knopf -- oder gleich Doppelklick. Der Name landet im SDK-Graphen auf der
        # Platte (`maps/store.py::benenne_wegpunkt`), nicht in einer Nebenliste.
        self.benennen_knopf = QPushButton("✎ Wegpunkt benennen…")
        self.benennen_knopf.setEnabled(False)
        self.benennen_knopf.clicked.connect(self._benenne)

        # Navigation: Wegpunkte anklicken, Spot faehrt hin -- ueber denselben einen
        # Startweg wie „Fahren" (`app.py::_starte_navigation`). Das Ziel geht als
        # `ziel.json` ins Lauf-Verzeichnis, der Stand kommt als `navigation.json`
        # zurueck (`record/navigation.py`); die GUI haelt keinen Draht in den Lauf.
        self.navigation_hinweis = QLabel(HINWEIS_NAVIGATION)
        self.navigation_hinweis.setObjectName("Gedaempft")
        self.navigation_hinweis.setWordWrap(True)
        self.navigation_knopf = QPushButton("🧭 Zu Wegpunkten fahren")
        self.navigation_knopf.clicked.connect(self._navigation_geklickt)
        self.navigation_stopp = QPushButton("■ Stopp")
        self.navigation_stopp.setEnabled(False)
        self.navigation_stopp.clicked.connect(self._stopp_geklickt)
        self.navigation_status = QLabel(KEINE_NAVIGATION)
        self.navigation_status.setObjectName("Gedaempft")
        self.navigation_status.setWordWrap(True)

        self.plot = MapPlot()
        self.plot.palette_ = self._palette
        self.plot.wegpunkt_geklickt.connect(self._wegpunkt_geklickt)
        self.plot.wegpunkt_doppelt.connect(self._wegpunkt_doppelt)
        self.plot_hinweis = QLabel("")
        self.plot_hinweis.setObjectName("Gedaempft")
        self.plot_hinweis.setWordWrap(True)

        aufnahme = QHBoxLayout()
        aufnahme.addWidget(self.start_knopf)
        aufnahme.addWidget(self.wegpunkt_knopf)
        aufnahme.addWidget(self.speichern_knopf)
        aufnahme.addStretch(1)
        aufnahme.addWidget(self.aufnahme_status)

        kartenknoepfe = QHBoxLayout()
        kartenknoepfe.addWidget(self.aktiv_knopf)
        kartenknoepfe.addWidget(self.loeschen_knopf)
        kartenknoepfe.addWidget(self.benennen_knopf)
        kartenknoepfe.addStretch(1)

        navigation = QHBoxLayout()
        navigation.addWidget(self.navigation_knopf)
        navigation.addWidget(self.navigation_stopp)
        navigation.addStretch(1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Aufnahme"))
        anordnung.addWidget(self.hinweis)
        anordnung.addWidget(self.graph_leeren)
        anordnung.addLayout(aufnahme)
        anordnung.addWidget(QLabel("Karten"))
        anordnung.addWidget(self.liste, 1)
        anordnung.addLayout(kartenknoepfe)
        anordnung.addWidget(QLabel("Navigation"))
        anordnung.addWidget(self.navigation_hinweis)
        anordnung.addLayout(navigation)
        anordnung.addWidget(self.navigation_status)
        anordnung.addWidget(self.plot, 3)
        anordnung.addWidget(self.plot_hinweis)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def setze_config(self, cfg):
        self._config = cfg

    def aktualisiere(self):
        self.liste.clear()
        self._karten = karten(self._ordner) if self._ordner else []
        for eintrag in self._karten:
            self.liste.addItem(
                f"{eintrag.name}  ·  {eintrag.wegpunkte} Wegpunkte, "
                f"{eintrag.kanten} Kanten"
            )

    def _gewaehlte(self):
        zeile = self.liste.currentRow()
        if zeile < 0 or zeile >= len(self._karten):
            return None
        return self._karten[zeile]

    def _zeige_karte(self, _zeile):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        try:
            riss = grundriss(lade_graph(eintrag.dir))
        except OSError as fehler:
            self.meldung.emit(f"Die Karte lässt sich nicht lesen: {fehler}")
            return
        self.plot.setze_grundriss(riss)
        self.plot_hinweis.setText(riss.hinweis)
        self.benennen_knopf.setEnabled(False)        # neue Karte, kein Wegpunkt gewaehlt

    # ------------------------------------------------------------- Karten

    def _setze_aktiv(self):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        self.aktive_karte_gewaehlt.emit(eintrag.name)
        self.meldung.emit(
            f"'{eintrag.name}' ist jetzt die aktive Karte — im Skript reicht "
            f"spot.load_map()."
        )

    def _loesche(self):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        antwort = QMessageBox.question(
            self, "spotlab", f"Die Karte '{eintrag.name}' wirklich löschen?"
        )
        if antwort != QMessageBox.Yes:
            return
        loesche(eintrag.dir)
        self.aktualisiere()

    # ----------------------------------------------------------- Navigation

    def laeuft(self):
        return self._lauf_dir is not None

    def karte_fuer_navigation(self):
        """Der Name der gewaehlten Karte -- die, auf der der Lauf faehrt."""
        eintrag = self._gewaehlte()
        return eintrag.name if eintrag is not None else None

    def lauf_beginnt(self, lauf_dir, name="navigieren.py"):
        """Der Watcher hat den Lauf gemeldet: ab jetzt schreiben Klicks Ziele."""
        self._lauf_dir = Path(lauf_dir)
        self._ziel_nr = 0
        # Die Liste bleibt stehen: die Zeichnung muss die Karte des Laufs zeigen,
        # sonst stuende der Roboter auf der falschen Karte.
        for knopf in (self.liste, self.aktiv_knopf, self.loeschen_knopf, self.benennen_knopf):
            knopf.setEnabled(False)
        self.navigation_knopf.setText("■ Navigation beenden")
        self.navigation_stopp.setEnabled(True)
        self.navigation_status.setText(f"{name} läuft — Karte wird geladen…")

    def lauf_beendet(self):
        self._lauf_dir = None
        for knopf in (self.liste, self.aktiv_knopf, self.loeschen_knopf):
            knopf.setEnabled(True)
        self.navigation_knopf.setText("🧭 Zu Wegpunkten fahren")
        self.navigation_stopp.setEnabled(False)
        self.navigation_status.setText(KEINE_NAVIGATION)
        self.plot.leere_navigation()

    def zeige_navigation(self, stand):
        """`navigation.json` des Laufs: Text in die Statuszeile, Lage in die Zeichnung."""
        status = stand.get("status")
        vorlage = STAND_TEXTE.get(status)
        if vorlage is None:
            return
        standort = stand.get("standort")
        ziel = stand.get("ziel")
        text = vorlage.format(
            karte=stand.get("karte") or "?", text=stand.get("text") or "",
            standort=self._name_von(standort), ziel=self._name_von(ziel),
        ).strip()
        gewaehlt = self._gewaehlte()
        if stand.get("karte") and gewaehlt is not None and stand["karte"] != gewaehlt.name:
            text += f' (Der Lauf fährt auf der Karte „{stand["karte"]}", gezeigt wird „{gewaehlt.name}".)'
        self.navigation_status.setText(text)
        self.plot.setze_standort(standort)
        self.plot.setze_roboter(lage_im_grundriss(self.plot.grundriss, standort, stand.get("versatz")))
        if status == "angekommen":
            self.plot.setze_ziel(None)
        elif ziel:
            self.plot.setze_ziel(ziel)

    def _name_von(self, kennung):
        if not kennung:
            return "?"
        for punkt in self.plot.grundriss.punkte:
            if punkt.id == kennung:
                return punkt.name or kennung[:8]
        return kennung[:8]

    def _wegpunkt_geklickt(self, kennung):
        self.plot.setze_ziel(kennung)
        name = self._name_von(kennung)
        if not self.laeuft():
            self.benennen_knopf.setEnabled(True)
            self.navigation_status.setText(
                f'Wegpunkt {name} gewählt — „🧭 Zu Wegpunkten fahren" fährt hin, '
                f'„✎ Wegpunkt benennen…" (oder Doppelklick) gibt ihm einen Namen.')
            return
        self._ziel_nr += 1
        if not navigation_datei.schreibe_ziel(self._lauf_dir, kennung, self._ziel_nr):
            self.meldung.emit("Das Ziel liess sich nicht schreiben — noch einmal klicken.")
            return
        self.navigation_status.setText(f"Ziel gesetzt: {name}. Spot fährt los, sobald er verortet ist.")

    def _wegpunkt_doppelt(self, kennung):
        if self.laeuft():
            return                                   # unterwegs wird nicht umbenannt
        self.plot.setze_ziel(kennung)
        self.benennen_knopf.setEnabled(True)
        self._benenne()

    def _benenne(self):
        """Den gewaehlten Wegpunkt (um)benennen -- Dialog, Platte, Zeichnung."""
        eintrag, kennung = self._gewaehlte(), self.plot.ziel
        if eintrag is None or kennung is None or self.laeuft():
            return
        try:
            bisher = wegpunkt_name(lade_graph(eintrag.dir), kennung)
        except (OSError, SpotlabError) as fehler:
            self.meldung.emit(str(fehler))
            return
        name, ok = QInputDialog.getText(
            self, "Wegpunkt benennen",
            "Name (Leerzeichen werden zu -, leer entfernt den Namen):", text=bisher)
        if not ok:
            return
        try:
            neu = benenne_wegpunkt(eintrag.dir, kennung, name)
        except (OSError, SpotlabError) as fehler:
            self.meldung.emit(str(fehler))
            return
        self._zeige_karte(self.liste.currentRow())   # neu zeichnen, mit Namen
        self.plot.setze_ziel(kennung)
        self.benennen_knopf.setEnabled(True)
        self.navigation_status.setText(
            f'Wegpunkt heisst jetzt „{neu}".' if neu else "Der Wegpunkt hat keinen Namen mehr.")

    def _navigation_geklickt(self):
        # Am `clicked`-Signal: Qt reicht `checked` herein, deshalb kein Parameter.
        self.navigation_gewuenscht.emit()

    def _stopp_geklickt(self):
        self.stopp_gewuenscht.emit()

    # ------------------------------------------------------------- Aufnahme

    def _starte_aufnahme(self):
        if self._config is None:
            self.meldung.emit("Der Spot ist noch nicht eingerichtet — Ansicht 'Spot'.")
            return
        if self._ordner is None:
            self.meldung.emit("Wähle zuerst einen Arbeitsordner — Ansicht 'Projekte'.")
            return
        if self._worker is not None:
            self.meldung.emit("Es läuft bereits eine Aufnahme.")
            return

        from spotlab.gui.recorder import RecordingWorker

        self._worker = RecordingWorker(self._config, self)
        self._worker.status.connect(self._zeige_status)
        self._worker.fehler.connect(self._aufnahme_fehler)
        self._worker.gespeichert.connect(self._aufnahme_gespeichert)
        self._worker.bereit.connect(
            lambda: self._worker.starte(self.graph_leeren.isChecked())
        )
        self._worker.start()
        self.start_knopf.setEnabled(False)
        self.wegpunkt_knopf.setEnabled(True)
        self.speichern_knopf.setEnabled(True)
        self.aufnahme_status.setText("Verbinde…")

    def _setze_wegpunkt(self):
        if self._worker is None:
            return
        name, ok = QInputDialog.getText(self, "Wegpunkt", "Name:")
        if ok and name.strip():
            self._worker.setze_wegpunkt(name.strip())

    def _beende_und_speichere(self):
        if self._worker is None or self._ordner is None:
            return
        name, ok = QInputDialog.getText(self, "Karte speichern", "Name der Karte:")
        if not ok or not name.strip():
            return
        self._worker.speichere(
            karten_wurzel(self._ordner),
            name.strip(),
            roboter=self._config.nickname if self._config else None,
        )

    def _zeige_status(self, status):
        self.aufnahme_status.setText(
            f"{status.meldung} · {status.wegpunkte} Wegpunkte, {status.kanten} Kanten"
        )

    def _aufnahme_fehler(self, text):
        self.meldung.emit(text)

    def _aufnahme_gespeichert(self, pfad):
        self.meldung.emit(f"Karte gespeichert: {pfad}")
        self._beende_worker()
        self.aktualisiere()

    def _beende_worker(self):
        if self._worker is not None:
            self._worker.schliesse()
            self._worker.wait(3000)
            self._worker = None
        self.start_knopf.setEnabled(True)
        self.wegpunkt_knopf.setEnabled(False)
        self.speichern_knopf.setEnabled(False)
        self.aufnahme_status.setText("Keine Aufnahme")
