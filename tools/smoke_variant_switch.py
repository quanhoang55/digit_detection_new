"""Exercise the actual switching script with isolated process/dialog shims."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

HARNESS = r'''
param([string]$Root, [string]$Mode, [switch]$Cancel, [switch]$Missing, [switch]$NoOther)
$ErrorActionPreference = 'Stop'
$env:LOCALAPPDATA = $Root
Add-Type -AssemblyName System.Windows.Forms
Add-Type 'public static class SwitchTestDialog { public static string Answer = "Yes"; public static string Show(params object[] args) { return Answer; } }'
if ($Cancel) { [SwitchTestDialog]::Answer = 'No' }
$global:SwitchStopped = $false
$global:SwitchOpened = $false
$local = Join-Path $Root 'Programs\TramCanQRLocal\TramCanQRLocal.exe'
$gemini = Join-Path $Root 'Programs\TramCanQR\TramCanQR.exe'
$global:SwitchTarget = if ($Mode -eq 'Local') { $local } else { $gemini }
$global:SwitchOther = if ($Mode -eq 'Local') { $gemini } else { $local }
if ($Missing) { Remove-Item -LiteralPath $global:SwitchTarget }
function Get-Process {
    param($Name, $ErrorAction)
    if ($Name -ne [IO.Path]::GetFileNameWithoutExtension($global:SwitchOther)) { throw 'Wrong process name' }
    if (-not $global:SwitchStopped -and -not $NoOther) { [pscustomobject]@{Path=$global:SwitchOther;Id=100} }
    [pscustomobject]@{Path=(Join-Path $Root 'unrelated.exe');Id=999}
}
function Stop-Process {
    param([Parameter(ValueFromPipeline=$true)]$InputObject, [switch]$Force)
    process {
        if ($InputObject.Id -ne 100 -or $InputObject.Path -ne $global:SwitchOther) { throw 'Stopped unrelated program' }
        if ($Cancel) { throw 'Ignored cancellation' }
        $global:SwitchStopped = $true
    }
}
function Start-Process {
    param($FilePath, $WorkingDirectory, $WindowStyle)
    if ($FilePath -ne $global:SwitchTarget -or $WindowStyle -ne 'Hidden') { throw 'Wrong target' }
    if (-not $NoOther -and -not $global:SwitchStopped) { throw 'Started two variants concurrently' }
    $global:SwitchOpened = $true
}
try {
    & (Join-Path $Root 'Programs\TramCanQRLocal\CHUYEN-BAN.ps1') -Mode $Mode
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
finally {
    @{stopped=$global:SwitchStopped;opened=$global:SwitchOpened} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $Root 'result.json') -Encoding UTF8
}
'''


def main():
    project = Path(__file__).resolve().parents[1]
    source = (project / 'packaging/CHUYEN-BAN.ps1').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='variant-switch-', dir=project / '.test-tmp') as tmp:
        base = Path(tmp)
        harness = base / 'harness.ps1'
        harness.write_text(HARNESS, encoding='utf-8-sig')
        for mode in ('Local', 'Gemini'):
            for scenario in ('switch', 'cancel', 'missing', 'no-other'):
                root = base / f'{mode}-{scenario}'
                local = root / 'Programs/TramCanQRLocal'
                local.mkdir(parents=True)
                gemini = root / 'Programs/TramCanQR'
                gemini.mkdir()
                (local / 'TramCanQRLocal.exe').write_bytes(b'local executable fixture')
                (gemini / 'TramCanQR.exe').write_bytes(b'gemini executable fixture')
                for name in ('config.env', 'measurements.db', 'photo.jpg'):
                    (root / name).write_bytes(b'existing data fixture')
                protected = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*') if p.is_file()}
                script = source.replace('[System.Windows.Forms.MessageBox]::Show', '[SwitchTestDialog]::Show')
                script = script.replace('Local\\TramCanQR-Switch', f'Local\\TramCanQR-Switch-Test-{root.name}')
                (local / 'CHUYEN-BAN.ps1').write_text(script, encoding='utf-8-sig')
                command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness), '-Root', str(root), '-Mode', mode]
                flag = {'cancel': '-Cancel', 'missing': '-Missing', 'no-other': '-NoOther'}.get(scenario)
                if flag:
                    command.append(flag)
                result = subprocess.run(command, capture_output=True, timeout=30)
                state = json.loads((root / 'result.json').read_text(encoding='utf-8-sig'))
                assert result.returncode == int(scenario == 'missing'), (mode, scenario, result.stdout, result.stderr)
                assert state == {'stopped': scenario == 'switch', 'opened': scenario in ('switch', 'no-other')}, state
                assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in protected.items())
                print(f'PASS {mode} {scenario}: exclusive startup, exact process path, shared data unchanged')


if __name__ == '__main__':
    main()
