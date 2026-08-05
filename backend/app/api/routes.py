from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db import get_db
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
)
from app.services.extract import combine_project_texts, extract_file_with_status
from app.services.export_docx import export_project_docx, safe_filename
from app.services.llm_parse import normalize_parsed, parse_with_llm
from app.services.detect import detect_project_type

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
        stored = f"{uuid.uuid4().hex}{ext}"
        path = dest_dir / stored
        content = await up.read()
        path.write_bytes(content)
        text, extract_status, extract_error = extract_file_with_status(path)
        pf = ProjectFile(
            project_id=project_id,
            original_name=raw_name,
            stored_path=str(path),
            content_type=up.content_type or "",
            file_ext=ext,
            size=len(content),
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
        p.status = "parse_failed"
        p.parse_error = str(exc)
        db.commit()
        raise HTTPException(500, f"解析失败: {exc}") from exc

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
    db.commit()
    return ParseResult(
        project_id=p.id,
        status=p.status,
        item_count=len(data["items"]),
        message="解析完成，请校对" if settings.llm_api_key else "已用本地启发式解析（未配置 LLM_API_KEY）",
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
