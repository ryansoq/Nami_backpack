/**
 * 🌊 Kaspa Web Miner - Web Worker (ES Module)
 * Runs HeavyHash mining in background thread
 */

import { cshake256 } from 'https://esm.sh/@noble/hashes@1.7.1/sha3';
import { blake2b } from 'https://esm.sh/@noble/hashes@1.7.1/blake2b';

// ─── HeavyHash Implementation (inlined for worker) ───

class Xoshiro256PlusPlus {
  constructor(s0, s1, s2, s3) {
    this.state = [
      BigInt(s0) & 0xFFFFFFFFFFFFFFFFn,
      BigInt(s1) & 0xFFFFFFFFFFFFFFFFn,
      BigInt(s2) & 0xFFFFFFFFFFFFFFFFn,
      BigInt(s3) & 0xFFFFFFFFFFFFFFFFn
    ];
  }
  next() {
    const s = this.state;
    const M = 0xFFFFFFFFFFFFFFFFn;
    let r = (s[0] + s[3]) & M;
    r = (((r << 23n) | (r >> 41n)) & M) + s[0];
    r &= M;
    const t = (s[1] << 17n) & M;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3];
    s[2] ^= t;
    s[3] = ((s[3] << 45n) | (s[3] >> 19n)) & M;
    return r;
  }
}

function generateMatrix(hashBytes) {
  const view = new DataView(hashBytes.buffer, hashBytes.byteOffset, 32);
  const rng = new Xoshiro256PlusPlus(
    view.getBigUint64(0, true), view.getBigUint64(8, true),
    view.getBigUint64(16, true), view.getBigUint64(24, true)
  );
  while (true) {
    const matrix = new Uint16Array(64 * 64);
    for (let i = 0; i < 64; i++) {
      for (let j = 0; j < 64; j += 16) {
        const v = rng.next();
        for (let k = 0; k < 16; k++) {
          matrix[i * 64 + j + k] = Number((v >> BigInt(4 * k)) & 0xFn);
        }
      }
    }
    if (matrixRank(matrix) === 64) return matrix;
  }
}

function matrixRank(matrix) {
  const mat = new Float64Array(64 * 64);
  for (let i = 0; i < 4096; i++) mat[i] = matrix[i];
  let rank = 0;
  const sel = new Uint8Array(64);
  for (let i = 0; i < 64; i++) {
    let j = 0;
    while (j < 64 && (sel[j] || Math.abs(mat[j * 64 + i]) < 1e-9)) j++;
    if (j < 64) {
      rank++; sel[j] = 1;
      const d = mat[j * 64 + i];
      for (let p = i + 1; p < 64; p++) mat[j * 64 + p] /= d;
      for (let k = 0; k < 64; k++) {
        if (k !== j && Math.abs(mat[k * 64 + i]) > 1e-9) {
          const f = mat[k * 64 + i];
          for (let p = i + 1; p < 64; p++) mat[k * 64 + p] -= mat[j * 64 + p] * f;
        }
      }
    }
  }
  return rank;
}

function computePow(prePowHash, timestamp, nonce, matrix) {
  const data = new Uint8Array(80);
  data.set(prePowHash, 0);
  const view = new DataView(data.buffer);
  const ts = BigInt(timestamp);
  view.setUint32(32, Number(ts & 0xFFFFFFFFn), true);
  view.setUint32(36, Number((ts >> 32n) & 0xFFFFFFFFn), true);
  // bytes 40-71 zeros
  const nb = BigInt(nonce);
  view.setUint32(72, Number(nb & 0xFFFFFFFFn), true);
  view.setUint32(76, Number((nb >> 32n) & 0xFFFFFFFFn), true);

  const enc = new TextEncoder();
  const powHash = cshake256(data, { personalization: enc.encode('ProofOfWorkHash'), dkLen: 32 });
  return heavyHash(matrix, powHash);
}

