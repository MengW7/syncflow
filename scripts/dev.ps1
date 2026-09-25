$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "找不到 docker。请先打开 Docker Desktop，等状态变为 Running，再开一个新的 PowerShell。"
}

if (-not (Test-Path "$Root\docker-compose.yml")) {
    Write-Error "找不到 $Root\docker-compose.yml"
}

if (-not (Test-Path "$Root\.env")) {
    Copy-Item "$Root\.env.example" "$Root\.env"
    Write-Host "已创建 .env（请确认 MYSQL_HOST=127.0.0.1，REDIS_ADDR=127.0.0.1:6379）"
}

docker compose -f "$Root\docker-compose.yml" --env-file "$Root\.env" up -d mysql redis
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose 启动失败，MySQL/Redis 并未起来。"
}

docker compose -f "$Root\docker-compose.yml" ps

Write-Host ""
Write-Host "依赖已提交启动。请等 mysql/redis 变为 healthy 后再起 API。"
Write-Host ""
Write-Host "终端 1 - API:"
Write-Host "  cd $Root\backend"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "终端 2 - Web:"
Write-Host "  cd $Root\frontend"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "检查:"
Write-Host "  curl.exe http://127.0.0.1:8000/healthz"