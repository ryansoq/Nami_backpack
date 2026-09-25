import { createRequire } from 'module';
import { computePow, generateMatrix as refMatrix, hex } from './ref.mjs';
const K = createRequire(import.meta.url)('./khh.js');
const pre = Uint8Array.from({length: 32}, (_, i) => [0x01,0x23,0x45,0x67,0x89,0xab,0xcd,0xef][i % 8]);
const m = K.generateMatrix(pre), rm = refMatrix(pre);
console.log('matrix equal:', m.every((x, i) => x === rm[i]));
let bad = 0;
for (let n = 0; n < 200; n++) {
  const nonce = 99999 + n * 7919;
  if (hex(K.cpuPow(pre, 1234567890, nonce, m)) !== hex(computePow(pre, 1234567890, nonce, rm))) bad++;
}
console.log('prefix-state path vs noble, 200 nonces, mismatches:', bad);
console.log('vector:', hex(K.cpuPow(pre, 1234567890, 99999, m)));
