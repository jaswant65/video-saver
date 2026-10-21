param([ValidateRange(1,65535)][int]$Port = 8787, [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$address = "http://127.0.0.1:$Port"
$existing = $null
try {
    $existing = Invoke-RestMethod -Uri "$address/api/state" -TimeoutSec 2
} catch { }
if ($existing) {
    if ($existing.app -ne 'video-saver') { throw "Port $Port is occupied by another app or an older Video Saver. Stop that copy first, or choose -Port 8788." }
    Write-Host 'Video Saver is already running.'
    $existing.links | ForEach-Object { Write-Host "Network link: $_" }
    exit 0
}
$pythonExe = Join-Path $appRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExe = & py -3 -c 'import sys; print(sys.executable)'
    } else {
        $pythonExe = & python -c 'import sys; print(sys.executable)'
    }
    if ($LASTEXITCODE -ne 0 -or -not $pythonExe) { throw 'Install Python 3.11+ and run Setup.cmd first.' }
}
& $pythonExe -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
$serverFile = Join-Path $appRoot 'server.py'
$serverArgs = @('-u', ('"' + $serverFile + '"'), '--port', $Port)
if ($LocalOnly) { $serverArgs += '--local-only' }
$process = Start-Process -FilePath $pythonExe -ArgumentList $serverArgs -WorkingDirectory $appRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appRoot 'server.log') -RedirectStandardError (Join-Path $appRoot 'server-error.log') -PassThru
@{pid=$process.Id; started=$process.StartTime.ToUniversalTime().Ticks.ToString(); executable=$pythonExe} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $appRoot 'running.json')
$ready = $null
for ($attempt=0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 300
    try { $ready = Invoke-RestMethod -Uri "$address/api/state" -TimeoutSec 2; break } catch { }
    if ($process.HasExited) { break }
}
if (-not $ready) { throw 'Video Saver did not start. Check server-error.log in this folder.' }
Write-Host "This computer: $address"
$ready.links | ForEach-Object { Write-Host "Network link: $_" }
Write-Host 'Keep this computer awake. Run Stop.cmd to stop sharing.'
