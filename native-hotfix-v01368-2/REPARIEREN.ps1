$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'HCA Produktionsmanager - Launcher-Reparatur v0.13.68.3'

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceExe = Join-Path $packageRoot 'payload\HCA_Produktionsmanager.exe'
$checksumFile = Join-Path $packageRoot 'SHA256SUMS_REPAIR.txt'
$stateRoot = Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager\repair'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logFile = Join-Path $stateRoot ('launcher-reparatur-' + $timestamp + '.log')
$candidates = New-Object System.Collections.Generic.List[string]

New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null

function Write-RepairLog([string] $Message, [ConsoleColor] $Color = [ConsoleColor]::Gray) {
    Add-Content -LiteralPath $logFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Message) -Encoding UTF8
    Write-Host $Message -ForegroundColor $Color
}

function Add-Candidate([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    try {
        $value = [Environment]::ExpandEnvironmentVariables($Path.Trim().Trim('"'))
        if ([IO.Path]::GetFileName($value) -ieq 'HCA_Produktionsmanager.exe') {
            $value = Split-Path -Parent $value
        }
        if ([string]::IsNullOrWhiteSpace($value)) { return }
        $full = [IO.Path]::GetFullPath($value)
        if (-not $candidates.Contains($full)) { $candidates.Add($full) }
    } catch { }
}

function Get-ValidCandidate {
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'HCA_Produktionsmanager.exe') -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Find-HcaInstall {
    # Laufender Client
    Get-Process -Name 'HCA_Produktionsmanager' -ErrorAction SilentlyContinue | ForEach-Object {
        try { Add-Candidate $_.MainModule.FileName } catch { }
    }
    try {
        Get-CimInstance Win32_Process -Filter "Name='HCA_Produktionsmanager.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
            Add-Candidate $_.ExecutablePath
        }
    } catch { }

    # Registry
    $registryRoots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $registryRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $entry = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction Stop
                if ($entry.DisplayName -like '*HCA*Produktionsmanager*' -or $_.PSChildName -eq 'HCA Produktionsmanager') {
                    Add-Candidate $entry.InstallLocation
                    Add-Candidate $entry.DisplayIcon
                }
            } catch { }
        }
    }

    # Exakter Pfad aus einem bereits erfolgreichen HCA-Reparaturprotokoll
    $logPatterns = @(
        (Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager\repair\reparatur-*.log'),
        'C:\Users\*\AppData\Local\HCA Produktionsmanager\repair\reparatur-*.log'
    )
    foreach ($pattern in $logPatterns) {
        Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | ForEach-Object {
            try {
                Get-Content -LiteralPath $_.FullName -ErrorAction Stop | ForEach-Object {
                    if ($_ -match 'Installation gefunden:\s*(.+)$') { Add-Candidate $matches[1] }
                }
            } catch { }
        }
    }

    # Typische Pfade des aktuellen und aller lokalen Benutzer
    Add-Candidate (Join-Path $env:LOCALAPPDATA 'Programs\HCA Produktionsmanager')
    Add-Candidate (Join-Path $env:LOCALAPPDATA 'Programs\HCA-Produktionsmanager')
    Add-Candidate (Join-Path $env:ProgramFiles 'HCA Produktionsmanager')
    if (${env:ProgramFiles(x86)}) { Add-Candidate (Join-Path ${env:ProgramFiles(x86)} 'HCA Produktionsmanager') }
    Add-Candidate 'C:\HCA Produktionsmanager'
    Add-Candidate 'C:\HCA-Produktionsmanager'
    @(
        'C:\Users\*\AppData\Local\Programs\HCA Produktionsmanager',
        'C:\Users\*\AppData\Local\Programs\HCA-Produktionsmanager'
    ) | ForEach-Object {
        Get-Item -Path $_ -ErrorAction SilentlyContinue | ForEach-Object { Add-Candidate $_.FullName }
    }

    # Desktop- und Startmenue-Verknuepfungen
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
                    if ([IO.Path]::GetFileName($shortcut.TargetPath) -ieq 'HCA_Produktionsmanager.exe') {
                        Add-Candidate $shortcut.TargetPath
                    }
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

try {
    Write-RepairLog 'HCA Launcher-Reparatur v0.13.68.3' White
    Write-RepairLog 'Reparaturpaket wird geprueft ...' Cyan

    if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf) -or -not (Test-Path -LiteralPath $checksumFile -PathType Leaf)) {
        throw 'Das Reparaturpaket ist unvollstaendig.'
    }
    $line = Get-Content -LiteralPath $checksumFile | Select-Object -First 1
    if ($line -notmatch '^([0-9a-fA-F]{64})\s+\*?(.+)$') { throw 'Die Pruefsummenliste ist ungueltig.' }
    $expectedHash = $matches[1].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceExe).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw 'Die Pruefsumme des neuen Launchers stimmt nicht.' }
    Write-RepairLog 'Reparaturpaket erfolgreich geprueft.' Green

    $installRoot = Find-HcaInstall
    if (-not $installRoot) {
        Write-RepairLog 'Installation nicht automatisch gefunden. Ordnerauswahl wird geoeffnet ...' Yellow
        $installRoot = Select-HcaInstall
    }
    if (-not $installRoot) { throw 'HCA_Produktionsmanager.exe wurde nicht gefunden. Es wurde nichts veraendert.' }

    $targetExe = Join-Path $installRoot 'HCA_Produktionsmanager.exe'
    Write-RepairLog "Installation gefunden: $installRoot" Cyan
    Get-Process -Name 'HCA_Produktionsmanager' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 1000

    $backupRoot = Join-Path $stateRoot ('launcher-backup-' + $timestamp)
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    $backupExe = Join-Path $backupRoot 'HCA_Produktionsmanager.exe'
    Copy-Item -LiteralPath $targetExe -Destination $backupExe -Force
    Write-RepairLog "Bisheriger Launcher gesichert: $backupRoot" Cyan

    try {
        Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $targetExe).Hash.ToLowerInvariant() -ne $expectedHash) {
            throw 'Die installierte Datei hat nicht die erwartete Pruefsumme.'
        }
    } catch {
        Copy-Item -LiteralPath $backupExe -Destination $targetExe -Force
        throw ($_.Exception.Message + ' Der bisherige Launcher wurde wiederhergestellt.')
    }

    Write-RepairLog 'Launcher-Hotfix erfolgreich installiert und geprueft.' Green
    Start-Process -FilePath $targetExe -WorkingDirectory $installRoot
    Write-RepairLog "Protokoll: $logFile" DarkGray
    exit 0
} catch {
    Write-RepairLog ('FEHLER: ' + $_.Exception.Message) Red
    Write-RepairLog "Protokoll: $logFile" Yellow
    exit 1
}
