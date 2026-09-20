#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if /usr/bin/python3 - <<'PY'
from pathlib import Path
import urllib.request
import webbrowser
p=Path('.state/launch-url')
if not p.exists():raise SystemExit(1)
url=p.read_text().strip()
try:
    with urllib.request.urlopen(url.split('#')[0],timeout=2) as r:
        if b'THE WAR ROOM' not in r.read():raise SystemExit(1)
except Exception:raise SystemExit(1)
webbrowser.open(url)
PY
then
  exit 0
fi
exec /usr/bin/python3 server.py
