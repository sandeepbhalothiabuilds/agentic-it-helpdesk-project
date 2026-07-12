[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

function Show-Json {
    param([Parameter(ValueFromPipeline = $true)]$Value)
    process {
        $Value | ConvertTo-Json -Depth 30
    }
}

Write-Host "Checking readiness..." -ForegroundColor Cyan
Invoke-RestMethod -Uri "$BaseUrl/ready" -Method Get | Show-Json

Write-Host "`nTesting retrieval..." -ForegroundColor Cyan
$retrieveBody = [ordered]@{
    query    = "reset password identity verification policy"
    workflow = "password_reset"
    top_k    = 3
} | ConvertTo-Json -Compress

Invoke-RestMethod `
    -Uri "$BaseUrl/retrieve" `
    -Method Post `
    -ContentType "application/json" `
    -Body $retrieveBody | Show-Json

Write-Host "`nTesting chat without action confirmation..." -ForegroundColor Cyan
$chatBody = [ordered]@{
    message     = "unlock my account"
    employee_id = "E10231"
    confirm     = $false
} | ConvertTo-Json -Compress

Invoke-RestMethod `
    -Uri "$BaseUrl/chat" `
    -Method Post `
    -ContentType "application/json" `
    -Body $chatBody | Show-Json
