# DigitalOcean Deployment Guide - Phone Agent

Complete deployment guide for deploying the Phone Agent application to a DigitalOcean Droplet with Nginx, PM2, SSL, monitoring, and backups.

**Deployment Configuration:**
- Platform: DigitalOcean Droplet (VM)
- Domain: DigitalOcean provided IP (no custom domain)
- WebSocket: Public URL with SSL
- Features: PM2 process manager, Nginx reverse proxy, system monitoring, automated backups

---

## Phase 1: Pre-Deployment Preparation (Local)

### 1. Create deployment configuration files
- ✅ `.gitignore` - Exclude sensitive files (.env, .venv/, __pycache__/, temp_audio/, transcripts/)
- ✅ `gunicorn_config.py` - Production WSGI server configuration
- ✅ `phone-agent.service` - Systemd service file for auto-start
- ✅ `nginx-phone-agent.conf` - Nginx configuration
- ✅ `ecosystem.config.js` - PM2 process manager configuration

### 2. Update code for production
- ✅ Remove hardcoded Cloudflare tunnel URL in `config.py:96`
- ✅ Make WebSocket URL dynamic based on environment variable
- ✅ Update Flask DEBUG mode to False for production (config.py:111)

### 3. Prepare deployment checklist
- Verify all API keys are in `.env` file
- Document all environment variables needed
- Create backup of `knowledge_base.txt`

---

## Phase 2: DigitalOcean Droplet Setup

### 1. Create Droplet
- Log into DigitalOcean dashboard
- Click "Create" → "Droplets"
- Choose: Ubuntu 22.04 LTS (recommended)
- Plan: Basic ($12/month minimum - needs 2GB RAM for your app)
- Datacenter: Choose closest to your users
- Authentication: SSH keys (recommended) or password
- Hostname: `phone-agent-server` or similar

### 2. Initial Server Access
```bash
ssh root@your_droplet_ip
```

### 3. Create non-root user with sudo
```bash
adduser phoneagent
usermod -aG sudo phoneagent
su - phoneagent
```

---

## Phase 3: Server Dependencies Installation

### 1. Update system packages
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Python 3.11+ and pip
```bash
sudo apt install -y python3.11 python3.11-venv python3-pip
```

### 3. Install ffmpeg (required for pydub/audio processing)
```bash
sudo apt install -y ffmpeg
```

### 4. Install Nginx
```bash
sudo apt install -y nginx
```

### 5. Install Node.js and PM2
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pm2
```

### 6. Install monitoring tools
```bash
sudo apt install -y htop nethogs
pm2 install pm2-logrotate
```

### 7. Configure firewall
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw allow 5000  # Flask port (behind Nginx)
sudo ufw enable
```

---

## Phase 4: Application Deployment

### 1. Create application directory
```bash
sudo mkdir -p /opt/phone-agent
sudo chown phoneagent:phoneagent /opt/phone-agent
cd /opt/phone-agent
```

### 2. Transfer code to server

**Option A - Using Git (recommended):**
```bash
# On server
git clone your_repository_url .
```

**Option B - Using SCP from local machine:**
```bash
# On local machine (PowerShell/CMD)
scp -r C:\Users\khawo\PycharmProjects\Phone-agent\* phoneagent@your_droplet_ip:/opt/phone-agent/
```

**Option C - Using rsync (if available):**
```bash
# On local machine (WSL or Git Bash)
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'temp_audio' \
  /mnt/c/Users/khawo/PycharmProjects/Phone-agent/ phoneagent@your_droplet_ip:/opt/phone-agent/
```

### 3. Create virtual environment
```bash
cd /opt/phone-agent
python3.11 -m venv venv
source venv/bin/activate
```

### 4. Install Python dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn  # Production WSGI server
```

### 5. Create necessary directories
```bash
mkdir -p temp_audio transcripts logs backups
chmod 755 temp_audio transcripts logs backups
```

### 6. Configure environment variables
```bash
nano .env
```
Add all your environment variables:
```env
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_number
DEEPGRAM_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
SALES_FORWARD_NUMBER=+18166741783
WEBSOCKET_URL=wss://YOUR_DROPLET_IP/media
PAUSE_THRESHOLD=0.3
RESPONSE_TIMEOUT=15.0
```

---

## Phase 5: SSL Certificate Setup (Let's Encrypt)

### 1. Install Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Get SSL certificate

**For Droplet IP (self-signed for testing):**
```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/nginx-selfsigned.key \
  -out /etc/ssl/certs/nginx-selfsigned.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=YOUR_DROPLET_IP"
