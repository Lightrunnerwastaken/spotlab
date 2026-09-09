from pathlib import Path

from spotlab import connect


def main():
    with connect() as spot:
        if not spot.supports("local_grid"):
            print("Kein LocalGrid verfuegbar; Backend mit Raum oder echten Spot waehlen.")
            return
        names = spot.grid_types()
        print("Verfuegbare Ebenen:", names)
        for name in ("obstacle_distance", "terrain", "no_step"):
            if name not in names:
                print(name, "wird hier nicht angeboten.")
                continue
            grid = spot.local_grid(name)
            print(name, grid.values.shape, grid.unit, "bekannt:", int(grid.known.sum()))
            print(grid.save(Path(__file__).parent / "auswertung" / (name + ".npz")))


if __name__ == "__main__":
    main()
