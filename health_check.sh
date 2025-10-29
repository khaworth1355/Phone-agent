#!/bin/bash
#
# Health Check Script for Phone Agent
# Checks if the application is responding and restarts if needed
#

LOG_FILE="/opt/phone-agent/logs/health-check.log"
ENDPOINT="http://localhost:5000/"
APP_NAME="phone-agent"

# Get current timestamp
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Check if application is responding
response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "$ENDPOINT")

if [ "$response" != "200" ]; then
    echo "$(timestamp) - ❌ Health check FAILED with status $response" >> "$LOG_FILE"
    echo "$(timestamp) - Attempting to restart $APP_NAME..." >> "$LOG_FILE"

    # Restart using PM2
    pm2 restart "$APP_NAME"

    # Wait a moment and check again
    sleep 5
    response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "$ENDPOINT")

    if [ "$response" = "200" ]; then
        echo "$(timestamp) - ✅ Application restarted successfully" >> "$LOG_FILE"
    else
        echo "$(timestamp) - ⚠️ Application still not responding after restart" >> "$LOG_FILE"
    fi
else
    echo "$(timestamp) - ✅ Health check passed" >> "$LOG_FILE"
fi

# Keep only last 1000 lines of log
tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
