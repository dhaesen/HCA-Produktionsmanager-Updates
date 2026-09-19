$ErrorActionPreference = 'Stop'

function Write-Step([string] $Message) {
    Write-Host "`n$Message" -ForegroundColor Cyan
}

function Find-HcaInstall {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\HCA Produktionsmanager'),
        (Join-Path $env:ProgramFiles 'HCA Produktionsmanager'),
        (Join-Path ${env:ProgramFiles(x86)} 'HCA Produktionsmanager'),
        (Join-Path $env:LOCALAPPDATA 'HCA Produktionsmanager')
    ) | Where-Object { $_ -and (Test-Path (Join-Path $_ 'HCA_Produktionsmanager.exe')) }

    if ($candidates.Count -gt 0) { return $candidates[0] }

    $shortcutRoots = @(
        [Environment]::GetFolderPath('Desktop'),
        [Environment]::GetFolderPath('CommonDesktopDirectory'),
        [Environment]::GetFolderPath('Programs'),
        [Environment]::GetFolderPath('CommonPrograms')
    ) | Where-Object { $_ -and (Test-Path $_) }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($root in $shortcutRoots) {
        foreach ($shortcut in Get-ChildItem -Path $root -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue) {
            try {
                $target = $shell.CreateShortcut($shortcut.FullName).TargetPath
                if ($target -and ([IO.Path]::GetFileName($target) -ieq 'HCA_Produktionsmanager.exe')) {
                    return [IO.Path]::GetDirectoryName($target)
                }
            } catch { }
        }
    }
    return $null
}

try {
    $packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    $sourceExe = Join-Path $packageRoot 'payload\HCA_Produktionsmanager.exe'
    $checksumFile = Join-Path $packageRoot 'SHA256SUMS_REPAIR.txt'
    if (!(Test-Path $sourceExe) -or !(Test-Path $checksumFile)) {
        throw 'Das Reparaturpaket ist unvollständig.'
    }

    Write-Step 'Reparaturpaket wird geprüft ...'
    $expectedHash = ((Get-Content $checksumFile | Select-Object -First 1) -split '\s+')[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $sourceExe).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw 'Die Prüfsumme des neuen Launchers stimmt nicht.' }

    $installRoot = Find-HcaInstall
    if (!$installRoot) {
        $installRoot = Read-Host 'Installationsordner des HCA Produktionsmanagers'
    }
    $targetExe = Join-Path $installRoot 'HCA_Produktionsmanager.exe'
    if (!(Test-Path $targetExe)) { throw "Im angegebenen Ordner wurde HCA_Produktionsmanager.exe nicht gefunden: $installRoot" }

    Write-Step "Installation gefunden: $installRoot"
    Get-Process -Name 'HCA_Produktionsmanager' -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 800

    $backupRoot = Join-Path $env:LOCALAPPDATA ('HCA Produktionsmanager\recovery\launcher-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    Copy-Item -LiteralPath $targetExe -Destination (Join-Path $backupRoot 'HCA_Produktionsmanager.exe') -Force

    Write-Step 'Neuer Launcher wird installiert ...'
    Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force
    $installedHash = (Get-FileHash -Algorithm SHA256 -Path $targetExe).Hash.ToLowerInvariant()
    if ($installedHash -ne $expectedHash) {
        Copy-Item -LiteralPath (Join-Path $backupRoot 'HCA_Produktionsmanager.exe') -Destination $targetExe -Force
        throw 'Der neue Launcher konnte nicht verifiziert werden. Die Sicherung wurde zurückgespielt.'
    }

    Write-Host "`nLauncher-Hotfix v0.13.68.2 wurde erfolgreich installiert." -ForegroundColor Green
    Write-Host "Sicherung: $backupRoot"
    Start-Process -FilePath $targetExe -WorkingDirectory $installRoot
    exit 0
} catch {
    Write-Host "`nReparatur fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
