from __future__ import annotations

import argparse
import json
import sys
import time
from urllib import error, request


def _wait(url: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            req = request.Request(url, headers={"Accept": "application/json"})
            with request.urlopen(req, timeout=5) as response:  # noqa: S310
                if response.status == 200:
                    payload = response.read().decode("utf-8")
                    if payload:
                        try:
                            parsed = json.loads(payload)
                            if isinstance(parsed, dict) and parsed.get("ok") is False:
                                raise RuntimeError("health endpoint returned ok=false")
                        except json.JSONDecodeError:
                            pass
                    return True
        except Exception as exc:  # noqa: BLE001
            print(
                f"wait_for_health attempt={attempt} url={url} status=retry "
                f"reason={type(exc).__name__} detail={str(exc)[:160]}",
                file=sys.stderr,
            )
        time.sleep(1)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait until a health endpoint responds with HTTP 200")
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args(argv)

    if _wait(args.url, args.timeout_seconds):
        print(f"wait_for_health status=ok url={args.url}")
        return 0
    print(f"wait_for_health status=timeout url={args.url}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
