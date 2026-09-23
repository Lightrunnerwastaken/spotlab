"""Ansicht „Karten": aufzeichnen, ansehen, auswählen.

Aufzeichnen braucht kein Lease — deshalb darf die GUI es. Hochladen und
Fahren gehören ins Skript, deshalb setzt der Auswählen-Knopf nur die aktive
Karte in der Konfiguration.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from spotlab.errors import SpotlabError
from spotlab.gui.mapplot import MapPlot
from spotlab.gui.theme import DUNKEL
from spotlab.maps.geometry import Grundriss, grundriss, lage_im_grundriss
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


WARTE_MS = 3000              # so lange wartet `_beende_worker` auf den Arbeiter

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


# Die kurzen Zeilen stehen immer; der volle Hinweis klappt darunter auf. Kein Text
# ist weg -- untereinander verlangte die Ansicht sonst mehr Hoehe, als ein
# Schul-Laptop hat, und die Navigation lag unter dem Rand (23.09.2026).
AUFNAHME_KURZ = "Spot muss ein Fiducial sehen. Gefahren wird mit dem TABLET — spotlab zeichnet mit."
NAVIGATION_KURZ = ("Wegpunkt in der Zeichnung anklicken — Spot fährt autonom hin. ⚠ Echter Spot: "
                   "Freifläche, Aufsicht, Tablet mit Not-Aus in Reichweite.")


def _klappbar(kurz, lang, warnung=False):
    """Eine kurze Zeile mit „Hinweise ▾“, darunter der volle Text, eingeklappt."""
    zeile = QLabel(kurz)
    zeile.setObjectName("Warnung" if warnung else "Gedaempft")
    zeile.setWordWrap(True)
    mehr = QPushButton("Hinweise ▾")
    mehr.setCheckable(True)
    lang.hide()
    mehr.toggled.connect(lang.setVisible)
    oben = QHBoxLayout()
    oben.addWidget(zeile, 1)
    oben.addWidget(mehr, 0, Qt.AlignTop)
    block = QVBoxLayout()
    block.addLayout(oben)
    block.addWidget(lang)
    return block


class MapsView(QWidget):
    aktive_karte_gewaehlt = Signal(str)
    navigation_gewuenscht = Signal()   # beginnen oder beenden -- die App entscheidet (ein Lauf)
    verbessern_gewuenscht = Signal()   # Schleifen und Anker einer alten Karte nachziehen
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
        self._start_wiederholen = False    # der Start scheiterte, die Verbindung steht
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
        # Fuer Karten, die vor dem 09.09.2026 aufgezeichnet wurden: damals lief
        # der Schleifenschluss beim Speichern noch nicht mit. Ein LAUF, keine
        # Arbeit der GUI -- die Karte muss dafuer auf den Roboter, und Hochladen
        # braucht ein Lease (`workshop/karte.py`).
        self.verbessern_knopf = QPushButton("✨ Karte verbessern…")
        self.verbessern_knopf.setToolTip(
            "Schleifen schliessen und Anker optimieren — für Karten, die noch als Kette "
            "aufgezeichnet wurden. Spot bewegt sich dabei nicht, braucht aber das Lease."
        )
        self.verbessern_knopf.clicked.connect(self._verbessern_geklickt)

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

        kartenknoepfe = QGridLayout()
        kartenknoepfe.addWidget(self.aktiv_knopf, 0, 0)
        kartenknoepfe.addWidget(self.loeschen_knopf, 0, 1)
        kartenknoepfe.addWidget(self.benennen_knopf, 1, 0)
        kartenknoepfe.addWidget(self.verbessern_knopf, 1, 1)
        kartenknoepfe.setColumnStretch(2, 1)

        navigation = QHBoxLayout()
        navigation.addWidget(self.navigation_knopf)
        navigation.addWidget(self.navigation_stopp)
        navigation.addStretch(1)

        # Links die Bedienung in drei Gruppen, rechts die Karte: untereinander
        # gestapelt verlangte die Ansicht 614 px Hoehe und liess der Karte den Rest
        # (UX-Pruefung 23.09.2026).
        aufnahme_gruppe = QGroupBox("Aufnahme")
        innen = QVBoxLayout(aufnahme_gruppe)
        innen.addLayout(_klappbar(AUFNAHME_KURZ, self.hinweis))
        innen.addWidget(self.graph_leeren)
        innen.addLayout(aufnahme)
        innen.addWidget(self.aufnahme_status)

        karten_gruppe = QGroupBox("Karten")
        innen = QVBoxLayout(karten_gruppe)
        # Eine Handvoll Karten -- die Liste soll die Navigation nicht aus dem Bild schieben.
        self.liste.setMaximumHeight(150)
        innen.addWidget(self.liste)
        innen.addLayout(kartenknoepfe)

        navigation_gruppe = QGroupBox("Navigation")
        innen = QVBoxLayout(navigation_gruppe)
        innen.addLayout(_klappbar(NAVIGATION_KURZ, self.navigation_hinweis, warnung=True))
        innen.addLayout(navigation)
        innen.addWidget(self.navigation_status)

        links = QWidget()
        spalte = QVBoxLayout(links)
        spalte.setContentsMargins(0, 0, 0, 0)
        spalte.addWidget(aufnahme_gruppe)
        spalte.addWidget(karten_gruppe)
        spalte.addWidget(navigation_gruppe)
        spalte.addStretch(1)

        rechts = QWidget()
        karte = QVBoxLayout(rechts)
        karte.setContentsMargins(0, 0, 0, 0)
        karte.addWidget(self.plot, 1)
        karte.addWidget(self.plot_hinweis)

        # Die Bedienung scrollt, wenn das Fenster niedrig ist: jeder Hinweis bleibt
        # ganz (vorher schnitt das Layout die letzte Zeile ab), und die Ansicht
        # zwingt dem Fenster keine Hoehe auf.
        rollbar = QScrollArea()
        rollbar.setWidget(links)
        rollbar.setWidgetResizable(True)
        rollbar.setFrameShape(QFrame.NoFrame)
        rollbar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rollbar.setMinimumWidth(links.minimumSizeHint().width() + 14)

        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(rollbar)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 2)
        teiler.setStretchFactor(1, 3)
        teiler.setChildrenCollapsible(False)
        # Die langen Hinweise links melden eine grosse Wunschbreite an -- ohne feste
        # Aufteilung schrumpfte die Karte rechts auf einen Streifen.
        rechts.setMinimumWidth(300)
        teiler.setSizes([460, 540])

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(teiler)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def setze_config(self, cfg):
        self._config = cfg

    def aktualisiere(self):
        """Liste neu von der Platte -- die AUSWAHL bleibt, nach Namen, samt gewaehltem Wegpunkt.

        Befund p14 (22.09.2026): `app.py::_lauf_beendet` ruft das nach JEDEM Lauf, und
        es leerte die Liste. Die Zeichnung blieb stehen, „Wegpunkt benennen" war aktiv
        und tat still nichts, „Zu Wegpunkten fahren" sagte „Waehle zuerst eine Karte" --
        obwohl sie zu sehen war. Nach Namen, nicht nach Zeile: die Liste ist nach
        Aenderungszeit sortiert, und nach einer Kartenarbeit rutscht eine Karte nach
        oben. Die Zeichnung kommt neu von der Platte (dafuer ruft die App das ja); ist
        die Karte weg, verschwindet auch die Zeichnung. Waehrend einer Navigation
        bleibt die Zeichnung, wie sie ist -- sie zeigt die Karte des Laufs.
        """
        vorher = self._gewaehlte()
        name = vorher.name if vorher is not None else None
        wegpunkt = self.plot.ziel
        self.liste.blockSignals(True)
        try:
            self.liste.clear()
            self._karten = karten(self._ordner) if self._ordner else []
            for eintrag in self._karten:
                self.liste.addItem(
                    f"{eintrag.name}  ·  {eintrag.wegpunkte} Wegpunkte, "
                    f"{eintrag.kanten} Kanten"
                )
            zeile = next((i for i, e in enumerate(self._karten) if e.name == name), -1)
            if zeile >= 0:
                self.liste.setCurrentRow(zeile)
        finally:
            self.liste.blockSignals(False)
        if name is None or self.laeuft():
            return
        if zeile < 0:
            self.plot.setze_grundriss(Grundriss([], [], "leer", "Keine Karte gewählt."))
            self.plot_hinweis.setText("")
            self.benennen_knopf.setEnabled(False)
            return
        self._zeige_karte(zeile)
        if wegpunkt is not None and any(p.id == wegpunkt for p in self.plot.grundriss.punkte):
            self.plot.setze_ziel(wegpunkt)
            self.benennen_knopf.setEnabled(True)

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
        for knopf in (self.liste, self.aktiv_knopf, self.loeschen_knopf,
                      self.benennen_knopf, self.verbessern_knopf):
            knopf.setEnabled(False)
        self.navigation_knopf.setText("■ Navigation beenden")
        self.navigation_stopp.setEnabled(True)
        self.navigation_status.setText(f"{name} läuft — Karte wird geladen…")

    def lauf_beendet(self):
        self._lauf_dir = None
        for knopf in (self.liste, self.aktiv_knopf, self.loeschen_knopf,
                      self.verbessern_knopf):
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

    def _verbessern_geklickt(self):
        self.verbessern_gewuenscht.emit()

    def zeige_verbesserung(self, text):
        self.navigation_status.setText(text)

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
        if self._worker is not None and self._start_wiederholen:
            # Der Start scheiterte (meist: kein Fiducial im Bild), die Verbindung steht:
            # noch einmal starten, ohne neu zu verbinden.
            self._start_wiederholen = False
            self._worker.starte(self.graph_leeren.isChecked())
            self.start_knopf.setEnabled(False)
            self.aufnahme_status.setText("Starte…")
            return
        if self._worker is not None:
            self.meldung.emit("Es läuft bereits eine Aufnahme.")
            return

        from spotlab.gui.recorder import RecordingWorker

        self._worker = RecordingWorker(self._config, self)
        self._worker.status.connect(self._zeige_status)
        self._worker.fehler.connect(self._auftrag_fehler)
        self._worker.abgebrochen.connect(self._aufnahme_fehler)
        self._worker.gespeichert.connect(self._aufnahme_gespeichert)
        self._worker.bereit.connect(self._worker_bereit)
        self._worker.start()
        self.start_knopf.setEnabled(False)
        self.wegpunkt_knopf.setEnabled(True)
        self.speichern_knopf.setEnabled(True)
        self.aufnahme_status.setText("Verbinde…")

    def _worker_bereit(self):
        """Verbunden: die Aufnahme beginnen. Eine Methode, keine Lambda -- nur so laesst
        sich die Verbindung beim Schliessen gezielt trennen."""
        if self._worker is not None:
            self._worker.starte(self.graph_leeren.isChecked())

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

    def _auftrag_fehler(self, art, text):
        """Ein einzelner Auftrag scheiterte: MELDEN, die Aufnahme bleibt offen.

        Befund p04 (22.09.2026): bis dahin beendete JEDER Fehlschlag die ganze
        Aufnahme im Fenster — ein Wegpunkt, der nicht gesetzt wurde, und „Beenden und
        speichern" war grau, waehrend der Roboter weiter aufzeichnete. Jetzt bleiben
        Verbindung und Knoepfe, der naechste Versuch kann gelingen. Scheiterte der
        START, zeichnet der Roboter nicht — dann geht der Startknopf wieder, ohne
        neu zu verbinden.
        """
        self.meldung.emit(text)
        if self._worker is None:
            return
        if art == "start":
            self._start_wiederholen = True
            self.start_knopf.setEnabled(True)
            self.aufnahme_status.setText(
                "Nicht gestartet — die Verbindung steht, „Aufnahme starten“ versucht es noch einmal.")
        elif art != "status":
            self.aufnahme_status.setText(f"{text} Die Verbindung steht — noch einmal versuchen.")

    def _aufnahme_fehler(self, text):
        """Die Verbindung kam nicht zustande: melden UND aufraeumen. Vorher blieb
        `_worker` stehen: der Startknopf blieb fuer immer grau, und der zweite Versuch
        antwortete "Es laeuft bereits eine Aufnahme" -- eine Ursache, die es nicht gab.
        Nur ein Neustart half, und getroffen hat es jeden ohne Roboter beim ersten Klick."""
        self.meldung.emit(text)
        self._beende_worker()
        self.aufnahme_status.setText("Nicht aufgenommen.")

    def _aufnahme_gespeichert(self, pfad):
        self.meldung.emit(f"Karte gespeichert: {pfad}")
        self._beende_worker()
        self.aktualisiere()

    def _beende_worker(self, warte_ms=WARTE_MS):
        """Den Aufnahme-Arbeiter beenden. Gibt True zurueck, wenn er danach NOCH LAEUFT.

        Erst trennen, dann warten: eine Meldung, die eine Millisekunde zu spaet kommt,
        darf das Widget nicht mehr anfassen. Laeuft er nach `warte_ms` noch (Verbinden
        haengt am Netz, die Nachbearbeitung rechnet), wird er NICHT vergessen — bis zum
        22.09.2026 geschah genau das: das Widget wurde zerstoert, der QThread als sein
        Kind mit, und Qt brach den Prozess ab („QThread: Destroyed while thread is
        still running", p05), samt NOT-AUS-Knopf. Jetzt wird er vom Widget geloest und
        gehalten, bis er fertig ist (`_halte_bis_zum_ende`). Die Rueckgabe sagt dem
        Hauptfenster, ob beim Schliessen noch etwas laeuft; ein zweiter Aufruf wartet
        erneut und zaehlt dabei auch einen schon geloesten Arbeiter.
        """
        arbeiter, self._worker = self._worker, None
        self._start_wiederholen = False
        self.start_knopf.setEnabled(True)
        self.wegpunkt_knopf.setEnabled(False)
        self.speichern_knopf.setEnabled(False)
        self.aufnahme_status.setText("Keine Aufnahme")
        if arbeiter is not None:
            self._trenne(arbeiter)
            arbeiter.schliesse()
            if arbeiter.wait(warte_ms):
                return aufnahme_laeuft_noch()    # fertig: bleibt Kind des Widgets, wie bisher
            _halte_bis_zum_ende(arbeiter)
            return True
        return _warte_auf_nachzuegler(warte_ms)

    def _trenne(self, arbeiter):
        """Jede Verbindung des Arbeiters zu DIESEM Widget einzeln kappen -- nie `disconnect()`
        ohne Argument, das kappte auch `finished`, an dem das Aufraeumen haengt."""
        for signal, slot in (("status", self._zeige_status), ("fehler", self._auftrag_fehler),
                             ("abgebrochen", self._aufnahme_fehler),
                             ("gespeichert", self._aufnahme_gespeichert),
                             ("bereit", self._worker_bereit)):
            try:
                getattr(arbeiter, signal).disconnect(slot)
            except (AttributeError, RuntimeError, TypeError):
                pass                              # war nicht verbunden -- dann eben nichts


# Arbeiter, die beim Beenden noch liefen: vom Widget geloest und hier gehalten, bis sie
# fertig sind. Ohne Referenz zerstoerte Python den QThread, waehrend er laeuft -- dasselbe
# Absturzmuster wie mit dem Widget als Elternteil.
_NACHZUEGLER = set()
# So lange wartet das Programmende hoechstens auf einen Nachzuegler. Eine Nachbearbeitung
# samt Herunterladen darf damit noch zu Ende kommen; die Karte liegt dann auf der Platte.
NACHZUEGLER_FRIST_S = 60.0


_ABSCHIED = {"angemeldet": False}


def _halte_bis_zum_ende(arbeiter):
    """Den laufenden Arbeiter vom Widget loesen und halten, bis er fertig ist.

    `finished` -> `deleteLater` ist das Qt-Muster fuer genau diesen Fall; die Referenz
    hier faellt beim naechsten Blick (`_raeume_nachzuegler`), sobald er nicht mehr laeuft.
    """
    import atexit

    arbeiter.setParent(None)                 # stirbt das Widget, stirbt der Faden nicht mit
    arbeiter.finished.connect(arbeiter.deleteLater)
    _NACHZUEGLER.add(arbeiter)
    if not _ABSCHIED["angemeldet"]:
        _ABSCHIED["angemeldet"] = True
        atexit.register(_warte_auf_nachzuegler, NACHZUEGLER_FRIST_S * 1000)


def _raeume_nachzuegler():
    """Fertige Nachzuegler vergessen -- die Referenz faellt, `deleteLater` raeumt den Rest."""
    import shiboken6

    for arbeiter in list(_NACHZUEGLER):
        if not shiboken6.isValid(arbeiter) or not arbeiter.isRunning():
            _NACHZUEGLER.discard(arbeiter)


def aufnahme_laeuft_noch():
    """Laeuft noch ein Arbeiter der Kartenaufnahme, der schon vom Fenster geloest ist?"""
    _raeume_nachzuegler()
    return bool(_NACHZUEGLER)


def _warte_auf_nachzuegler(warte_ms):
    """Hoechstens `warte_ms` auf die Nachzuegler warten. True, wenn danach noch einer laeuft.

    Auch der Haken fuer das Programmende (`atexit`): ein QThread, der beim Abbau des
    Interpreters noch laeuft, wird zerstoert und reisst den Prozess mit.
    """
    import time

    ende = time.monotonic() + max(0.0, float(warte_ms)) / 1000.0
    _raeume_nachzuegler()
    for arbeiter in list(_NACHZUEGLER):
        rest_ms = int(max(0.0, ende - time.monotonic()) * 1000)
        try:
            arbeiter.wait(rest_ms)
        except RuntimeError:
            pass                                  # schon zerstoert
    return aufnahme_laeuft_noch()
