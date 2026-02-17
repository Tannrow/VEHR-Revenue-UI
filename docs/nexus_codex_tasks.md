# Nexus Codex Tasks

This repo supports a Nexus endpoint that creates a GitHub Issue and dispatches a Codex workflow.

## One-time setup

1. Add a GitHub Actions secret named `OPENAI_API_KEY`.
2. Ensure the GitHub App has these minimal permissions:
   - Issues: Read & Write
   - Actions: Read & Write
   - Metadata: Read

## Endpoint

`POST /api/dev/codex-task`

Request JSON:

```json
{
  "title": "string",
  "goal": "string",
  "acceptance_criteria": ["string"],
  "risk": "low|med|high",
  "files_or_area": "string",
  "notes": "string",
  "requested_by": "string"
}
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
