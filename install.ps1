param(
  [switch]$NoGui,
  [switch]$ConfigureOnly,
  [switch]$SkipDeps,
  [switch]$SkipPowerShell7,
  [switch]$SkipSbertCache
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Temporäres Logging für Fehlersuche
$logFile = Join-Path $PSScriptRoot "install_debug.log"
Start-Transcript -Path $logFile -Append
Write-Host "=== Installation gestartet: $(Get-Date) ===" -ForegroundColor Cyan

function Ensure-PowerShell7 {
  # Prüfe ob pwsh bereits installiert
  $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
  if ($pwsh) {
    Write-Host "✅ PowerShell 7 bereits installiert: $($pwsh.Version)" -ForegroundColor Green
    return $true
  }
  
  Write-Host "⚠️  PowerShell 7 nicht gefunden - starte automatische Installation..." -ForegroundColor Cyan
  
  # Methode 1: winget (Windows 10 1809+)
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    Write-Host "   Nutze winget..." -ForegroundColor Gray
    try {
      & winget install --id Microsoft.PowerShell --source winget --silent --accept-package-agreements --accept-source-agreements
      if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ PowerShell 7 via winget installiert" -ForegroundColor Green
        Write-Host "   HINWEIS: Oeffne nach dem Setup ein neues Terminal fuer pwsh.exe" -ForegroundColor Yellow
        return $true
      }
    } catch {
      Write-Host "⚠️  winget Installation fehlgeschlagen" -ForegroundColor Yellow
    }
  }
  
  # Methode 2: Direkter MSI-Download
  Write-Host "   Lade PowerShell 7 MSI herunter..." -ForegroundColor Gray
  $msiUrl = "https://github.com/PowerShell/PowerShell/releases/download/v7.4.8/PowerShell-7.4.8-win-x64.msi"
  $msiPath = Join-Path $env:TEMP "PowerShell-7.msi"
  
  try {
    # Download mit .NET WebClient (PowerShell 5.x kompatibel)
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($msiUrl, $msiPath)
    
    Write-Host "   Installiere MSI..." -ForegroundColor Gray
    Start-Process msiexec.exe -ArgumentList "/i `"$msiPath`" /quiet /norestart" -Wait
    
    Remove-Item $msiPath -ErrorAction SilentlyContinue
    
    Write-Host "✅ PowerShell 7 installiert" -ForegroundColor Green
    Write-Host "   WICHTIG: Öffne ein NEUES Terminal für pwsh.exe" -ForegroundColor Yellow
    return $true
    
  } catch {
    Write-Host "❌ Installation fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "   Manuelle Installation: https://aka.ms/powershell" -ForegroundColor Yellow
    return $false
  }
}

function Nz($v, $d) { if ($null -eq $v) { return $d }; return $v }
function Normalize-WinPath([string]$p) {
  $s = [string](Nz $p "")
  if ([string]::IsNullOrWhiteSpace($s)) { return $s }
  return $s.Replace("/", "\")
}

function Convert-ObjToHash($obj) {
  if ($null -eq $obj) { return $null }
  if ($obj -is [hashtable]) { return $obj }
  if ($obj -is [pscustomobject]) {
    $h = @{}
    foreach ($p in $obj.PSObject.Properties) { $h[$p.Name] = Convert-ObjToHash $p.Value }
    return $h
  }
  if (($obj -is [System.Collections.IEnumerable]) -and -not ($obj -is [string])) {
    $a = @()
    foreach ($i in $obj) { $a += ,(Convert-ObjToHash $i) }
    return $a
  }
  return $obj
}

function Merge-Hash([hashtable]$a, [hashtable]$b) {
  $r = @{}
  foreach ($k in $a.Keys) { $r[$k] = $a[$k] }
  foreach ($k in $b.Keys) {
    if (($r[$k] -is [hashtable]) -and ($b[$k] -is [hashtable])) { $r[$k] = Merge-Hash $r[$k] $b[$k] }
    else { $r[$k] = $b[$k] }
  }
  return $r
}

function Split-Models([string]$s) {
  if ([string]::IsNullOrWhiteSpace($s)) { return @() }
  return @(($s -split '[,;\r\n]+' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) | Select-Object -Unique)
}

function To-Array($v) {
  if ($null -eq $v) { return @() }
  if (($v -is [System.Collections.IEnumerable]) -and -not ($v -is [string])) { return @($v) }
  return @($v)
}

function Default-Config {
  @{
    security = @{ active_role = "user"; execution_mode = "unrestricted" }
    filesystem = @{ full_access = $false; delete_to_trash = $true }
    llm = @{ active_provider_id = "openai"; active_model = "gpt-4o-mini"; temperature = 0.2 }
    providers = @{
      openai = @{ type = "openai_compatible"; api_key = ""; base_url = "https://api.openai.com/v1"; models = @("gpt-4o-mini"); default_model = "gpt-4o-mini" }
      gemini = @{ type = "gemini"; api_key = ""; base_url = "https://generativelanguage.googleapis.com"; models = @("gemini-2.0-flash"); default_model = "gemini-2.0-flash" }
      claude = @{ type = "anthropic"; api_key = ""; base_url = "https://api.anthropic.com"; models = @("claude-3-5-sonnet-latest"); default_model = "claude-3-5-sonnet-latest" }
      grok = @{ type = "xai"; api_key = ""; base_url = "https://api.x.ai/v1"; models = @("grok-2-latest"); default_model = "grok-2-latest" }
    }
    memory = @{ db_path = "data\memory.db"; cache_sbert_model = $true }
    workspace = "data\workspace"
    messenger = @{
      telegram = @{ enabled = $false; token = ""; require_prefix = $false; command_prefix = "/K.AI Agent" }
      discord = @{ enabled = $false; token = ""; channel_id = ""; require_prefix = $true; command_prefix = "/Lucy"; gateway_enabled = $true }
      session_memory_enabled = $true
    }
    tts = @{ enabled = $false; voice = "de-DE-ConradNeural"; mode = "reply_audio" }
    logging = @{ enabled = $true; verbose = $true; audit_log_path = "data\logs\audit.log" }
    mcp = @{
      timeout = 45;
      cache_ttl_sec = 300;
      local_server_enabled = $true;
      servers = @{};
      registry_sources = @(
        @{ id = "mcp_registry_official"; type = "mcp_registry"; name = "Official MCP Registry"; base_url = "https://registry.modelcontextprotocol.io"; enabled = $true },
        @{ id = "github"; type = "github"; name = "GitHub (topic:mcp-server)"; base_url = "https://api.github.com"; enabled = $true }
      )
    }
    tools = @{ dynamic_timeout_sec = 120; max_output_chars = 8000 }
  }
}

function Normalize-Config([hashtable]$cfg) {
  if (-not ($cfg.providers -is [hashtable])) { $cfg.providers = @{} }
  foreach ($providerId in @($cfg.providers.Keys)) {
    $p = Convert-ObjToHash $cfg.providers[$providerId]
    $models = @()
    if ($p.models -is [string]) { $models = @(Split-Models ([string]$p.models)) }
    elseif (($p.models -is [System.Collections.IEnumerable]) -and -not ($p.models -is [string])) {
      $models = @($p.models | ForEach-Object { [string]$_ } | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique)
    }
    $models = To-Array $models
    if (@($models).Count -eq 0) {
      $d = [string](Nz $p.default_model "")
      if ($d -match '[,;]') { $d = (Split-Models $d | Select-Object -First 1) }
      if ([string]::IsNullOrWhiteSpace($d)) { $d = "model-1" }
      $models = @($d)
    }
    $p.models = $models
    $p.default_model = [string]$models[0]
    if (-not $p.ContainsKey("api_key")) { $p.api_key = "" }
    if (-not $p.ContainsKey("base_url")) { $p.base_url = "" }
    if (-not $p.ContainsKey("type")) { $p.type = "openai_compatible" }
    $cfg.providers[$providerId] = $p
  }
  if (-not ($cfg.llm -is [hashtable])) { $cfg.llm = @{} }
  $ap = [string](Nz $cfg.llm.active_provider_id "")
  if ([string]::IsNullOrWhiteSpace($ap) -or -not $cfg.providers.ContainsKey($ap)) {
    $ap = if ($cfg.providers.Count -gt 0) { [string]($cfg.providers.Keys | Select-Object -First 1) } else { "openai" }
  }
  $cfg.llm.active_provider_id = $ap
  $am = [string](Nz $cfg.llm.active_model "")
  if ($am -match '[,;]') { $am = (Split-Models $am | Select-Object -First 1) }
  if ([string]::IsNullOrWhiteSpace($am) -or -not (@($cfg.providers[$ap].models) -contains $am)) { $am = [string]$cfg.providers[$ap].default_model }
  $cfg.llm.active_model = $am
  try { $cfg.llm.temperature = [math]::Round([double]$cfg.llm.temperature, 2) } catch { $cfg.llm.temperature = 0.2 }
  if ($cfg.llm.temperature -lt 0) { $cfg.llm.temperature = 0 }
  if ($cfg.llm.temperature -gt 2) { $cfg.llm.temperature = 2 }
  return $cfg
}

function Load-Config([string]$path) {
  $base = Default-Config
  if (-not (Test-Path $path)) { return (Normalize-Config $base) }
  $raw = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
  return (Normalize-Config (Merge-Hash $base (Convert-ObjToHash $raw)))
}

function Save-Config([string]$path, [hashtable]$cfg) {
  $json = (Normalize-Config $cfg) | ConvertTo-Json -Depth 100
  Set-Content -Path $path -Value $json -Encoding UTF8
}

function Ensure-WingetPackage {
  param([string]$name, [string]$id, [string]$cmdCheck)
  $check = Get-Command $cmdCheck -ErrorAction SilentlyContinue
  if ($check) {
    Write-Host "✅ $name bereits installiert" -ForegroundColor Green
    return $true
  }
  
  Write-Host "⚠️  $name nicht gefunden - installiere automatisch via winget..." -ForegroundColor Cyan
  
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) {
    Write-Host "❌ winget nicht gefunden. Bitte $name manuell installieren." -ForegroundColor Red
    return $false
  }
  
  try {
    & winget install --id $id --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) {
      Write-Host "✅ $name erfolgreich installiert. (HINWEIS: Terminal-Neustart evtl. noetig)" -ForegroundColor Green
      return $true
    }
  } catch {}
  Write-Host "❌ $name Installation via winget fehlgeschlagen." -ForegroundColor Red
  return $false
}

function Ensure-Python {
  $bootstrap = $null
  Write-Host "Suche Python 3.12 (empfohlen)..." -ForegroundColor Yellow
  foreach ($c in @("py -3.12", "py -3.11", "py", "python")) {
    try {
      $p = $c.Split(" ")
      $ver = & $p[0] @($p | Select-Object -Skip 1) -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
      if ($LASTEXITCODE -eq 0) { 
        $verNum = [version]$ver
        if ($verNum.Major -eq 3 -and $verNum.Minor -eq 14) {
          Write-Host "⚠️  Python 3.14 gefunden - hat bekannte Kompatibilitätsprobleme!" -ForegroundColor Red
          Write-Host "   Empfehlung: Installiere Python 3.12 von python.org" -ForegroundColor Yellow
          continue
        }
        $bootstrap = $c
        Write-Host "✅ Python $ver gefunden: $c" -ForegroundColor Green
        return $bootstrap
      }
    } catch {}
  }

  if (-not $bootstrap) {
    Write-Host "⚠️  Kein kompatibles Python gefunden - starte automatische Installation von Python 3.12 via winget..." -ForegroundColor Cyan
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
      try {
        & winget install --id Python.Python.3.12 --source winget --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
          Write-Host "✅ Python 3.12 via winget installiert" -ForegroundColor Green
          # Wir muessen den Pfad evtl. aktualisieren oder erneut suchen
          return "python"
        }
      } catch {
        Write-Host "⚠️  winget Installation von Python fehlgeschlagen" -ForegroundColor Yellow
      }
    }
  }

  if (-not $bootstrap) { 
    Write-Host ""
    Write-Host "❌ Kein kompatibles Python gefunden!" -ForegroundColor Red
    Write-Host ""
    Write-Host "EMPFOHLEN: Python 3.12" -ForegroundColor Yellow
    Write-Host "Download: https://www.python.org/downloads/release/python-31210/" -ForegroundColor Cyan
    Write-Host ""
    throw "Python 3.12+ nicht gefunden (Python 3.14 wird nicht empfohlen)."
  }
  return $bootstrap
}

function Ensure-Deps([string]$root) {
  # System-Abhängigkeiten prüfen
  Write-Host "Pruefe System-Abhaengigkeiten..." -ForegroundColor Cyan
  Ensure-WingetPackage "Node.js (LTS)" "OpenJS.NodeJS.LTS" "node"
  Ensure-WingetPackage "FFmpeg" "Gyan.FFmpeg" "ffmpeg"
  Ensure-WingetPackage "Git" "Git.Git" "git"
  Write-Host ""

  $venvPy = Join-Path $root ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPy)) {
    $bootstrap = Ensure-Python
    $p = $bootstrap.Split(" ")
    & $p[0] @($p | Select-Object -Skip 1) -m venv ".venv"
  }
  if (-not (Test-Path $venvPy)) { throw "Konnte .venv nicht erstellen." }
  
  Write-Host "Upgrade pip..." -ForegroundColor Cyan
  & $venvPy -m pip install --no-cache-dir --upgrade pip
  if ($LASTEXITCODE -ne 0) { throw "pip upgrade fehlgeschlagen." }
  
  Write-Host "Installiere requirements..." -ForegroundColor Cyan
  & $venvPy -m pip install --no-cache-dir -r "requirements.txt"
  if ($LASTEXITCODE -ne 0) { throw "requirements Installation fehlgeschlagen." }

  # MCP (Model Context Protocol) – separat absichern, da Paketname variieren kann
  Write-Host "Installiere MCP..." -ForegroundColor Cyan
  & $venvPy -m pip install "mcp>=1.2.0"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  MCP (mcp) nicht gefunden – versuche Fallback-Paket..." -ForegroundColor Yellow
    & $venvPy -m pip install "modelcontextprotocol>=1.2.0"
    if ($LASTEXITCODE -ne 0) {
      Write-Host "⚠️  MCP Installation fehlgeschlagen. MCP-Tools werden deaktiviert." -ForegroundColor Yellow
      Write-Host "   Tipp: Prüfe PyPI-Verfügbarkeit oder installiere manuell in der venv." -ForegroundColor Gray
    }
  } else {
    Write-Host "✅ MCP installiert" -ForegroundColor Green
  }

  # Vektor-Memory: ChromaDB + sentence-transformers sicherstellen
  Write-Host "Installiere ChromaDB..." -ForegroundColor Cyan
  & $venvPy -m pip install chromadb>=0.4.24
  if ($LASTEXITCODE -ne 0) { throw "ChromaDB Installation fehlgeschlagen." }
  
  Write-Host "Installiere sentence-transformers..." -ForegroundColor Cyan
  & $venvPy -m pip install sentence-transformers>=2.6.1
  if ($LASTEXITCODE -ne 0) { throw "sentence-transformers Installation fehlgeschlagen." }

  # Download Whisper model for SST
  Write-Host "Lade Whisper-Modell herunter (ca. 500MB-1GB)..." -ForegroundColor Cyan
  try {
    & $venvPy "scripts\download_whisper.py"
    if ($LASTEXITCODE -ne 0) { 
      Write-Host "⚠️  Whisper-Modell Download fehlgeschlagen." -ForegroundColor Yellow
      Write-Host "   Audio-Transkription wird nicht funktionieren." -ForegroundColor Yellow
      Write-Host "   Manuelle Installation: python scripts\download_whisper.py" -ForegroundColor Gray
    } else {
      Write-Host "✅ Whisper-Modell erfolgreich heruntergeladen." -ForegroundColor Green
    }
  } catch {
    Write-Host "⚠️  Whisper-Modell Download fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   Audio-Transkription wird nicht funktionieren." -ForegroundColor Yellow
  }

  # Playwright entfernt: Web/Browser-Tools sind nicht mehr Teil des Agents.
}

function Cache-SbertModel([string]$root) {
  $venvPy = Join-Path $root ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPy)) {
    Write-Host "⚠️  Cache uebersprungen: .venv fehlt." -ForegroundColor Yellow
    return
  }
  Write-Host "Cache SentenceTransformer Modell (all-MiniLM-L6-v2)..." -ForegroundColor Cyan
  try {
    & $venvPy -c "from sentence_transformers import SentenceTransformer as S; S('all-MiniLM-L6-v2'); print('ok')"
    if ($LASTEXITCODE -ne 0) {
      Write-Host "⚠️  Modell-Cache fehlgeschlagen (evtl. offline). Fallback wird beim Start genutzt." -ForegroundColor Yellow
    } else {
      Write-Host "✅ Modell-Cache abgeschlossen." -ForegroundColor Green
    }
  } catch {
    Write-Host "⚠️  Modell-Cache fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

function Start-Bot([string]$root) {
  $bat = Join-Path $root "start_K.AI Agent.bat"
  if (Test-Path $bat) { Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$bat`"" -WorkingDirectory $root | Out-Null; return }
  $py = Join-Path $root ".venv\Scripts\python.exe"
  if (Test-Path $py) { Start-Process -FilePath $py -ArgumentList "-m app.main" -WorkingDirectory $root | Out-Null; return }
  throw "Start fehlgeschlagen."
}

