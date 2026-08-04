# Windows Server 一键构建启动（需已安装 Docker + 已配置 backend\.env）
# 用法: 在项目根目录 PowerShell 执行  .\scripts\deploy-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 工作目录: $Root" -ForegroundColor Cyan

function Get-ComposeCommand {
    # 优先 Compose V2 插件: docker compose
    $null = docker compose version 2>$null
    if ($LASTEXITCODE -eq 0) {
        return @{ Mode = "v2"; Args = @("compose") }
    }
    # 回退 Compose V1 独立程序: docker-compose
    $dc = Get-Command docker-compose -ErrorAction SilentlyContinue
    if ($dc) {
        return @{ Mode = "v1"; Args = @() }
    }
    return $null
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 docker 命令。请先安装 Docker Engine / Mirantis Container Runtime。" -ForegroundColor Red
    Write-Host "安装后执行: docker version" -ForegroundColor Yellow
    exit 1
}

$compose = Get-ComposeCommand
if (-not $compose) {
    Write-Host @"
未找到 Docker Compose。

你的环境能运行 docker，但不支持「docker compose」子命令（常见于 WinServer 2019）。

请任选其一:
  1) 安装 Docker Compose V1（推荐先试）
     下载: https://github.com/docker/compose/releases
     将 docker-compose-windows-x86_64.exe 重命名为 docker-compose.exe
     放到例如 C:\Program Files\Docker\ 并加入 PATH

  2) 或升级到带 Compose 插件的 Docker（docker compose version 能跑通）

安装后在本目录执行:
  docker-compose up -d --build
  或
  docker compose up -d --build
"@ -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host "已创建 backend\.env，请先编辑 DATABASE_URL / LLM_API_KEY 后再运行。" -ForegroundColor Yellow
    notepad "backend\.env"
    exit 1
}

New-Item -ItemType Directory -Force -Path "data\uploads", "data\exports" | Out-Null

Write-Host "==> 使用 Compose 模式: $($compose.Mode)" -ForegroundColor Cyan
if ($compose.Mode -eq "v2") {
    Write-Host "==> docker compose up -d --build" -ForegroundColor Cyan
    docker compose up -d --build
} else {
    Write-Host "==> docker-compose up -d --build" -ForegroundColor Cyan
    docker-compose up -d --build
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "启动失败，exit code=$LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "==> 状态" -ForegroundColor Cyan
if ($compose.Mode -eq "v2") {
    docker compose ps
} else {
    docker-compose ps
}

Write-Host ""
Write-Host "前端: http://$((hostname)):8080" -ForegroundColor Green
Write-Host "API : http://$((hostname)):8000/docs" -ForegroundColor Green
Write-Host "健康: 浏览器或 curl http://127.0.0.1:8000/api/health" -ForegroundColor Green
