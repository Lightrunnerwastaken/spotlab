"""Die Ansicht „Code": Dateibaum, Reiter, Ausgabe.

Leitsatz der Aufteilung: „Code" zeigt, was das Programm sagt; „Live-Lauf"
zeigt, was der Roboter tut. Deshalb steht hier keine Telemetrie.

Gestartet wird ueber workshop/launcher.py::start_script — derselbe Weg wie
„Projekte" und `spotlab run`. Gestoppt wird ueber ein Signal, das das
Hauptfenster an LiveView.stoppe() weiterreicht: dasselbe Objekt mit demselben
Zustand, nicht eine zweite Kopie der Logik.
"""

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spotlab.editor.syntax import pruefe
from spotlab.editor.traceback import finde_stellen
from spotlab.errors import SpotlabError
from spotlab.gui.editor.codeedit import CodeEdit
from spotlab.gui.editor.completer import Vervollstaendigung
from spotlab.gui.editor.highlighter import Hervorheber
from spotlab.gui.editor.tree import Dateibaum
from spotlab.gui.views.projects import projekte_in
from spotlab.workshop.launcher import start_script

# Beschriftung -> Backend-Name. Drei Zustaende, nicht zwei: der Trockenlauf HAT
# keine Position (Pose bleibt 0/0/0) und kann im Uebungsraum nichts zeigen.
# `sim` war bis hierher aus der GUI ueberhaupt nicht erreichbar.
BACKENDS = (
    ("Echter Spot", "real"),
    ("Trockenlauf (nur Text)", "dryrun"),
    ("Übungsraum (virtuell)", "sim"),
    ("Übungsraum 3D (MuJoCo)", "mujoco"),
)


def verfuegbare_backends():
    """Nur, was auf diesem Laptop laeuft.

    `mujoco` braucht `spotsim` aus matura-spot; ein Eintrag, der beim Start
    mit ModuleNotFoundError stirbt, ist keine Wahl. Geprueft per `find_spec`,
    nicht per Import -- die GUI importiert kein MuJoCo (CLAUDE.md).
    """
    dreidimensional = importlib.util.find_spec("spotsim") is not None
    return tuple(b for b in BACKENDS if b[1] != "mujoco" or dreidimensional)


def lade_text(pfad):
    try:
        return Path(pfad).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise SpotlabError(
            f"{Path(pfad).name} ist nicht UTF-8 kodiert und lässt sich hier nicht "
            "öffnen. Speichere die Datei in VS Code als UTF-8."
        )


def schreibe_text(pfad, text):
    # newline="\n": sonst schreibt Python auf Windows CRLF und jede Datei sieht
    # nach dem ersten Speichern in git vollstaendig geaendert aus.
    Path(pfad).write_text(text, encoding="utf-8", newline="\n")


def stempel(pfad):
    zustand = Path(pfad).stat()
    return zustand.st_mtime, zustand.st_size


@dataclass
class Reiter:
    pfad: Path
    feld: CodeEdit
    hervorheber: object
    hilfe: object
    mtime: float
    groesse: int
    verschmutzt: bool = False


