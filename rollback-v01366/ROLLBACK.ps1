$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'HCA Produktionsmanager - Notfall-Rollback auf v0.13.66'

$rollbackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadRoot = Join-Path $rollbackRoot 'payload'
$checksumFile = Join-Path $rollbackRoot 'SHA256SUMS_ROLLBACK.txt'
$stateRoot = Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager\rollback'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $stateRoot ('backup-' + $timestamp)
$logFile = Join-Path $stateRoot ('rollback-' + $timestamp + '.log')
$candidates = New-Object System.Collections.Generic.List[string]
$newFiles = New-Object System.Collections.Generic.List[string]
$backupReady = $false
$cacheMoved = $false
$installRoot = $null

New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null

function Write-RollbackLog([string] $Message, [ConsoleColor] $Color = [ConsoleColor]::Gray) {
    Add-Content -LiteralPath $logFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Message) -Encoding UTF8
    Write-Host $Message -ForegroundColor $Color
}

function Get-RelativePath([string] $BasePath, [string] $FullPath) {
    $base = [IO.Path]::GetFullPath($BasePath)
    if (-not $base.EndsWith([IO.Path]::DirectorySeparatorChar)) { $base += [IO.Path]::DirectorySeparatorChar }
    $full = [IO.Path]::GetFullPath($FullPath)
    if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Datei liegt ausserhalb des Rollback-Pakets: $FullPath"
    }
    return $full.Substring($base.Length)
}

function Add-Candidate([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    try {
        $value = [Environment]::ExpandEnvironmentVariables($Path.Trim().Trim('"'))
        if ([IO.Path]::GetFileName($value) -ieq 'HCA_Produktionsmanager.exe') { $value = Split-Path -Parent $value }
        if ([string]::IsNullOrWhiteSpace($value)) { return }
        $full = [IO.Path]::GetFullPath($value)
        if (-not $candidates.Contains($full)) { $candidates.Add($full) }
    } catch { }
}

function Get-ValidCandidate {
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'HCA_Produktionsmanager.exe') -PathType Leaf) { return $candidate }
    }
    return $null
}

function Find-HcaInstall {
    Get-Process -Name 'HCA_Produktionsmanager' -ErrorAction SilentlyContinue | ForEach-Object {
        try { Add-Candidate $_.MainModule.FileName } catch { }
    }
    try {
        Get-CimInstance Win32_Process -Filter "Name='HCA_Produktionsmanager.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
            Add-Candidate $_.ExecutablePath
        }
    } catch { }

    @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    ) | ForEach-Object {
        if (-not (Test-Path -LiteralPath $_)) { return }
        Get-ChildItem -LiteralPath $_ -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $entry = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction Stop
                if ($entry.DisplayName -like '*HCA*Produktionsmanager*' -or $_.PSChildName -eq 'HCA Produktionsmanager') {
                    Add-Candidate $entry.InstallLocation
                    Add-Candidate $entry.DisplayIcon
                }
            } catch { }
        }
    }

    @(
        (Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager\repair\reparatur-*.log'),
        'C:\Users\*\AppData\Local\HCA Produktionsmanager\repair\reparatur-*.log'
    ) | ForEach-Object {
        Get-ChildItem -Path $_ -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | ForEach-Object {
            try {
                Get-Content -LiteralPath $_.FullName -ErrorAction Stop | ForEach-Object {
                    if ($_ -match 'Installation gefunden:\s*(.+)$') { Add-Candidate $matches[1] }
                }
            } catch { }
        }
    }

    Add-Candidate 'C:\Users\WK - Dennis Haesen\AppData\Local\Programs\HCA Produktionsmanager'
    Add-Candidate (Join-Path $env:LOCALAPPDATA 'Programs\HCA Produktionsmanager')
    Add-Candidate (Join-Path $env:LOCALAPPDATA 'Programs\HCA-Produktionsmanager')
    Add-Candidate (Join-Path $env:ProgramFiles 'HCA Produktionsmanager')
    if (${env:ProgramFiles(x86)}) { Add-Candidate (Join-Path ${env:ProgramFiles(x86)} 'HCA Produktionsmanager') }
    @(
        'C:\Users\*\AppData\Local\Programs\HCA Produktionsmanager',
        'C:\Users\*\AppData\Local\Programs\HCA-Produktionsmanager'
    ) | ForEach-Object {
        Get-Item -Path $_ -ErrorAction SilentlyContinue | ForEach-Object { Add-Candidate $_.FullName }
    }

    try {
        $shell = New-Object -ComObject WScript.Shell
        @(
            [Environment]::GetFolderPath('Desktop'),
            [Environment]::GetFolderPath('CommonDesktopDirectory'),
            [Environment]::GetFolderPath('Programs'),
            [Environment]::GetFolderPath('CommonPrograms')
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique | ForEach-Object {
            Get-ChildItem -LiteralPath $_ -Filter '*.lnk' -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                try {
                    $shortcut = $shell.CreateShortcut($_.FullName)
                    if ([IO.Path]::GetFileName($shortcut.TargetPath) -ieq 'HCA_Produktionsmanager.exe') { Add-Candidate $shortcut.TargetPath }
                } catch { }
            }
        }
    } catch { }

    return Get-ValidCandidate
}

function Select-HcaInstall {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Ordner auswaehlen, in dem HCA_Produktionsmanager.exe liegt.'
        $dialog.ShowNewFolderButton = $false
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
            Add-Candidate $dialog.SelectedPath
            return Get-ValidCandidate
        }
    } catch { }
    return $null
}

