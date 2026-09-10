"""HTTP surface of the daemon: POST /text, GET /healthz, and the browser simulator at /sim."""

import asyncio
import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ledboard import __version__
from ledboard.apps.etch import EtchApp
from ledboard.apps.text import TextApp
from ledboard.auth import ClerkVerifier, require_user
from ledboard.canvas import parse_color
from ledboard.config import Settings
from ledboard.display.base import FrameStore

log = logging.getLogger("ledboard.api")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SIM_HTML = (Path(__file__).parent / "static" / "sim.html").read_text()


class TextIn(BaseModel):
    text: str = Field(min_length=1)
    color: str | None = None
    duration_s: float | None = Field(default=None, gt=0)  # None: the board's default


class EtchMove(BaseModel):
    dx: int = Field(default=0, ge=-32, le=32)
    dy: int = Field(default=0, ge=-32, le=32)


class RateLimiter:
    """Sliding window per client. Small and in-memory; this is a wall in a flat, not Stripe."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.time() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60.0:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


def clean_text(raw: str, max_len: int) -> str:
    s = _CONTROL.sub("", raw).replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    # the bitmap fonts only cover latin-1; anything else becomes "?"
    s = s.encode("latin-1", errors="replace").decode("latin-1")
    if not s:
        raise HTTPException(400, "text is empty after cleaning")
    if len(s) > max_len:
        raise HTTPException(413, f"text longer than {max_len} characters")
    return s


def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_api(
    settings: Settings,
    store: FrameStore,
    text_app: TextApp | None,
    verifier: ClerkVerifier | None = None,
    etch_app: EtchApp | None = None,
) -> FastAPI:
    app = FastAPI(title="ledboard", version=__version__)
    limiter = RateLimiter(settings.rate_limit_per_min)
    if verifier is None and settings.auth_issuer_list:
        verifier = ClerkVerifier(settings.auth_issuer_list, settings.auth_authorized_party_list)
    if verifier is None:
        log.warning("LEDBOARD_AUTH_ISSUER is empty: POST /text accepts anyone")
    user = Depends(require_user(verifier))

    @app.get("/healthz")
    def healthz() -> dict:
        age = time.time() - store.last_show if store.last_show else None
        ok = age is not None and age < 5.0
        return {
            "ok": ok,
            "version": __version__,
            "active_app": store.active_app,
            "last_frame_age_s": None if age is None else round(age, 3),
            "pending_text": text_app.pending if text_app else None,
            "size": [store.width, store.height],
        }

    @app.post("/text", status_code=202)
    async def post_text(request: Request, claims: dict = user) -> dict:
        if text_app is None:
            raise HTTPException(503, "text app is not enabled on this board")
        if not limiter.allow(claims.get("sub") or client_key(request)):
            raise HTTPException(429, "slow down: too many messages this minute")

        body = await request.body()
        ctype = request.headers.get("content-type", "")
        if "json" in ctype:
            try:
                payload = TextIn.model_validate(json.loads(body))
            except (ValueError, TypeError) as e:
                raise HTTPException(422, f"bad json body: {e}") from e
            raw, color, duration = payload.text, payload.color, payload.duration_s
        else:
            raw, color, duration = body.decode("utf-8", errors="replace"), None, None

        text = clean_text(raw, settings.text_max_len)
        try:
            parsed = parse_color(color) if color else None
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if duration is not None and duration > settings.text_max_duration_s:
            raise HTTPException(422, f"duration_s longer than {settings.text_max_duration_s:g}s")
        position = text_app.submit(text, parsed, duration)
        return {"queued": True, "position": position, "text": text, "duration_s": duration}

    @app.delete("/text")
    def clear_text(claims: dict = user) -> dict:
        if text_app is None:
            raise HTTPException(503, "text app is not enabled on this board")
        text_app.clear()
        return {"cleared": True}

    @app.get("/", response_class=PlainTextResponse)
    def root() -> str:
        return (
            f"ledboard {__version__}\n"
            f'POST /text  with a plain-text body or {{"text": "...", "color": "#hex"}}\n'
            f'            "duration_s": seconds to show it, max {settings.text_max_duration_s:g}\n'
            f"            Authorization: Bearer <clerk jwt> when LEDBOARD_AUTH_ISSUER is set\n"
            f"GET  /etch  etch-a-sketch state (background layer, bus/text overwrite it)\n"
            f'POST /etch/move {{"dx": 1, "dy": 0}}  turn the knobs, draws live\n'
            f"POST /etch/clear  shake to wipe\n"
            f"GET  /sim   to watch the board in a browser\n"
            f"GET  /healthz\n"
        )

    @app.get("/sim", response_class=HTMLResponse)
    def sim() -> str:
        return SIM_HTML

    def _need_etch() -> EtchApp:
        if etch_app is None:
            raise HTTPException(503, "etch app is not enabled on this board")
        return etch_app

    # Etch is anonymous (no login), but only the home-dash frontend may use it.
    # Browsers attest this with Origin/Referer, matched against
    # LEDBOARD_AUTH_AUTHORIZED_PARTIES; empty leaves it open, like `make dev`.
    allowed_origins = {p.rstrip("/") for p in settings.auth_authorized_party_list}

    def _need_frontend(request: Request) -> None:
        if not allowed_origins:
            return
        for header in (request.headers.get("origin"), request.headers.get("referer")):
            if not header:
                continue
            parts = urlsplit(header)
            origin = (
                f"{parts.scheme}://{parts.netloc}".rstrip("/")
                if parts.netloc
                else header.rstrip("/")
            )
            if origin in allowed_origins:
                return
        raise HTTPException(403, "etch is only available from the home-dash frontend")

    frontend = Depends(_need_frontend)

    @app.get("/etch", dependencies=[frontend])
    def get_etch() -> dict:
        return _need_etch().state()

    @app.post("/etch/move", dependencies=[frontend])
    def etch_move(move: EtchMove) -> dict:
        if move.dx == 0 and move.dy == 0:
            raise HTTPException(422, "dx/dy can't both be zero")
        x, y = _need_etch().move(move.dx, move.dy)
        return {"x": x, "y": y}

    @app.post("/etch/clear", dependencies=[frontend])
    def etch_clear() -> dict:
        x, y = _need_etch().clear()
        return {"cleared": True, "x": x, "y": y}

    @app.websocket("/sim/ws")
    async def sim_ws(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_text(json.dumps({"w": store.width, "h": store.height}))
        seen = -1
        try:
            while True:
                version, frame = store.snapshot()
                if version != seen:
                    seen = version
                    await ws.send_bytes(frame)
                await asyncio.sleep(1.0 / 30)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app
