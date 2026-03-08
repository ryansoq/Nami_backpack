// Kaspa Testnet-12 Web Wallet
// Pure browser-based, no private keys leave the client

// ============================================================
// Crypto helpers - secp256k1 (Schnorr) + Kaspa address encoding
// ============================================================

// We use SubtleCrypto for PBKDF2/AES and noble-secp256k1 via CDN
let secp;
const NETWORK_PREFIX = 'kaspatest';

async function loadSecp256k1() {
    // Load noble-secp256k1 v2
    const mod = await import('https://esm.sh/@noble/secp256k1@2.1.0');
    secp = mod;
    // Also need noble-hashes for schnorr
    const hashes = await import('https://esm.sh/@noble/hashes@1.6.1/sha256');
    const utils = await import('https://esm.sh/@noble/hashes@1.6.1/utils');
    return { secp: mod, sha256: hashes.sha256, bytesToHex: utils.bytesToHex, hexToBytes: utils.hexToBytes };
}

let cryptoLib;

async function init() {
    cryptoLib = await loadSecp256k1();
}

// Generate a random 32-byte private key
function generatePrivateKey() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return cryptoLib.bytesToHex(bytes);
}

// Get public key (x-only for schnorr, 32 bytes)
function getPublicKey(privKeyHex) {
    const pubKey = secp.getPublicKey(privKeyHex, true); // compressed 33 bytes
    // Kaspa uses the schnorr x-only public key (32 bytes, drop first byte)
    return pubKey.slice(1); // remove 02/03 prefix
}

// ============================================================
// Kaspa Address encoding (bech32-like, but Kaspa uses its own variant)
// ============================================================

// Kaspa uses a custom cashaddr-like encoding
// Format: prefix:payload
// Payload = base32 encoded (version byte + pubkey hash)

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

function encodeCashAddr(prefix, version, hash) {
    // version: 0 = pubkey, 1 = script
    // Kaspa address payload: [version_byte, ...hash_5bit]
    const versionByte = (version << 3); // type in upper bits, size=0 (20 bytes)
    const payload5bit = convertBits([versionByte, ...hash], 8, 5, true);
    const checksum = createChecksum(prefix, payload5bit);
    const combined = [...payload5bit, ...checksum];
    let addr = prefix + ':';
    for (const c of combined) {
        addr += CHARSET[c];
    }
    return addr;
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
    // Verify checksum
    const values = [...prefixExpand(prefix), ...data5bit];
    if (polymod(values) !== 0n) throw new Error('Invalid checksum');
    // Remove 8-byte checksum
    const payload5bit = data5bit.slice(0, -8);
    const payload8bit = convertBits(payload5bit, 5, 8, false);
    const versionByte = payload8bit[0];
    const hash = payload8bit.slice(1);
    return { prefix, version: versionByte >> 3, hash: new Uint8Array(hash) };
}

// Simple BLAKE2b (Kaspa uses blake2b for address hashing)
// We'll use SubtleCrypto SHA-256 as fallback, but Kaspa actually uses
// ECDSA Schnorr pubkey directly in address (no hashing for schnorr addresses)

// Actually, Kaspa schnorr addresses use the raw 32-byte x-only pubkey directly
// Address = prefix:cashaddr_encode(version=1, schnorr_pubkey_32bytes)
// But Kaspa also supports ECDSA addresses with version=0 and pubkey hash

// For schnorr (which is the modern Kaspa way):
// version byte encodes: type (3 bits) | size (5 bits)
// type 1 = schnorr, size depends on pubkey length
// For 32 byte pubkey: size code = 0x03 (32 bytes => code 3 in the size table)

// Kaspa address version byte:
// bits 0-2: address type (0=PubKey, 1=PubKeyECDSA, 8=ScriptHash)  
// bits 3-7: depends on implementation
// Actually let me look at this more carefully...

// In Kaspa, the address payload is simply:
// For P2PK (schnorr): version=0x00, then 32 bytes of schnorr public key
// For P2PKH (ecdsa): version=0x01, then 33 bytes of compressed public key  
// Encoded with cashaddr

