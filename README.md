# 环境监测方案管理系统

将客户发来的各式方案（docx / xlsx / pdf / doc 等）解析为结构化数据，人工校对后按 **基础监测方案** 或 **年度检测方案** 模板导出 Word。

## 功能

1. 上传客户方案附件  
2. AI（`dsv4f`，OpenAI 兼容）抽取监测点位 / 因子 / 频次  
3. 页面校对并入库  
4. 导出对应 Word 模板  

未配置 `LLM_API_KEY` 时会使用本地启发式解析（适合联调导出）。

## 技术栈

- 后端：Python FastAPI + SQLAlchemy  
- 前端：Vue 3 + Element Plus  
- 数据库：开发默认 SQLite；生产使用 **SQL Server 新建库 `detection`**  
- LLM：`LLM_MODEL=dsv4f`  

## 本地开发

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # 填写 LLM_API_KEY 等
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 ，API 经 Vite 代理到 8000。

### SQL Server（生产）

1. 在 SQL Server 上执行：`CREATE DATABASE detection;`  
2. 安装 [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)  
3. 安装 `pip install pyodbc`  
4. `.env` 中设置：

```env
DATABASE_URL=mssql+pyodbc://用户:密码@主机/detection?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
LLM_BASE_URL=https://你的网关/v1
LLM_API_KEY=你的密钥
LLM_MODEL=dsv4f
```

首次启动会自动建表。

## Docker（Windows 服务器可用）

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env
docker compose up -d --build
```

- 前端：http://服务器:8080  
- API：http://服务器:8000/docs  

SQL Server 在宿主机时，`DATABASE_URL` 主机可用 `host.docker.internal`（需在 compose 中取消 `extra_hosts` 注释）。

## 目录

```
detection/
  方案/                 # 原始客户方案与模板样例
  backend/              # FastAPI
  frontend/             # Vue
  data/uploads|exports  # 运行时文件
  docker-compose.yml
```

## 使用流程

1. 新建项目（可选填名称/类型）  
2. 上传客户方案  
3. 点击 **AI 解析**  
4. 校对监测条目与基本信息 → **保存校对**  
5. **导出 Word** 下载填充后的模板  

## API 摘要

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/projects | 列表 |
| POST | /api/projects | 创建 |
| POST | /api/projects/{id}/files | 上传 |
| POST | /api/projects/{id}/parse | 解析 |
| PUT | /api/projects/{id}/items | 保存条目 |
| POST | /api/projects/{id}/export | 导出 |
| GET | /api/exports/{id}/download | 下载 |
