const { cshake256 } = require('@noble/hashes/sha3-addons.js');
const { blake2b } = require('@noble/hashes/blake2.js');
globalThis._noble_cshake256 = cshake256;
globalThis._noble_blake2b = blake2b;
