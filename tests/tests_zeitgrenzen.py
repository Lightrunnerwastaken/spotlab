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
import time
from types import SimpleNamespace

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


def warte_bis(bedingung, worauf, grenze_s=TEST_TIMEOUT_S, takt_s=0.02, zwischendurch=None):
    """Pollt, BIS `bedingung()` wahr ist -- und scheitert nach `grenze_s` AUSDRUECKLICH.

    Der Gegenentwurf zur festen Frist: `QTimer.singleShot(5000)`, `time.sleep(4)`,
    `qWait(400)` -- und danach ungeprueft weiter. Unter Last war die Frist zu
    kurz, und aus einem Zeitproblem wurde eine falsche inhaltliche Aussage: eine
    leere Dateiliste, 0.185 statt 0.2 m, ein fehlendes Bild (sieben volle Laeufe,
    14.-16.09.2026). Hier ist die Grenze nur das Netz gegen HAENGEN: sobald die
    Bedingung eintritt, geht es weiter, und beim Ablauf sagt die Meldung, WORAUF
    gewartet wurde.

    `worauf`: Text -- oder eine Funktion, die den Text erst beim Scheitern baut
    und dann den zuletzt gesehenen Wert nennen kann. `zwischendurch` laeuft vor
    jeder Pruefung: bei Qt `qapp.processEvents`, sonst kommt kein Signal an; beim
    Totmann der Fahrt das erneute Schreiben des Befehls.
    Rueckgabe: der wahre Wert der Bedingung.
    """
    ende = time.monotonic() + grenze_s
    while True:
        # Erst pruefen, dann Ereignisse verarbeiten: eine schon erfuellte Bedingung
        # (Signal kam synchron) soll nicht auf einen Rueckstand der Ereignisschleife
        # warten -- in der vollen Suite kostete ein processEvents() bis zu 10 s.
        wert = bedingung()
        if wert:
            return wert
        if time.monotonic() >= ende:
            text = worauf() if callable(worauf) else worauf
            raise AssertionError(f"Nach {grenze_s:.0f} s nicht eingetreten: {text}")
        if zwischendurch is not None:
            zwischendurch()
        time.sleep(takt_s)


def simuhr(backend):
    """Eine Wanduhr fuer `backends.physics`, die mit der Simulation laeuft.

    Der Backend prueft `end_time_secs` und den Ablauf eines Kommandos an
    `time.time()` -- am Roboter richtig (test_velocity_expiry_uses_wall_clock...),
    im Offline-Lauf mit `realtime=False` aber ein Mass fuer Maschinenlast: ein
    `advance(.001)` ist dort ein ganzer Beinschritt (rund 3.3 s Sim-Zeit, 1.2 s
    Wanduhr allein, unter Last ein Vielfaches). Eine Frist von 120 s Wanduhr lief
    unter Last ab, der Backend sandte Stopp, und die Fuesse hoben nicht mehr
    (15.09.2026). Mit dieser Uhr sind Endzeit und Ablauf Sim-Zeit: `_tick` und
    `send_command` sehen dieselbe Uhr wie die Physik.

        uhr = simuhr(b); monkeypatch.setattr(physics, 'time', uhr)
        b.send_command(..., end_time_secs=uhr.time() + 600)
    """
    wand0, sim0 = time.time(), backend.sim.time
    return SimpleNamespace(time=lambda: wand0 + backend.sim.time - sim0,
                           monotonic=time.monotonic, sleep=time.sleep)