```

**OR if you get a domain later:**
```bash
sudo certbot --nginx -d your_domain.com
```

---

## Phase 6: Nginx Configuration

### 1. Copy Nginx config file
```bash
sudo cp /opt/phone-agent/nginx-phone-agent.conf /etc/nginx/sites-available/phone-agent
```

### 2. Update server_name in config
```bash
sudo nano /etc/nginx/sites-available/phone-agent
# Replace "your_droplet_ip" with actual IP address
```

### 3. Enable site and test configuration
```bash
sudo ln -s /etc/nginx/sites-available/phone-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## Phase 7: PM2 Process Manager Setup

### 1. Start application with PM2
```bash
cd /opt/phone-agent
pm2 start ecosystem.config.js
pm2 save
pm2 startup
# Follow the instructions from the startup command (copy/paste the command it gives you)
```

### 2. Monitor application
```bash
pm2 status
pm2 logs phone-agent
pm2 monit
```

---

## Phase 8: System Monitoring Setup

### 1. Install monitoring tools
```bash
sudo apt install -y prometheus-node-exporter
```

### 2. Make health check script executable
```bash
chmod +x /opt/phone-agent/health_check.sh
```

### 3. Add to crontab (runs every 5 minutes)
```bash
crontab -e
```
Add:
```
*/5 * * * * /opt/phone-agent/health_check.sh
```

---

## Phase 9: Backup Configuration

### 1. Make backup script executable
```bash
chmod +x /opt/phone-agent/backup.sh
```

### 2. Schedule daily backups
```bash
crontab -e
```
Add:
```
0 2 * * * /opt/phone-agent/backup.sh
```

---

## Phase 10: Twilio Configuration

### 1. Get your Droplet's public IP
```bash
curl ifconfig.me
```

### 2. Update Twilio webhook URLs
- Log into Twilio Console: https://console.twilio.com/
- Go to Phone Numbers → Active Numbers
- Click your phone number
- Under "Voice & Fax":
  - Webhook URL: `https://YOUR_DROPLET_IP/voice`
  - Method: HTTP POST
- Click "Save"

### 3. Update .env file with correct WebSocket URL
```bash
nano /opt/phone-agent/.env
# Update: WEBSOCKET_URL=wss://YOUR_DROPLET_IP/media
```

### 4. Restart application
```bash
pm2 restart phone-agent
```

---

## Phase 11: Testing & Validation

### 1. Test health endpoint
```bash
curl http://localhost:5000/
# Should return: "Phone Agent Running!"
```

### 2. Test via public IP (HTTP)
```bash
curl http://YOUR_DROPLET_IP/
```

### 3. Test via public IP (HTTPS)
```bash
curl -k https://YOUR_DROPLET_IP/
# -k flag ignores self-signed certificate warning
```

### 4. Check logs
```bash
pm2 logs phone-agent --lines 50
sudo tail -f /var/log/nginx/phone-agent-error.log
sudo tail -f /var/log/nginx/phone-agent-access.log
```

### 5. Test phone call
- Call your Twilio number from your phone
- Verify greeting plays: "TEMCO, how can I help you?"
- Speak and verify transcription works
- Check transcript files:
```bash
ls -lh /opt/phone-agent/transcripts/
cat /opt/phone-agent/transcripts/latest_file.txt
```

### 6. Monitor resources
```bash
htop  # CPU/RAM usage (press q to quit)
pm2 monit  # PM2 dashboard
df -h  # Disk space
```

---

## Phase 12: Post-Deployment Maintenance

### Daily Tasks
```bash
# Check application status
pm2 status
pm2 logs phone-agent --lines 50

# Monitor disk space
df -h

# Check for errors
sudo tail -50 /var/log/nginx/phone-agent-error.log
```

### Weekly Tasks
```bash
# Review logs
ls -lh /opt/phone-agent/logs/

# Check backups
ls -lh /opt/phone-agent/backups/

# Update system packages
sudo apt update && sudo apt upgrade -y
sudo systemctl restart nginx
pm2 restart phone-agent
```

