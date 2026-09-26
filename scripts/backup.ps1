$ErrorActionPreference = "Stop"

$QdrantUrl = if ($env:CHRONICLE_QDRANT_URL) { $env:CHRONICLE_QDRANT_URL } else { "http://localhost:6333" }
$Collection = if ($env:CHRONICLE_COLLECTION) { $env:CHRONICLE_COLLECTION } else { "memories" }
$BackupDir = Join-Path (Split-Path -Parent $PSScriptRoot) "backups"
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

try {
    Invoke-RestMethod -Uri "$QdrantUrl/collections/$Collection" -Method Get | Out-Null
} catch {
    Write-Host "Collection '$Collection' doesn't exist yet — nothing to back up."
    exit 0
}

Write-Host "Creating snapshot of collection '$Collection'..."
$snapshotResponse = Invoke-RestMethod -Uri "$QdrantUrl/collections/$Collection/snapshots" -Method Post
$SnapshotName = $snapshotResponse.result.name

Write-Host "Downloading snapshot: $SnapshotName"
$Dest = Join-Path $BackupDir "$Collection-$Timestamp.snapshot"
Invoke-WebRequest -Uri "$QdrantUrl/collections/$Collection/snapshots/$SnapshotName" -OutFile $Dest

Write-Host "Removing snapshot copy from Qdrant (kept locally at $Dest)..."
Invoke-RestMethod -Uri "$QdrantUrl/collections/$Collection/snapshots/$SnapshotName" -Method Delete | Out-Null

$sizeKB = [math]::Round((Get-Item $Dest).Length / 1KB, 1)
Write-Host "Backup saved: $Dest ($sizeKB KB)"

Write-Host "Pruning old backups (keeping newest 14)..."
$old = Get-ChildItem -Path $BackupDir -Filter "$Collection-*.snapshot" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14
if ($old) { $old | Remove-Item -Force }
