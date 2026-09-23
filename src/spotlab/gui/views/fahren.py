"""Die Ansicht „Fahren“: den echten Spot live ueber W A S D Q E fahren.

Kein eigener Weg zum Roboter: der Knopf startet `Beispiele/fahren.py` ueber die
App -- derselbe eine Startweg wie „Starten“ im Editor, mit dem Backend „real“
(`app.py::_starte_fahrt`), also Lease, Not-Aus-Endpunkt, Geschwindigkeits-
deckel aus `config.toml` und die Aufzeichnung wie bei jedem Programm. Die
Tasten gehen als `fahrt.json` ins Lauf-Verzeichnis (`gui/tastenfahrt.py`,
`record/fahrt.py`); `fahren.py` liest sie mit 20 Hz. **Ein Befehl aelter als
eine halbe Sekunde heisst Stopp** -- und jedes Kommando traegt eine Endzeit
von rund einer Sekunde: stirbt die GUI oder der Lauf, steht der Roboter.

Die Tastatur gehoert dem Tab nur, solange er sichtbar ist und der Lauf lebt.
Reiterwechsel oder ein Fenster, das den Fokus verliert (Alt-Tab mit gehaltenem
W), lassen alle Tasten los und schreiben Stillstand -- Qt schickt in dem Fall
kein KeyRelease mehr, und der Takt frischte den letzten Befehl sonst blind auf.
Stopp und NOT-AUS delegieren an die Live-Ansicht bzw. den Kopf: dasselbe
Objekt mit demselben Zustand, kein zweiter Weg.

Diese Ansicht importiert weder `bosdyn` noch `spotlab.backends`.
"""

import math
import time
from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.tastenfahrt import Tastenfahrt
from spotlab.gui.tastenfeld import Tastenfeld
from spotlab.record import ansicht as ansichtsschalter
from spotlab.record import fahrt

VORGABE_STUFE = "langsam"             # am echten Roboter gemächlich anfangen

HINWEIS = (
    'Startet das Programm „fahren.py“ aus dem Projekt Beispiele am ECHTEN Spot — mit Lease, '
    "Not-Aus-Endpunkt und den Tempogrenzen aus der Konfiguration, aufgezeichnet wie jeder Lauf. "
    "Tasten: W/S vor und zurück · A/D seitwärts · Q/E drehen · 1/2/3 Tempo · "
    "Leertaste oder Esc hält. "
    "Losgelassen heisst Stopp (Totmannschalter, ½ s); stirbt die GUI, steht Spot nach einer "
    "Sekunde. Freifläche, Aufsicht, Tablet mit Not-Aus in Reichweite — "
    "vor dem ersten Mal Abnahmepunkt A1 (docs/ABNAHME.md)."
)
# Immer sichtbar -- der lange HINWEIS klappt darunter auf („Hinweise“).
SICHERHEIT = (
    "⚠ Echter Spot: Freifläche, Aufsicht, Tablet mit Not-Aus in Reichweite. "
    "Losgelassen heisst Stopp."
)
KEIN_BILD = "Kein Bild — der Blick kommt, sobald der Lauf steht."

