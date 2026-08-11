# spotlab auf einem Schul-Laptop einrichten.
#
# Warum ein Skript und nicht drei Zeilen im README: die drei Zeilen wurden auf
# jedem Laptop anders getippt. Einer hatte das Extra [gui] vergessen und keine
# Oberflaeche, einer installierte in das System-Python und legte sich damit
# eine andere numpy-Fassung hin, als das uebrige Schulsystem erwartet.
#
# Das Skript ist absichtlich WIEDERHOLBAR: zweimal ausgefuehrt aendert es
# nichts und meldet trotzdem, ob alles steht.
#
# Aufruf im Ordner, in dem diese Datei liegt:
#     powershell -ExecutionPolicy Bypass -File einrichten.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$umgebung = Join-Path $PSScriptRoot ".venv"
$python   = Join-Path $umgebung "Scripts\python.exe"

# ---------------------------------------------------------------- Python finden
# py -3.13 zuerst: der Launcher ist auf einer Windows-Installation da, und die
# gewuenschte Fassung ist damit waehlbar. `python` allein trifft, was zufaellig
# im PATH steht -- an der Schule oft eine Anaconda-Installation.
#
# Jeder Kandidat wird AUSPROBIERT, nicht nur gefunden: `py` ist auch dann da,
# wenn keine einzige Fassung dahinter registriert ist ("No suitable Python
# runtime found"). Genau daran ist die erste Fassung dieses Skripts
# gescheitert.
$starter = $null
foreach ($versuch in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("python"))) {
    if (-not (Get-Command $versuch[0] -ErrorAction SilentlyContinue)) { continue }
    $rest = @($versuch[1..($versuch.Length - 1)])
    try {
        # 2>$null: ein nicht registriertes `py -3.13` schreibt vier Zeilen
        # "No suitable Python runtime found" nach stderr. Das ist hier kein
        # Fehler, sondern die Antwort auf die Frage -- und im Ablauf nur Laerm,
        # der aussieht, als sei etwas schiefgegangen.
        $gemeldet = & $versuch[0] @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    } catch {
        continue
    }
    if ($LASTEXITCODE -ne 0) { continue }
    # Die Obergrenze steht auch in pyproject.toml (requires-python). Ein zu
    # neues Python scheitert sonst erst bei pip, mit einer Meldung, die nach
    # einem Netzproblem aussieht.
    $teile = $gemeldet.Trim().Split(".")
    if ([int]$teile[0] -ne 3 -or [int]$teile[1] -lt 11 -or [int]$teile[1] -gt 14) {
        Write-Host "  $($versuch -join ' ') ist Python $gemeldet -- gebraucht wird 3.11 bis 3.14." -ForegroundColor DarkGray
        continue
    }
    $starter = $versuch
    break
}
if ($null -eq $starter) {
    Write-Host "Kein passendes Python gefunden (gebraucht: 3.11 bis 3.14)." -ForegroundColor Red
    Write-Host "Herunterladen unter https://www.python.org/downloads/ und beim Installieren" -ForegroundColor Red
    Write-Host "'Add python.exe to PATH' ankreuzen." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------ Umgebung anlegen
if (-not (Test-Path $python)) {
    Write-Host "Lege die Umgebung unter .venv an ..." -ForegroundColor Cyan
    $rest = @($starter[1..($starter.Length - 1)])
    & $starter[0] @rest -m venv $umgebung
    if ($LASTEXITCODE -ne 0) { throw "venv liess sich nicht anlegen" }
} else {
    Write-Host "Umgebung .venv ist schon da." -ForegroundColor DarkGray
}

$fassung = & $python -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Host "Python $fassung in .venv" -ForegroundColor DarkGray

# -------------------------------------------------------------- Installieren
# Alle drei Extras. Ohne [gui] gibt es kein Fenster, ohne [mcp] keine
# Agenten-Anbindung, ohne [dev] kein pytest -- und alle drei wurden schon
# einzeln vergessen.
Write-Host "Installiere spotlab mit gui, mcp und dev ..." -ForegroundColor Cyan
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -e ".[dev,gui,mcp]"
if ($LASTEXITCODE -ne 0) { throw "Installation fehlgeschlagen" }

# ------------------------------------------------------------------ Nachweis
# Der Teil, der den Unterschied zu „hat wohl geklappt" macht.
Write-Host ""
Write-Host "Pruefe die Installation ..." -ForegroundColor Cyan
& $python -c @"
import importlib.util as u, sys
fehlt = [n for n in ('bosdyn.client', 'PySide6.QtWidgets', 'mcp', 'pytest') if not u.find_spec(n)]
if fehlt:
    sys.exit('FEHLT: ' + ', '.join(fehlt))
import spotlab
print('spotlab', spotlab.__version__, 'einsatzbereit')
"@
if ($LASTEXITCODE -ne 0) { throw "Die Installation ist unvollstaendig" }

Write-Host ""
Write-Host "Fertig. Weiter geht es mit:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\activate"
Write-Host "    spotlab login       # IP, Benutzer, Passwort in den Windows-Tresor"
Write-Host "    spotlab doctor      # prueft Netz, Anmeldung, Zeitsync, Not-Aus, Lease"
Write-Host "    spotlab gui"
