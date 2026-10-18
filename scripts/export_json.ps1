$ErrorActionPreference = "Stop"

$QdrantUrl = if ($env:CHRONICLE_QDRANT_URL) { $env:CHRONICLE_QDRANT_URL } else { "http://localhost:6333" }
$Collection = if ($env:CHRONICLE_COLLECTION) { $env:CHRONICLE_COLLECTION } else { "memories" }
$BackupDir = Join-Path (Split-Path -Parent $PSScriptRoot) "backups"
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

try {
    Invoke-RestMethod -Uri "$QdrantUrl/collections/$Collection" -Method Get | Out-Null
} catch {
    Write-Host "Collection '$Collection' doesn't exist yet - nothing to export."
    exit 0
}

$Dest = Join-Path $BackupDir "$Collection-$Timestamp.json"

Write-Host "Exporting collection '$Collection' to JSON..."
$points = @()
$offset = $null
while ($true) {
    $body = @{ limit = 200; with_payload = $true; with_vector = $false }
    if ($null -ne $offset) { $body["offset"] = $offset }
    $result = Invoke-RestMethod -Uri "$QdrantUrl/collections/$Collection/points/scroll" `
        -Method Post -ContentType "application/json" -Body ($body | ConvertTo-Json)
    foreach ($p in $result.result.points) {
        $entry = [ordered]@{ id = $p.id }
        foreach ($prop in $p.payload.PSObject.Properties) {
            $entry[$prop.Name] = $prop.Value
        }
        $points += [pscustomobject]$entry
    }
    $offset = $result.result.next_page_offset
    if ($null -eq $offset) { break }
}

# -InputObject (not a pipeline / -AsArray, which is PowerShell 7 only) keeps
# 0 or 1 points a JSON array on Windows PowerShell 5.1 too; WriteAllText
# writes UTF-8 without the BOM that 5.1's `Set-Content -Encoding utf8` adds.
$json = ConvertTo-Json -InputObject @($points) -Depth 10
[System.IO.File]::WriteAllText($Dest, $json, (New-Object System.Text.UTF8Encoding $false))

Write-Host "Exported $($points.Count) memories to $Dest"

Write-Host "Pruning old exports (keeping newest 14)..."
$old = Get-ChildItem -Path $BackupDir -Filter "$Collection-*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14
if ($old) { $old | Remove-Item -Force }
