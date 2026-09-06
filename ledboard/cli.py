"""`ledboard` command. `text` is the simple entry point: string in, pixels out."""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request

from ledboard import __version__
from ledboard.config import Settings


def _settings(args: argparse.Namespace) -> Settings:
    overrides = {}
    if getattr(args, "display", None):
        overrides["display"] = args.display
    if getattr(args, "size", None):
        w, h = args.size.lower().split("x")
        overrides["width"], overrides["height"] = int(w), int(h)
    return Settings(**overrides)


def cmd_daemon(args: argparse.Namespace) -> int:
    from ledboard.daemon import run

    run(_settings(args))
    return 0


def _run_until_done(settings: Settings, app, timeout: float | None = None) -> int:
    """Drive one app on the chosen display until it no longer wants the screen."""
    from ledboard.display import make_display
    from ledboard.scheduler import Scheduler

    display = make_display(settings)
    sched = Scheduler(
        display, [app], fps=settings.fps, brightness=settings.brightness, stop_when_idle=True
    )
    stop = threading.Event()
    t = threading.Thread(target=sched.run, args=(stop,), daemon=True)
    t.start()
    started = time.time()
    try:
        while t.is_alive():
            if timeout and time.time() - started > timeout:
                break
            t.join(timeout=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        t.join(timeout=3)
    return 0


def cmd_text(args: argparse.Namespace) -> int:
    from ledboard.apps.text import TextApp

    settings = _settings(args)
    text = " ".join(args.text) if args.text else sys.stdin.read()
    app = TextApp(
        settings.width,
        settings.height,
        dwell_s=args.dwell,
        scroll_pps=settings.text_scroll_pps,
        default_color=settings.text_color,
    )
    app.submit(text.strip(), args.color)
    return _run_until_done(settings, app)


def cmd_testpattern(args: argparse.Namespace) -> int:
    from ledboard.apps.testpattern import TestPatternApp

    settings = _settings(args)
    app = TestPatternApp(settings.width, settings.height, loop=args.loop)
    return _run_until_done(settings, app)


def cmd_send(args: argparse.Namespace) -> int:
    """POST text to a running daemon."""
    text = " ".join(args.text) if args.text else sys.stdin.read().strip()
    body = json.dumps({"text": text, "color": args.color}).encode()
    req = urllib.request.Request(
        args.url.rstrip("/") + "/text",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            print(r.read().decode())
            return 0
    except urllib.error.HTTPError as e:
        print(f"{e.code}: {e.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"could not reach {args.url}: {e.reason}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ledboard", description="LED matrix display daemon and tools")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--display", choices=["hw", "web", "png", "array"], help="override LEDBOARD_DISPLAY"
        )
        sp.add_argument("--size", help="WxH, override LEDBOARD_WIDTH/HEIGHT, e.g. 128x32")

    d = sub.add_parser("daemon", help="run the display daemon + HTTP API")
    common(d)
    d.set_defaults(fn=cmd_daemon)

    t = sub.add_parser("text", help="show a string on the board and exit")
    common(t)
    t.add_argument("text", nargs="*", help="text to show (reads stdin if omitted)")
    t.add_argument("--color", help="hex colour, e.g. #ff8c00")
    t.add_argument("--dwell", type=float, default=4.0, help="seconds to hold short text")
    t.set_defaults(fn=cmd_text)

    tp = sub.add_parser("testpattern", help="colours, gradient, frame")
    common(tp)
    tp.add_argument("--loop", action="store_true")
    tp.set_defaults(fn=cmd_testpattern)

    s = sub.add_parser("send", help="POST text to a running daemon")
    s.add_argument("text", nargs="*")
    s.add_argument("--url", default="http://jasperpi.local:8080")
    s.add_argument("--color")
    s.set_defaults(fn=cmd_send)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