function heavyHash(matrix, hashBytes) {
  const v = new Uint16Array(64);
  for (let i = 0; i < 32; i++) {
    v[i * 2] = (hashBytes[i] >> 4) & 0x0F;
    v[i * 2 + 1] = hashBytes[i] & 0x0F;
  }
  const p = new Uint32Array(64);
  for (let r = 0; r < 64; r++) {
    let sum = 0;
    const off = r * 64;
    for (let j = 0; j < 64; j++) sum += matrix[off + j] * v[j];
    p[r] = (sum >> 10) & 0x0F;
  }
  const digest = new Uint8Array(32);
  for (let i = 0; i < 32; i++) {
    digest[i] = hashBytes[i] ^ (((p[i * 2] & 0xF) << 4) | (p[i * 2 + 1] & 0xF));
  }
  const enc = new TextEncoder();
  return cshake256(digest, { personalization: enc.encode('HeavyHash'), dkLen: 32 });
}

function hashToInt(h) {
  let r = 0n;
  for (let i = h.length - 1; i >= 0; i--) r = (r << 8n) | BigInt(h[i]);
  return r;
}

function bitsToTarget(bits) {
  const exp = (bits >> 24) & 0xFF;
  const man = bits & 0xFFFFFF;
  return exp <= 3 ? BigInt(man >> (8 * (3 - exp))) : BigInt(man) << BigInt(8 * (exp - 3));
}

// ─── Pre-PoW Hash ───

function calculatePrePowHash(header) {
  const parts = [];
  const push = (a) => parts.push(a);

  // version u16 LE
  const vb = new Uint8Array(2);
  new DataView(vb.buffer).setUint16(0, header.version || 0, true);
  push(vb);

  // parents
  const parents = header.parents || [];
  push(u64le(parents.length));
  for (const level of parents) {
    const hashes = level.parentHashes || [];
    push(u64le(hashes.length));
    for (const h of hashes) push(hexToBytes(h));
  }

  push(hexToBytes(header.hashMerkleRoot || ''));
  push(hexToBytes(header.acceptedIdMerkleRoot || ''));
  push(hexToBytes(header.utxoCommitment || ''));
  push(u64le(0)); // timestamp=0
  push(u32le(header.bits));
  push(u64le(0)); // nonce=0
  push(u64le(header.daaScore || 0));
  push(u64le(header.blueScore || 0));

  // blueWork
  const bw = header.blueWork || '';
  if (bw) {
    let hex = bw.length % 2 ? '0' + bw : bw;
    let bytes = hexToBytes(hex);
    let start = 0;
    while (start < bytes.length && bytes[start] === 0) start++;
    bytes = bytes.slice(start);
    push(u64le(bytes.length));
    if (bytes.length) push(bytes);
  } else {
    push(u64le(0));
  }

  push(hexToBytes(header.pruningPoint || ''));

  // Concat
  const total = parts.reduce((s, p) => s + p.length, 0);
  const buf = new Uint8Array(total);
  let off = 0;
  for (const p of parts) { buf.set(p, off); off += p.length; }

  return blake2b(buf, { key: new TextEncoder().encode('BlockHash'), dkLen: 32 });
}

function hexToBytes(hex) {
  if (!hex || !hex.length) return new Uint8Array(32);
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(hex.substr(i * 2, 2), 16);
  return b;
}

function u64le(n) {
  const b = new Uint8Array(8);
  const v = new DataView(b.buffer);
  const big = BigInt(n);
  v.setUint32(0, Number(big & 0xFFFFFFFFn), true);
  v.setUint32(4, Number((big >> 32n) & 0xFFFFFFFFn), true);
  return b;
}

function u32le(n) {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n >>> 0, true);
  return b;
}

// ─── wRPC Client (inline) ───

