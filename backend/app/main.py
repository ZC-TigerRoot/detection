import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

# 原生 Windows 部署：uvicorn 同时托管 frontend/dist
_static = os.environ.get("STATIC_DIR", "").strip()
if _static:
    static_path = Path(_static)
    if static_path.is_dir() and (static_path / "index.html").exists():
        assets = static_path / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # API 已由 router 处理；其余走前端 SPA
            # 防止路径穿越：规范化后检查是否在 static_path 内
            candidate = (static_path / full_path).resolve()
            if not candidate.is_relative_to(static_path):
                return FileResponse(static_path / "index.html")
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_path / "index.html")
