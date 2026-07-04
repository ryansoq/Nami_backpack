// Kaspa Testnet-12 Web Wallet
// BIP-39 mnemonic + BIP-32 key derivation
// Pure browser-based, no private keys leave the client

// ============================================================
// Crypto helpers - secp256k1 (Schnorr) + Kaspa address encoding
// ============================================================

let secp;
const NETWORK_PREFIX = 'kaspatest';

// BIP-39 / BIP-32 modules
let bip39, bip32, hmacMod, sha512Mod;

async function loadSecp256k1() {
    const mod = await import('https://esm.sh/@noble/secp256k1@2.1.0');
    secp = mod;
    const hashes = await import('https://esm.sh/@noble/hashes@1.6.1/sha256');
    const utils = await import('https://esm.sh/@noble/hashes@1.6.1/utils');
    return { secp: mod, sha256: hashes.sha256, bytesToHex: utils.bytesToHex, hexToBytes: utils.hexToBytes };
}

async function loadBip39Bip32() {
    // Load scure-bip39 and scure-bip32 (from same author as noble-secp256k1)
    const [bip39Mod, bip32Mod, wordlistMod, hmac, sha512] = await Promise.all([
        import('https://esm.sh/@scure/bip39@1.4.0'),
        import('https://esm.sh/@scure/bip32@1.5.0'),
        import('https://esm.sh/@scure/bip39@1.4.0/wordlists/english'),
        import('https://esm.sh/@noble/hashes@1.6.1/hmac'),
        import('https://esm.sh/@noble/hashes@1.6.1/sha512'),
    ]);
    bip39 = { ...bip39Mod, wordlist: wordlistMod.wordlist };
    bip32 = bip32Mod;
    hmacMod = hmac;
    sha512Mod = sha512;
}

let cryptoLib;

async function init() {
    cryptoLib = await loadSecp256k1();
    await loadBip39Bip32();
}

// ============================================================
// BIP-39 Mnemonic + BIP-32 Key Derivation
// ============================================================

// Kaspa derivation path: m/44'/111111'/0'/0/0
const KASPA_DERIVATION_PATH = "m/44'/111111'/0'/0/0";

function generateMnemonic() {
    return bip39.generateMnemonic(bip39.wordlist, 128); // 128 bits = 12 words
}

function validateMnemonic(mnemonic) {
    return bip39.validateMnemonic(mnemonic, bip39.wordlist);
}

function derivePrivateKeyFromMnemonic(mnemonic) {
    const seed = bip39.mnemonicToSeedSync(mnemonic);
    const hdKey = bip32.HDKey.fromMasterSeed(seed);
    const child = hdKey.derive(KASPA_DERIVATION_PATH);
    return cryptoLib.bytesToHex(child.privateKey);
}

// Generate a random 32-byte private key (fallback, used for raw import)
function generatePrivateKey() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return cryptoLib.bytesToHex(bytes);
}

// Get public key (x-only for schnorr, 32 bytes)
function getPublicKey(privKeyHex) {
    const pubKey = secp.getPublicKey(privKeyHex, true); // compressed 33 bytes
    return pubKey.slice(1); // remove 02/03 prefix → x-only 32 bytes
}

// ============================================================
// Kaspa Address encoding (cashaddr variant)
// ============================================================

const CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';

function polymod(values) {
    let c = 1n;
    for (const v of values) {
        const c0 = c >> 35n;
        c = ((c & 0x07ffffffffn) << 5n) ^ BigInt(v);
        if (c0 & 1n) c ^= 0x98f2bc8e61n;
        if (c0 & 2n) c ^= 0x79b76d99e2n;
        if (c0 & 4n) c ^= 0xf33e5fb3c4n;
        if (c0 & 8n) c ^= 0xae2eabe2a8n;
        if (c0 & 16n) c ^= 0x1e4f43e470n;
    }
    return c ^ 1n;
}

function prefixExpand(prefix) {
    const result = [];
    for (let i = 0; i < prefix.length; i++) {
        result.push(prefix.charCodeAt(i) & 0x1f);
    }
    result.push(0);
    return result;
}

function convertBits(data, fromBits, toBits, pad) {
    let acc = 0, bits = 0;
    const result = [];
    const maxv = (1 << toBits) - 1;
    for (const value of data) {
        acc = (acc << fromBits) | value;
        bits += fromBits;
        while (bits >= toBits) {
            bits -= toBits;
            result.push((acc >> bits) & maxv);
        }
    }
    if (pad && bits > 0) {
        result.push((acc << (toBits - bits)) & maxv);
    }
    return result;
}

function createChecksum(prefix, payload) {
    const values = [...prefixExpand(prefix), ...payload, 0, 0, 0, 0, 0, 0, 0, 0];
    const poly = polymod(values);
    const result = [];
    for (let i = 0; i < 8; i++) {
        result.push(Number((poly >> BigInt(5 * (7 - i))) & 0x1fn));
    }
    return result;
}

function decodeCashAddr(addrStr) {
    const parts = addrStr.split(':');
    if (parts.length !== 2) throw new Error('Invalid address format');
    const prefix = parts[0];
    const data5bit = [];
    for (const c of parts[1]) {
        const idx = CHARSET.indexOf(c);
        if (idx === -1) throw new Error('Invalid character in address');
        data5bit.push(idx);
    }
    const values = [...prefixExpand(prefix), ...data5bit];
    if (polymod(values) !== 0n) throw new Error('Invalid checksum');
    const payload5bit = data5bit.slice(0, -8);
    const payload8bit = convertBits(payload5bit, 5, 8, false);
    const versionByte = payload8bit[0];
    const hash = payload8bit.slice(1);
    return { prefix, version: versionByte >> 3, hash: new Uint8Array(hash) };
}

function pubkeyToAddress(pubkeyBytes, prefix = NETWORK_PREFIX) {
    // Schnorr x-only pubkey (32 bytes), version=0 (PubKey)
    const versionByte = 0x00;
    const payload = [versionByte, ...pubkeyBytes];
    const payload5bit = convertBits(payload, 8, 5, true);
    const checksum = createChecksum(prefix, payload5bit);
    const combined = [...payload5bit, ...checksum];
    let addr = prefix + ':';
    for (const c of combined) {
        addr += CHARSET[c];
    }
    return addr;
}

// ============================================================
// PBKDF2 + AES-256-GCM encryption (Web Crypto API)
// ============================================================

async function deriveKey(password, salt) {
    const enc = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        'raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']
    );
    return crypto.subtle.deriveKey(
        { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' },
        keyMaterial,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
    );
}

async function encryptData(password, data) {
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await deriveKey(password, salt);
    const enc = new TextEncoder();
    const encrypted = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv },
        key,
        enc.encode(data)
    );
    const result = new Uint8Array(salt.length + iv.length + encrypted.byteLength);
    result.set(salt, 0);
    result.set(iv, salt.length);
    result.set(new Uint8Array(encrypted), salt.length + iv.length);
    return cryptoLib.bytesToHex(result);
}

async function decryptData(password, hexData) {
    const data = cryptoLib.hexToBytes(hexData);
    const salt = data.slice(0, 16);
    const iv = data.slice(16, 28);
    const ciphertext = data.slice(28);
    const key = await deriveKey(password, salt);
    const dec = new TextDecoder();
    const decrypted = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv },
        key,
        ciphertext
    );
    return dec.decode(decrypted);
}

// ============================================================
// IndexedDB storage
// ============================================================

