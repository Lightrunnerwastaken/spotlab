# spotlab starten -- das Ziel der Desktop-Verknuepfung.
#
# Selbstheilend: fehlt die Umgebung, wird sie zuerst eingerichtet. Ein Schueler
# soll auch auf einem frisch aufgesetzten Laptop mit EINEM Klick zum Fenster
# kommen; dass der erste Klick dann ein paar Minuten braucht, ist verkraftbar --
# eine Fehlermeldung, die niemand einordnen kann, waere es nicht.
#
# `pythonw.exe` statt `spotlab.exe`: Letzteres ist ein Konsolenskript und
# liesse ein schwarzes Fenster offen, solange die GUI laeuft.

param(
    # Gibt aus, was geschehen WUERDE, und startet nichts. Fuer die Tests --
    # eine echte GUI liesse sich dort nicht wieder schliessen.
    [switch]$NurPruefen
)

$ErrorActionPreference = "Stop"

# Das eigene Verzeichnis, nicht das Arbeitsverzeichnis: eine Verknuepfung wird
# von irgendwo gestartet, und Windows setzt das Arbeitsverzeichnis nicht
# zuverlaessig auf den Zielordner.
$wurzel  = $PSScriptRoot
$pythonw = Join-Path $wurzel ".venv\Scripts\pythonw.exe"

# Die eigene .venv hat Vorrang: auf einem Schul-Laptop ist sie das, was
# einrichten.ps1 angelegt und geprueft hat.
if (-not (Test-Path $pythonw) -and -not (Test-Path (Join-Path $wurzel "release.json"))) {
    # Steht schon ein spotlab im PATH? Das ist der Entwicklungsrechner-Fall --
    # dort liegt spotlab oft in einer Conda-Umgebung. Ohne diese Suche legte ein
    # Doppelklick dort ein ZWEITES Environment an (allein PySide6 sind 642 MB),
    # obwohl alles laengst installiert ist.
    $vorhanden = Get-Command spotlab -ErrorAction SilentlyContinue
    if ($vorhanden) {
        $skripte = Split-Path $vorhanden.Source -Parent
        # conda legt pythonw.exe EINE Ebene ueber Scripts\ ab, ein venv darin.
        foreach ($kandidat in @(
            (Join-Path (Split-Path $skripte -Parent) "pythonw.exe"),
            (Join-Path $skripte "pythonw.exe")
        )) {
            if (Test-Path $kandidat) { $pythonw = $kandidat; break }
        }
    }
}

if (-not (Test-Path $pythonw)) {
    $einrichten = Join-Path $wurzel "einrichten.ps1"
    if ($NurPruefen) {
        Write-Host "wuerde einrichten: $einrichten"
        exit 0
    }
    Write-Host "Die Umgebung fehlt -- sie wird jetzt eingerichtet." -ForegroundColor Cyan
    Write-Host "Das dauert beim ersten Mal einige Minuten." -ForegroundColor DarkGray
    Write-Host ""
    & powershell -NoProfile -ExecutionPolicy Bypass -File $einrichten
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Die Einrichtung ist gescheitert. Die Meldungen oben sagen, woran." -ForegroundColor Red
        Write-Host "Taste druecken zum Schliessen ..." -ForegroundColor DarkGray
        # Ohne das schliesst sich das Fenster sofort und niemand liest den Grund.
        [void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
}

if ($NurPruefen) {
    Write-Host "wuerde starten: $pythonw -m spotlab.cli gui"
    exit 0
}

# Start-Process statt `&`: die Konsole schliesst sich sofort, das Fenster bleibt.
Start-Process -FilePath $pythonw -ArgumentList "-m", "spotlab.cli", "gui" -WorkingDirectory $wurzel -WindowStyle Hidden
