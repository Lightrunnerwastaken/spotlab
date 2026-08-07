"""Qt-freie und SDK-freie Bausteine des eingebauten Editors.

Dieses Paket importiert NICHTS aus spotlab.api, spotlab.backends oder
spotlab.maps und nichts ausserhalb der Standardbibliothek. api/spot.py zieht
ueber motion/posture/state/perception bosdyn, numpy und Pillow herein; ein
Import von dort ketten den Editor an das SDK und braeche die Schichtregel der
GUI. tests/test_editor_verbs.py haelt das in einem Unterprozess fest.
"""
