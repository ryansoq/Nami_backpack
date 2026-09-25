// kHeavyHash on WebGPU. Shared by the game page (browser) and the tests (node).
//
// Per nonce the GPU runs: cSHAKE256("ProofOfWorkHash", header) -> 64x64
// nibble matrix x vector -> cSHAKE256("HeavyHash", digest). Both cSHAKE calls
// fit in one 136-byte rate block after the personalization block, and that
// first block is the same for every nonce, so the CPU absorbs it once and
// the shader starts from the resulting state: two Keccak-f per hash, not four.

const M64 = (1n << 64n) - 1n;
const RC = [
  0x0000000000000001n, 0x0000000000008082n, 0x800000000000808An, 0x8000000080008000n,
  0x000000000000808Bn, 0x0000000080000001n, 0x8000000080008081n, 0x8000000000008009n,
  0x000000000000008An, 0x0000000000000088n, 0x0000000080008009n, 0x000000008000000An,
  0x000000008000808Bn, 0x800000000000008Bn, 0x8000000000008089n, 0x8000000000008003n,
  0x8000000000008002n, 0x8000000000000080n, 0x000000000000800An, 0x800000008000000An,
  0x8000000080008081n, 0x8000000000008080n, 0x0000000080000001n, 0x8000000080008008n,
];
// ROT[x + 5y], and pi sends (x, y) -> (y, 2x + 3y).
const ROT = [0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14];
const rotl = (v, n) => n ? ((v << BigInt(n)) | (v >> BigInt(64 - n))) & M64 : v;

function keccakF(a) {
  for (let r = 0; r < 24; r++) {
    const c = [0, 1, 2, 3, 4].map(x => a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20]);
    for (let x = 0; x < 5; x++) {
      const d = c[(x + 4) % 5] ^ rotl(c[(x + 1) % 5], 1);
      for (let y = 0; y < 5; y++) a[x + 5 * y] ^= d;
    }
    const b = new Array(25);
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++)
      b[y + 5 * ((2 * x + 3 * y) % 5)] = rotl(a[x + 5 * y], ROT[x + 5 * y]);
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++)
      a[x + 5 * y] = b[x + 5 * y] ^ (~b[(x + 1) % 5 + 5 * y] & M64 & b[(x + 2) % 5 + 5 * y]);
    a[0] ^= RC[r];
  }
  return a;
}

// State after absorbing bytepad(encode_string("") || encode_string(S), 136).
function cshakePrefixState(name) {
  const s = new TextEncoder().encode(name);
  const blk = new Uint8Array(136);
  blk.set([1, 136, 1, 0, 1, s.length * 8]);
  blk.set(s, 6);
  const a = new Array(25).fill(0n);
  const v = new DataView(blk.buffer);
  for (let i = 0; i < 17; i++) a[i] ^= v.getBigUint64(8 * i, true);
  return keccakF(a);
}

// Absorb one final block of `msg` (< 136 bytes) into a prefix state and squeeze 32 bytes.
function cshakeFinish(prefix, msg) {
  const blk = new Uint8Array(136);
  blk.set(msg); blk[msg.length] ^= 0x04; blk[135] ^= 0x80;
  const a = prefix.slice();
  const v = new DataView(blk.buffer);
  for (let i = 0; i < 17; i++) a[i] ^= v.getBigUint64(8 * i, true);
  keccakF(a);
  const out = new Uint8Array(32), ov = new DataView(out.buffer);
  for (let i = 0; i < 4; i++) ov.setBigUint64(8 * i, a[i], true);
  return out;
}

const POW_PREFIX = cshakePrefixState('ProofOfWorkHash');
const HH_PREFIX = cshakePrefixState('HeavyHash');

// ---- matrix (xoshiro256++ seeded by pre_pow_hash, retried until full rank) ----
function xoshiro(s) {
  return () => {
    let r = (s[0] + s[3]) & M64; r = (rotl(r, 23) + s[0]) & M64;
    const t = (s[1] << 17n) & M64;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t;
    s[3] = rotl(s[3], 45);
    return r;
  };
}
function rank(m) {
  const a = Float64Array.from(m); let r = 0; const sel = new Uint8Array(64);
  for (let i = 0; i < 64; i++) {
    let j = 0; while (j < 64 && (sel[j] || Math.abs(a[j * 64 + i]) < 1e-9)) j++;
    if (j === 64) continue;
    r++; sel[j] = 1; const d = a[j * 64 + i];
    for (let p = i + 1; p < 64; p++) a[j * 64 + p] /= d;
    for (let k = 0; k < 64; k++) if (k !== j && Math.abs(a[k * 64 + i]) > 1e-9) {
      const f = a[k * 64 + i]; for (let p = i + 1; p < 64; p++) a[k * 64 + p] -= a[j * 64 + p] * f;
    }
  }
  return r;
}
function generateMatrix(pre) {
  const v = new DataView(pre.buffer, pre.byteOffset, 32);
  const next = xoshiro([0, 8, 16, 24].map(o => v.getBigUint64(o, true)));
  for (;;) {
    const m = new Uint32Array(4096);
    for (let i = 0; i < 64; i++) for (let j = 0; j < 64; j += 16) {
      const x = next(); for (let k = 0; k < 16; k++) m[i * 64 + j + k] = Number((x >> BigInt(4 * k)) & 0xFn);
    }
    if (rank(m) === 64) return m;
  }
}

