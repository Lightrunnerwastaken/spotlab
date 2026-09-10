"""Autonome Messhilfe für Schulversuche — heute: Gehzeit und Gruppengrösse.

Der Anlass ist ein Verhaltensbiologie-Versuch: wie hängt die Gehgeschwindigkeit
von der Gruppengrösse ab? Bisher steht ein Mensch mit der Stoppuhr im Gang und
kann immer nur EINE Gruppe messen. Spot kann zusehen und für jede Person
gleichzeitig die Zeit nehmen.

Die Aufteilung ist dieselbe wie beim Folgen: was Spot MISST, steht getrennt von
dem, was ein Mensch ENTSCHEIDET.

    strecke.py     Wie lang ist die Strecke — gemessen aus zwei AprilTags, nicht
                   eingetippt. Dazu die Projektion einer Person auf die Strecke.
    zeitnahme.py   Wer wann losgeht und ankommt, mehrere gleichzeitig. Und wann
                   ein Durchgang VERWORFEN wird (stehen geblieben, umgekehrt,
                   verloren) — verworfen heisst hier protokolliert, nicht
                   verschwiegen.
    durchgang.py   Welche Querungen zeitlich zusammengehören. Nur ein VORSCHLAG:
                   ob drei Leute eine Gruppe sind oder drei Einzelne, kann Spot
                   nicht wissen.
    tabelle.py     Die Tabelle auf der Platte (CSV, Standardbibliothek) und der
                   Nachtrag des Menschen: Klasse und Gruppengrösse.

Was hier NICHT steht, ist ebenso wichtig:

- **Kein Alter aus dem Gesicht.** Der Wunsch stand im Raum, die Messung spricht
  dagegen: über die Aufzeichnung vom 12.08.2026 fand der Gesichtserkenner in 4
  von 107 Takten etwas, und die zwei nachgesehenen Treffer waren eine Stuhllehne
  und ein Schienbein. Eine Altersschätzung darauf wäre ein Modell auf einem
  Modell, und die Zahl landete ununterscheidbar neben gemessenen Zeiten.
- **Keine Gruppenerkennung.** Spot liefert Zeiten und einen Vorschlag; die
  Gruppengrösse trägt der Mensch nach, nachdem er den Abschnitt angesehen hat.
- **Keine Bewegung.** Spot steht und schaut zu. Das Programm läuft deshalb über
  `spotlab.connect(nur_lesen=True)`: kein Lease, kein Not-Aus-Endpunkt, und die
  Aufsichtsperson behält das Tablet in der Hand.

`strecke`, `zeitnahme`, `durchgang` und `tabelle` sind reine
Standardbibliothek — sie rechnen auf Zahlen, nicht auf Robotern. Deshalb sind
sie ohne Spot prüfbar, und deshalb darf eine spätere Auswertung sie importieren.
"""
