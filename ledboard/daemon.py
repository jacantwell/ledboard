"""Wire settings -> display -> apps -> scheduler thread + HTTP server.

One process owns the panel."""

import logging
import threading

import uvicorn

from ledboard.api import create_api
from ledboard.apps import build_apps
from ledboard.apps.etch import EtchApp
from ledboard.apps.text import TextApp
from ledboard.config import Settings
from ledboard.display import FrameStore, make_display
from ledboard.scheduler import Scheduler

log = logging.getLogger("ledboard")


def run(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log.info(
        "display=%s size=%dx%d apps=%s",
        settings.display,
        settings.width,
        settings.height,
        settings.app_names,
    )

    display = make_display(settings)
    store = FrameStore(settings.width, settings.height)
    apps = build_apps(settings)
    text_app = apps.get("text")
    assert text_app is None or isinstance(text_app, TextApp)
    etch_app = apps.get("etch")
    assert etch_app is None or isinstance(etch_app, EtchApp)

    scheduler = Scheduler(
        display, apps.values(), store, fps=settings.fps, brightness=settings.brightness
    )
    stop = threading.Event()
    worker = threading.Thread(target=scheduler.run, args=(stop,), name="scheduler", daemon=True)
    worker.start()

    api = create_api(settings, store, text_app, etch_app=etch_app)
    server = uvicorn.Server(
        uvicorn.Config(
            api,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    )
    try:
        server.run()  # installs SIGINT/SIGTERM handlers, returns on shutdown
    finally:
        stop.set()
        worker.join(timeout=5)
        log.info("bye")


if __name__ == "__main__":
    run()
