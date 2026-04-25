param(
  [string]$MongoUri = "mongodb://localhost:27017",
  [string]$Database = "nerox",
  [string]$OutputDir = ".\\backups"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$targetDir = Join-Path $OutputDir "mongo_$timestamp"

New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

Write-Host "Running mongodump for database '$Database'..."
mongodump --uri="$MongoUri" --db="$Database" --out="$targetDir"

if ($LASTEXITCODE -ne 0) {
  Write-Error "Backup failed."
  exit 1
}

Write-Host "Backup completed at: $targetDir"