function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open('KaspaWallet', 1);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains('wallet')) {
                db.createObjectStore('wallet');
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function dbGet(key) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction('wallet', 'readonly');
        const req = tx.objectStore('wallet').get(key);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function dbSet(key, value) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction('wallet', 'readwrite');
        tx.objectStore('wallet').put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function dbDelete(key) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction('wallet', 'readwrite');
        tx.objectStore('wallet').delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

// ============================================================
// RPC - Two paths: public REST (default) or local proxy
// ============================================================
//
// 2026-05-10 rewrite: backend kaspad + kaspa-api.cjs proxy died after
// 4/3 mining pause and quant.openclaw-alpha.com took the 18806 port.
// Rather than ship without revival, route read/write wallet ops through
// the public testnet REST endpoint (api-tn12.kaspa.org) — no backend
// needed, works in any browser. Mining-specific methods (getBlockTemplate
// / submitBlock) stay on the proxy path; they remain disabled until
// local kaspad is brought back.
//
// Source is selectable at runtime via Settings → "RPC Source":
//   'public' — api-tn12.kaspa.org (default; balance/utxos/send work,
//              mining returns a clear "needs local kaspad" error)
//   'proxy'  — same /api/* backend as before (kaspa-api.cjs); full
//              feature set including mining when backend is up.
//
// Stored in localStorage so user choice persists across reloads.

// Auto-detect proxy base path (standalone /api/ vs embedded /kaspa/api/).
const PROXY_BASE = window.location.pathname.startsWith('/kaspa') ? '/kaspa/api' : '/api';
const PUBLIC_REST_BASE = 'https://api-tn12.kaspa.org';

const RPC_MINING_METHODS = new Set(['getBlockTemplate', 'submitBlock', 'getBlockDagInfo']);

let rpcSource = localStorage.getItem('rpcSource') || 'public';
export function setRpcSource(s) {
    rpcSource = s;
    localStorage.setItem('rpcSource', s);
}
export function getRpcSource() { return rpcSource; }

// Mapping from kaspad RPC method → REST call.
// Returns the parsed JSON body of the REST response (already shaped to
// look like the proxy's response so callers don't care about the source).
async function publicRestCall(method, params) {
    if (RPC_MINING_METHODS.has(method)) {
        throw new Error(
            `${method} requires local kaspad. Switch RPC source to "Local Proxy" ` +
            `in Settings (and ensure kaspa-api.cjs + kaspad are running).`
        );
    }
    if (method === 'getBalanceByAddress') {
        const addr = params.address;
        const r = await fetch(`${PUBLIC_REST_BASE}/addresses/${encodeURIComponent(addr)}/balance`);
        if (!r.ok) throw new Error(`REST ${r.status}`);
        const j = await r.json();
        return { balance: j.balance };
    }
    if (method === 'getUtxosByAddresses') {
        const addr = params.addresses[0];
        const r = await fetch(`${PUBLIC_REST_BASE}/addresses/${encodeURIComponent(addr)}/utxos`);
        if (!r.ok) throw new Error(`REST ${r.status}`);
        const j = await r.json();
        // Public REST returns a list shaped like [{outpoint, utxoEntry}]; the
        // proxy returned {entries: [...]}. Normalize so callers see the same.
        return { entries: Array.isArray(j) ? j : (j.entries || []) };
    }
    if (method === 'submitTransaction') {
        const r = await fetch(`${PUBLIC_REST_BASE}/transactions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transaction: params.transaction })
        });
        if (!r.ok) throw new Error(`REST ${r.status}: ${await r.text()}`);
        return r.json();
    }
    throw new Error(`Public REST: method "${method}" not mapped`);
}

async function proxyRpcCall(method, params) {
    const res = await fetch(`${PROXY_BASE}/${method}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
    });
    if (!res.ok) throw new Error(`RPC error: ${res.status}`);
    return res.json();
}

async function rpcCall(method, params = {}) {
    return rpcSource === 'public'
        ? publicRestCall(method, params)
        : proxyRpcCall(method, params);
}

async function getBalance(address) {
    try {
        const data = await rpcCall('getBalanceByAddress', { address });
        return data.balance || 0;
    } catch (e) {
        console.error('Balance fetch error:', e);
        return null;
    }
}

async function getUtxos(address) {
    try {
        const data = await rpcCall('getUtxosByAddresses', { addresses: [address] });
        return data.entries || [];
    } catch (e) {
        console.error('UTXO fetch error:', e);
        return [];
    }
}

async function submitTransaction(tx) {
    return rpcCall('submitTransaction', { transaction: tx });
}

// ============================================================
// Local Transaction Signing (browser-side, no private key leaves the client)
// Uses Blake2b-256 sighash (Kaspa consensus) + Schnorr signature
// ============================================================

let blake2bMod;

async function loadBlake2b() {
    if (!blake2bMod) {
        blake2bMod = await import('https://esm.sh/@noble/hashes@1.6.1/blake2b');
    }
    return blake2bMod;
}

// Blake2b-256 with key (personalization) — matches Kaspa's TransactionSigningHash
function sigHasher(key) {
    // @noble/hashes blake2b uses `key` option for keyed hashing
    return blake2bMod.blake2b.create({ dkLen: 32, key });
}

const SIG_HASH_ALL = 0x01;
const ZERO_HASH = new Uint8Array(32); // 32 zero bytes
const SUBNETWORK_ID_NATIVE = new Uint8Array(20); // 20 zero bytes
const TX_SIGNING_KEY = new TextEncoder().encode('TransactionSigningHash');

// Little-endian encoding helpers
function writeU8(v) { return new Uint8Array([v & 0xff]); }
function writeU16LE(v) { const b = new Uint8Array(2); new DataView(b.buffer).setUint16(0, v, true); return b; }
function writeU32LE(v) { const b = new Uint8Array(4); new DataView(b.buffer).setUint32(0, v, true); return b; }
function writeU64LE(v) {
    // v can be number or BigInt; we handle both
    const b = new Uint8Array(8);
    const dv = new DataView(b.buffer);
    const big = BigInt(v);
    dv.setUint32(0, Number(big & 0xFFFFFFFFn), true);
    dv.setUint32(4, Number((big >> 32n) & 0xFFFFFFFFn), true);
    return b;
}

function writeVarBytes(bytes) {
    // length as u64 LE, then the bytes
    const lenBytes = writeU64LE(bytes.length);
    const result = new Uint8Array(8 + bytes.length);
    result.set(lenBytes, 0);
    result.set(bytes, 8);
    return result;
}

function addressToScriptPublicKey(addr) {
    const decoded = decodeCashAddr(addr);
    const hashBytes = decoded.hash;
    // P2PK script: OP_DATA_32 <pubkey_hash> OP_CHECKSIG
    const script = new Uint8Array(34);
    script[0] = 0x20; // push 32 bytes
    script.set(hashBytes, 1);
    script[33] = 0xac; // OP_CHECKSIG
    return { script, version: 0 };
}

function hashScriptPublicKey(hasher, spk) {
    hasher.update(writeU16LE(spk.version));
    hasher.update(writeVarBytes(spk.script));
}

function hashOutpoint(hasher, txIdBytes, index) {
    hasher.update(txIdBytes); // 32 bytes
    hasher.update(writeU32LE(index));
}

function hashOutput(hasher, output) {
    hasher.update(writeU64LE(output.amount));
    hashScriptPublicKey(hasher, output.spk);
}

function hexToBytes32(hex) {
    // Transaction IDs in Kaspa are stored/displayed in natural byte order
    const bytes = cryptoLib.hexToBytes(hex);
    if (bytes.length !== 32) throw new Error(`Expected 32 bytes, got ${bytes.length}`);
    return bytes;
}

function calcPreviousOutputsHash(inputs) {
    const h = sigHasher(TX_SIGNING_KEY);
    for (const inp of inputs) {
        hashOutpoint(h, inp.txIdBytes, inp.index);
    }
    return h.digest();
}

function calcSequencesHash(inputs) {
    const h = sigHasher(TX_SIGNING_KEY);
    for (const inp of inputs) {
        h.update(writeU64LE(inp.sequence));
    }
    return h.digest();
}

function calcSigOpCountsHash(inputs) {
    const h = sigHasher(TX_SIGNING_KEY);
    for (const inp of inputs) {
        h.update(writeU8(inp.sigOpCount));
    }
    return h.digest();
}

function calcOutputsHash(outputs) {
    const h = sigHasher(TX_SIGNING_KEY);
    for (const out of outputs) {
        hashOutput(h, out);
    }
    return h.digest();
}

function calcPayloadHash(payloadBytes) {
    // Native subnetwork + empty payload = ZERO_HASH
    if (!payloadBytes || payloadBytes.length === 0) return ZERO_HASH;
    // Blake2b-256(key="TransactionSigningHash", varint_len + payload)
    const h = sigHasher(TX_SIGNING_KEY);
    h.update(writeU64LE(payloadBytes.length));  // var_bytes: length prefix
    h.update(payloadBytes);
    return h.digest();
}

function calcSigHash(tx, inputIndex, utxoEntry) {
    const h = sigHasher(TX_SIGNING_KEY);
    const inp = tx.inputs[inputIndex];

    // Precomputed hashes (SIG_HASH_ALL)
    h.update(writeU16LE(tx.version));                    // version
    h.update(tx._previousOutputsHash);                   // previous outputs hash
    h.update(tx._sequencesHash);                         // sequences hash
    h.update(tx._sigOpCountsHash);                       // sig op counts hash

    // Per-input data
    hashOutpoint(h, inp.txIdBytes, inp.index);           // outpoint
    hashScriptPublicKey(h, utxoEntry.spk);               // utxo script public key
    h.update(writeU64LE(utxoEntry.amount));               // utxo amount
    h.update(writeU64LE(inp.sequence));                   // sequence
    h.update(writeU8(inp.sigOpCount));                    // sig op count

    h.update(tx._outputsHash);                           // outputs hash
    h.update(writeU64LE(tx.lockTime));                    // lock time
    h.update(SUBNETWORK_ID_NATIVE);                      // subnetwork id (20 bytes)
    h.update(writeU64LE(0));                              // gas
    h.update(tx._payloadHash || ZERO_HASH);               // payload hash
    h.update(writeU8(SIG_HASH_ALL));                      // hash type

    return h.digest();
}

// Build, sign locally, and submit a transaction (all client-side!)
let schnorrMod = null;
async function loadSchnorr() {
    if (!schnorrMod) {
        const mod = await import('https://esm.sh/@noble/curves@1.7.0/secp256k1');
        schnorrMod = mod.schnorr;
    }
    return schnorrMod;
}
function schnorrSign(msgHash, privKey) {
    if (!schnorrMod) throw new Error('schnorr not loaded');
    return schnorrMod.sign(msgHash, privKey);
}

async function buildAndSendTransaction(privKeyHex, fromAddress, toAddress, amountSompi) {
    await loadBlake2b();
    await loadSchnorr();
    const { bytesToHex, hexToBytes } = cryptoLib;

    const pubKeyFull = secp.getPublicKey(privKeyHex, true); // 33 bytes compressed
    const pubKeyXOnly = pubKeyFull.slice(1); // 32 bytes x-only

    // Get UTXOs
    const utxos = await getUtxos(fromAddress);
    if (!utxos.length) throw new Error('No UTXOs available');

    // Select UTXOs (fee = 0.0001 KAS)
    const fee = 10000;
    const needed = amountSompi + fee;
    let total = 0;
    const selected = [];
    const sorted = [...utxos].sort((a, b) => parseInt(b.utxoEntry.amount) - parseInt(a.utxoEntry.amount));
    for (const u of sorted) {
        selected.push(u);
        total += parseInt(u.utxoEntry.amount);
        if (total >= needed) break;
    }
    if (total < needed) throw new Error(`Insufficient balance: have ${total/1e8}, need ${needed/1e8}`);

    const change = total - amountSompi - fee;

    const toSPK = addressToScriptPublicKey(toAddress);
    const fromSPK = addressToScriptPublicKey(fromAddress);

    // Build structured inputs
    const inputs = selected.map(u => ({
        txIdBytes: hexToBytes32(u.outpoint.transactionId),
        txId: u.outpoint.transactionId,
        index: u.outpoint.index,
        sequence: 0,
        sigOpCount: 1,
        utxoEntry: {
            amount: parseInt(u.utxoEntry.amount),
            spk: fromSPK  // all UTXOs belong to fromAddress
        }
    }));

    // Build outputs
    const outputs = [{ amount: amountSompi, spk: toSPK }];
    if (change > 0) {
        outputs.push({ amount: change, spk: fromSPK });
    }

    // Build tx object with precomputed hashes
    const tx = {
        version: 0,
        inputs,
        outputs,
        lockTime: 0,
        _previousOutputsHash: calcPreviousOutputsHash(inputs),
        _sequencesHash: calcSequencesHash(inputs),
        _sigOpCountsHash: calcSigOpCountsHash(inputs),
        _outputsHash: calcOutputsHash(outputs),
    };

    // Sign each input with Schnorr
    const signedInputs = [];
    for (let i = 0; i < inputs.length; i++) {
        const sigHash = calcSigHash(tx, i, inputs[i].utxoEntry);
        const sig = schnorrSign(sigHash, privKeyHex);
        const sigScript = new Uint8Array(1 + 64 + 1);
        sigScript[0] = 65; // push 65 bytes (sig + hashType)
        sigScript.set(sig, 1);
        sigScript[65] = SIG_HASH_ALL;

        signedInputs.push({
            previousOutpoint: {
                transactionId: inputs[i].txId,
                index: inputs[i].index
            },
            signatureScript: bytesToHex(sigScript),
            sequence: '0',
            sigOpCount: 1
        });
    }

    // Format outputs for submission
    const formattedOutputs = outputs.map(o => ({
        amount: o.amount.toString(),
        scriptPublicKey: {
            scriptPublicKey: bytesToHex(o.spk.script),
            version: o.spk.version
        }
    }));

    // Submit the signed transaction
    const submittedTx = {
        version: 0,
        inputs: signedInputs,
        outputs: formattedOutputs,
        lockTime: '0',
        subnetworkId: '0000000000000000000000000000000000000000',
        gas: '0',
        payload: ''
    };

    const result = await submitTransaction(submittedTx);
    return result;
}

// ============================================================
// ECIES Encryption/Decryption (browser-side)
// ============================================================

// ECIES encrypt — compatible with Python ecies library
// KDF: HKDF-SHA256(ephPub + sharedPoint) → 32-byte AES key
// Format: ephPub(65) + nonce(16) + tag(16) + ciphertext
async function eciesEncrypt(recipientPubKeyHex, plaintext) {
    const recipientPubBytes = cryptoLib.hexToBytes(recipientPubKeyHex);
    const ephPrivKey = secp.utils.randomPrivateKey();
    const ephPubKey = secp.getPublicKey(ephPrivKey, false); // uncompressed 65 bytes
    const sharedPoint = secp.getSharedSecret(ephPrivKey, recipientPubBytes, false); // uncompressed 65 bytes

    // KDF: HKDF-SHA256(master=ephPub+sharedPoint, salt="", info="", len=32)
    // Uses manual HKDF to match Python eciespy v0.4.6 exactly
    const aesKeyBits = await hkdfSha256(
        new Uint8Array([...ephPubKey, ...sharedPoint]),
        new Uint8Array(0),
        new Uint8Array(0),
        32
    );

    const nonce = crypto.getRandomValues(new Uint8Array(16));
    const key = await crypto.subtle.importKey('raw', aesKeyBits, 'AES-GCM', false, ['encrypt']);
    const enc = new TextEncoder();
    const encrypted = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv: nonce, tagLength: 128 },
        key,
        enc.encode(plaintext)
    );
    // AES-GCM output = ciphertext + tag(16)
    const encArray = new Uint8Array(encrypted);
    const ciphertext = encArray.slice(0, -16);
    const tag = encArray.slice(-16);
    // Output format: ephPub(65) + nonce(16) + tag(16) + ciphertext (matches Python ecies)
    const result = new Uint8Array(65 + 16 + 16 + ciphertext.length);
    result.set(ephPubKey, 0);
    result.set(nonce, 65);
    result.set(tag, 65 + 16);
    result.set(ciphertext, 65 + 16 + 16);
    return cryptoLib.bytesToHex(result);
}

