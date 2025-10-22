"""
Simple WebSocket test client
"""
import socketio

# Create SocketIO client
sio = socketio.Client()

@sio.event
def connect():
    print("✅ Connected to WebSocket server!")

@sio.event
def disconnect():
    print("❌ Disconnected from WebSocket server")

@sio.event
def connect_error(data):
    print(f"❌ Connection failed: {data}")

# Connect to your server
try:
    print("Attempting to connect to ws://localhost:5000/media")
    sio.connect('http://localhost:5000', namespaces=['/media'])
    print("Connection successful!")
    sio.disconnect()
except Exception as e:
    print(f"Error: {e}")
