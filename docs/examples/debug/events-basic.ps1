<#
    Follow the NLH trainer engine events stream.
    Usage: .\events-basic.ps1 -ApiUrl http://localhost:8000 -Since 0 -Limit 100
#>
param(
    [string]$ApiUrl = "http://localhost:8000",
    [int]$Since = 0,
    [int]$Limit = 100
)

Write-Host "Fetching events since seq=$Since (limit $Limit)..."
$url = "$ApiUrl/api/debug/engine/events?since=$Since&limit=$Limit"
Invoke-RestMethod -Uri $url | ConvertTo-Json -Depth 5