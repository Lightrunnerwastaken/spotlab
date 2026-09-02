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

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QTextCursor
from PySide6.QtWidgets import QCompleter, QLabel, QStyle, QStyledItemDelegate

from spotlab.editor.verbs import (
    Vorschlag,
    praefix,
    spot_verben,
    spotlab_verben,
    teilwort,
)
from spotlab.gui.theme import DUNKEL

try:
    import jedi
except Exception:       # pragma: no cover - haengt an der Installation
    jedi = None

NAME_ROLLE = Qt.UserRole + 1
SIGNATUR_ROLLE = Qt.UserRole + 2
HILFE_ROLLE = Qt.UserRole + 3
ART_ROLLE = Qt.UserRole + 4

# jedis Typnamen auf unsere Arten. t.type ist billig; t.description loest die
# Inferenz aus und waere bei jedem Tastendruck zu teuer.
JEDI_ART = {
    "function": "funktion",
    "class": "klasse",
    "module": "modul",
    "instance": "wert",
    "keyword": "schluesselwort",
    "statement": "variable",
    "param": "parameter",
    "path": "pfad",
}

# Je Art: Beschriftung fuer den Hilfekasten, Buchstabe im Icon.
ART_LABEL = {
    "methode": "Methode", "eigenschaft": "Eigenschaft", "funktion": "Funktion",
    "klasse": "Klasse", "modul": "Modul", "wert": "Wert",
    "schluesselwort": "Schlüsselwort", "variable": "Variable",
    "parameter": "Parameter", "pfad": "Pfad",
}
ART_ZEICHEN = {
    "methode": "m", "eigenschaft": "e", "funktion": "f", "klasse": "K",
    "modul": "M", "wert": "w", "schluesselwort": "k", "variable": "v",
    "parameter": "p", "pfad": "/",
}

ZEILENHOEHE = 24
ICON = 16
LISTE_MAX_BREITE = 360
KASTEN_BREITE = 320


def art_von(jedi_typ):
    return JEDI_ART.get(jedi_typ, "")


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
            Vorschlag(treffer.name, treffer.name, "", art_von(treffer.type))
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
        if role in (Qt.DisplayRole, NAME_ROLLE):
            return eintrag.name
        if role == SIGNATUR_ROLLE:
            return eintrag.signatur
        if role == HILFE_ROLLE:
            return eintrag.hilfe
        if role == ART_ROLLE:
            return eintrag.art
        return None


def _icon_farbe(p, art):
    """Farben nur aus der Palette: die Syntaxfarben tragen die Arten mit."""
    if art in ("methode", "funktion"):
        return p.funktion
    if art == "eigenschaft":
        return p.zahl
    if art in ("modul", "klasse", "schluesselwort"):
        return p.schluesselwort
    return p.gedaempft


class VorschlagDelegate(QStyledItemDelegate):
    """Eine Zeile wie in VS Code: Icon-Kaestchen, Name, rechts gedaempft die
    Parameter. Alles aus der Palette, kein Farbliteral."""

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette

    def sizeHint(self, option, index):
        # Aus dem INHALT messen, nicht aus option.rect: bei der Spaltenmessung
        # ist das Rechteck null, und die Liste fiel auf 74 px zusammen.
        masse = QFontMetrics(option.font)
        name = index.data(Qt.DisplayRole) or ""
        signatur = index.data(SIGNATUR_ROLLE) or ""
        parameter = signatur[len(name):] if signatur.startswith(name) else ""
        breite = 6 + ICON + 10 + masse.horizontalAdvance(name) + 8
        if parameter:
            breite += masse.horizontalAdvance(parameter) + 8
        return QSize(min(LISTE_MAX_BREITE, breite), ZEILENHOEHE)

    def paint(self, painter, option, index):
        p = self._p
        r = option.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            painter.fillRect(r, QColor(p.rand))

        art = index.data(ART_ROLLE) or ""
        kasten = QRect(r.left() + 6, r.top() + (r.height() - ICON) // 2, ICON, ICON)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_icon_farbe(p, art)))
        painter.drawRoundedRect(kasten, 4, 4)
        painter.setPen(QColor(p.flaeche))
        schrift = painter.font()
        schrift.setBold(True)
        schrift.setPointSizeF(max(7.0, schrift.pointSizeF() - 1))
        painter.setFont(schrift)
        painter.drawText(kasten, Qt.AlignCenter, ART_ZEICHEN.get(art, "·"))

        painter.setFont(option.font)
        masse = QFontMetrics(option.font)
        name = index.data(Qt.DisplayRole) or ""
        signatur = index.data(SIGNATUR_ROLLE) or ""
        parameter = signatur[len(name):] if signatur.startswith(name) else ""
        x = kasten.right() + 10
        painter.setPen(QColor(p.text))
        painter.drawText(QRect(x, r.top(), r.right() - x, r.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, name)
        if parameter:
            x += masse.horizontalAdvance(name) + 8
            breite = max(0, r.right() - 8 - x)
            painter.setPen(QColor(p.gedaempft))
            painter.drawText(QRect(x, r.top(), breite, r.height()),
                             Qt.AlignVCenter | Qt.AlignLeft,
                             masse.elidedText(parameter, Qt.ElideRight, breite))
        painter.restore()


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

        palette = getattr(editor, "_palette", None) or DUNKEL
        popup = self.completer.popup()
        # Der Name ist die Bruecke zum Stylesheet: ein QCompleter-Popup ist ein
        # eigenes Toplevel-Widget und bekaeme sonst Qts Standardlook.
        popup.setObjectName("Vorschlaege")
        popup.setItemDelegate(VorschlagDelegate(palette, popup))
        popup.setUniformItemSizes(True)
        popup.installEventFilter(self)

        # Der Hilfekasten rechts neben der Liste, wie in VS Code. Kind des
        # Editors, damit er mit ihm verschwindet; ToolTip-Flag, damit er als
        # eigenes Fenster neben dem Popup schwebt statt darin zu liegen.
        self.hilfekasten = QLabel(editor, Qt.ToolTip | Qt.FramelessWindowHint)
        self.hilfekasten.setObjectName("Hilfekasten")
        self.hilfekasten.setWordWrap(True)
        self.hilfekasten.setFixedWidth(KASTEN_BREITE)
        self.hilfekasten.hide()
        self.completer.highlighted[QModelIndex].connect(self._markiert)

        editor.vervollstaendigung_gewuenscht.connect(self.anfordern)

    def eventFilter(self, beobachtet, ereignis):
        if beobachtet is self.completer.popup() and ereignis.type() == QEvent.Hide:
            self.hilfekasten.hide()
        return super().eventFilter(beobachtet, ereignis)

    def _markiert(self, index):
        """Der markierte Eintrag wandert in den Hilfekasten."""
        if not index.isValid():
            self.hilfekasten.hide()
            return
        hilfe = index.data(HILFE_ROLLE) or ""
        signatur = index.data(SIGNATUR_ROLLE) or ""
        art = ART_LABEL.get(index.data(ART_ROLLE) or "", "")
        teile = [t for t in (hilfe or art, signatur) if t]
        self.hilfekasten.setText("\n\n".join(teile))
        self.hilfekasten.adjustSize()
        popup = self.completer.popup()
        self.hilfekasten.move(popup.geometry().topRight() + QPoint(6, 0))
        self.hilfekasten.show()

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
        # Gedeckelt: frueher wurde die Liste so breit wie der laengste Hilfesatz.
        popup = self.completer.popup()
        rechteck.setWidth(min(
            LISTE_MAX_BREITE,
            popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 60,
        ))
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
        self.hilfekasten.hide()
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
