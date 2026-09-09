from spotlab import connect


def main():
    with connect() as spot:
        if not spot.supports("look"):
            print("Dieses Backend bietet kein Hindernisgitter.")
            return
        view = spot.look()
        for name in ("front", "left", "right", "back"):
            ray = getattr(view, name)
            if not ray.known:
                print(f"{name}: unbekannt, geprueft ab {ray.start:.2f} bis {ray.observed_distance:.2f} m")
            else:
                print(f"{name}: {ray.status} bei {ray.distance:.2f} m ab Koerpermitte")
        print("Momentaufnahme, keine automatische Fahrfreigabe.")


if __name__ == "__main__":
    main()
