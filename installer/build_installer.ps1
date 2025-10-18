param(
    [ValidateSet('Portable', 'Installer')]
    [string]$Mode = 'Portable',
    [string]$Python = 'python',
    [string]$InnoSetupPath
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..')).Path

function Invoke-Step {
    param(
        [string]$Message,
        [scriptblock]$Action
    )
    Write-Host "[+] $Message"
    & $Action
}

Push-Location $repoRoot
try {
    Invoke-Step -Message 'Upgrading pip and installing build dependencies' -Action {
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -r (Join-Path $scriptRoot 'requirements.txt')
    }

    Invoke-Step -Message 'Cleaning previous build artifacts' -Action {
        Remove-Item -ErrorAction Ignore -Recurse -Force (Join-Path $repoRoot 'build')
        Remove-Item -ErrorAction Ignore -Recurse -Force (Join-Path $repoRoot 'dist')
    }

    Invoke-Step -Message 'Running PyInstaller' -Action {
        & $Python -m PyInstaller --noconfirm --clean (Join-Path $scriptRoot 'ActiveRecallPDF.spec')
    }

    $portableDir = Join-Path $repoRoot 'dist/ActiveRecallPDF'
    if (-not (Test-Path $portableDir)) {
        throw 'PyInstaller output missing: dist/ActiveRecallPDF'
    }

    Invoke-Step -Message 'Copying documentation into distribution' -Action {
        Copy-Item -Path (Join-Path $repoRoot 'README.md') -Destination $portableDir -Force
        Copy-Item -Path (Join-Path $repoRoot 'GUIDE.md') -Destination $portableDir -Force
    }

    Invoke-Step -Message 'Creating portable zip archive' -Action {
        $zipPath = Join-Path $repoRoot 'dist/ActiveRecallPDF-portable.zip'
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }
        Compress-Archive -Path (Join-Path $portableDir '*') -DestinationPath $zipPath
    }

    if ($Mode -eq 'Installer') {
        if (-not $InnoSetupPath) {
            throw 'Provide -InnoSetupPath pointing to ISCC.exe to build the installer.'
        }
        if (-not (Test-Path $InnoSetupPath)) {
            throw "Inno Setup compiler not found at $InnoSetupPath"
        }
        Invoke-Step -Message 'Building guided installer with Inno Setup' -Action {
            & $InnoSetupPath (Join-Path $scriptRoot 'ActiveRecallPDF.iss')
        }
    }

    Invoke-Step -Message 'Generating SHA256 checksums' -Action {
        $checksumPath = Join-Path $repoRoot 'dist/checksums.txt'
        if (Test-Path $checksumPath) {
            Remove-Item $checksumPath -Force
        }
        Get-ChildItem -Path (Join-Path $repoRoot 'dist') -File -Recurse |
            Where-Object { $_.Extension -in '.exe', '.zip' } |
            Get-FileHash -Algorithm SHA256 |
            ForEach-Object { "{0}  {1}" -f $_.Hash, $_.Path } |
            Out-File -FilePath $checksumPath -Encoding ascii
    }

    Write-Host "[+] Build complete. Review artifacts under dist/"
}
finally {
    Pop-Location
}
