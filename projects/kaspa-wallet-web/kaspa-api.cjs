// Kaspa Testnet-12 API proxy
// Connects to local kaspad via gRPC (port 16210)

const http = require('http');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const path = require('path');

const PORT = 18806;
const GRPC_HOST = '127.0.0.1:16210';

// ============================================================
// Bech32/Bech32m address translation
// KNG wallet generates bech32m addresses, but our kaspad only
// understands bech32. We translate on the fly in the proxy.
// ============================================================

const BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';

// Exact Kaspa bech32 — ported from rusty-kaspa/crypto/addresses/src/bech32.rs
function polymod(values) {
    // values is an array of u8
    let c = 1n;
    for (const d of values) {
        const c0 = c >> 35n;
        c = ((c & 0x07ffffffffn) << 5n) ^ BigInt(d);
        if (c0 & 0x01n) c ^= 0x98f2bc8e61n;
        if (c0 & 0x02n) c ^= 0x79b76d99e2n;
        if (c0 & 0x04n) c ^= 0xf33e5fb3c4n;
        if (c0 & 0x08n) c ^= 0xae2eabe2a8n;
        if (c0 & 0x10n) c ^= 0x1e4f43e470n;
    }
    return c ^ 1n;  // XOR 1 at end
}

function conv8to5(bytes) {
    const padding = (bytes.length * 8 % 5 === 0) ? 0 : 1;
    const result = new Array(Math.floor(bytes.length * 8 / 5) + padding);
    let idx = 0, buff = 0, bits = 0;
    for (const b of bytes) {
        buff = (buff << 8) | b;
        bits += 8;
        while (bits >= 5) { bits -= 5; result[idx++] = (buff >> bits) & 31; }
    }
    if (bits > 0) result[idx] = (buff << (5 - bits)) & 31;
    return result;
}

function kaspaChecksum(payload5bit, prefix) {
    // prefix: each byte & 0x1f, then [0], then payload, then 8 zeros
    const fivebitPrefix = [...Buffer.from(prefix)].map(b => b & 0x1f);
    const values = [...fivebitPrefix, 0, ...payload5bit, 0, 0, 0, 0, 0, 0, 0, 0];
    return polymod(values);
}

function bech32Encode(hrp, payload5bit) {
    const checksumVal = kaspaChecksum(payload5bit, hrp);
    // checksum → 5 big-endian bytes (bytes 3..8 of u64) → conv8to5 → 8 chars
    const checksumBytes = [];
    for (let i = 4; i >= 0; i--) checksumBytes.push(Number((checksumVal >> BigInt(i * 8)) & 0xffn));
    const checksum5bit = conv8to5(checksumBytes);
    return hrp + ':' + [...payload5bit, ...checksum5bit].map(v => BECH32_CHARSET[v]).join('');
}

function decodeBech32Data(addrStr) {
    // Extract prefix and data part
    const colonIdx = addrStr.indexOf(':');
    if (colonIdx === -1) return null;
    const hrp = addrStr.slice(0, colonIdx);
    const dataPart = addrStr.slice(colonIdx + 1);
    
    const values = [];
    for (const c of dataPart) {
        const idx = BECH32_CHARSET.indexOf(c);
        if (idx === -1) return null;
        values.push(idx);
    }
    
    // version = first 5-bit value, payload = middle, checksum = last 8
    const version = values[0];
    const payload5bit = values.slice(1, -8);
    
    // Convert 5-bit to 8-bit
    let acc = 0, bits = 0;
    const payload = [];
    for (const v of payload5bit) {
        acc = (acc << 5) | v;
        bits += 5;
        while (bits >= 8) { bits -= 8; payload.push((acc >> bits) & 0xff); }
    }
    
    return { hrp, version, payload: Buffer.from(payload), data5bit: [version, ...payload5bit] };
}

function reencodeAddress(addrStr) {
    const decoded = decodeBech32Data(addrStr);
    if (!decoded) return addrStr;  // can't decode, pass through
    // Re-encode with standard bech32 checksum
    return bech32Encode(decoded.hrp, decoded.data5bit);
}

// Translate addresses in requests so kaspad can understand them
function translateAddress(addr) {
    try {
        return reencodeAddress(addr);
    } catch {
        return addr;  // pass through on error
    }
}

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
                const translated = translateAddress(params.address);
                console.log(`[balance] ${params.address === translated ? '' : 'translated: '}${translated}`);
                const r = await rpcCall(
                    'getBalanceByAddressRequest',
                    'getBalanceByAddressResponse', 
                    { address: translated }
                );
                result = { balance: parseInt(r.balance || '0') };
                break;
            }
            
            case 'getUtxosByAddresses': {
                const translated = (params.addresses || []).map(a => translateAddress(a));
                const r = await rpcCall(
                    'getUtxosByAddressesRequest',
                    'getUtxosByAddressesResponse',
                    { addresses: translated }
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
            
            case 'signAndSubmitTransaction': {
                // POC: sign transaction server-side using Python kaspa SDK
                // ⚠️ Private key is sent to server - testnet only!
                const { execFile } = require('child_process');
                const signResult = await new Promise((resolve, reject) => {
                    const args = ['-c', `
import asyncio, json, kaspa, sys

async def main():
    p = json.loads(sys.argv[1])
    pk = kaspa.PrivateKey(p['privateKey'])
    dest = kaspa.Address(p['toAddress'])
    my_addr = kaspa.Address(p['fromAddress'])
    amount = int(p['amount'])
    fee = 10000

    client = kaspa.RpcClient(url='ws://127.0.0.1:17210')
    await client.connect()
    resp = await client.get_utxos_by_addresses({'addresses': [p['fromAddress']]})
    entries = resp.get('entries', resp) if isinstance(resp, dict) else resp

    selected = []
    total = 0
    for e in sorted(entries, key=lambda x: int(x['utxoEntry']['amount']), reverse=True):
        selected.append(e)
        total += int(e['utxoEntry']['amount'])
        if total >= amount + fee:
            break

    if total < amount + fee:
        print(json.dumps({'error': f'Insufficient: have {total}, need {amount+fee}'}))
        return

    change = total - amount - fee
    outputs = [kaspa.PaymentOutput(dest, amount)]
    if change > 0:
        outputs.append(kaspa.PaymentOutput(my_addr, change))

    tx = kaspa.create_transaction(selected, outputs, 0)
    kaspa.sign_transaction(tx, [pk] * len(selected), True)
    result = await client.submit_transaction({'transaction': tx, 'allow_orphan': False})
    await client.disconnect()
    print(json.dumps({'transactionId': result.get('transactionId', str(result))}))

asyncio.run(main())
`, JSON.stringify({
                        privateKey: params.privateKey || params.transaction?.privateKey,
                        toAddress: params.toAddress || params.transaction?.toAddress,
                        fromAddress: params.fromAddress || params.transaction?.fromAddress,
                        amount: String(params.amount || params.transaction?.amount)
                    })];
                    execFile('python3', args, { timeout: 30000 }, (err, stdout, stderr) => {
                        if (err) return reject(new Error(stderr || err.message));
                        try { resolve(JSON.parse(stdout.trim())); }
                        catch { reject(new Error(stdout || 'Parse error')); }
                    });
                });
                if (signResult.error) throw new Error(signResult.error);
                result = signResult;
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
