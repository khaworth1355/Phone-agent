module.exports = {
  apps: [{
    name: 'phone-agent',
    script: 'app.py',
    cwd: '/opt/phone-agent',
    interpreter: '/opt/phone-agent/venv/bin/python',
    env_file:'/opt/phone-agent/.env',
    // Environment
    env: {
      PYTHONPATH: '/opt/phone-agent',
      PYTHONUNBUFFERED: '1'
    },

    // Process management
    instances: 1,
    exec_mode: 'fork',
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',

    // Restart settings
    min_uptime: '10s',
    max_restarts: 10,
    restart_delay: 5000,

    // Logging
    error_file: '/opt/phone-agent/logs/pm2-error.log',
    out_file: '/opt/phone-agent/logs/pm2-out.log',
    log_file: '/opt/phone-agent/logs/pm2-combined.log',
    time: true,

    // Log rotation (requires pm2-logrotate module)
    // Install: pm2 install pm2-logrotate
    merge_logs: true,

    // Crash handling
    kill_timeout: 5000,
    listen_timeout: 10000,

    // Advanced settings
    instance_var: 'INSTANCE_ID',

    // Monitoring
    pmx: true
  }]
};
