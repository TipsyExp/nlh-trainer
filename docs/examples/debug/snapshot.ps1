<#
    Print the current NLH trainer engine snapshot as JSON.
    Usage: .\snapshot.ps1 -ApiUrl http://localhost:8000
#>
param(
    [string]$ApiUrl = "http://localhost:8000"
)
Write-Host "Fetching engine snapshot..."
$url = "$ApiUrl/api/debug/engine/snapshot"
Invoke-RestMethod -Uri $url | ConvertTo-Json -Depth 5