async function eciesDecrypt(privKeyHex, ciphertextHex) {
    const data = cryptoLib.hexToBytes(ciphertextHex);
    const ephPubKey = data.slice(0, 65);
    const iv = data.slice(65, 81);
    const tag = data.slice(81, 97);
    const ciphertext = data.slice(97);

    // ECDH: get shared point (uncompressed, 65 bytes)
    // Web Wallet loads @noble/curves@1.7.0/secp256k1, so use schnorrMod's parent
    const sharedPoint = secp.getSharedSecret(privKeyHex, ephPubKey, false);

    // HKDF-SHA256: master = ephPub(65) + sharedPoint(65), salt="", info="", len=32
    // Manual HKDF to avoid Web Crypto API inconsistencies
    const aesKeyBits = await hkdfSha256(
        new Uint8Array([...ephPubKey, ...sharedPoint]),
        new Uint8Array(0),
        new Uint8Array(0),
        32
    );

    const key = await crypto.subtle.importKey('raw', aesKeyBits, 'AES-GCM', false, ['decrypt']);
    const encData = new Uint8Array(ciphertext.length + 16);
    encData.set(ciphertext, 0);
    encData.set(tag, ciphertext.length);
    const decrypted = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv, tagLength: 128 },
        key,
        encData
    );
    return new TextDecoder().decode(decrypted);
}

