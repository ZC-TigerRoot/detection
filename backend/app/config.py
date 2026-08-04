from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "环境监测方案管理系统"
    debug: bool = True

    # 默认 SQLite；生产改为 SQL Server，例:
    # mssql+pyodbc://user:pass@host/detection?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'detection.db'}"

    upload_dir: Path = ROOT_DIR / "data" / "uploads"
    export_dir: Path = ROOT_DIR / "data" / "exports"
    template_dir: Path = BASE_DIR / "templates"

    basic_template_name: str = "基础监测方案模板.docx"
    annual_template_name: str = "年度检测方案模板.docx"

    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "dsv4f"
    llm_timeout: float = 120.0
    llm_max_input_chars: int = 60000

    @field_validator("upload_dir", "export_dir", "template_dir", mode="before")
    @classmethod
    def _to_path(cls, v):
        return Path(v) if v else v


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings
