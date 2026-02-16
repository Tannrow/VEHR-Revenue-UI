from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from scripts.era_extract.extract_era import run


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_in_dir() -> Path:
    return _repo_root() / "inputs" / "eras"


def _wait_for_stable_file(path: Path, settle_seconds: float = 1.0, timeout_seconds: float = 60.0) -> None:
    start = time.time()
    last_size = -1
    stable_for = 0.0
    while True:
        if not path.exists():
            time.sleep(0.25)
            continue

        size = path.stat().st_size
        if size == last_size and size > 0:
            stable_for += 0.25
        else:
            stable_for = 0.0
        last_size = size

        if stable_for >= settle_seconds:
            return
        if time.time() - start > timeout_seconds:
            raise TimeoutError(f"File did not stabilize in time: {path}")
        time.sleep(0.25)


class _Handler(FileSystemEventHandler):
    def __init__(self, settle_seconds: float):
        self.settle_seconds = settle_seconds

    def on_created(self, event):
        if getattr(event, "is_directory", False):
            return
        path = Path(getattr(event, "src_path", ""))
        if path.suffix.lower() != ".pdf":
            return
        try:
            _wait_for_stable_file(path, settle_seconds=self.settle_seconds)
            out = run(path)
            print(str(out))
        except Exception as e:
            # No silent failures; watcher keeps running.
            print(f"[era_extract] failed for {path.name}: {e}")

    def on_moved(self, event):
        # Handle atomic writes where files appear via move into directory.
        if getattr(event, "is_directory", False):
            return
        dest = Path(getattr(event, "dest_path", ""))
        if dest.suffix.lower() != ".pdf":
            return
        try:
            _wait_for_stable_file(dest, settle_seconds=self.settle_seconds)
            out = run(dest)
            print(str(out))
        except Exception as e:
            print(f"[era_extract] failed for {dest.name}: {e}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Watch inputs/eras and auto-extract new PDFs to outputs/eras.")
    p.add_argument("--dir", dest="watch_dir", required=False, help="Directory to watch (default: inputs/eras)")
    p.add_argument("--settle", dest="settle", required=False, type=float, default=1.0, help="Seconds file must be stable before processing")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    watch_dir = Path(args.watch_dir).resolve() if args.watch_dir else _default_in_dir().resolve()
    watch_dir.mkdir(parents=True, exist_ok=True)

    handler = _Handler(settle_seconds=float(args.settle))
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    print(f"[era_extract] watching: {watch_dir}")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