// ---- CPU kHeavyHash through the same prefix-state path the shader uses ----
function header80(pre, ts, nonce) {
  const d = new Uint8Array(80); d.set(pre, 0); const v = new DataView(d.buffer);
  v.setBigUint64(32, BigInt(ts), true); v.setBigUint64(72, BigInt(nonce), true);
  return d;
}
function cpuPow(pre, ts, nonce, m) {
  const h = cshakeFinish(POW_PREFIX, header80(pre, ts, nonce));
  const v = []; for (let i = 0; i < 32; i++) v.push(h[i] >> 4, h[i] & 15);
  const d = new Uint8Array(32);
  for (let i = 0; i < 32; i++) {
    let hi = 0, lo = 0;
    for (let j = 0; j < 64; j++) { hi += m[(2 * i) * 64 + j] * v[j]; lo += m[(2 * i + 1) * 64 + j] * v[j]; }
    d[i] = h[i] ^ ((((hi >> 10) & 15) << 4) | ((lo >> 10) & 15));
  }
  return cshakeFinish(HH_PREFIX, d);
}

// ---- fast CPU path: Keccak on 32-bit word pairs (the BigInt one above is ~50x slower) ----
const RC32 = new Uint32Array(48);
RC.forEach((c, i) => { RC32[2 * i] = Number(c & 0xFFFFFFFFn); RC32[2 * i + 1] = Number(c >> 32n); });
const PI_SRC = new Uint8Array(25), PI_ROT = new Uint8Array(25);
for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) {
  const d = y + 5 * ((2 * x + 3 * y) % 5);
  PI_SRC[d] = x + 5 * y; PI_ROT[d] = ROT[x + 5 * y];
}
const _c = new Uint32Array(10), _b = new Uint32Array(50);
function keccakF32(s) {
  for (let r = 0; r < 24; r++) {
    for (let x = 0; x < 5; x++) {
      _c[2 * x] = s[2 * x] ^ s[2 * x + 10] ^ s[2 * x + 20] ^ s[2 * x + 30] ^ s[2 * x + 40];
      _c[2 * x + 1] = s[2 * x + 1] ^ s[2 * x + 11] ^ s[2 * x + 21] ^ s[2 * x + 31] ^ s[2 * x + 41];
    }
    for (let x = 0; x < 5; x++) {
      const p = (x + 4) % 5, q = (x + 1) % 5;
      const lo = _c[2 * p] ^ ((_c[2 * q] << 1) | (_c[2 * q + 1] >>> 31));
      const hi = _c[2 * p + 1] ^ ((_c[2 * q + 1] << 1) | (_c[2 * q] >>> 31));
      for (let y = 0; y < 25; y += 5) { s[2 * (x + y)] ^= lo; s[2 * (x + y) + 1] ^= hi; }
    }
    for (let d = 0; d < 25; d++) {
      const i = PI_SRC[d], n = PI_ROT[d], lo = s[2 * i], hi = s[2 * i + 1];
      if (n === 0) { _b[2 * d] = lo; _b[2 * d + 1] = hi; }
      else if (n < 32) { _b[2 * d] = (lo << n) | (hi >>> (32 - n)); _b[2 * d + 1] = (hi << n) | (lo >>> (32 - n)); }
      else if (n === 32) { _b[2 * d] = hi; _b[2 * d + 1] = lo; }
      else { const k = n - 32; _b[2 * d] = (hi << k) | (lo >>> (32 - k)); _b[2 * d + 1] = (lo << k) | (hi >>> (32 - k)); }
    }
    for (let y = 0; y < 25; y += 5) for (let x = 0; x < 5; x++) {
      const i = 2 * (x + y), j = 2 * ((x + 1) % 5 + y), k = 2 * ((x + 2) % 5 + y);
      s[i] = _b[i] ^ (~_b[j] & _b[k]); s[i + 1] = _b[i + 1] ^ (~_b[j + 1] & _b[k + 1]);
    }
    s[0] ^= RC32[2 * r]; s[1] ^= RC32[2 * r + 1];
  }
}