GESICHT_HINWEIS = (
    "Die Kästen sind das, was der Erkenner setzt — OHNE die Tiefen-Gegenprobe des "
    "Folgemodus. Ein Fehltreffer (eine Stuhllehne, ein Schienbein) bekommt hier "
    "genauso einen Kasten wie ein Gesicht. Die Zahl ist die Punktzahl."
)
GESICHT_WERKZEUG = (
    "Zeichnet die Kästen des Gesichtserkenners in den Blick — im Laufprozess, nicht "
    "im Fenster. Ohne Tiefenmessung: was hier steht, ist der rohe Befund von YuNet."
)
HAND_HINWEIS = (
    "Der Handkasten kommt aus dem Rumpf-Ausschnitt des gefundenen Körpers, wie im "
    'Folgemodus: „Halt“ ist die offene Hand aufrecht, „Weiter“ der Daumen hoch, sonst '
    'steht nur „Hand“. Kostet Bildrate: ohne Mensch im Bild sucht der Körpererkenner '
    "jedes Bild neu (rund 0.4 s), mit Mensch trägt die Spur."
)
HAND_WERKZEUG = (
    "Zeichnet die Hände des gefundenen Körpers mit dem gelesenen Zeichen in den Blick — "
    "im Laufprozess. Braucht die Körper- und Handmodelle; fehlen sie, steht es rot im Bild."
)
LAGE_HINWEIS = (
    "Lage — vorher: Motoren am Tablet AUS (sonst kann spotlab seinen Not-Aus nicht eintragen), "
    "Spot sitzt auf ebenem Boden mit einem Meter Platz auf der Rollseite, das Lease ist frei "
    "oder wird übernommen. Die Akku-Haltung ist das Weiteste, was die API rollt (etwa 130°); "
    "ganz auf den Rücken, etwa für den Koffer, kippt man ihn von dort von Hand. "
    "„Aufrichten“ ist auch der Weg aus der Rückenlage nach dem Auspacken."
)
AKKU_WERKZEUG = (
    "Spot setzt sich, rollt zur gewählten Seite in die Batteriewechsel-Haltung und schaltet "
    "die Motoren ab. Ein eigener Lauf mit Lease, Not-Aus-Endpunkt und Aufzeichnung, am ECHTEN "
    "Spot. Nach dem Wechsel startet der Roboter neu — danach „Aufrichten“. "
    "Motoren vorher aus, ebener Boden, Platz, Lease frei oder übernommen."
)
AUFRICHTEN_WERKZEUG = (
    "Self-right: Spot rollt sich auf die Füsse und setzt sich hin — aus der Seiten- oder "
    "Rückenlage, nach dem Akkuwechsel oder dem Auspacken. Ein eigener Lauf am ECHTEN Spot. "
    "Motoren vorher aus, Platz rundum, Lease frei oder übernommen."
)
UEBERNEHMEN_WERKZEUG = (
    "Nimmt die Kontrolle, egal wer sie hält — das Tablet oder ein abgestürzter Lauf. "
    "Eine bewusste Handlung, sie wird als „lease_übernommen“ aufgezeichnet. Gilt für die "
    "Fahrt und für die Lage-Knöpfe. Ohne Häkchen bricht der Start ab, wenn jemand anders hält."
)
NOTAUS_HINWEIS = (
    "Nach dem NOT-AUS: der Lauf wurde hart getötet und konnte das Lease nicht zurückgeben — "
    "der Spot hängt jetzt an einem toten Prozess, gesteuert wird er von niemandem. "
    "Häkchen „🔓 Kontrolle übernehmen“ setzen und neu starten. Der Not-Aus-Endpunkt wird "
    "beim nächsten Verbinden von selbst ersetzt, solange die Motoren aus sind."
)


