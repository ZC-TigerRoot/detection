# 原生启动：FastAPI 提供 API，并托管 frontend/dist 静态文件
# 用法: .\scripts\run-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path "backend\.venv\Scripts\uvicorn.exe")) {
    Write-Host "请先运行: .\scripts\setup-windows-native.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "缺少 frontend\dist，请先 setup 或 npm run build" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "backend\.env")) {
    Write-Host "缺少 backend\.env" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path "data\uploads", "data\exports" | Out-Null

$env:STATIC_DIR = (Resolve-Path "frontend\dist").Path
# 让配置能读到 uploads（相对项目根）
$env:PYTHONPATH = (Resolve-Path "backend").Path

Write-Host "STATIC_DIR=$env:STATIC_DIR" -ForegroundColor Cyan
Write-Host "启动 http://0.0.0.0:8000  (Ctrl+C 停止)" -ForegroundColor Green

Set-Location backend
& .\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