// Manual HKDF-SHA256 implementation (matches RFC 5869)
async function hkdfSha256(ikm, salt, info, length) {
    // Extract: PRK = HMAC-SHA256(salt, IKM)
    if (!salt || salt.length === 0) salt = new Uint8Array(32); // default salt = 32 zero bytes
    const saltKey = await crypto.subtle.importKey('raw', salt, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const prk = new Uint8Array(await crypto.subtle.sign('HMAC', saltKey, ikm));
    // Expand: OKM = T(1) || T(2) || ...
    const prkKey = await crypto.subtle.importKey('raw', prk, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const n = Math.ceil(length / 32);
    const okm = new Uint8Array(n * 32);
    let prev = new Uint8Array(0);
    for (let i = 0; i < n; i++) {
        const input = new Uint8Array(prev.length + info.length + 1);
        input.set(prev, 0);
        input.set(info, prev.length);
        input[prev.length + info.length] = i + 1;
        prev = new Uint8Array(await crypto.subtle.sign('HMAC', prkKey, input));
        okm.set(prev, i * 32);
    }
    return okm.slice(0, length);
}

async function eciesDecryptWithRetry(privKeyHex, ciphertextHex) {
    try {
        return await eciesDecrypt(privKeyHex, ciphertextHex);
    } catch (e) {
        const n = BigInt('0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141');
        const privBigInt = BigInt('0x' + privKeyHex);
        const negated = (n - privBigInt).toString(16).padStart(64, '0');
        return await eciesDecrypt(negated, ciphertextHex);
    }
}

// ============================================================
// Whisper API
// ============================================================

const WHISPER_API = '/whisper';

// Chain-scanning inbox - scans blockchain directly instead of using API
async function whisperInbox(address) {
    const messages = [];

    // 1) Whisper API — has indexed covenant info
    try {
        const res = await fetch(`${WHISPER_API}/api/inbox?address=${encodeURIComponent(address)}`);
        if (res.ok) {
            const data = await res.json();
            for (const msg of (data.messages || [])) {
                // Enrich with on-chain payload data
                let payload = null, p2shOutpoint = null;
                try {
                    const txRes = await fetch(`https://api-tn12.kaspa.org/transactions/${msg.tx_id}`);
                    if (txRes.ok) {
                        const tx = await txRes.json();
                        if (tx.payload) {
                            const payloadBytes = cryptoLib.hexToBytes(tx.payload);
                            payload = JSON.parse(new TextDecoder().decode(payloadBytes));
                        }
                        for (let i = 0; i < (tx.outputs || []).length; i++) {
                            if (tx.outputs[i].script_public_key_type === 'scripthash') {
                                p2shOutpoint = { txId: tx.transaction_id, index: i, amount: parseInt(tx.outputs[i].amount) };
                                break;
                            }
                        }
                    }
                } catch {}
                messages.push({
                    tx_id: msg.tx_id,
                    sender: msg.sender || 'unknown',
                    type: payload ? (payload.t || 'whisper') : 'whisper',
                    timestamp: msg.timestamp || '',
                    deposit: msg.deposit || DEPOSIT_SOMPI,
                    payload,
                    p2sh_outpoint: p2shOutpoint,
                });
            }
        }
    } catch (e) {
        console.warn('Whisper API inbox error:', e.message);
    }

    // 2) Chain scan — catch any whispers not indexed by API
    try {
        const txRes = await fetch(`https://api-tn12.kaspa.org/addresses/${address}/full-transactions?limit=50&resolve_previous_outpoints=no`);
        if (txRes.ok) {
            const txData = await txRes.json();
            const knownTxIds = new Set(messages.map(m => m.tx_id));
            for (const tx of txData) {
                if (knownTxIds.has(tx.transaction_id)) continue;
                if (!tx.payload || tx.payload.length < 20) continue;
                try {
                    const payloadBytes = cryptoLib.hexToBytes(tx.payload);
                    const payloadObj = JSON.parse(new TextDecoder().decode(payloadBytes));
                    if (payloadObj.v !== 3 || !payloadObj.a || !payloadObj.a.script) continue;
                    const recipientAddr = extractRecipientFromCovenantScript(payloadObj.a.script, address);
                    if (recipientAddr !== address) continue;
                    let p2shOutpoint = null;
                    for (let i = 0; i < (tx.outputs || []).length; i++) {
                        if (tx.outputs[i].script_public_key_type === 'scripthash') {
                            p2shOutpoint = { txId: tx.transaction_id, index: i, amount: parseInt(tx.outputs[i].amount) };
                            break;
                        }
                    }
                    messages.push({
                        tx_id: tx.transaction_id,
                        sender: payloadObj.a.from || 'unknown',
                        type: payloadObj.t || 'whisper',
                        timestamp: tx.block_time ? new Date(tx.block_time).toISOString() : '',
                        deposit: payloadObj.a.deposit || DEPOSIT_SOMPI,
                        payload: payloadObj,
                        p2sh_outpoint: p2shOutpoint,
                    });
                } catch {}
            }
        }
    } catch (e) {
        console.warn('Chain scan inbox error:', e.message);
    }

    // Deduplicate & sort newest first
    const seen = new Set();
    const unique = messages.filter(m => { if (seen.has(m.tx_id)) return false; seen.add(m.tx_id); return true; });
    unique.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
    return { messages: unique };
}

// Extract recipient pubkey from covenant script and convert to address
function extractRecipientFromCovenantScript(scriptHex, currentUserAddress) {
    try {
        const scriptBytes = cryptoLib.hexToBytes(scriptHex);
        
        // Look for the second occurrence of 0x20 + 32bytes + 0xac pattern
        // This pattern represents: OP_PUSH(32) <pubkey> OP_CHECKSIG
        let patternCount = 0;
        
        for (let i = 0; i < scriptBytes.length - 33; i++) {
            if (scriptBytes[i] === 0x20 && scriptBytes[i + 33] === 0xac) {
                patternCount++;
                if (patternCount === 2) {
                    // Found the second pattern (recipient pubkey)
                    const pubkeyBytes = scriptBytes.slice(i + 1, i + 33);
                    return pubkeyToAddress(pubkeyBytes, NETWORK_PREFIX);
                }
            }
        }
        
        return currentUserAddress; // Fallback if parsing fails
    } catch (e) {
        console.warn('Failed to extract recipient from covenant script:', e);
        return currentUserAddress; // Fallback
    }
}

async function whisperGetInfo(txId) {
    const res = await fetch(`${WHISPER_API}/api/whisper/${txId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

// ── Whisper Covenant: local build + sign (private key never leaves browser) ──

const DEPOSIT_SOMPI = 20_000_000; // 0.2 tKAS
const WHISPER_FEE = 10_000;
const WHISPER_FEE_BUFFER = 5_000;
const TIMEOUT_OFFSET = 1000; // ~100 seconds in DAA score

// Script push helpers (match encode.py)
function pushData(data) {
    const n = data.length;
    if (n === 0) return new Uint8Array([0x00]);
    if (n <= 75) return new Uint8Array([n, ...data]);
    if (n <= 255) return new Uint8Array([0x4c, n, ...data]);
    return new Uint8Array([0x4d, n & 0xff, (n >> 8) & 0xff, ...data]);
}

function pushInt(val) {
    if (val === 0) return new Uint8Array([0x00]);
    if (val >= 1 && val <= 16) return new Uint8Array([0x50 + val]);
    const neg = val < 0;
    let absVal = Math.abs(val);
    const result = [];
    while (absVal > 0) {
        result.push(absVal & 0xff);
        absVal = Math.floor(absVal / 256);
    }
    if (result[result.length - 1] & 0x80) {
        result.push(neg ? 0x80 : 0x00);
    } else if (neg) {
        result[result.length - 1] |= 0x80;
    }
    return pushData(new Uint8Array(result));
}

function buildCovenantScript(aSPKBytes, aPubkey, bPubkey, deposit, timeoutDaa) {
    // CLTV covenant: IF (B reads + covenant check) ELSE (A reclaims after timeout)
    const OP_IF = 0x63, OP_ELSE = 0x67, OP_ENDIF = 0x68;
    const OP_CLTV = 0xb0;
    const OP_TX_OUTPUT_SPK = 0xc3, OP_TX_OUTPUT_AMOUNT = 0xc2;
    const OP_EQUAL = 0x87, OP_VERIFY = 0x69, OP_GTE = 0xa2;
    const OP_CHECKSIG = 0xac;

    const parts = [];
    parts.push(new Uint8Array([OP_IF]));
    // IF: covenant check — output[0] must pay to A's address
    parts.push(pushData(aSPKBytes));
    parts.push(pushInt(0));
    parts.push(new Uint8Array([OP_TX_OUTPUT_SPK, OP_EQUAL, OP_VERIFY]));
    // output[0] amount >= deposit
    parts.push(pushInt(0));
    parts.push(new Uint8Array([OP_TX_OUTPUT_AMOUNT]));
    parts.push(pushInt(deposit));
    parts.push(new Uint8Array([OP_GTE, OP_VERIFY]));
    // B signs
    parts.push(pushData(bPubkey));
    parts.push(new Uint8Array([OP_CHECKSIG]));
    // ELSE: A reclaims after timeout
    parts.push(new Uint8Array([OP_ELSE]));
    parts.push(pushInt(timeoutDaa));
    parts.push(new Uint8Array([OP_CLTV]));
    parts.push(pushData(aPubkey));
    parts.push(new Uint8Array([OP_CHECKSIG]));
    parts.push(new Uint8Array([OP_ENDIF]));

    // Concatenate
    let totalLen = 0;
    for (const p of parts) totalLen += p.length;
    const script = new Uint8Array(totalLen);
    let offset = 0;
    for (const p of parts) { script.set(p, offset); offset += p.length; }
    return script;
}

function blake2b256(data) {
    return blake2bMod.blake2b(data, { dkLen: 32 });
}

function computeP2SHScriptPublicKey(covenantScript) {
    // P2SH: OP_HASH256 OP_DATA_32 <hash> OP_EQUAL
    const scriptHash = blake2b256(covenantScript);
    const spkScript = new Uint8Array(35);
    spkScript[0] = 0xaa; // OP_HASH256 (actually OP_BLAKE2B in Kaspa)
    spkScript[1] = 0x20; // push 32 bytes
    spkScript.set(scriptHash, 2);
    spkScript[34] = 0x87; // OP_EQUAL
    return { script: spkScript, version: 0 };
}

async function getDaaScore() {
    // Use Kaspa REST API to get current DAA score
    const res = await fetch('https://api-tn12.kaspa.org/info/virtual-chain-blue-score');
    if (!res.ok) throw new Error('Failed to get DAA score');
    const data = await res.json();
    return parseInt(data.blueScore);
}

async function whisperSend(toAddress, dataValue, senderPrivKeyHex, msgType = 'whisper') {
    await loadBlake2b();
    await loadSchnorr();
    const { bytesToHex, hexToBytes } = cryptoLib;

    // Derive sender info
    const senderPubFull = secp.getPublicKey(senderPrivKeyHex, true); // 33 bytes
    const senderPubXOnly = senderPubFull.slice(1); // 32 bytes
    const senderAddress = currentAddress;

    // Sender SPK (P2PK)
    const senderSPK = addressToScriptPublicKey(senderAddress);
    // For covenant script: version(2 bytes BE) + script
    const aSPKBytes = new Uint8Array(2 + senderSPK.script.length);
    aSPKBytes[0] = 0; aSPKBytes[1] = 0; // version 0 big-endian
    aSPKBytes.set(senderSPK.script, 2);

    // Recipient pubkey from address
    const recipientDecoded = decodeCashAddr(toAddress);
    const recipientPubBytes = recipientDecoded.hash; // 32 bytes x-only

    // Get DAA score for CLTV timeout
    const currentDaa = await getDaaScore();
    const timeoutDaa = currentDaa + TIMEOUT_OFFSET;

    // Build covenant script
    const covenantScript = buildCovenantScript(
        aSPKBytes, senderPubXOnly, recipientPubBytes, DEPOSIT_SOMPI, timeoutDaa
    );

    // P2SH script public key
    const p2shSPK = computeP2SHScriptPublicKey(covenantScript);

    // Build payload
    const payloadObj = {
        v: 3,
        t: msgType,
        d: dataValue,
        a: {
            from: senderAddress,
            script: bytesToHex(covenantScript),
            spk: bytesToHex(senderSPK.script),
            deposit: DEPOSIT_SOMPI,
            timeout_daa: timeoutDaa,
        }
    };
    const payloadBytes = new TextEncoder().encode(JSON.stringify(payloadObj));

    // Select UTXOs
    const lockAmount = DEPOSIT_SOMPI + WHISPER_FEE_BUFFER;
    const needed = lockAmount + WHISPER_FEE + 10000;
    const utxos = await getUtxos(senderAddress);
    if (!utxos.length) throw new Error('No UTXOs available');

    const sorted = [...utxos].sort((a, b) => parseInt(b.utxoEntry.amount) - parseInt(a.utxoEntry.amount));
    let total = 0;
    const selected = [];
    for (const u of sorted) {
        selected.push(u);
        total += parseInt(u.utxoEntry.amount);
        if (total >= needed) break;
    }
    if (total < needed) throw new Error(`Insufficient balance: have ${(total/1e8).toFixed(4)}, need ${(needed/1e8).toFixed(4)} tKAS`);

    const change = total - lockAmount - WHISPER_FEE;

    // Build inputs
    const inputs = selected.map(u => ({
        txIdBytes: hexToBytes32(u.outpoint.transactionId),
        txId: u.outpoint.transactionId,
        index: u.outpoint.index,
        sequence: 0,
        sigOpCount: 1,
        utxoEntry: { amount: parseInt(u.utxoEntry.amount), spk: senderSPK }
    }));

    // Build outputs: [0] P2SH covenant, [1] change
    const outputs = [
        { amount: lockAmount, spk: p2shSPK },
    ];
    if (change > 0) {
        outputs.push({ amount: change, spk: senderSPK });
    }

    // Build tx with precomputed hashes
    const tx = {
        version: 0,
        inputs,
        outputs,
        lockTime: 0,
        _previousOutputsHash: calcPreviousOutputsHash(inputs),
        _sequencesHash: calcSequencesHash(inputs),
        _sigOpCountsHash: calcSigOpCountsHash(inputs),
        _outputsHash: calcOutputsHash(outputs),
        _payloadHash: calcPayloadHash(payloadBytes),
    };

    // Sign each input
    const signedInputs = [];
    for (let i = 0; i < inputs.length; i++) {
        const sigHash = calcSigHash(tx, i, inputs[i].utxoEntry);
        const sig = schnorrSign(sigHash, senderPrivKeyHex);
        const sigScript = new Uint8Array(1 + 64 + 1);
        sigScript[0] = 65;
        sigScript.set(sig, 1);
        sigScript[65] = SIG_HASH_ALL;
        signedInputs.push({
            previousOutpoint: { transactionId: inputs[i].txId, index: inputs[i].index },
            signatureScript: bytesToHex(sigScript),
            sequence: '0',
            sigOpCount: 1
        });
    }

    // Format outputs for submission
    const formattedOutputs = outputs.map(o => ({
        amount: o.amount.toString(),
        scriptPublicKey: {
            scriptPublicKey: bytesToHex(o.spk.script),
            version: o.spk.version
        }
    }));

    // Build payload hex
    const payloadHex = bytesToHex(payloadBytes);

    // Submit signed transaction
    const submittedTx = {
        version: 0,
        inputs: signedInputs,
        outputs: formattedOutputs,
        lockTime: '0',
        subnetworkId: '0000000000000000000000000000000000000000',
        gas: '0',
        payload: payloadHex
    };

    const result = await submitTransaction(submittedTx);

    // Also notify Whisper API about the covenant (for inbox indexing)
    try {
        const covenantInfo = {
            tx_id: result.transactionId || '',
            covenant_script_hex: bytesToHex(covenantScript),
            p2sh_spk: bytesToHex(p2shSPK.script),
            a_address: senderAddress,
            a_spk: bytesToHex(senderSPK.script),
            a_pubkey: bytesToHex(senderPubXOnly),
            b_pubkey: bytesToHex(recipientPubBytes),
            deposit_sompi: DEPOSIT_SOMPI,
            timeout_daa: timeoutDaa,
        };
        await fetch(`${WHISPER_API}/api/broadcast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Whisper-Key': 'whisper-testnet-poc-key' },
            body: JSON.stringify({ covenant_info: covenantInfo })
        });
    } catch (e) {
        console.warn('Covenant info upload failed (non-critical):', e);
    }

    return { tx_id: result.transactionId || 'submitted' };
}

