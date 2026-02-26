from __future__ import annotations

import os
import re
from typing import List, Optional

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


_DEFAULT_ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
_DEFAULT_ALLOWED_HEADERS = ["Authorization", "Content-Type"]


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def _is_localhost_origin(origin: str) -> bool:
    # Strict enough to match your tests; flexible enough for local dev ports.
    # Accept exactly localhost or 127.0.0.1 with optional port, http/https.
    return bool(
        re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", origin)
    )


def get_cors_origins() -> List[str]:
    """
    Backwards-compatible helper expected by tests and app.main.

    Rules (based on your tests):
    - If LOCAL_DEV truthy -> filter CORS_ALLOWED_ORIGINS down to localhost-only.
    - Otherwise -> return CORS_ALLOWED_ORIGINS as-is (CSV), or [] if unset.
    - Return sorted unique list for deterministic behavior.
    """
    local_dev = os.getenv("LOCAL_DEV", "").strip().lower() in {"1", "true", "yes", "y", "on"}
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = _parse_csv(raw)

    if local_dev:
        origins = [o for o in origins if _is_localhost_origin(o)]

    # Unique + deterministic order (your test expects 127.0.0.1 before localhost)
    return sorted(set(origins))


def create_app() -> FastAPI:
    """
    App factory. Keeps global app creation in app.main simple and testable.
    """
    app = FastAPI()

    # Apply standard CORS for non-preflight responses.
    # Preflight handling + logging is implemented in app.main middleware.
    allow_origins = get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=_DEFAULT_ALLOWED_METHODS,
        allow_headers=_DEFAULT_ALLOWED_HEADERS,
        max_age=86400,
    )

    # Minimal routes used by your tests (they only OPTIONS these paths).
    # These handlers aren’t strictly required for OPTIONS if middleware intercepts,
    # but having them avoids surprises in other environments.
    @app.post("/api/v1/auth/login")
    async def auth_login():
        return {"ok": True}

    @app.get("/api/v1/auth/me")
    async def auth_me():
        return {"ok": True}

    @app.get("/api/v1/ai/notifications/stream")
    async def notifications_stream():
        return {"ok": True}

    return app
