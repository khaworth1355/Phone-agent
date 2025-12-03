# Deployment Checklist

Use this checklist to ensure all steps are completed before and during deployment.

## Pre-Deployment (Local Machine)

### Environment Variables
- [ ] Verify all API keys are set in `.env` file
- [ ] Copy `.env` content to secure location for server setup
- [ ] Document any custom environment variables

**Required Environment Variables:**
```
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
DEEPGRAM_API_KEY=
ANTHROPIC_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
SALES_FORWARD_NUMBER=+18166741783
WEBSOCKET_URL=wss://YOUR_DROPLET_IP/media
PAUSE_THRESHOLD=0.3
RESPONSE_TIMEOUT=15.0
DEBUG=False
```

### Files Verification
- [ ] All deployment config files created (Phase 1 completed)
- [ ] `.gitignore` excludes sensitive files
- [ ] `knowledge_base.txt` exists and is up to date
- [ ] `requirements.txt` includes all dependencies

### Code Review
- [ ] DEBUG mode set to False in production (via environment variable)
- [ ] WEBSOCKET_URL reads from environment variable
- [ ] No hardcoded secrets in code
- [ ] All file paths use relative or configurable paths

---

## DigitalOcean Droplet Setup

### Droplet Creation
- [ ] Droplet created (Ubuntu 22.04 LTS)
- [ ] Minimum 2GB RAM selected
- [ ] SSH key added or password saved
- [ ] Droplet IP address noted: `________________`

### Initial Server Configuration
- [ ] SSH access verified: `ssh root@YOUR_DROPLET_IP`
- [ ] System packages updated: `sudo apt update && sudo apt upgrade -y`
- [ ] Non-root user created: `phoneagent`
- [ ] User added to sudo group
- [ ] Firewall configured (UFW)

---

## Dependencies Installation

### System Dependencies
- [ ] Python 3.11+ installed
- [ ] pip installed
- [ ] ffmpeg installed (for audio processing)
- [ ] Nginx installed
- [ ] Node.js 20.x installed
- [ ] PM2 installed globally
- [ ] htop and monitoring tools installed

### Firewall Rules
- [ ] OpenSSH allowed
- [ ] Nginx Full allowed (ports 80, 443)
- [ ] UFW enabled

---

## Application Deployment

### Code Transfer
- [ ] Application directory created: `/opt/phone-agent`
- [ ] Ownership set to `phoneagent` user
- [ ] Code transferred to server (git clone or scp)
- [ ] All files present and readable

### Python Environment
- [ ] Virtual environment created
- [ ] Virtual environment activated
- [ ] Dependencies installed from requirements.txt
- [ ] gunicorn installed

### Directory Structure
- [ ] `temp_audio/` directory created
- [ ] `transcripts/` directory created
- [ ] `logs/` directory created
- [ ] `backups/` directory created
- [ ] Correct permissions set (755)

### Configuration
- [ ] `.env` file created with all variables
- [ ] `.env` permissions set to 600
- [ ] WEBSOCKET_URL updated with actual Droplet IP
- [ ] knowledge_base.txt transferred

---

## SSL Certificate

### Self-Signed Certificate (for IP-based deployment)
- [ ] Self-signed certificate generated
- [ ] Certificate paths: `/etc/ssl/certs/nginx-selfsigned.crt`
- [ ] Key paths: `/etc/ssl/private/nginx-selfsigned.key`

### OR Let's Encrypt (if using domain)
- [ ] Certbot installed
- [ ] Certificate obtained for domain
- [ ] Auto-renewal configured

---

## Nginx Configuration

### Setup
- [ ] Nginx config copied to `/etc/nginx/sites-available/phone-agent`
- [ ] `server_name` updated with actual IP or domain
- [ ] SSL certificate paths verified in config
- [ ] Symlink created to sites-enabled
- [ ] Nginx configuration tested: `sudo nginx -t`
- [ ] Nginx restarted
- [ ] Nginx enabled to start on boot

### Verification
- [ ] Can access http://DROPLET_IP (redirects to HTTPS)
- [ ] Can access https://DROPLET_IP (shows application)
- [ ] WebSocket endpoint accessible

---

## PM2 Process Manager

### Setup
- [ ] PM2 started with ecosystem.config.js
- [ ] Application running: `pm2 status`
- [ ] PM2 configuration saved: `pm2 save`
- [ ] PM2 startup script configured: `pm2 startup`
- [ ] Startup command executed (from pm2 startup output)

### Verification
- [ ] Application status shows "online"
- [ ] Logs show no errors: `pm2 logs phone-agent`
- [ ] Auto-restart working (test with `pm2 restart phone-agent`)

---

## Monitoring & Backups

