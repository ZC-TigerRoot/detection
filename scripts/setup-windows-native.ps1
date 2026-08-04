# 在 Windows Server 上原生安装依赖并启动（不依赖 Docker Linux 容器）
# 要求: Python 3.11+、Node 20+（仅首次构建前端）、ODBC Driver 18（用 SQL Server 时）
# 用法（管理员 PowerShell 可选）:
#   cd C:\Users\Administrator\Documents\GitHub\detection
#   .\scripts\setup-windows-native.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 项目目录: $Root" -ForegroundColor Cyan

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Cmd "python")) {
    Write-Host "未找到 python。请安装 Python 3.11+ 并勾选 Add to PATH: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

$pyVer = python --version 2>&1
Write-Host "Python: $pyVer"

if (-not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host "已生成 backend\.env，请编辑 DATABASE_URL / LLM 后保存。" -ForegroundColor Yellow
    Write-Host "本机原生部署 SQL Server 示例:" -ForegroundColor Yellow
    Write-Host '  DATABASE_URL=mssql+pyodbc://user:pass@127.0.0.1/detection?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
    Write-Host "若暂无 SQL Server，可先用 SQLite（把 DATABASE_URL 改成下面一行）:" -ForegroundColor Yellow
    $sqlitePath = (Join-Path $Root "data\detection.db") -replace '\\', '/'
    Write-Host "  DATABASE_URL=sqlite:///$sqlitePath"
    notepad "backend\.env"
    Read-Host "编辑并保存 .env 后按回车继续"
}

New-Item -ItemType Directory -Force -Path "data\uploads", "data\exports" | Out-Null

Write-Host "==> 创建/更新 Python 虚拟环境" -ForegroundColor Cyan
Push-Location backend
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt
# SQL Server 需要 pyodbc（失败不阻断，可用 SQLite）
& .\.venv\Scripts\pip.exe install "pyodbc==5.2.0" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pyodbc 安装失败（若用 SQLite 可忽略）。SQL Server 请先装 ODBC Driver 18 再: pip install pyodbc" -ForegroundColor Yellow
}
Pop-Location

$needBuild = -not (Test-Path "frontend\dist\index.html")
if ($needBuild) {
    if (-not (Test-Cmd "npm")) {
        Write-Host "未找到 npm，且 frontend\dist 不存在。请安装 Node.js LTS 后重跑，或在有 Node 的机器 build 后拷贝 frontend\dist。" -ForegroundColor Red
        exit 1
    }
    Write-Host "==> 构建前端" -ForegroundColor Cyan
    Push-Location frontend
    npm install
    npm run build
    Pop-Location
} else {
    Write-Host "==> 已存在 frontend\dist，跳过构建（强制重建请删除 dist 后重跑）" -ForegroundColor Green
}

# 简易静态服务：用后端同时挂静态（开发/小规模生产够用）
Write-Host @"

==> 安装完成。

【方式 1】一键前台运行（API + 静态页同一端口 8000）:
  .\scripts\run-windows.ps1

浏览器打开: http://服务器IP:8000

【方式 2】仅 API，前端交给 IIS:
  见 docs\DEPLOY-Windows.md 方案 B

"@ -ForegroundColor Green
