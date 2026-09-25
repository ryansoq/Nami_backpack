# kaspa-boss-miner — 雜湊討伐

A boss fight driven by real kHeavyHash mining in the browser (WebGPU, with a
multi-worker CPU fallback). Each hash below the share target is a hit; extra
leading zero bits are crits. Credit per hit = share difficulty × 2^min(b,6)/4,
whose expectation is exactly the difficulty, so damage tracks work done.
Practice mode: no pool, nothing submitted, no KAS earned.

Published: https://claude.ai/artifact/FyP17Ci39iH1Ar2ZECux2X (private)

## Files
- `khh.js` — kHeavyHash: BigInt Keccak (reference + cSHAKE prefix precompute),
  32-bit Keccak CPU path (`fastPow`), WGSL generator, `GpuMiner`
- `game.src.html` + `build.py` → `game.html` (khh.js inlined, single file)
- `ref.mjs` — independent CPU reference on @noble/hashes cshake256

## Trick
Both cSHAKE256 calls fit in one rate block after the personalization block,
which is identical for every nonce. The CPU absorbs it once; the shader starts
from that state, so each hash costs 2 Keccak-f instead of 4.

## Tests (all green 2026-09-25)
- `node ref.mjs` — matches ShioKaze vector d2154c14…dc82
- `node test_cpu.mjs` — prefix-state path == noble, 200 nonces
- `node test_fast.mjs` — fastPow == cpuPow, 500 hashes (8.6 kH/s vs 0.7 kH/s, node 1 core)
- `node test_gpu.cjs` — GPU hit set == CPU's 5 smallest of 256, 4 cases incl. 32-bit carry;
  a swapped-nibble mutation fails all 4
- `node test_2d.cjs` — 2D dispatch indexing, 3 cases across rows
- `node play.cjs gpu|cpu` — headless smoke test of the page

Headless tests run on SwiftShader (software WebGPU, ~14 kH/s): proves
correctness, says nothing about real GPU speed. The shader is unoptimized
(matrix in a storage buffer, per-thread vector array).

## Next
- measure on a real GPU; then matrix in workgroup memory, packed dot products
- v2: real pool shares via a stratum↔WebSocket bridge (browsers can't open raw TCP)
