$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$repo = 'quanhoang55/digit_detection_new'
$match = Select-String -LiteralPath packaging\TramCanQR.iss -Pattern '^#define MyAppVersion "([^"]+)"'
$version = $match.Matches[0].Groups[1].Value
if (-not $version) { throw 'Khong doc duoc phien ban' }
$tag = "v$version"
$handoff = Join-Path $projectRoot "dist\handoff-$version"
$notes = Join-Path $projectRoot "docs\release-notes-$version.md"
$assets = @('TramCanQRLocal-Setup.exe', "TramCanQRLocal-Setup-$version.exe", 'SHA256SUMS.txt', 'CAP-NHAT-BAN-MOI.cmd') |
    ForEach-Object { Join-Path $handoff $_ }
foreach ($file in @($assets) + @($notes)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Thieu $file; hay build va kiem chung truoc" }
}
foreach ($line in [IO.File]::ReadAllLines((Join-Path $handoff 'SHA256SUMS.txt'))) {
    if ($line -notmatch '^([a-fA-F0-9]{64})  (TramCanQRLocal-Setup[^\\/]*\.exe)$') { throw 'Checksum khong hop le' }
    $expected = $Matches[1]
    $file = Join-Path $handoff $Matches[2]
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $expected) { throw "Checksum khong khop $file" }
}
$dirty = & git status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Can commit va push dung source da kiem chung truoc khi release' }
& gh release create $tag $assets --repo $repo --verify-tag --draft --title "Tram Can QR Local $tag" --notes-file $notes
if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc draft release; khong ghi de release da co' }
& gh release edit $tag --repo $repo --draft=false --latest
if ($LASTEXITCODE -ne 0) { throw 'Da tao draft nhung chua phat hanh' }
Write-Output "https://github.com/$repo/releases/tag/$tag"
