"""Der Tab „Raumeditor": Werkzeuge links, Sicht mit Zustandszeile in der Mitte,
Liste, Eigenschaften und Hinweise rechts (feste Breite), der Startknopf unten.

Ersetzt die Ansicht „Übungsraum" und bietet app.py dieselbe Schnittstelle:
`meldung`, `config_gespeichert`, `start_gewuenscht`, `setze_laeuft`,
`setze_arbeitsordner`, `setze_config`, `waehle_raum`, `raum`, `raumname`,
`startpose`, `lade`. DER STARTKNOPF STARTET NICHT SELBST -- er meldet den Wunsch,
und app.py laesst den Editor starten: genau EIN Lauf ist der, auf den Stopp und
NOT-AUS zeigen.

Kein Modell hier: alles, was der Editor kann, steht in `steuerung.py` (ohne Qt).
Dieser Tab uebersetzt Knoepfe, Felder und Dialoge in Aufrufe dorthin.
"""

import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.raumeditor.sicht2d import Sicht2D
from spotlab.gui.raumeditor.sicht3d import Sicht3D, gl_verfuegbar
from spotlab.gui.raumeditor.steuerung import Steuerung
from spotlab.welt import bearbeitung as b
from spotlab.welt import pauspapier
from spotlab.welt.gelaende import zusammenfassung
from spotlab.welt.raum import (
    Raum,
    eigene_raeume,
    raum_laden,
    raum_pfad,
    raum_speichern,
    vorlagen,
)

# Der Startknopf nennt die Datei, die er startet -- sobald app.py sie mitteilt
# (`setze_datei`). Bis dahin der allgemeine Text, und der Knopf bleibt benutzbar.
START_TEXT = "▶ Offene Datei im Übungsraum starten"
START_DATEI = "▶ {name} im Übungsraum starten"
START_OHNE_DATEI = "▶ Im Übungsraum starten"
START_OHNE_DATEI_TIPP = ("Erst im Reiter „Code“ eine Datei öffnen — dieser Knopf startet sie "
                         "dann im Übungsraum, in dem Raum, der hier offen ist.")
STOPP_TEXT = "■ Stopp"
FAHREN_TEXT = "🎮 Selbst fahren"
_UNBEKANNT = object()            # app.py hat (noch) keine Datei gemeldet
WERKZEUGE = (("auswahl", "Auswählen"), ("wand", "Wand"), ("block", "Block"),
             ("boden", "Boden"), ("sperrzone", "Sperrzone"), ("tag", "Tag"),
             ("start", "Start"))
# Je Werkzeug die Bedienung -- die Tasten standen bis zum 23.09.2026 nirgends.
WERKZEUG_TIPPS = {
    "auswahl": "Auswählen — Klick wählt, Umschalt+Klick ergänzt, Ziehen im Leeren zieht einen "
               "Rahmen. Griffe ziehen: Enden, Ecken, Drehung. G bewegt, R dreht, S skaliert, "
               "Entf löscht.",
    "wand": "Wand — Klick setzt Punkte, jeder weitere Klick eine Wand; Esc oder Rechtsklick "
            "beendet. Enden fangen sich an anderen Wänden. Strg: ohne Raster.",
    "block": "Block — ein Rechteck aufziehen (Tisch, Kiste); Höhe und Drehung rechts. "
             "Strg: ohne Raster.",
    "boden": "Boden — ein Rechteck aufziehen: ein Podest; mit Anstieg eine Rampe, mit Stufen "
             "eine Treppe. Strg: ohne Raster.",
    "sperrzone": "Sperrzone — ein Rechteck aufziehen, in das Spot nie fährt (Glasfront, "
                 "Treppenabgang). Strg: ohne Raster.",
    "tag": "Tag — Klick setzt einen AprilTag; die Richtung am Griff ziehen. Strg: ohne Raster.",
    "start": "Start — Klick setzt Spots Startpunkt, Ziehen gibt die Blickrichtung. "
             "Strg: ohne Raster.",
}
RECHTS_BREITE = 300              # die rechte Spalte springt nicht mit der Auswahl
LINKS_BREITE = 132
HINWEISE_HOEHE = 110
# Beschriftung und Einheit der Felder. Die objectNames bleiben `feld_<name>`.
FELD_BESCHRIFTUNG = {
    "name": ("Name", ""), "beschreibung": ("Beschreibung", ""), "grund": ("Grund", ""),
    "x": ("x", " m"), "y": ("y", " m"),
    "x1": ("Anfang x", " m"), "y1": ("Anfang y", " m"), "x2": ("Ende x", " m"), "y2": ("Ende y", " m"),
    "z": ("Ebene z", " m"), "breite": ("Breite", " m"), "tiefe": ("Tiefe", " m"),
    "hoehe": ("Höhe", " m"), "drehung": ("Drehung", " °"), "grad": ("Richtung", " °"),
    "anstieg": ("Anstieg", " m"), "stufen": ("Stufen", ""), "id": ("Tag-Nummer", ""),
    "wand_dicke": ("Wanddicke", " m"), "wand_hoehe": ("Wandhöhe", " m"),
}
FELD_BESCHRIFTUNG_JE_ART = {("tag", "hoehe"): "Hängehöhe"}
ALLE_EBENEN = "alle Ebenen"
NEUER_RAUM = Raum(
    name="Neuer Raum", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0)),
)
GRAD_FELDER = ("grad", "drehung")
TEXT_FELDER = ("name", "beschreibung", "grund")
PFADZEICHEN = '/\\:*?"<>|'


def _zeilen(pfad):
    """jsonl lesen, halbe letzte Zeile ueberspringen (wie record/read.py)."""
    if not pfad.is_file():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return saetze


def _winkel_anzeige(grad):
    """Ein Winkel im Bereich (-180, 180] -- -90 bleibt -90, 270 wird -90."""
    grad = float(grad) % 360.0
    return grad - 360.0 if grad > 180.0 else grad


def _wert_von(widget):
    if isinstance(widget, QLineEdit):
        return widget.text()
    return widget.value()


class Zahlenfeld(QDoubleSpinBox):
    """Bis zu `decimals()` Nachkommastellen, angezeigt ohne Nullen am Ende
    (mindestens zwei): 6.1234 bleibt 6.1234, 3.1 steht als 3.10 da."""

    def textFromValue(self, wert):
        gebiet = self.locale()
        text = gebiet.toString(float(wert), "f", self.decimals())
        text = text.replace(gebiet.groupSeparator(), "")
        punkt = gebiet.decimalPoint()
        if punkt in text:
            ganz, nach = text.split(punkt, 1)
            text = ganz + punkt + nach.rstrip("0").ljust(2, "0")
        return text


def _ueberschrift(text):
    etikett = QLabel(text)
    etikett.setObjectName("Gedaempft")
    return etikett


def _beschrifte(raum, schluessel):
    art = schluessel[0]
    if art == "wand":
        return f"Wand {schluessel[1] + 1}"
    if art == "block":
        return f"{raum.bloecke[schluessel[1]].name} (Block)"
    if art == "boden":
        boden = raum.boeden[schluessel[1]]
        return f"{boden.name} ({ {'podest': 'Podest', 'rampe': 'Rampe', 'treppe': 'Treppe'}[boden.art] })"
    if art == "sperrzone":
        zone = raum.sperrzonen[schluessel[1]]
        return f"{zone.name} (Sperrzone{f' — {zone.grund}' if zone.grund else ''})"
    if art == "tag":
        return f"Tag {raum.tags[schluessel[1]].id}"
    if art == "gelaende":
        return zusammenfassung(raum.gelaende)
    return "Start"


class RaumeditorView(QWidget):
    meldung = Signal(str)
    config_gespeichert = Signal(object)
    start_gewuenscht = Signal()
    fahrt_gewuenscht = Signal()          # Fahrmodus: fahren.py mit W A S D Q E im Uebungsfenster

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._config = None
        self._arbeitsordner = None
        self._raumname = ""
        self._eigen = False          # liegt der Raum unter <arbeitsordner>/raeume?
        self._laeuft = False
        self._liste_sperre = False
        self._pauspapier = []        # Punktwolke einer Rekonstruktion, neben dem Raum gespeichert
        self._weg = []               # der gelaufene Weg (x, y, z_boden) derselben Rekonstruktion
        self._pauspapier_unlesbar = None   # Name des Raums, dessen Pauspapier nicht zu lesen war
        self._ebenen_memo = None           # (Boeden, Gelaendehoehen, Ebenen)
        self._korrektur_dialog = None
        self.steuerung = Steuerung()
        self._datei = _UNBEKANNT         # die Datei im Reiter „Code" (`setze_datei`)

        # -- links: Werkzeuge (eine Gruppe, genau eines gedrueckt), Datei, Karte.
        # Kompakt und in fester Breite: vierzehn gleich grosse Knoepfe passten bei
        # 1080 x 720 nicht mehr untereinander (UX-Pruefung 23.09.2026).
        self.links = QWidget()
        self.links.setObjectName("Werkzeugleiste")
        self.links.setFixedWidth(LINKS_BREITE)
        # Nur Abstaende, keine Farben -- die kommen aus dem Stylesheet der App.
        self.links.setStyleSheet(
            "#Werkzeugleiste QPushButton { padding: 5px 8px; text-align: left; }"
            "#Werkzeugleiste QPushButton::menu-indicator { image: none; width: 0px; }")
        links = QVBoxLayout(self.links)
        links.setContentsMargins(0, 0, 0, 0)
        links.setSpacing(4)
        links.addWidget(_ueberschrift("Zeichnen"))
        self.werkzeuge = QButtonGroup(self)
        self.werkzeuge.setExclusive(True)
        self._werkzeug_knoepfe = {}
        for name, text in WERKZEUGE:
            knopf = QPushButton(text)
            knopf.setCheckable(True)
            knopf.setObjectName(f"werkzeug_{name}")
            knopf.setToolTip(WERKZEUG_TIPPS[name])
            self.werkzeuge.addButton(knopf)
            knopf.clicked.connect(lambda _=False, n=name: self._werkzeug(n))
            self._werkzeug_knoepfe[name] = knopf
            links.addWidget(knopf)
        self._werkzeug_knoepfe["auswahl"].setChecked(True)
        links.addSpacing(8)
        links.addWidget(_ueberschrift("Datei"))
        self.dateimenue = QMenu(self)
        self.dateimenue.addAction("Neu", self.neu)
        self.dateimenue.addAction("Vorlage laden…", self._vorlage_laden)
        self.dateimenue.addAction("Öffnen…", self._oeffnen)
        self.dateimenue.addSeparator()
        # Das Kuerzel selbst haengt am Tab (`_baue_kuerzel`); hier nur angezeigt.
        self.dateimenue.addAction("Speichern\tStrg+S", self.speichern)
        self.dateimenue.addAction("Speichern unter…", self.speichern_unter)
        self.datei_knopf = QPushButton("Datei ▾")
        self.datei_knopf.setObjectName("knopf_datei")
        self.datei_knopf.setToolTip("Neu, Vorlage laden, Öffnen, Speichern unter")
        self.datei_knopf.setMenu(self.dateimenue)
        links.addWidget(self.datei_knopf)
        self.speichern_knopf = QPushButton("Speichern")
        self.speichern_knopf.setObjectName("knopf_speichern")
        self.speichern_knopf.setToolTip("Den Raum unter seinem Namen speichern")
        self.speichern_knopf.clicked.connect(lambda _=False: self.speichern())
        links.addWidget(self.speichern_knopf)
        links.addSpacing(8)
        links.addWidget(_ueberschrift("Karte"))
        rekonstruieren = QPushButton("Rekonstruieren…")
        rekonstruieren.setObjectName("knopf_rekonstruieren")
        rekonstruieren.setToolTip("Einen Raum aus einer aufgezeichneten GraphNav-Karte bauen")
        rekonstruieren.clicked.connect(self._rekonstruieren)
        links.addWidget(rekonstruieren)
        korrigieren = QPushButton("Korrigieren…")
        korrigieren.setObjectName("knopf_korrigieren")
        korrigieren.setToolTip("Wandlücken schliessen und das Gelände aus dem gelaufenen Weg bauen")
        korrigieren.clicked.connect(self._korrigieren)
        links.addWidget(korrigieren)
        links.addStretch(1)

        # -- Mitte: Titel, Umschalter, Sicht
        self.titel = QLabel("")
        self.titel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.umschalter = QPushButton("3D")
        self.umschalter.setCheckable(True)
        # Vor dem ersten Zeigen nur die Kontextprobe; scheitert initializeGL
        # spaeter doch, schaltet `_3d_bereit` zurueck und erklaert es.
        self.umschalter.setEnabled(gl_verfuegbar())
        self.umschalter.setToolTip("3D-Sicht (Tab): rechte Maustaste dreht, mittlere schwenkt, "
                                   "Rad zoomt, Home rahmt")
        self.umschalter.toggled.connect(self._umschalten)
        # Die Ebene der 2D-Sicht: abgeleitet aus den Bodenhoehen des Raums
        # (Entscheidung des Autors: keine benannten Stockwerke).
        self.ebenenwahl = QComboBox()
        self.ebenenwahl.setObjectName("ebenenwahl")
        self.ebenenwahl.setToolTip("Ebene der 2D-Sicht: andere Ebenen erscheinen blass; "
                                   "neue Elemente landen auf der gewählten Ebene")
        self._ebenen_sperre = False
        self.ebenenwahl.currentIndexChanged.connect(self._ebene_gewaehlt)
        self.tasten_knopf = QPushButton("Tasten ?")
        self.tasten_knopf.setObjectName("knopf_tasten")
        self.tasten_knopf.setToolTip("Alle Tasten des Raumeditors auf einen Blick (F1)")
        self.tasten_knopf.clicked.connect(lambda _=False: self.zeige_tasten())
        self._tastentafel = None
        kopf = QHBoxLayout()
        kopf.addWidget(self.titel, 1)
        kopf.addWidget(self.ebenenwahl)
        kopf.addWidget(self.umschalter)
        kopf.addWidget(self.tasten_knopf)
        self.sicht = Sicht2D(palette)
        self.sicht.gedrueckt.connect(self._gedrueckt)
        self.sicht.bewegt.connect(self._bewegt)
        self.sicht.losgelassen.connect(self._losgelassen)
        self.sicht.taste_gedrueckt.connect(self._taste)
        self.sicht3d = Sicht3D(palette)
        self.sicht3d.gedrueckt.connect(self._gedrueckt_3d)
        self.sicht3d.bewegt.connect(self._bewegt)
        self.sicht3d.losgelassen.connect(self._losgelassen)
        self.sicht3d.taste_gedrueckt.connect(self._taste)
        self.sicht3d.bereit.connect(self._3d_bereit)
        self.stapel = QStackedWidget()
        self.stapel.addWidget(self.sicht)
        self.stapel.addWidget(self.sicht3d)
        # Die Zustandszeile aus `Steuerung.beschreibung_teile()`: links, was gerade
        # geht (darf abgeschnitten werden), rechts Zeiger und Raster (immer ganz).
        self.zustand = QLabel("")
        self.zustand.setObjectName("Statuszeile")
        self.zustand.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.zustand_ort = QLabel("")
        self.zustand_ort.setObjectName("Statuszeile")
        self.zustand_ort.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        zustand = QHBoxLayout()
        zustand.setSpacing(0)
        zustand.addWidget(self.zustand, 1)
        zustand.addWidget(self.zustand_ort)
        mitte = QVBoxLayout()
        mitte.setSpacing(4)
        mitte.addLayout(kopf)
        mitte.addWidget(self.stapel, 1)

        # -- rechts, FESTE Breite: sonst wurde die Sicht bei jeder Auswahl mit
        # langem Namen schmaler und sprang (UX-Pruefung 23.09.2026).
        self.rechts = QWidget()
        self.rechts.setFixedWidth(RECHTS_BREITE)
        self.liste = QListWidget()
        self.liste.setSelectionMode(QListWidget.ExtendedSelection)
        self.liste.itemSelectionChanged.connect(self._liste_gewaehlt)
        self.eigenschaften = QWidget()
        self._form = QFormLayout(self.eigenschaften)
        self._form.setContentsMargins(0, 0, 4, 0)
        self._felder = {}                # Feldname -> Widget der gezeigten Auswahl
        self._form_signatur = None       # (Schluessel, Felder): gleich -> nur Werte nachtragen
        rollbar = QScrollArea()
        rollbar.setWidgetResizable(True)
        rollbar.setFrameShape(QFrame.NoFrame)
        rollbar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rollbar.setWidget(self.eigenschaften)
        # Hinweise als Liste mit fester Hoehe: sechzehn gleiche Zeilen „Wand n hat
        # keine Laenge" schoben vorher die ganze Spalte zusammen. Gleiche werden
        # zusammengefasst, ein Klick waehlt die Elemente.
        self.hinweis_titel = QLabel("Hinweise")
        self.hinweisliste = QListWidget()
        self.hinweisliste.setObjectName("hinweisliste")
        self.hinweisliste.setMaximumHeight(HINWEISE_HOEHE)
        self.hinweisliste.setWordWrap(True)
        self.hinweisliste.itemClicked.connect(self._hinweis_gewaehlt)
        rechts = QVBoxLayout(self.rechts)
        rechts.setContentsMargins(0, 0, 0, 0)
        rechts.setSpacing(4)
        rechts.addWidget(_ueberschrift("Elemente"))
        rechts.addWidget(self.liste, 3)
        rechts.addWidget(_ueberschrift("Eigenschaften"))
        rechts.addWidget(rollbar, 4)
        rechts.addWidget(self.hinweis_titel)
        rechts.addWidget(self.hinweisliste)

        self.starten = QPushButton(START_TEXT)
        self.starten.setObjectName("Primaer")
        self.starten.clicked.connect(self._start_klick)
        self.fahren = QPushButton(FAHREN_TEXT)
        self.fahren.setObjectName("knopf_fahren")
        self.fahren.setToolTip("Selbst durch diesen Raum fahren — im Übungsfenster, nicht mit "
                               "dem echten Spot: W/S vor und zurück, A/D seitwärts, Q/E drehen, "
                               "die Kamera folgt")
        self.fahren.clicked.connect(self._fahren_klick)

        oben = QHBoxLayout()
        oben.setSpacing(10)
        oben.addWidget(self.links)
        oben.addLayout(mitte, 1)
        oben.addWidget(self.rechts)
        aussen = QVBoxLayout(self)
        aussen.addLayout(oben, 1)
        # Ueber die ganze Breite: unter der Sicht allein wurde sie bei 1080 px
        # schon nach „Enter bestätigt" abgeschnitten.
        aussen.addLayout(zustand)
        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.starten, 1)
        knoepfe.addWidget(self.fahren)
        aussen.addLayout(knoepfe)
        self._startknopf_auffrischen()

        self._baue_kuerzel()
        if vorlagen():
            self.waehle_raum(vorlagen()[0])

    # ----------------------------------------------------------- Kuerzel

    def _baue_kuerzel(self):
        """Strg+S, Strg+Z, Strg+Y, Entf, Home und F1 wirken im GANZEN Tab, nicht nur
        mit Fokus auf der Zeichenflaeche: wer eben in die Liste geklickt hatte,
        drueckte Strg+Z ins Leere (UX-Pruefung 23.09.2026). Ein Eingabefeld behaelt
        seine eigenen Tasten -- Qt fragt es zuerst (ShortcutOverride), deshalb
        loescht Entf im Namensfeld einen Buchstaben und keine Wand."""
        def kuerzel(text, tasten, ziel):
            aktion = QAction(text, self)
            aktion.setShortcuts([QKeySequence(t) for t in tasten])
            aktion.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            aktion.triggered.connect(lambda _=False: ziel())
            self.addAction(aktion)
            return aktion

        self.kuerzel = {
            "speichern": kuerzel("Speichern", ("Ctrl+S",), self.speichern),
            "rueckgaengig": kuerzel("Rückgängig", ("Ctrl+Z",), self._rueckgaengig),
            "wiederholen": kuerzel("Wiederholen", ("Ctrl+Y", "Ctrl+Shift+Z"), self._wiederholen),
            "loeschen": kuerzel("Löschen", ("Del",), self._loesche_auswahl),
            "alles": kuerzel("Alles zeigen", ("Home",), self._alles_zeigen),
            "tasten": kuerzel("Tasten", ("F1",), self.zeige_tasten),
        }

    def zeige_tasten(self):
        from spotlab.gui.raumeditor.tastentafel import Tastentafel

        if self._tastentafel is None:
            self._tastentafel = Tastentafel(self)
        self._tastentafel.show()
        self._tastentafel.raise_()

    @staticmethod
    def _eingabe_hat_fokus():
        return isinstance(QApplication.focusWidget(), (QLineEdit, QAbstractSpinBox))

    def _uebernimm_offenes_feld(self):
        """Ein getippter, noch nicht bestaetigter Wert gilt vor dem Speichern -- sonst
        speicherte Strg+S im Feld den alten."""
        fokus = QApplication.focusWidget()
        for widget in self._felder.values():
            if widget is fokus or (fokus is not None and widget.isAncestorOf(fokus)):
                if isinstance(widget, QAbstractSpinBox):
                    widget.interpretText()
                widget.editingFinished.emit()
                return

    def _rueckgaengig(self):
        self.steuerung.rueckgaengig()
        self._zeige()

    def _wiederholen(self):
        self.steuerung.wiederholen()
        self._zeige()

    def _loesche_auswahl(self):
        if self._eingabe_hat_fokus():
            return
        self._taste("delete", False, False, False)

    def _alles_zeigen(self):
        self.stapel.currentWidget().alles_zeigen()

    # ---------------------------------------------------------- Zustand

    def setze_laeuft(self, laeuft):
        """Waehrend eines Laufs haelt derselbe Knopf an."""
        self._laeuft = laeuft
        self.fahren.setEnabled(not laeuft)   # Stopp heisst der Startknopf; ein Lauf zur Zeit
        self._startknopf_auffrischen()

    def setze_datei(self, name):
        """Der Name der Datei, die im Reiter „Code" offen ist -- None, wenn keine.

        Der Startknopf nennt sie („▶ hallo_spot.py im Übungsraum starten") und ist
        ohne Datei gesperrt, mit einer Erklaerung im Tooltip: vorher stand dort
        „Offene Datei starten", und wer keine offen hatte, bekam nur eine Meldung
        in der Statuszeile. app.py ruft das, wenn im Reiter „Code" die Datei
        wechselt; solange es nie gerufen wurde, bleibt der Knopf wie bisher.
        """
        self._datei = name or None
        self._startknopf_auffrischen()

    def _startknopf_auffrischen(self):
        knopf = self.starten
        if self._laeuft:
            knopf.setText(STOPP_TEXT)
            knopf.setEnabled(True)
            knopf.setToolTip("Das laufende Programm anhalten")
        elif self._datei is _UNBEKANNT:
            knopf.setText(START_TEXT)
            knopf.setEnabled(True)
            knopf.setToolTip("Die Datei, die im Reiter „Code“ offen ist, in diesem Raum starten")
        elif self._datei is None:
            knopf.setText(START_OHNE_DATEI)
            knopf.setEnabled(False)
            knopf.setToolTip(START_OHNE_DATEI_TIPP)
        else:
            knopf.setText(START_DATEI.format(name=self._datei))
            knopf.setEnabled(True)
            knopf.setToolTip(f"{self._datei} in diesem Raum starten — im Übungsraum, nicht am "
                             f"echten Spot")

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None

    def setze_config(self, cfg):
        self._config = cfg
        if cfg and cfg.raum and cfg.raum != self._raumname:
            self.waehle_raum(cfg.raum)

    # ------------------------------------------------------------- Raum

    def _setze(self, raum, name, eigen, geaendert, punkte=(), weg=()):
        if not self.darf_verlassen():
            return False
        if self._korrektur_dialog is not None:
            self._korrektur_dialog.close()
            self._korrektur_dialog = None
        self._raumname, self._eigen = name, eigen
        self._pauspapier = list(punkte)
        self._weg = list(weg)
        self._pauspapier_unlesbar = None
        self.steuerung.setze_raum(raum, geaendert=geaendert)
        for sicht in (self.sicht, self.sicht3d):
            sicht.setze_spur([])
            sicht.setze_anstoesse([])
            sicht.setze_pauspapier(self._pauspapier)
            sicht.zeige(raum)
            sicht.alles_zeigen()
        self.sicht.setze_markierung([])
        self.sicht.setze_kandidaten([])
        self.sicht.setze_offen([])
        self._zeige()
        return True

    def darf_verlassen(self):
        """Dokumentwechsel und App-Schliessen schuetzen denselben Entwurf."""
        if not self.steuerung.geaendert:
            return True
        wahl = QMessageBox.warning(
            self, "Ungespeicherter Raum",
            "Der Raum wurde geändert. Änderungen vor dem Verlassen speichern?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel)
        if wahl == QMessageBox.Save:
            return self.speichern()
        return wahl == QMessageBox.Discard

    def waehle_raum(self, name):
        if not name:
            return
        try:
            raum = raum_laden(name, workspace=self._arbeitsordner)
        except Exception as fehler:
            self.meldung.emit(str(fehler))
            return
        eigen = name in eigene_raeume(self._arbeitsordner)
        punkte, weg, unlesbar = [], [], None
        if eigen:
            pfad = pauspapier.pfad_zu(raum_pfad(self._arbeitsordner, name))
            try:
                punkte, weg = pauspapier.lies(pfad), pauspapier.lies_weg(pfad)
            except Exception as fehler:
                unlesbar = (pfad, fehler)
        if not self._setze(raum, name, eigen, False, punkte, weg):
            return
        if unlesbar is not None:
            # Merken, damit das naechste Speichern die Datei NICHT loescht: ohne
            # Punkte und Weg hielt `_schreibe` sie fuer die Messdaten eines
            # Vorgaengers -- weg war die ganze Kartenfahrt (23.09.2026).
            self._pauspapier_unlesbar = name
            self.meldung.emit(
                f"Das Pauspapier {unlesbar[0].name} ließ sich nicht lesen ({unlesbar[1]}). "
                f"Der Raum ist ohne Pauspapier geöffnet; die Datei bleibt unverändert liegen. "
                f"Für neue Messdaten den Raum aus der Karte neu rekonstruieren.")

    def _rekonstruieren(self):
        from spotlab.gui.raumeditor.rekonstruktion_dialog import RekonstruktionsDialog

        dialog = RekonstruktionsDialog(self, self._arbeitsordner)
        try:
            if dialog.exec() and dialog.ergebnis is not None:
                self.uebernimm_rekonstruktion(dialog.ergebnis)
        finally:
            # `exec` kehrt erst zurueck, wenn nichts mehr rechnet (`reject` wartet
            # darauf) -- ohne das blieb jeder Dialog als Kind des Tabs haengen.
            dialog.deleteLater()

    def uebernimm_rekonstruktion(self, ergebnis):
        """Das Ergebnis als neuen, ungespeicherten Raum oeffnen -- mit Pauspapier und Weg."""
        if not self._setze(ergebnis.raum, "", False, True, ergebnis.pauspapier,
                          getattr(ergebnis, "weg", ())):
            return
        hinweise = ergebnis.bericht.get("hinweise") or []
        b = ergebnis.bericht
        self.meldung.emit(
            f"Rekonstruiert: {b['waende']} Wände, {b['tags']} Tags, "
            f"{b.get('treppen', 0)} Treppen, {b.get('rampen', 0)} Rampen, {b.get('boeden', 0)} Böden"
            + (" — " + " ".join(hinweise) if hinweise else "")
        )

    def _korrigieren(self):
        """Der Korrigierer: nicht modal, die 2D-Sicht leuchtet die gewaehlte Luecke auf."""
        from spotlab.gui.raumeditor.korrektur_dialog import KorrekturDialog

        if self.steuerung.raum is None:
            return
        if self._korrektur_dialog is not None:
            self._korrektur_dialog.close()
        dialog = KorrekturDialog(self, self.steuerung.raum, self._weg, self._pauspapier)
        dialog.markiere.connect(self.sicht.setze_markierung)
        dialog.kandidaten.connect(self.sicht.setze_kandidaten)
        basis, revision = self.steuerung.raum, self.steuerung.revision
        dialog.angewendet.connect(
            lambda korrektur: self._korrektur_fertig(dialog, basis, revision, korrektur))
        dialog.finished.connect(lambda _ergebnis: self._korrektur_zu(dialog))
        self._korrektur_dialog = dialog
        dialog.show()

    def _korrektur_zu(self, dialog):
        """Der Dialog ist zu (angewendet, abgebrochen, ersetzt): Markierung weg, Dialog
        abraeumen. Sein Arbeiter braucht ihn nicht mehr (`korrektur_dialog._LAUFENDE`)."""
        self.sicht.setze_markierung([])
        self.sicht.setze_kandidaten([])
        if self._korrektur_dialog is dialog:
            self._korrektur_dialog = None
        if dialog.abgebrochen:
            self.meldung.emit("Korrigieren abgebrochen — nichts übernommen, der Raum ist unverändert.")
        dialog.deleteLater()

    def _korrektur_fertig(self, dialog, basis, revision, korrektur):
        if (dialog is not self._korrektur_dialog or self.steuerung.raum is not basis
                or self.steuerung.revision != revision):
            self.meldung.emit("Korrektur nicht übernommen: Der Raum wurde inzwischen geändert. "
                              "Korrigieren erneut öffnen und die Vorschläge neu prüfen.")
            return
        self.uebernimm_korrektur(korrektur)

    def uebernimm_korrektur(self, korrektur):
        """Das Ergebnis des Korrigierers als EIN Verlaufsschritt, offene Raender sichtbar.
        Die Auswahl wird leer: ihre Indizes galten fuer den Raum vor der Korrektur."""
        self.steuerung.ersetze_raum(korrektur.raum)
        self.sicht.setze_markierung([])
        self.sicht.setze_kandidaten([])
        self.sicht.setze_offen(korrektur.offene_raender)
        self.sicht3d.zeige(korrektur.raum, self.steuerung.auswahl)
        self._zeige()
        b = korrektur.bericht
        text = (f"Korrigiert: {b['waende_verbunden']} Wände verbunden, "
                f"{b['durchgaenge']} {'Durchgang' if b['durchgaenge'] == 1 else 'Durchgänge'}, "
                f"{b['geloescht']} Wände gelöscht")
        g = b.get("gelaende")
        if g:
            offen = g.get("offen", 0)
            text += (f" · Gelände {g['knoten']} Knoten, {g['z_min']:.2f} bis {g['z_max']:.2f} m, "
                     f"{offen} {'offener Rand' if offen == 1 else 'offene Ränder'}")
        self.meldung.emit(text)

    def neu(self):
        self._setze(NEUER_RAUM, "", False, True)

    def _vorlage_laden(self):
        name, ok = QInputDialog.getItem(self, "Vorlage laden", "Vorlage", vorlagen(), 0, False)
        if ok and name:
            self.waehle_raum(name)

    def _oeffnen(self):
        namen = eigene_raeume(self._arbeitsordner)
        if not namen:
            self.meldung.emit(
                "Noch kein eigener Raum. Speichere zuerst einen unter „Speichern unter…“."
            )
            return
        name, ok = QInputDialog.getItem(self, "Raum öffnen", "Raum", namen, 0, False)
        if ok and name:
            self.waehle_raum(name)

    def raum(self):
        """Der offene Raum -- das Uebungsfenster belegt seine Zeichnung damit vor."""
        return self.steuerung.raum

    def raumname(self):
        """Der Name des offenen Raums -- der geht mit an den Lauf."""
        return self._raumname

    def startpose(self):
        return self.steuerung.raum.start if self.steuerung.raum else None

    # ---------------------------------------------------------- Speichern

    def _beende_offenes(self):
        """Eine offene Geste (G/R/S, Ziehen) vor dem Speichern verwerfen: auf die
        Platte kommt nur, was bestaetigt ist. Bis zum 23.09.2026 speicherte Strg+S
        waehrend G die Vorschau, und nach Esc zeigte der Editor etwas anderes als
        die Datei -- mit `geaendert` falsch."""
        if self.steuerung.breche_ab():
            self._zeige()

    def speichern(self):
        """True, wenn der Raum danach auf der Platte liegt."""
        self._uebernimm_offenes_feld()
        self._beende_offenes()
        if not self._eigen or not self._raumname:
            return self.speichern_unter()
        return self._schreibe(self._raumname)

    def speichern_unter(self):
        self._beende_offenes()
        if self._arbeitsordner is None:
            self.meldung.emit(
                "Kein Arbeitsordner gewählt — unter „Projekte“ einen wählen, dann speichern."
            )
            return False
        vorschlag = self._raumname if self._eigen else ""
        name, ok = QInputDialog.getText(self, "Raum speichern", "Name des Raums", text=vorschlag)
        name = (name or "").strip()
        if not ok or not name:
            return False
        if any(z in name for z in PFADZEICHEN):
            self.meldung.emit(f"Der Name darf keine Pfadzeichen enthalten ({PFADZEICHEN}).")
            return False
        if name in vorlagen():
            # Ein eigener Raum geht beim Laden vor: er verdeckte die Vorlage, und ein
            # Lauf mit `SPOTLAB_RAUM=<name>` waere mehrdeutig (23.09.2026).
            self.meldung.emit(f"„{name}“ heisst wie eine Vorlage — bitte einen anderen Namen "
                              f"wählen, z. B. „{name} 2“.")
            return False
        if raum_pfad(self._arbeitsordner, name).exists():
            wahl = QMessageBox.question(
                self, "Raum ersetzen?", f"Der Raum „{name}“ existiert bereits. Ersetzen?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if wahl != QMessageBox.Yes:
                return False
        return self._schreibe(name)

    def _schreibe(self, name):
        raum = self.steuerung.raum
        if raum is None:
            return False
        pfad = raum_pfad(self._arbeitsordner, name)
        try:
            raum_speichern(raum, pfad)
            if self._pauspapier or self._weg:
                pauspapier.schreibe(pauspapier.pfad_zu(pfad), self._pauspapier, weg=self._weg)
            elif self._pauspapier_unlesbar == name and self._raumname == name:
                pass            # die unlesbare Datei gehoert genau diesem Raum: liegen lassen
            else:
                # Sonst laedt ein neuer Raum die Messdaten seines Vorgaengers.
                pauspapier.pfad_zu(pfad).unlink(missing_ok=True)
        except OSError as fehler:
            self.meldung.emit(f"Speichern nach {pfad} scheiterte: {fehler}")
            return False
        self._raumname, self._eigen = name, True
        self.steuerung.geaendert = False
        self._config_merken()
        self._zeige()
        self.meldung.emit(f"Gespeichert: {pfad}")
        return True

    def _config_merken(self):
        if self._config is None or not self._raumname or self.steuerung.raum is None:
            return
        x, y, grad = self.steuerung.raum.start
        self._config = replace(self._config, raum=self._raumname,
                               raum_start=f"{x:.2f},{y:.2f},{grad:.1f}")
        self.config_gespeichert.emit(self._config)

    # -------------------------------------------------------------- Lauf

    def bereit_fuer_lauf(self):
        """None, wenn der offene Raum so gefahren werden darf -- sonst der Grund.

        Zwei Bedingungen, fuer JEDEN virtuellen Startweg (Knopf hier oder „Code"):
        der Start steht in keinem Hindernis, und der Raum liegt so auf der
        Platte, wie er hier steht -- `SPOTLAB_RAUM` ist ein Name. Ein
        geaenderter oder namenloser Raum (Neu, Rekonstruktion) wird vorher
        gespeichert; bricht der Nutzer den Dialog ab, faehrt der Lauf NICHT
        still ohne Raum. Am 06.09.2026 zeigte das Uebungsfenster die
        rekonstruierten Katakomben, waehrend MuJoCo auf leerem Boden fuhr:
        `raumname()` war leer, und der Start aus „Code" ging am Knopf vorbei.
        """
        if self.steuerung.raum is None:
            return None
        self._beende_offenes()       # gefahren wird, was bestaetigt ist -- wie beim Speichern
        im_weg = [h for h in self.steuerung.hinweise() if h.startswith("Der Start steht")]
        if im_weg:
            return im_weg[0]
        if (self.steuerung.geaendert or not self._raumname) and not self.speichern():
            return ("Nicht gestartet: der Raum ist nicht gespeichert, und ein Lauf braucht "
                    "einen Raum auf der Platte. Im Raumeditor speichern, dann starten.")
        return None

    def _start_klick(self):
        if self._laeuft:
            self.start_gewuenscht.emit()          # derselbe Knopf heisst jetzt Stopp
            return
        if self.steuerung.raum is None:
            return
        grund = self.bereit_fuer_lauf()
        if grund:
            self.meldung.emit(grund)
            return
        self._config_merken()
        self.start_gewuenscht.emit()

    def _fahren_klick(self):
        """Wie Starten -- gespeicherter Raum, Start nicht im Hindernis -- nur mit `fahren.py`."""
        if self._laeuft or self.steuerung.raum is None:
            return
        grund = self.bereit_fuer_lauf()
        if grund:
            self.meldung.emit(grund)
            return
        self._config_merken()
        self.fahrt_gewuenscht.emit()

    def lade(self, lauf_verzeichnis):
        ordner = Path(lauf_verzeichnis)
        name, anstoesse = None, []
        for satz in _zeilen(ordner / "ereignisse.jsonl"):
            daten = satz.get("daten") or {}
            if satz.get("art") == "verbunden":
                name = daten.get("raum")
            elif satz.get("art") == "angestossen":
                anstoesse.append((daten.get("x", 0.0), daten.get("y", 0.0)))
        # Offene Aenderungen gehen vor: das Nachspielen eines Laufs darf die
        # Arbeit des Schuelers nicht ueberschreiben.
        if self.steuerung.geaendert:
            return
        if name and not self._ist_offen(name):
            self.waehle_raum(name)
        spur = []
        for satz in _zeilen(ordner / "zustand.jsonl"):
            pose = (satz.get("daten") or {}).get("pose")
            if pose and len(pose) >= 2:
                spur.append((pose[0], pose[1]))
        for sicht in (self.sicht, self.sicht3d):
            sicht.setze_spur(spur)
            sicht.setze_anstoesse(anstoesse)

    def _ist_offen(self, name):
        """Liegt genau DIESER Raum schon offen im Editor, so wie er auf der Platte steht?

        Dann laedt `lade()` ihn nicht neu: `setze_raum` leert den Verlauf, und
        nach jedem Lauf war Strg+Z weg (23.09.2026). Verglichen wird mit der
        Datei, nicht nur der Name -- hat jemand sie ausserhalb geaendert, wird
        neu geladen."""
        if name != self._raumname or self.steuerung.raum is None:
            return False
        try:
            return raum_laden(name, workspace=self._arbeitsordner) == self.steuerung.raum
        except Exception:
            return False

    # ------------------------------------------------------- Ereignisse

    def _umschalten(self, an):
        self.stapel.setCurrentWidget(self.sicht3d if an else self.sicht)
        if an:
            self.sicht3d.alles_zeigen()
        self.stapel.currentWidget().setFocus()

    def _3d_bereit(self, ok):
        """Nach initializeGL: ohne Kontext zurueck auf 2D, und sagen warum."""
        self.umschalter.setEnabled(ok)
        if not ok:
            self.umschalter.setChecked(False)
            self.umschalter.setToolTip(self.sicht3d.tafel)
            self.meldung.emit(f"3D-Sicht nicht verfügbar: {self.sicht3d.grund}")

    def _gedrueckt_3d(self, x, y, taste, shift, ctrl):
        self.steuerung.druecke(x, y, taste, shift, ctrl, toleranz=self.sicht3d.toleranz_m(),
                               treffer=self.sicht3d.klick_schluessel)
        self._zeige()

    def _werkzeug(self, name):
        self.steuerung.setze_werkzeug(name)
        self._zeige()

    def _gedrueckt(self, x, y, taste, shift, ctrl):
        self.steuerung.druecke(x, y, taste, shift, ctrl, toleranz=self.sicht.toleranz_m())
        self._zeige()

    def _bewegt(self, x, y, ctrl):
        self.steuerung.bewege(x, y, ctrl, toleranz=self.stapel.currentWidget().toleranz_m())
        self._zeige(nur_sicht=True)

    def _losgelassen(self, x, y, shift, ctrl):
        self.steuerung.lasse_los(x, y, shift, ctrl)
        self._zeige()

    def _taste(self, name, shift, ctrl, alt):
        if ctrl and name == "s":
            self.speichern()
            return
        if name == "tab":
            if self.umschalter.isEnabled():
                self.umschalter.toggle()
            return
        if name == "f" and not (ctrl or alt or self.steuerung.modus.aktiv):
            # F wie in Blender: die Auswahl einrahmen; ohne Auswahl alles zeigen.
            huelle_ = self.steuerung.auswahl_huelle()
            sicht = self.stapel.currentWidget()
            if huelle_ is not None:
                sicht.rahme(*huelle_)
            else:
                sicht.alles_zeigen()
            return
        self.steuerung.taste(name, shift, ctrl, alt)
        self._zeige()

    def _liste_gewaehlt(self):
        if self._liste_sperre:
            return
        self.steuerung.auswahl = frozenset(
            w.data(Qt.UserRole) for w in self.liste.selectedItems()
        ) & self.steuerung.auswaehlbare()
        self._zeige()

    def _ebene_gewaehlt(self, index):
        if self._ebenen_sperre or index < 0:
            return
        self.steuerung.setze_ebene(self.ebenenwahl.itemData(index))
        self._zeige()

    def _ebenen(self, raum):
        """`hoehe.ebenen`, gemerkt je (Boeden, Gelaendehoehen): die Plateaus eines
        Gelaendes zu suchen kostete auf den Katakomben 55 ms -- bei JEDEM Klick."""
        from spotlab.welt.hoehe import ebenen

        hoehen = raum.gelaende.hoehen if raum.gelaende is not None else None
        memo = self._ebenen_memo
        if memo is None or memo[0] is not raum.boeden or memo[1] is not hoehen:
            memo = self._ebenen_memo = (raum.boeden, hoehen, ebenen(raum))
        return memo[2]

    def _fuelle_ebenen(self):
        st = self.steuerung
        hoehen = self._ebenen(st.raum)
        gewaehlt = 0
        if st.ebene is not None:
            for i, hoehe in enumerate(hoehen, start=1):
                if abs(hoehe - st.ebene) < 1e-6:
                    gewaehlt = i
        eintraege = [self.ebenenwahl.itemData(i) for i in range(1, self.ebenenwahl.count())]
        if (self.ebenenwahl.count() and eintraege == hoehen
                and self.ebenenwahl.currentIndex() == gewaehlt
                and (gewaehlt or st.ebene is None)):
            return                              # nichts Neues: die Liste bleibt, wie sie ist
        self._ebenen_sperre = True
        try:
            self.ebenenwahl.clear()
            self.ebenenwahl.addItem(ALLE_EBENEN, None)
            for hoehe in hoehen:
                self.ebenenwahl.addItem(f"{hoehe:.2f} m", hoehe)
            if gewaehlt == 0:
                st.setze_ebene(None)            # die Ebene gibt es nicht mehr
            self.ebenenwahl.setCurrentIndex(gewaehlt)
            self.ebenenwahl.setVisible(self.ebenenwahl.count() > 2)
        finally:
            self._ebenen_sperre = False

    def _feld_geaendert(self, schluessel, feld, widget):
        """`editingFinished` kommt auch beim blossen Verlassen des Felds. Geschrieben
        wird deshalb nur, wenn der Wert ein ANDERER ist als der angezeigte -- sonst
        wurden -90 Grad beim Durchklicken 0, 6.1234 m wurden 6.12, und jedes Mal
        stand ein Verlaufsschritt mehr da (23.09.2026)."""
        wert = _wert_von(widget)
        if wert == widget.property("anfang"):
            return
        try:
            self.steuerung.setze_feld(schluessel, feld, wert)
        except ValueError as fehler:
            self.meldung.emit(str(fehler))
        self._zeige()

    # ---------------------------------------------------------- Anzeige

    def _klippen(self, raum):
        """Die Klippen fuer die 2D-Sicht. Waehrend einer Geste, die nur das Gelaende
        VERSCHIEBT (gleiche Hoehen, anderer Ursprung), werden die Klippen vom Anfang
        der Geste mitgeschoben statt neu gerechnet -- 40 ms je Mausbewegung auf den
        Katakomben. Nach dem Bestaetigen rechnet `klippen_von` sie genau."""
        from spotlab.welt.kollision import klippen_von

        if raum is None or not (raum.boeden or raum.gelaende is not None):
            return []
        basis = self.steuerung.vorschau_basis
        if (basis is not None and basis is not raum and raum.gelaende is not None
                and basis.gelaende is not None and raum.gelaende is not basis.gelaende
                and raum.gelaende.hoehen is basis.gelaende.hoehen):
            dx, dy = raum.gelaende.x0 - basis.gelaende.x0, raum.gelaende.y0 - basis.gelaende.y0
            return [(x1 + dx, y1 + dy, x2 + dx, y2 + dy) for x1, y1, x2, y2 in klippen_von(basis)]
        return klippen_von(raum)

    def _zeige(self, nur_sicht=False):
        st = self.steuerung
        self.sicht.zeige(st.raum, st.auswahl, st.griffe(), st.rahmen, st.kette,
                         ebene=st.ebene, klippen_=self._klippen(st.raum),
                         ueber=st.ueber, achse=st.achslinie())
        self.sicht3d.zeige(st.raum, st.auswahl)
        self.stapel.currentWidget().setze_zeigerart(st.zeigerart())
        links, rechts = st.beschreibung_teile()
        self.zustand.setText(links)
        self.zustand_ort.setText(rechts)
        if nur_sicht or st.raum is None:
            return
        self._fuelle_ebenen()
        self._fuelle_liste()
        self._fuelle_eigenschaften()
        self._fuelle_hinweise()
        knopf = self._werkzeug_knoepfe.get(st.werkzeug)
        if knopf is not None and not knopf.isChecked():
            knopf.setChecked(True)               # z. B. nach „Neu": zurueck auf Auswählen
        self.titel.setText(self._titeltext())

    def _titeltext(self):
        """„Möbliert · Vorlage", „Katakomben" (ein eigener Raum heisst wie seine
        Datei) oder „Neuer Raum · nicht gespeichert"; ● bei ungespeicherten
        Aenderungen. Vorher „Möbliert — moebliert": zweimal dasselbe."""
        st = self.steuerung
        if not self._raumname:
            text = f"{st.raum.name} · nicht gespeichert"
        elif self._eigen:
            text = self._raumname
        else:
            text = f"{st.raum.name} · Vorlage"
        return text + (" ●" if st.geaendert else "")

    def _fuelle_hinweise(self):
        """Gleiche Befunde (dieselbe Gruppe) werden EINE Zeile: „Wände ohne Länge (16)".
        Jede Zeile traegt ihre Elemente; ein Klick waehlt sie."""
        gruppen = {}
        reihe = []
        for befund in self.steuerung.befunde():
            schluessel = befund.gruppe or befund.text
            if schluessel not in gruppen:
                gruppen[schluessel] = []
                reihe.append(schluessel)
            gruppen[schluessel].append(befund)
        self.hinweisliste.clear()
        for schluessel in reihe:
            befunde = gruppen[schluessel]
            text = befunde[0].text if len(befunde) == 1 else f"{schluessel} ({len(befunde)})"
            eintrag = QListWidgetItem(text)
            eintrag.setToolTip("\n".join(f.text for f in befunde))
            eintrag.setData(Qt.UserRole, [f.schluessel for f in befunde if f.schluessel])
            self.hinweisliste.addItem(eintrag)
        anzahl = sum(len(v) for v in gruppen.values())
        self.hinweis_titel.setText(f"Hinweise ({anzahl})" if anzahl else "Keine Hinweise")
        self.hinweis_titel.setObjectName("Warnung" if anzahl else "Gedaempft")
        self.hinweis_titel.style().unpolish(self.hinweis_titel)
        self.hinweis_titel.style().polish(self.hinweis_titel)
        self.hinweisliste.setVisible(bool(anzahl))

    def _hinweis_gewaehlt(self, eintrag):
        schluessel = frozenset(eintrag.data(Qt.UserRole) or ()) & self.steuerung.auswaehlbare()
        if schluessel:
            self.steuerung.auswahl = schluessel
            self._zeige()

    def _fuelle_liste(self):
        st = self.steuerung
        self._liste_sperre = True
        try:
            self.liste.clear()
            for s in sorted(st.alle(), key=lambda k: (k[0] != "start", k)):
                eintrag = QListWidgetItem(_beschrifte(st.raum, s))
                eintrag.setData(Qt.UserRole, s)
                self.liste.addItem(eintrag)
                eintrag.setSelected(s in st.auswahl)
        finally:
            self._liste_sperre = False

    def _fuelle_eigenschaften(self):
        """Die Felder der Auswahl. Bleibt die Auswahl dieselbe, werden nur die WERTE
        nachgetragen -- neu gebaute Felder nahmen den Fokus mit, und Tab von x nach
        y landete im Nichts."""
        st = self.steuerung
        if len(st.auswahl) > 1:
            signatur = ("mehrere", len(st.auswahl))
        else:
            schluessel = next(iter(st.auswahl)) if st.auswahl else b.RAUM
            signatur = (schluessel, b.FELDER[schluessel[0]])
        if signatur == self._form_signatur and self._felder:
            self._trage_werte_ein(signatur[0])
            return
        while self._form.rowCount():
            self._form.removeRow(0)
        self._felder = {}
        self._form_signatur = signatur
        if signatur[0] == "mehrere":
            self._form.addRow(QLabel(f"{len(st.auswahl)} Elemente gewählt"))
            return
        schluessel = signatur[0]
        e = b.element(st.raum, schluessel)
        if schluessel[0] == "gelaende":
            self._form_signatur = None             # die Zusammenfassung folgt dem Gelaende
            self._form.addRow(QLabel(zusammenfassung(e)))
            hinweis = QLabel("gerechnet aus Wänden, Weg und Pauspapier — nicht von Hand zu ändern")
            hinweis.setWordWrap(True)
            self._form.addRow(hinweis)
            return
        for feld in b.FELDER[schluessel[0]]:
            beschriftung, einheit = FELD_BESCHRIFTUNG.get(feld, (feld, ""))
            beschriftung = FELD_BESCHRIFTUNG_JE_ART.get((schluessel[0], feld), beschriftung)
            if feld in TEXT_FELDER:
                widget = QLineEdit()
            elif feld in ("id", "stufen"):
                widget = QSpinBox()
                widget.setRange(0, 9999)
            else:
                widget = Zahlenfeld()
                if feld in GRAD_FELDER:
                    widget.setDecimals(2)
                    widget.setRange(-360.0, 360.0)
                    widget.setSingleStep(5.0)
                else:
                    widget.setDecimals(4)
                    widget.setRange(-1000.0, 1000.0)
                    widget.setSingleStep(0.05)
                widget.setSuffix(einheit)
            widget.setObjectName(f"feld_{feld}")
            widget.editingFinished.connect(
                lambda s=schluessel, f=feld, w=widget: self._feld_geaendert(s, f, w))
            self._felder[feld] = widget
            self._form.addRow(beschriftung, widget)
        self._trage_werte_ein(schluessel)

    def _trage_werte_ein(self, schluessel):
        e = b.element(self.steuerung.raum, schluessel)
        for feld, widget in self._felder.items():
            if schluessel[0] == "start":
                wert = {"x": e[0], "y": e[1], "grad": e[2]}[feld]
            else:
                wert = getattr(e, feld)
            if isinstance(widget, QLineEdit):
                widget.setText(str(wert))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(wert))
            else:
                widget.setValue(_winkel_anzeige(wert) if feld in GRAD_FELDER else float(wert))
            # Was angezeigt wird (gerundet wie im Feld) -- der Vergleich in `_feld_geaendert`.
            widget.setProperty("anfang", _wert_von(widget))
