"""Interactive, read-only Toss connection check. Credentials never saved."""
from datetime import datetime, timezone
from getpass import getpass
import os
from .data import root
from .toss import collect

def connect(symbol="005930", pages=20):
    names = ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET")
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            if not os.environ.get(name):
                value = getpass(f"{name} (hidden input): ").strip()
                if not value:
                    raise ValueError("인증 정보를 입력하지 않아 조회를 중단했습니다.")
                os.environ[name] = value
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = root() / "raw" / ("toss-" + timestamp)
        return collect(symbol, str(output), max_pages=pages)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
