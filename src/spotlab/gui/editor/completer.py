"""Vorschlaege: die eigene Liste sofort, jedi wenn es rechtzeitig antwortet.

Die eigene Liste ist geprueft und garantiert — "nach spot. muss navigate_to
vorkommen" ist eine Aussage ueber unseren eigenen Code. Ob jedi durch
`with spotlab.connect() as spot:` hindurch auf Spot schliesst, haengt an
fremder Inferenz durch einen @contextmanager. jedi deckt dafuer ab, was wir
nicht wissen koennen: lokale Variablen, math., np., Importnamen.

Fehlt jedi oder wirft es, bleibt es bei der eigenen Liste — ohne Hinweis und
ohne Fehler. Ein Editor, der sich ueber eine fehlende Vervollstaendigung
beschwert, ist laestiger als einer, der leise weniger kann.
"""

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCompleter

from spotlab.editor.verbs import (
    Vorschlag,
    praefix,
    spot_verben,
    spotlab_verben,
    teilwort,
)

try:
    import jedi
except Exception:       # pragma: no cover - haengt an der Installation
    jedi = None

NAME_ROLLE = Qt.UserRole + 1

# jedis Typnamen auf Deutsch. t.type ist billig; t.description loest die
# Inferenz aus und waere bei jedem Tastendruck zu teuer.
ARTEN = {
    "function": "Funktion",
    "class": "Klasse",
    "module": "Modul",
    "instance": "Wert",
    "keyword": "Schlüsselwort",
    "statement": "Variable",
    "param": "Parameter",
    "path": "Pfad",
}


def zusammenfuehren(eigene, fremde):
    """Erst die eigenen, dann der Rest. Bei Namensgleichheit gewinnt der eigene.

    Nur der eigene Eintrag traegt Signatur und deutsche Erklaerung.
    """
    ergebnis = list(eigene)
    bekannt = {v.name for v in ergebnis}
    for vorschlag in fremde:
        if vorschlag.name in bekannt:
            continue
        bekannt.add(vorschlag.name)
        ergebnis.append(vorschlag)
    return ergebnis


def eigene_vorschlaege(text_vor_cursor):
    ziel = praefix(text_vor_cursor)
    if ziel == "spot":
        return list(spot_verben())
    if ziel == "spotlab":
        return list(spotlab_verben())
    return []


def jedi_lesen(quelltext, zeile, spalte, pfad):
    """Blockierend — laeuft nur im JediWorker oder im Test."""
    if jedi is None:
        return []
    try:
        skript = jedi.Script(code=quelltext, path=pfad)
        return [
            Vorschlag(treffer.name, treffer.name, ARTEN.get(treffer.type, ""))
            for treffer in skript.complete(zeile, spalte)
        ]
    except Exception:
        # Fremder Code: was hier schiefgeht, darf den Editor nicht mitreissen.
        return []


class VorschlagModell(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._zeilen = []

    def setze(self, vorschlaege):
        self.beginResetModel()
        self._zeilen = list(vorschlaege)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._zeilen)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._zeilen):
            return None
        eintrag = self._zeilen[index.row()]
        if role == Qt.DisplayRole:
            return f"{eintrag.signatur}   {eintrag.hilfe}".rstrip()
        if role == NAME_ROLLE:
            return eintrag.name
        return None


class JediWorker(QThread):
    fertig = Signal(int, list)

    def __init__(self, nummer, quelltext, zeile, spalte, pfad, parent=None):
        super().__init__(parent)
        self._nummer = nummer
        self._quelltext = quelltext
        self._zeile = zeile
        self._spalte = spalte
        self._pfad = pfad

    def run(self):
        self.fertig.emit(
            self._nummer,
            jedi_lesen(self._quelltext, self._zeile, self._spalte, self._pfad),
        )