class Bildfeld(QWidget):
    """Zeigt ein Bild so gross wie möglich, im Seitenverhältnis, ohne eigene Farben.

    Kein `QLabel` mit vorskaliertem Pixmap: das skalierte bei jedem Bild ein
    zweites Mal auf dem GUI-Thread. Hier wird nur beim Zeichnen skaliert, und
    nur in die Grösse, die das Feld gerade hat.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setze(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def leeren(self):
        self._pixmap = None
        self.update()

    def hat_bild(self):
        return self._pixmap is not None

    def pixmap(self):
        return self._pixmap

    def paintEvent(self, _ereignis):
        if self._pixmap is None:
            return
        maler = QPainter(self)
        maler.setRenderHint(QPainter.SmoothPixmapTransform)
        groesse = self._pixmap.size().scaled(self.size(), Qt.KeepAspectRatio)
        ziel = QRect(0, 0, groesse.width(), groesse.height())
        ziel.moveCenter(self.rect().center())
        maler.drawPixmap(ziel, self._pixmap)


class FahrenView(QWidget):
    fahrt_gewuenscht = Signal(bool)    # beginnen oder beenden, mit Uebernahme -- die App entscheidet
    stopp_gewuenscht = Signal()
    lage_gewuenscht = Signal(str, str, bool)   # Aktion (akku|aufrichten), Seite, Lease uebernehmen
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._laeuft = False
        self._lauf_dir = None
        self._lage_laeuft = False

        titel = QLabel("Den echten Spot über die Tastatur fahren")
        titel.setObjectName("Titel")
        # Die Sicherheitszeile steht immer; der lange Text klappt auf. Nichts davon
        # ist weg -- die UX-Pruefung vom 23.09.2026 fand eine Textwand ueber einem
        # kleinen Kamerabild.
        self.sicherheit = QLabel(SICHERHEIT)
        self.sicherheit.setObjectName("Warnung")
        self.sicherheit.setWordWrap(True)
        self.mehr = QPushButton("Hinweise ▾")
        self.mehr.setCheckable(True)
        self.mehr.setToolTip("Was der Knopf startet, die Tasten, der Totmannschalter, Abnahmepunkt A1")
        self.hinweis = QLabel(HINWEIS)
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)
        self.hinweis.hide()
        self.mehr.toggled.connect(self.hinweis.setVisible)

        self.start = QPushButton("🎮 Fahrt beginnen")
        self.start.setObjectName("Primaer")
        self.start.clicked.connect(self._start_geklickt)
        self.stufe = QComboBox()
        self.stufe.setToolTip("Tempostufe — auch mit den Tasten 1, 2, 3 während der Fahrt")
        for name, faktor in fahrt.STUFEN:
            self.stufe.addItem(f"{name.capitalize()} — {fahrt.TEMPO_M_S * faktor:.1f} m/s", name)
        self.stufe.setCurrentIndex(self.stufe.findData(VORGABE_STUFE))
        self.stufe.currentIndexChanged.connect(self._stufe_gewaehlt)
        self.stopp = QPushButton("■ Stopp")
        self.stopp.setEnabled(False)
        self.stopp.clicked.connect(self._stopp_geklickt)

        # Der Schalter reist als `ansicht.json` ins Lauf-Verzeichnis; gelesen und
        # gezeichnet wird im Laufprozess (`workshop/blick.py`). Die GUI bekommt
        # davon nur ein Bild, in dem Kästen stehen -- sie rechnet selbst nichts,
        # und YuNet läuft nie im Fenster-Thread.
        self.gesicht = QCheckBox("👤 Gesichtserkennung")
        self.gesicht.setEnabled(False)
        self.gesicht.setToolTip(GESICHT_WERKZEUG)
        self.gesicht.toggled.connect(self._gesicht_umgelegt)
        # Ein zweiter Schalter, nicht derselbe: die Hand kostet die Körpersuche,
        # und wer nur Gesichter sehen will, soll die nicht mitbezahlen.
        self.hand = QCheckBox("✋ Handzeichen")
        self.hand.setEnabled(False)
        self.hand.setToolTip(HAND_WERKZEUG)
        self.hand.toggled.connect(self._hand_umgelegt)
        # EIN Haekchen fuer diesen Reiter: es geht immer um dieselbe Frage, wer steuert --
        # das Tablet oder ein vom NOT-AUS getoeteter Lauf, der sein Lease nie zurueckgab.
        # Deshalb steht es bei den Knoepfen und nicht in der Lage-Zeile.
        self.uebernehmen = QCheckBox("🔓 Kontrolle übernehmen")
        self.uebernehmen.setToolTip(UEBERNEHMEN_WERKZEUG)

        fahrt_gruppe = QGroupBox("Fahrt")
        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.start)
        knoepfe.addWidget(self.stopp)
        knoepfe.addSpacing(12)
        knoepfe.addWidget(QLabel("Tempo"))
        knoepfe.addWidget(self.stufe)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.uebernehmen)
        im_blick = QHBoxLayout()
        blick = QLabel("Im Blick einzeichnen:")
        blick.setObjectName("Gedaempft")
        im_blick.addWidget(blick)
        im_blick.addWidget(self.gesicht)
        im_blick.addWidget(self.hand)
        im_blick.addStretch(1)
        innen = QVBoxLayout(fahrt_gruppe)
        innen.addLayout(knoepfe)
        innen.addLayout(im_blick)

        # Die Lage: Akku wechseln (auf die Seite rollen) und Aufrichten. Kein eigener
        # Weg zum Roboter -- jeder Knopf startet einen Lauf ueber die App, mit dem
        # Paketcode `workshop/lage.py` (wie der Gehzeit-Knopf: der Knopf verspricht
        # eine bestimmte Bewegung, und die Kopie im Arbeitsordner kann jemand
        # bearbeitet haben). Die Uebernahme des Leases ist ein Haekchen, nie Vorgabe.
        # Die Seite gilt NUR fuer den Akkuwechsel: `lage.aufrichten` liest sie nie.
        # Ein Auswahlfeld neben zwei Knoepfen, das nur fuer einen gilt, ist ein
        # Haekchen ohne Wirkung -- deshalb steht das in der Beschriftung.
        self.seite_beschriftung = QLabel("Akku-Seite")
        self.seite = QComboBox()
        self.seite.setToolTip("Zu welcher Seite Spot sich beim Akkuwechsel legt. "
                              "Fuer das Aufrichten spielt sie keine Rolle.")
        self.seite.addItem("nach links", "links")
        self.seite.addItem("nach rechts", "rechts")
        self.akku = QPushButton("🔋 Akku wechseln")
        self.akku.setToolTip(AKKU_WERKZEUG)
        self.akku.clicked.connect(self._akku_geklickt)
        self.aufrichten = QPushButton("⬆ Aufrichten")
        self.aufrichten.setToolTip(AUFRICHTEN_WERKZEUG)
        self.aufrichten.clicked.connect(self._aufrichten_geklickt)
        self.lage_zustand = QLabel("")
        self.lage_zustand.setObjectName("Gedaempft")
        self.lage_zustand.setWordWrap(True)
        self.lage_zustand.hide()             # erst, wenn es etwas zu sagen gibt
        self.lage_hinweis = QLabel(LAGE_HINWEIS)
        self.lage_hinweis.setObjectName("Gedaempft")
        self.lage_hinweis.setWordWrap(True)

        lage_gruppe = QGroupBox("Lage — Akku wechseln und Aufrichten")
        lage = QHBoxLayout()
        lage.addWidget(self.seite_beschriftung)
        lage.addWidget(self.seite)
        lage.addWidget(self.akku)
        lage.addWidget(self.aufrichten)
        lage.addStretch(1)
        lage_innen = QVBoxLayout(lage_gruppe)
        lage_innen.addLayout(lage)
        lage_innen.addWidget(self.lage_zustand)
        lage_innen.addWidget(self.lage_hinweis)

        # Der Blick nach vorn: `workshop/blick.py` schreibt `ansicht.jpg` (beide
        # Frontkameras zu einem Bild) ins Lauf-Verzeichnis, der Watcher meldet
        # jede Aenderung mit bis zu 60 Hz. Die GUI holt sich nichts vom Roboter
        # -- die Platte bleibt der einzige Kanal.
        self.hinweis_bild = QLabel(KEIN_BILD)
        self.hinweis_bild.setObjectName("Gedaempft")
        self.hinweis_bild.setAlignment(Qt.AlignCenter)
        self.bild = Bildfeld()
        self.bild.hide()
        self.bildrate = QLabel("")
        self.bildrate.setObjectName("Gedaempft")
        self._bilder_seit = 0
        self._rate_beginn = None
        self.gesicht_hinweis = QLabel(GESICHT_HINWEIS)
        self.gesicht_hinweis.setObjectName("Gedaempft")
        self.gesicht_hinweis.setWordWrap(True)
        self.gesicht_hinweis.hide()
        self.hand_hinweis = QLabel(HAND_HINWEIS)
        self.hand_hinweis.setObjectName("Gedaempft")
        self.hand_hinweis.setWordWrap(True)
        self.hand_hinweis.hide()
        self.notaus_hinweis = QLabel(NOTAUS_HINWEIS)
        self.notaus_hinweis.setObjectName("Gedaempft")
        self.notaus_hinweis.setWordWrap(True)
        self.notaus_hinweis.hide()

        # Rechts neben dem Bild: welche Tasten gedrueckt sind, die Stufe, ob die
        # Tastatur faehrt -- und was Spot daraus macht.
        self.tastenfeld = Tastenfeld()
        self.befehl_zeile = QLabel("Spot steht.")
        self.befehl_zeile.setWordWrap(True)
        self.zustand = QLabel("Kein Lauf.")
        self.zustand.setObjectName("Gedaempft")
        self.zustand.setWordWrap(True)

        kopf = QHBoxLayout()
        kopf.addWidget(titel, 1)
        kopf.addWidget(self.mehr)

        bildspalte = QVBoxLayout()
        bildspalte.addWidget(self.hinweis_bild, 1)
        bildspalte.addWidget(self.bild, 1)
        bildspalte.addWidget(self.bildrate)
        bildspalte.addWidget(self.gesicht_hinweis)
        bildspalte.addWidget(self.hand_hinweis)
        seite = QVBoxLayout()
        seite.addWidget(self.tastenfeld)
        seite.addWidget(self.befehl_zeile)
        seite.addStretch(1)
        mitte = QHBoxLayout()
        mitte.addLayout(bildspalte, 1)
        mitte.addLayout(seite)

        anordnung = QVBoxLayout(self)
        anordnung.addLayout(kopf)
        anordnung.addWidget(self.sicherheit)
        anordnung.addWidget(self.hinweis)
        anordnung.addWidget(fahrt_gruppe)
        anordnung.addWidget(self.notaus_hinweis)
        anordnung.addLayout(mitte, 1)
        anordnung.addWidget(self.zustand)
        anordnung.addWidget(lage_gruppe)

        self.tastenfahrt = Tastenfahrt(self)
        self.tastenfahrt.befehl.connect(self._zeige_befehl)
        self.tastenfahrt.stufe_geaendert.connect(self._zeige_stufe)
        self.tastenfahrt.setze_stufe(VORGABE_STUFE)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._app_zustand)

    # ------------------------------------------------------------- Zustand

    def laeuft(self):
        return self._laeuft

    def lauf_beginnt(self, lauf_dir, name="fahren.py"):
        """Der Watcher hat den Lauf gemeldet: ab jetzt fahren die Tasten."""
        self._laeuft = True
        self._lauf_dir = Path(lauf_dir)
        self.tastenfahrt.beginne(lauf_dir)
        self.start.setText("■ Fahrt beenden")
        self.stopp.setEnabled(True)
        # Die Übernahme ist verbraucht: sie gilt für EINEN Start, nie als Vorgabe --
        # sonst nahm jede spätere Fahrt dem Tablet das Lease wortlos weg.
        self.uebernehmen.setChecked(False)
        self.notaus_hinweis.hide()          # es läuft wieder etwas: erledigt
        self._lageknoepfe(False)          # waehrend der Fahrt legt er sich nicht hin
        self.gesicht.setEnabled(True)
        self.hand.setEnabled(True)
        # Die Häkchen bleiben über Läufe hinweg stehen, die Datei aber nicht: sie
        # gehört dem Lauf. Ohne diese Zeile stünde das Häkchen und der neue Lauf
        # erkennte nichts -- ein Schalter, der lügt.
        self._schreibe_schalter()
        self._zustand_normal()
        self.zustand.setText(f"{name} läuft — Tasten sind scharf.")
        self.tastenfeld.zeige_aktiv(True)
        self._tastatur_greifen()

    def _zustand_normal(self):
        if self.zustand.objectName() == "Gefahr":
            self.zustand.setObjectName("")
            self.zustand.style().unpolish(self.zustand)
            self.zustand.style().polish(self.zustand)

    def lauf_beendet(self):
        self.tastenfahrt.beende()
        self._laeuft = False
        self._lauf_dir = None
        self._tastatur_loslassen()
        self.start.setText("🎮 Fahrt beginnen")
        self.stopp.setEnabled(False)
        self._lageknoepfe(not self._lage_laeuft)
        # Grau, aber nicht abgehakt: die Wahl des Menschen gilt für den nächsten Lauf.
        self.gesicht.setEnabled(False)
        self.gesicht_hinweis.hide()
        self.hand.setEnabled(False)
        self.hand_hinweis.hide()
        self.tastenfeld.zeige_aktiv(False)
        self.befehl_zeile.setText("Spot steht.")
        self.zustand.setText("Kein Lauf.")
        self.bild.leeren()
        self.bild.hide()
        self.hinweis_bild.show()
        self.bildrate.setText("")
        self._bilder_seit, self._rate_beginn = 0, None

    def zeige_ansicht(self, pfad, jetzt=time.monotonic):
        """Das neueste Bild des Laufs (`ansicht.jpg`) -- und die erreichte Bildrate."""
        # Gleicher Dateiname, neue Bytes: den dateibasierten QPixmap-Cache umgehen
        # (derselbe Weg wie im Uebungsfenster). Die Datei ist vor dem Dekodieren zu.
        try:
            daten = Path(pfad).read_bytes()
        except OSError:
            return                               # gerade ersetzt: der naechste Takt bringt es
        pixmap = QPixmap()
        if not pixmap.loadFromData(daten):       # halb geschrieben: das letzte Bild bleibt
            return
        self.bild.setze(pixmap)
        if self.bild.isHidden():
            self.hinweis_bild.hide()
            self.bild.show()
        self._zaehle_bild(jetzt())

    def _zaehle_bild(self, t):
        if self._rate_beginn is None:
            self._rate_beginn = t
            return
        self._bilder_seit += 1
        dauer = t - self._rate_beginn
        if dauer >= 1.0:
            self.bildrate.setText(f"Blick: {self._bilder_seit / dauer:.0f} Bilder/s")
            self._bilder_seit, self._rate_beginn = 0, t

    def zeige_zustand(self, satz):
        daten = satz.get("daten") or {}
        pose = daten.get("pose") or [0.0, 0.0, 0.0]
        tempo = daten.get("velocity") or [0.0, 0.0, 0.0]
        akku = daten.get("battery")
        text = (f"Position {pose[0]:.2f} / {pose[1]:.2f} m · Blick {math.degrees(pose[2]):.0f}° · "
                f"Tempo {tempo[0]:.2f} m/s")
        if akku is not None:
            text += f" · Akku {akku:.0f} %"
        self.zustand.setText(text)

    # -------------------------------------------------------------- Knoepfe

    def zeige_startfehler(self, text):
        """Der Lauf, auf den der Tab wartete, ist gescheitert, bevor er verbunden war --
        hier, wo der Knopf gedrueckt wurde, nicht in einer anderen Ansicht."""
        self.zustand.setObjectName("Gefahr")
        self.zustand.setText(text)
        self.zustand.style().unpolish(self.zustand)
        self.zustand.style().polish(self.zustand)

    def _start_geklickt(self):
        # Am `clicked`-Signal: Qt reicht `checked` herein, deshalb kein Parameter.
        self.fahrt_gewuenscht.emit(self.uebernehmen.isChecked())

    def nach_notaus(self, getoetet=True):
        """Ein Lauf wurde wirklich hart getötet: hier steht, wie man zurückkommt.

        Der Knopf tötet den Lauf hart, damit er nicht auf einen sauberen Abbau
        warten muss — der Preis ist ein Lease, das an einem toten Prozess hängt.
        Das Häkchen wird NICHT gesetzt: Übernehmen bleibt eine Handlung des Menschen.

        `getoetet=False` heisst: es lief nichts, oder das Töten ist GESCHEITERT.
        Dann wäre der Satz falsch — im zweiten Fall sogar gefährlich, weil er zur
        Lease-Übernahme schickt, während der Roboter weiterfährt.
        """
        if getoetet:
            self.notaus_hinweis.show()

    def _stopp_geklickt(self):
        self.tastenfahrt.alle_los()
        self.stopp_gewuenscht.emit()

    # ----------------------------------------------------------------- Lage

    def _akku_geklickt(self):
        self.lage_gewuenscht.emit("akku", self.seite.currentData(), self.uebernehmen.isChecked())

    def _aufrichten_geklickt(self):
        self.lage_gewuenscht.emit("aufrichten", self.seite.currentData(), self.uebernehmen.isChecked())

    def _lageknoepfe(self, an):
        self.akku.setEnabled(an)
        self.aufrichten.setEnabled(an)

    def lage_beginnt(self, aktion):
        """Die App hat den Lauf gestartet: Fahrt und Lage sind gesperrt, bis er endet."""
        self._lage_laeuft = True
        self.start.setEnabled(False)
        self._lageknoepfe(False)
        self.uebernehmen.setChecked(False)          # verbraucht, wie bei der Fahrt
        # Der Stopp hier: im Kopf gibt es nur den NOT-AUS, und der bricht hart ab --
        # mitten im Rollen. Der Stopp lässt das Programm sauber enden.
        self.stopp.setEnabled(True)
        name = "Akku wechseln" if aktion == "akku" else "Aufrichten"
        self.lage_zustand.setText(f"{name} läuft — Spot bewegt sich. „■ Stopp“ hier, Not-Aus am Tablet.")
        self.lage_zustand.show()
        self.zustand.setText(f"{name} läuft.")

    def zeige_lage_zeile(self, zeile):
        """Die letzte Ausgabezeile des Lage-Laufs (Rollwinkel, Befund) -- dort, wo der Knopf ist."""
        if not self._lage_laeuft:
            return
        text = str(zeile).strip()
        if text:
            self.lage_zustand.setText(text)

    def lage_beendet(self):
        if not self._lage_laeuft:
            return
        self._lage_laeuft = False
        self.start.setEnabled(True)
        self.stopp.setEnabled(self._laeuft)
        self._lageknoepfe(not self._laeuft)
        self.zustand.setText("Kein Lauf.")

    def _gesicht_umgelegt(self, an):
        self.gesicht_hinweis.setVisible(bool(an) and self._laeuft)
        self._schreibe_schalter()

    def _hand_umgelegt(self, an):
        self.hand_hinweis.setVisible(bool(an) and self._laeuft)
        self._schreibe_schalter()

    def _schreibe_schalter(self):
        """Beide Schalterstände in den laufenden Lauf schreiben — mehr tut die GUI nicht.

        Ohne Lauf gibt es kein Verzeichnis; dann bleibt das Häkchen eine Absicht,
        bis der nächste Lauf beginnt.
        """
        if self._lauf_dir is None:
            return
        ansichtsschalter.schreibe(self._lauf_dir, gesicht=self.gesicht.isChecked(),
                                  hand=self.hand.isChecked())

    def _stufe_gewaehlt(self, _index):
        name = self.stufe.currentData()
        if name and name != self.tastenfahrt.stufe:
            self.tastenfahrt.setze_stufe(name)

    def _zeige_stufe(self, name):
        self.tastenfeld.zeige_stufe(name)
        # Per Ziffer gewechselt: die Auswahl folgt, ohne noch einmal zu setzen.
        if self.stufe.currentData() != name:
            self.stufe.blockSignals(True)
            self.stufe.setCurrentIndex(self.stufe.findData(name))
            self.stufe.blockSignals(False)

    # -------------------------------------------------------------- Tasten

    def keyPressEvent(self, ereignis):
        if self.tastenfahrt.tastenereignis(ereignis, gedrueckt=True):
            ereignis.accept()
            return
        super().keyPressEvent(ereignis)

    def keyReleaseEvent(self, ereignis):
        if self.tastenfahrt.tastenereignis(ereignis, gedrueckt=False):
            ereignis.accept()
            return
        super().keyReleaseEvent(ereignis)

    def _zeige_befehl(self, vx, vy, wz):
        self.tastenfeld.zeige_tasten(self.tastenfahrt.tasten)
        teile = []
        if vx:
            teile.append(f"{'vor' if vx > 0 else 'zurück'} {abs(vx):.2f} m/s")
        if vy:
            teile.append(f"{'links' if vy > 0 else 'rechts'} {abs(vy):.2f} m/s")
        if wz:
            teile.append(f"drehen {'links' if wz > 0 else 'rechts'} {math.degrees(abs(wz)):.0f}°/s")
        self.befehl_zeile.setText(" · ".join(teile) if teile else "Spot steht.")

    def _app_zustand(self, zustand):
        # Alt-Tab mit gehaltener Taste: kein KeyRelease mehr -- also alle los.
        if zustand != Qt.ApplicationActive and self._laeuft:
            self.tastenfahrt.alle_los()

    # ------------------------------------------------------------ Tastatur

    def _tastatur_greifen(self):
        """Die Tasten gehoeren dem Tab, egal welches Widget den Fokus hat -- aber nur,
        solange er sichtbar ist und ein Lauf lebt."""
        if self._laeuft and self.isVisible():
            self.grabKeyboard()

    def _tastatur_loslassen(self):
        if QWidget.keyboardGrabber() is self:
            self.releaseKeyboard()

    def showEvent(self, ereignis):
        super().showEvent(ereignis)
        self._tastatur_greifen()

    def hideEvent(self, ereignis):
        # Reiterwechsel: Tasten los, Spot steht -- eine gehaltene Taste darf nicht
        # aus einem anderen Reiter heraus weiterfahren.
        self._tastatur_loslassen()
        if self._laeuft:
            self.tastenfahrt.alle_los()
        super().hideEvent(ereignis)
