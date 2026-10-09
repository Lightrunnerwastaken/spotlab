"""Die Ansicht „Fahren“ — die STEUERZENTRALE: sehen, wo Spot ist, und ihn fahren.

Seit dem 27.09.2026 (Entwurf `docs/superpowers/specs/2026-09-27-steuerzentrale-design.md`)
links die Draufsicht (`gui/lagebild.py`: wachsende Skizze mit Boden, Wänden, Tags und
Spot), rechts Kamerabild, Tasten, Licht und Ton. Oben die Wahl, WO gefahren wird:
Übungsraum (Vorgabe — wer nichts einstellt, fährt nicht den Roboter) oder echter Spot.

Kein eigener Weg zum Roboter: der Knopf startet `workshop/zentrale.py` als Paketcode
über die App -- derselbe eine Startweg wie „Starten“ im Editor (`app.py::_starte_zentrale`),
also Lease, Not-Aus-Endpunkt, Geschwindigkeitsdeckel aus `config.toml` und die
Aufzeichnung wie bei jedem Programm. Die Tasten gehen als `fahrt.json` ins
Lauf-Verzeichnis (`gui/tastenfahrt.py`, `record/fahrt.py`), ein Klick in die
Draufsicht als `klickziel.json`, Licht und Ton als `aktion.json` (`record/zentrale.py`);
zurück kommt `lagebild.json` + `.png`. Der Regler „Menschen“ (Teil 2) geht als Aktion
`suche` hinaus; weicht die Stufe im Lagebild ab (eine Aktion kann überschrieben werden, bevor
das Programm sie liest), schickt der Tab sie nach, höchstens alle `SUCHE_NACHSENDEN_S`. Ein
Klick auf einen Menschen wird ein Klickziel der Art `mensch`, an dessen Ort, nicht am
Klickpunkt: dann folgt Spot ihm. Die Zeile „🗺 Karte“ (Teil 3) schickt Kartenaufträge
(`kartenauftrag.json`: laden, Aufnahme starten/beenden, Wegpunkt) und schickt einen nach, den
das Lagebild nach `KARTEN_NACHSENDEN_S` noch nicht bestätigt hat; das Kartenbild kommt als
`lagebild_karte.png`. **Ein Befehl aelter als eine halbe Sekunde heisst
Stopp** -- für die Klickfahrt frischt der Tab alle 200 ms ein Lebenszeichen auf, aber nur,
solange er sichtbar ist und das Fenster aktiv. Jedes Kommando traegt eine Endzeit von
rund einer Sekunde: stirbt die GUI oder der Lauf, steht der Roboter.

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

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.kurztext import Kurztext
from spotlab.gui.lagebild import Lagebild
from spotlab.gui.tastenfahrt import Tastenfahrt
from spotlab.gui.tastenfeld import Tastenfeld
from spotlab.record import ansicht as ansichtsschalter
from spotlab.record import fahrt
from spotlab.record import zentrale as protokoll

VORGABE_STUFE = "langsam"             # am echten Roboter gemächlich anfangen
HERZSCHLAG_MS = 200                   # Lebenszeichen der Klickfahrt
GUI_PULS_S = 1.0                      # Puls der Oberfläche (record/zentrale.GUI_PULS)
LAGEBILD_MS = 100                     # so oft schaut der Tab nach einem neuen Lagebild
# Kurz, weil das Feld in der Knopfzeile steht: die Namen aus dem Entwurf („Übungsraum 3D
# (Wiedergabe)“, „Übungsraum Physik“) machten das Fenster 69 px breiter als sein Mindestmass.
# Was die Orte sind, sagt ORT_WERKZEUG.
ORTE = (("🧪 3D-Wiedergabe", "uebungsraum"), ("⚙ 3D-Physik", "physik"), ("🐕 Echter Spot", "real"))
LICHTER = (("💡 Licht aus", "aus"), ("blau", "blau"), ("grün", "gruen"), ("gelb", "gelb"),
           ("rot", "rot"))
NUR_AM_ROBOTER = "Gibt es nur am echten Spot (Dienst audio-visual)."
ORT_WERKZEUG = (
    "Wo gefahren wird. 3D-Wiedergabe: der Übungsraum aus dem Raumeditor, Spot spielt "
    "gemessene Gänge ab — schnell, jeder Raum. 3D-Physik: derselbe Raum, aber "
    "Kontaktkräfte tragen den Körper und ein eigener Kraftregler setzt die Füsse (nicht der von "
    "Boston Dynamics); nur ebene Räume. Echter Spot: mit Lease, Not-Aus-Endpunkt und den "
    "Tempogrenzen aus der Konfiguration."
)
KLICK_HINWEIS = ("Klick in die Draufsicht: Spot geht dorthin (höchstens 5 m, nur auf gesehenen "
                 "Boden). Klick auf einen Menschen: Spot folgt ihm.")
# Die Menschensuche: wie viel Rechenzeit sie bekommt. Vorgabe sparsam -- wer mehr will,
# schiebt; der Laptop soll neben dem Fahren nicht voll ausgelastet sein.
VORGABE_SUCHE = "sparsam"
SUCHSTUFEN_TEXT = {"aus": "Aus", "sparsam": "Sparsam — vorne, alle 2 s",
                   "normal": "Normal — vorne, so oft es geht",
                   "rundum": "Rundum — vorne, links, rechts, hinten"}
SUCHE_WERKZEUG = (
    "Wie viel Rechenzeit die Menschensuche bekommt. Aus: keine. Sparsam: die Frontkameras, "
    "eine Runde alle 2 s. Normal: die Frontkameras, so oft es geht (rund ein Rechenkern). "
    "Rundum: dazu die Seiten- und die Rückkamera, über eine Sekunde je Runde. Gefunden wird "
    "wie beim Folgen: YOLOX, Skelett, Abstand aus der Tiefenkamera. Ein Klick auf einen "
    "Menschen in der Draufsicht: Spot folgt ihm."
)
SUCHE_NACHSENDEN_S = 1.5
KARTEN_NACHSENDEN_S = 1.5
KEIN_GRAPHNAV = "Karten gibt es nur am echten Spot (GraphNav)."
AUFNAHME_ZUSTAENDE = ("nimmt_auf", "speichert", "nicht_gespeichert")
KARTEN_WERKZEUG = (
    "Karten wie im Tab „Karten“, aber aus der Zentrale: „Laden“ legt eine gespeicherte Karte auf "
    "den Roboter und verortet Spot an einem AprilTag. „● Aufnahme“ nimmt auf, während du fährst "
    "(Tasten, Klick, Folgen) — verortet in einer geladenen Karte wird sie WEITERGEFÜHRT, sonst "
    "beginnt eine neue. Gespeichert wird unter dem Namen im Feld, nie über eine vorhandene Karte. "
    "In der Draufsicht: grün erkannt, rot neu, gestrichelt fehlt, blass nicht geprüft."
)
MENSCH_KLICK_M = 0.5                  # so weit neben einem Menschen gilt ein Klick als seiner

HINWEIS = (
    "Startet die Steuerzentrale (Programm „zentrale.py“) im Übungsraum oder am ECHTEN Spot — "
    "am Roboter mit Lease, Not-Aus-Endpunkt und den Tempogrenzen aus der Konfiguration, "
    "aufgezeichnet wie jeder Lauf. Links die Draufsicht: hell ist gesehener Boden, dunkel eine "
    "Wand, grau unbekannt; ein Klick schickt Spot dorthin, er geht um Hindernisse herum. "
    "Unter der Draufsicht der Regler „Menschen“: wie viel Rechenzeit die Menschensuche "
    "bekommt (am echten Spot); ein Klick auf einen Menschen, und Spot folgt ihm, bis eine "
    "Taste, ein neuer Klick oder Stopp kommt. "
    "Tasten: W/S vor und zurück · A/D seitwärts · Q/E drehen · 1/2/3 Tempo · "
    "Leertaste oder Esc hält, jede Taste beendet eine Klickfahrt. "
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
KEINE_KAMERA = ("Hier gibt es keine Kamera (2D-Übungsraum) — was Spot „sieht“, zeigt "
                "die Draufsicht links.")

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
        self.setMinimumHeight(160)
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

    def __init__(self, palette=None, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._laeuft = False
        self._lauf_dir = None
        self._puls_t = None              # Wanduhr des letzten Pulses der Oberfläche
        self._lage_laeuft = False
        self._klick_nummer = 0
        self._klick_ziel = None
        self._klick_art = "ort"
        self._aktion_nummer = 0
        self._suche_gesendet = None      # (Stufe, Uhr) der zuletzt geschickten Suchstufe
        self._arbeitsordner = None
        self._karten_nummer = 0
        self._karten_gesendet = None     # [Nummer, was, Name, Uhr] des zuletzt geschickten Auftrags
        self._karte = None               # der Platz `karte` aus dem letzten Lagebild
        self._name_beruehrt = False      # hat jemand den Namen selbst getippt?
        self._frage_name = self._frage_wegpunkt_name
        self._lagebild_stempel = None
        self._app_aktiv = True

        titel = QLabel("Steuerzentrale — sehen, wo Spot ist, und ihn fahren")
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

        self.ort_wahl = QComboBox()
        for name, wert in ORTE:
            self.ort_wahl.addItem(name, wert)
        self.ort_wahl.setToolTip(ORT_WERKZEUG)
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
        knoepfe.addWidget(self.ort_wahl)
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

        # Die Draufsicht der Zentrale: gezeichnet wird, was der Lauf als `lagebild.*`
        # schreibt; ein Klick wird zum Klickziel.
        self.lagebild = Lagebild(palette)
        self.lagebild.klick.connect(self._klick)
        self.mitte_knopf = QPushButton("⌖ Mitte")
        self.mitte_knopf.setToolTip("Die Draufsicht folgt wieder Spot (Ziehen verschiebt, "
                                    "Mausrad zoomt)")
        self.mitte_knopf.clicked.connect(self.lagebild.mitte)
        self.klick_zeile = QLabel(KLICK_HINWEIS)
        self.klick_zeile.setObjectName("Gedaempft")
        self.klick_zeile.setWordWrap(True)
        # Der Regler der Menschensuche: vier Stufen, grau, bis das Lagebild sagt, dass
        # der Lauf Menschen suchen KANN (Bild- und Tiefenkameras).
        self.suche_regler = QSlider(Qt.Horizontal)
        self.suche_regler.setRange(0, len(protokoll.SUCHSTUFEN) - 1)
        self.suche_regler.setPageStep(1)
        self.suche_regler.setTickPosition(QSlider.TicksBelow)
        self.suche_regler.setTickInterval(1)
        self.suche_regler.setMaximumWidth(140)
        self.suche_regler.setValue(protokoll.SUCHSTUFEN.index(VORGABE_SUCHE))
        self.suche_regler.setEnabled(False)
        self.suche_regler.setToolTip(SUCHE_WERKZEUG)
        self.suche_regler.valueChanged.connect(self._suche_gewaehlt)
        self.suche_text = Kurztext(SUCHSTUFEN_TEXT[VORGABE_SUCHE])
        self.suche_text.setObjectName("Gedaempft")
        # Die Kartenzeile (Teil 3): alles grau, bis das Lagebild sagt, dass der Lauf GraphNav hat.
        self.karten_wahl = QComboBox()
        self.karten_wahl.setToolTip(KARTEN_WERKZEUG)
        self.laden = QPushButton("Laden")
        self.laden.setToolTip("Die gewählte Karte auf den Roboter laden und am AprilTag verorten")
        self.laden.clicked.connect(self._laden_geklickt)
        self.karten_name = QLineEdit()
        self.karten_name.setPlaceholderText("Name der Aufnahme")
        self.karten_name.setMaximumWidth(170)
        self.karten_name.textEdited.connect(self._name_getippt)
        self.aufnahme = QPushButton("● Aufnahme")
        self.aufnahme.setToolTip(KARTEN_WERKZEUG)
        self.aufnahme.clicked.connect(self._aufnahme_geklickt)
        self.wegpunkt = QPushButton("📍 Wegpunkt")
        self.wegpunkt.setToolTip("Eine benannte Marke an Spots Ort setzen (nur während der Aufnahme)")
        self.wegpunkt.clicked.connect(self._wegpunkt_geklickt)
        self.karten_zeile = Kurztext("")
        self.karten_zeile.setObjectName("Gedaempft")
        self._karten_knoepfe(False, False, False)
        self.licht = QComboBox()
        for name, wert in LICHTER:
            self.licht.addItem(name, wert)
        self.licht.setEnabled(False)
        self.licht.setToolTip(NUR_AM_ROBOTER)
        self.licht.currentIndexChanged.connect(self._licht_gewaehlt)
        self.ton = QPushButton("🔔 Piep")
        self.ton.setEnabled(False)
        self.ton.setToolTip(NUR_AM_ROBOTER)
        self.ton.clicked.connect(self._ton_geklickt)
        self.herzschlag_takt = QTimer(self)
        self.herzschlag_takt.setInterval(HERZSCHLAG_MS)
        self.herzschlag_takt.timeout.connect(self._herzschlag)
        # Ein eigener, schnellerer Takt fürs Lagebild: nachsehen kostet nur ein stat().
        self.lagebild_takt = QTimer(self)
        self.lagebild_takt.setInterval(LAGEBILD_MS)
        self.lagebild_takt.timeout.connect(self._lade_lagebild)

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

        lagespalte = QVBoxLayout()
        lagespalte.addWidget(self.lagebild, 1)
        menschen_zeile = QHBoxLayout()
        menschen_beschriftung = QLabel("👥 Menschen")
        menschen_beschriftung.setToolTip(SUCHE_WERKZEUG)
        menschen_zeile.addWidget(menschen_beschriftung)
        menschen_zeile.addWidget(self.suche_regler)
        menschen_zeile.addWidget(self.suche_text, 1)
        lagespalte.addLayout(menschen_zeile)
        karten_knoepfe = QHBoxLayout()
        karten_beschriftung = QLabel("🗺 Karte")
        karten_beschriftung.setToolTip(KARTEN_WERKZEUG)
        karten_knoepfe.addWidget(karten_beschriftung)
        karten_knoepfe.addWidget(self.karten_wahl, 1)
        karten_knoepfe.addWidget(self.laden)
        karten_knoepfe.addSpacing(8)
        karten_knoepfe.addWidget(self.karten_name)
        karten_knoepfe.addWidget(self.aufnahme)
        karten_knoepfe.addWidget(self.wegpunkt)
        lagespalte.addLayout(karten_knoepfe)
        lagespalte.addWidget(self.karten_zeile)
        unter_lage = QHBoxLayout()
        unter_lage.addWidget(self.klick_zeile, 1)
        unter_lage.addWidget(self.mitte_knopf)
        lagespalte.addLayout(unter_lage)
        licht_ton = QHBoxLayout()
        licht_ton.addWidget(self.licht)
        licht_ton.addWidget(self.ton)
        licht_ton.addStretch(1)
        seite = QVBoxLayout()
        seite.addWidget(self.hinweis_bild, 1)
        seite.addWidget(self.bild, 1)
        seite.addWidget(self.bildrate)
        seite.addWidget(self.gesicht_hinweis)
        seite.addWidget(self.hand_hinweis)
        seite.addWidget(self.tastenfeld)
        seite.addWidget(self.befehl_zeile)
        seite.addLayout(licht_ton)
        mitte = QHBoxLayout()
        mitte.addLayout(lagespalte, 3)
        mitte.addLayout(seite, 2)

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

    def ort(self):
        """Wo die nächste Fahrt läuft: „uebungsraum“ (Vorgabe), „physik“ oder „real“."""
        return self.ort_wahl.currentData()

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
        self._klick_nummer, self._klick_ziel, self._aktion_nummer = 0, None, 0
        self._klick_art = "ort"
        self._suche_gesendet = None
        self._karten_nummer, self._karten_gesendet, self._karte = 0, None, None
        self._name_beruehrt = False
        self._fuelle_karten()
        self._lagebild_stempel = None
        self.lagebild.leeren()
        self.klick_zeile.setText(KLICK_HINWEIS)
        self.ort_wahl.setEnabled(False)
        self._puls_t = None
        self._puls(sofort=True)
        self.herzschlag_takt.start()
        self.lagebild_takt.start()
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
        self.herzschlag_takt.stop()
        self.lagebild_takt.stop()
        self._klick_nummer, self._klick_ziel = 0, None
        self._klick_art = "ort"
        self.lagebild.leeren()
        self.klick_zeile.setText(KLICK_HINWEIS)
        self.suche_regler.setEnabled(False)
        self.suche_text.setText(SUCHSTUFEN_TEXT[self.suchstufe()])
        self._karte, self._karten_gesendet = None, None
        self._karten_knoepfe(False, False, False)
        self.karten_zeile.setText("")
        self.hinweis_bild.setText(KEIN_BILD)
        self.ort_wahl.setEnabled(True)
        self._faehigkeiten({})
        self.licht.blockSignals(True)
        self.licht.setCurrentIndex(0)
        self.licht.blockSignals(False)
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
        if self._laeuft and len(daten.get("pose") or ()) == 3:
            self.lagebild.setze_odom_lage(daten["pose"])     # der Pfeil 10-mal je Sekunde
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
            # Jede Taste übernimmt: eine laufende Klickfahrt endet hier UND im Programm.
            self._klick_abbrechen()
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
        # Alt-Tab mit gehaltener Taste: kein KeyRelease mehr -- also alle los. Und kein
        # Lebenszeichen mehr für die Klickfahrt: ohne Blick aufs Fenster fährt Spot nicht.
        self._app_aktiv = zustand == Qt.ApplicationActive
        if not self._app_aktiv and self._laeuft:
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

    # --------------------------------------------------- Steuerzentrale

    def _klick(self, x, y):
        """Ein Klick in die Draufsicht: ein neues Klickziel -- nur, solange ein Lauf lebt.
        Neben einem Menschen heisst es „folge ihm“, und das Ziel ist SEIN Ort."""
        if not self._laeuft or self._lauf_dir is None:
            return
        self._klick_nummer += 1
        mensch = self.lagebild.mensch_bei(x, y, MENSCH_KLICK_M)
        if mensch is not None:
            self._klick_art = "mensch"
            self._klick_ziel = (float(mensch["x"]), float(mensch["y"]))
            text = "Klick auf einen Menschen — Spot sucht ihn und folgt …"
        else:
            self._klick_art = "ort"
            self._klick_ziel = (float(x), float(y))
            text = f"Klick nach ({x:.1f}, {y:.1f}) m — wird geprüft …"
        self._schreibe_klickziel()
        self.klick_zeile.setText(text)

    def _klick_abbrechen(self):
        if self._klick_ziel is None or self._lauf_dir is None:
            return
        self._klick_nummer += 1
        self._klick_ziel = None
        self._klick_art = "ort"
        self._schreibe_klickziel()

    def _schreibe_klickziel(self, jetzt=time.time):
        protokoll.schreibe_klickziel(self._lauf_dir, self._klick_nummer, self._klick_ziel,
                                     self.tastenfahrt.stufe, jetzt=jetzt, art=self._klick_art)

    def _herzschlag(self, jetzt=time.time):
        """Das Lebenszeichen der Klickfahrt -- nur bei sichtbarem Tab und aktivem Fenster.
        Dazu der Puls der Oberfläche: der kommt aus JEDEM Reiter (siehe `_puls`)."""
        self._puls(jetzt)
        if (self._laeuft and self._lauf_dir is not None and self._klick_nummer
                and self.isVisible() and self._app_aktiv):
            self._schreibe_klickziel(jetzt=jetzt)

    def _puls(self, jetzt=time.time, sofort=False):
        """„Die GUI lebt“, einmal je Sekunde, solange ein Lauf lebt -- egal welcher Reiter vorne
        ist. Bleibt er GUI_FRIST_S aus (Absturz oder Hänger), endet die Zentrale und Spot setzt
        sich (Befund 09.10.2026)."""
        if not self._laeuft or self._lauf_dir is None:
            return
        t = jetzt()
        # abs(): stellt die Zeitsynchronisierung die Wanduhr zurück, käme sonst bis zum Aufholen
        # kein Puls -- und die Zentrale setzte Spot hin, obwohl die GUI lebt.
        if sofort or self._puls_t is None or abs(t - self._puls_t) >= GUI_PULS_S:
            protokoll.schreibe_gui_puls(self._lauf_dir, jetzt=lambda: t)
            self._puls_t = t

    def _lade_lagebild(self):
        """`lagebild.json` + `.png` zeigen, wenn es ein neues gibt -- sonst nichts tun."""
        if self._lauf_dir is None:
            return
        pfad = self._lauf_dir / protokoll.LAGEBILD
        try:
            stempel = pfad.stat().st_mtime_ns
        except OSError:
            return
        if stempel == self._lagebild_stempel:
            return
        daten = protokoll.lies_lagebild(self._lauf_dir)
        if daten is None:
            return                              # halb geschrieben: der nächste Takt
        self._lagebild_stempel = stempel
        try:
            bild = (self._lauf_dir / protokoll.LAGEBILD_BILD).read_bytes()
        except OSError:
            bild = None
        kartenbild = None
        if (daten.get("karte") or {}).get("raster"):
            try:
                kartenbild = (self._lauf_dir / protokoll.LAGEBILD_KARTE).read_bytes()
            except OSError:
                kartenbild = None
        self.lagebild.zeige(daten, bild, kartenbild)
        faehig = daten.get("faehigkeiten") or {}
        self._faehigkeiten(faehig)
        if not self.bild.hat_bild():
            self.hinweis_bild.setText(KEIN_BILD if faehig.get("kamera") else KEINE_KAMERA)
        self.klick_zeile.setText(_klick_text(daten.get("klickfahrt") or {}))
        self._zeige_suche(daten.get("suche"))
        self._zeige_karte(daten.get("karte"))

    # --------------------------------------------------- Karten (Teil 3)

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None
        self._fuelle_karten()

    def _fuelle_karten(self, waehle=None):
        """Die gespeicherten Karten des Arbeitsordners — die Auswahl bleibt, wenn es sie noch gibt."""
        vorher = waehle or self.karten_wahl.currentText()
        namen = []
        if self._arbeitsordner is not None:
            try:
                from spotlab.maps.store import karten

                namen = [k.name for k in karten(self._arbeitsordner)]
            except Exception:
                namen = []
        self.karten_wahl.blockSignals(True)
        self.karten_wahl.clear()
        self.karten_wahl.addItems(namen)
        if vorher in namen:
            self.karten_wahl.setCurrentIndex(namen.index(vorher))
        self.karten_wahl.blockSignals(False)

    def _karten_knoepfe(self, laden, aufnahme, wegpunkt):
        self.laden.setEnabled(laden)
        self.aufnahme.setEnabled(aufnahme)
        self.wegpunkt.setEnabled(wegpunkt)
        self.karten_wahl.setEnabled(laden)
        self.karten_name.setEnabled(aufnahme)

    def _karten_auftrag(self, was, name=None, jetzt=time.monotonic):
        if self._lauf_dir is None:
            return
        self._karten_nummer += 1
        protokoll.schreibe_kartenauftrag(self._lauf_dir, self._karten_nummer, was, name=name)
        self._karten_gesendet = [self._karten_nummer, was, name, jetzt()]

    def _offen(self, karte):
        """Der zuletzt geschickte Auftrag, solange das Lagebild ihn nicht bestätigt hat."""
        g = self._karten_gesendet
        if g is None or karte is None:
            return None
        return g if (karte.get("auftrag") or 0) < g[0] else None

    def _laden_geklickt(self):
        name = self.karten_wahl.currentText()
        if name:
            self._karten_auftrag("laden", name)

    def _aufnahme_geklickt(self):
        zustand = (self._karte or {}).get("zustand")
        name = self.karten_name.text().strip() or None
        if zustand in ("nimmt_auf", "nicht_gespeichert"):
            self._karten_auftrag("aufnahme_stopp", name)
        else:
            self._karten_auftrag("aufnahme_start", name)
        self._name_beruehrt = False

    def _wegpunkt_geklickt(self):
        vorschlag = f"Punkt {((self._karte or {}).get('aufnahme') or {}).get('wegpunkte', 0) + 1}"
        name, ok = self._frage_name(vorschlag)
        if ok:
            self._karten_auftrag("wegpunkt", name.strip() or vorschlag)
            self.wegpunkt.setEnabled(False)          # bis der Auftrag bestätigt ist

    def _frage_wegpunkt_name(self, vorschlag):
        return QInputDialog.getText(self, "Wegpunkt", "Name des Wegpunkts:", text=vorschlag)

    def _name_getippt(self, _text):
        self._name_beruehrt = True

    def _namensvorschlag(self, karte):
        from spotlab.workshop.kartenarbeit import namensvorschlag

        if karte.get("zustand") == "verortet" and karte.get("name"):
            return f"{karte['name']}-2"
        return namensvorschlag()

    def _zeige_karte(self, karte, jetzt=time.monotonic):
        """Knöpfe, Name, Statuszeile und Nachschicken nach dem Platz `karte` im Lagebild."""
        alter_name = (self._karte or {}).get("name")
        self._karte = karte
        if not karte or not karte.get("kann") or not self._laeuft:
            self._karten_knoepfe(False, False, False)
            self.karten_zeile.setText((karte or {}).get("grund") or KEIN_GRAPHNAV)
            return
        zustand = karte.get("zustand") or "keine"
        offen = self._offen(karte)
        if offen is not None and jetzt() - offen[3] > KARTEN_NACHSENDEN_S:
            protokoll.schreibe_kartenauftrag(self._lauf_dir, offen[0], offen[1], name=offen[2])
            offen[3] = jetzt()
        nimmt_auf = zustand in ("nimmt_auf", "nicht_gespeichert")
        beschaeftigt = zustand in ("laedt", "speichert")
        self.aufnahme.setText("■ Aufnahme beenden" if nimmt_auf else "● Aufnahme")
        wegpunkt_offen = offen is not None and offen[1] == "wegpunkt"
        self._karten_knoepfe(
            laden=not nimmt_auf and not beschaeftigt and self.karten_wahl.count() > 0,
            aufnahme=not beschaeftigt,
            wegpunkt=zustand == "nimmt_auf" and not wegpunkt_offen)
        if not nimmt_auf and zustand != "speichert" and not self._name_beruehrt:
            self.karten_name.setText(self._namensvorschlag(karte))
        if karte.get("name") and karte.get("name") != alter_name:
            self._fuelle_karten(waehle=karte["name"])     # eine neu gespeicherte Karte zeigen
        self.karten_zeile.setText(_karten_text(karte))

    # --------------------------------------------------- Menschensuche

    def suchstufe(self):
        return protokoll.SUCHSTUFEN[self.suche_regler.value()]

    def _suche_gewaehlt(self, _wert):
        self.suche_text.setText(SUCHSTUFEN_TEXT[self.suchstufe()])
        if self._lauf_dir is not None and self.suche_regler.isEnabled():
            self._sende_suche()

    def _sende_suche(self, jetzt=time.monotonic):
        self._aktion_nummer += 1
        protokoll.schreibe_aktion(self._lauf_dir, self._aktion_nummer, "suche",
                                  stufe=self.suchstufe())
        self._suche_gesendet = (self.suchstufe(), jetzt())

    def _zeige_suche(self, suche, jetzt=time.monotonic):
        """Regler, Zeile und Nachsenden nach dem Stand der Suche im Lagebild."""
        if not suche or self._lauf_dir is None:
            self.suche_regler.setEnabled(False)
            return
        kann = bool(suche.get("kann")) and self._laeuft
        self.suche_regler.setEnabled(kann)
        grund = suche.get("grund") or ""
        if not kann:
            self.suche_text.setText(grund or SUCHSTUFEN_TEXT[self.suchstufe()])
            return
        text = SUCHSTUFEN_TEXT[self.suchstufe()]
        runde = suche.get("runde_s")
        if suche.get("stufe") == self.suchstufe() and self.suchstufe() != "aus" \
                and runde is not None:
            text += f" · Runde {float(runde):.1f} s"
        if grund:
            text += f" — {grund}"
        self.suche_text.setText(text)
        if suche.get("stufe") != self.suchstufe():
            gesendet = self._suche_gesendet
            if gesendet is None or jetzt() - gesendet[1] > SUCHE_NACHSENDEN_S:
                self._sende_suche(jetzt)

    def _faehigkeiten(self, faehig):
        for knopf, schluessel in ((self.licht, "licht"), (self.ton, "ton")):
            kann = bool(faehig.get(schluessel)) and self._laeuft
            knopf.setEnabled(kann)
            knopf.setToolTip("" if kann else NUR_AM_ROBOTER)

    def _licht_gewaehlt(self, _index):
        if self._lauf_dir is None or not self.licht.isEnabled():
            return
        self._aktion_nummer += 1
        protokoll.schreibe_aktion(self._lauf_dir, self._aktion_nummer, "licht",
                                  self.licht.currentData())

    def _ton_geklickt(self):
        if self._lauf_dir is None:
            return
        self._aktion_nummer += 1
        protokoll.schreibe_aktion(self._lauf_dir, self._aktion_nummer, "ton")


def _karten_text(karte):
    """Der Stand der Karte in einem Satz -- unter der Kartenzeile."""
    zustand = karte.get("zustand") or "keine"
    name, grund = karte.get("name"), karte.get("grund") or ""
    if zustand in ("nimmt_auf", "nicht_gespeichert"):
        auf = karte.get("aufnahme") or {}
        text = (f"Aufnahme läuft ({'weitergeführt' if auf.get('weiter') else 'neu'}): "
                f"{auf.get('wegpunkte', 0)} Wegpunkte, {auf.get('kanten', 0)} Kanten")
        return f"{text} — {grund}" if grund else text
    if zustand in ("laedt", "speichert"):
        return grund
    if zustand == "verloren":
        return f"Karte ‹{name}›: verloren — Spot findet sich in der Karte nicht mehr."
    if zustand == "sucht_tag":
        return f"Karte ‹{name}›: {grund}"
    if zustand == "verortet":
        text = f"Karte ‹{name}›: verortet"
        wieder = karte.get("wiedererkennung") or {}
        abgleiche = (wieder.get("angenommen") or 0) + (wieder.get("abgelehnt") or 0)
        if abgleiche:
            text += f" · Roboter: {wieder['angenommen']} von {abgleiche} angenommen"
        if wieder:
            anteil = wieder.get("anteil")
            text += (f" · {round(anteil * 100)} % der Wände erkannt"
                     if anteil is not None else " · zu wenig Wand im Blick")
        return text
    return grund or "Keine Karte geladen — eine wählen und „Laden“, oder „● Aufnahme“ für eine neue."


def _klick_text(klickfahrt):
    """Der Stand der Klickfahrt in einem Satz -- unter der Draufsicht."""
    zustand = klickfahrt.get("zustand") or "keine"
    grund = klickfahrt.get("grund") or ""
    if zustand == "unterwegs":
        return "Klickfahrt: unterwegs — eine Taste oder „■ Stopp“ hält an."
    if zustand == "angekommen":
        return "Klickfahrt: angekommen."
    if zustand == "abgelehnt":
        return f"Klick abgelehnt: {grund}."
    if zustand == "versperrt":
        return f"Klickfahrt: {grund}."
    if zustand == "folgt":
        return f"Spot {grund} — eine Taste, ein Klick oder „■ Stopp“ beendet das Folgen."
    if zustand == "abgebrochen":
        if grund.startswith("Folgen beendet"):
            return f"{grund}."
        return f"Klickfahrt abgebrochen: {grund}."
    return KLICK_HINWEIS
