from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    func,
)
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# SQL Server: NVARCHAR / NVARCHAR(max)；SQLite: 仍为 Unicode 文本
_Str50 = Unicode(50).with_variant(NVARCHAR(50), "mssql")
_Str20 = Unicode(20).with_variant(NVARCHAR(20), "mssql")
_Str100 = Unicode(100).with_variant(NVARCHAR(100), "mssql")
_Str255 = Unicode(255).with_variant(NVARCHAR(255), "mssql")
_Str500 = Unicode(500).with_variant(NVARCHAR(500), "mssql")
_Str1000 = Unicode(1000).with_variant(NVARCHAR(1000), "mssql")
_Text = UnicodeText().with_variant(NVARCHAR(None), "mssql")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(_Str255, default="")
    client_name: Mapped[str] = mapped_column(_Str255, default="")
    address: Mapped[str] = mapped_column(_Str500, default="")
    contact: Mapped[str] = mapped_column(_Str100, default="")
    phone: Mapped[str] = mapped_column(_Str50, default="")
    project_type: Mapped[str] = mapped_column(_Str20, default="annual")  # basic | annual
    status: Mapped[str] = mapped_column(_Str20, default="draft")
    year: Mapped[Optional[str]] = mapped_column(_Str20, nullable=True)
    longitude: Mapped[str] = mapped_column(_Str50, default="")
    latitude: Mapped[str] = mapped_column(_Str50, default="")
    overview: Mapped[str] = mapped_column(_Text, default="")
    remark: Mapped[str] = mapped_column(_Text, default="")
    parse_raw: Mapped[str] = mapped_column(_Text, default="")
    parse_error: Mapped[str] = mapped_column(_Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    files: Mapped[list[ProjectFile]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    items: Mapped[list[MonitoringItem]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="MonitoringItem.sort_order",
    )
    exports: Mapped[list[ExportRecord]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    original_name: Mapped[str] = mapped_column(_Str500)
    stored_path: Mapped[str] = mapped_column(_Str1000)
    content_type: Mapped[str] = mapped_column(_Str100, default="")
    file_ext: Mapped[str] = mapped_column(_Str20, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(_Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="files")


class MonitoringItem(Base):
    __tablename__ = "monitoring_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(_Str100, default="")
    outlet_code: Mapped[str] = mapped_column(_Str100, default="")
    outlet_name: Mapped[str] = mapped_column(_Str255, default="")
    point_location: Mapped[str] = mapped_column(_Str255, default="")
    factors: Mapped[str] = mapped_column(_Text, default="")
    sample_freq: Mapped[str] = mapped_column(_Str255, default="")
    period_freq: Mapped[str] = mapped_column(_Str100, default="")
    monitor_days: Mapped[str] = mapped_column(_Str50, default="")
    samples_per_day: Mapped[str] = mapped_column(_Str50, default="")
    annual_times: Mapped[str] = mapped_column(_Str100, default="")
    months_plan: Mapped[str] = mapped_column(_Text, default="")
    standard_text: Mapped[str] = mapped_column(_Text, default="")
    remark: Mapped[str] = mapped_column(_Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="items")


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    export_type: Mapped[str] = mapped_column(_Str20)
    file_name: Mapped[str] = mapped_column(_Str500)
    stored_path: Mapped[str] = mapped_column(_Str1000)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="exports")