### Monthly Tasks
- Review and archive old transcripts
- Check SSL certificate expiry (if using Let's Encrypt)
- Review API usage and costs (Twilio, Deepgram, Anthropic, ElevenLabs)
- Review PM2 logs and rotate if needed

---

## Quick Reference Commands

### Application Management
```bash
# Start/stop/restart
pm2 start phone-agent
pm2 stop phone-agent
pm2 restart phone-agent
pm2 reload phone-agent  # Zero-downtime restart

# View logs
pm2 logs phone-agent
pm2 logs phone-agent --lines 100
pm2 logs phone-agent --err  # Only errors

# Monitor
pm2 monit
pm2 status
pm2 info phone-agent

# Clear logs
pm2 flush phone-agent
```

### Nginx Management
```bash
# Status
sudo systemctl status nginx

# Restart/reload
sudo systemctl restart nginx
sudo systemctl reload nginx  # Graceful reload

# Test configuration
sudo nginx -t

# View logs
sudo tail -f /var/log/nginx/phone-agent-error.log
sudo tail -f /var/log/nginx/phone-agent-access.log
```

### System Monitoring
```bash
# Disk usage
df -h
du -sh /opt/phone-agent/transcripts/
du -sh /opt/phone-agent/temp_audio/

# Memory usage
free -h

# CPU/Process monitoring
htop
top

# Network monitoring
nethogs  # Real-time bandwidth usage
sudo netstat -tulpn | grep :5000  # Check port 5000
```

### Application Logs
```bash
# PM2 logs
tail -f /opt/phone-agent/logs/pm2-out.log
tail -f /opt/phone-agent/logs/pm2-error.log

# Health check log
tail -f /opt/phone-agent/logs/health-check.log

# Backup log
tail -f /opt/phone-agent/logs/backup.log
```

### Update Code
```bash
# Pull latest code
cd /opt/phone-agent
git pull

# Restart application
pm2 restart phone-agent

# If dependencies changed
source venv/bin/activate
pip install -r requirements.txt
pm2 restart phone-agent
```

### Troubleshooting
```bash
# Application not responding
pm2 restart phone-agent

# Check if port 5000 is listening
sudo netstat -tulpn | grep :5000

# Check Nginx is proxying correctly
curl http://localhost:5000/

# Check WebSocket connection
sudo tail -f /var/log/nginx/phone-agent-access.log
# Make a test call and watch for /media requests

# Disk full
df -h
du -sh /opt/phone-agent/transcripts/*
# Clean old transcripts if needed
find /opt/phone-agent/transcripts -mtime +30 -delete

# Python errors
source /opt/phone-agent/venv/bin/activate
python /opt/phone-agent/app.py  # Run directly to see errors
```

---

## Security Checklist

- [ ] Firewall configured (UFW enabled)
- [ ] Non-root user created
- [ ] SSH key authentication enabled (disable password auth)
- [ ] `.env` file has correct permissions (600)
- [ ] SSL certificate installed
- [ ] Nginx security headers configured
- [ ] Regular backups scheduled
- [ ] System updates automated or scheduled weekly

---

## Environment Variables Reference

Required variables in `.env`:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# Deepgram Speech-to-Text
DEEPGRAM_API_KEY=your_deepgram_key

# Anthropic Claude AI
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
CLAUDE_MODEL=claude-3-haiku-20240307

# ElevenLabs Text-to-Speech
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
ELEVENLABS_MODEL=eleven_turbo_v2_5

# Application Configuration
WEBSOCKET_URL=wss://YOUR_DROPLET_IP/media
PAUSE_THRESHOLD=0.3
RESPONSE_TIMEOUT=15.0
PREDICTIVE_RESPONSES=True
INTERIM_STABILITY_THRESHOLD=3

# Call Forwarding
SALES_FORWARD_NUMBER=+18166741783
```

---

## Support & Resources

- **DigitalOcean Docs**: https://docs.digitalocean.com/
- **PM2 Documentation**: https://pm2.keymetrics.io/docs/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Twilio Documentation**: https://www.twilio.com/docs

---

## Estimated Costs

- **DigitalOcean Droplet**: $12/month (2GB RAM, 50GB SSD)
- **Twilio Phone Number**: $1/month
- **Twilio Voice**: $0.0130/min inbound, $0.0140/min outbound
- **Deepgram**: Pay-as-you-go (check current pricing)
- **Anthropic Claude**: Pay-as-you-go (check current pricing)
- **ElevenLabs**: Varies by plan (check current pricing)

**Total Infrastructure**: ~$15-20/month + API usage costs

---

**Last Updated**: 2025-01-XX
**Version**: 1.0
