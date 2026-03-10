const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer, WebSocket } = require('ws');

const PORT = 8080;
const KASPAD_WS = 'ws://127.0.0.1:17210';

// Static file server
const mimeTypes = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
  '.json': 'application/json', '.png': 'image/png', '.ico': 'image/x-icon'
};

const server = http.createServer((req, res) => {
  let filePath = path.join(__dirname, req.url === '/' ? 'index.html' : req.url);
  const ext = path.extname(filePath);
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

// WebSocket proxy: /ws → kaspad wRPC
const wss = new WebSocketServer({ server, path: '/ws' });
wss.on('connection', (clientWs) => {
  console.log('[proxy] New client connected');
  const kaspadWs = new WebSocket(KASPAD_WS);
  
  kaspadWs.on('open', () => console.log('[proxy] Connected to kaspad'));
  kaspadWs.on('message', (data) => clientWs.send(data));
  kaspadWs.on('close', () => clientWs.close());
  kaspadWs.on('error', (e) => { console.error('[proxy] kaspad error:', e.message); clientWs.close(); });
  
  clientWs.on('message', (data) => {
    if (kaspadWs.readyState === WebSocket.OPEN) kaspadWs.send(data);
  });
  clientWs.on('close', () => kaspadWs.close());
});

server.listen(PORT, () => console.log(`🌊 Kas Portal running on http://0.0.0.0:${PORT}`));
