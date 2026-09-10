"""Die Tabelle auf der Platte — und der Nachtrag des Menschen.

Die Spalten sind die der Tabelle, die der Autor bisher von Hand gefuehrt hat
(Gruppengroesse, Klasse, Laufzeit, Uhrzeit), und daneben das, was Spot dazu
beisteuert: die GEMESSENE Strecke, das daraus gerechnete Tempo, wie viele
Personen er gesehen hat und der Grund, falls ein Durchgang verworfen wurde.

`klasse` und `gruppengroesse` bleiben LEER, bis ein Mensch sie eintraegt. Leer
heisst hier wirklich leer und nicht 0 oder 1 — dieselbe Regel wie ueberall:
fehlende Werte sind None, nie ein geratener Wert, der sich durch jede Auswertung
mittelt.

SEMIKOLON UND DEZIMALKOMMA. Diese Datei geht an einen Menschen, nicht an eine
Bibliothek: ein Doppelklick soll im Tabellenprogramm eine Tabelle zeigen und
nicht eine einzige Spalte voller Text. `lies()` rechnet beides beim Einlesen
zurueck, damit eine spaetere Auswertung wieder mit Zahlen arbeitet. Geschrieben
wird mit BOM (`utf-8-sig`), sonst zeigt Excel aus 'Gruppengroesse' Kraut und
Rueben.

Reine Standardbibliothek.
"""

import csv
import io
import time

from spotlab.errors import SpotlabError
from spotlab.record.atomar import schreibe_atomar

TRENNER = ";"
KODIERUNG = "utf-8-sig"

# Reihenfolge = Spaltenreihenfolge. Vorne das, was der Mensch liest und
# ausfuellt; hinten die Rohzeiten, die nur eine Auswertung braucht.
FELDER = (
    "nummer",
    "uhrzeit",
    "klasse",
    "gruppengroesse",
    "laufzeit_s",
    "tempo_m_s",
    "strecke_m",
    "personen",
    "gemessen",
    "verworfen",
    "gruende",
    "spanne_s",
    "gueltig",
    "t_start",
    "t_ende",
)

_GANZE = ("nummer", "gruppengroesse", "personen", "gemessen", "verworfen")
_KOMMA = ("laufzeit_s", "tempo_m_s", "strecke_m", "spanne_s")
_ZEIT = ("t_start", "t_ende")
# Spalten, die Text bleiben. `uhrzeit` steht hier, weil "09:41:03" keine Zahl
# ist und ein Umweg ueber Sekunden sie unlesbar machte -- die Spalte gibt es fuer
# den Menschen, die Rohzeit steht hinten in `t_start`.
_TEXT = ("klasse", "uhrzeit")


def zeile_aus(durchgang, strecke_m, uhrzeit=None, versatz=0.0):
    """Eine Tabellenzeile aus einem Durchgang.

    `t_start` und `t_ende` sind LAUFZEIT in Sekunden seit dem Start der
    Aufzeichnung — dieselbe Zeitbasis wie `t` im Bildindex `kamera/kamera.jsonl`.
    Nur so findet der Nachtrag die Bilder zu einem Durchgang.

    `versatz` ist die Wanduhrzeit, die zur Laufzeit 0 gehoerte; daraus wird die
    Spalte `uhrzeit` gerechnet. `uhrzeit` direkt zu setzen geht auch — die Tests
    tun es.
    """
    laufzeit = durchgang.laufzeit_s
    return {
        "nummer": durchgang.nummer,
        "uhrzeit": uhrzeit or time.strftime(
            "%H:%M:%S", time.localtime(durchgang.t_start + versatz)
        ),
        "klasse": "",
        "gruppengroesse": None,
        "laufzeit_s": laufzeit,
        "tempo_m_s": (strecke_m / laufzeit) if laufzeit else None,
        "strecke_m": float(strecke_m),
        "personen": durchgang.personen,
        "gemessen": durchgang.gemessen,
        "verworfen": durchgang.verworfen,
        "gruende": durchgang.gruende,
        "spanne_s": durchgang.spanne_s,
        "gueltig": durchgang.gueltig,
        "t_start": durchgang.t_start,
        "t_ende": durchgang.t_ende,
    }


# ------------------------------------------------------------ Schreiben


def _text(feld, wert):
    if wert is None:
        return ""
    if feld == "gueltig":
        return "ja" if wert else "nein"
    if feld == "gruende":
        return " ".join(wert)
    if feld in _KOMMA:
        return f"{float(wert):.2f}".replace(".", ",")
    if feld in _ZEIT:
        return f"{float(wert):.3f}".replace(".", ",")
    return str(wert)


def schreibe(pfad, zeilen):
    """Die ganze Tabelle atomar ersetzen. True, wenn es gelang.

    Atomar, weil die Datei waehrend des Laufs waechst und gleichzeitig offen
    sein kann — dieselbe Begruendung wie bei `fahrt.json`.
    """
    puffer = io.StringIO()
    schreiber = csv.DictWriter(
        puffer, fieldnames=list(FELDER), delimiter=TRENNER, lineterminator="\n"
    )
    schreiber.writeheader()
    for zeile in zeilen:
        schreiber.writerow({feld: _text(feld, zeile.get(feld)) for feld in FELDER})
    return schreibe_atomar(pfad, "﻿" + puffer.getvalue())


# --------------------------------------------------------------- Lesen


def _wert(feld, text):
    text = (text or "").strip()
    if feld == "gueltig":
        return text == "ja"
    if feld == "gruende":
        return tuple(text.split()) if text else ()
    if feld in _TEXT:
        return text
    if text == "":
        return None
    if feld in _GANZE:
        return int(text)
    return float(text.replace(",", "."))


def lies(pfad):
    """Die Tabelle als Liste von Zeilen — Zahlen wieder als Zahlen."""
    from pathlib import Path

    text = Path(pfad).read_text(encoding=KODIERUNG)
    leser = csv.DictReader(io.StringIO(text), delimiter=TRENNER)
    return [{feld: _wert(feld, zeile.get(feld)) for feld in FELDER} for zeile in leser]


# ------------------------------------------------------------- Nachtrag


def ergaenze(pfad, nummer, klasse=None, gruppengroesse=None):
    """Was der Mensch nach dem Ansehen des Abschnitts eintraegt.

    Nur diese beiden Spalten. Spots Messwerte bleiben stehen — wer die Zeit
    korrigieren will, hat den falschen Versuch gemacht und nicht die falsche
    Zahl.
    """
    zeilen = lies(pfad)
    treffer = [z for z in zeilen if z["nummer"] == int(nummer)]
    if not treffer:
        raise SpotlabError(
            f"Kein Durchgang mit der Nummer {nummer} in dieser Tabelle. "
            f"Vorhanden: {', '.join(str(z['nummer']) for z in zeilen) or 'keiner'}."
        )
    if klasse is not None:
        treffer[0]["klasse"] = str(klasse)
    if gruppengroesse is not None:
        treffer[0]["gruppengroesse"] = int(gruppengroesse)
    schreibe(pfad, zeilen)
    return treffer[0]
