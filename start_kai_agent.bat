@echo off
setlocal

rem Wechsel in das Arbeitsverzeichnis des Projekts
cd /d "%~dp0"

echo [Bot] K.AI Agent wird gestartet (PowerShell 7)...

rem Wir nutzen pwsh.exe, da es bereits installiert ist (v7.5.4)
rem Das PowerShell-Skript sorgt fuer UTF-8, Icons und Animationen.
pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_kai_agent.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [Fehler] Der Agent konnte in PowerShell 7 nicht gestartet werden.
    echo Versuche es in der Standard-CMD...
    pause
    ".venv\Scripts\python.exe" -m app.main
    pause
)

endlocal