class Ausgabefeld(QPlainTextEdit):
    """Die Ausgabe des Laufs, mit anklickbaren Stellen aus dem Traceback.

    Anklickbar wird nur, was in der Werkstatt liegt: sonst landet ein Schueler
    mit einem Klick in bosdyn/client/... und aendert fremden Bibliothekscode.
    """

    stelle_geklickt = Signal(object, int)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._palette = palette
        self._wurzel = None
        self._stellen = []          # (von, bis, pfad, zeile), absolut im Dokument
        self._laenge = 0            # Dokumentlänge in Zeichen, laufend geführt

    def setze_wurzel(self, pfad):
        self._wurzel = Path(pfad) if pfad else None

    def stellen(self):
        return list(self._stellen)

    def leere(self):
        self.clear()
        self._stellen = []
        self._laenge = 0

    def haenge_an(self, zeile):
        # LAUFENDER Offset statt toPlainText(): jener kopiert bei jeder Zeile
        # das ganze Dokument, und das ist quadratisch. Gemessen 0.070 ms/Zeile
        # bei 500 Zeilen, 0.402 bei 4000 — auf 50 000 Zeilen hochgerechnet
        # Minuten, in denen die Qt-Ereignisschleife besetzt ist. Ein Klick auf
        # NOT-AUS steht in derselben Warteschlange.
        #
        # Die Zahl MUSS stimmen: an ihr hängen die Zeichenpositionen der
        # anklickbaren Traceback-Stellen. Ein Fehler hier schickt den Schüler in
        # die falsche Datei, deshalb prüft ein Test sie gegen toPlainText().
        basis = self._laenge + (1 if self._laenge else 0)  # append setzt ein \n davor
        self.appendPlainText(zeile)
        self._laenge = basis + len(zeile)
        if self._wurzel is None:
            return
        for stelle in finde_stellen(zeile, self._wurzel):
            von, bis = basis + stelle.von, basis + stelle.bis
            self._stellen.append((von, bis, stelle.pfad, stelle.zeile))
            self._male_link(von, bis)

    def _male_link(self, von, bis):
        cursor = self.textCursor()
        cursor.setPosition(von)
        cursor.setPosition(bis, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._palette.akzent))
        fmt.setFontUnderline(True)
        cursor.mergeCharFormat(fmt)

    def mousePressEvent(self, ereignis):
        pos = self.cursorForPosition(ereignis.position().toPoint()).position()
        for von, bis, pfad, zeile in self._stellen:
            if von <= pos < bis:
                self.stelle_geklickt.emit(pfad, zeile)
                return
        super().mousePressEvent(ereignis)