// Same math as cpuPow, reusing the shader's precomputed states (buildParams).
let _job = null;
function fastPow(pre, ts, nonce, m) {
  if (!_job || _job.pre !== pre || _job.ts !== ts) {
    const u = buildParams(pre, ts, 0n, 0n);
    _job = { pre, ts, pow: u.slice(0, 50), hh: u.slice(52, 102) };
  }
  const s = _job.pow.slice();
  const n = BigInt(nonce);
  s[18] ^= Number(n & 0xFFFFFFFFn); s[19] ^= Number(n >> 32n);
  keccakF32(s);
  const h = new Uint8Array(s.buffer, 0, 32).slice();   // little-endian host (every WebGPU/JS target)
  const v = new Uint8Array(64);
  for (let i = 0; i < 32; i++) { v[2 * i] = h[i] >> 4; v[2 * i + 1] = h[i] & 15; }
  const t = _job.hh.slice(), d = new Uint8Array(t.buffer, 0, 32);
  for (let i = 0; i < 32; i++) {
    let hi = 0, lo = 0; const r0 = 128 * i, r1 = r0 + 64;
    for (let j = 0; j < 64; j++) { hi += m[r0 + j] * v[j]; lo += m[r1 + j] * v[j]; }
    d[i] ^= h[i] ^ ((((hi >> 10) & 15) << 4) | ((lo >> 10) & 15));
  }
  keccakF32(t);
  return new Uint8Array(t.buffer, 0, 32).slice();
}

// ---- WGSL generator: lanes are vec2<u32> (x = low word, y = high word) ----
function rotExpr(v, n) {
  if (n === 0) return v;
  if (n === 32) return `${v}.yx`;
  if (n < 32) return `vec2<u32>((${v}.x << ${n}u) | (${v}.y >> ${32 - n}u), (${v}.y << ${n}u) | (${v}.x >> ${32 - n}u))`;
  const k = n - 32;
  return `vec2<u32>((${v}.y << ${k}u) | (${v}.x >> ${32 - k}u), (${v}.x << ${k}u) | (${v}.y >> ${32 - k}u))`;
}
function keccakWGSL() {
  const L = [];
  L.push('fn keccak_f(s: ptr<function, array<vec2<u32>, 25>>) {');
  L.push('  var a0 = (*s)[0];' + [...Array(24)].map((_, i) => ` var a${i + 1} = (*s)[${i + 1}];`).join(''));
  L.push('  for (var r = 0u; r < 24u; r++) {');
  for (let x = 0; x < 5; x++) L.push(`    let c${x} = a${x} ^ a${x + 5} ^ a${x + 10} ^ a${x + 15} ^ a${x + 20};`);
  for (let x = 0; x < 5; x++) {
    L.push(`    let d${x} = c${(x + 4) % 5} ^ ${rotExpr(`c${(x + 1) % 5}`, 1)};`);
  }
  for (let i = 0; i < 25; i++) L.push(`    a${i} ^= d${i % 5};`);
  for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++)
    L.push(`    let b${y + 5 * ((2 * x + 3 * y) % 5)} = ${rotExpr(`a${x + 5 * y}`, ROT[x + 5 * y])};`);
  for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++)
    L.push(`    a${x + 5 * y} = b${x + 5 * y} ^ (~b${(x + 1) % 5 + 5 * y} & b${(x + 2) % 5 + 5 * y});`);
  L.push('    a0 ^= RC[r];');
  L.push('  }');
  for (let i = 0; i < 25; i++) L.push(`  (*s)[${i}] = a${i};`);
  L.push('}');
  const rc = RC.map(c => `vec2<u32>(${Number(c & 0xFFFFFFFFn)}u, ${Number(c >> 32n)}u)`).join(', ');
  return `const RC = array<vec2<u32>, 24>(${rc});\n` + L.join('\n');
}

