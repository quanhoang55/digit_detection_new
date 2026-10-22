param([ValidateSet("Local", "AiAuto")][string]$Variant = "Local")
$ErrorActionPreference = "Stop"
if ($Variant -eq "AiAuto") {
    & (Join-Path $PSScriptRoot "build_windows_auto.ps1")
    exit
}
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$versionMatch = Select-String -LiteralPath packaging\TramCanQR.iss -Pattern '^#define MyAppVersion "([^"]+)"'
$version = $versionMatch.Matches[0].Groups[1].Value
if (-not $version) { throw "Khong doc duoc phien ban bo cai" }
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path -LiteralPath $iscc)) {
    $iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path -LiteralPath $python)) { throw "Thieu .venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $iscc)) { throw "Can Inno Setup 6 de tao bo cai Windows" }
& $python -c "import torch, PyInstaller; assert torch.version.cuda is None, 'Use CPU-only PyTorch'; assert PyInstaller.__version__ == '6.21.0'; print('CPU Torch', torch.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Moi truong build local YOLO chua dung" }
$modelInfo = Get-Content -LiteralPath model\MODEL-INFO.json -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath backend\model\best.pt -Algorithm SHA256).Hash -ne $modelInfo.sha256) {
    throw "Model khong khop MODEL-INFO.json"
}
if ((Get-FileHash -LiteralPath backend\model\crop.pt -Algorithm SHA256).Hash -ne $modelInfo.crop_sha256) {
    throw "Crop model khong khop MODEL-INFO.json"
}
$buildTemp = Join-Path $projectRoot ".test-tmp\local-build-temp"
New-Item -ItemType Directory -Path $buildTemp -Force | Out-Null
$previousTemp, $previousTmp, $previousCache = $env:TEMP, $env:TMP, $env:PYINSTALLER_CONFIG_DIR
try {
    $env:TEMP = $buildTemp
    $env:TMP = $buildTemp
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot ".test-tmp\pyinstaller-local-cache"
    # PowerShell 5 treats native stderr as ErrorRecords when output is logged.
    # PyInstaller writes normal progress to stderr; retain its actual exit code.
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $python -m PyInstaller --noconfirm --clean --workpath build\local packaging\TramCanQR.spec 2>&1 |
            ForEach-Object { Write-Output $_.ToString() }
        $pyInstallerExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($pyInstallerExit -ne 0) { throw "PyInstaller local build failed (exit $pyInstallerExit)" }
    $portable = Join-Path $projectRoot "dist\TramCanQRLocal"
    $handoff = Join-Path $projectRoot "dist\handoff-$version"
    New-Item -ItemType Directory -Path $handoff -Force | Out-Null
    foreach ($name in @("customer-config.env.example", "HUONG-DAN-KHACH-HANG.md", "CAP-NHAT-BAN-MOI.cmd", "CHUYEN-BAN.ps1")) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\$name") -Destination $portable -Force
        Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\$name") -Destination $handoff -Force
    }
    Copy-Item -LiteralPath model\MODEL-INFO.json -Destination $portable -Force
    Copy-Item -LiteralPath model\MODEL-INFO.json -Destination $handoff -Force
    & $iscc packaging\TramCanQR.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup local build failed" }
    $installer = Join-Path $projectRoot "dist\installer\TramCanQRLocal-Setup-$version.exe"
    Copy-Item -LiteralPath $installer -Destination $handoff -Force
    Copy-Item -LiteralPath $installer -Destination (Join-Path $handoff "TramCanQRLocal-Setup.exe") -Force
    Copy-Item -LiteralPath $installer -Destination (Join-Path $projectRoot "dist\installer\TramCanQRLocal-Setup.exe") -Force
    $hashes = Get-ChildItem -LiteralPath $handoff -File -Filter *.exe | ForEach-Object {
        (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() + "  " + $_.Name
    }
    $hashes | Set-Content -LiteralPath (Join-Path $handoff "SHA256SUMS.txt") -Encoding ascii
    Write-Output "Local upgrade handoff: $handoff"
} finally {
    $env:TEMP, $env:TMP, $env:PYINSTALLER_CONFIG_DIR = $previousTemp, $previousTmp, $previousCache
}
