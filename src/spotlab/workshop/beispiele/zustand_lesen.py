from spotlab import connect


def main():
    with connect() as spot:
        state = spot.state
        # Ohne Akkumeldung (Physikmodus) ist state.battery None, nicht 0.
        akku = f"{state.battery:.1f} %" if state.battery is not None else "unbekannt"
        print(f"Akku: {akku}, Motoren: {state.powered}")
        print(f"Odom: x={state.x:.2f} m, y={state.y:.2f} m")
        print(f"Richtung: {state.heading:.1f} Grad, Tempo: {state.speed:.2f} m/s")


if __name__ == "__main__":
    main()