// ============================================================
// App State & UI
// ============================================================

let currentAddress = null;
let currentPubKey = null;
let currentImportMethod = 'mnemonic';
let pendingMnemonic = null; // temp store during create flow

const $ = (id) => document.getElementById(id);
const show = (el) => { if (typeof el === 'string') el = $(el); el.style.display = ''; };
const hide = (el) => { if (typeof el === 'string') el = $(el); el.style.display = 'none'; };

function showError(msg) {
    const el = $('auth-error');
    el.textContent = msg;
    show(el);
    setTimeout(() => hide(el), 5000);
}

function showAuthForm(formId) {
    ['no-wallet', 'has-wallet', 'create-form', 'import-form', 'mnemonic-display'].forEach(id => hide(id));
    show(formId);
    hide('auth-error');
}

async function checkWalletExists() {
    const data = await dbGet('encryptedKey');
    return !!data;
}

async function showAuthScreen() {
    hide('wallet-screen');
    const authScreen = $('auth-screen');
    authScreen.classList.add('active');
    show(authScreen);

    if (await checkWalletExists()) {
        showAuthForm('has-wallet');
    } else {
        showAuthForm('no-wallet');
    }
}

// Display mnemonic words in a numbered grid
function displayMnemonicGrid(mnemonic) {
    const words = mnemonic.split(' ');
    const grid = $('mnemonic-grid');
    grid.innerHTML = words.map((word, i) =>
        `<div class="mnemonic-word"><span class="mnemonic-num">${i + 1}</span><span class="mnemonic-text">${word}</span></div>`
    ).join('');
}

async function createWallet(password) {
    const mnemonic = generateMnemonic();
    const privKey = derivePrivateKeyFromMnemonic(mnemonic);
    const pubKey = getPublicKey(privKey);
    const address = pubkeyToAddress(pubKey);

    // Encrypt and store the derived private key (NOT the mnemonic)
    const encrypted = await encryptData(password, privKey);
    await dbSet('encryptedKey', encrypted);
    await dbSet('address', address);
    await dbSet('pubkey', cryptoLib.bytesToHex(pubKey));

    return { mnemonic, address };
}

async function importWalletFromMnemonic(mnemonic, password) {
    const normalized = mnemonic.trim().toLowerCase().replace(/\s+/g, ' ');
    if (!validateMnemonic(normalized)) {
        throw new Error('Invalid mnemonic phrase. Please check your words.');
    }

    const privKey = derivePrivateKeyFromMnemonic(normalized);
    const pubKey = getPublicKey(privKey);
    const address = pubkeyToAddress(pubKey);

    const encrypted = await encryptData(password, privKey);
    await dbSet('encryptedKey', encrypted);
    await dbSet('address', address);
    await dbSet('pubkey', cryptoLib.bytesToHex(pubKey));

    return { address };
}

