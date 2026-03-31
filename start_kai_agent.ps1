# K.AI Agent Starter Script (PowerShell 7 Edition)
# Sorgt fuer UTF-8, Icons und Animationen

$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "K.AI Agent (v0.1.0)"

Write-Host "[Bot] K.AI Agent wird gestartet..." -ForegroundColor Cyan

# Pfad zum venv
$python = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "[Fehler] Virtuelle Umgebung nicht gefunden! Bitte install.ps1 ausfuehren."
    Read-Host "Druecke Enter zum Beenden..."
    exit 1
}

# Start des Agents
try {
    & $python -m app.main
} catch {
    Write-Error "Agent wurde mit Fehlern beendet: $_"
    Read-Host "Druecke Enter zum Beenden..."
}
