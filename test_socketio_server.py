"""
Test SocketIO WITHOUT namespace
"""
import eventlet
eventlet.monkey_patch()

from flask import Flask, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=True, engineio_logger=True)

@app.route('/')
def home():
    return "Test server running"

@socketio.on('connect')
def handle_connect():
    print("✅ WebSocket connected (no namespace)!")
    print(f"   Request SID: {request.sid}")
    print(f"   Request environ keys: {list(request.environ.keys())[:10]}")

@socketio.on('message')
def handle_message(msg):
    print(f"📩 Message received: {msg}")

@socketio.on('disconnect')
def handle_disconnect():
    print("❌ WebSocket disconnected")

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🧪 TEST SERVER - NO NAMESPACE")
    print("="*60)
    print("HTTP: http://localhost:5000")
    print("WebSocket: ws://localhost:5000")
    print("="*60 + "\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)