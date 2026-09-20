# One command to show Nightshift.
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python -m pip install -q -r requirements.txt
Write-Host "Desk:     http://127.0.0.1:8080"
Write-Host "Cockpit:  http://127.0.0.1:8080/cockpit"
Write-Host "Share:    http://127.0.0.1:8080/share"
Write-Host "LAN bind 0.0.0.0:8080 — still not the public internet"
& .\.venv\Scripts\python -m nightshift serve --host 0.0.0.0 --port 8080
