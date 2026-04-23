param(
  [string]$BackupDir = ".\\backup"
)

if (-not $env:MONGO_URI) {
  Write-Error "MONGO_URI is required"
  exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outPath = Join-Path $BackupDir $timestamp
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

mongodump --uri=$env:MONGO_URI --out=$outPath
Write-Host "Mongo backup completed: $outPath"

