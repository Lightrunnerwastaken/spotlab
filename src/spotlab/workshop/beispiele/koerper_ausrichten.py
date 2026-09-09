from spotlab import connect


def main():
    with connect() as spot:
        if not spot.supports("pose"):
            print("Koerperausrichtung wird in diesem Backend noch nicht unterstuetzt.")
            return
        spot.power_on()
        spot.stand()
        spot.pose(pitch=5, yaw=10, height=0.03)
        spot.pose()
        spot.sit()


if __name__ == "__main__":
    main()
