# Local Development

Local startup can skip external integration checks (ex: RingCentral) to make dev runs simpler.

Run locally:

```powershell
$env:SKIP_STARTUP_CHECKS="1"
python -m uvicorn app.main:app --reload --port 8000
```
