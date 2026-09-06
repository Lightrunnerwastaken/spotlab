"""Der Raumeditor: Raeume bauen, in 2D sehen, darin fahren.

Ein Modell (`welt/raum.py`), eine Steuerung ohne Qt (`steuerung.py`), darueber
die Qt-Haut: `sicht2d.py` zeichnet und meldet Ereignisse in Metern, `tab.py`
haelt Werkzeuge, Liste, Eigenschaften und den Startknopf. Kein bosdyn, kein
`spotlab.backends`, kein mujoco -- dieselbe Regel wie ueberall unter gui/.
"""

from spotlab.gui.raumeditor.tab import RaumeditorView

__all__ = ["RaumeditorView"]
