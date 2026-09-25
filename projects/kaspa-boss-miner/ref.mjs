// CPU reference for kHeavyHash, ported from kaspa-wallet-web/miner-worker.js.
// Used only to check the WebGPU shader bit-for-bit.
import { cshake256 } from '@noble/hashes/sha3-addons.js';

const M64 = 0xFFFFFFFFFFFFFFFFn;
function xoshiro(s) {
  s = s.map(BigInt);
  return () => {
    let r = (s[0] + s[3]) & M64; r = ((((r << 23n) | (r >> 41n)) & M64) + s[0]) & M64;
    const t = (s[1] << 17n) & M64;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t;
    s[3] = ((s[3] << 45n) | (s[3] >> 19n)) & M64;
    return r;
  };
}
function rank(m) {
  const a = Float64Array.from(m); let r = 0; const sel = new Uint8Array(64);
  for (let i = 0; i < 64; i++) {
    let j = 0; while (j < 64 && (sel[j] || Math.abs(a[j*64+i]) < 1e-9)) j++;
    if (j === 64) continue;
    r++; sel[j] = 1; const d = a[j*64+i];
    for (let p = i+1; p < 64; p++) a[j*64+p] /= d;
    for (let k = 0; k < 64; k++) if (k !== j && Math.abs(a[k*64+i]) > 1e-9) {
      const f = a[k*64+i]; for (let p = i+1; p < 64; p++) a[k*64+p] -= a[j*64+p]*f;
    }
  }
  return r;
}
export function generateMatrix(h) {
  const v = new DataView(h.buffer, h.byteOffset, 32);
  const next = xoshiro([0,8,16,24].map(o => v.getBigUint64(o, true)));
  for (;;) {
    const m = new Uint16Array(4096);
    for (let i = 0; i < 64; i++) for (let j = 0; j < 64; j += 16) {
      const x = next(); for (let k = 0; k < 16; k++) m[i*64+j+k] = Number((x >> BigInt(4*k)) & 0xFn);
    }
    if (rank(m) === 64) return m;
  }
}
const enc = s => new TextEncoder().encode(s);
export function heavyHash(m, h) {
  const v = new Uint16Array(64);
  for (let i = 0; i < 32; i++) { v[2*i] = h[i] >> 4; v[2*i+1] = h[i] & 15; }
  const p = new Uint32Array(64);
  for (let r = 0; r < 64; r++) { let s = 0; for (let j = 0; j < 64; j++) s += m[r*64+j]*v[j]; p[r] = (s >> 10) & 15; }
  const d = new Uint8Array(32);
  for (let i = 0; i < 32; i++) d[i] = h[i] ^ ((p[2*i] << 4) | p[2*i+1]);
  return cshake256(d, { personalization: enc('HeavyHash'), dkLen: 32 });
}
export function header80(pre, ts, nonce) {
  const d = new Uint8Array(80); d.set(pre, 0); const v = new DataView(d.buffer);
  v.setBigUint64(32, BigInt(ts), true); v.setBigUint64(72, BigInt(nonce), true);
  return d;
}
export function computePow(pre, ts, nonce, m) {
  return heavyHash(m, cshake256(header80(pre, ts, nonce), { personalization: enc('ProofOfWorkHash'), dkLen: 32 }));
}
export const hex = b => Buffer.from(b).toString('hex');

if (import.meta.url === `file://${process.argv[1]}`) {
  const pre = Uint8Array.from({length: 32}, (_, i) => [0x01,0x23,0x45,0x67,0x89,0xab,0xcd,0xef][i % 8]);
  const m = generateMatrix(pre);
  const got = hex(computePow(pre, 1234567890, 99999, m));
  const want = 'd2154c1435c99a4ea58ca81dc35829ebd1513b67b0bdec12ba15fb27fefadc82';
  console.log(got, got === want ? 'MATCH ShioKaze vector' : 'MISMATCH want ' + want);
}
