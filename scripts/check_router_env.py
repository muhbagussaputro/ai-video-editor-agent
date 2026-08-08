from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / ".env", ROOT / "config" / "9router.env.local"]
KEYS = ["OPENAI_BASE_URL", "OPENAI_API_KEY", "NINE_ROUTER_API_KEY"]


def read_key(key: str) -> str | None:
    for path in FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    return None


def mask_status(value: str | None) -> str:
    if not value:
        return "MISSING"
    if value in {"***", ""} or value.lower().startswith("your_") or "changeme" in value.lower():
        return "placeholder"
    return "set"


if __name__ == "__main__":
    for key in KEYS:
        print(f"{key}: {mask_status(read_key(key))}")
