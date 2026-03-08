# Nami Eye 👁️

Web-based live camera streaming system. Open `/` on your phone to stream camera frames via WebSocket, view the live feed at `/view`.

## Usage
```bash
node server.js
# Camera: http://<host>:18805/
# Viewer: http://<host>:18805/view
# API:    http://<host>:18805/api/latest (JPEG)
#         http://<host>:18805/api/latest-base64
```

## Architecture
Single Node.js server, no framework. Phone camera → WebSocket → viewers + `/tmp/nami-eye-latest.jpg`.
