"""Zeitgrenzen fuer alles, was in Tests einen echten Prozess startet.

Ohne sie HAENGT ein Lauf, statt zu scheitern. Lokal ist das nur aergerlich; in
der CI ist es toedlich: der Job laeuft bis zum globalen Limit und sagt am Ende
nicht, woran es lag. Ein Test, der 10 Minuten wartet und dann abbricht, ist
schlechter als einer, der nach 120 Sekunden sagt, welcher Prozess stumm blieb.

Grosszuegig gewaehlt: ein Schul-Laptop unter Last darf keine Fehlalarme
erzeugen. Die Grenze ist gegen HAENGEN gerichtet, nicht gegen Langsamkeit.
"""

import queue
import threading

TEST_TIMEOUT_S = 120

# Eine einzelne Protokollzeile kommt in Millisekunden oder gar nicht.
ZEILE_TIMEOUT_S = 30


def zeile_mit_frist(strom, sekunden=ZEILE_TIMEOUT_S):
    """Liest eine Zeile und gibt nach `sekunden` auf, statt ewig zu blockieren.

    `strom.readline()` laesst sich nicht unterbrechen, deshalb der Umweg ueber
    einen Faden. Der bleibt haengen, bis jemand den Prozess abraeumt und damit
    die Leitung schliesst — als Daemon gestartet, damit er pytest nicht am
    Beenden hindert.

    Rueckgabe: die Zeile, oder "" bei Zeitablauf (wie am Dateiende, damit der
    Aufrufer nur einen Fall behandeln muss).
    """
    kasten = queue.Queue(maxsize=1)

    def lesen():
        try:
            kasten.put(strom.readline())
        except Exception:                       # Leitung zu — Prozess ist weg
            kasten.put("")

    threading.Thread(target=lesen, daemon=True).start()
    try:
        return kasten.get(timeout=sekunden)
    except queue.Empty:
        return ""
