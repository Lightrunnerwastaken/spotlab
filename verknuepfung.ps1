# Legt die Verknuepfung an, die Schueler anklicken.
#
# Eigenes Skript statt eines Abschnitts in einrichten.ps1, damit es sich einzeln
# starten UND einzeln pruefen laesst -- ein Test, der erst die ganze Installation
# durchlaufen muesste, wird nie ausgefuehrt.
#
# Wiederholbar wie einrichten.ps1: dieselbe Datei wird ueberschrieben, es
# entsteht keine zweite Verknuepfung.

param(
    # Wohin die Verknuepfung soll. Standard ist der Desktop des angemeldeten
    # Benutzers -- an der Schule hat jeder sein eigenes Profil.
    [string]$Ordner = [Environment]::GetFolderPath("Desktop"),
    [string]$Name   = "spotlab"
)

$ErrorActionPreference = "Stop"

$wurzel  = $PSScriptRoot
$ziel    = Join-Path $wurzel "starten.ps1"
$icon    = Join-Path $wurzel "spotlab.ico"

if (-not (Test-Path $ziel)) { throw "starten.ps1 liegt nicht neben diesem Skript" }
if (-not (Test-Path $Ordner)) { New-Item -ItemType Directory -Path $Ordner | Out-Null }

$lnk = Join-Path $Ordner "$Name.lnk"

# Die Verknuepfung ruft PowerShell auf, nicht starten.ps1 direkt: ein
# doppelgeklicktes .ps1 wird von Windows im Editor GEOEFFNET, nicht ausgefuehrt.
$shell = New-Object -ComObject WScript.Shell
$v = $shell.CreateShortcut($lnk)
$v.TargetPath       = (Get-Command powershell).Source
$v.Arguments        = "-NoProfile -ExecutionPolicy Bypass -File `"$ziel`""
$v.WorkingDirectory = $wurzel
$v.Description      = "Den Boston Dynamics Spot programmieren"
if (Test-Path $icon) { $v.IconLocation = $icon }
$v.Save()

Write-Host "Verknuepfung angelegt: $lnk" -ForegroundColor Green
