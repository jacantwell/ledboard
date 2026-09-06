.PHONY: dev test lint fmt image text run-hw

dev:
	LEDBOARD_DISPLAY=web uv run ledboard daemon

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

image:
	docker buildx build --platform linux/arm64 -t ledboard:local .

# make text MSG="hello"  -> renders to out/frame.png
text:
	LEDBOARD_DISPLAY=png uv run ledboard text "$(MSG)"
