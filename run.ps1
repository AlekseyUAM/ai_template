# Запуск Web UI Agent Monitor (Windows). Одна команда:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
# Требует предварительного .\setup.ps1.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Root = (Get-Location).Path
$Venv = Join-Path $Root ".venv"

if (-not (Test-Path $Venv)) { throw "Сначала выполните .\setup.ps1" }
$EnvFile = Join-Path $Root ".ai1c.env"
if (Test-Path $EnvFile) { . $EnvFile }

$py = Join-Path $Venv "Scripts\python.exe"
$port = if ($env:AGENTMON_PORT) { $env:AGENTMON_PORT } else { "8765" }
Write-Host "[run] Agent Monitor: http://127.0.0.1:$port  (Ctrl+C для остановки)" -ForegroundColor Cyan
& $py -m agentmon
