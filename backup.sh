#!/bin/bash
#
# Backup Script for Phone Agent
# Backs up transcripts, knowledge base, and configuration
#

BACKUP_DIR="/opt/phone-agent/backups"
APP_DIR="/opt/phone-agent"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$APP_DIR/logs/backup.log"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log_message "Starting backup process..."

# Backup transcripts
if [ -d "$APP_DIR/transcripts" ]; then
    log_message "Backing up transcripts..."
    tar -czf "$BACKUP_DIR/transcripts_$DATE.tar.gz" -C "$APP_DIR" transcripts/ 2>/dev/null
    if [ $? -eq 0 ]; then
        log_message "✅ Transcripts backed up successfully"
    else
        log_message "⚠️ Failed to backup transcripts"
    fi
fi

# Backup knowledge base
if [ -f "$APP_DIR/knowledge_base.txt" ]; then
    log_message "Backing up knowledge base..."
    cp "$APP_DIR/knowledge_base.txt" "$BACKUP_DIR/knowledge_base_$DATE.txt"
    if [ $? -eq 0 ]; then
        log_message "✅ Knowledge base backed up successfully"
    else
        log_message "⚠️ Failed to backup knowledge base"
    fi
fi

# Backup environment file (be careful with this - contains secrets!)
if [ -f "$APP_DIR/.env" ]; then
    log_message "Backing up environment configuration..."
    cp "$APP_DIR/.env" "$BACKUP_DIR/env_$DATE.txt"
    chmod 600 "$BACKUP_DIR/env_$DATE.txt"  # Restrict permissions
    if [ $? -eq 0 ]; then
        log_message "✅ Environment config backed up successfully"
    else
        log_message "⚠️ Failed to backup environment config"
    fi
fi

# Backup PM2 config
if [ -f "$APP_DIR/ecosystem.config.js" ]; then
    cp "$APP_DIR/ecosystem.config.js" "$BACKUP_DIR/ecosystem_$DATE.js"
    log_message "✅ PM2 config backed up"
fi

# Clean up old backups (keep last 7 days)
log_message "Cleaning up old backups (keeping last 7 days)..."
find "$BACKUP_DIR" -type f -mtime +7 -delete
if [ $? -eq 0 ]; then
    log_message "✅ Old backups cleaned up"
fi

# Calculate backup directory size
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log_message "Current backup directory size: $BACKUP_SIZE"

# Count remaining backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR" | wc -l)
log_message "Total backup files: $BACKUP_COUNT"

log_message "Backup process completed successfully"
log_message "----------------------------------------"

# Keep only last 1000 lines of log
tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