function Run-Gui([hashtable]$cfg, [string]$configPath, [string]$root) {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  [System.Windows.Forms.Application]::EnableVisualStyles()

  # ---------- Color palette ----------
  $clrNavBg      = [Drawing.Color]::FromArgb(26, 31, 54)
  $clrNavHover   = [Drawing.Color]::FromArgb(37, 45, 74)
  $clrNavActive  = [Drawing.Color]::FromArgb(79, 142, 247)
  $clrContentBg  = [Drawing.Color]::FromArgb(240, 242, 247)
  $clrCardBg     = [Drawing.Color]::White
  $clrCardBorder = [Drawing.Color]::FromArgb(226, 232, 240)
  $clrText       = [Drawing.Color]::FromArgb(26, 31, 54)
  $clrMuted      = [Drawing.Color]::FromArgb(100, 116, 139)
  $clrAccent     = [Drawing.Color]::FromArgb(79, 142, 247)
  $clrSuccess    = [Drawing.Color]::FromArgb(34, 197, 94)
  $clrDanger     = [Drawing.Color]::FromArgb(239, 68, 68)
  $clrInputBg    = [Drawing.Color]::FromArgb(248, 250, 252)

  # ---------- Form ----------
  $f = New-Object Windows.Forms.Form
  $f.Text            = "K.AI Agent Setup & Konfiguration"
  $f.StartPosition   = "CenterScreen"
  $f.ClientSize      = New-Object Drawing.Size(1280, 820)
  $f.FormBorderStyle = "FixedSingle"
  $f.MaximizeBox     = $false
  $f.BackColor       = $clrContentBg
  $f.Font            = New-Object Drawing.Font("Segoe UI", 9)

  # ---------- Header (0,0 1160x56) ----------
  $hdr = New-Object Windows.Forms.Panel
  $hdr.Location  = New-Object Drawing.Point(0, 0)
  $hdr.Size      = New-Object Drawing.Size(1280, 56)
  $hdr.BackColor = $clrNavBg
  $f.Controls.Add($hdr)

  # Roboter-Icon als PictureBox – gezeichnet mit GDI+ Primitiven (kein Emoji/Unicode)
  $hdrIcon = New-Object Windows.Forms.PictureBox
  $hdrIcon.Size     = New-Object Drawing.Size(36, 36)
  $hdrIcon.Location = New-Object Drawing.Point(12, 10)
  $hdrIcon.BackColor = [Drawing.Color]::Transparent
  $bmp = New-Object Drawing.Bitmap(36, 36)
  $g   = [Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $white  = [Drawing.Brushes]::White
  $wPen   = New-Object Drawing.Pen([Drawing.Color]::White, 1.5)
  # Kopf
  $g.DrawRectangle($wPen, 6, 8, 24, 18)
  # Augen
  $g.FillEllipse($white, 10, 13, 5, 5)
  $g.FillEllipse($white, 21, 13, 5, 5)
  # Mund (3 Punkte)
  $g.FillRectangle($white, 11, 22, 3, 2)
  $g.FillRectangle($white, 17, 22, 3, 2)
  $g.FillRectangle($white, 23, 22, 3, 2)
  # Antenne
  $g.DrawLine($wPen, 18, 4, 18, 8)
  $g.FillEllipse($white, 15, 1, 6, 5)
  # Hals
  $g.DrawLine($wPen, 18, 26, 18, 30)
  # Schultern
  $g.DrawLine($wPen, 8, 30, 28, 30)
  $wPen.Dispose()
  $g.Dispose()
  $hdrIcon.Image = $bmp
  $hdr.Controls.Add($hdrIcon)

  $hdrTitle = New-Object Windows.Forms.Label
  $hdrTitle.Text      = "K.AI Agent"
  $hdrTitle.ForeColor = [Drawing.Color]::White
  $hdrTitle.Font      = New-Object Drawing.Font("Segoe UI", 13, [Drawing.FontStyle]::Bold)
  $hdrTitle.AutoSize  = $true
  $hdrTitle.Location  = New-Object Drawing.Point(52, 6)
  $hdr.Controls.Add($hdrTitle)

  $hdrSub = New-Object Windows.Forms.Label
  $hdrSub.Text      = "Setup & Konfiguration"
  $hdrSub.ForeColor = [Drawing.Color]::FromArgb(160, 180, 220)
  $hdrSub.Font      = New-Object Drawing.Font("Segoe UI", 8)
  $hdrSub.AutoSize  = $true
  $hdrSub.Location  = New-Object Drawing.Point(54, 34)
  $hdr.Controls.Add($hdrSub)

  # ---------- Sidebar (0,56 180x704) ----------
  $sidebar = New-Object Windows.Forms.Panel
  $sidebar.Location  = New-Object Drawing.Point(0, 56)
  $sidebar.Size      = New-Object Drawing.Size(180, 704)
  $sidebar.BackColor = $clrNavBg
  $f.Controls.Add($sidebar)

  # ---------- Content area (180,56 1100x704) ----------
  $content = New-Object Windows.Forms.Panel
  $content.Location  = New-Object Drawing.Point(180, 56)
  $content.Size      = New-Object Drawing.Size(1100, 704)
  $content.BackColor = $clrContentBg
  $f.Controls.Add($content)

  # ---------- Footer (0,760 1280x60) ----------
  $footer = New-Object Windows.Forms.Panel
  $footer.Location  = New-Object Drawing.Point(0, 760)
  $footer.Size      = New-Object Drawing.Size(1280, 60)
  $footer.BackColor = [Drawing.Color]::White
  $f.Controls.Add($footer)

  $footerLine = New-Object Windows.Forms.Panel
  $footerLine.Location  = New-Object Drawing.Point(0, 0)
  $footerLine.Size      = New-Object Drawing.Size(1280, 1)
  $footerLine.BackColor = $clrCardBorder
  $footer.Controls.Add($footerLine)

  $status = New-Object Windows.Forms.Label
  $status.Text      = "Bereit."
  $status.Location  = New-Object Drawing.Point(14, 18)
  $status.Size      = New-Object Drawing.Size(820, 24)
  $status.ForeColor = $clrMuted
  $footer.Controls.Add($status)

  $btnClose = New-Object Windows.Forms.Button
  $btnClose.Text     = "Schliessen"
  $btnClose.Location = New-Object Drawing.Point(940, 12)
  $btnClose.Size     = New-Object Drawing.Size(100, 36)
  $btnClose.FlatStyle = "Flat"
  $btnClose.BackColor = [Drawing.Color]::FromArgb(235, 239, 245)
  $btnClose.ForeColor = $clrText
  $btnClose.FlatAppearance.BorderColor = $clrCardBorder
  $footer.Controls.Add($btnClose)

  $btnSave = New-Object Windows.Forms.Button
  $btnSave.Text      = "Speichern"
  $btnSave.Location  = New-Object Drawing.Point(1050, 12)
  $btnSave.Size      = New-Object Drawing.Size(100, 36)
  $btnSave.FlatStyle = "Flat"
  $btnSave.BackColor = $clrAccent
  $btnSave.ForeColor = [Drawing.Color]::White
  $btnSave.FlatAppearance.BorderSize = 0
  $footer.Controls.Add($btnSave)

  $btnSaveStart = New-Object Windows.Forms.Button
  $btnSaveStart.Text      = "Speichern + Start"
  $btnSaveStart.Location  = New-Object Drawing.Point(1160, 12)
  $btnSaveStart.Size      = New-Object Drawing.Size(110, 36)
  $btnSaveStart.FlatStyle = "Flat"
  $btnSaveStart.BackColor = $clrSuccess
  $btnSaveStart.ForeColor = [Drawing.Color]::White
  $btnSaveStart.FlatAppearance.BorderSize = 0
  $footer.Controls.Add($btnSaveStart)

  # ---------- Helper scriptblocks ----------
  $mkCard = {
    param($title, $x, $y, $w, $h, $parent)
    $card = New-Object Windows.Forms.Panel
    $card.Location    = New-Object Drawing.Point($x, $y)
    $card.Size        = New-Object Drawing.Size($w, $h)
    $card.BackColor   = $clrCardBg
    $card.BorderStyle = "FixedSingle"
    $parent.Controls.Add($card)
    $tl = New-Object Windows.Forms.Label
    $tl.Text      = $title
    $tl.Font      = New-Object Drawing.Font("Segoe UI Semibold", 9, [Drawing.FontStyle]::Bold)
    $tl.ForeColor = $clrText
    $tl.Location  = New-Object Drawing.Point(12, 10)
    $tl.AutoSize  = $true
    $card.Controls.Add($tl)
    $al = New-Object Windows.Forms.Panel
    $al.Location  = New-Object Drawing.Point(12, 29)
    $al.Size      = New-Object Drawing.Size(($w - 26), 2)
    $al.BackColor = $clrAccent
    $card.Controls.Add($al)
    return $card
  }

  $mkLbl = {
    param($txt, $x, $y, $parent)
    $l = New-Object Windows.Forms.Label
    $l.Text      = $txt
    $l.ForeColor = $clrText
    $l.AutoSize  = $true
    $l.Location  = New-Object Drawing.Point($x, $y)
    $parent.Controls.Add($l)
    return $l
  }

  $mkTxt = {
    param($x, $y, $w, $parent)
    $t = New-Object Windows.Forms.TextBox
    $t.Location    = New-Object Drawing.Point($x, $y)
    $t.Size        = New-Object Drawing.Size($w, 24)
    $t.BackColor   = $clrInputBg
    $t.BorderStyle = "FixedSingle"
    $parent.Controls.Add($t)
    return $t
  }

  $mkCbo = {
    param($x, $y, $w, $parent, $items)
    $c = New-Object Windows.Forms.ComboBox
    $c.Location      = New-Object Drawing.Point($x, $y)
    $c.Size          = New-Object Drawing.Size($w, 26)
    $c.DropDownStyle = "DropDownList"
    $c.FlatStyle     = "Flat"
    if ($null -ne $items) { $c.Items.AddRange($items) }
    $parent.Controls.Add($c)
    return $c
  }

  $mkChk = {
    param($txt, $x, $y, $parent)
    $cb = New-Object Windows.Forms.CheckBox
    $cb.Text      = $txt
    $cb.Location  = New-Object Drawing.Point($x, $y)
    $cb.AutoSize  = $true
    $cb.FlatStyle = "Flat"
    $cb.ForeColor = $clrText
    $parent.Controls.Add($cb)
    return $cb
  }

  $mkNum = {
    param($x, $y, $w, $min, $max, $dec, $inc, $parent)
    $n = New-Object Windows.Forms.NumericUpDown
    $n.Location      = New-Object Drawing.Point($x, $y)
    $n.Size          = New-Object Drawing.Size($w, 24)
    $n.Minimum       = [decimal]$min
    $n.Maximum       = [decimal]$max
    $n.DecimalPlaces = [int]$dec
    $n.Increment     = [decimal]$inc
    $parent.Controls.Add($n)
    return $n
  }

  # ================================================
  # PAGE: Allgemein
  # ================================================
  $pageAllgemein = New-Object Windows.Forms.Panel
  $pageAllgemein.Location  = New-Object Drawing.Point(0, 0)
  $pageAllgemein.Size      = New-Object Drawing.Size(1100, 704)
  $pageAllgemein.BackColor = $clrContentBg
  $content.Controls.Add($pageAllgemein)

  # Card "Sicherheit" (20,20) 460x160
  $cSec = & $mkCard "Sicherheit" 20 20 460 160 $pageAllgemein
  & $mkLbl "Rolle" 12 46 $cSec | Out-Null
  $role = & $mkCbo 120 42 200 $cSec @("user","admin")
  & $mkLbl "Execution Mode" 12 80 $cSec | Out-Null
  $mode = & $mkCbo 120 76 200 $cSec @("unrestricted","deny")
  $deleteTrash = & $mkChk "delete_to_trash" 12 114 $cSec
  $fullAccess  = & $mkChk "full_access"    230 114 $cSec

  # Card "Pfade & Speicher" (500,20) 460x160
  $cPath = & $mkCard "Pfade & Speicher" 500 20 460 160 $pageAllgemein
  & $mkLbl "Workspace" 12 46 $cPath | Out-Null
  $workspace = & $mkTxt 105 42 330 $cPath
  & $mkLbl "Memory DB" 12 80 $cPath | Out-Null
  $memoryDb = & $mkTxt 105 76 330 $cPath

  # Card "Session Memory" (20,200) 460x120
  $cSess = & $mkCard "Session Memory" 20 200 460 120 $pageAllgemein
  $sessEnabled = & $mkChk "session_memory_enabled" 12 46 $cSess
  $cacheSbert  = & $mkChk "Embeddings-Modell laden (Memory-Suche)" 12 76 $cSess
  & $mkLbl "Laedt 'all-MiniLM-L6-v2' einmalig in den lokalen Cache fuer semantische Suche." 30 98 $cSess | Out-Null

  # Card "TTS / Audio" (500,200) 460x120
  $cTts = & $mkCard "TTS / Audio" 500 200 460 120 $pageAllgemein
  $ttsEnabled = & $mkChk "TTS aktiviert" 12 46 $cTts
  & $mkLbl "TTS Stimme" 12 80 $cTts | Out-Null
  $ttsVoice = & $mkTxt 110 76 320 $cTts

  # Card "Logging" (20,340) 920x110
  $cLog = & $mkCard "Logging" 20 340 920 110 $pageAllgemein
  $logEnabled = & $mkChk "Logging aktiviert" 12 46 $cLog
  $logVerbose = & $mkChk "Verbose"           200 46 $cLog
  & $mkLbl "Audit Log Pfad" 12 80 $cLog | Out-Null
  $logPath = & $mkTxt 120 76 776 $cLog

  # ================================================
  # PAGE: LLM
  # ================================================
  $pageLlm = New-Object Windows.Forms.Panel
  $pageLlm.Location  = New-Object Drawing.Point(0, 0)
  $pageLlm.Size      = New-Object Drawing.Size(1100, 704)
  $pageLlm.BackColor = $clrContentBg
  $pageLlm.Visible   = $false
  $content.Controls.Add($pageLlm)

  # Card "Aktive Konfiguration" (20,20) 940x110
  $cLlm = & $mkCard "Aktive Konfiguration" 20 20 940 110 $pageLlm
  & $mkLbl "Aktiver Provider" 12 46 $cLlm | Out-Null
  $activeProvider = & $mkCbo 130 42 200 $cLlm $null
  & $mkLbl "Aktives Modell" 345 46 $cLlm | Out-Null
  $activeModel = & $mkCbo 450 42 290 $cLlm $null
  & $mkLbl "Temperatur" 756 46 $cLlm | Out-Null
  $temp = & $mkNum 840 42 80 0 2 2 0.05 $cLlm

  # Card "Provider-Konfiguration" (20,150) 940x510
  $cProv = & $mkCard "Provider-Konfiguration" 20 150 940 510 $pageLlm
  $grid = New-Object Windows.Forms.DataGridView
  $grid.Location                   = New-Object Drawing.Point(12, 42)
  $grid.Size                       = New-Object Drawing.Size(914, 454)
  $grid.AutoSizeColumnsMode        = "Fill"
  $grid.RowHeadersVisible          = $false
  $grid.AllowUserToAddRows         = $true
  $grid.AllowUserToDeleteRows      = $true
  $grid.BackgroundColor            = [Drawing.Color]::White
  $grid.BorderStyle                = "FixedSingle"
  $grid.GridColor                  = [Drawing.Color]::FromArgb(220, 228, 238)
  $grid.EnableHeadersVisualStyles  = $false
  $grid.ColumnHeadersDefaultCellStyle.BackColor = [Drawing.Color]::FromArgb(234, 241, 250)
  $grid.ColumnHeadersDefaultCellStyle.Font      = New-Object Drawing.Font("Segoe UI Semibold", 9)
  $grid.AlternatingRowsDefaultCellStyle.BackColor = [Drawing.Color]::FromArgb(249, 252, 255)
  [void]$grid.Columns.Add("id","id")
  [void]$grid.Columns.Add("type","type")
  [void]$grid.Columns.Add("base_url","base_url")
  [void]$grid.Columns.Add("models_csv","models_csv")
  [void]$grid.Columns.Add("api_key","api_key")
  $cProv.Controls.Add($grid)

  # ================================================
  # PAGE: Messenger
  # ================================================
  $pageMessenger = New-Object Windows.Forms.Panel
  $pageMessenger.Location  = New-Object Drawing.Point(0, 0)
  $pageMessenger.Size      = New-Object Drawing.Size(1100, 704)
  $pageMessenger.BackColor = $clrContentBg
  $pageMessenger.Visible   = $false
  $content.Controls.Add($pageMessenger)

  # Card "Telegram" (20,20) 940x170
  $cTg = & $mkCard "Telegram" 20 20 940 170 $pageMessenger
  & $mkLbl "Telegram Token" 12 46 $cTg | Out-Null
  $tgToken = & $mkTxt 130 42 786 $cTg
  $tgToken.UseSystemPasswordChar = $true
  $tgEnabled   = & $mkChk "Telegram aktiviert"  12 80 $cTg
  $tgPrefixReq = & $mkChk "Prefix erforderlich" 200 80 $cTg
  & $mkLbl "Telegram Prefix" 12 116 $cTg | Out-Null
  $tgPrefix = & $mkTxt 130 112 260 $cTg

  # Card "Discord" (20,210) 940x200
  $cDc = & $mkCard "Discord" 20 210 940 200 $pageMessenger
  & $mkLbl "Discord Token" 12 46 $cDc | Out-Null
  $dcToken = & $mkTxt 130 42 786 $cDc
  $dcToken.UseSystemPasswordChar = $true
  $dcEnabled   = & $mkChk "Discord aktiviert"   12 80 $cDc
  $dcPrefixReq = & $mkChk "Prefix erforderlich" 195 80 $cDc
  $dcGateway   = & $mkChk "Gateway aktiv"       380 80 $cDc
  & $mkLbl "Discord Prefix" 12 116 $cDc | Out-Null
  $dcPrefix  = & $mkTxt 130 112 250 $cDc
  & $mkLbl "Discord Channel ID" 400 120 $cDc | Out-Null
  $dcChannel = & $mkTxt 530 116 386 $cDc

  # ================================================
  # SIDEBAR NAVIGATION
  # ================================================
  $script:navButtons = @()
  $script:allPages   = @($pageAllgemein, $pageLlm, $pageMessenger)

  $switchPage = {
    param($targetPage, $activeNavBtn)
    foreach ($pg in $script:allPages) { $pg.Visible = $false }
    $targetPage.Visible = $true
    foreach ($nb in $script:navButtons) {
      $nb.BackColor = $clrNavBg
      $nb.ForeColor = [Drawing.Color]::FromArgb(180, 200, 230)
    }
    $activeNavBtn.BackColor = $clrNavActive
    $activeNavBtn.ForeColor = [Drawing.Color]::White
  }

  $navBtn1 = New-Object Windows.Forms.Button
  $navBtn1.Text      = "Allgemein"
  $navBtn1.Location  = New-Object Drawing.Point(0, 20)
  $navBtn1.Size      = New-Object Drawing.Size(180, 48)
  $navBtn1.FlatStyle = "Flat"
  $navBtn1.FlatAppearance.BorderSize = 0
  $navBtn1.BackColor = $clrNavActive
  $navBtn1.ForeColor = [Drawing.Color]::White
  $navBtn1.Font      = New-Object Drawing.Font("Segoe UI", 9)
  $navBtn1.TextAlign = "MiddleLeft"
  $navBtn1.Padding   = New-Object Windows.Forms.Padding(16, 0, 0, 0)
  $navBtn1.Tag       = $pageAllgemein
  $sidebar.Controls.Add($navBtn1)
  $script:navButtons += $navBtn1

  $navBtn2 = New-Object Windows.Forms.Button
  $navBtn2.Text      = "LLM"
  $navBtn2.Location  = New-Object Drawing.Point(0, 68)
  $navBtn2.Size      = New-Object Drawing.Size(180, 48)
  $navBtn2.FlatStyle = "Flat"
  $navBtn2.FlatAppearance.BorderSize = 0
  $navBtn2.BackColor = $clrNavBg
  $navBtn2.ForeColor = [Drawing.Color]::FromArgb(180, 200, 230)
  $navBtn2.Font      = New-Object Drawing.Font("Segoe UI", 9)
  $navBtn2.TextAlign = "MiddleLeft"
  $navBtn2.Padding   = New-Object Windows.Forms.Padding(16, 0, 0, 0)
  $navBtn2.Tag       = $pageLlm
  $sidebar.Controls.Add($navBtn2)
  $script:navButtons += $navBtn2

  $navBtn3 = New-Object Windows.Forms.Button
  $navBtn3.Text      = "Messenger"
  $navBtn3.Location  = New-Object Drawing.Point(0, 116)
  $navBtn3.Size      = New-Object Drawing.Size(180, 48)
  $navBtn3.FlatStyle = "Flat"
  $navBtn3.FlatAppearance.BorderSize = 0
  $navBtn3.BackColor = $clrNavBg
  $navBtn3.ForeColor = [Drawing.Color]::FromArgb(180, 200, 230)
  $navBtn3.Font      = New-Object Drawing.Font("Segoe UI", 9)
  $navBtn3.TextAlign = "MiddleLeft"
  $navBtn3.Padding   = New-Object Windows.Forms.Padding(16, 0, 0, 0)
  $navBtn3.Tag       = $pageMessenger
  $sidebar.Controls.Add($navBtn3)
  $script:navButtons += $navBtn3

  $navBtn1.Add_Click({ & $switchPage $pageAllgemein $navBtn1 })
  $navBtn2.Add_Click({ & $switchPage $pageLlm       $navBtn2 })
  $navBtn3.Add_Click({ & $switchPage $pageMessenger $navBtn3 })

  $navBtn1.Add_MouseEnter({ if ($navBtn1.BackColor.ToArgb() -ne $clrNavActive.ToArgb()) { $navBtn1.BackColor = $clrNavHover } })
  $navBtn1.Add_MouseLeave({ if ($navBtn1.BackColor.ToArgb() -ne $clrNavActive.ToArgb()) { $navBtn1.BackColor = $clrNavBg } })
  $navBtn2.Add_MouseEnter({ if ($navBtn2.BackColor.ToArgb() -ne $clrNavActive.ToArgb()) { $navBtn2.BackColor = $clrNavHover } })
  $navBtn2.Add_MouseLeave({ if ($navBtn2.BackColor.ToArgb() -ne $clrNavActive.ToArgb()) { $navBtn2.BackColor = $clrNavBg } })
  $navBtn3.Add_MouseEnter({ if ($navBtn3.BackColor.ToArgb() -ne $clrNavActive.ToArgb()) { $navBtn3.BackColor = $clrNavHover } })
  $navBtn3.Add_MouseLeave({ if ($navBtn3.BackColor.ToArgb() -ne $clrNavActive.ToArgb()) { $navBtn3.BackColor = $clrNavBg } })

  # ================================================
  # refreshModels
  # ================================================
  $refreshModels = {
    $activeModel.Items.Clear()
    $selectedProviderId = [string]$activeProvider.SelectedItem
    if (-not $selectedProviderId) { return }
    $providerHasKey = $false
    foreach ($r in $grid.Rows) {
      if (-not $r.IsNewRow -and [string](Nz $r.Cells["id"].Value "") -eq $selectedProviderId) {
        $apiKey = [string](Nz $r.Cells["api_key"].Value "")
        $providerHasKey = -not [string]::IsNullOrWhiteSpace($apiKey)
        if ($providerHasKey) {
          foreach ($m in (Split-Models ([string](Nz $r.Cells["models_csv"].Value "")))) { [void]$activeModel.Items.Add($m) }
        }
        break
      }
    }
    if (-not $providerHasKey) {
      $status.Text      = "Hinweis: Der ausgewaehlte Provider hat keinen API-Key. Aktives Modell kann erst nach Speichern mit API-Key gesetzt werden."
      $status.ForeColor = $clrMuted
      return
    }
    if ($activeModel.Items.Count -gt 0 -and $activeModel.SelectedIndex -lt 0) { $activeModel.SelectedIndex = 0 }
  }
  $activeProvider.add_SelectedIndexChanged({ & $refreshModels })
  $grid.add_CellValueChanged({ & $refreshModels })

  # Provider-Dropdown nur mit Einträgen befüllen die einen API-Key haben
  $refreshProviderDropdown = {
    $current = [string]$activeProvider.SelectedItem
    $activeProvider.Items.Clear()
    foreach ($r in $grid.Rows) {
      if ($r.IsNewRow) { continue }
      $providerId = [string]$r.Cells["id"].Value
      $apiKey = [string]$r.Cells["api_key"].Value
      if (-not [string]::IsNullOrWhiteSpace($providerId) -and -not [string]::IsNullOrWhiteSpace($apiKey)) {
        [void]$activeProvider.Items.Add($providerId)
      }
    }
    # Auswahl beibehalten wenn noch vorhanden
    if ($current -and $activeProvider.Items.Contains($current)) {
      $activeProvider.SelectedItem = $current
    } elseif ($activeProvider.Items.Count -gt 0) {
      $activeProvider.SelectedIndex = 0
    }
    & $refreshModels
  }
  $grid.add_CellEndEdit({ & $refreshProviderDropdown })
  $grid.add_RowsRemoved({ & $refreshProviderDropdown })

  # ================================================
  # LOAD DATA
  # ================================================
  foreach ($providerId in @($cfg.providers.Keys | Sort-Object)) {
    $p = $cfg.providers[$providerId]
    [void]$grid.Rows.Add([string]$providerId, [string]$p.type, [string]$p.base_url, (@($p.models) -join ", "), [string]$p.api_key)
    # Nur in Dropdown wenn API-Key vorhanden
    if (-not [string]::IsNullOrWhiteSpace([string]$p.api_key)) {
      [void]$activeProvider.Items.Add([string]$providerId)
    }
  }
  $activeProvider.SelectedItem = [string]$cfg.llm.active_provider_id
  if ($activeProvider.SelectedIndex -lt 0 -and $activeProvider.Items.Count -gt 0) { $activeProvider.SelectedIndex = 0 }
  & $refreshModels
  if ([string]$cfg.llm.active_model) { $idx = $activeModel.Items.IndexOf([string]$cfg.llm.active_model); if ($idx -ge 0) { $activeModel.SelectedIndex = $idx } }

  $role.SelectedItem = [string]$cfg.security.active_role
  if ($role.SelectedIndex -lt 0) { $role.SelectedItem = "user" }
  $mode.SelectedItem = [string]$cfg.security.execution_mode
  if ($mode.SelectedIndex -lt 0) { $mode.SelectedItem = "unrestricted" }

  $workspace.Text      = [string]$cfg.workspace
  $memoryDb.Text       = [string]$cfg.memory.db_path
  $fullAccess.Checked  = [bool]$cfg.filesystem.full_access
  $deleteTrash.Checked = [bool]($cfg.filesystem.delete_to_trash -ne $false)
  $sessEnabled.Checked = [bool]$cfg.messenger.session_memory_enabled
  $cacheSbert.Checked  = [bool](Nz $cfg.memory.cache_sbert_model $true)
  $temp.Value          = [decimal]([double]$cfg.llm.temperature)

  $tgEnabled.Checked   = [bool]$cfg.messenger.telegram.enabled
  $tgToken.Text        = [string]$cfg.messenger.telegram.token
  $tgPrefixReq.Checked = [bool]$cfg.messenger.telegram.require_prefix
  $tgPrefix.Text       = [string]$cfg.messenger.telegram.command_prefix

  $dcEnabled.Checked   = [bool]$cfg.messenger.discord.enabled
  $dcToken.Text        = [string]$cfg.messenger.discord.token
  $dcChannel.Text      = [string]$cfg.messenger.discord.channel_id
  $dcPrefixReq.Checked = [bool]$cfg.messenger.discord.require_prefix
  $dcPrefix.Text       = [string]$cfg.messenger.discord.command_prefix
  $dcGateway.Checked   = [bool]$cfg.messenger.discord.gateway_enabled


  # TTS
  $tts = if ($cfg.ContainsKey("tts")) { Convert-ObjToHash $cfg.tts } else { @{enabled=$false; voice="de-DE-ConradNeural"} }
  $ttsEnabled.Checked = [bool]$tts.enabled
  $ttsVoice.Text      = [string](Nz $tts.voice "de-DE-ConradNeural")

  # Logging
  $logCfg = if ($cfg.ContainsKey("logging")) { Convert-ObjToHash $cfg.logging } else { @{enabled=$true; verbose=$true; audit_log_path="data\logs\audit.log"} }
  $logEnabled.Checked = [bool](Nz $logCfg.enabled $true)
  $logVerbose.Checked = [bool](Nz $logCfg.verbose $true)
  $logPath.Text       = [string](Nz $logCfg.audit_log_path "data\logs\audit.log")

  # ================================================
  # SAVE LOGIC
  # ================================================
  $save = {
    param([bool]$startAfter)
    try {
      $next = Load-Config $configPath
      $next.security.active_role      = [string]$role.SelectedItem
      $next.security.execution_mode   = [string]$mode.SelectedItem
      $next.workspace                  = Normalize-WinPath ($workspace.Text.Trim())
      $next.memory.db_path             = Normalize-WinPath ($memoryDb.Text.Trim())
      $next.memory.cache_sbert_model   = $cacheSbert.Checked
      $next.filesystem.full_access     = $fullAccess.Checked
      $next.filesystem.delete_to_trash = $deleteTrash.Checked
      $next.llm.temperature            = [double]$temp.Value
      $prov = @{}
      foreach ($r in $grid.Rows) {
        if ($r.IsNewRow) { continue }
        $id = [string](Nz $r.Cells["id"].Value "")
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        $models = @(Split-Models ([string](Nz $r.Cells["models_csv"].Value "")))
        if (@($models).Count -eq 0) { throw "Provider '$id' ohne gueltige Modelle." }
        $prov[$id.Trim()] = @{
          type          = [string](Nz $r.Cells["type"].Value "openai_compatible")
          base_url      = [string](Nz $r.Cells["base_url"].Value "")
          api_key       = [string](Nz $r.Cells["api_key"].Value "")
          models        = $models
          default_model = [string]$models[0]
        }
      }
      if ($prov.Count -eq 0) { throw "Mindestens ein Provider erforderlich." }
      $next.providers = $prov
      $selectedProvider = [string]$activeProvider.SelectedItem
      if ([string]::IsNullOrWhiteSpace($selectedProvider) -or -not $next.providers.ContainsKey($selectedProvider)) {
        throw "Aktiver Provider ist ungueltig."
      }
      $selectedProviderKey = [string](Nz $next.providers[$selectedProvider].api_key "")
      if ([string]::IsNullOrWhiteSpace($selectedProviderKey)) {
        throw "Aktiver Provider darf nur gesetzt werden, wenn ein API-Key hinterlegt ist."
      }
      $selectedModel = [string]$activeModel.SelectedItem
      if ([string]::IsNullOrWhiteSpace($selectedModel)) {
        throw "Aktives Modell fehlt (Provider ohne API-Key oder Modellauswahl leer)."
      }
      if (-not (@($next.providers[$selectedProvider].models) -contains $selectedModel)) {
        throw "Aktives Modell ist fuer den ausgewaehlten Provider nicht in models_csv enthalten."
      }
      $next.llm.active_provider_id = $selectedProvider
      $next.llm.active_model        = $selectedModel
      $next.messenger.telegram.enabled        = $tgEnabled.Checked
      $next.messenger.telegram.token          = $tgToken.Text.Trim()
      $next.messenger.telegram.require_prefix = $tgPrefixReq.Checked
      $next.messenger.telegram.command_prefix = $tgPrefix.Text.Trim()
      $next.messenger.discord.enabled         = $dcEnabled.Checked
      $next.messenger.discord.token           = $dcToken.Text.Trim()
      $next.messenger.discord.channel_id      = $dcChannel.Text.Trim()
      $next.messenger.discord.require_prefix  = $dcPrefixReq.Checked
      $next.messenger.discord.command_prefix  = $dcPrefix.Text.Trim()
      $next.messenger.discord.gateway_enabled = $dcGateway.Checked
      $next.messenger.session_memory_enabled  = $sessEnabled.Checked
      # TTS
      if (-not ($next.ContainsKey("tts"))) { $next.tts = @{} }
      $next.tts.enabled = $ttsEnabled.Checked
      $next.tts.voice   = $ttsVoice.Text.Trim()
      # Logging
      if (-not ($next.ContainsKey("logging"))) { $next.logging = @{} }
      $next.logging.enabled        = $logEnabled.Checked
      $next.logging.verbose        = $logVerbose.Checked
      $next.logging.audit_log_path = Normalize-WinPath ($logPath.Text.Trim())
      Save-Config $configPath $next
      if (-not $ConfigureOnly -and $cacheSbert.Checked) {
        Cache-SbertModel $root
      }
      if ($startAfter -and -not $ConfigureOnly) {
        $status.Text      = "🚀 Starte K.AI Agent..."
        $status.ForeColor = $clrAccent
        [Windows.Forms.Application]::DoEvents()
        Start-Bot $root
        $f.Close()
      } else {
        $status.Text      = "✅ Gespeichert."
        $status.ForeColor = $clrSuccess
      }
    } catch {
      [Windows.Forms.MessageBox]::Show($_.Exception.Message, "Fehler", "OK", "Error") | Out-Null
      $status.Text      = "❌ $($_.Exception.Message)"
      $status.ForeColor = $clrDanger
    }
  }
  $btnSave.Add_Click({ & $save $false })
  $btnSaveStart.Add_Click({ & $save $true })
  $btnClose.Add_Click({ $f.Close() })
  [void]$f.ShowDialog()
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$configPath = Join-Path $root "config.json"
$cfg = Load-Config $configPath
Save-Config $configPath $cfg

# PowerShell 7 Installation (optional aber empfohlen)
if (-not $SkipPowerShell7 -and -not $ConfigureOnly) {
  Ensure-PowerShell7
}

if ($NoGui) {
  if (-not $SkipDeps -and -not $ConfigureOnly) { Ensure-Deps $root }
  if (-not $ConfigureOnly -and -not $SkipSbertCache) { Cache-SbertModel $root }
  exit 0
}
if (-not $SkipDeps -and -not $ConfigureOnly) { Ensure-Deps $root }
Run-Gui $cfg $configPath $root
Stop-Transcript
exit 0
