# Windows Server 2019 部署指南

## 重要：先看你的 Docker 模式

本仓库镜像基于 **Linux**（`python:3.11-slim-bookworm`）。

若出现：

```text
no matching manifest for windows(10.0.17763)/amd64 in the manifest list entries
```

说明当前是 **Windows 容器模式**，**不能**直接 `docker-compose build` 本项目。

可选：

| 路线 | 条件 | 说明 |
|------|------|------|
| **A. 原生 Python（推荐 WinServer）** | 装 Python + Node | 不依赖 Linux 容器，见下文「方案 B」/`setup-windows-native.ps1` |
| B. 切换到 Linux 容器再 Docker | 需 Docker 支持 LCOW / 较新引擎 | 很多 2019 默认环境做不到或很折腾 |
| C. 另备一台 Linux 主机跑 Docker | 有 Linux 服务器 | 用原来的 `docker-compose` |

**WinServer 2019 默认请走方案 A（原生）。**

---

## 一、部署前准备

### 1. 服务器软件

| 组件 | 说明 |
|------|------|
| SQL Server | 已有实例即可 |
| Docker | Docker Engine / Mirantis / Docker Desktop（需支持 **Linux 容器**） |
| Git（可选） | 拉代码；或从本机拷贝项目目录 |
| 出网 | 构建镜像、调用 LLM 网关需要 |

检查 Docker：

```powershell
docker version
docker compose version
# 若上一行报错，再试（WinServer 2019 很常见）:
docker-compose version
```

| 现象 | 原因 | 处理 |
|------|------|------|
| `unknown shorthand flag: 'd' in -d` | 没有 Compose **插件**，`docker compose` 无效 | 改用 `docker-compose`（带连字符），或安装 Compose |
| `compose is not a docker command` | 同上 | 同上 |
| 只有 Windows 容器 | 无法按本仓库 Dockerfile 构建 | 改用下文「方案 B：无 Docker 原生部署」 |

**安装 Compose V1（独立 exe，WinServer 最省事）：**

1. 打开 https://github.com/docker/compose/releases  
2. 下载 `docker-compose-windows-x86_64.exe`（可用较稳的 v1.29.2 或 v2 的 Windows 独立包）  
3. 重命名为 `docker-compose.exe`，放到已在 PATH 的目录，例如：  
   `C:\Program Files\Docker\docker-compose.exe`  
4. 新开 PowerShell 执行：`docker-compose version`

### 2. 创建数据库

在 SSMS 或 `sqlcmd` 中执行：

```sql
CREATE DATABASE detection;
GO
-- 建议单独登录（示例）
CREATE LOGIN detection_app WITH PASSWORD = '改成强密码';
GO
USE detection;
CREATE USER detection_app FOR LOGIN detection_app;
ALTER ROLE db_owner ADD MEMBER detection_app;
GO
```

确认 SQL Server 允许 TCP 连接（配置管理器 → TCP/IP 启用，默认 1433），防火墙放行 1433（若仅本机 Docker 访问，可只允许本地）。

### 3. 获取代码

```powershell
# 示例目录
cd C:\
git clone https://github.com/ZC-TigerRoot/detection.git
cd detection
```

或把整个项目文件夹拷到 `C:\detection`。

### 4. 配置环境变量

```powershell
cd C:\detection
copy backend\.env.example backend\.env
notepad backend\.env
```

**Docker 部署**时 `DATABASE_URL` 主机名用 `host.docker.internal`：

```env
DATABASE_URL=mssql+pyodbc://detection_app:你的密码@host.docker.internal/detection?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
LLM_BASE_URL=https://你的网关/v1
LLM_API_KEY=你的密钥
LLM_MODEL=dsv4f
DEBUG=false
```

> 密码含 `@ : / # %` 等时必须 **URL 编码**（如 `@` → `%40`）。

---

## 二、方案 A：Docker 部署（推荐）

### 1. 构建并启动

在项目根目录 PowerShell：

```powershell
cd C:\Users\Administrator\Documents\GitHub\detection
# 或你的实际路径，如 C:\detection

New-Item -ItemType Directory -Force -Path data\uploads, data\exports | Out-Null

# ★ WinServer 2019 请优先用带连字符的命令：
docker-compose up -d --build

# 仅当「docker compose version」成功时才用：
# docker compose up -d --build
```

或运行脚本（自动选择 compose / docker-compose）：

```powershell
.\scripts\deploy-windows.ps1
```

首次构建会下载基础镜像并安装 ODBC 18，约数分钟。

### 2. 查看状态

```powershell
docker-compose ps
docker-compose logs -f api
# 若用的是插件版则改为: docker compose ps / logs
```

浏览器访问：

| 地址 | 说明 |
|------|------|
| `http://服务器IP:8080` | 前端页面 |
| `http://服务器IP:8000/docs` | API 文档 |
| `http://服务器IP:8000/api/health` | 健康检查，应返回 `{"ok":true}` |

### 3. 防火墙

