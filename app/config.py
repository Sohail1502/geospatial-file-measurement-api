from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Geospatial File Measurement API"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("./data/uploads")
    max_upload_bytes: int = 50 * 1024 * 1024
    allowed_extensions: tuple[str, ...] = (".zip", ".kml")


settings = Settings()
