"""Der Tab „Raumeditor": Werkzeuge links, Sicht in der Mitte, Liste und
Eigenschaften rechts, der Startknopf unten.

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
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
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
from spotlab.welt.raum import (
    Raum,
    eigene_raeume,
    raum_laden,
    raum_pfad,
    raum_speichern,
    vorlagen,
)

START_TEXT = "▶ Offene Datei starten"
STOPP_TEXT = "■ Stopp"
WERKZEUGE = (("auswahl", "Auswählen"), ("wand", "Wand"), ("block", "Block"),
             ("boden", "Boden"), ("tag", "Tag"), ("start", "Start"))
ALLE_EBENEN = "alle Ebenen"
NEUER_RAUM = Raum(
    name="Neuer Raum", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0)),
)
GRAD_FELDER = ("grad", "drehung")
TEXT_FELDER = ("name", "beschreibung")
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


def _beschrifte(raum, schluessel):
    art = schluessel[0]
    if art == "wand":
        return f"Wand {schluessel[1] + 1}"
    if art == "block":
        return f"{raum.bloecke[schluessel[1]].name} (Block)"
    if art == "boden":
        boden = raum.boeden[schluessel[1]]
        return f"{boden.name} ({ {'podest': 'Podest', 'rampe': 'Rampe', 'treppe': 'Treppe'}[boden.art] })"
    if art == "tag":
        return f"Tag {raum.tags[schluessel[1]].id}"
    return "Start"


class RaumeditorView(QWidget):
    meldung = Signal(str)
    config_gespeichert = Signal(object)
    start_gewuenscht = Signal()

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
        self.steuerung = Steuerung()

        # -- links: Werkzeuge und Dateien
        links = QVBoxLayout()
        self.werkzeuge = QButtonGroup(self)
        for name, text in WERKZEUGE:
            knopf = QPushButton(text)
            knopf.setCheckable(True)
            knopf.setObjectName(f"werkzeug_{name}")
            self.werkzeuge.addButton(knopf)
            knopf.clicked.connect(lambda _=False, n=name: self._werkzeug(n))
            links.addWidget(knopf)
        self.werkzeuge.buttons()[0].setChecked(True)
        links.addSpacing(12)
        for text, ziel in (("Neu", self.neu), ("Vorlage laden…", self._vorlage_laden),
                           ("Öffnen…", self._oeffnen), ("Speichern", self.speichern),
                           ("Speichern unter…", self.speichern_unter),
                           ("Rekonstruieren…", self._rekonstruieren)):
            knopf = QPushButton(text)
            knopf.clicked.connect(ziel)
            links.addWidget(knopf)
        links.addStretch(1)

        # -- Mitte: Titel, Umschalter, Sicht
        self.titel = QLabel("")
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
        kopf = QHBoxLayout()
        kopf.addWidget(self.titel, 1)
        kopf.addWidget(self.ebenenwahl)
        kopf.addWidget(self.umschalter)
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
        mitte = QVBoxLayout()
        mitte.addLayout(kopf)
        mitte.addWidget(self.stapel, 1)

        # -- rechts: Liste, Eigenschaften, Hinweise
        self.liste = QListWidget()
        self.liste.setSelectionMode(QListWidget.ExtendedSelection)
        self.liste.itemSelectionChanged.connect(self._liste_gewaehlt)
        self.eigenschaften = QWidget()
        self._form = QFormLayout(self.eigenschaften)
        self.hinweise = QLabel("")
        self.hinweise.setWordWrap(True)
        self.hinweise.setObjectName("Gedaempft")
        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("Elemente"))
        rechts.addWidget(self.liste, 2)
        rechts.addWidget(QLabel("Eigenschaften"))
        rechts.addWidget(self.eigenschaften, 1)
        rechts.addWidget(self.hinweise)

        self.starten = QPushButton(START_TEXT)
        self.starten.clicked.connect(self._start_klick)

        oben = QHBoxLayout()
        oben.addLayout(links)
        oben.addLayout(mitte, 4)
        oben.addLayout(rechts, 1)
        aussen = QVBoxLayout(self)
        aussen.addLayout(oben, 1)
        aussen.addWidget(self.starten)

        if vorlagen():
            self.waehle_raum(vorlagen()[0])

    # ---------------------------------------------------------- Zustand

    def setze_laeuft(self, laeuft):
        """Waehrend eines Laufs haelt derselbe Knopf an."""
        self._laeuft = laeuft
        self.starten.setText(STOPP_TEXT if laeuft else START_TEXT)

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None

    def setze_config(self, cfg):
        self._config = cfg
        if cfg and cfg.raum and cfg.raum != self._raumname:
            self.waehle_raum(cfg.raum)

    # ------------------------------------------------------------- Raum

    def _setze(self, raum, name, eigen, geaendert, punkte=(), weg=()):
        self._raumname, self._eigen = name, eigen
        self._pauspapier = list(punkte)
        self._weg = list(weg)
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

    def waehle_raum(self, name):
        if not name:
            return
        try:
            raum = raum_laden(name, workspace=self._arbeitsordner)
        except Exception as fehler:
            self.meldung.emit(str(fehler))
            return
        eigen = name in eigene_raeume(self._arbeitsordner)
        punkte, weg = [], []
        if eigen:
            try:
                pfad = pauspapier.pfad_zu(raum_pfad(self._arbeitsordner, name))
                punkte, weg = pauspapier.lies(pfad), pauspapier.lies_weg(pfad)
            except Exception as fehler:
                self.meldung.emit(str(fehler))
        self._setze(raum, name, eigen, False, punkte, weg)

    def _rekonstruieren(self):
        from spotlab.gui.raumeditor.rekonstruktion_dialog import RekonstruktionsDialog

        dialog = RekonstruktionsDialog(self, self._arbeitsordner)
        if dialog.exec() and dialog.ergebnis is not None:
            self.uebernimm_rekonstruktion(dialog.ergebnis)

    def uebernimm_rekonstruktion(self, ergebnis):
        """Das Ergebnis als neuen, ungespeicherten Raum oeffnen -- mit Pauspapier und Weg."""
        self._setze(ergebnis.raum, "", False, True, ergebnis.pauspapier, getattr(ergebnis, "weg", ()))
        hinweise = ergebnis.bericht.get("hinweise") or []
        b = ergebnis.bericht
        self.meldung.emit(
            f"Rekonstruiert: {b['waende']} Wände, {b['tags']} Tags, "
            f"{b.get('treppen', 0)} Treppen, {b.get('rampen', 0)} Rampen, {b.get('boeden', 0)} Böden"
            + (" — " + " ".join(hinweise) if hinweise else "")
        )

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

    def speichern(self):
        """True, wenn der Raum danach auf der Platte liegt."""
        if not self._eigen or not self._raumname:
            return self.speichern_unter()
        return self._schreibe(self._raumname)

    def speichern_unter(self):
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
        if name and (name != self._raumname or not self.steuerung.geaendert):
            self.waehle_raum(name)
        spur = []
        for satz in _zeilen(ordner / "zustand.jsonl"):
            pose = (satz.get("daten") or {}).get("pose")
            if pose and len(pose) >= 2:
                spur.append((pose[0], pose[1]))
        for sicht in (self.sicht, self.sicht3d):
            sicht.setze_spur(spur)
            sicht.setze_anstoesse(anstoesse)

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
        self.steuerung.bewege(x, y, ctrl)
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
        self.steuerung.taste(name, shift, ctrl, alt)
        self._zeige()

    def _liste_gewaehlt(self):
        if self._liste_sperre:
            return
        self.steuerung.auswahl = frozenset(
            w.data(Qt.UserRole) for w in self.liste.selectedItems()
        )
        self._zeige()

    def _ebene_gewaehlt(self, index):
        if self._ebenen_sperre or index < 0:
            return
        self.steuerung.setze_ebene(self.ebenenwahl.itemData(index))
        self._zeige(nur_sicht=True)

    def _fuelle_ebenen(self):
        from spotlab.welt.hoehe import ebenen

        st = self.steuerung
        self._ebenen_sperre = True
        try:
            self.ebenenwahl.clear()
            self.ebenenwahl.addItem(ALLE_EBENEN, None)
            for hoehe in ebenen(st.raum):
                self.ebenenwahl.addItem(f"{hoehe:.2f} m", hoehe)
            gewaehlt = 0
            if st.ebene is not None:
                for i in range(1, self.ebenenwahl.count()):
                    if abs(self.ebenenwahl.itemData(i) - st.ebene) < 1e-6:
                        gewaehlt = i
            if gewaehlt == 0:
                st.setze_ebene(None)            # die Ebene gibt es nicht mehr
            self.ebenenwahl.setCurrentIndex(gewaehlt)
            self.ebenenwahl.setVisible(self.ebenenwahl.count() > 2)
        finally:
            self._ebenen_sperre = False

    def _feld_geaendert(self, schluessel, feld, widget):
        wert = widget.text() if isinstance(widget, QLineEdit) else widget.value()
        try:
            self.steuerung.setze_feld(schluessel, feld, wert)
        except ValueError as fehler:
            self.meldung.emit(str(fehler))
        self._zeige()

    # ---------------------------------------------------------- Anzeige

    def _zeige(self, nur_sicht=False):
        from spotlab.welt.kollision import klippen_von

        st = self.steuerung
        klippen_ = klippen_von(st.raum) if st.raum is not None and st.raum.boeden else []
        self.sicht.zeige(st.raum, st.auswahl, st.griffe(), st.rahmen, st.kette,
                         ebene=st.ebene, klippen_=klippen_)
        self.sicht3d.zeige(st.raum, st.auswahl)
        if nur_sicht or st.raum is None:
            return
        self._fuelle_ebenen()
        self._fuelle_liste()
        self._fuelle_eigenschaften()
        hinweise = st.hinweise()
        self.hinweise.setText("\n".join(hinweise) if hinweise else "Keine Hinweise.")
        stern = " *" if st.geaendert else ""
        name = self._raumname or "ohne Namen"
        self.titel.setText(f"{st.raum.name} — {name}{stern}")

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
        while self._form.rowCount():
            self._form.removeRow(0)
        st = self.steuerung
        if len(st.auswahl) > 1:
            self._form.addRow(QLabel(f"{len(st.auswahl)} Elemente gewählt"))
            return
        schluessel = next(iter(st.auswahl)) if st.auswahl else b.RAUM
        e = b.element(st.raum, schluessel)
        for feld in b.FELDER[schluessel[0]]:
            if schluessel[0] == "start":
                wert = {"x": e[0], "y": e[1], "grad": e[2]}[feld]
            else:
                wert = getattr(e, feld)
            if feld in TEXT_FELDER:
                widget = QLineEdit(str(wert))
            elif feld in ("id", "stufen"):
                widget = QSpinBox()
                widget.setRange(0, 9999)
                widget.setValue(int(wert))
            else:
                widget = QDoubleSpinBox()
                widget.setDecimals(2)
                if feld in GRAD_FELDER:
                    widget.setRange(0.0, 360.0)
                    widget.setSingleStep(5.0)
                else:
                    widget.setRange(-1000.0, 1000.0)
                    widget.setSingleStep(0.05)
                widget.setValue(float(wert))
            widget.setObjectName(f"feld_{feld}")
            widget.editingFinished.connect(
                lambda s=schluessel, f=feld, w=widget: self._feld_geaendert(s, f, w))
            self._form.addRow(feld, widget)
