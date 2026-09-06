"""Die 3D-Sicht des Raumeditors: OpenGL 3.3 Core ueber QOpenGLWidget + PyOpenGL.

Die Geometrie und die Kamera kommen aus `geometrie3d.py`; hier gibt es nur
Shader, Puffer, Zeichnen und den Farb-ID-Puffer fuer die Auswahl. PyOpenGL wird
ERST hier und erst beim Erzeugen des Kontexts importiert -- fehlt es, oder kommt
kein 3.3-Kontext zustande, zeigt die Sicht eine Tafel mit dem Grund. Kein
schwarzes Fenster.

Ereignisse gehen wie in 2D in METERN an die Steuerung: der Mausstrahl wird
mit der Bodenebene geschnitten. Weil ein Klick auf den Deckel eines Blocks am
Boden HINTER dem Block landet, gibt die Sicht zusaetzlich den Farb-ID-Treffer
mit (`klick_schluessel`).
"""

import ctypes
from array import array

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QOpenGLContext,
    QPainter,
    QSurfaceFormat,
    QVector3D,
)
from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from spotlab.gui.raumeditor import geometrie3d as geo
from spotlab.gui.raumeditor.sicht2d import TASTEN
from spotlab.welt.raum import huelle

TOLERANZ_M = 0.12
MINDESTVERSION = (3, 3)
TAFEL = ("3D-Sicht nicht verfügbar: {grund}\n\n"
         "Der Editor bleibt in 2D. Auf Rechnern ohne OpenGL 3.3 hilft oft "
         "QT_OPENGL=software setzen, dann spotlab neu starten.")

VERTEX = """
#version 330 core
layout(location = 0) in vec3 pos;
layout(location = 1) in vec3 normal;
uniform mat4 mvp;
out vec3 n;
void main() { gl_Position = mvp * vec4(pos, 1.0); n = normal; }
"""
FRAGMENT = """
#version 330 core
in vec3 n;
uniform vec3 farbe;
uniform vec3 licht;
uniform float flach;
out vec4 aus;
void main() {
    float l = mix(0.55 + 0.45 * max(dot(normalize(n), normalize(licht)), 0.0), 1.0, flach);
    aus = vec4(farbe * l, 1.0);
}
"""


def gl_verfuegbar():
    """Kommt auf diesem Rechner ein 3.3-Core-Kontext zustande (und ist PyOpenGL da)?

    Nur mit laufender QGuiApplication -- `QOpenGLContext.create()` ohne sie ist
    kein Fehler, sondern ein Absturz (Zugriffsverletzung, 06.09.2026).
    """
    try:
        import OpenGL  # noqa: F401
    except ImportError:
        return False
    if QGuiApplication.instance() is None:
        return False
    fmt = QSurfaceFormat()
    fmt.setVersion(*MINDESTVERSION)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    if not ctx.create():
        return False
    return (ctx.format().majorVersion(), ctx.format().minorVersion()) >= MINDESTVERSION


def _farbe(hexwert):
    c = QColor(hexwert)
    return (c.redF(), c.greenF(), c.blueF())


