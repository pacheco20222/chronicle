$ErrorActionPreference = "Stop"

$QdrantUrl = if ($env:CHRONICLE_QDRANT_URL) { $env:CHRONICLE_QDRANT_URL } else { "http://localhost:6333" }
$Collection = if ($env:CHRONICLE_COLLECTION) { $env:CHRONICLE_COLLECTION } else { "memories" }
$SqlitePath = if ($env:CHRONICLE_SQLITE_PATH) { $env:CHRONICLE_SQLITE_PATH } else { Join-Path $env:USERPROFILE ".chronicle\chronicle.db" }
$BackupDir = Join-Path (Split-Path -Parent $PSScriptRoot) "backups"
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# SQLite is the canonical store (since the 3.0.0 rearchitecture) — every
# memory, source, and scope lives here first. The Qdrant snapshot below is
# a derived vector index only; back this up first since it's the one that
# actually matters if something is lost.
if (Test-Path $SqlitePath) {
    Write-Host "Backing up SQLite database ($SqlitePath)..."
    $DbDest = Join-Path $BackupDir "chronicle-$Timestamp.db"
    $sqlite3 = Get-Command sqlite3 -ErrorAction SilentlyContinue
    if ($sqlite3) {
        # .backup is safe against a concurrent writer (uses SQLite's own
        # online backup API); a plain copy could grab a half-written page.
        & sqlite3 $SqlitePath ".backup '$DbDest'"
    } else {
        Copy-Item -Path $SqlitePath -Destination $DbDest
    }
    $dbSizeKB = [math]::Round((Get-Item $DbDest).Length / 1KB, 1)
    Write-Host "Database backup saved: $DbDest ($dbSizeKB KB)"
    Write-Host "Pruning old database backups (keeping newest 14)..."
    $oldDb = Get-ChildItem -Path $BackupDir -Filter "chronicle-*.db" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 14
    if ($oldDb) { $oldDb | Remove-Item -Force }
} else {
    Write-Host "No SQLite database found at $SqlitePath — nothing to back up there yet."
}

try {
    Invoke-RestMethod -Uri "$QdrantUrl/collections/$Collection" -Method Get | Out-Null
} catch {
    Write-Host "Collection '$Collection' doesn't exist yet — nothing to snapshot."
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
Write-Host "Vector index snapshot saved: $Dest ($sizeKB KB)"

Write-Host "Pruning old vector snapshots (keeping newest 14)..."
$old = Get-ChildItem -Path $BackupDir -Filter "$Collection-*.snapshot" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14
if ($old) { $old | Remove-Item -Force }
