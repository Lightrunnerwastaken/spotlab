from pathlib import Path

from spotlab import connect


def main():
    with connect() as spot:
        if not spot.supports("depth"):
            print("Keine Tiefenkamera: echten Spot oder MuJoCo waehlen.")
            return
        depth = spot.depth("frontleft")
        rows, cols = depth.meters.shape
        print("Tiefe in Bildmitte (m):", depth.distance_at(cols // 2, rows // 2))
        print("Gueltige Pixel:", int(depth.valid.sum()), "von", depth.valid.size)
        print(depth.save(Path(__file__).parent / "auswertung" / "tiefe.npz"))


if __name__ == "__main__":
    main()