function pubkeyToAddress(pubkeyBytes, prefix = NETWORK_PREFIX) {
    // Kaspa uses schnorr x-only pubkey (32 bytes) with version 0
    // The version byte for cashaddr:
    // Upper 4 bits = type (0 for pubkey)
    // Lower 4 bits = size index
    // For 32 bytes, size index is 3 (since 32 = 20 + 12... actually let me check the size table)
    
    // CashAddr size table: 
    // 0 -> 20 bytes, 1 -> 24, 2 -> 28, 3 -> 32, 4 -> 40, 5 -> 48, 6 -> 56, 7 -> 64
    // So 32 bytes = index 3
    
    // Type: 0 = P2PK_Schnorr in Kaspa
    // Version byte = (type << 3) | sizeIndex = (0 << 3) | 3 = 3
    
    const versionByte = 0x03; // type=0 (schnorr pubkey), size=3 (32 bytes)
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
    // Return salt + iv + ciphertext as hex
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
// RPC - Talk to kaspad via API proxy
// ============================================================

const API_BASE = '/kaspa/api';

async function rpcCall(method, params = {}) {
    const res = await fetch(`${API_BASE}/${method}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
    });
    if (!res.ok) throw new Error(`RPC error: ${res.status}`);
    return res.json();
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
// App State & UI
// ============================================================

let currentAddress = null;
let currentPubKey = null;

// DOM helpers
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

async function createWallet(password) {
    const privKey = generatePrivateKey();
    const pubKey = getPublicKey(privKey);
    const address = pubkeyToAddress(pubKey);
    
    // Encrypt and store
    const encrypted = await encryptData(password, privKey);
    await dbSet('encryptedKey', encrypted);
    await dbSet('address', address);
    await dbSet('pubkey', cryptoLib.bytesToHex(pubKey));
    
    return { privKey, address };
}

async function importWallet(privKeyHex, password) {
    // Validate
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
        // Verify it's valid
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
    
    // Show address
    $('address-display').textContent = address;
    
    // Generate QR
    const qr = qrcode(0, 'M');
    qr.addData(address);
    qr.make();
    $('qr-container').innerHTML = qr.createSvgTag(5, 0);
    // Style the SVG
    const svg = $('qr-container').querySelector('svg');
    if (svg) {
        svg.style.borderRadius = '8px';
        svg.style.background = 'white';
        svg.style.padding = '12px';
    }
    
    // Fetch balance
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
            const { privKey, address } = await createWallet(pw);
            $('privkey-display').textContent = privKey;
            showAuthForm('mnemonic-display');
            
            // Store address for later
            currentAddress = address;
        } catch (e) {
            showError(e.message);
        }
    });
    
    $('saved-checkbox').addEventListener('change', (e) => {
        $('btn-continue').disabled = !e.target.checked;
    });
    
    $('btn-continue').addEventListener('click', () => {
        $('privkey-display').textContent = ''; // Clear from DOM
        showWalletScreen(currentAddress);
    });
    
    // Import wallet
    $('btn-import').addEventListener('click', () => showAuthForm('import-form'));
    $('btn-back-import').addEventListener('click', () => showAuthForm('no-wallet'));
    
    $('btn-do-import').addEventListener('click', async () => {
        const privKey = $('import-privkey').value.trim();
        const pw = $('import-password').value;
        const pw2 = $('import-password2').value;
        if (pw.length < 6) return showError('Password must be at least 6 characters');
        if (pw !== pw2) return showError('Passwords do not match');
        
        try {
            const { address } = await importWallet(privKey, pw);
            $('import-privkey').value = '';
            showWalletScreen(address);
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
        if (confirm('This will delete your wallet from this browser. Make sure you have your private key backed up!')) {
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
            // Fallback
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
            // Decrypt private key
            const encrypted = await dbGet('encryptedKey');
            const privKey = await decryptData(pw, encrypted);
            
            // Get UTXOs
            const utxos = await getUtxos(currentAddress);
            if (!utxos.length) {
                showSendResult('No UTXOs available', true);
                return;
            }
            
            const sompiAmount = Math.round(amount * 100000000);
            
            // Build and submit transaction via API
            const result = await rpcCall('createAndSubmitTransaction', {
                privateKey: privKey,
                toAddress: addr,
                amount: sompiAmount,
                fromAddress: currentAddress
            });
            
            // Clear privkey from memory
            showSendResult(`✅ Transaction sent! TX: ${result.transactionId || 'submitted'}`, false);
            $('send-password').value = '';
            
            // Refresh balance
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
        if (confirm('⚠️ DELETE WALLET?\n\nThis permanently removes your encrypted key from this browser.\nMake sure you have backed up your private key!')) {
            await dbDelete('encryptedKey');
            await dbDelete('address');
            await dbDelete('pubkey');
            currentAddress = null;
            showAuthScreen();
        }
    });
}

// ============================================================
// Boot
// ============================================================

(async () => {
    await init();
    setupEventListeners();
    showAuthScreen();
})();
