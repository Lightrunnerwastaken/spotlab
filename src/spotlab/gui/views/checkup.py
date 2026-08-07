"""Zugangsdaten und Prüfung.

Der Einrichtungsteil schliesst eine Lücke: `spotlab login` fragt über input()
und getpass() im Terminal. Wer nur die GUI benutzt, könnte sich damit nie
einrichten. Gespeichert wird über dieselben Funktionen wie im CLI — kein
zweiter Speicherweg, nur eine zweite Eingabemaske.

Die Geschwindigkeitsgrenzen stehen hier, damit eine Lehrperson sie für
Anfängerstunden herunterdrehen kann, ohne eine TOML-Datei zu suchen.
"""

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

    def speichere(self):
        alt = self._config
        cfg = Config(
            ip=self.ip.text().strip(),
            username=self.benutzer.text().strip(),
            nickname=self.spitzname.text().strip() or "Spot",
            limits=Limits(
                max_speed=self.max_tempo.value(), max_turn_rate=self.max_drehung.value()
            ),
            editor_command=alt.editor_command if alt else "code",
            default_backend=alt.default_backend if alt else "real",
            workspace=alt.workspace if alt else "",
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