async function importWalletFromPrivKey(privKeyHex, password) {
    if (!/^[0-9a-fA-F]{64}$/.test(privKeyHex)) {
        throw new Error('Invalid private key (must be 64 hex characters)');
    }

    const pubKey = getPublicKey(privKeyHex);
    const address = pubkeyToAddress(pubKey);

    const encrypted = await encryptData(password, privKeyHex);
    await dbSet('encryptedKey', encrypted);
    await dbSet('address', address);
    await dbSet('pubkey', cryptoLib.bytesToHex(pubKey));

    return { address };
}

async function unlockWallet(password) {
    const encrypted = await dbGet('encryptedKey');
    if (!encrypted) throw new Error('No wallet found');

    try {
        const privKey = await decryptData(password, encrypted);
        const pubKey = getPublicKey(privKey);
        const address = pubkeyToAddress(pubKey);
        return { address, pubKey: cryptoLib.bytesToHex(pubKey) };
    } catch (e) {
        throw new Error('Wrong password');
    }
}

async function showWalletScreen(address) {
    currentAddress = address;

    hide('auth-screen');
    $('auth-screen').classList.remove('active');
    const walletScreen = $('wallet-screen');
    walletScreen.classList.add('active');
    show(walletScreen);

    $('address-display').textContent = address;

    const qr = qrcode(0, 'M');
    qr.addData(address);
    qr.make();
    $('qr-container').innerHTML = qr.createSvgTag(5, 0);
    const svg = $('qr-container').querySelector('svg');
    if (svg) {
        svg.style.borderRadius = '8px';
        svg.style.background = 'white';
        svg.style.padding = '12px';
    }

    refreshBalance();
}

async function refreshBalance() {
    const btn = $('btn-refresh');
    btn.classList.add('spinning');

    try {
        const sompi = await getBalance(currentAddress);
        if (sompi !== null) {
            const kas = sompi / 100000000;
            $('balance-value').textContent = kas.toFixed(8);
        } else {
            $('balance-value').textContent = 'Error';
            $('balance-usd').textContent = 'Could not connect to node';
        }
    } catch (e) {
        $('balance-value').textContent = '--';
        $('balance-usd').textContent = 'Connection error';
    }

    btn.classList.remove('spinning');
}

// ============================================================
// Event listeners
// ============================================================

function setupEventListeners() {
    // Create wallet
    $('btn-create').addEventListener('click', () => showAuthForm('create-form'));
    $('btn-back-create').addEventListener('click', () => showAuthForm('no-wallet'));

    $('btn-do-create').addEventListener('click', async () => {
        const pw = $('create-password').value;
        const pw2 = $('create-password2').value;
        if (pw.length < 6) return showError('Password must be at least 6 characters');
        if (pw !== pw2) return showError('Passwords do not match');

        try {
            const { mnemonic, address } = await createWallet(pw);
            pendingMnemonic = mnemonic;
            displayMnemonicGrid(mnemonic);
            showAuthForm('mnemonic-display');
            currentAddress = address;
        } catch (e) {
            showError(e.message);
        }
    });

    $('saved-checkbox').addEventListener('change', (e) => {
        $('btn-continue').disabled = !e.target.checked;
    });

    $('btn-continue').addEventListener('click', () => {
        // Clear mnemonic from memory and DOM
        pendingMnemonic = null;
        $('mnemonic-grid').innerHTML = '';
        showWalletScreen(currentAddress);
    });

    // Import wallet
    $('btn-import').addEventListener('click', () => showAuthForm('import-form'));
    $('btn-back-import').addEventListener('click', () => showAuthForm('no-wallet'));

    // Import method tabs
    document.querySelectorAll('.import-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.import-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentImportMethod = tab.dataset.import;
            if (currentImportMethod === 'mnemonic') {
                show('import-mnemonic-panel');
                hide('import-privkey-panel');
            } else {
                hide('import-mnemonic-panel');
                show('import-privkey-panel');
            }
        });
    });

    $('btn-do-import').addEventListener('click', async () => {
        const pw = $('import-password').value;
        const pw2 = $('import-password2').value;
        if (pw.length < 6) return showError('Password must be at least 6 characters');
        if (pw !== pw2) return showError('Passwords do not match');

        try {
            let result;
            if (currentImportMethod === 'mnemonic') {
                const mnemonic = $('import-mnemonic').value.trim();
                if (!mnemonic) return showError('Enter your mnemonic phrase');
                result = await importWalletFromMnemonic(mnemonic, pw);
                $('import-mnemonic').value = '';
            } else {
                const privKey = $('import-privkey').value.trim();
                if (!privKey) return showError('Enter your private key');
                result = await importWalletFromPrivKey(privKey, pw);
                $('import-privkey').value = '';
            }
            showWalletScreen(result.address);
        } catch (e) {
            showError(e.message);
        }
    });

    // Login
    $('btn-login').addEventListener('click', async () => {
        const pw = $('login-password').value;
        if (!pw) return showError('Enter your password');

        try {
            const { address } = await unlockWallet(pw);
            $('login-password').value = '';
            showWalletScreen(address);
        } catch (e) {
            showError(e.message);
        }
    });

    $('login-password').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') $('btn-login').click();
    });

    // Reset wallet
    $('btn-reset').addEventListener('click', async (e) => {
        e.preventDefault();
        if (confirm('This will delete your wallet from this browser. Make sure you have your recovery phrase or private key backed up!')) {
            await dbDelete('encryptedKey');
            await dbDelete('address');
            await dbDelete('pubkey');
            showAuthForm('no-wallet');
        }
    });

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            $(`tab-${tab.dataset.tab}`).classList.add('active');
        });
    });

    // Refresh balance
    $('btn-refresh').addEventListener('click', refreshBalance);

    // Copy address
    $('btn-copy-addr').addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(currentAddress);
            $('btn-copy-addr').textContent = '✅ Copied!';
            setTimeout(() => $('btn-copy-addr').textContent = '📋 Copy Address', 2000);
        } catch {
            const ta = document.createElement('textarea');
            ta.value = currentAddress;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            $('btn-copy-addr').textContent = '✅ Copied!';
            setTimeout(() => $('btn-copy-addr').textContent = '📋 Copy Address', 2000);
        }
    });

    // Send
    $('btn-send').addEventListener('click', async () => {
        const addr = $('send-address').value.trim();
        const amount = parseFloat($('send-amount').value);
        const pw = $('send-password').value;

        if (!addr.startsWith('kaspatest:')) return showSendResult('Invalid address (must start with kaspatest:)', true);
        if (!amount || amount <= 0) return showSendResult('Invalid amount', true);
        if (!pw) return showSendResult('Enter your password', true);

        try {
            const encrypted = await dbGet('encryptedKey');
            const privKey = await decryptData(pw, encrypted);
            const utxos = await getUtxos(currentAddress);
            if (!utxos.length) {
                showSendResult('No UTXOs available', true);
                return;
            }

            const sompiAmount = Math.round(amount * 100000000);
            const result = await buildAndSendTransaction(privKey, currentAddress, addr, sompiAmount);

            showSendResult(`✅ Transaction sent! TX: ${result.transactionId || 'submitted'}`, false);
            $('send-password').value = '';
            setTimeout(refreshBalance, 3000);
        } catch (e) {
            showSendResult(`Error: ${e.message}`, true);
        }
    });

    function showSendResult(msg, isError) {
        const el = $('send-result');
        el.className = isError ? 'error-msg' : 'success-msg';
        el.textContent = msg;
        show(el);
        setTimeout(() => hide(el), 8000);
    }

    // Export
    $('btn-export').addEventListener('click', () => {
        show('export-modal');
        $('export-password').value = '';
        hide('export-result');
    });

    $('btn-do-export').addEventListener('click', async () => {
        const pw = $('export-password').value;
        try {
            const encrypted = await dbGet('encryptedKey');
            const privKey = await decryptData(pw, encrypted);
            $('export-result').textContent = privKey;
            $('export-result').style.color = '';
            show('export-result');
        } catch {
            $('export-result').textContent = 'Wrong password';
            $('export-result').style.color = 'var(--danger)';
            show('export-result');
        }
    });

    $('btn-close-export').addEventListener('click', () => {
        $('export-result').textContent = '';
        hide('export-modal');
    });

    // Logout
    $('btn-logout').addEventListener('click', () => {
        currentAddress = null;
        currentPubKey = null;
        showAuthScreen();
    });

    // Delete wallet
    $('btn-delete').addEventListener('click', async () => {
        if (confirm('⚠️ DELETE WALLET?\n\nThis permanently removes your encrypted key from this browser.\nMake sure you have backed up your recovery phrase or private key!')) {
            await dbDelete('encryptedKey');
            await dbDelete('address');
            await dbDelete('pubkey');
            currentAddress = null;
            showAuthScreen();
        }
    });

    // ── Whisper ──────────────────────────────────────────────

    document.querySelectorAll('.whisper-subtab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.whisper-subtab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const target = tab.dataset.subtab;
            hide('whisper-inbox');
            hide('whisper-compose');
            hide('whisper-read');
            if (target === 'inbox') show('whisper-inbox');
            else show('whisper-compose');
        });
    });

    $('btn-refresh-inbox').addEventListener('click', loadInbox);
    document.querySelector('[data-tab="whisper"]').addEventListener('click', loadInbox);

    // Toggle encrypt checkbox info text
    $('whisper-encrypt').addEventListener('change', () => {
        const info = $('whisper-mode-info');
        if ($('whisper-encrypt').checked) {
            info.textContent = '🔒 ECIES encrypted with recipient\'s public key';
        } else {
            info.textContent = '📝 Plaintext — anyone can read this on-chain';
        }
    });

    $('btn-send-whisper').addEventListener('click', async () => {
        const toAddr = $('whisper-to').value.trim();
        const message = $('whisper-message').value.trim();
        const password = $('whisper-password').value;
        const doEncrypt = $('whisper-encrypt').checked;

        if (!toAddr.startsWith('kaspatest:')) return showWhisperResult('Invalid address', true);
        if (!message) return showWhisperResult('Enter a message', true);
        if (!password) return showWhisperResult('Enter your wallet password', true);

        const btn = $('btn-send-whisper');
        btn.disabled = true;
        btn.textContent = doEncrypt ? '🔐 Encrypting & Sending...' : '📝 Sending plaintext...';

        try {
            const encrypted = await dbGet('encryptedKey');
            const privKey = await decryptData(password, encrypted);

            let dataHex, msgType;
            if (doEncrypt) {
                const decoded = decodeCashAddr(toAddr);
                const recipientPubHex = '02' + cryptoLib.bytesToHex(decoded.hash);
                dataHex = await eciesEncrypt(recipientPubHex, message);
                msgType = 'whisper';
            } else {
                msgType = 'message';
                dataHex = message; // plaintext string, not hex
            }
            const result = await whisperSend(toAddr, dataHex, privKey, msgType);

            showWhisperResult(`✅ Whisper sent!\nTX: ${result.tx_id || 'submitted'}\nDeposit: 0.2 tKAS (refunded when read)`, false);
            $('whisper-message').value = '';
            $('whisper-password').value = '';
            setTimeout(refreshBalance, 3000);
        } catch (e) {
            showWhisperResult(`Error: ${e.message}`, true);
        } finally {
            btn.disabled = false;
            btn.textContent = '🌊 Send Whisper';
        }
    });

    $('btn-close-whisper').addEventListener('click', () => {
        hide('whisper-read');
        show('whisper-inbox');
        currentWhisperData = null; // Clear current whisper data
    });

    // Redeem deposit button
    $('btn-redeem-deposit').addEventListener('click', redeemCovenantDeposit);
}