```powershell
New-NetFirewallRule -DisplayName "Detection Web 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
# 若外网不需要直接访问 API，可不开放 8000
New-NetFirewallRule -DisplayName "Detection API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

### 4. 常用运维

```powershell
cd C:\detection   # 或你的项目路径
docker-compose up -d --build
docker-compose restart
docker-compose down
docker-compose logs --tail=100 api
# 插件版把 docker-compose 换成 docker compose 即可
```

### 5. 连不上 SQL Server 时排查

1. 宿主机用 SSMS 能连 `127.0.0.1` / 实例名  
2. `backend\.env` 里主机是 `host.docker.internal`（不是 `127.0.0.1`）  
3. SQL 启用 TCP，端口 1433  
4. 容器内测试（可选）：

```powershell
docker-compose exec api python -c "from app.db import engine; print(engine.connect())"
```

5. 若 `host.docker.internal` 无效：在 `docker-compose.yml` 的 `api.extra_hosts` 已配置；仍失败可把 `DATABASE_URL` 主机改成 **宿主机局域网 IP**（如 `192.168.x.x`）。

### 6. 开机自启

Docker 服务设为自动启动后，`restart: unless-stopped` 会在 Docker 启动后拉起容器。

```powershell
# 确保 Docker 服务自动启动（服务名因安装方式而异，常见 com.docker.service）
Get-Service *docker*
```

---

## 三、方案 B：无 Docker 原生部署（WinServer 推荐）

适合：`no matching manifest for windows...`、或没有 Linux 容器。

### 0. 一键脚本（最简单）

1. 安装：
   - [Python 3.11+](https://www.python.org/downloads/windows/)（勾选 **Add python.exe to PATH**）
   - [Node.js 20 LTS](https://nodejs.org/)（仅第一次构建前端需要）
   - 使用 SQL Server 时再装 [ODBC Driver 18](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)

2. 在项目根目录 PowerShell：

```powershell
cd C:\Users\Administrator\Documents\GitHub\detection

# 可选：先只跑通，用 SQLite（不配 SQL Server）
# 脚本会生成 backend\.env，可把 DATABASE_URL 改成:
# DATABASE_URL=sqlite:///C:/Users/Administrator/Documents/GitHub/detection/data/detection.db

.\scripts\setup-windows-native.ps1
.\scripts\run-windows.ps1
```

浏览器打开：

- 页面：`http://服务器IP:8000`
- 健康：`http://127.0.0.1:8000/api/health`

`run-windows.ps1` 会让 **同一个 8000 端口** 同时提供 API 和前端（无需 IIS）。

防火墙：

```powershell
New-NetFirewallRule -DisplayName "Detection 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

### 1. 手动安装运行时（不用脚本时）

- Python 3.11+（勾选 Add to PATH）  
- Node.js 20+ LTS  
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)  

### 2. 后端

```powershell
cd C:\Users\Administrator\Documents\GitHub\detection\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pyodbc
copy .env.example .env
# 编辑 .env：DATABASE_URL 主机用 127.0.0.1（不是 host.docker.internal）
notepad .env
```

```env
DATABASE_URL=mssql+pyodbc://detection_app:密码@127.0.0.1/detection?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=dsv4f
```

试跑：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://127.0.0.1:8000/api/health`。

### 3. 前端构建

```powershell
cd C:\Users\Administrator\Documents\GitHub\detection\frontend
npm install
npm run build
```

产物在 `frontend\dist`。

**简单做法**：用 `.\scripts\run-windows.ps1`（API+静态一体）。

**IIS 做法**：网站指向 `frontend\dist`，并做 `/api` 反向代理到 `http://127.0.0.1:8000`。

#### IIS 要点

1. 安装：IIS + URL Rewrite + Application Request Routing (ARR)  
2. 网站物理路径：`C:\detection\frontend\dist`  
3. `web.config` 示例（放在 dist 根目录）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="API" stopProcessing="true">
          <match url="^api/(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8000/api/{R:1}" />
        </rule>
        <rule name="SPA" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="/index.html" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="104857600" />
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
```

ARR 需启用「反向代理」。上传大文件时注意 `maxAllowedContentLength`（上例 100MB）。

### 4. 后端做成 Windows 服务（NSSM）

1. 下载 [NSSM](https://nssm.cc/download)  
2. 管理员 PowerShell：

```powershell
nssm install DetectionAPI "C:\detection\backend\.venv\Scripts\uvicorn.exe" "app.main:app --host 127.0.0.1 --port 8000"
nssm set DetectionAPI AppDirectory "C:\detection\backend"
nssm set DetectionAPI AppEnvironmentExtra "PYTHONPATH=C:\detection\backend"
nssm start DetectionAPI
```

---

## 四、验证清单

1. `GET /api/health` → `{"ok":true}`  
2. 打开前端 → 新建项目 → 上传 `方案\客户方案` 中一个 docx  
3. 点「AI 解析」（未配 Key 时为启发式）  
4. 保存校对 → 导出 Word 能下载  

---

## 五、目录与端口

```
C:\detection\
  backend\          API + 模板
  frontend\         源码；Docker 内构建
  data\uploads\     上传原件（需备份）
  data\exports\     导出 Word（需备份）
  docker-compose.yml
  backend\.env      密钥，勿提交 Git
```

| 端口 | 用途 |
|------|------|
| 8080 | 用户访问前端（Docker） |
| 8000 | API（可只内网） |
| 1433 | SQL Server |

---

## 六、备份建议

- 数据库：定期备份 SQL Server 库 `detection`  
- 文件：备份 `data\uploads`、`data\exports`  
- 配置：备份 `backend\.env`（离线安全保存）  

---

## 七、更新版本

```powershell
cd C:\detection
git pull
docker-compose up -d --build
# 或原生：更新代码后重启 DetectionAPI，重新 npm run build 并覆盖 IIS 站点
```
