from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DisplayKind = Literal["hw", "web", "png", "array"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEDBOARD_", env_file=".env", extra="ignore")

    display: DisplayKind = "web"
    width: int = 128
    height: int = 32
    apps: str = "text,etch,clock"

    host: str = "0.0.0.0"
    port: int = 8080

    fps: int = 30
    brightness: float = 1.0

    text_max_len: int = 200
    text_dwell_s: float = 4.0  # default hold for short text when no duration is given
    text_max_duration_s: float = 60.0
    text_scroll_pps: float = 40.0
    text_color: str = "#FF8C00"

    # St Giles Church (stop U), the code printed on the pole. A naptan id works too.
    bus_stop_id: str = "59378"
    bus_routes: str = ""  # empty shows every route at the stop
    bus_windows: str = ""  # empty is always on, e.g. "07:00-10:00,17:00-20:00"
    bus_refresh_s: float = 30.0  # the api caches for 30s, no point going faster
    bus_stale_s: float = 120.0
    bus_color: str = "#FF8C00"
    bus_font: str = "5x7"
    bus_api_key: str = ""
    bus_api_url: str = "https://api.tfl.gov.uk"

    etch_color: str = "#FFFFFF"

    rate_limit_per_min: int = 10

    # Clerk frontend API url, e.g. https://xxx.clerk.accounts.dev. Empty leaves POST /text open.
    auth_issuer: str = ""
    auth_authorized_parties: str = ""  # comma list of origins allowed in azp; empty = don't check

    png_path: str = "out/frame.png"
    png_scale: int = 8

    log_level: str = "INFO"

    @property
    def app_names(self) -> list[str]:
        return [a.strip() for a in self.apps.split(",") if a.strip()]

    @property
    def bus_route_names(self) -> list[str]:
        return [r.strip() for r in self.bus_routes.split(",") if r.strip()]

    @property
    def auth_authorized_party_list(self) -> list[str]:
        return [p.strip() for p in self.auth_authorized_parties.split(",") if p.strip()]
