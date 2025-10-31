#!/bin/bash
BACKUP_DIR="/opt/phone-agent/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

tar -czf $BACKUP_DIR/transcripts_$DATE.tar.gz /opt/phone-agent/transcripts/

cp /opt/phone-agent/knowledge_base.txt $BACKUP_DIR/knowledge_base$DATE.txt
cp /opt/phone-agent/.env $BACKUP_DIR/env_$DATE.txt

find $BACKUP_DIR -type f -mtime +7 -delete

echo "$(date): Backup completed" >> /opt/phone-agent/logs/backup.log
