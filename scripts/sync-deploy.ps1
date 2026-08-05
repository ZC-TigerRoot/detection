# 从 Git 拉取最新代码并重新部署（WinServer）
# 用法（项目根目录 PowerShell）:
#   .\scripts\sync-deploy.ps1
#   .\scripts\sync-deploy.ps1 -Mode native   # 强制原生
#   .\scripts\sync-deploy.ps1 -Mode docker   # 强制 Docker
#   .\scripts\sync-deploy.ps1 -SkipPull      # 已拉过代码只重建

param(
    [ValidateSet("auto", "docker", "native")]
    [string]$Mode = "auto",
    [switch]$SkipPull
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 工作目录: $Root" -ForegroundColor Cyan

if (-not $SkipPull) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "未找到 git，请安装 Git 或手动拷贝代码后加 -SkipPull" -ForegroundColor Red
        exit 1
    }
    Write-Host "==> git fetch / pull" -ForegroundColor Cyan
    git fetch origin
    git pull origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "git pull 失败，请处理冲突后重试" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    git log -1 --oneline
}

New-Item -ItemType Directory -Force -Path "data\uploads", "data\exports" | Out-Null

if (-not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host "已创建 backend\.env，请先填 DATABASE_URL / LLM_API_KEY 后重跑" -ForegroundColor Yellow
    notepad "backend\.env"
    exit 1
}

function Test-DockerCompose {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $null }
    $null = docker compose version 2>$null
    if ($LASTEXITCODE -eq 0) { return "v2" }
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) { return "v1" }
    return $null
}

$composeMode = Test-DockerCompose
if ($Mode -eq "auto") {
    if ($composeMode) { $Mode = "docker" } else { $Mode = "native" }
}

if ($Mode -eq "docker") {
    if (-not $composeMode) {
        Write-Host "未检测到 Docker Compose，改用 native 或先装 Docker" -ForegroundColor Red
        exit 1
    }
    Write-Host "==> Docker 重建启动 ($composeMode)" -ForegroundColor Cyan
    if ($composeMode -eq "v2") {
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        docker compose ps
    } else {
        docker-compose up -d --build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        docker-compose ps
    }
    Write-Host ""
    Write-Host "部署完成。前端: http://$((hostname)):8088  API: http://$((hostname)):8000/docs" -ForegroundColor Green
    Write-Host "中文若曾是 ????: 重启后已迁移 NVARCHAR；请重新上传并 AI 解析损坏项目。" -ForegroundColor Yellow
    exit 0
}

# ----- native -----
Write-Host "==> 原生部署：更新依赖 + 构建前端" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 python。请安装 Python 3.11+ 并加入 PATH" -ForegroundColor Red
    exit 1
}

Push-Location backend
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\pip.exe install -q -r requirements.txt
& .\.venv\Scripts\pip.exe install -q "pyodbc==5.2.0" 2>$null
Pop-Location

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path "frontend\dist\index.html")) {
        Write-Host "无 npm 且无 frontend\dist，无法构建前端" -ForegroundColor Red
        exit 1
    }
    Write-Host "无 npm，沿用已有 frontend\dist" -ForegroundColor Yellow
} else {
    Push-Location frontend
    npm install
    npm run build
    Pop-Location
}

Write-Host @"

==> 代码与依赖已就绪。

请重启 API 进程（任选）:
  1) 若前台跑着 run-windows.ps1：Ctrl+C 后执行
       .\scripts\run-windows.ps1
  2) 若用 nssm / 服务:
       nssm restart DetectionAPI
       # 或 Restart-Service DetectionAPI
  3) 临时前台启动:
       .\scripts\run-windows.ps1

启动后访问: http://服务器IP:8000
健康检查:  http://127.0.0.1:8000/api/health

中文 ????: 重启会自动把 varchar 升为 nvarchar；已损坏数据需重新上传并 AI 解析。
"@ -ForegroundColor Green
