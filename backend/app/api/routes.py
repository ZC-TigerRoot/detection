from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.db import SessionLocal, get_db
from app.models import ExportRecord, MonitoringItem, Project, ProjectFile
from app.schemas import (
    ExportRequest,
    ExportResult,
    ItemsReplace,
    ParseResult,
    ProjectCreate,
    ProjectDetail,
    ProjectFileOut,
    ProjectSummary,
    ProjectUpdate,
    ExportRecordOut,
    MonitoringItemOut,
    TypeDetectResult,
    LLMSettingsOut,
    LLMSettingsUpdate,
    LLMTestResult,
)
from app.services.extract import combine_project_texts, extract_file_with_status
from app.services.export_docx import export_project_docx, safe_filename
from app.services.llm_parse import normalize_parsed, parse_with_llm, stream_parse_with_llm
from app.services.detect import detect_project_type

# 允许上传的扩展名白名单
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".docx", ".doc", ".xlsx", ".xlsm", ".pdf", ".txt", ".md", ".csv",
     ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
)
# 单文件最大字节数（50 MB）
_MAX_FILE_SIZE = 50 * 1024 * 1024

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _project_summary(db: Session, p: Project) -> ProjectSummary:
    item_count = db.scalar(
        select(func.count()).select_from(MonitoringItem).where(MonitoringItem.project_id == p.id)
    ) or 0
    file_count = db.scalar(
        select(func.count()).select_from(ProjectFile).where(ProjectFile.project_id == p.id)
    ) or 0
    return ProjectSummary(
        id=p.id,
        name=p.name,
        client_name=p.client_name,
        project_type=p.project_type,
        status=p.status,
        year=p.year,
        item_count=item_count,
        file_count=file_count,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _file_extract_status(f: ProjectFile) -> str:
    if f.extract_status:
        return f.extract_status
    # 兼容旧数据：按 extracted_text 内容推断
    text = f.extracted_text or ""
    if not text or text.startswith("["):
        return "failed" if text.startswith("[解析失败") else "no_text"
    return "success"


def _to_detail(p: Project) -> ProjectDetail:
    return ProjectDetail(
        id=p.id,
        name=p.name,
        client_name=p.client_name,
        address=p.address,
        contact=p.contact,
        phone=p.phone,
        project_type=p.project_type,
        status=p.status,
        year=p.year,
        longitude=p.longitude or "",
        latitude=p.latitude or "",
        overview=p.overview or "",
        remark=p.remark or "",
        parse_error=p.parse_error or "",
        created_at=p.created_at,
        updated_at=p.updated_at,
        files=[
            ProjectFileOut(
                id=f.id,
                original_name=f.original_name,
                file_ext=f.file_ext,
                size=f.size,
                content_type=f.content_type,
                created_at=f.created_at,
                has_text=bool(f.extracted_text and not f.extracted_text.startswith("[")),
                extract_status=_file_extract_status(f),
                extract_error=f.extract_error or "",
            )
            for f in p.files
        ],
        items=[MonitoringItemOut.model_validate(i) for i in p.items],
        exports=[ExportRecordOut.model_validate(e) for e in p.exports],
    )


def _get_project(db: Session, project_id: int, load_all: bool = False) -> Project:
    stmt = select(Project).where(Project.id == project_id)
    if load_all:
        stmt = stmt.options(
            selectinload(Project.files),
            selectinload(Project.items),
            selectinload(Project.exports),
        )
    p = db.scalar(stmt)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(
    q: str | None = Query(None),
    project_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Project).order_by(Project.id.desc())
    projects = list(db.scalars(stmt).all())
    result = [_project_summary(db, p) for p in projects]
    if q:
        ql = q.lower()
        result = [
            r
            for r in result
            if ql in (r.name or "").lower()
            or ql in (r.client_name or "").lower()
        ]
    if project_type:
        result = [r for r in result if r.project_type == project_type]
    if status:
        result = [r for r in result if r.status == status]
    return result


@router.post("/projects", response_model=ProjectDetail)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(
        name=body.name,
        client_name=body.client_name,
        address=body.address,
        contact=body.contact,
        phone=body.phone,
        project_type=body.project_type,
        year=body.year,
        longitude=body.longitude,
        latitude=body.latitude,
        overview=body.overview,
        remark=body.remark,
        status="draft",
    )
    db.add(p)
    db.commit()
    p = _get_project(db, p.id, load_all=True)
    return _to_detail(p)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = _get_project(db, project_id, load_all=True)
    return _to_detail(p)


@router.put("/projects/{project_id}", response_model=ProjectDetail)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = _get_project(db, project_id, load_all=True)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    p = _get_project(db, project_id, load_all=True)
    return _to_detail(p)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    p = _get_project(db, project_id, load_all=True)
    # remove files on disk
    proj_dir = settings.upload_dir / str(project_id)
    if proj_dir.exists():
        shutil.rmtree(proj_dir, ignore_errors=True)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/files", response_model=ProjectDetail)
async def upload_files(
    project_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    p = _get_project(db, project_id)
    dest_dir = settings.upload_dir / str(project_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for up in files:
        raw_name = up.filename or "upload.bin"
        ext = Path(raw_name).suffix.lower()

        # 扩展名白名单校验
        if ext not in _ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"不支持的文件类型: {ext}，允许类型: {', '.join(sorted(_ALLOWED_EXTENSIONS))}")

        stored = f"{uuid.uuid4().hex}{ext}"
        path = dest_dir / stored

        # 分块写磁盘，同时检查文件大小上限，避免一次性读进内存
        size = 0
        chunk_size = 1024 * 1024  # 1 MB per chunk
        with path.open("wb") as fp:
            while True:
                chunk = await up.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_FILE_SIZE:
                    fp.close()
                    path.unlink(missing_ok=True)
                    raise HTTPException(400, f"文件 {raw_name!r} 超过大小限制 {_MAX_FILE_SIZE // 1024 // 1024} MB")
                fp.write(chunk)

        # 文件提取是阻塞操作（OCR/PDF解析），移到线程池避免堵塞事件循环
        text, extract_status, extract_error = await run_in_threadpool(extract_file_with_status, path)
        pf = ProjectFile(
            project_id=project_id,
            original_name=raw_name,
            stored_path=str(path),
            content_type=up.content_type or "",
            file_ext=ext,
            size=size,
            extracted_text=text,
            extract_status=extract_status,
            extract_error=extract_error,
        )
        db.add(pf)

    # 上传后自动识别应套用 单次(基础) 还是 年度 模板
    db.flush()
    texts = [
        f"===== {f.original_name} =====\n{f.extracted_text or ''}" for f in p.files
    ]
    det = detect_project_type("\n\n".join(texts)[:20000])
    p.project_type = det["project_type"]

    if p.status == "draft":
        p.status = "reviewing"
    db.commit()
    p = _get_project(db, project_id, load_all=True)
    return _to_detail(p)


@router.post("/projects/{project_id}/detect-type", response_model=TypeDetectResult)
def detect_type(project_id: int, db: Session = Depends(get_db)):
    """直接识别该方案应套用 单次(基础) 还是 年度 模板，无需 LLM 解析。"""
    p = _get_project(db, project_id)
    if not p.files:
        raise HTTPException(400, "请先上传方案文件")
    parts = [
        f"===== {f.original_name} =====\n{f.extracted_text or ''}" for f in p.files
    ]
    combined = "\n\n".join(parts)
    if not combined.strip():
        raise HTTPException(400, "未能从文件中提取到文本")
    return detect_project_type(combined[:20000])


def _apply_parsed(db: Session, p: Project, data: dict) -> None:
    """把 normalize_parsed 的结果写入项目与监测条目（不提交事务）。"""

    def _merge(field: str, value: str | None, *, overwrite: bool = False) -> None:
        if value is None:
            return
        value = str(value).strip()
        if not value or value.startswith("====="):
            return
        cur = getattr(p, field) or ""
        if overwrite or not cur or cur in {"测试项目", "未命名项目"}:
            setattr(p, field, value)

    _merge("name", data.get("name"), overwrite=True)
    _merge("client_name", data.get("client_name"))
    _merge("address", data.get("address"))
    _merge("contact", data.get("contact"))
    _merge("phone", data.get("phone"))
    if data.get("project_type") in {"basic", "annual"}:
        # 仅在用户未明确改过、或仍是默认时更新；这里简单采用解析结果
        p.project_type = data["project_type"]
    if data.get("year"):
        p.year = data["year"]
    _merge("longitude", data.get("longitude"))
    _merge("latitude", data.get("latitude"))
    _merge("overview", data.get("overview"))
    if data.get("remark"):
        # 解析备注追加感不强，直接有则写
        if not p.remark or "启发式" in (data.get("remark") or ""):
            p.remark = data["remark"]

    p.parse_raw = data.get("raw") or ""
    p.parse_error = ""

    # replace items
    for old in list(p.items):
        db.delete(old)
    db.flush()

    for it in data["items"]:
        db.add(
            MonitoringItem(
                project_id=p.id,
                category=it["category"],
                outlet_code=it["outlet_code"],
                outlet_name=it["outlet_name"],
                point_location=it["point_location"],
                factors=it["factors"],
                sample_freq=it["sample_freq"],
                period_freq=it["period_freq"],
                monitor_days=it["monitor_days"],
                samples_per_day=it["samples_per_day"],
                annual_times=it["annual_times"],
                months_plan=it["months_plan"],
                standard_text=it["standard_text"],
                remark=it["remark"],
                sort_order=it["sort_order"],
            )
        )

    p.status = "reviewing"


@router.post("/projects/{project_id}/parse", response_model=ParseResult)
async def parse_project(
    project_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    p = _get_project(db, project_id, load_all=True)
    if not p.files:
        raise HTTPException(400, "请先上传方案文件")

    file_texts = [(f.original_name, f.extracted_text or "") for f in p.files]
    combined = combine_project_texts(file_texts, settings.llm_max_input_chars)
    if not combined.strip():
        raise HTTPException(400, "未能从文件中提取到文本")

    try:
        raw = await parse_with_llm(settings, combined)
        data = normalize_parsed(raw)
    except Exception as exc:  # noqa: BLE001
        logger.exception("项目 %s 解析失败", project_id)
        p.status = "parse_failed"
        p.parse_error = "解析失败，请查看服务端日志"
        db.commit()
        raise HTTPException(500, "解析失败，请稍后重试") from exc

    _apply_parsed(db, p, data)
    db.commit()
    return ParseResult(
        project_id=p.id,
        status=p.status,
        item_count=len(data["items"]),
        message="解析完成，请校对" if settings.llm_api_key else "已用本地启发式解析（未配置 LLM_API_KEY）",
    )


@router.post("/projects/{project_id}/parse-stream")
async def parse_project_stream(
    project_id: int,
    settings: Settings = Depends(get_settings),
):
    """
    流式 SSE 解析端点。返回 text/event-stream，实时展示解析进度和 AI 思考过程。
    前端用 EventSource 或 fetch + ReadableStream 消费。
    """

    async def event_generator():
        db = SessionLocal()
        try:
            p = db.scalar(
                select(Project)
                .where(Project.id == project_id)
                .options(selectinload(Project.files), selectinload(Project.items))
            )
            if not p:
                yield f"event: error\ndata: {json.dumps({'message': '项目不存在'}, ensure_ascii=False)}\n\n"
                return

            if not p.files:
                yield f"event: error\ndata: {json.dumps({'message': '请先上传方案文件'}, ensure_ascii=False)}\n\n"
                return

            file_texts = [(f.original_name, f.extracted_text or "") for f in p.files]
            combined = combine_project_texts(file_texts, settings.llm_max_input_chars)
            if not combined.strip():
                yield f"event: error\ndata: {json.dumps({'message': '未能从文件中提取到文本'}, ensure_ascii=False)}\n\n"
                return

            # 流式解析，先收集所有事件
            done_event = None
            async for event in stream_parse_with_llm(settings, combined):
                event_type = event.get("type", "message")
                
                if event_type == "done":
                    # 先不发送 done，而是保存到数据库
                    done_event = event
                    break
                elif event_type == "error":
                    # 详细原因只落服务端日志，客户端只收通用提示
                    logger.error(
                        "项目 %s 流式解析失败: %s", project_id, event.get("message", "未知错误")
                    )
                    p.status = "parse_failed"
                    p.parse_error = "解析失败，请查看服务端日志"
                    db.commit()
                    payload = json.dumps(
                        {"message": "解析失败，请查看服务端日志"}, ensure_ascii=False
                    )
                    yield f"event: error\ndata: {payload}\n\n"
                    return
                else:
                    # stage, delta, thought 事件立即转发
                    event_copy = dict(event)
                    event_copy.pop("type", None)
                    payload = json.dumps(event_copy, ensure_ascii=False)
                    yield f"event: {event_type}\ndata: {payload}\n\n"

            # 解析完成，保存到数据库
            if done_event:
                data = done_event["data"]
                _apply_parsed(db, p, data)
                db.commit()
                
                # 数据库保存完成后才发送 done 事件
                done_payload: dict = {"item_count": len(data["items"])}
                if done_event.get("usage"):
                    done_payload["usage"] = done_event["usage"]
                yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception:  # noqa: BLE001
            logger.exception("SSE 解析项目 %s 失败", project_id)
            db.rollback()
            yield (
                "event: error\ndata: "
                f"{json.dumps({'message': '解析失败，请查看服务端日志'}, ensure_ascii=False)}\n\n"
            )
        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.put("/projects/{project_id}/items", response_model=ProjectDetail)
def replace_items(project_id: int, body: ItemsReplace, db: Session = Depends(get_db)):
    p = _get_project(db, project_id, load_all=True)
    for old in list(p.items):
        db.delete(old)
    db.flush()
    for i, it in enumerate(body.items):
        db.add(
            MonitoringItem(
                project_id=project_id,
                category=it.category,
                outlet_code=it.outlet_code,
                outlet_name=it.outlet_name,
                point_location=it.point_location,
                factors=it.factors,
                sample_freq=it.sample_freq,
                period_freq=it.period_freq,
                monitor_days=it.monitor_days,
                samples_per_day=it.samples_per_day,
                annual_times=it.annual_times,
                months_plan=it.months_plan,
                standard_text=it.standard_text,
                remark=it.remark,
                sort_order=it.sort_order if it.sort_order else i,
            )
        )
    if body.status:
        p.status = body.status
    db.commit()
    p = _get_project(db, project_id, load_all=True)
    return _to_detail(p)


@router.post("/projects/{project_id}/export", response_model=ExportResult)
def export_project(
    project_id: int,
    body: ExportRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    p = _get_project(db, project_id, load_all=True)
    export_type = (body.export_type if body and body.export_type else None) or p.project_type
    if export_type not in {"basic", "annual"}:
        raise HTTPException(400, "export_type 必须是 basic 或 annual")

    tpl_name = (
        settings.basic_template_name if export_type == "basic" else settings.annual_template_name
    )
    template_path = settings.template_dir / tpl_name
    if not template_path.exists():
        raise HTTPException(500, f"模板不存在: {tpl_name}")

    base = safe_filename(p.name or p.client_name or f"project_{p.id}")
    file_name = f"{base}_{export_type}_{uuid.uuid4().hex[:8]}.docx"
    out_path = settings.export_dir / str(project_id) / file_name

    export_project_docx(p, list(p.items), template_path, out_path, export_type)

    rec = ExportRecord(
        project_id=p.id,
        export_type=export_type,
        file_name=file_name,
        stored_path=str(out_path),
    )
    db.add(rec)
    p.status = "exported"
    db.commit()
    db.refresh(rec)

    return ExportResult(
        id=rec.id,
        file_name=file_name,
        export_type=export_type,
        download_url=f"/api/exports/{rec.id}/download",
    )


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, db: Session = Depends(get_db)):
    rec = db.get(ExportRecord, export_id)
    if not rec:
        raise HTTPException(404, "导出记录不存在")
    # 校验关联项目是否存在（防止孤立记录或删除后残留）
    # 内网无认证场景下已做数据完整性检查，如有认证可加用户归属校验
    project = db.get(Project, rec.project_id)
    if not project:
        raise HTTPException(404, "关联项目不存在")
    path = Path(rec.stored_path)
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(
        path,
        filename=rec.file_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/projects/{project_id}/files/{file_id}/text")
def get_file_text(project_id: int, file_id: int, db: Session = Depends(get_db)):
    f = db.get(ProjectFile, file_id)
    if not f or f.project_id != project_id:
        raise HTTPException(404, "文件不存在")
    return {"id": f.id, "name": f.original_name, "text": f.extracted_text or ""}


def _mask_api_key(api_key: str) -> str:
    """API Key 掩码，避免明文回传前端。"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}***{api_key[-4:]}"


def _llm_settings_out(settings: Settings) -> LLMSettingsOut:
    return LLMSettingsOut(
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        llm_timeout=settings.llm_timeout,
        llm_max_input_chars=settings.llm_max_input_chars,
        api_key_masked=_mask_api_key(settings.llm_api_key),
        api_key_set=bool(settings.llm_api_key),
    )


def _write_env(env_file: Path, updates: dict[str, str]) -> None:
    """就地更新 .env 的 KEY=VALUE，保留注释与顺序，缺失的键追加到末尾。"""
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")

    # Docker 生产环境 .env 是单文件 bind mount，tmp+rename 会报"设备忙"，
    # 只能直接写内容（文件很小，写入中断风险可忽略）
    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@router.get("/settings/llm", response_model=LLMSettingsOut)
def get_llm_settings(settings: Settings = Depends(get_settings)):
    """获取当前 LLM 配置（API Key 只返回掩码）。"""
    return _llm_settings_out(settings)


@router.put("/settings/llm", response_model=LLMSettingsOut)
def update_llm_settings(body: LLMSettingsUpdate):
    """更新 LLM 配置，持久化到 backend/.env 并刷新配置缓存。"""
    env_file = Path(Settings.model_config["env_file"])
    if not env_file.parent.is_dir():
        raise HTTPException(500, "配置目录不存在，无法保存设置")

    updates: dict[str, str] = {}
    if body.llm_base_url is not None:
        url = body.llm_base_url.strip()
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(400, "Base URL 必须以 http:// 或 https:// 开头")
        updates["LLM_BASE_URL"] = url
    if body.llm_model is not None:
        updates["LLM_MODEL"] = body.llm_model.strip()
    if body.llm_timeout is not None:
        updates["LLM_TIMEOUT"] = str(body.llm_timeout)
    if body.llm_max_input_chars is not None:
        updates["LLM_MAX_INPUT_CHARS"] = str(body.llm_max_input_chars)

    if body.clear_api_key:
        updates["LLM_API_KEY"] = ""
    elif body.llm_api_key:
        key = body.llm_api_key.strip()
        # 前端回显的是掩码，收到掩码说明用户没改，跳过
        if "***" not in key:
            updates["LLM_API_KEY"] = key

    if not updates:
        return _llm_settings_out(get_settings())

    try:
        _write_env(env_file, updates)
    except OSError as exc:
        logger.exception("写入 .env 失败")
        raise HTTPException(500, "保存设置失败，请检查服务端文件权限") from exc

    # .env 已变更，清缓存让后续请求读到新值
    get_settings.cache_clear()
    return _llm_settings_out(get_settings())


@router.post("/settings/llm/test", response_model=LLMTestResult)
async def test_llm_connection(settings: Settings = Depends(get_settings)):
    """用当前已保存的配置向 LLM 发一个最小请求，验证连通性。"""
    if not settings.llm_api_key:
        return LLMTestResult(ok=False, message="未配置 API Key，解析将回退到本地启发式")

    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 4,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("LLM 连通性测试失败: %s", exc)
        return LLMTestResult(
            ok=False,
            message=f"接口返回 {exc.response.status_code}，请检查 Base URL / API Key / 模型名",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 连通性测试失败: %s", exc)
        return LLMTestResult(
            ok=False,
            message="连接失败，请检查网络与 Base URL",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    return LLMTestResult(
        ok=True,
        message="连接成功",
        model=str(body.get("model") or settings.llm_model),
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
