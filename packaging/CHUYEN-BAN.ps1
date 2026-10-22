param([ValidateSet('Local', 'Gemini')][string]$Mode = 'Local')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$switchLock = New-Object System.Threading.Mutex($false, 'Local\TramCanQR-Switch')
$locked = $false
try {
    $locked = $switchLock.WaitOne(0)
    if (-not $locked) { exit }
    $localExe = Join-Path $PSScriptRoot 'TramCanQRLocal.exe'
    $geminiExe = Join-Path $env:LOCALAPPDATA 'Programs\TramCanQR\TramCanQR.exe'
    $target = if ($Mode -eq 'Local') { $localExe } else { $geminiExe }
    $other = if ($Mode -eq 'Local') { $geminiExe } else { $localExe }
    $otherName = [IO.Path]::GetFileNameWithoutExtension($other)
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "Chua cai ban $Mode. Hay cai bo cai cua ban nay truoc. Du lieu hien tai van duoc giu nguyen."
    }
    $running = @(Get-Process -Name $otherName -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq [IO.Path]::GetFullPath($other) })
    if ($running.Count) {
        $answer = [System.Windows.Forms.MessageBox]::Show(
            "Hay luu xong luot can dang lam truoc khi chuyen ban.`n`nDa luu xong va muon chuyen sang $Mode?",
            'Tram Can QR - Chuyen ban', 'YesNo', 'Question', 'Button2')
        if ($answer -ne 'Yes') { exit }
        $running | Stop-Process -Force
        foreach ($attempt in 1..40) {
            $remaining = @(Get-Process -Name $otherName -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -eq $other })
            if (-not $remaining.Count) { break }
            Start-Sleep -Milliseconds 250
        }
        if ($remaining.Count) { throw 'Chua dong duoc ban dang chay. Hay luu va dong ung dung, sau do thu lai.' }
    }
    # Both programs use the same origin, DB, photos, station and cloud config.
    Start-Process -FilePath $target -WorkingDirectory (Split-Path -Parent $target) -WindowStyle Hidden
} catch {
    [void][System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Tram Can QR', 'OK', 'Error')
    exit 1
} finally {
    if ($locked) { $switchLock.ReleaseMutex() }
    $switchLock.Dispose()
}
