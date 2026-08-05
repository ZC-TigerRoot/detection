from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ProjectType = Literal["basic", "annual"]
ProjectStatus = Literal["draft", "reviewing", "confirmed", "exported", "parse_failed"]


class MonitoringItemIn(BaseModel):
    id: Optional[int] = None
    category: str = ""
    outlet_code: str = ""
    outlet_name: str = ""
    point_location: str = ""
    factors: str = ""
    sample_freq: str = ""
    period_freq: str = ""
    monitor_days: str = ""
    samples_per_day: str = ""
    annual_times: str = ""
    months_plan: str = ""
    standard_text: str = ""
    remark: str = ""
    sort_order: int = 0


class MonitoringItemOut(MonitoringItemIn):
    id: int
    project_id: int

    model_config = {"from_attributes": True}


class ProjectFileOut(BaseModel):
    id: int
    original_name: str
    file_ext: str
    size: int
    content_type: str
    created_at: Optional[datetime] = None
    has_text: bool = False

    model_config = {"from_attributes": True}


class ExportRecordOut(BaseModel):
    id: int
    export_type: str
    file_name: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = ""
    client_name: str = ""
    address: str = ""
    contact: str = ""
    phone: str = ""
    project_type: ProjectType = "annual"
    year: Optional[str] = None
    longitude: str = ""
    latitude: str = ""
    overview: str = ""
    remark: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    project_type: Optional[ProjectType] = None
    status: Optional[ProjectStatus] = None
    year: Optional[str] = None
    longitude: Optional[str] = None
    latitude: Optional[str] = None
    overview: Optional[str] = None
    remark: Optional[str] = None


class ProjectSummary(BaseModel):
    id: int
    name: str
    client_name: str
    project_type: str
    status: str
    year: Optional[str] = None
    item_count: int = 0
    file_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProjectDetail(BaseModel):
    id: int
    name: str
    client_name: str
    address: str
    contact: str
    phone: str
    project_type: str
    status: str
    year: Optional[str] = None
    longitude: str = ""
    latitude: str = ""
    overview: str = ""
    remark: str = ""
    parse_error: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    files: list[ProjectFileOut] = Field(default_factory=list)
    items: list[MonitoringItemOut] = Field(default_factory=list)
    exports: list[ExportRecordOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ItemsReplace(BaseModel):
    items: list[MonitoringItemIn]
    status: Optional[ProjectStatus] = "reviewing"


class ParseResult(BaseModel):
    project_id: int
    status: str
    item_count: int
    message: str = ""


class ExportRequest(BaseModel):
    export_type: Optional[ProjectType] = None


class TypeDetectResult(BaseModel):
    project_type: str
    label: str
    annual_score: int = 0
    basic_score: int = 0
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""


class ExportResult(BaseModel):
    id: int
    file_name: str
    export_type: str
    download_url: str