function Restore-Backup {
    if (-not $installRoot -or -not $backupReady) { return }
    Write-RollbackLog 'Fehler erkannt. Der vorherige Dateistand wird wiederhergestellt ...' Yellow
    foreach ($relative in $newFiles) {
        $target = Join-Path $installRoot $relative
        if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue }
    }
    Get-ChildItem -LiteralPath (Join-Path $backupRoot 'files') -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $relative = Get-RelativePath (Join-Path $backupRoot 'files') $_.FullName
        $target = Join-Path $installRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
    $cachePath = Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager\WebView2'
    $savedCache = Join-Path $backupRoot 'WebView2-cache'
    if ($cacheMoved -and (Test-Path -LiteralPath $savedCache) -and -not (Test-Path -LiteralPath $cachePath)) {
        Move-Item -LiteralPath $savedCache -Destination $cachePath
    }
    Write-RollbackLog 'Vorheriger Dateistand wurde wiederhergestellt.' Yellow
}

try {
    Write-RollbackLog 'HCA Notfall-Rollback auf v0.13.66' White
    Write-RollbackLog 'Rollback-Paket wird vollstaendig geprueft ...' Cyan
    if (-not (Test-Path -LiteralPath $checksumFile -PathType Leaf)) { throw 'SHA256SUMS_ROLLBACK.txt fehlt.' }

    $checked = 0
    Get-Content -LiteralPath $checksumFile | ForEach-Object {
        if ($_ -match '^([0-9a-fA-F]{64})\s+\*?(.+)$') {
            $expected = $matches[1].ToLowerInvariant()
            $relative = $matches[2] -replace '/', '\'
            $source = Join-Path $rollbackRoot $relative
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Rollback-Datei fehlt: $relative" }
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant() -ne $expected) {
                throw "Pruefsumme falsch: $relative"
            }
            $checked++
        }
    }
    $payloadFiles = Get-ChildItem -LiteralPath $payloadRoot -Recurse -File
    if ($checked -ne $payloadFiles.Count) { throw "Pruefsummenliste unvollstaendig: $checked von $($payloadFiles.Count) Dateien." }
    Write-RollbackLog "$checked Dateien erfolgreich geprueft." Green

    $installRoot = Find-HcaInstall
    if (-not $installRoot) {
        Write-RollbackLog 'Installation nicht automatisch gefunden. Ordnerauswahl wird geoeffnet ...' Yellow
        $installRoot = Select-HcaInstall
    }
    if (-not $installRoot) { throw 'HCA_Produktionsmanager.exe wurde nicht gefunden. Es wurde nichts veraendert.' }
    Write-RollbackLog "Installation gefunden: $installRoot" Cyan

    Get-Process -Name 'HCA_Produktionsmanager' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name 'HCA_Backend' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 1200

    New-Item -ItemType Directory -Force -Path (Join-Path $backupRoot 'files') | Out-Null
    $backupReady = $true
    Write-RollbackLog "Aktueller Programmstand wird gesichert: $backupRoot" Cyan

    foreach ($source in $payloadFiles) {
        $relative = Get-RelativePath $payloadRoot $source.FullName
        if ($relative -ieq 'config.json' -or $relative.StartsWith('data\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unzulaessige Datei im Rollback-Paket: $relative"
        }
        $target = Join-Path $installRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $backupFile = Join-Path (Join-Path $backupRoot 'files') $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupFile) | Out-Null
            Copy-Item -LiteralPath $target -Destination $backupFile -Force
        } else {
            $newFiles.Add($relative)
        }
        Copy-Item -LiteralPath $source.FullName -Destination $target -Force
    }

    Write-RollbackLog 'Wiederhergestellte Dateien werden kontrolliert ...' Cyan
    foreach ($source in $payloadFiles) {
        $relative = Get-RelativePath $payloadRoot $source.FullName
        $target = Join-Path $installRoot $relative
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source.FullName).Hash -ne
            (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash) {
            throw "Installierte Datei ist beschaedigt: $relative"
        }
    }

    $cachePath = Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager\WebView2'
    if (Test-Path -LiteralPath $cachePath) {
        Move-Item -LiteralPath $cachePath -Destination (Join-Path $backupRoot 'WebView2-cache')
        $cacheMoved = $true
        Write-RollbackLog 'WebView2-Zwischenspeicher wurde gesichert und geleert.' Cyan
    }

    Write-RollbackLog 'Letzter funktionierender Programmstand v0.13.66 wurde wiederhergestellt.' Green
    Write-RollbackLog 'config.json, data, Datenbank, Dokumente und NAS-Konfiguration wurden nicht veraendert.' Green
    Write-RollbackLog 'HCA wird gestartet ...' Cyan
    Start-Process -FilePath (Join-Path $installRoot 'HCA_Produktionsmanager.exe') -WorkingDirectory $installRoot
    Write-RollbackLog "Protokoll: $logFile" DarkGray
    exit 0
} catch {
    Write-RollbackLog ('FEHLER: ' + $_.Exception.Message) Red
    try { Restore-Backup } catch { Write-RollbackLog ('ROLLBACK-FEHLER: ' + $_.Exception.Message) Red }
    Write-RollbackLog "Protokoll: $logFile" Yellow
    exit 1
}
