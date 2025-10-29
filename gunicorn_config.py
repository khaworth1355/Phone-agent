"""
Gunicorn Configuration for Phone Agent
Production WSGI server configuration
"""
import multiprocessing
import os

# Server socket
bind = "127.0.0.1:5000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn-access.log")
errorlog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn-error.log")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "phone-agent"

# Server mechanics
daemon = False
pidfile = os.path.join(os.path.dirname(__file__), "logs", "gunicorn.pid")

# User and group (update these on server)
# user = "phoneagent"
# group = "phoneagent"

# Preload application
preload_app = False

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

print(f"[Gunicorn] Starting with {workers} workers")
print(f"[Gunicorn] Binding to {bind}")
print(f"[Gunicorn] Logging to {errorlog}")
