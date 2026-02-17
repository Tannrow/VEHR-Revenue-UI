param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$Path = "/api/dev/codex-task"
)

$payload = @{
  title = "Add health endpoint"
  goal  = "Add GET /health returning {ok:true}"
  acceptance_criteria = @("GET /health returns 200 and ok:true")
  risk = "low"
  requested_by = "Tanner"
} | ConvertTo-Json -Depth 5

try {
  $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl$Path" -ContentType "application/json" -Body $payload
  $response | ConvertTo-Json -Depth 5
} catch {
  Write-Error $_
  exit 1
}