class KaspaWRPC {
  constructor(url) {
    this.url = url; this.ws = null; this.rid = 0;
    this.pending = new Map(); this.connected = false;
  }
  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => { this.connected = true; resolve(); };
      this.ws.onerror = (e) => { this.connected = false; reject(e); };
      this.ws.onclose = () => { this.connected = false; };
      this.ws.onmessage = (ev) => {
        try {
          const d = JSON.parse(ev.data);
          const id = d.id;
          if (id !== undefined && this.pending.has(id)) {
            const { resolve, reject } = this.pending.get(id);
            this.pending.delete(id);
            d.error ? reject(new Error(d.error.message || JSON.stringify(d.error))) : resolve(d.params || d.result || d);
          }
        } catch {}
      };
    });
  }
  disconnect() { if (this.ws) { this.ws.onclose = null; this.ws.close(); this.ws = null; } this.connected = false; }
  _call(method, params = {}) {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== 1) { reject(new Error('Not connected')); return; }
      const id = this.rid++;
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('Timeout')); } }, 10000);
    });
  }
  getBlockTemplate(payAddress) { return this._call('getBlockTemplate', { payAddress, extraData: 'KasPortal' }); }
  submitBlock(block) { return this._call('submitBlock', { block, allowNonDAABlocks: true }); }
  getInfo() { return this._call('getInfo', {}); }
}

// ─── Mining Loop ───

let mining = false;
let stats = { hashes: 0, blocks: 0, startTime: 0 };

self.onmessage = async (e) => {
  const { type, data } = e.data;
  if (type === 'start') await startMining(data);
  if (type === 'stop') mining = false;
};

async function startMining({ wsUrl, walletAddress }) {
  mining = true;
  stats = { hashes: 0, blocks: 0, startTime: Date.now() };
  const post = (type, data) => self.postMessage({ type, data });

  post('status', 'connecting');
  const wrpc = new KaspaWRPC(wsUrl);

  try {
    await wrpc.connect();
    post('status', 'connected');
    try {
      const info = await wrpc.getInfo();
      post('log', `Node: ${JSON.stringify(info)}`);
    } catch (e) {
      post('log', `getInfo: ${e.message}`);
    }
  } catch (e) {
    post('status', 'error');
    post('log', `Connection failed: ${e.message}`);
    mining = false;
    return;
  }

  let errors = 0;
  while (mining) {
    try {
      const template = await wrpc.getBlockTemplate(walletAddress);
      if (!template || !template.block) { errors++; if (errors > 5) break; await sleep(1000); continue; }
      errors = 0;

      const block = template.block;
      const header = block.header;
      const prePowHash = calculatePrePowHash(header);
      const target = bitsToTarget(header.bits);
      const matrix = generateMatrix(prePowHash);

      post('log', `Template: bits=0x${header.bits.toString(16)}`);

      const t0 = Date.now();
      let startNonce = BigInt(Math.floor(Math.random() * 0xFFFFFFFF)) << 32n;

      for (let i = 0; mining && Date.now() - t0 < 2000; i++) {
        const nonce = startNonce + BigInt(i);
        const powHash = computePow(prePowHash, header.timestamp, nonce, matrix);
        stats.hashes++;

        if (hashToInt(powHash) <= target) {
          stats.blocks++;
          post('found', { nonce: nonce.toString(), hash: [...powHash].map(b => b.toString(16).padStart(2, '0')).join('') });
          try {
            block.header.nonce = nonce.toString();
            const r = await wrpc.submitBlock(block);
            post('log', `Submitted: ${JSON.stringify(r)}`);
            post('accepted');
          } catch (e) { post('log', `Submit failed: ${e.message}`); }
          break;
        }

        if (i % 200 === 0) {
          const elapsed = (Date.now() - stats.startTime) / 1000;
          post('stats', { hashes: stats.hashes, hashrate: Math.round(elapsed > 0 ? stats.hashes / elapsed : 0), blocks: stats.blocks, elapsed });
        }
      }
    } catch (e) {
      self.postMessage({ type: 'log', data: `Error: ${e.message}` });
      errors++;
      await sleep(1000);
    }
  }

  wrpc.disconnect();
  self.postMessage({ type: 'status', data: 'stopped' });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