### Health Check
- [ ] `health_check.sh` made executable: `chmod +x health_check.sh`
- [ ] Cron job added (every 5 minutes)
- [ ] Health check tested manually: `./health_check.sh`
- [ ] Log file created and writing: `logs/health-check.log`

### Backup Script
- [ ] `backup.sh` made executable: `chmod +x backup.sh`
- [ ] Cron job added (daily at 2 AM)
- [ ] Backup tested manually: `./backup.sh`
- [ ] Backup directory created: `backups/`
- [ ] Log file created: `logs/backup.log`

### Monitoring Setup
- [ ] pm2-logrotate installed
- [ ] htop installed for system monitoring
- [ ] Log rotation configured

---

## Twilio Configuration

### Webhook Setup
- [ ] Logged into Twilio Console
- [ ] Phone number configured
- [ ] Voice webhook URL set: `https://YOUR_DROPLET_IP/voice`
- [ ] Webhook method set to POST
- [ ] Status callback URL configured (optional)

### Testing
- [ ] Test call made to Twilio number
- [ ] Greeting plays correctly
- [ ] Speech-to-text transcription working
- [ ] AI responses playing back
- [ ] Call transfer working (if applicable)

---

## Application Testing

### Health Checks
- [ ] Root endpoint responding: `curl https://YOUR_DROPLET_IP/`
- [ ] Health endpoint responding (if implemented)
- [ ] Audio serving endpoint working: `/audio/`
- [ ] Logs showing no errors

### Phone Call Testing
- [ ] Call connects successfully
- [ ] Greeting audio plays (ElevenLabs)
- [ ] Transcription working (Deepgram)
- [ ] AI responds correctly (Claude)
- [ ] TTS audio quality good (ElevenLabs)
- [ ] Call transfer works
- [ ] Transcript saved to file

### Load Testing (Optional)
- [ ] Multiple concurrent calls tested
- [ ] Memory usage monitored
- [ ] CPU usage monitored
- [ ] No crashes or errors

---

## Post-Deployment

### Documentation
- [ ] Server IP documented: `________________`
- [ ] SSH access instructions documented
- [ ] Emergency contacts documented
- [ ] API usage limits documented

### Monitoring Setup
- [ ] PM2 monitoring dashboard accessible
- [ ] Log files being written correctly
- [ ] Backup process verified
- [ ] Alert system configured (optional)

### Security
- [ ] Only required ports open in firewall
- [ ] SSH key authentication enabled
- [ ] Password authentication disabled (recommended)
- [ ] `.env` file has restricted permissions (600)
- [ ] SSL certificate valid and trusted

---

## Ongoing Maintenance Schedule

### Daily
- [ ] Check PM2 status: `pm2 status`
- [ ] Review recent logs: `pm2 logs --lines 50`
- [ ] Monitor disk space: `df -h`

### Weekly
- [ ] Review all logs in `/opt/phone-agent/logs/`
- [ ] Check backup status
- [ ] System updates: `sudo apt update && sudo apt upgrade`
- [ ] Review transcript volume

### Monthly
- [ ] Review and archive old transcripts
- [ ] Check SSL certificate expiry
- [ ] Review API usage and costs
- [ ] Test disaster recovery process
- [ ] Review security patches

---

## Troubleshooting Quick Reference

### Application Not Running
```bash
pm2 status
pm2 logs phone-agent
pm2 restart phone-agent
```

### Nginx Issues
```bash
sudo systemctl status nginx
sudo nginx -t
sudo tail -f /var/log/nginx/phone-agent-error.log
```

### Call Not Connecting
```bash
# Check Twilio webhook URL is correct
# Check SSL certificate is valid
# Check firewall allows HTTPS traffic
sudo tail -f /var/log/nginx/phone-agent-access.log
```

### Disk Space Issues
```bash
df -h
du -sh /opt/phone-agent/transcripts/
# Clean old transcripts if needed
find /opt/phone-agent/transcripts -mtime +30 -delete
```

---

## Emergency Contacts

- **Twilio Support**: https://support.twilio.com
- **DigitalOcean Support**: https://www.digitalocean.com/support
- **Application Owner**: ________________
- **On-Call Developer**: ________________

---

## Rollback Plan

If deployment fails:

1. **Stop application**: `pm2 stop phone-agent`
2. **Restore from backup**: `tar -xzf backups/transcripts_YYYYMMDD.tar.gz`
3. **Revert code**: `git checkout previous_commit`
4. **Restart**: `pm2 restart phone-agent`
5. **Update Twilio webhook** to previous URL if needed

---

**Deployment Date**: ________________
**Deployed By**: ________________
**Version**: ________________
**Notes**:
