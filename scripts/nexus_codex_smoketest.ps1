param(
  [string]$BaseUrl = "http://localhost:8000"
)

$payload = @{
  title = "Add health endpoint"
  goal = "Add GET /health returning {ok:true}"
  acceptance_criteria = @("GET /health returns 200 and ok:true")
  risk = "low"
} | ConvertTo-Json -Depth 5

try {
  $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/dev/codex-task" -ContentType "application/json" -Body $payload
  $response | ConvertTo-Json -Depth 5
} catch {
  Write-Error $_
  exit 1
}
