# ledboard

Display daemon for the LED matrix on `jasperpi` (Raspberry Pi 5, Adafruit RGB Matrix Bonnet,
two 64x32 HUB75 panels chained to 128x32). One process owns the panel; **apps** give it frames.

- `POST /text` puts a string on the wall (bearer Clerk JWT when `LEDBOARD_AUTH_ISSUER` is set).
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
  apps/          text (POST /text queue), bus (departure board), etch (etch-a-sketch
               background), clock (idle), testpattern
  schedule.py    time-of-day windows an app can gate itself on
  tfl.py         live bus arrivals for one stop, off the render thread
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
| `LEDBOARD_TEXT_DWELL_S` | `4` | how long short text holds when no `duration_s` is sent |
| `LEDBOARD_TEXT_MAX_DURATION_S` | `300` | reject a longer `duration_s` |
| `LEDBOARD_RATE_LIMIT_PER_MIN` | `10` | per user (`sub`), or per client IP when open |
| `LEDBOARD_AUTH_ISSUER` | *(empty, open)* | Clerk frontend API url, e.g. `https://xxx.clerk.accounts.dev` |
| `LEDBOARD_AUTH_AUTHORIZED_PARTIES` | *(empty, any)* | comma list of origins allowed in `azp`, and in etch `Origin`/`Referer` |
| `LEDBOARD_BUS_STOP_ID` | `59378` | the code on the pole, or a naptan id |
| `LEDBOARD_BUS_ROUTES` | *(all)* | comma list, e.g. `12,36,171` |
| `LEDBOARD_BUS_WINDOWS` | *(always)* | e.g. `07:00-10:00,17:00-20:00`, local time |
| `LEDBOARD_BUS_REFRESH_S` | `30` | the API caches for 30s |
| `LEDBOARD_BUS_STALE_S` | `120` | after this the board yields to the clock |
| `LEDBOARD_BUS_API_KEY` | *(none)* | optional, raises the TfL rate limit |
| `LEDBOARD_ETCH_COLOR` | `#FFFFFF` | stylus colour for the etch-a-sketch background |

## Auth

`POST /text` and `DELETE /text` take a Clerk session JWT as `Authorization: Bearer <token>`.
The daemon fetches the issuer's JWKS once (cached), checks the RS256 signature, `exp`/`iat`,
that `iss` matches `LEDBOARD_AUTH_ISSUER`, and that `azp` (the origin that minted the token) is
in `LEDBOARD_AUTH_AUTHORIZED_PARTIES` when that list is non-empty. Anything else is a 401.

An empty `LEDBOARD_AUTH_ISSUER` leaves both endpoints open, which is what `make dev` wants; the
daemon logs a warning at startup so you notice on the Pi. `/healthz`, `/`, `/sim` are always open.

`/etch`, `/etch/move` and `/etch/clear` take no login, but only the home-dash frontend may
call them: the request's `Origin`/`Referer` must match an entry in
`LEDBOARD_AUTH_AUTHORIZED_PARTIES`, otherwise it's a 403. (The home-dash backend forwards the
browser's headers when it proxies, so its calls pass the same check.) Empty means don't
check, which is what `make dev` wants.

```sh
uv run ledboard send "hi" --token "$(pbpaste)"   # or export LEDBOARD_TOKEN=...
```

## Bus board

Live TfL countdown for one stop, four rows of route / destination / minutes. It is the background
app: whenever it has nothing honest to show it yields and the clock comes back.

```
12   Oxford Circus          5
36   Queen's Park           7
436  Battersea Park Stat    7
171  Elephant & Castle      8
```

`LEDBOARD_BUS_STOP_ID` takes either a naptan id or the five-digit code printed on the bus stop
(resolved once at startup). The default, `59378`, is St Giles Church. No API key is needed — TfL
allows 50 requests a minute unauthenticated and the app polls twice a minute.

`LEDBOARD_BUS_WINDOWS` restricts it to times of day, e.g. `07:00-10:00,17:00-20:00`. Empty means
always on. Outside a window the poll thread doesn't even ask, so nothing hits the API at 3am.

## Etch-a-sketch

The `etch` app is the background layer (priority 10, above the clock, below bus and
text). The `/sim` page has an **etch-a-sketch** tab: left knob draws ◀ ▶, right knob
draws ▲ ▼, and it inks live onto the board. The knobs are the only way to draw —
drag them (or scroll over them) with the mouse. Shake the frame — grab it and
waggle side-to-side, or hit **shake to clear** — to wipe the screen. Bus times and
messages overwrite the sketch while they're showing, then it comes back intact.

```
POST /etch/move {"dx": 1, "dy": 0}   # a knob nudge, each axis clamped to ±32
POST /etch/clear                     # shake
GET  /etch                           # {w, h, x, y, lit, pixels_b64}
```

## Writing an app

```python
class MyApp:
    name = "my"
    priority = 20  # text is 50, bus is 20, etch is 10, clock is 0

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
