# Schueler: GUI + Sim aus dem Release. Entwickler: ausdruecklich -Entwickler.
param(
    [switch]$Entwickler,
    [switch]$MitSim,
    [string]$SimPfad = (Join-Path $PSScriptRoot "..\matura-spot"),
    [switch]$KeineVerknuepfung
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$anforderungen = Join-Path $PSScriptRoot "schueler-requirements.txt"

if (-not $Entwickler -and -not (Test-Path -LiteralPath $anforderungen)) {
    throw "Bitte das Schueler-Release-ZIP herunterladen und entpacken (nicht 'Source code'). Entwickler verwenden -Entwickler."
}
if ($Entwickler -and $MitSim) {
    if (-not (Test-Path -LiteralPath (Join-Path $SimPfad "pyproject.toml"))) {
        throw "Sim-Quellen fehlen unter '$SimPfad'. -SimPfad angeben. Schueler brauchen diese Quellen nicht."
    }
    $SimPfad = (Resolve-Path -LiteralPath $SimPfad).Path
}

if (-not (Test-Path -LiteralPath $python)) {
    $starter = $null
    foreach ($versuch in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3.14"), @("python"))) {
        if (-not (Get-Command $versuch[0] -ErrorAction SilentlyContinue)) { continue }
        $rest = @($versuch | Select-Object -Skip 1)
        try {
            & $versuch[0] @rest -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,15) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { $starter = $versuch; break }
        } catch { continue }
    }
    if ($null -eq $starter) { throw "Python 3.11 bis 3.14 fehlt. Bitte Python 3.13 installieren lassen." }
    $rest = @($starter | Select-Object -Skip 1)
    & $starter[0] @rest -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Python-Umgebung konnte nicht angelegt werden." }
}
& $python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,15) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Vorhandene .venv verwendet eine nicht unterstuetzte Python-Version." }

if ($Entwickler) {
    $extras = ".[dev,gui,mcp]"
    if ($MitSim) { $extras = ".[dev,gui,mcp,sim]" }
    $pakete = @("-e", $extras)
    if ($MitSim) { $pakete += @("-e", $SimPfad) }
    & $python -m pip install @pakete
} else {
    Write-Host "Installiere Spotlab mit GUI und Simulation (ohne Entwicklerwerkzeuge) ..."
    # Feste lokale App-/Runtime-Versionen; binaere Abhaengigkeiten statt Compilerbedarf.
    & $python -m pip install --only-binary=:all: -r $anforderungen
}
if ($LASTEXITCODE -ne 0) { throw "Installation fehlgeschlagen. Internetzugang und Meldung oben pruefen." }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Paketkonflikt: siehe pip-check-Ausgabe oben." }
if (-not $Entwickler) {
    & $python (Join-Path $PSScriptRoot "pruefe_schueler.py")
    if ($LASTEXITCODE -ne 0) { throw "GUI-/Sim-Installationspruefung fehlgeschlagen." }
} else {
    & $python -c "import spotlab; from PySide6 import QtWidgets; print('Entwicklerumgebung installiert')"
    if ($LASTEXITCODE -ne 0) { throw "Entwicklerumgebung unvollstaendig." }
}
if (-not $KeineVerknuepfung) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "verknuepfung.ps1")
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Verknuepfung fehlgeschlagen. Mit starten.ps1 starten."
    }
}
Write-Host "Fertig. Spotlab ueber die Desktop-Verknuepfung starten."
