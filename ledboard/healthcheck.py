"""Container healthcheck: exit 0 if the daemon answers and has shown a frame recently."""

import json
import os
import sys
import urllib.request

url = f"http://127.0.0.1:{os.environ.get('LEDBOARD_PORT', '8080')}/healthz"
try:
    with urllib.request.urlopen(url, timeout=3) as r:
        h = json.load(r)
except Exception as e:  # noqa: BLE001
    print(f"unhealthy: {e}")
    sys.exit(1)
if not h.get("ok"):
    print(f"unhealthy: {h}")
    sys.exit(1)
print("ok")
