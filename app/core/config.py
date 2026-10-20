from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    model_name: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    max_upload_size_mb: int = 50
    supported_extensions: str = ".wav,.mp3,.m4a,.flac,.ogg"
    temp_dir: Path = Path("tmp")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_extensions(self) -> set[str]:
        return {ext.strip().lower() for ext in self.supported_extensions.split(",") if ext.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
