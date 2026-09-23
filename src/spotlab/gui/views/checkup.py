"""Zugangsdaten und Prüfung.

Der Einrichtungsteil schliesst eine Lücke: `spotlab login` fragt über input()
und getpass() im Terminal. Wer nur die GUI benutzt, könnte sich damit nie
einrichten. Gespeichert wird über dieselben Funktionen wie im CLI — kein
zweiter Speicherweg, nur eine zweite Eingabemaske.

Die Geschwindigkeitsgrenzen stehen hier, damit eine Lehrperson sie für
Anfängerstunden herunterdrehen kann, ohne eine TOML-Datei zu suchen.
"""

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.config import Config, Limits, load_config, save_config, save_password
from spotlab.errors import SpotlabError
from spotlab.gui import konfig


class CheckupView(QWidget):
    config_gespeichert = Signal(object)
    pruefung_angefordert = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = None

        self.ip = QLineEdit()
        self.benutzer = QLineEdit()
        self.spitzname = QLineEdit()
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        self.passwort.setPlaceholderText("leer lassen, um es nicht zu ändern")

        self.max_tempo = QDoubleSpinBox()
        self.max_tempo.setRange(0.05, 1.6)
        self.max_tempo.setSingleStep(0.05)
        self.max_tempo.setSuffix(" m/s")
        self.max_drehung = QDoubleSpinBox()
        self.max_drehung.setRange(0.05, 2.0)
        self.max_drehung.setSingleStep(0.05)
        self.max_drehung.setSuffix(" rad/s")

        self.speichern_knopf = QPushButton("Speichern")
        self.speichern_knopf.clicked.connect(self.speichere)
        self.pruefen_knopf = QPushButton("Spot prüfen")
        self.pruefen_knopf.clicked.connect(self.pruefung_angefordert.emit)

        self.ergebnisse = QPlainTextEdit()
        self.ergebnisse.setReadOnly(True)

        formular = QFormLayout()
        formular.addRow("IP-Adresse", self.ip)
        formular.addRow("Benutzername", self.benutzer)
        formular.addRow("Spitzname", self.spitzname)
        formular.addRow("Passwort", self.passwort)
        formular.addRow("Höchstgeschwindigkeit", self.max_tempo)
        formular.addRow("Höchste Drehrate", self.max_drehung)

        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.speichern_knopf)
        knoepfe.addWidget(self.pruefen_knopf)
        knoepfe.addStretch(1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Zugangsdaten"))
        anordnung.addLayout(formular)
        anordnung.addLayout(knoepfe)
        anordnung.addWidget(QLabel("Prüfung"))
        anordnung.addWidget(self.ergebnisse, 1)
        # Lizenz, Nutzlasten, Dienste und Zertifikatsablauf stehen seit Stufe 9
        # in dieser Ausgabe. Wer sie an die Schule oder den BD-Support gibt, soll
        # sie nicht abtippen müssen.
        self.kopieren = QPushButton("Als Text kopieren")
        self.kopieren.clicked.connect(self._kopiere)
        anordnung.addWidget(self.kopieren)

        self.lade()

    # ------------------------------------------------------------- Daten

    def lade(self):
        try:
            self._config = load_config()
        except SpotlabError:
            self._config = None
        grenzen = self._config.limits if self._config else Limits()
        self.ip.setText(self._config.ip if self._config else "")
        self.benutzer.setText(self._config.username if self._config else "")
        self.spitzname.setText(self._config.nickname if self._config else "")
        self.max_tempo.setValue(grenzen.max_speed)
        self.max_drehung.setValue(grenzen.max_turn_rate)
        # Was die Felder JETZT zeigen (gerundet): daran erkennt speichere(), ob
        # jemand sie geaendert hat (gui/konfig.unberuehrt).
        self._tempo_beim_laden = self.max_tempo.value()
        self._drehung_beim_laden = self.max_drehung.value()

    def speichere(self):
        # ERGAENZEN, nicht neu bauen: ein frisches `Config(...)` liess jedes nicht
        # genannte Feld auf die Vorgabe zurueckfallen -- aktive Karte, Uebungsraum,
        # Startpose und `treppen` waren nach einer Passwortaenderung weg. `treppen`
        # ist dabei ein SICHERHEITSWERT (`mobility.mit_grenze` -> `stairs_mode`).
        # Auf der Kommandozeile war das in `cli.py::_login` laengst so geloest.
        # Und FRISCH von der Platte, nicht die Kopie vom Start: sonst kam alles
        # zurueck, was inzwischen anderswo gesetzt wurde (gui/konfig.py).
        gezeigt = self._config
        alt = konfig.frisch(gezeigt) or Config(ip="", username="", limits=Limits())
        cfg = replace(
            alt,
            ip=self.ip.text().strip(),
            username=self.benutzer.text().strip(),
            nickname=self.spitzname.text().strip() or "Spot",
            limits=replace(
                alt.limits,
                max_speed=konfig.unberuehrt(
                    self.max_tempo.value(), self._tempo_beim_laden,
                    gezeigt.limits.max_speed if gezeigt else None),
                max_turn_rate=konfig.unberuehrt(
                    self.max_drehung.value(), self._drehung_beim_laden,
                    gezeigt.limits.max_turn_rate if gezeigt else None),
            ),
        )
        save_config(cfg)
        wort = self.passwort.text()
        if wort:
            save_password(cfg.username, wort)
            self.passwort.clear()
        self._config = cfg
        self.config_gespeichert.emit(cfg)

    def zeige_pruefung(self, pruefungen):
        zeilen = []
        for pruefung in pruefungen:
            zeichen = "OK  " if pruefung.ok else "FEHL"
            zeilen.append(f"{zeichen} {pruefung.name:<14} {pruefung.detail}")
            if pruefung.rat:
                zeilen.append(f"       → {pruefung.rat}")
        self.ergebnisse.setPlainText("\n".join(zeilen))

    def _kopiere(self):
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.ergebnisse.toPlainText())