const SHADER = () => `
struct Params {
  pow_state: array<vec4<u32>, 13>, // 25 lanes pre-xored with the constant header bytes and padding (lanes 0..8, 10, 16)
  hh_state:  array<vec4<u32>, 13>, // HeavyHash prefix state, padding pre-xored (lanes 4, 16)
  tgt:       array<vec4<u32>, 2>,  // 256-bit little-endian target, word 7 most significant
  nonce_lo:  u32,
  nonce_hi:  u32,
  _pad0: u32, _pad1: u32,
};
@group(0) @binding(0) var<uniform> P: Params;
@group(0) @binding(1) var<storage, read> matrix: array<u32, 512>; // 64 rows x 8 words, 8 nibbles per word (packMatrix)
@group(0) @binding(2) var<storage, read_write> out: array<atomic<u32>, 64>;
// out[0] = hits, out[1] = best (min) top word, out[2..] = hit nonce pairs (lo, hi), up to 31

${keccakWGSL()}

fn lane(st: array<vec4<u32>, 13>, i: u32) -> vec2<u32> {
  let q = st[i / 2u];
  return select(q.xy, q.zw, (i & 1u) == 1u);
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>, @builtin(num_workgroups) nwg: vec3<u32>) {
  let lo = P.nonce_lo + gid.x + gid.y * nwg.x * 64u;
  let hi = P.nonce_hi + select(0u, 1u, lo < P.nonce_lo);

  var s: array<vec2<u32>, 25>;
  for (var i = 0u; i < 25u; i++) { s[i] = lane(P.pow_state, i); }
  s[9] ^= vec2<u32>(lo, hi);
  keccak_f(&s);

  // 32-byte hash as 8 little-endian words
  var w = array<u32, 8>(s[0].x, s[0].y, s[1].x, s[1].y, s[2].x, s[2].y, s[3].x, s[3].y);

  // vector nibbles, high nibble first within each byte
  var vec: array<u32, 64>;
  for (var i = 0u; i < 32u; i++) {
    let b = (w[i / 4u] >> (8u * (i % 4u))) & 0xFFu;
    vec[2u * i] = b >> 4u;
    vec[2u * i + 1u] = b & 15u;
  }

  var dig: array<u32, 8>;
  for (var i = 0u; i < 32u; i++) {
    var sh = 0u; var sl = 0u;
    for (var k = 0u; k < 8u; k++) {
      let rh = matrix[(2u * i) * 8u + k];
      let rl = matrix[(2u * i + 1u) * 8u + k];
      for (var n = 0u; n < 8u; n++) {
        let v = vec[k * 8u + n];
        sh += ((rh >> (4u * n)) & 15u) * v;
        sl += ((rl >> (4u * n)) & 15u) * v;
      }
    }
    let p = (((sh >> 10u) & 15u) << 4u) | ((sl >> 10u) & 15u);
    let b = ((w[i / 4u] >> (8u * (i % 4u))) & 0xFFu) ^ p;
    dig[i / 4u] |= b << (8u * (i % 4u));
  }

  for (var i = 0u; i < 25u; i++) { s[i] = lane(P.hh_state, i); }
  for (var i = 0u; i < 4u; i++) { s[i] ^= vec2<u32>(dig[2u * i], dig[2u * i + 1u]); }
  keccak_f(&s);

  let h = array<u32, 8>(s[0].x, s[0].y, s[1].x, s[1].y, s[2].x, s[2].y, s[3].x, s[3].y);
  atomicMin(&out[1], h[7]);

  // hash <= target, compared from the most significant word down
  var le = true;
  for (var k = 0; k < 8; k++) {
    let i = 7 - k;
    let t = P.tgt[i / 4][i % 4];
    if (h[i] < t) { break; }
    if (h[i] > t) { le = false; break; }
  }
  if (le) {
    let slot = atomicAdd(&out[0], 1u);
    if (slot < 31u) {
      atomicStore(&out[2u + 2u * slot], lo);
      atomicStore(&out[3u + 2u * slot], hi);
    }
  }
}
`;

// Pack the Uint32Array(4096) matrix into 8 nibbles per word, row-major.
function packMatrix(m) {
  const p = new Uint32Array(512);
  for (let r = 0; r < 64; r++) for (let k = 0; k < 8; k++) {
    let w = 0; for (let n = 0; n < 8; n++) w |= m[r * 64 + k * 8 + n] << (4 * n);
    p[r * 8 + k] = w >>> 0;
  }
  return p;
}

function laneWords(state) {
  const u = new Uint32Array(52);
  state.forEach((v, i) => { u[2 * i] = Number(v & 0xFFFFFFFFn); u[2 * i + 1] = Number(v >> 32n); });
  return u;
}

