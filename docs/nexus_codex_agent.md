# Nexus Codex Agent

Nexus can create a GitHub Issue and dispatch a Codex workflow to open a PR.

## One-time repo setup

1. Add a GitHub Actions secret named `OPENAI_API_KEY`.
2. Ensure the GitHub App used by Nexus has minimal permissions:
   - Issues: Read & Write
   - Actions: Read & Write
   - Metadata: Read

## Endpoint

`POST /api/dev/codex-task`

Request JSON:

```json
{
  "title": "Add /health endpoint returning {ok:true}",
  "goal": "Expose a simple health endpoint for smoke checks",
  "acceptance_criteria": ["GET /health returns {ok:true}"],
  "risk": "low",
  "files_or_area": "app/main.py",
  "notes": "Keep changes minimal",
  "requested_by": "Nexus"
}
```

Curl example:

```bash
curl -X POST "http://localhost:8000/api/dev/codex-task" \
  -H "Content-Type: application/json" \
  -d '{"title":"Add /health endpoint returning {ok:true}","goal":"Expose a simple health endpoint for smoke checks","acceptance_criteria":["GET /health returns {ok:true}"],"risk":"low","files_or_area":"app/main.py","notes":"Keep changes minimal","requested_by":"Nexus"}'
```

Behavior:
- Creates a GitHub Issue with labels `ai-task` and `risk:<risk>`.
- Dispatches `.github/workflows/codex_task.yml` with the issue number.
- The workflow runs Codex using the issue body and opens a PR.

Response:

```json
{
  "status": "started",
  "issue_number": 123,
  "issue_url": "https://github.com/Tannrow/VEHR/issues/123"
}
```

## Where to watch

- GitHub Actions run for `Codex Task`
- PR list for new Codex-generated pull requests