class EditorView(QWidget):
    meldung = Signal(str)
    lauf_gestartet = Signal(object, str)
    stopp_gewuenscht = Signal()
    # Wer den Knopfzustand ANDERSWO spiegeln will, hoert hier zu statt eine
    # zweite Buchfuehrung anzulegen: der Uebungsraum hat genau daran gefehlt --
    # seine Methode war vorhanden und nirgends verbunden.
    laeuft_geaendert = Signal(bool)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._ordner = None
        self._projekt = None
        self._reiter = {}          # CodeEdit -> Reiter
        self._laeuft = False
        self._prozess = None
        # Zusaetzliche Umgebungsvariablen fuer den Kindprozess. Der Editor
        # kennt keine Raeume; das Hauptfenster haengt hier ein, was in der
        # Ansicht „Übungsraum" gewaehlt ist.
        self.zusatz_umgebung = dict

        # -------------------------------------------------- links: Dateien
        self.projektwahl = QComboBox()
        self.projektwahl.currentTextChanged.connect(self._projekt_gewechselt)
        self.baum = Dateibaum()
        self.baum.datei_gewaehlt.connect(self.oeffne)
        self.baum.datei_entfernt.connect(self.schliesse_pfad)
        self.baum.meldung.connect(self.meldung)

        links = QWidget()
        links_anordnung = QVBoxLayout(links)
        links_anordnung.setContentsMargins(0, 0, 0, 0)
        links_anordnung.addWidget(self.projektwahl)
        links_anordnung.addWidget(self.baum, 1)

        # -------------------------------------------------- mitte: Editor
        self.reiter = QTabWidget()
        self.reiter.setTabsClosable(True)
        self.reiter.setDocumentMode(True)
        self.reiter.tabCloseRequested.connect(self._schliesse)

        self.backendwahl = QComboBox()
        for beschriftung, name in verfuegbare_backends():
            self.backendwahl.addItem(beschriftung, name)
        self.start_knopf = QPushButton("▶ Starten")
        self.start_knopf.clicked.connect(self._starten_oder_stoppen)

        werkzeuge = QHBoxLayout()
        werkzeuge.addWidget(QLabel("Wo läuft es?"))
        werkzeuge.addWidget(self.backendwahl)
        werkzeuge.addStretch(1)
        werkzeuge.addWidget(self.start_knopf)

        mitte = QWidget()
        mitte_anordnung = QVBoxLayout(mitte)
        mitte_anordnung.setContentsMargins(0, 0, 0, 0)
        mitte_anordnung.addLayout(werkzeuge)
        mitte_anordnung.addWidget(self.reiter, 1)

        # -------------------------------------------------- rechts: Ausgabe
        self.ausgabe = Ausgabefeld(self._palette)
        self.ausgabe.stelle_geklickt.connect(self.springe_zu)
        self.hinweis = QLabel('Pose, Tempo und Kamerabild zeigt die Ansicht „Live-Lauf".')
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        rechts = QWidget()
        rechts_anordnung = QVBoxLayout(rechts)
        rechts_anordnung.setContentsMargins(0, 0, 0, 0)
        rechts_anordnung.addWidget(QLabel("Ausgabe"))
        rechts_anordnung.addWidget(self.ausgabe, 1)
        rechts_anordnung.addWidget(self.hinweis)

        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.addWidget(links)
        self.teiler.addWidget(mitte)
        self.teiler.addWidget(rechts)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setSizes([220, 620, 300])

        aussen = QVBoxLayout(self)
        aussen.addWidget(self.teiler, 1)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.ausgabe.setze_wurzel(self._ordner)
        self.projektwahl.blockSignals(True)
        self.projektwahl.clear()
        if self._ordner is not None:
            for projekt in projekte_in(self._ordner):
                self.projektwahl.addItem(projekt.name)
        self.projektwahl.blockSignals(False)
        if self.projektwahl.count():
            self.projektwahl.setCurrentIndex(0)
            self._projekt_gewechselt(self.projektwahl.currentText())
        else:
            self.setze_projekt(None)

    def setze_projekt(self, pfad):
        self._projekt = Path(pfad) if pfad else None
        self.baum.setze_projekt(self._projekt)
        if self._projekt is None:
            return
        name = self._projekt.name
        if self.projektwahl.currentText() != name:
            index = self.projektwahl.findText(name)
            if index >= 0:
                self.projektwahl.setCurrentIndex(index)

    def _projekt_gewechselt(self, name):
        if self._ordner is None or not name:
            return
        self.setze_projekt(self._ordner / name)

    def laeuft(self):
        return self._laeuft

    def gewaehltes_backend(self):
        return self.backendwahl.currentData()

    def setze_backend(self, name):
        """Ein UNBEKANNTER Name aendert nichts.

        `load_config()` liefert `default_backend` aus einer Datei, die jemand von
        Hand geschrieben haben kann. Die Auswahl darf davon nicht in einen
        Zustand geraten, den sie gar nicht kennt.
        """
        index = self.backendwahl.findData(name)
        if index >= 0:
            self.backendwahl.setCurrentIndex(index)

    def aktueller_reiter(self):
        return self._reiter.get(self.reiter.currentWidget())

    # ------------------------------------------------------------- Dateien

    def oeffne(self, pfad):
        pfad = Path(pfad)
        for feld, eintrag in self._reiter.items():
            if eintrag.pfad == pfad:
                self.reiter.setCurrentWidget(feld)
                return
        try:
            text = lade_text(pfad)
            zeit, groesse = stempel(pfad)
        except (SpotlabError, OSError) as fehler:
            self.meldung.emit(str(fehler))
            return

        feld = CodeEdit(self._palette)
        feld.setPlainText(text)
        feld.document().setModified(False)
        hervorheber = Hervorheber(feld.document(), self._palette)
        hilfe = Vervollstaendigung(feld)
        hilfe.setze_pfad(pfad)
        feld.ruhe.connect(hervorheber.neu_lexen)
        feld.ruhe.connect(lambda f=feld: self._pruefe(f))
        # modificationChanged statt textChanged: rehighlight() aendert
        # Formatierung, und Qt zaehlt das als Inhaltsaenderung — der Reiter
        # waere sonst schon beim Oeffnen als geaendert markiert.
        # QSyntaxHighlighter stellt das Modified-Flag ausdruecklich wieder her.
        feld.document().modificationChanged.connect(
            lambda geaendert, f=feld: self._verschmutzt(f, geaendert)
        )
        feld.speichern_gewuenscht.connect(self.speichere_aktuellen)

        self._reiter[feld] = Reiter(pfad, feld, hervorheber, hilfe, zeit, groesse)
        self.reiter.addTab(feld, pfad.name)
        self.reiter.setCurrentWidget(feld)
        hervorheber.neu_lexen()

    def _pruefe(self, feld):
        eintrag = self._reiter.get(feld)
        if eintrag is None:
            return
        feld.zeige_fehler(pruefe(feld.toPlainText(), name=str(eintrag.pfad)))

    def _verschmutzt(self, feld, geaendert=True):
        eintrag = self._reiter.get(feld)
        if eintrag is None or eintrag.verschmutzt == geaendert:
            return
        eintrag.verschmutzt = geaendert
        self._titel(eintrag)

    def _titel(self, eintrag):
        index = self.reiter.indexOf(eintrag.feld)
        if index >= 0:
            marke = "● " if eintrag.verschmutzt else ""
            self.reiter.setTabText(index, f"{marke}{eintrag.pfad.name}")

    def fremd_geaendert(self, eintrag):
        try:
            return stempel(eintrag.pfad) != (eintrag.mtime, eintrag.groesse)
        except OSError:
            return False

    def frage_bei_konflikt(self, pfad):
        """Gibt 'ueberschreiben', 'neu_laden' oder 'abbrechen' zurück.

        Als eigene Methode und nicht als Dialog mitten im Speichern: Tests
        ersetzen sie.
        """
        antwort = QMessageBox.question(
            self,
            "spotlab",
            f"{pfad.name} wurde ausserhalb von spotlab geändert.\n\n"
            "Speichern überschreibt die fremde Änderung, Verwerfen lädt die Datei neu.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if antwort == QMessageBox.Save:
            return "ueberschreiben"
        if antwort == QMessageBox.Discard:
            return "neu_laden"
        return "abbrechen"

    def ungespeicherte(self):
        """Pfade aller Reiter mit ungespeicherten Aenderungen."""
        return [e.pfad for e in self._reiter.values() if e.verschmutzt]

    def speichere_alle_geaenderten(self):
        """Alle verschmutzten Reiter speichern. False, sobald einer scheitert.

        Vor dem Start reicht der aktuelle Reiter nicht: ein Mehrdatei-Projekt
        liefe sonst mit der alten Fassung der importierten Dateien, und der
        Schueler sucht den Fehler in Code, der gar nicht ausgefuehrt wurde.
        """
        for eintrag in list(self._reiter.values()):
            if self._weicht_ab(eintrag) and not self._speichere(eintrag):
                return False
        return True

    def _weicht_ab(self, eintrag):
        """Weicht der Reiter von der Datei ab?

        Nicht `verschmutzt` allein: `setPlainText()` setzt Qts Modified-Flag
        zurueck, die Markierung kann also falsch stehen. Vor dem Start zaehlt,
        was WIRKLICH anders ist — der Vergleich mit der Datei luegt nicht.
        """
        if eintrag.verschmutzt:
            return True
        try:
            return lade_text(eintrag.pfad) != eintrag.feld.toPlainText()
        except (OSError, SpotlabError):
            return True

    def speichere_aktuellen(self):
        eintrag = self.aktueller_reiter()
        if eintrag is None:
            return False
        return self._speichere(eintrag)

    def _speichere(self, eintrag):
        if self.fremd_geaendert(eintrag):
            wahl = self.frage_bei_konflikt(eintrag.pfad)
            if wahl == "abbrechen":
                return False
            if wahl == "neu_laden":
                self._neu_laden(eintrag)
                return False
        try:
            schreibe_text(eintrag.pfad, eintrag.feld.toPlainText())
            eintrag.mtime, eintrag.groesse = stempel(eintrag.pfad)
        except OSError as fehler:
            self.meldung.emit(f"{eintrag.pfad.name} liess sich nicht speichern: {fehler}")
            return False
        eintrag.feld.document().setModified(False)
        eintrag.verschmutzt = False
        self._titel(eintrag)
        return True

    def _neu_laden(self, eintrag):
        try:
            text = lade_text(eintrag.pfad)
        except (SpotlabError, OSError) as fehler:
            self.meldung.emit(str(fehler))
            return
        eintrag.feld.setPlainText(text)
        eintrag.feld.document().setModified(False)
        eintrag.mtime, eintrag.groesse = stempel(eintrag.pfad)
        eintrag.verschmutzt = False
        self._titel(eintrag)

    def schliesse_pfad(self, pfad):
        """Den Reiter zu `pfad` schliessen, falls einer offen ist.

        Geht ueber `_schliesse`, damit die Rueckfrage bei ungespeicherten
        Aenderungen gilt: die geloeschte Datei liegt im Papierkorb und ist
        wiederherstellbar, ein ungespeicherter Puffer nicht.
        """
        pfad = Path(pfad)
        for feld, eintrag in list(self._reiter.items()):
            if eintrag.pfad == pfad:
                self._schliesse(self.reiter.indexOf(feld))
                return

    def _schliesse(self, index):
        feld = self.reiter.widget(index)
        eintrag = self._reiter.get(feld)
        if eintrag is not None and eintrag.verschmutzt:
            antwort = QMessageBox.question(
                self,
                "spotlab",
                f"{eintrag.pfad.name} hat ungespeicherte Änderungen. Trotzdem schliessen?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if antwort != QMessageBox.Yes:
                return
        self.reiter.removeTab(index)
        reiter = self._reiter.pop(feld, None)
        # ERST den jedi-Arbeiter beenden, DANN das Feld zur Zerstörung
        # vormerken. Umgekehrt wird ein arbeitender QThread destruiert, und das
        # reisst das ganze Fenster mit — samt NOT-AUS-Knopf.
        if reiter is not None and reiter.hilfe is not None:
            reiter.hilfe.schliesse()
        feld.deleteLater()

    def springe_zu(self, pfad, zeile):
        self.oeffne(pfad)
        feld = self.reiter.currentWidget()
        if feld is None:
            return
        block = feld.document().findBlockByNumber(max(0, zeile - 1))
        if not block.isValid():
            return
        feld.setTextCursor(QTextCursor(block))
        feld.centerCursor()
        feld.setFocus()

    # ------------------------------------------------------------- Lauf

    def starte_aktuelles(self):
        """Startet die offene Datei -- oder haelt an, wenn schon etwas laeuft.

        Oeffentlich, damit der Uebungsraum daran delegieren kann. Kein zweiter
        Startweg: genau EIN Lauf ist der, auf den Stopp und NOT-AUS zeigen.
        """
        self._starten_oder_stoppen()

    def _starten_oder_stoppen(self):
        if self._laeuft:
            # Delegation ans Hauptfenster, das LiveView.stoppe() ruft: der
            # freundliche Stopp haengt am Lauf-Verzeichnis, das nur die
            # Live-Ansicht vom Watcher bekommt.
            self.stopp_gewuenscht.emit()
            return
        eintrag = self.aktueller_reiter()
        if eintrag is None:
            self.meldung.emit("Öffne zuerst eine Datei, die du starten möchtest.")
            return
        # ALLE geaenderten, nicht nur den sichtbaren: wer auf Starten drueckt,
        # meint das Programm, wie es gerade dasteht — samt seiner Importe.
        if not self.speichere_alle_geaenderten():
            return
        wo = self.gewaehltes_backend()
        try:
            # nur_trocken NUR beim Uebungsraum: `connect(backend="real")` im
            # Skript schlaegt die Umgebungsvariable, und ein Lauf, den der
            # Schueler als virtuell gewaehlt hat, darf den Roboter nicht
            # bewegen koennen. Beim Trockenlauf bleibt es wie bisher -- dessen
            # Bedeutung hier zu aendern, waere eine zweite, ungefragte Aenderung.
            prozess = start_script(
                eintrag.pfad, backend=wo, nur_trocken=(wo == "sim"),
                umgebung=self.zusatz_umgebung(),
            )
        except SpotlabError as fehler:
            self.meldung.emit(str(fehler))
            return
        self.ausgabe.leere()
        self._prozess = prozess
        self._setze_laeuft(True)
        self.lauf_gestartet.emit(prozess, str(eintrag.pfad))

    def _setze_laeuft(self, laeuft):
        self._laeuft = laeuft
        self.start_knopf.setText("■ Stopp" if laeuft else "▶ Starten")
        self.laeuft_geaendert.emit(laeuft)

    def zeige_ausgabe(self, zeile):
        self.ausgabe.haenge_an(zeile)

    def pruefe_lauf_lebt(self):
        """Knopf freigeben, wenn der Prozess schon tot ist.

        Ein Skript mit Syntaxfehler stirbt, bevor es ein Lauf-Verzeichnis
        anlegt. Der Watcher meldet dann nie ein Ende, und der Knopf blieb fuer
        immer auf „Stopp" — der Schueler konnte danach nichts mehr starten und
        musste das Fenster neu oeffnen.
        """
        prozess = self._prozess
        if prozess is None or not self._laeuft:
            return
        if prozess.poll() is not None:
            self.lauf_beendet()

    def lauf_beendet(self):
        self._prozess = None
        self._setze_laeuft(False)
