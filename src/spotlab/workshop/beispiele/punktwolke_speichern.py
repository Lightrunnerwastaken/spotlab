from pathlib import Path

from spotlab import connect


def main():
    with connect() as spot:
        if not spot.supports("point_cloud"):
            print("Keine Tiefenkamera: echten Spot oder MuJoCo waehlen.")
            return
        depth = spot.depth("frontleft")
        cloud = depth.point_cloud(frame="body", stride=2, max_distance=4)
        print(len(cloud.points), "Punkte in Metern, Rahmen:", cloud.frame)
        print(cloud.save(Path(__file__).parent / "auswertung" / "punkte.ply"))
        # Fuer mehrere Aufnahmen einen gemeinsamen Weltframe verwenden:
        world = depth.point_cloud(frame="vision", stride=2, max_distance=4)
        print(world.save(Path(__file__).parent / "auswertung" / "punkte_vision.npz"))


if __name__ == "__main__":
    main()
