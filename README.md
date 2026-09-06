# ledboard

Display daemon for the LED matrix on `jasperpi` (Raspberry Pi 5, Adafruit RGB Matrix Bonnet,
two 64x32 HUB75 panels chained to 128x32). One process owns the panel; **apps** give it frames.

- `POST /text` puts a string on the wall.
- `GET /sim` shows the board live in a browser, so you can develop without hardware.
- `ledboard text "hello"` is the same thing from a shell, no daemon needed.

## Quick start (laptop, no hardware)

```sh
uv sync
make dev            # daemon with the web simulator on http://localhost:8080/sim
```

In another terminal:

```sh
curl -d 'yo from the terminal' localhost:8080/text
uv run ledboard send "same thing, via the cli" --url http://localhost:8080
```

Or skip the daemon and render straight to a PNG:

```sh
uv run ledboard text --display png "hello"   # writes out/frame.png
```

## Layout

```
ledboard/
  daemon.py      wires everything, runs the scheduler thread + HTTP server
  scheduler.py   picks the highest-priority app that wants the screen, applies brightness, shows
  app.py         the App protocol every app implements
  apps/          text (POST /text queue), clock (idle), testpattern
  canvas.py      numpy framebuffer + Pillow bitmap-font text helpers
  fonts/         X11 misc-fixed BDF fonts, public domain, compiled on first use
  display/       hw (Piomatter on /dev/pio0), png, array; FrameStore feeds the web sim
  api.py         FastAPI: /text, /healthz, /sim, /sim/ws
  cli.py         `ledboard daemon | text | testpattern | send`
```

Apps never touch hardware. They draw on a `Canvas`; the scheduler owns the `Display`.
Swap `LEDBOARD_DISPLAY` between `hw`, `web`, `png` and `array` and nothing else changes.

## Config

Everything is an env var with the `LEDBOARD_` prefix (or a `.env` file). Defaults in
`ledboard/config.py`. The ones you'll touch:

| Var | Default | Meaning |
|---|---|---|
| `LEDBOARD_DISPLAY` | `web` | `hw` on the Pi |
| `LEDBOARD_WIDTH` / `HEIGHT` | `128` / `32` | logical panel size |
| `LEDBOARD_APPS` | `text,clock` | comma list, see `apps/__init__.py` |
| `LEDBOARD_PORT` | `8080` | HTTP port |
| `LEDBOARD_BRIGHTNESS` | `1.0` | 0..1, gamma-aware |
| `LEDBOARD_TEXT_MAX_LEN` | `200` | reject longer POSTs |
| `LEDBOARD_RATE_LIMIT_PER_MIN` | `10` | per client IP |

## Writing an app

```python
class MyApp:
    name = "my"
    priority = 20  # text is 50, clock is 0

    def start(self): ...
    def stop(self): ...
    def wants_display(self, now: float) -> bool: ...
    def render(self, canvas: Canvas, now: float) -> None: ...
```

Register it in `ledboard/apps/__init__.py`, add it to `LEDBOARD_APPS`, done. Higher priority
wins whenever it wants the screen, so a message interrupts the clock and the clock comes back.

## Tests and lint

```sh
make test
make lint
```

## Deploying

CI builds a `linux/arm64` image to `ghcr.io/jacantwell/ledboard` on every push to `main`.
The Pi pulls it via the compose stack in [jacantwell/homelab](https://github.com/jacantwell/homelab).
The container needs `/dev/pio0` and the `gpio` group, nothing else.
