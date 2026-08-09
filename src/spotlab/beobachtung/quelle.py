"""Die Nur-Lese-Zustandsquelle — der Kern der Sicherheitsaussage.

`StateSampler` braucht vom Backend genau eine Methode: `robot_state()`. Diese
Klasse hat genau diese eine. Es gibt hier keine Kommando-Methode, die man
versehentlich aufrufen könnte — das ist stärker als eine Capability-Prüfung,
die erst zur Laufzeit wirft.

Daran hängt, warum der Beobachter-Modus vor Abnahmepunkt A1 benutzt werden
darf: er nimmt dem Tablet nichts weg und kann den Roboter nicht bewegen.
`tests/test_beobachtung_quelle.py` hält beides fest — auch, dass der Abtaster
nicht heimlich anfängt, mehr zu verlangen.
"""


class Zustandsquelle:
    def __init__(self, state_client):
        self._state = state_client

    def robot_state(self):
        return self._state.get_robot_state()
