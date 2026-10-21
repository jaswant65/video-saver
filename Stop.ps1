$ErrorActionPreference = 'Stop'
$stateFile = Join-Path $PSScriptRoot 'running.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'No running Video Saver was recorded.'; exit 0 }
$record = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$target = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
if ($target) {
    if ($target.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.started -or $target.Path -ne $record.executable) {
        throw 'The recorded process no longer matches Video Saver. No process was stopped.'
    }
    & taskkill.exe /PID $target.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Windows could not stop Video Saver.' }
}
Remove-Item -LiteralPath $stateFile
Write-Host 'Video Saver stopped. Your saved videos are still in the library folder.'
