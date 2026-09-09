from spotlab import connect


def main():
    with connect() as spot:
        if not spot.supports("lights") or not spot.supports("beep"):
            print("Licht und Summer werden hier nicht unterstuetzt.")
            return
        spot.lights("blue", duration=1, brightness=0.25)
        spot.beep("C", duration=0.3)
        print("Befehle abgeschlossen; dryrun prueft nur Protobufs, ohne Wiedergabe.")


if __name__ == "__main__":
    main()
