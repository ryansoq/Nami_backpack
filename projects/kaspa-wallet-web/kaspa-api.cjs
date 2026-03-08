// Kaspa Testnet-12 API proxy
// Connects to local kaspad via gRPC (port 16210)

const http = require('http');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const path = require('path');

const PORT = 18806;
const GRPC_HOST = '127.0.0.1:16210';

// Load proto files
const PROTO_DIR = path.join(process.env.HOME, 'rusty-kaspa/rpc/grpc/core/proto');
const packageDef = protoLoader.loadSync(
    [path.join(PROTO_DIR, 'messages.proto'), path.join(PROTO_DIR, 'rpc.proto')],
    { keepCase: true, longs: String, enums: String, defaults: true, oneofs: true, includeDirs: [PROTO_DIR] }
);
const proto = grpc.loadPackageDefinition(packageDef).protowire;

// Create gRPC client
const client = new proto.RPC(GRPC_HOST, grpc.credentials.createInsecure());

// Helper: make a gRPC streaming call (kaspad uses bidirectional streaming)
function rpcCall(requestField, responseField, requestData) {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('gRPC timeout')), 10000);
        
        const stream = client.MessageStream();
        
        stream.on('data', (msg) => {
            clearTimeout(timeout);
            if (msg[responseField]) {
                const resp = msg[responseField];
                if (resp.error && resp.error.message) {
                    reject(new Error(resp.error.message));
                } else {
                    resolve(resp);
                }
            }
            stream.end();
        });
        
        stream.on('error', (e) => {
            clearTimeout(timeout);
            reject(e);
        });
        
        // Send request
        const message = {};
        message[requestField] = requestData;
        stream.write(message);
    });
}

const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
    
    let urlPath = req.url.replace(/^\/kaspa\/api\//, '').replace(/^\/api\//, '').replace(/^\//, '');
    const method = urlPath.split('?')[0];
    
    if (req.method === 'GET' && method === 'status') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok', network: 'testnet-12' }));
        return;
    }
    
    if (req.method !== 'POST') {
        res.writeHead(405, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Method not allowed' }));
        return;
    }
    
    let body = '';
    for await (const chunk of req) body += chunk;
    let params = {};
    try { params = JSON.parse(body); } catch {}
    
    try {
        let result;
        
        switch (method) {
            case 'getBalanceByAddress': {
                const r = await rpcCall(
                    'getBalanceByAddressRequest',
                    'getBalanceByAddressResponse', 
                    { address: params.address }
                );
                result = { balance: parseInt(r.balance || '0') };
                break;
            }
            
            case 'getUtxosByAddresses': {
                const r = await rpcCall(
                    'getUtxosByAddressesRequest',
                    'getUtxosByAddressesResponse',
                    { addresses: params.addresses }
                );
                result = { entries: r.entries || [] };
                break;
            }
            
            case 'getBlockDagInfo': {
                const r = await rpcCall(
                    'getBlockDagInfoRequest',
                    'getBlockDagInfoResponse',
                    {}
                );
                result = r;
                break;
            }
            
            case 'getServerInfo': {
                const r = await rpcCall(
                    'getServerInfoRequest',
                    'getServerInfoResponse',
                    {}
                );
                result = r;
                break;
            }
            
            case 'submitTransaction': {
                const r = await rpcCall(
                    'submitTransactionRequest',
                    'submitTransactionResponse',
                    { transaction: params.transaction, allowOrphan: false }
                );
                result = r;
                break;
            }
            
            default:
                res.writeHead(404, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: `Unknown method: ${method}` }));
                return;
        }
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(result));
        
    } catch (e) {
        console.error(`Error [${method}]:`, e.message);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
    }
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`Kaspa API proxy on :${PORT} → kaspad gRPC ${GRPC_HOST}`);
});