// Uniform block: pow_state(52) hh_state(52) target(8) nonce_lo nonce_hi pad pad = 116 words
function buildParams(pre, ts, targetBig, nonceBig) {
  const blk = new Uint8Array(136);
  blk.set(pre, 0);
  new DataView(blk.buffer).setBigUint64(32, BigInt(ts), true);
  blk[80] ^= 0x04; blk[135] ^= 0x80;
  const a = POW_PREFIX.slice();
  const v = new DataView(blk.buffer);
  for (let i = 0; i < 17; i++) a[i] ^= v.getBigUint64(8 * i, true);

  const hb = new Uint8Array(136); hb[32] ^= 0x04; hb[135] ^= 0x80;
  const b = HH_PREFIX.slice(); const hv = new DataView(hb.buffer);
  for (let i = 0; i < 17; i++) b[i] ^= hv.getBigUint64(8 * i, true);

  const u = new Uint32Array(116);
  u.set(laneWords(a), 0);
  u.set(laneWords(b), 52);
  for (let i = 0; i < 8; i++) u[104 + i] = Number((targetBig >> BigInt(32 * i)) & 0xFFFFFFFFn);
  u[112] = Number(nonceBig & 0xFFFFFFFFn);
  u[113] = Number((nonceBig >> 32n) & 0xFFFFFFFFn);
  return u;
}

class GpuMiner {
  static async create() {
    if (!navigator.gpu) throw new Error('This browser has no WebGPU');
    const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
    if (!adapter) throw new Error('No GPU adapter available');
    const device = await adapter.requestDevice();
    const m = new GpuMiner();
    m.device = device;
    m.adapterInfo = adapter.info || {};
    const module = device.createShaderModule({ code: SHADER() });
    const info = await module.getCompilationInfo();
    const errs = info.messages.filter(x => x.type === 'error');
    if (errs.length) throw new Error('WGSL: ' + errs.map(e => `${e.lineNum}:${e.linePos} ${e.message}`).join('; '));
    m.pipeline = await device.createComputePipelineAsync({ layout: 'auto', compute: { module, entryPoint: 'main' } });
    m.params = device.createBuffer({ size: 116 * 4, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    m.matrix = device.createBuffer({ size: 2048, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
    m.out = device.createBuffer({ size: 256, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.COPY_SRC });
    m.read = device.createBuffer({ size: 256, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
    m.bind = device.createBindGroup({ layout: m.pipeline.getBindGroupLayout(0), entries: [
      { binding: 0, resource: { buffer: m.params } },
      { binding: 1, resource: { buffer: m.matrix } },
      { binding: 2, resource: { buffer: m.out } },
    ] });
    return m;
  }

  setJob(pre, ts, targetBig) {
    this.pre = pre; this.ts = ts; this.target = targetBig;
    this.mat = generateMatrix(pre);
    this.device.queue.writeBuffer(this.matrix, 0, packMatrix(this.mat));
  }

  setTarget(targetBig) { this.target = targetBig; }

  // Hash about `count` nonces starting at `nonce`; returns how many were actually hashed
  // (rounded to whole workgroups; a 2D dispatch lifts the 65535-workgroup cap).
  async run(nonce, count, maxX = 65535) {
    const groups = Math.max(1, Math.ceil(count / 64));
    const gx = Math.min(groups, maxX), gy = Math.ceil(groups / gx);
    count = gx * gy * 64;
    const q = this.device.queue;
    q.writeBuffer(this.params, 0, buildParams(this.pre, this.ts, this.target, BigInt(nonce)));
    const init = new Uint32Array(64); init[1] = 0xFFFFFFFF;
    q.writeBuffer(this.out, 0, init);
    const enc = this.device.createCommandEncoder();
    const pass = enc.beginComputePass();
    pass.setPipeline(this.pipeline); pass.setBindGroup(0, this.bind);
    pass.dispatchWorkgroups(gx, gy);
    pass.end();
    enc.copyBufferToBuffer(this.out, 0, this.read, 0, 256);
    q.submit([enc.finish()]);
    await this.read.mapAsync(GPUMapMode.READ);
    const r = new Uint32Array(this.read.getMappedRange().slice(0));
    this.read.unmap();
    const hits = [];
    for (let i = 0; i < Math.min(r[0], 31); i++) hits.push((BigInt(r[3 + 2 * i]) << 32n) | BigInt(r[2 + 2 * i]));
    return { count, hitCount: r[0], hits, bestTop: r[1] };
  }
}

const KHH = { keccakF, keccakF32, fastPow, cshakeFinish, POW_PREFIX, HH_PREFIX, generateMatrix, packMatrix, cpuPow, header80, buildParams, SHADER, GpuMiner };
if (typeof module !== 'undefined') module.exports = KHH;
if (typeof window !== 'undefined') window.KHH = KHH;
