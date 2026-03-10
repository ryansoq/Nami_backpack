const http = require('http');
const fs = require('fs');
const path = require('path');
let WebSocket, WebSocketServer;
try { ({ WebSocket, WebSocketServer } = require('ws')); } catch(e) {}

const PORT = 18807;
const KASPAD_WS = 'ws://127.0.0.1:17210';
const DIR = __dirname;

const MIME = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
};

const server = http.createServer((req, res) => {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    // Proxy /api/* to kaspa-api (port 18806)
    if (req.url.startsWith('/api/') || req.url.startsWith('/kaspa/api/')) {
        const proxyPath = req.url.replace(/^\/kaspa\/api\//, '/api/').replace(/^\/api\//, '');
        const options = {
            hostname: '127.0.0.1',
            port: 18806,
            path: '/' + proxyPath,
            method: req.method,
            headers: req.headers,
        };
        const proxyReq = http.request(options, (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers);
            proxyRes.pipe(res);
        });
        proxyReq.on('error', () => {
            res.writeHead(502, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'API proxy error' }));
        });
        req.pipe(proxyReq);
        return;
    }

    // Proxy /whisper/* to whisper API (port 18803)
    if (req.url.startsWith('/whisper/')) {
        const proxyPath = req.url.replace(/^\/whisper/, '');
        const options = {
            hostname: '127.0.0.1',
            port: 18803,
            path: proxyPath || '/',
            method: req.method,
            headers: req.headers,
        };
        const proxyReq = http.request(options, (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers);
            proxyRes.pipe(res);
        });
        proxyReq.on('error', () => {
            res.writeHead(502, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Whisper proxy error' }));
        });
        req.pipe(proxyReq);
        return;
    }

    // Static files
    let urlPath = req.url.split('?')[0];
    if (urlPath === '/') urlPath = '/index.html';
    // Strip /kaspa/ prefix if someone still uses old path
    urlPath = urlPath.replace(/^\/kaspa\//, '/');

    const filePath = path.join(DIR, urlPath);
    // Security: prevent path traversal
    if (!filePath.startsWith(DIR)) { res.writeHead(403); res.end(); return; }

    fs.readFile(filePath, (err, data) => {
        if (err) {
            res.writeHead(404, { 'Content-Type': 'text/plain' });
            res.end('Not found');
            return;
        }
        const ext = path.extname(filePath);
        res.writeHead(200, { 
            'Content-Type': MIME[ext] || 'application/octet-stream',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache'
        });
        res.end(data);
    });
});

// WebSocket proxy: /ws → kaspad wRPC
if (WebSocketServer) {
    const wss = new WebSocketServer({ server, path: '/ws' });
    wss.on('connection', (clientWs) => {
        console.log('[ws-proxy] Client connected');
        const kaspadWs = new WebSocket(KASPAD_WS);
        kaspadWs.on('open', () => console.log('[ws-proxy] Connected to kaspad'));
        kaspadWs.on('message', (data) => clientWs.send(data));
        kaspadWs.on('close', () => clientWs.close());
        kaspadWs.on('error', (e) => { console.error('[ws-proxy]', e.message); clientWs.close(); });
        clientWs.on('message', (data) => { if (kaspadWs.readyState === WebSocket.OPEN) kaspadWs.send(data); });
        clientWs.on('close', () => kaspadWs.close());
    });
    console.log('WebSocket proxy /ws → kaspad enabled');
} else {
    console.log('ws module not found, mining proxy disabled. Run: npm install ws');
}

server.listen(PORT, '127.0.0.1', () => {
    console.log(`Kaspa Wallet server on :${PORT} → ${DIR}`);
});
