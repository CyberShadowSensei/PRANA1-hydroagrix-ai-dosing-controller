#!/usr/bin/env bash
# SQLite WAL Database Backup Script
BACKUP_DIR="/var/backups/hydroagrix"
mkdir -p "$BACKUP_DIR"
sqlite3 backend/mydatabase.db ".backup '$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).db'"
echo "==> Database backup complete."
