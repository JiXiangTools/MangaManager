from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MANGAMANAGER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/mangamanager.db"
    data_dir: Path = Path("./data")
    temp_password: str = ""
    temp_password_hash: str = ""
    session_secret: str = "dev-session-secret"
    desktop_token: str = ""
    translation_base_url: str = "https://www.mangatranslate.com"
    translation_proxy_base: str = "https://plugin-server.mangatranslate.com"
    translation_user_id: str = ""
    translation_email: str = ""
    translation_access_token: str = ""

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
