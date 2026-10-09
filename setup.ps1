# Единая установка и подготовка окружения Agent Monitor (Windows).
# Одна команда:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
#   - создаёт .venv, ставит приложение и зависимости
#   - поднимает PostgreSQL в Docker (если доступен), иначе SQLite
#   - пишет .ai1c.env для .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Root = (Get-Location).Path
$Venv = Join-Path $Root ".venv"
$EnvFile = Join-Path $Root ".ai1c.env"

function Say($m)  { Write-Host "[setup] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[setup] $m" -ForegroundColor Yellow }

# 1. Python + venv
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "python не найден — установите Python 3.10+" }
if (-not (Test-Path $Venv)) {
  Say "создаю виртуальное окружение .venv"
  python -m venv $Venv
}
$py = Join-Path $Venv "Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null

# 2. Приложение
Say "устанавливаю приложение (app, editable) и зависимости"
& $py -m pip install -e (Join-Path $Root "app")

# 3. База данных
$dockerOk = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
  try { docker info *> $null; $dockerOk = $true } catch { $dockerOk = $false }
}
if ($dockerOk) {
  # Свободный хост-порт начиная с 5432 (5432 может быть занят локальным Postgres).
  $env:AI1C_PG_PORT = (& $py -c @"
import socket
for p in range(5432, 5460):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', p)); s.close(); print(p); break
    except OSError:
        continue
else:
    print(5432)
"@).Trim()
  $compose = "deploy\postgres\docker-compose.yml"
  Say "поднимаю PostgreSQL в Docker (deploy/postgres) на порту $($env:AI1C_PG_PORT)"
  docker compose -f (Join-Path $Root $compose) down --remove-orphans *> $null
  docker compose -f (Join-Path $Root $compose) up -d
  Say "устанавливаю драйвер psycopg"
  & $py -m pip install "psycopg[binary]" | Out-Null
  Say "жду готовности PostgreSQL..."
  for ($i = 0; $i -lt 30; $i++) {
    docker exec ai1c-postgres pg_isready -U ai1c *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
  }
  $Dsn = "postgresql://ai1c:ai1c@127.0.0.1:$($env:AI1C_PG_PORT)/ai1c"
} else {
  Warn "Docker недоступен — использую локальный SQLite"
  $Dsn = Join-Path $Root "app\agentmon.db"
}

# 4. Конфиг
@"
# Сгенерировано setup.ps1 — используется run.ps1
`$env:AGENTMON_DSN = "$Dsn"
`$env:AGENTMON_DB = "$(Join-Path $Root "app\agentmon.db")"
"@ | Set-Content -Encoding UTF8 $EnvFile
Say "конфиг записан: .ai1c.env (AGENTMON_DSN=$Dsn)"

# 5. Проверка требований
foreach ($t in @("git","docker","claude")) {
  if (Get-Command $t -ErrorAction SilentlyContinue) { Say "найдено: $t" } else { Warn "не найдено (не блокирует): $t" }
}
Say "Готово. Поднять Web UI: .\run.ps1"
