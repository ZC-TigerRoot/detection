from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

elif "mssql" in settings.database_url:

    @event.listens_for(engine, "connect")
    def set_mssql_encoding(dbapi_connection, connection_record):
        # 避免 VARCHAR/CHAR 路径用系统代码页把中文变成 ?
        try:
            import pyodbc

            dbapi_connection.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
            dbapi_connection.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16le")
            dbapi_connection.setencoding(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 已有 SQL Server 库若仍是 varchar/text，create_all 不会改类型，启动时自动升级
_MSSQL_UNICODE_ALTERS = [
    ("projects", "name", "NVARCHAR(255) NOT NULL"),
    ("projects", "client_name", "NVARCHAR(255) NOT NULL"),
    ("projects", "address", "NVARCHAR(500) NOT NULL"),
    ("projects", "contact", "NVARCHAR(100) NOT NULL"),
    ("projects", "phone", "NVARCHAR(50) NOT NULL"),
    ("projects", "project_type", "NVARCHAR(20) NOT NULL"),
    ("projects", "status", "NVARCHAR(20) NOT NULL"),
    ("projects", "year", "NVARCHAR(20) NULL"),
    ("projects", "longitude", "NVARCHAR(50) NOT NULL"),
    ("projects", "latitude", "NVARCHAR(50) NOT NULL"),
    ("projects", "overview", "NVARCHAR(MAX) NOT NULL"),
    ("projects", "remark", "NVARCHAR(MAX) NOT NULL"),
    ("projects", "parse_raw", "NVARCHAR(MAX) NOT NULL"),
    ("projects", "parse_error", "NVARCHAR(MAX) NOT NULL"),
    ("project_files", "original_name", "NVARCHAR(500) NOT NULL"),
    ("project_files", "stored_path", "NVARCHAR(1000) NOT NULL"),
    ("project_files", "content_type", "NVARCHAR(100) NOT NULL"),
    ("project_files", "file_ext", "NVARCHAR(20) NOT NULL"),
    ("project_files", "extracted_text", "NVARCHAR(MAX) NOT NULL"),
    ("monitoring_items", "category", "NVARCHAR(100) NOT NULL"),
    ("monitoring_items", "outlet_code", "NVARCHAR(100) NOT NULL"),
    ("monitoring_items", "outlet_name", "NVARCHAR(255) NOT NULL"),
    ("monitoring_items", "point_location", "NVARCHAR(255) NOT NULL"),
    ("monitoring_items", "factors", "NVARCHAR(MAX) NOT NULL"),
    ("monitoring_items", "sample_freq", "NVARCHAR(255) NOT NULL"),
    ("monitoring_items", "period_freq", "NVARCHAR(100) NOT NULL"),
    ("monitoring_items", "monitor_days", "NVARCHAR(50) NOT NULL"),
    ("monitoring_items", "samples_per_day", "NVARCHAR(50) NOT NULL"),
    ("monitoring_items", "annual_times", "NVARCHAR(100) NOT NULL"),
    ("monitoring_items", "months_plan", "NVARCHAR(MAX) NOT NULL"),
    ("monitoring_items", "standard_text", "NVARCHAR(MAX) NOT NULL"),
    ("monitoring_items", "remark", "NVARCHAR(MAX) NOT NULL"),
    ("export_records", "export_type", "NVARCHAR(20) NOT NULL"),
    ("export_records", "file_name", "NVARCHAR(500) NOT NULL"),
    ("export_records", "stored_path", "NVARCHAR(1000) NOT NULL"),
]


def _migrate_mssql_unicode() -> None:
    """把已有 varchar/text 列改为 nvarchar，修复中文写入变成 ? 的问题。"""
    with engine.begin() as conn:
        for table, column, type_sql in _MSSQL_UNICODE_ALTERS:
            row = conn.execute(
                text(
                    """
                    SELECT t.name AS type_name
                    FROM sys.columns c
                    JOIN sys.types t ON c.user_type_id = t.user_type_id
                    JOIN sys.tables tb ON c.object_id = tb.object_id
                    WHERE tb.name = :table AND c.name = :column
                    """
                ),
                {"table": table, "column": column},
            ).fetchone()
            if not row:
                continue
            type_name = (row[0] or "").lower()
            if type_name in {"nvarchar", "nchar", "ntext"}:
                continue
            if type_name not in {"varchar", "char", "text"}:
                continue
            conn.execute(
                text(f"ALTER TABLE [{table}] ALTER COLUMN [{column}] {type_sql}")
            )


def _ensure_project_file_columns() -> None:
    """为已有数据库补 project_files 新增列（create_all 不会为已存在的表加列）。"""
    with engine.begin() as conn:
        if settings.database_url.startswith("sqlite"):
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(project_files)")).fetchall()
            }
            if "extract_status" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE project_files "
                        "ADD COLUMN extract_status VARCHAR(20) NOT NULL DEFAULT ''"
                    )
                )
            if "extract_error" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE project_files "
                        "ADD COLUMN extract_error TEXT NOT NULL DEFAULT ''"
                    )
                )
        elif "mssql" in settings.database_url:
            for col, type_sql in (
                ("extract_status", "NVARCHAR(20) NOT NULL DEFAULT ''"),
                ("extract_error", "NVARCHAR(MAX) NOT NULL DEFAULT ''"),
            ):
                row = conn.execute(
                    text(
                        """
                        SELECT 1 FROM sys.columns c
                        JOIN sys.tables tb ON c.object_id = tb.object_id
                        WHERE tb.name = 'project_files' AND c.name = :name
                        """
                    ),
                    {"name": col},
                ).fetchone()
                if not row:
                    conn.execute(
                        text(f"ALTER TABLE project_files ADD {col} {type_sql}")
                    )


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        _ensure_project_file_columns()
    except Exception as exc:  # noqa: BLE001
        # 不阻断启动；日志由 uvicorn 打印
        print(f"[db] project_files 新增列迁移跳过/失败: {exc}")
    if "mssql" in settings.database_url:
        try:
            _migrate_mssql_unicode()
        except Exception as exc:  # noqa: BLE001
            # 不阻断启动；日志由 uvicorn 打印
            print(f"[db] MSSQL Unicode 列迁移跳过/失败: {exc}")
