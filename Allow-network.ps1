# Adds one inbound rule, limited to this app, TCP port 8787, and local subnets.
# Run in an administrator PowerShell only if other devices cannot connect.
$ErrorActionPreference = 'Stop'
$ruleName = 'LocalVideoSaver8787'
$pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run Setup.cmd first so the local Python environment exists.' }
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter -Program $pythonExe | Out-Null
    $existing | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any | Out-Null
    $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 8787 | Out-Null
    $existing | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress LocalSubnet | Out-Null
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Video Saver - local network' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8787 -RemoteAddress LocalSubnet -Program $pythonExe -Profile Any | Out-Null
}
Write-Host 'Video Saver is allowed on the local network at port 8787.'
