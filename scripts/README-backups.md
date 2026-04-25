# MongoDB Backup and Restore

## Backup (Windows PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\mongo_backup.ps1 -MongoUri "mongodb://localhost:27017" -Database "nerox"
```

## Suggested Schedule

- Windows Task Scheduler: run `mongo_backup.ps1` every 6 hours.
- Keep at least 14 days of rolling backups.
- Copy daily backup archives to offsite object storage.

## Restore

1. Stop API/worker writes.
2. Restore from a chosen dump:

```powershell
mongorestore --uri="mongodb://localhost:27017" --drop --db nerox .\backups\mongo_YYYYMMDD_HHMMSS\nerox
```

3. Start services and verify:
- `/health`
- `/system/metrics`
- sample login + dashboard load