class Sicht3D(QOpenGLWidget):
    gedrueckt = Signal(float, float, str, bool, bool)
    bewegt = Signal(float, float, bool)
    losgelassen = Signal(float, float, bool, bool)
    taste_gedrueckt = Signal(str, bool, bool, bool)
    bereit = Signal(bool)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(*MINDESTVERSION)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setSamples(4)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)
        self._p = palette
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.kamera = geo.Kamera()
        self.verfuegbar = None
        self.grund = ""
        self.tafel = ""
        self.klick_schluessel = None
        self._raum = None
        self._auswahl = frozenset()
        self._spur = []
        self._anstoesse = []
        self._pauspapier = []
        self._gl = None             # das OpenGL.GL-Modul, sobald es da ist
        self._programm = None
        self._vao = None
        self._vbo = None
        self._puffer_dirty = True
        self._geometrie = []        # [(schluessel, anfang, anzahl)] im VBO
        self._linien = []           # [(farbe, anfang, anzahl, art)]
        self._letzte_maus = None

    # ------------------------------------------------------------ Fuellen

    def zeige(self, raum, auswahl=frozenset(), griffe=(), rahmen=None, kette=None):
        self._raum, self._auswahl = raum, frozenset(auswahl)
        self._puffer_dirty = True
        self.update()

    def setze_spur(self, punkte):
        self._spur = list(punkte)
        self._puffer_dirty = True
        self.update()

    def setze_anstoesse(self, punkte):
        self._anstoesse = list(punkte)
        self._puffer_dirty = True
        self.update()

    def setze_pauspapier(self, punkte):
        self._pauspapier = list(punkte)
        self._puffer_dirty = True
        self.update()

    def alles_zeigen(self):
        if self._raum is not None:
            self.kamera.rahme(huelle(self._raum))
            self.update()

    def toleranz_m(self):
        return TOLERANZ_M

    # ---------------------------------------------------------------- GL

    def initializeGL(self):
        try:
            from OpenGL import GL
        except ImportError as fehler:
            self._scheitere(f"PyOpenGL fehlt ({fehler}). Installieren: pip install \"spotlab[gui]\"")
            return
        ctx = self.context()
        if ctx is None or not ctx.isValid():
            self._scheitere("kein OpenGL-Kontext")
            return
        fassung = (ctx.format().majorVersion(), ctx.format().minorVersion())
        if fassung < MINDESTVERSION:
            self._scheitere(f"OpenGL {fassung[0]}.{fassung[1]} — gebraucht wird 3.3")
            return
        self._gl = GL
        programm = QOpenGLShaderProgram(self)
        if (not programm.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX)
                or not programm.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT)
                or not programm.link()):
            self._scheitere(f"Shader: {programm.log().strip()}")
            return
        self._programm = programm
        # Uniforms ueber PyOpenGL, nicht ueber `setUniformValue`: PySide6 waehlt
        # fuer `(location, 0.0)` die int-Ueberladung -- glUniform1i auf ein
        # float-Uniform ist GL_INVALID_OPERATION (gemessen 06.09.2026).
        self._u = {name: programm.uniformLocation(name) for name in ("mvp", "licht", "farbe", "flach")}
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        self._puffer_dirty = True
        self.verfuegbar = True
        self.bereit.emit(True)

    def _scheitere(self, grund):
        self.verfuegbar = False
        self.grund = grund
        self.tafel = TAFEL.format(grund=grund)
        self.bereit.emit(False)

    @staticmethod
    def _mit_normale(xyz):
        aus = []
        for i in range(0, len(xyz), 3):
            aus += [xyz[i], xyz[i + 1], xyz[i + 2], 0.0, 0.0, 1.0]
        return aus

    def _baue_puffer(self):
        """Alle Vertices in EINEN Puffer: Kaesten (mit Normale), dann Linien und Punkte."""
        GL = self._gl
        daten = array("f")
        self._geometrie = []
        self._linien = []
        if self._raum is not None:
            for schluessel, vertices in geo.kaesten_aus_raum(self._raum, self._auswahl):
                self._geometrie.append((schluessel, len(daten) // 6, len(vertices) // 6))
                daten.extend(vertices)
            from spotlab.welt.hoehe import boden_bei, boden_z

            raster = geo.bodenraster(huelle(self._raum), z=boden_z(self._raum))
            self._linien.append((self._p.rand, len(daten) // 6, len(raster) // 3, GL.GL_LINES))
            daten.extend(self._mit_normale(raster))
            start_z, _ = boden_bei(self._raum, self._raum.start[0], self._raum.start[1])
            pfeil = geo.spot_pfeil(self._raum.start, z=start_z)
            self._linien.append((self._p.funktion, len(daten) // 6, 2, GL.GL_LINES))
            daten.extend(self._mit_normale(pfeil))
        if len(self._spur) > 1:
            punkte = []
            for (x1, y1), (x2, y2) in zip(self._spur, self._spur[1:]):
                punkte += [x1, y1, 0.01, x2, y2, 0.01]
            self._linien.append((self._p.akzent, len(daten) // 6, len(punkte) // 3, GL.GL_LINES))
            daten.extend(self._mit_normale(punkte))
        if self._anstoesse:
            punkte = []
            for x, y in self._anstoesse:
                punkte += [x - 0.1, y - 0.1, 0.02, x + 0.1, y + 0.1, 0.02,
                           x - 0.1, y + 0.1, 0.02, x + 0.1, y - 0.1, 0.02]
            self._linien.append((self._p.gefahr, len(daten) // 6, len(punkte) // 3, GL.GL_LINES))
            daten.extend(self._mit_normale(punkte))
        if self._pauspapier:
            punkte = []
            for x, y in self._pauspapier:
                punkte += [x, y, 0.02]
            self._linien.append((self._p.gedaempft, len(daten) // 6, len(punkte) // 3, GL.GL_POINTS))
            daten.extend(self._mit_normale(punkte))
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        roh = daten.tobytes()
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(roh), roh, GL.GL_DYNAMIC_DRAW)
        schritt = 6 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, schritt, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, schritt, ctypes.c_void_p(12))
        GL.glBindVertexArray(0)
        self._puffer_dirty = False

    def _mvp(self):
        return self.kamera.projektion(self.width(), self.height()) * self.kamera.ansicht()

    def _elementfarbe(self, schluessel):
        if schluessel in self._auswahl:
            return self._p.akzent
        art = schluessel[0]
        if art == "tag":
            return self._p.zahl
        if art == "start":
            return self._p.funktion
        if art == "wand":
            return self._p.text
        if art == "boden":
            return self._p.rand
        return self._p.flaeche

    def _zeichne_szene(self, ids=False):
        GL = self._gl
        if self._puffer_dirty:
            self._baue_puffer()
        p = self._programm
        u = self._u
        p.bind()
        GL.glUniformMatrix4fv(u["mvp"], 1, GL.GL_FALSE, list(self._mvp().data()))
        GL.glUniform3f(u["licht"], 0.4, -0.6, 1.0)
        GL.glBindVertexArray(self._vao)
        for i, (schluessel, anfang, anzahl) in enumerate(self._geometrie):
            if ids:
                farbe = geo.farbe_fuer(i + 1)
                GL.glUniform1f(u["flach"], 1.0)
            else:
                farbe = _farbe(self._elementfarbe(schluessel))
                GL.glUniform1f(u["flach"], 0.0)
            GL.glUniform3f(u["farbe"], *farbe)
            GL.glDrawArrays(GL.GL_TRIANGLES, anfang, anzahl)
        if not ids:
            GL.glUniform1f(u["flach"], 1.0)
            GL.glPointSize(2.0)
            for farbe, anfang, anzahl, art in self._linien:
                GL.glUniform3f(u["farbe"], *_farbe(farbe))
                GL.glDrawArrays(art, anfang, anzahl)
        GL.glBindVertexArray(0)
        p.release()

    def paintGL(self):
        if not self.verfuegbar:
            return
        GL = self._gl
        r, g, b = _farbe(self._p.hintergrund)
        GL.glClearColor(r, g, b, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        self._zeichne_szene()
        # Beschriftungen ueber dem GL-Bild -- Text in GL waere die Arbeit nicht wert.
        if self._raum is not None:
            maler = QPainter(self)
            maler.setPen(QColor(self._p.text))
            mvp = self._mvp()
            for block in self._raum.bloecke:
                self._beschrifte(maler, mvp, block.x, block.y, block.hoehe + 0.1, block.name)
            for t in self._raum.tags:
                self._beschrifte(maler, mvp, t.x, t.y, t.hoehe + 0.15, str(t.id))
            maler.end()

    def _beschrifte(self, maler, mvp, x, y, z, text):
        p = mvp.map(QVector3D(x, y, z))
        if not (-1.0 <= p.z() <= 1.0):
            return
        maler.drawText(QPointF((p.x() + 1.0) / 2 * self.width(),
                               (1.0 - p.y()) / 2 * self.height()), text)

    def resizeGL(self, breite, hoehe):
        if self.verfuegbar:
            self._gl.glViewport(0, 0, breite, hoehe)

    def paintEvent(self, ereignis):
        if self.verfuegbar is None:
            # Erst Qt den Kontext anlegen lassen (ruft initializeGL); bleibt das
            # Widget danach ungueltig, gab es keinen -- unter `offscreen` und auf
            # Rechnern ohne OpenGL 3.3 landet man hier, nicht in initializeGL.
            super().paintEvent(ereignis)
            if self.verfuegbar is None and not self.isValid():
                self._scheitere("kein OpenGL-Kontext auf diesem Rechner")
                self.update()
            return
        if self.verfuegbar is False:
            maler = QPainter(self)
            maler.fillRect(self.rect(), QColor(self._p.hintergrund))
            maler.setPen(QColor(self._p.gedaempft))
            maler.drawText(self.rect().adjusted(20, 20, -20, -20),
                           Qt.AlignCenter | Qt.TextWordWrap, self.tafel)
            return
        super().paintEvent(ereignis)

    # ---------------------------------------------------------- Auswahl

    def treffer(self, px, py):
        """Das Element unter dem Pixel -- ueber einen Farb-ID-Durchgang."""
        if not self.verfuegbar:
            return None
        GL = self._gl
        self.makeCurrent()
        try:
            fbo = QOpenGLFramebufferObject(self.width(), self.height(),
                                           QOpenGLFramebufferObject.CombinedDepthStencil)
            fbo.bind()
            GL.glViewport(0, 0, self.width(), self.height())
            GL.glClearColor(0.0, 0.0, 0.0, 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDisable(GL.GL_MULTISAMPLE)
            self._zeichne_szene(ids=True)
            GL.glEnable(GL.GL_MULTISAMPLE)
            pixel = GL.glReadPixels(int(px), self.height() - int(py) - 1, 1, 1,
                                    GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
            fbo.release()
        finally:
            self.doneCurrent()
        roh = bytes(pixel)
        index = geo.index_aus(roh[0], roh[1], roh[2]) if len(roh) >= 3 else 0
        if 0 < index <= len(self._geometrie):
            return self._geometrie[index - 1][0]
        return None

    def bodenpunkt(self, px, py):
        return self.kamera.bodenpunkt(px, py, self.width(), self.height())

    def bild(self):
        return self.grabFramebuffer()

    # ------------------------------------------------------- Ereignisse

    @staticmethod
    def _tasten(ereignis):
        m = ereignis.modifiers()
        return bool(m & Qt.ShiftModifier), bool(m & Qt.ControlModifier), bool(m & Qt.AltModifier)

    def mousePressEvent(self, ereignis):
        self.setFocus()
        p = ereignis.position()
        self._letzte_maus = (p.x(), p.y())
        if ereignis.button() != Qt.LeftButton or not self.verfuegbar:
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        boden = self.bodenpunkt(p.x(), p.y())
        if boden is None:
            return
        self.klick_schluessel = self.treffer(p.x(), p.y())
        self.gedrueckt.emit(boden[0], boden[1], "links", shift, ctrl)

    def mouseMoveEvent(self, ereignis):
        p = ereignis.position()
        if self._letzte_maus is None:
            self._letzte_maus = (p.x(), p.y())
        dx, dy = p.x() - self._letzte_maus[0], p.y() - self._letzte_maus[1]
        self._letzte_maus = (p.x(), p.y())
        knoepfe = ereignis.buttons()
        if knoepfe & Qt.RightButton or knoepfe & Qt.MiddleButton:
            if knoepfe & Qt.MiddleButton or ereignis.modifiers() & Qt.ShiftModifier:
                self.kamera.schwenke(-dx * self.kamera.abstand / 500.0,
                                     dy * self.kamera.abstand / 500.0)
            else:
                self.kamera.orbit(-dx * 0.5, dy * 0.5)
            self.update()
            return
        if not self.verfuegbar:
            return
        _shift, ctrl, _alt = self._tasten(ereignis)
        boden = self.bodenpunkt(p.x(), p.y())
        if boden is not None:
            self.bewegt.emit(boden[0], boden[1], ctrl)

    def mouseReleaseEvent(self, ereignis):
        if ereignis.button() != Qt.LeftButton or not self.verfuegbar:
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        p = ereignis.position()
        boden = self.bodenpunkt(p.x(), p.y())
        if boden is not None:
            self.losgelassen.emit(boden[0], boden[1], shift, ctrl)

    def wheelEvent(self, ereignis):
        self.kamera.zoom(1.15 ** (-ereignis.angleDelta().y() / 120.0))
        self.update()

    def keyPressEvent(self, ereignis):
        taste = ereignis.key()
        if taste == Qt.Key_Home:
            self.alles_zeigen()
            return
        shift, ctrl, alt = self._tasten(ereignis)
        if taste in TASTEN:
            name = TASTEN[taste]
        elif Qt.Key_0 <= taste <= Qt.Key_9:
            name = chr(taste)
        elif Qt.Key_A <= taste <= Qt.Key_Z:
            name = chr(taste).lower()
        else:
            super().keyPressEvent(ereignis)
            return
        self.taste_gedrueckt.emit(name, shift, ctrl, alt)
