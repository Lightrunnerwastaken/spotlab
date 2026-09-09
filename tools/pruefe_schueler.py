"""Offline installation smoke check. Does not connect to a robot or open a GUI."""
import importlib.metadata


def main():
    import mujoco
    from PySide6 import QtWidgets

    from spotlab.backends.mujoco import _puppe_laden

    assert QtWidgets.QApplication is not None
    puppe = _puppe_laden()
    figure = puppe.SpotPuppe(puppe.Welt())
    try:
        assert figure.model.nq > 0
        mujoco.mj_forward(figure.model, figure.data)
    finally:
        figure.close()
    for name in ('spotlab', 'spotlab-sim-runtime', 'mujoco', 'PySide6'):
        print(f'{name}: {importlib.metadata.version(name)}')
    print('GUI importiert, Robotermodell geladen, Simulation initialisiert. Grafikdarstellung separat pruefen.')


if __name__ == '__main__':
    main()