// ── Whisper helper functions ─────────────────────────────────

async function loadInbox() {
    if (!currentAddress) return;

    const btn = $('btn-refresh-inbox');
    btn.classList.add('spinning');

    try {
        const data = await whisperInbox(currentAddress);
        const messages = data.messages || [];
        const list = $('inbox-list');

        if (!messages.length) {
            list.innerHTML = '<div class="inbox-empty">No whispers yet. Share your address to receive encrypted messages!</div>';
        } else {
            list.innerHTML = messages.map((msg, index) => {
                const timestamp = new Date(msg.timestamp).toLocaleDateString();
                const typeIcon = msg.type === 'whisper' ? '🔐' : '📝';
                return `
                    <div class="inbox-item" data-txid="${msg.tx_id}" data-index="${index}">
                        <div class="inbox-item-icon">${typeIcon}</div>
                        <div class="inbox-item-details">
                            <div class="inbox-item-sender">From: ${msg.sender || 'unknown'}</div>
                            <div class="inbox-item-meta">
                                <span class="inbox-item-type">${msg.type || 'whisper'}</span>
                                <span class="inbox-item-time">${timestamp}</span>
                            </div>
                            <div class="inbox-item-deposit">${(msg.deposit || 0) / 1e8} tKAS locked</div>
                        </div>
                        <button class="btn-read">Read</button>
                    </div>
                `;
            }).join('');

            // Store messages data for readWhisper function
            list._messagesData = messages;

            list.querySelectorAll('.inbox-item').forEach(item => {
                const readBtn = item.querySelector('.btn-read');
                readBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const txId = item.dataset.txid;
                    const index = parseInt(item.dataset.index);
                    const messageData = messages[index];
                    readWhisper(txId, messageData);
                });
            });
        }
    } catch (e) {
        $('inbox-list').innerHTML = `<div class="inbox-empty">Error loading inbox: ${e.message}</div>`;
    }

    btn.classList.remove('spinning');
}

// Store current message data for redeem functionality
let currentWhisperData = null;

async function readWhisper(txId, messageData = null) {
    hide('whisper-inbox');
    show('whisper-read');

    $('whisper-read-meta').innerHTML = `<strong>TX:</strong> ${txId}<br><div class="whisper-decrypting">🔐 Loading message...</div>`;
    $('whisper-read-content').textContent = '';
    hide('whisper-redeem-section');

    try {
        // Use messageData from chain scanning if provided, otherwise fall back to API
        let info;
        if (messageData) {
            info = {
                sender: messageData.sender,
                type: messageData.type,
                d: messageData.payload.d,
                payload: messageData.payload,
                p2sh_outpoint: messageData.p2sh_outpoint
            };
        } else {
            info = await whisperGetInfo(txId);
        }

        // Store for redeem functionality
        currentWhisperData = info;

        $('whisper-read-meta').innerHTML = `
            <strong>From:</strong> ${info.sender || 'unknown'}<br>
            <strong>TX:</strong> <span style="font-size:11px">${txId}</span><br>
            <strong>Type:</strong> ${info.type || 'whisper'}
        `;

        const msgType = info.type || 'message';
        const rawData = info.d || '';

        if (msgType === 'whisper' && rawData) {
            // Encrypted whisper - prompt for password
            const password = prompt('Enter wallet password to decrypt this whisper:');
            if (!password) {
                $('whisper-read-content').textContent = '❌ Decryption cancelled';
                return;
            }

            try {
                const encrypted = await dbGet('encryptedKey');
                if (!encrypted) throw new Error('No wallet key found — import wallet first');
                const privKey = await decryptData(password, encrypted);
                console.log('Private key decrypted OK, length:', privKey.length);
                console.log('ECIES ciphertext length:', rawData.length);
                const plaintext = await eciesDecryptWithRetry(privKey, rawData);
                $('whisper-read-content').textContent = plaintext;
                
                // Show redeem button after successful decryption
                showRedeemButton();
            } catch (e) {
                console.error('Decrypt error:', e);
                $('whisper-read-content').textContent = `❌ Decryption failed: ${e.message}\n\n(Check browser console for details)`;
            }
        } else {
            // Plaintext message
            $('whisper-read-content').textContent = rawData || '(empty message)';
            
            // Show redeem button for plaintext messages too
            showRedeemButton();
        }
    } catch (e) {
        $('whisper-read-content').textContent = `❌ Error: ${e.message}`;
    }
}

function showRedeemButton() {
    if (currentWhisperData && currentWhisperData.payload) {
        show('whisper-redeem-section');
        const depositAmount = (currentWhisperData.payload.a.deposit || DEPOSIT_SOMPI) / 1e8;
        $('whisper-redeem-info').textContent = `Covenant deposit: ${depositAmount} tKAS`;
    }
}

