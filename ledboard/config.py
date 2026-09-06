from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DisplayKind = Literal["hw", "web", "png", "array"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEDBOARD_", env_file=".env", extra="ignore")

    display: DisplayKind = "web"
    width: int = 128
    height: int = 32
    apps: str = "text,clock"

    host: str = "0.0.0.0"
    port: int = 8080

    fps: int = 30
    brightness: float = 1.0

    text_max_len: int = 200
    text_dwell_s: float = 4.0
    text_scroll_pps: float = 40.0
    text_color: str = "#FF8C00"

    rate_limit_per_min: int = 10

    png_path: str = "out/frame.png"
    png_scale: int = 8

    log_level: str = "INFO"

    @property
    def app_names(self) -> list[str]:
        return [a.strip() for a in self.apps.split(",") if a.strip()]
