import { createRequire } from 'module';
import { hex } from './ref.mjs';
const K = createRequire(import.meta.url)('./khh.js');
let bad = 0;
for (let c = 0; c < 5; c++) {
  const pre = c === 0 ? Uint8Array.from({length: 32}, (_, i) => [1,0x23,0x45,0x67,0x89,0xab,0xcd,0xef][i % 8]) : Uint8Array.from({length: 32}, () => Math.random() * 256 | 0);
  const m = K.generateMatrix(pre), ts = 1234567890 + c;
  for (let i = 0; i < 100; i++) {
    const n = (c === 2 ? 0xFFFFFFF0n : 99999n) + BigInt(i * 31);
    if (hex(K.fastPow(pre, ts, n, m)) !== hex(K.cpuPow(pre, ts, n, m))) bad++;
  }
}
console.log('fastPow vs cpuPow, 500 hashes, mismatches:', bad);
const pre = new Uint8Array(32).fill(7), m = K.generateMatrix(pre);
for (const [name, f] of [['cpuPow', K.cpuPow], ['fastPow', K.fastPow]]) {
  const t0 = performance.now(); let n = 0;
  while (performance.now() - t0 < 1000) { f(pre, 1, BigInt(n), m); n++; }
  console.log(name, n, 'H/s (node, one core)');
}
