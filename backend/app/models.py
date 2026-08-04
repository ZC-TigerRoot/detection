from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    client_name: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    contact: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    project_type: Mapped[str] = mapped_column(String(20), default="annual")  # basic | annual
    status: Mapped[str] = mapped_column(String(20), default="draft")
    year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    longitude: Mapped[str] = mapped_column(String(50), default="")
    latitude: Mapped[str] = mapped_column(String(50), default="")
    overview: Mapped[str] = mapped_column(Text, default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    parse_raw: Mapped[str] = mapped_column(Text, default="")
    parse_error: Mapped[str] = mapped_column(Text, default="")
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
    original_name: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000))
    content_type: Mapped[str] = mapped_column(String(100), default="")
    file_ext: Mapped[str] = mapped_column(String(20), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="files")


class MonitoringItem(Base):
    __tablename__ = "monitoring_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(100), default="")
    outlet_code: Mapped[str] = mapped_column(String(100), default="")
    outlet_name: Mapped[str] = mapped_column(String(255), default="")
    point_location: Mapped[str] = mapped_column(String(255), default="")
    factors: Mapped[str] = mapped_column(Text, default="")
    sample_freq: Mapped[str] = mapped_column(String(255), default="")
    period_freq: Mapped[str] = mapped_column(String(100), default="")
    monitor_days: Mapped[str] = mapped_column(String(50), default="")
    samples_per_day: Mapped[str] = mapped_column(String(50), default="")
    annual_times: Mapped[str] = mapped_column(String(100), default="")
    months_plan: Mapped[str] = mapped_column(Text, default="")
    standard_text: Mapped[str] = mapped_column(Text, default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="items")


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    export_type: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="exports")
