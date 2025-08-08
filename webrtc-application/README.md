# WebRTC Video App

## Components
- Signaling server (Node.js + socket.io)
- Web client (vanilla HTML/JS + WebRTC)
- Python client (aiortc)

## Setup

### 1. Run Signaling Server
```
cd signaling-server
npm install
node server.js
```

### 2. Open Web Client
```
cd web-client
Open index.html in a browser (use 2 tabs or different devices)
```

### 3. Run Python Client (if ready)
```
cd python-client
pip install -r requirements.txt
python client.py
```

## Network Notes
- Use your machine’s IP, not "localhost", for multi-device connections
- Use STUN/TURN for internet or remote use

