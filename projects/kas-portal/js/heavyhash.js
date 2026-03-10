/**
 * 🌊 HeavyHash (kHeavyHash) - JavaScript Implementation
 * Ported from ShioKaze Python miner by Nami
 * 
 * Flow: cSHAKE256("ProofOfWorkHash") → 64x64 matrix multiply → cSHAKE256("HeavyHash")
 */

// We use @noble/hashes loaded via CDN (imported in worker)
// Expects: blake2b, cshake256 from noble-hashes

/**
 * Xoshiro256++ PRNG for matrix generation
 */
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
    const MASK = 0xFFFFFFFFFFFFFFFFn;
    let result = (s[0] + s[3]) & MASK;
    result = (((result << 23n) | (result >> 41n)) & MASK) + s[0];
    result &= MASK;

    const t = (s[1] << 17n) & MASK;
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = ((s[3] << 45n) | (s[3] >> 19n)) & MASK;

    return result;
  }
}

/**
 * Generate 64x64 HeavyHash matrix from pre_pow_hash
 * Uses Xoshiro256++ PRNG, must produce full-rank matrix
 */
function generateMatrix(hashBytes) {
  // Extract 4 uint64 LE from hash
  const view = new DataView(hashBytes.buffer, hashBytes.byteOffset, 32);
  const s0 = view.getBigUint64(0, true);
  const s1 = view.getBigUint64(8, true);
  const s2 = view.getBigUint64(16, true);
  const s3 = view.getBigUint64(24, true);

  const rng = new Xoshiro256PlusPlus(s0, s1, s2, s3);

  while (true) {
    const matrix = new Uint16Array(64 * 64);

    for (let i = 0; i < 64; i++) {
      for (let j = 0; j < 64; j += 16) {
        const value = rng.next();
        for (let k = 0; k < 16; k++) {
          matrix[i * 64 + j + k] = Number((value >> BigInt(4 * k)) & 0xFn);
        }
      }
    }

    if (matrixRank(matrix) === 64) {
      return matrix;
    }
    // If not full rank, continue with same PRNG state
  }
}

/**
 * Compute matrix rank using Gaussian elimination
 * Reference: rusty-kaspa ordering.rs
 */
function matrixRank(matrix) {
  const EPS = 1e-9;
  const mat = new Float64Array(64 * 64);
  for (let i = 0; i < 64 * 64; i++) mat[i] = matrix[i];

  let rank = 0;
  const rowSelected = new Uint8Array(64);

  for (let i = 0; i < 64; i++) {
    let j = 0;
    while (j < 64) {
      if (!rowSelected[j] && Math.abs(mat[j * 64 + i]) > EPS) break;
      j++;
    }

    if (j !== 64) {
      rank++;
      rowSelected[j] = 1;
      for (let p = i + 1; p < 64; p++) {
        mat[j * 64 + p] /= mat[j * 64 + i];
      }
      for (let k = 0; k < 64; k++) {
        if (k !== j && Math.abs(mat[k * 64 + i]) > EPS) {
          for (let p = i + 1; p < 64; p++) {
            mat[k * 64 + p] -= mat[j * 64 + p] * mat[k * 64 + i];
          }
        }
      }
    }
  }

  return rank;
}

/**
 * HeavyHash core computation
 * 
 * 1. Split 32 bytes into 64 x 4-bit values (high nibble first)
 * 2. Matrix-vector multiply, right-shift 10, take low 4 bits
 * 3. Merge back to 32 bytes, XOR with original hash
 * 4. Final cSHAKE256("HeavyHash")
 */
function heavyHash(matrix, hashBytes, cshake256Fn) {
  // Expand into 64 x 4-bit values
  const v = new Uint16Array(64);
  for (let i = 0; i < 32; i++) {
    v[i * 2] = (hashBytes[i] >> 4) & 0x0F;
    v[i * 2 + 1] = hashBytes[i] & 0x0F;
  }

  // Matrix-vector multiply
  const p = new Uint32Array(64);
  for (let row = 0; row < 64; row++) {
    let sum = 0;
    const rowOff = row * 64;
    for (let j = 0; j < 64; j++) {
      sum += matrix[rowOff + j] * v[j];
    }
    p[row] = (sum >> 10) & 0x0F;
  }

  // XOR back
  const digest = new Uint8Array(32);
  for (let i = 0; i < 32; i++) {
    const high4 = p[i * 2] & 0x0F;
    const low4 = p[i * 2 + 1] & 0x0F;
    digest[i] = hashBytes[i] ^ ((high4 << 4) | low4);
  }

  // Final cSHAKE256("HeavyHash")
  return cshake256Fn(digest, { personalization: encodeText('HeavyHash'), dkLen: 32 });
}

/**
 * Compute full PoW hash
 * Input: pre_pow_hash(32) || timestamp(8) || zeros(32) || nonce(8) = 80 bytes
 */
function computePow(prePowHash, timestamp, nonce, matrix, cshake256Fn) {
  const data = new Uint8Array(80);
  data.set(prePowHash, 0);

  // timestamp as uint64 LE
  const view = new DataView(data.buffer);
  // Use two 32-bit writes for uint64
  const tsLow = Number(BigInt(timestamp) & 0xFFFFFFFFn);
  const tsHigh = Number((BigInt(timestamp) >> 32n) & 0xFFFFFFFFn);
  view.setUint32(32, tsLow, true);
  view.setUint32(36, tsHigh, true);

  // bytes 40-71 are zeros (already)

  // nonce as uint64 LE
  const nonceBig = BigInt(nonce);
  const nLow = Number(nonceBig & 0xFFFFFFFFn);
  const nHigh = Number((nonceBig >> 32n) & 0xFFFFFFFFn);
  view.setUint32(72, nLow, true);
  view.setUint32(76, nHigh, true);

  // First hash: cSHAKE256("ProofOfWorkHash")
  const powHash = cshake256Fn(data, { personalization: encodeText('ProofOfWorkHash'), dkLen: 32 });

  // HeavyHash
  return heavyHash(matrix, powHash, cshake256Fn);
}

/**
 * Convert hash bytes to BigInt (little-endian) for target comparison
 */
function hashToInt(hashBytes) {
  let result = 0n;
  for (let i = hashBytes.length - 1; i >= 0; i--) {
    result = (result << 8n) | BigInt(hashBytes[i]);
  }
  return result;
}

/**
 * Convert compact bits to target BigInt
 */
function bitsToTarget(bits) {
  const exponent = (bits >> 24) & 0xFF;
  const mantissa = bits & 0x00FFFFFF;
  if (exponent <= 3) {
    return BigInt(mantissa >> (8 * (3 - exponent)));
  }
  return BigInt(mantissa) << BigInt(8 * (exponent - 3));
}

// Helper
function encodeText(str) {
  return new TextEncoder().encode(str);
}

// Export for Web Worker
if (typeof self !== 'undefined') {
  self.HeavyHash = {
    generateMatrix,
    computePow,
    hashToInt,
    bitsToTarget,
    encodeText
  };
}