class Vervollstaendigung(QObject):
    def __init__(self, editor, parent=None):
        super().__init__(parent or editor)
        self._editor = editor
        self._pfad = None
        self._nummer = 0
        self._eigene = []
        self._anzeige_zu_name = {}
        self._worker = None
        # Ab `schliesse()` wird nichts mehr angefordert und keine Antwort mehr
        # verarbeitet — das Widget darunter ist dann schon zur Zerstörung
        # vorgemerkt.
        self._geschlossen = False

        self.modell = VorschlagModell(self)
        self.completer = QCompleter(self.modell, self)
        self.completer.setWidget(editor)
        self.completer.setCompletionRole(NAME_ROLLE)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.activated.connect(self._einfuegen)

        editor.vervollstaendigung_gewuenscht.connect(self.anfordern)

    # jedi laeuft im eigenen Thread. Damit die eigene Liste sofort erscheint,
    # ist der Ablauf zweistufig statt abwartend.
    jedi_lesen = staticmethod(jedi_lesen)

    def setze_pfad(self, pfad):
        self._pfad = str(pfad) if pfad else None

    def anfordern(self, erzwungen=False):
        vor = self._vor_dem_cursor()
        self._eigene = eigene_vorschlaege(vor)
        if not self._eigene and not erzwungen:
            self.completer.popup().hide()
            return
        self._nummer += 1
        self._zeige(self._eigene, teilwort(vor))
        self._frage_jedi(self._nummer)

    def _vor_dem_cursor(self):
        cursor = self._editor.textCursor()
        return cursor.block().text()[: cursor.positionInBlock()]

    def _zeige(self, vorschlaege, praefixwort):
        self.modell.setze(vorschlaege)
        self._anzeige_zu_name = {}
        for zeile in range(self.modell.rowCount()):
            index = self.modell.index(zeile, 0)
            self._anzeige_zu_name[self.modell.data(index)] = self.modell.data(
                index, NAME_ROLLE
            )
        if not vorschlaege:
            self.completer.popup().hide()
            return
        self.completer.setCompletionPrefix(praefixwort)
        if self.completer.completionCount() == 0:
            self.completer.popup().hide()
            return
        rechteck = self._editor.cursorRect()
        rechteck.setWidth(
            self.completer.popup().sizeHintForColumn(0)
            + self.completer.popup().verticalScrollBar().sizeHint().width()
        )
        self.completer.complete(rechteck)

    def schliesse(self):
        """Vor dem Zerstören des Editors aufrufen. Läuft immer durch.

        `deleteLater()` auf dem CodeEdit nimmt den Vervollständiger und den
        darunter hängenden `JediWorker`-QThread mit. Läuft der noch, wird ein
        arbeitender QThread destruiert — das reisst das ganze Fenster mit,
        samt NOT-AUS-Knopf, und ein laufendes Roboterprogramm im Kindprozess
        bleibt führerlos zurück.

        Erst trennen, dann warten: die Antwort darf das zerstörte Widget nicht
        mehr anfassen, auch wenn sie eine Millisekunde zu spät kommt.
        """
        self._geschlossen = True
        arbeiter, self._worker = self._worker, None
        if arbeiter is None:
            return
        # NUR die eigene Verbindung trennen. `arbeiter.disconnect()` ohne
        # Argument kappt ALLE Signale des QThread — auch `finished` und
        # `destroyed`, an denen Qt seine eigene Aufräumarbeit hängt. Das hat
        # beim ersten Versuch prompt den Interpreter abgestürzt, und zwar erst
        # mehrere Testdateien später.
        try:
            arbeiter.fertig.disconnect(self._jedi_fertig)
        except (RuntimeError, TypeError):
            pass          # war nie verbunden oder ist schon weg
        try:
            arbeiter.wait(2000)
        except RuntimeError:
            pass

    def _frage_jedi(self, nummer):
        if self._geschlossen:
            return
        if jedi is None:
            return
        cursor = self._editor.textCursor()
        self._worker = JediWorker(
            nummer,
            self._editor.toPlainText(),
            cursor.blockNumber() + 1,
            cursor.positionInBlock(),
            self._pfad,
            self,
        )
        self._worker.fertig.connect(self._jedi_fertig)
        self._worker.start()

    def _jedi_fertig(self, nummer, fremde):
        if self._geschlossen:
            return
        if nummer != self._nummer:
            # Veraltet: eine langsame alte Antwort darf eine schnelle neue
            # nicht ueberschreiben.
            return
        self._zeige(
            zusammenfuehren(self._eigene, fremde), teilwort(self._vor_dem_cursor())
        )

    def _einfuegen(self, text):
        """QCompleter.activated liefert je nach Qt-Aufbau den completionRole
        (= den Namen) oder den Anzeigetext. Beides fuehrt hier zum Namen."""
        name = self._anzeige_zu_name.get(text, text)
        cursor = self._editor.textCursor()
        offen = len(teilwort(self._vor_dem_cursor()))
        if offen:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, offen)
            cursor.removeSelectedText()
        cursor.insertText(name)
        self._editor.setTextCursor(cursor)
