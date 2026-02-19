from __future__ import annotations

from pathlib import Path

FORBIDDEN_TOKENS = ["float(", "np.float", "numpy.float", "random()", "random.random", "Math.random"]


def _revenue_files() -> list[Path]:
  files: list[Path] = list(Path("app/api/v1/endpoints").glob("revenue_*.py"))
  app_revenue = Path("app_revenue")
  if app_revenue.exists():
    files.extend(app_revenue.rglob("*.py"))
  return files


def test_revenue_backend_has_no_float_usage_tokens() -> None:
  files = _revenue_files()
  assert files, "Expected revenue modules to scan"

  violations = []
  for path in files:
    text = path.read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
      if token in text:
        violations.append(f"{path}:{token}")

  assert not violations, "Forbidden non-deterministic tokens found:\n" + "\n".join(violations)