// Redeem covenant deposit by spending the P2SH UTXO
async function redeemCovenantDeposit() {
    if (!currentWhisperData || !currentWhisperData.payload || !currentWhisperData.p2sh_outpoint) {
        alert('No covenant data available for redemption');
        return;
    }

    const password = prompt('Enter wallet password to sign redemption transaction:');
    if (!password) return;

    const btn = $('btn-redeem-deposit');
    btn.disabled = true;
    btn.textContent = '🔐 Building redemption transaction...';

    try {
        await loadBlake2b();
        await loadSchnorr();
        
        // Get private key
        const encrypted = await dbGet('encryptedKey');
        const recipientPrivKey = await decryptData(password, encrypted);
        
        const payload = currentWhisperData.payload;
        const p2shOutpoint = currentWhisperData.p2sh_outpoint;
        
        // Covenant script from payload
        const covenantScript = cryptoLib.hexToBytes(payload.a.script);
        
        // Sender address and SPK (from payload.a.from and payload.a.spk)
        const senderAddress = payload.a.from;
        const senderSPKBytes = cryptoLib.hexToBytes(payload.a.spk);
        const senderSPK = { script: senderSPKBytes, version: 0 };
        
        // Build redemption transaction
        const depositAmount = payload.a.deposit;
        const fee = WHISPER_FEE_BUFFER; // Use the fee buffer as actual fee
        const outputAmount = depositAmount; // Send full deposit back to sender
        
        // Input: P2SH UTXO
        const input = {
            txIdBytes: cryptoLib.hexToBytes(p2shOutpoint.txId),
            txId: p2shOutpoint.txId,
            index: p2shOutpoint.index,
            sequence: 0,
            sigOpCount: 1,
            utxoEntry: {
                amount: p2shOutpoint.amount,
                spk: { script: computeP2SHScriptPublicKey(covenantScript).script, version: 0 }
            }
        };

        // Output: send deposit back to sender (MUST be output[0] for covenant check)
        const output = {
            amount: outputAmount,
            spk: { script: senderSPKBytes, version: 0 }
        };

        // Build transaction
        const tx = {
            version: 0,
            inputs: [input],
            outputs: [output],
            lockTime: 0,
            _previousOutputsHash: calcPreviousOutputsHash([input]),
            _sequencesHash: calcSequencesHash([input]),
            _sigOpCountsHash: calcSigOpCountsHash([input]),
            _outputsHash: calcOutputsHash([output]),
            _payloadHash: ZERO_HASH
        };

        // For P2SH spend, the scriptPublicKey in SigHash should be the redeem script
        const redeemScriptSPK = { version: 0, script: covenantScript };
        const sigHash = calcSigHash(tx, 0, { 
            amount: p2shOutpoint.amount, 
            spk: redeemScriptSPK 
        });
        
        // Sign with recipient's private key
        const signature = schnorrSign(sigHash, recipientPrivKey);
        
        // Build sig script for IF branch: <signature + SIG_HASH_ALL> <OP_TRUE> <redeem_script>
        const scriptLen = covenantScript.length;
        let sigScriptLen = 1 + 64 + 1 + 1; // sig push + sig + sighash + OP_TRUE
        
        if (scriptLen <= 75) {
            sigScriptLen += 1 + scriptLen; // length byte + script
        } else {
            sigScriptLen += 2 + scriptLen; // OP_PUSHDATA1 + length + script
        }
        
        const sigScript = new Uint8Array(sigScriptLen);
        let offset = 0;
        
        // Push signature (65 bytes: 64-byte signature + SIG_HASH_ALL)
        sigScript[offset++] = 65;
        sigScript.set(signature, offset);
        offset += 64;
        sigScript[offset++] = SIG_HASH_ALL;
        
        // OP_TRUE (0x51)
        sigScript[offset++] = 0x51;
        
        // Push redeem script
        if (scriptLen <= 75) {
            sigScript[offset++] = scriptLen;
        } else {
            // Handle longer scripts if needed
            sigScript[offset++] = 0x4c;
            sigScript[offset++] = scriptLen;
        }
        sigScript.set(covenantScript, offset);

        // Build final transaction for submission
        const submittedTx = {
            version: 0,
            inputs: [{
                previousOutpoint: {
                    transactionId: p2shOutpoint.txId,
                    index: p2shOutpoint.index
                },
                signatureScript: cryptoLib.bytesToHex(sigScript),
                sequence: '0',
                sigOpCount: 1
            }],
            outputs: [{
                amount: outputAmount.toString(),
                scriptPublicKey: {
                    scriptPublicKey: cryptoLib.bytesToHex(senderSPKBytes),
                    version: 0
                }
            }],
            lockTime: '0',
            subnetworkId: '0000000000000000000000000000000000000000',
            gas: '0',
            payload: ''
        };

        // Submit transaction
        const result = await submitTransaction(submittedTx);
        
        btn.textContent = '✅ Deposit redeemed!';
        btn.style.background = '#00e5a0';
        setTimeout(() => {
            hide('whisper-redeem-section');
            setTimeout(refreshBalance, 2000);
        }, 3000);

        // Show success message
        const successMsg = document.createElement('div');
        successMsg.className = 'success-msg';
        successMsg.style.marginTop = '12px';
        successMsg.textContent = `✅ Redemption successful! TX: ${result.transactionId || 'submitted'}`;
        $('whisper-redeem-section').appendChild(successMsg);

    } catch (e) {
        console.error('Redemption error:', e);
        btn.textContent = '❌ Redemption failed';
        btn.style.background = '#ff4444';
        btn.disabled = false;
        
        // Show error message
        const errorMsg = document.createElement('div');
        errorMsg.className = 'error-msg';
        errorMsg.style.marginTop = '12px';
        errorMsg.textContent = `❌ Redemption failed: ${e.message}`;
        $('whisper-redeem-section').appendChild(errorMsg);
        
        setTimeout(() => {
            btn.textContent = '🔓 Redeem 0.2 tKAS deposit';
            btn.style.background = '';
            const msgs = $('whisper-redeem-section').querySelectorAll('.error-msg');
            msgs.forEach(msg => msg.remove());
        }, 5000);
    }
}

function showWhisperResult(msg, isError) {
    const el = $('whisper-send-result');
    el.className = isError ? 'error-msg' : 'success-msg';
    el.textContent = msg;
    el.style.whiteSpace = 'pre-line';
    show(el);
    if (!isError) setTimeout(() => hide(el), 15000);
}

// ============================================================
// Mining
// ============================================================

let mineWorker = null;
let miningActive = false;
let mineStartTime = null;

function setupMining() {
    const btnStart = $('btn-mine-start');
    const btnStop = $('btn-mine-stop');
    console.log('[Mine] setup:', btnStart, btnStop);
    if (!btnStart) { console.error('[Mine] btn-mine-start not found!'); return; }

    btnStart.onclick = () => {
        console.log('[Mine] Start clicked');
        try { startMining(); } catch(e) { console.error('[Mine]', e); mineLog('❌ ' + e.message); }
    };
    btnStop.onclick = () => {
        console.log('[Mine] Stop clicked');
        stopMining();
    };
}

function startMining() {
    if (miningActive) return;
    if (!currentAddress) { mineLog('❌ Unlock wallet first'); return; }

    if (rpcSource === 'public') {
        mineLog('❌ Mining requires Local Proxy (kaspa-api.cjs + kaspad).');
        mineLog('   Public REST does not expose getBlockTemplate/submitBlock.');
        mineLog('   → Switch RPC Source in Settings → re-try.');
        return;
    }

    miningActive = true;
    mineStartTime = Date.now();
    $('btn-mine-start').style.display = 'none';
    $('btn-mine-stop').style.display = 'block';

    // Mining always goes through the proxy (worker fetches /api/* directly).
    const apiUrl = `${location.origin}${PROXY_BASE}/`;

    mineLog('🔧 Creating Web Worker...');
    try {
        mineWorker = new Worker('miner-v20.js');
    } catch(e) {
        mineLog('❌ Worker creation failed: ' + e.message);
        stopMining();
        return;
    }

    mineWorker.onmessage = (e) => {
        const { type, data } = e.data;
        switch (type) {
            case 'stats':
                $('mine-hashrate').textContent = `${data.hashrate} H/s`;
                $('mine-hashes').textContent = data.hashes.toLocaleString();
                $('mine-blocks').textContent = data.blocks;
                const secs = Math.floor((Date.now() - mineStartTime) / 1000);
                $('mine-elapsed').textContent = `${Math.floor(secs/60)}m ${secs%60}s`;
                break;
            case 'log':
                mineLog(data);
                break;
            case 'found':
                mineLog(`💎 FOUND! nonce=${data.nonce}`);
                $('mine-blocks').textContent = parseInt($('mine-blocks').textContent || '0') + 1;
                break;
            case 'accepted':
                mineLog('🎉 Block ACCEPTED by network!');
                break;
            case 'status':
                mineLog(`Status: ${data}`);
                break;
        }
    };

    mineWorker.onerror = (e) => {
        mineLog(`❌ Worker error: ${e.message || e.filename + ':' + e.lineno}`);
        stopMining();
    };
    mineWorker.addEventListener('messageerror', (e) => mineLog(`❌ Message error: ${e}`));

    mineWorker.postMessage({
        type: 'start',
        data: { apiUrl, walletAddress: currentAddress }
    });

    mineLog(`🌊 Mining started → ${currentAddress.slice(0,20)}...`);
    mineLog(`Worker created, sending start command...`);
}

function stopMining() {
    miningActive = false;
    $('btn-mine-start').style.display = 'block';
    $('btn-mine-stop').style.display = 'none';
    if (mineWorker) {
        mineWorker.postMessage({ type: 'stop' });
        setTimeout(() => { mineWorker.terminate(); mineWorker = null; }, 500);
    }
    mineLog('⏹ Mining stopped');
}

function mineLog(msg) {
    const el = $('mine-log');
    if (!el) return;
    const t = new Date().toLocaleTimeString();
    el.innerHTML += `<div>[${t}] ${msg}</div>`;
    el.scrollTop = el.scrollHeight;
    while (el.children.length > 50) el.removeChild(el.firstChild);
}

// ============================================================
// Boot
// ============================================================

(async () => {
    await init();
    setupEventListeners();
    setupMining();
    // Expose for inline onclick
    window.startMining = startMining;
    window.stopMining = stopMining;
    showAuthScreen();
})();
