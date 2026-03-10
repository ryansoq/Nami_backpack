(() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __esm = (fn, res) => function __init() {
    return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
  };
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // node_modules/@noble/hashes/_u64.js
  function fromBig(n, le = false) {
    if (le)
      return { h: Number(n & U32_MASK64), l: Number(n >> _32n & U32_MASK64) };
    return { h: Number(n >> _32n & U32_MASK64) | 0, l: Number(n & U32_MASK64) | 0 };
  }
  function split(lst, le = false) {
    const len = lst.length;
    let Ah = new Uint32Array(len);
    let Al = new Uint32Array(len);
    for (let i = 0; i < len; i++) {
      const { h, l } = fromBig(lst[i], le);
      [Ah[i], Al[i]] = [h, l];
    }
    return [Ah, Al];
  }
  function add(Ah, Al, Bh, Bl) {
    const l = (Al >>> 0) + (Bl >>> 0);
    return { h: Ah + Bh + (l / 2 ** 32 | 0) | 0, l: l | 0 };
  }
  var U32_MASK64, _32n, rotrSH, rotrSL, rotrBH, rotrBL, rotr32H, rotr32L, rotlSH, rotlSL, rotlBH, rotlBL, add3L, add3H;
  var init_u64 = __esm({
    "node_modules/@noble/hashes/_u64.js"() {
      U32_MASK64 = /* @__PURE__ */ BigInt(2 ** 32 - 1);
      _32n = /* @__PURE__ */ BigInt(32);
      rotrSH = (h, l, s) => h >>> s | l << 32 - s;
      rotrSL = (h, l, s) => h << 32 - s | l >>> s;
      rotrBH = (h, l, s) => h << 64 - s | l >>> s - 32;
      rotrBL = (h, l, s) => h >>> s - 32 | l << 64 - s;
      rotr32H = (_h, l) => l;
      rotr32L = (h, _l) => h;
      rotlSH = (h, l, s) => h << s | l >>> 32 - s;
      rotlSL = (h, l, s) => l << s | h >>> 32 - s;
      rotlBH = (h, l, s) => l << s - 32 | h >>> 64 - s;
      rotlBL = (h, l, s) => h << s - 32 | l >>> 64 - s;
      add3L = (Al, Bl, Cl) => (Al >>> 0) + (Bl >>> 0) + (Cl >>> 0);
      add3H = (low, Ah, Bh, Ch) => Ah + Bh + Ch + (low / 2 ** 32 | 0) | 0;
    }
  });

  // node_modules/@noble/hashes/utils.js
  function isBytes(a) {
    return a instanceof Uint8Array || ArrayBuffer.isView(a) && a.constructor.name === "Uint8Array";
  }
  function anumber(n, title = "") {
    if (!Number.isSafeInteger(n) || n < 0) {
      const prefix = title && `"${title}" `;
      throw new Error(`${prefix}expected integer >= 0, got ${n}`);
    }
  }
  function abytes(value, length, title = "") {
    const bytes = isBytes(value);
    const len = value?.length;
    const needsLen = length !== void 0;
    if (!bytes || needsLen && len !== length) {
      const prefix = title && `"${title}" `;
      const ofLen = needsLen ? ` of length ${length}` : "";
      const got = bytes ? `length=${len}` : `type=${typeof value}`;
      throw new Error(prefix + "expected Uint8Array" + ofLen + ", got " + got);
    }
    return value;
  }
  function aexists(instance, checkFinished = true) {
    if (instance.destroyed)
      throw new Error("Hash instance has been destroyed");
    if (checkFinished && instance.finished)
      throw new Error("Hash#digest() has already been called");
  }
  function aoutput(out, instance) {
    abytes(out, void 0, "digestInto() output");
    const min = instance.outputLen;
    if (out.length < min) {
      throw new Error('"digestInto() output" expected to be of length >=' + min);
    }
  }
  function u32(arr) {
    return new Uint32Array(arr.buffer, arr.byteOffset, Math.floor(arr.byteLength / 4));
  }
  function clean(...arrays) {
    for (let i = 0; i < arrays.length; i++) {
      arrays[i].fill(0);
    }
  }
  function rotr(word, shift) {
    return word << 32 - shift | word >>> shift;
  }
  function byteSwap(word) {
    return word << 24 & 4278190080 | word << 8 & 16711680 | word >>> 8 & 65280 | word >>> 24 & 255;
  }
  function byteSwap32(arr) {
    for (let i = 0; i < arr.length; i++) {
      arr[i] = byteSwap(arr[i]);
    }
    return arr;
  }
  function utf8ToBytes(str) {
    if (typeof str !== "string")
      throw new Error("string expected");
    return new Uint8Array(new TextEncoder().encode(str));
  }
  function kdfInputToBytes(data, errorTitle = "") {
    if (typeof data === "string")
      return utf8ToBytes(data);
    return abytes(data, void 0, errorTitle);
  }
  function createHasher(hashCons, info = {}) {
    const hashC = (msg, opts) => hashCons(opts).update(msg).digest();
    const tmp = hashCons(void 0);
    hashC.outputLen = tmp.outputLen;
    hashC.blockLen = tmp.blockLen;
    hashC.create = (opts) => hashCons(opts);
    Object.assign(hashC, info);
    return Object.freeze(hashC);
  }
  var isLE, swap8IfBE, swap32IfBE;
  var init_utils = __esm({
    "node_modules/@noble/hashes/utils.js"() {
      isLE = /* @__PURE__ */ (() => new Uint8Array(new Uint32Array([287454020]).buffer)[0] === 68)();
      swap8IfBE = isLE ? (n) => n : (n) => byteSwap(n);
      swap32IfBE = isLE ? (u) => u : byteSwap32;
    }
  });

  // node_modules/@noble/hashes/sha3.js
  function keccakP(s, rounds = 24) {
    const B = new Uint32Array(5 * 2);
    for (let round = 24 - rounds; round < 24; round++) {
      for (let x = 0; x < 10; x++)
        B[x] = s[x] ^ s[x + 10] ^ s[x + 20] ^ s[x + 30] ^ s[x + 40];
      for (let x = 0; x < 10; x += 2) {
        const idx1 = (x + 8) % 10;
        const idx0 = (x + 2) % 10;
        const B0 = B[idx0];
        const B1 = B[idx0 + 1];
        const Th = rotlH(B0, B1, 1) ^ B[idx1];
        const Tl = rotlL(B0, B1, 1) ^ B[idx1 + 1];
        for (let y = 0; y < 50; y += 10) {
          s[x + y] ^= Th;
          s[x + y + 1] ^= Tl;
        }
      }
      let curH = s[2];
      let curL = s[3];
      for (let t = 0; t < 24; t++) {
        const shift = SHA3_ROTL[t];
        const Th = rotlH(curH, curL, shift);
        const Tl = rotlL(curH, curL, shift);
        const PI = SHA3_PI[t];
        curH = s[PI];
        curL = s[PI + 1];
        s[PI] = Th;
        s[PI + 1] = Tl;
      }
      for (let y = 0; y < 50; y += 10) {
        for (let x = 0; x < 10; x++)
          B[x] = s[y + x];
        for (let x = 0; x < 10; x++)
          s[y + x] ^= ~B[(x + 2) % 10] & B[(x + 4) % 10];
      }
      s[0] ^= SHA3_IOTA_H[round];
      s[1] ^= SHA3_IOTA_L[round];
    }
    clean(B);
  }
  var _0n, _1n, _2n, _7n, _256n, _0x71n, SHA3_PI, SHA3_ROTL, _SHA3_IOTA, IOTAS, SHA3_IOTA_H, SHA3_IOTA_L, rotlH, rotlL, Keccak;
  var init_sha3 = __esm({
    "node_modules/@noble/hashes/sha3.js"() {
      init_u64();
      init_utils();
      _0n = BigInt(0);
      _1n = BigInt(1);
      _2n = BigInt(2);
      _7n = BigInt(7);
      _256n = BigInt(256);
      _0x71n = BigInt(113);
      SHA3_PI = [];
      SHA3_ROTL = [];
      _SHA3_IOTA = [];
      for (let round = 0, R = _1n, x = 1, y = 0; round < 24; round++) {
        [x, y] = [y, (2 * x + 3 * y) % 5];
        SHA3_PI.push(2 * (5 * y + x));
        SHA3_ROTL.push((round + 1) * (round + 2) / 2 % 64);
        let t = _0n;
        for (let j = 0; j < 7; j++) {
          R = (R << _1n ^ (R >> _7n) * _0x71n) % _256n;
          if (R & _2n)
            t ^= _1n << (_1n << BigInt(j)) - _1n;
        }
        _SHA3_IOTA.push(t);
      }
      IOTAS = split(_SHA3_IOTA, true);
      SHA3_IOTA_H = IOTAS[0];
      SHA3_IOTA_L = IOTAS[1];
      rotlH = (h, l, s) => s > 32 ? rotlBH(h, l, s) : rotlSH(h, l, s);
      rotlL = (h, l, s) => s > 32 ? rotlBL(h, l, s) : rotlSL(h, l, s);
      Keccak = class _Keccak {
        state;
        pos = 0;
        posOut = 0;
        finished = false;
        state32;
        destroyed = false;
        blockLen;
        suffix;
        outputLen;
        enableXOF = false;
        rounds;
        // NOTE: we accept arguments in bytes instead of bits here.
        constructor(blockLen, suffix, outputLen, enableXOF = false, rounds = 24) {
          this.blockLen = blockLen;
          this.suffix = suffix;
          this.outputLen = outputLen;
          this.enableXOF = enableXOF;
          this.rounds = rounds;
          anumber(outputLen, "outputLen");
          if (!(0 < blockLen && blockLen < 200))
            throw new Error("only keccak-f1600 function is supported");
          this.state = new Uint8Array(200);
          this.state32 = u32(this.state);
        }
        clone() {
          return this._cloneInto();
        }
        keccak() {
          swap32IfBE(this.state32);
          keccakP(this.state32, this.rounds);
          swap32IfBE(this.state32);
          this.posOut = 0;
          this.pos = 0;
        }
        update(data) {
          aexists(this);
          abytes(data);
          const { blockLen, state } = this;
          const len = data.length;
          for (let pos = 0; pos < len; ) {
            const take = Math.min(blockLen - this.pos, len - pos);
            for (let i = 0; i < take; i++)
              state[this.pos++] ^= data[pos++];
            if (this.pos === blockLen)
              this.keccak();
          }
          return this;
        }
        finish() {
          if (this.finished)
            return;
          this.finished = true;
          const { state, suffix, pos, blockLen } = this;
          state[pos] ^= suffix;
          if ((suffix & 128) !== 0 && pos === blockLen - 1)
            this.keccak();
          state[blockLen - 1] ^= 128;
          this.keccak();
        }
        writeInto(out) {
          aexists(this, false);
          abytes(out);
          this.finish();
          const bufferOut = this.state;
          const { blockLen } = this;
          for (let pos = 0, len = out.length; pos < len; ) {
            if (this.posOut >= blockLen)
              this.keccak();
            const take = Math.min(blockLen - this.posOut, len - pos);
            out.set(bufferOut.subarray(this.posOut, this.posOut + take), pos);
            this.posOut += take;
            pos += take;
          }
          return out;
        }
        xofInto(out) {
          if (!this.enableXOF)
            throw new Error("XOF is not possible for this instance");
          return this.writeInto(out);
        }
        xof(bytes) {
          anumber(bytes);
          return this.xofInto(new Uint8Array(bytes));
        }
        digestInto(out) {
          aoutput(out, this);
          if (this.finished)
            throw new Error("digest() was already called");
          this.writeInto(out);
          this.destroy();
          return out;
        }
        digest() {
          return this.digestInto(new Uint8Array(this.outputLen));
        }
        destroy() {
          this.destroyed = true;
          clean(this.state);
        }
        _cloneInto(to) {
          const { blockLen, suffix, outputLen, rounds, enableXOF } = this;
          to ||= new _Keccak(blockLen, suffix, outputLen, enableXOF, rounds);
          to.state32.set(this.state32);
          to.pos = this.pos;
          to.posOut = this.posOut;
          to.finished = this.finished;
          to.rounds = rounds;
          to.suffix = suffix;
          to.outputLen = outputLen;
          to.enableXOF = enableXOF;
          to.destroyed = this.destroyed;
          return to;
        }
      };
    }
  });

  // node_modules/@noble/hashes/sha3-addons.js
  var sha3_addons_exports = {};
  __export(sha3_addons_exports, {
    HopMAC128: () => HopMAC128,
    HopMAC256: () => HopMAC256,
    _KMAC: () => _KMAC,
    _KangarooTwelve: () => _KangarooTwelve,
    _KeccakPRG: () => _KeccakPRG,
    _ParallelHash: () => _ParallelHash,
    _TupleHash: () => _TupleHash,
    cshake128: () => cshake128,
    cshake256: () => cshake256,
    keccakprg: () => keccakprg,
    kmac128: () => kmac128,
    kmac128xof: () => kmac128xof,
    kmac256: () => kmac256,
    kmac256xof: () => kmac256xof,
    kt128: () => kt128,
    kt256: () => kt256,
    parallelhash128: () => parallelhash128,
    parallelhash128xof: () => parallelhash128xof,
    parallelhash256: () => parallelhash256,
    parallelhash256xof: () => parallelhash256xof,
    tuplehash128: () => tuplehash128,
    tuplehash128xof: () => tuplehash128xof,
    tuplehash256: () => tuplehash256,
    tuplehash256xof: () => tuplehash256xof,
    turboshake128: () => turboshake128,
    turboshake256: () => turboshake256
  });
  function leftEncode(n) {
    n = BigInt(n);
    const res = [Number(n & _ffn)];
    n >>= _8n;
    for (; n > 0; n >>= _8n)
      res.unshift(Number(n & _ffn));
    res.unshift(res.length);
    return new Uint8Array(res);
  }
  function rightEncode(n) {
    n = BigInt(n);
    const res = [Number(n & _ffn)];
    n >>= _8n;
    for (; n > 0; n >>= _8n)
      res.unshift(Number(n & _ffn));
    res.push(res.length);
    return new Uint8Array(res);
  }
  function chooseLen(opts, outputLen) {
    return opts.dkLen === void 0 ? outputLen : opts.dkLen;
  }
  function cshakePers(hash, opts = {}) {
    if (!opts || opts.personalization === void 0 && opts.NISTfn === void 0)
      return hash;
    const blockLenBytes = leftEncode(hash.blockLen);
    const fn = opts.NISTfn === void 0 ? EMPTY_BUFFER : kdfInputToBytes(opts.NISTfn);
    const fnLen = leftEncode(_8n * BigInt(fn.length));
    const pers = abytesOrZero(opts.personalization, "personalization");
    const persLen = leftEncode(_8n * BigInt(pers.length));
    if (!fn.length && !pers.length)
      return hash;
    hash.suffix = 4;
    hash.update(blockLenBytes).update(fnLen).update(fn).update(persLen).update(pers);
    let totalLen = blockLenBytes.length + fnLen.length + fn.length + persLen.length + pers.length;
    hash.update(getPadding(totalLen, hash.blockLen));
    return hash;
  }
  function genKmac(blockLen, outputLen, xof = false) {
    const kmac = (key, message, opts) => kmac.create(key, opts).update(message).digest();
    kmac.create = (key, opts = {}) => new _KMAC(blockLen, chooseLen(opts, outputLen), xof, key, opts);
    return kmac;
  }
  function genTuple(blockLen, outputLen, xof = false) {
    const tuple = (messages, opts) => {
      const h = tuple.create(opts);
      if (!Array.isArray(messages))
        throw new Error("expected array of messages");
      for (const msg of messages)
        h.update(msg);
      return h.digest();
    };
    tuple.create = (opts = {}) => new _TupleHash(blockLen, chooseLen(opts, outputLen), xof, opts);
    return tuple;
  }
  function genPrl(blockLen, outputLen, leaf, xof = false) {
    const parallel = (message, opts) => parallel.create(opts).update(message).digest();
    parallel.create = (opts = {}) => new _ParallelHash(blockLen, chooseLen(opts, outputLen), () => leaf.create({ dkLen: 2 * outputLen }), xof, opts);
    parallel.outputLen = outputLen;
    parallel.blockLen = blockLen;
    return parallel;
  }
  function rightEncodeK12(n) {
    n = BigInt(n);
    const res = [];
    for (; n > 0; n >>= _8n)
      res.unshift(Number(n & _ffn));
    res.push(res.length);
    return Uint8Array.from(res);
  }
  var _8n, _ffn, abytesOrZero, getPadding, gencShake, cshake128, cshake256, _KMAC, kmac128, kmac256, kmac128xof, kmac256xof, _TupleHash, tuplehash128, tuplehash256, tuplehash128xof, tuplehash256xof, _ParallelHash, parallelhash128, parallelhash256, parallelhash128xof, parallelhash256xof, genTurbo, turboshake128, turboshake256, EMPTY_BUFFER, _KangarooTwelve, kt128, kt256, genHopMAC, HopMAC128, HopMAC256, _KeccakPRG, keccakprg;
  var init_sha3_addons = __esm({
    "node_modules/@noble/hashes/sha3-addons.js"() {
      init_sha3();
      init_utils();
      _8n = /* @__PURE__ */ BigInt(8);
      _ffn = /* @__PURE__ */ BigInt(255);
      abytesOrZero = (buf, title = "") => {
        if (buf === void 0)
          return EMPTY_BUFFER;
        abytes(buf, void 0, title);
        return buf;
      };
      getPadding = (len, block) => new Uint8Array((block - len % block) % block);
      gencShake = (suffix, blockLen, outputLen) => createHasher((opts = {}) => cshakePers(new Keccak(blockLen, suffix, chooseLen(opts, outputLen), true), opts));
      cshake128 = /* @__PURE__ */ gencShake(31, 168, 16);
      cshake256 = /* @__PURE__ */ gencShake(31, 136, 32);
      _KMAC = class extends Keccak {
        constructor(blockLen, outputLen, enableXOF, key, opts = {}) {
          super(blockLen, 31, outputLen, enableXOF);
          cshakePers(this, { NISTfn: "KMAC", personalization: opts.personalization });
          abytes(key, void 0, "key");
          const blockLenBytes = leftEncode(this.blockLen);
          const keyLen = leftEncode(_8n * BigInt(key.length));
          this.update(blockLenBytes).update(keyLen).update(key);
          const totalLen = blockLenBytes.length + keyLen.length + key.length;
          this.update(getPadding(totalLen, this.blockLen));
        }
        finish() {
          if (!this.finished)
            this.update(rightEncode(this.enableXOF ? 0 : _8n * BigInt(this.outputLen)));
          super.finish();
        }
        _cloneInto(to) {
          if (!to) {
            to = Object.create(Object.getPrototypeOf(this), {});
            to.state = this.state.slice();
            to.blockLen = this.blockLen;
            to.state32 = u32(to.state);
          }
          return super._cloneInto(to);
        }
        clone() {
          return this._cloneInto();
        }
      };
      kmac128 = /* @__PURE__ */ genKmac(168, 16);
      kmac256 = /* @__PURE__ */ genKmac(136, 32);
      kmac128xof = /* @__PURE__ */ genKmac(168, 16, true);
      kmac256xof = /* @__PURE__ */ genKmac(136, 32, true);
      _TupleHash = class __TupleHash extends Keccak {
        constructor(blockLen, outputLen, enableXOF, opts = {}) {
          super(blockLen, 31, outputLen, enableXOF);
          cshakePers(this, { NISTfn: "TupleHash", personalization: opts.personalization });
          this.update = (data) => {
            abytes(data);
            super.update(leftEncode(_8n * BigInt(data.length)));
            super.update(data);
            return this;
          };
        }
        finish() {
          if (!this.finished)
            super.update(rightEncode(this.enableXOF ? 0 : _8n * BigInt(this.outputLen)));
          super.finish();
        }
        _cloneInto(to) {
          to ||= new __TupleHash(this.blockLen, this.outputLen, this.enableXOF);
          return super._cloneInto(to);
        }
        clone() {
          return this._cloneInto();
        }
      };
      tuplehash128 = /* @__PURE__ */ genTuple(168, 16);
      tuplehash256 = /* @__PURE__ */ genTuple(136, 32);
      tuplehash128xof = /* @__PURE__ */ genTuple(168, 16, true);
      tuplehash256xof = /* @__PURE__ */ genTuple(136, 32, true);
      _ParallelHash = class __ParallelHash extends Keccak {
        leafHash;
        leafCons;
        chunkPos = 0;
        // Position of current block in chunk
        chunksDone = 0;
        // How many chunks we already have
        chunkLen;
        constructor(blockLen, outputLen, leafCons, enableXOF, opts = {}) {
          super(blockLen, 31, outputLen, enableXOF);
          cshakePers(this, { NISTfn: "ParallelHash", personalization: opts.personalization });
          this.leafCons = leafCons;
          let { blockLen: B = 8 } = opts;
          anumber(B);
          this.chunkLen = B;
          super.update(leftEncode(B));
          this.update = (data) => {
            abytes(data);
            const { chunkLen, leafCons: leafCons2 } = this;
            for (let pos = 0, len = data.length; pos < len; ) {
              if (this.chunkPos == chunkLen || !this.leafHash) {
                if (this.leafHash) {
                  super.update(this.leafHash.digest());
                  this.chunksDone++;
                }
                this.leafHash = leafCons2();
                this.chunkPos = 0;
              }
              const take = Math.min(chunkLen - this.chunkPos, len - pos);
              this.leafHash.update(data.subarray(pos, pos + take));
              this.chunkPos += take;
              pos += take;
            }
            return this;
          };
        }
        finish() {
          if (this.finished)
            return;
          if (this.leafHash) {
            super.update(this.leafHash.digest());
            this.chunksDone++;
          }
          super.update(rightEncode(this.chunksDone));
          super.update(rightEncode(this.enableXOF ? 0 : _8n * BigInt(this.outputLen)));
          super.finish();
        }
        _cloneInto(to) {
          to ||= new __ParallelHash(this.blockLen, this.outputLen, this.leafCons, this.enableXOF);
          if (this.leafHash)
            to.leafHash = this.leafHash._cloneInto(to.leafHash);
          to.chunkPos = this.chunkPos;
          to.chunkLen = this.chunkLen;
          to.chunksDone = this.chunksDone;
          return super._cloneInto(to);
        }
        destroy() {
          super.destroy.call(this);
          if (this.leafHash)
            this.leafHash.destroy();
        }
        clone() {
          return this._cloneInto();
        }
      };
      parallelhash128 = /* @__PURE__ */ genPrl(168, 16, cshake128);
      parallelhash256 = /* @__PURE__ */ genPrl(136, 32, cshake256);
      parallelhash128xof = /* @__PURE__ */ genPrl(168, 16, cshake128, true);
      parallelhash256xof = /* @__PURE__ */ genPrl(136, 32, cshake256, true);
      genTurbo = (blockLen, outputLen) => createHasher((opts = {}) => {
        const D = opts.D === void 0 ? 31 : opts.D;
        if (!Number.isSafeInteger(D) || D < 1 || D > 127)
          throw new Error('"D" (domain separation byte) must be 0x01..0x7f, got: ' + D);
        return new Keccak(blockLen, D, opts.dkLen === void 0 ? outputLen : opts.dkLen, true, 12);
      });
      turboshake128 = /* @__PURE__ */ genTurbo(168, 32);
      turboshake256 = /* @__PURE__ */ genTurbo(136, 64);
      EMPTY_BUFFER = /* @__PURE__ */ Uint8Array.of();
      _KangarooTwelve = class __KangarooTwelve extends Keccak {
        chunkLen = 8192;
        leafHash;
        leafLen;
        personalization;
        chunkPos = 0;
        // Position of current block in chunk
        chunksDone = 0;
        // How many chunks we already have
        constructor(blockLen, leafLen, outputLen, rounds, opts) {
          super(blockLen, 7, outputLen, true, rounds);
          this.leafLen = leafLen;
          this.personalization = abytesOrZero(opts.personalization, "personalization");
        }
        update(data) {
          abytes(data);
          const { chunkLen, blockLen, leafLen, rounds } = this;
          for (let pos = 0, len = data.length; pos < len; ) {
            if (this.chunkPos == chunkLen) {
              if (this.leafHash)
                super.update(this.leafHash.digest());
              else {
                this.suffix = 6;
                super.update(Uint8Array.from([3, 0, 0, 0, 0, 0, 0, 0]));
              }
              this.leafHash = new Keccak(blockLen, 11, leafLen, false, rounds);
              this.chunksDone++;
              this.chunkPos = 0;
            }
            const take = Math.min(chunkLen - this.chunkPos, len - pos);
            const chunk = data.subarray(pos, pos + take);
            if (this.leafHash)
              this.leafHash.update(chunk);
            else
              super.update(chunk);
            this.chunkPos += take;
            pos += take;
          }
          return this;
        }
        finish() {
          if (this.finished)
            return;
          const { personalization } = this;
          this.update(personalization).update(rightEncodeK12(personalization.length));
          if (this.leafHash) {
            super.update(this.leafHash.digest());
            super.update(rightEncodeK12(this.chunksDone));
            super.update(Uint8Array.from([255, 255]));
          }
          super.finish.call(this);
        }
        destroy() {
          super.destroy.call(this);
          if (this.leafHash)
            this.leafHash.destroy();
          this.personalization = EMPTY_BUFFER;
        }
        _cloneInto(to) {
          const { blockLen, leafLen, leafHash, outputLen, rounds } = this;
          to ||= new __KangarooTwelve(blockLen, leafLen, outputLen, rounds, {});
          super._cloneInto(to);
          if (leafHash)
            to.leafHash = leafHash._cloneInto(to.leafHash);
          to.personalization.set(this.personalization);
          to.leafLen = this.leafLen;
          to.chunkPos = this.chunkPos;
          to.chunksDone = this.chunksDone;
          return to;
        }
        clone() {
          return this._cloneInto();
        }
      };
      kt128 = /* @__PURE__ */ createHasher((opts = {}) => new _KangarooTwelve(168, 32, chooseLen(opts, 32), 12, opts));
      kt256 = /* @__PURE__ */ createHasher((opts = {}) => new _KangarooTwelve(136, 64, chooseLen(opts, 64), 12, opts));
      genHopMAC = (hash) => (key, message, personalization, dkLen) => hash(key, { personalization: hash(message, { personalization }), dkLen });
      HopMAC128 = /* @__PURE__ */ genHopMAC(kt128);
      HopMAC256 = /* @__PURE__ */ genHopMAC(kt256);
      _KeccakPRG = class __KeccakPRG extends Keccak {
        rate;
        constructor(capacity) {
          anumber(capacity);
          const rate = 1600 - capacity;
          const rho = rate - 2;
          if (capacity < 0 || capacity > 1600 - 10 || rho % 8)
            throw new Error("invalid capacity");
          super(rho / 8, 0, 0, true);
          this.rate = rate;
          this.posOut = Math.floor((rate + 7) / 8);
        }
        keccak() {
          this.state[this.pos] ^= 1;
          this.state[this.blockLen] ^= 2;
          super.keccak();
          this.pos = 0;
          this.posOut = 0;
        }
        update(data) {
          super.update(data);
          this.posOut = this.blockLen;
          return this;
        }
        finish() {
        }
        digestInto(_out) {
          throw new Error("digest is not allowed, use .fetch instead");
        }
        addEntropy(seed) {
          this.update(seed);
        }
        randomBytes(length) {
          return this.xof(length);
        }
        clean() {
          if (this.rate < 1600 / 2 + 1)
            throw new Error("rate is too low to use .forget()");
          this.keccak();
          for (let i = 0; i < this.blockLen; i++)
            this.state[i] = 0;
          this.pos = this.blockLen;
          this.keccak();
          this.posOut = this.blockLen;
        }
        _cloneInto(to) {
          const { rate } = this;
          to ||= new __KeccakPRG(1600 - rate);
          super._cloneInto(to);
          to.rate = rate;
          return to;
        }
        clone() {
          return this._cloneInto();
        }
      };
      keccakprg = (capacity = 254) => new _KeccakPRG(capacity);
    }
  });

  // node_modules/@noble/hashes/_blake.js
  function G1s(a, b, c, d, x) {
    a = a + b + x | 0;
    d = rotr(d ^ a, 16);
    c = c + d | 0;
    b = rotr(b ^ c, 12);
    return { a, b, c, d };
  }
  function G2s(a, b, c, d, x) {
    a = a + b + x | 0;
    d = rotr(d ^ a, 8);
    c = c + d | 0;
    b = rotr(b ^ c, 7);
    return { a, b, c, d };
  }
  var BSIGMA;
  var init_blake = __esm({
    "node_modules/@noble/hashes/_blake.js"() {
      init_utils();
      BSIGMA = /* @__PURE__ */ Uint8Array.from([
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        14,
        10,
        4,
        8,
        9,
        15,
        13,
        6,
        1,
        12,
        0,
        2,
        11,
        7,
        5,
        3,
        11,
        8,
        12,
        0,
        5,
        2,
        15,
        13,
        10,
        14,
        3,
        6,
        7,
        1,
        9,
        4,
        7,
        9,
        3,
        1,
        13,
        12,
        11,
        14,
        2,
        6,
        5,
        10,
        4,
        0,
        15,
        8,
        9,
        0,
        5,
        7,
        2,
        4,
        10,
        15,
        14,
        1,
        11,
        12,
        6,
        8,
        3,
        13,
        2,
        12,
        6,
        10,
        0,
        11,
        8,
        3,
        4,
        13,
        7,
        5,
        15,
        14,
        1,
        9,
        12,
        5,
        1,
        15,
        14,
        13,
        4,
        10,
        0,
        7,
        6,
        3,
        9,
        2,
        8,
        11,
        13,
        11,
        7,
        14,
        12,
        1,
        3,
        9,
        5,
        0,
        15,
        4,
        8,
        6,
        2,
        10,
        6,
        15,
        14,
        9,
        11,
        3,
        0,
        8,
        12,
        2,
        13,
        7,
        1,
        4,
        10,
        5,
        10,
        2,
        8,
        4,
        7,
        6,
        1,
        5,
        15,
        11,
        9,
        14,
        3,
        12,
        13,
        0,
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        14,
        10,
        4,
        8,
        9,
        15,
        13,
        6,
        1,
        12,
        0,
        2,
        11,
        7,
        5,
        3,
        // Blake1, unused in others
        11,
        8,
        12,
        0,
        5,
        2,
        15,
        13,
        10,
        14,
        3,
        6,
        7,
        1,
        9,
        4,
        7,
        9,
        3,
        1,
        13,
        12,
        11,
        14,
        2,
        6,
        5,
        10,
        4,
        0,
        15,
        8,
        9,
        0,
        5,
        7,
        2,
        4,
        10,
        15,
        14,
        1,
        11,
        12,
        6,
        8,
        3,
        13,
        2,
        12,
        6,
        10,
        0,
        11,
        8,
        3,
        4,
        13,
        7,
        5,
        15,
        14,
        1,
        9
      ]);
    }
  });

  // node_modules/@noble/hashes/_md.js
  var SHA256_IV;
  var init_md = __esm({
    "node_modules/@noble/hashes/_md.js"() {
      SHA256_IV = /* @__PURE__ */ Uint32Array.from([
        1779033703,
        3144134277,
        1013904242,
        2773480762,
        1359893119,
        2600822924,
        528734635,
        1541459225
      ]);
    }
  });

  // node_modules/@noble/hashes/blake2.js
  var blake2_exports = {};
  __export(blake2_exports, {
    _BLAKE2: () => _BLAKE2,
    _BLAKE2b: () => _BLAKE2b,
    _BLAKE2s: () => _BLAKE2s,
    blake2b: () => blake2b,
    blake2s: () => blake2s,
    compress: () => compress
  });
  function G1b(a, b, c, d, msg, x) {
    const Xl = msg[x], Xh = msg[x + 1];
    let Al = BBUF[2 * a], Ah = BBUF[2 * a + 1];
    let Bl = BBUF[2 * b], Bh = BBUF[2 * b + 1];
    let Cl = BBUF[2 * c], Ch = BBUF[2 * c + 1];
    let Dl = BBUF[2 * d], Dh = BBUF[2 * d + 1];
    let ll = add3L(Al, Bl, Xl);
    Ah = add3H(ll, Ah, Bh, Xh);
    Al = ll | 0;
    ({ Dh, Dl } = { Dh: Dh ^ Ah, Dl: Dl ^ Al });
    ({ Dh, Dl } = { Dh: rotr32H(Dh, Dl), Dl: rotr32L(Dh, Dl) });
    ({ h: Ch, l: Cl } = add(Ch, Cl, Dh, Dl));
    ({ Bh, Bl } = { Bh: Bh ^ Ch, Bl: Bl ^ Cl });
    ({ Bh, Bl } = { Bh: rotrSH(Bh, Bl, 24), Bl: rotrSL(Bh, Bl, 24) });
    BBUF[2 * a] = Al, BBUF[2 * a + 1] = Ah;
    BBUF[2 * b] = Bl, BBUF[2 * b + 1] = Bh;
    BBUF[2 * c] = Cl, BBUF[2 * c + 1] = Ch;
    BBUF[2 * d] = Dl, BBUF[2 * d + 1] = Dh;
  }
  function G2b(a, b, c, d, msg, x) {
    const Xl = msg[x], Xh = msg[x + 1];
    let Al = BBUF[2 * a], Ah = BBUF[2 * a + 1];
    let Bl = BBUF[2 * b], Bh = BBUF[2 * b + 1];
    let Cl = BBUF[2 * c], Ch = BBUF[2 * c + 1];
    let Dl = BBUF[2 * d], Dh = BBUF[2 * d + 1];
    let ll = add3L(Al, Bl, Xl);
    Ah = add3H(ll, Ah, Bh, Xh);
    Al = ll | 0;
    ({ Dh, Dl } = { Dh: Dh ^ Ah, Dl: Dl ^ Al });
    ({ Dh, Dl } = { Dh: rotrSH(Dh, Dl, 16), Dl: rotrSL(Dh, Dl, 16) });
    ({ h: Ch, l: Cl } = add(Ch, Cl, Dh, Dl));
    ({ Bh, Bl } = { Bh: Bh ^ Ch, Bl: Bl ^ Cl });
    ({ Bh, Bl } = { Bh: rotrBH(Bh, Bl, 63), Bl: rotrBL(Bh, Bl, 63) });
    BBUF[2 * a] = Al, BBUF[2 * a + 1] = Ah;
    BBUF[2 * b] = Bl, BBUF[2 * b + 1] = Bh;
    BBUF[2 * c] = Cl, BBUF[2 * c + 1] = Ch;
    BBUF[2 * d] = Dl, BBUF[2 * d + 1] = Dh;
  }
  function checkBlake2Opts(outputLen, opts = {}, keyLen, saltLen, persLen) {
    anumber(keyLen);
    if (outputLen < 0 || outputLen > keyLen)
      throw new Error("outputLen bigger than keyLen");
    const { key, salt, personalization } = opts;
    if (key !== void 0 && (key.length < 1 || key.length > keyLen))
      throw new Error('"key" expected to be undefined or of length=1..' + keyLen);
    if (salt !== void 0)
      abytes(salt, saltLen, "salt");
    if (personalization !== void 0)
      abytes(personalization, persLen, "personalization");
  }
  function compress(s, offset, msg, rounds, v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14, v15) {
    let j = 0;
    for (let i = 0; i < rounds; i++) {
      ({ a: v0, b: v4, c: v8, d: v12 } = G1s(v0, v4, v8, v12, msg[offset + s[j++]]));
      ({ a: v0, b: v4, c: v8, d: v12 } = G2s(v0, v4, v8, v12, msg[offset + s[j++]]));
      ({ a: v1, b: v5, c: v9, d: v13 } = G1s(v1, v5, v9, v13, msg[offset + s[j++]]));
      ({ a: v1, b: v5, c: v9, d: v13 } = G2s(v1, v5, v9, v13, msg[offset + s[j++]]));
      ({ a: v2, b: v6, c: v10, d: v14 } = G1s(v2, v6, v10, v14, msg[offset + s[j++]]));
      ({ a: v2, b: v6, c: v10, d: v14 } = G2s(v2, v6, v10, v14, msg[offset + s[j++]]));
      ({ a: v3, b: v7, c: v11, d: v15 } = G1s(v3, v7, v11, v15, msg[offset + s[j++]]));
      ({ a: v3, b: v7, c: v11, d: v15 } = G2s(v3, v7, v11, v15, msg[offset + s[j++]]));
      ({ a: v0, b: v5, c: v10, d: v15 } = G1s(v0, v5, v10, v15, msg[offset + s[j++]]));
      ({ a: v0, b: v5, c: v10, d: v15 } = G2s(v0, v5, v10, v15, msg[offset + s[j++]]));
      ({ a: v1, b: v6, c: v11, d: v12 } = G1s(v1, v6, v11, v12, msg[offset + s[j++]]));
      ({ a: v1, b: v6, c: v11, d: v12 } = G2s(v1, v6, v11, v12, msg[offset + s[j++]]));
      ({ a: v2, b: v7, c: v8, d: v13 } = G1s(v2, v7, v8, v13, msg[offset + s[j++]]));
      ({ a: v2, b: v7, c: v8, d: v13 } = G2s(v2, v7, v8, v13, msg[offset + s[j++]]));
      ({ a: v3, b: v4, c: v9, d: v14 } = G1s(v3, v4, v9, v14, msg[offset + s[j++]]));
      ({ a: v3, b: v4, c: v9, d: v14 } = G2s(v3, v4, v9, v14, msg[offset + s[j++]]));
    }
    return { v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14, v15 };
  }
  var B2B_IV, BBUF, _BLAKE2, _BLAKE2b, blake2b, B2S_IV, _BLAKE2s, blake2s;
  var init_blake2 = __esm({
    "node_modules/@noble/hashes/blake2.js"() {
      init_blake();
      init_md();
      init_u64();
      init_utils();
      B2B_IV = /* @__PURE__ */ Uint32Array.from([
        4089235720,
        1779033703,
        2227873595,
        3144134277,
        4271175723,
        1013904242,
        1595750129,
        2773480762,
        2917565137,
        1359893119,
        725511199,
        2600822924,
        4215389547,
        528734635,
        327033209,
        1541459225
      ]);
      BBUF = /* @__PURE__ */ new Uint32Array(32);
      _BLAKE2 = class {
        buffer;
        buffer32;
        finished = false;
        destroyed = false;
        length = 0;
        pos = 0;
        blockLen;
        outputLen;
        constructor(blockLen, outputLen) {
          anumber(blockLen);
          anumber(outputLen);
          this.blockLen = blockLen;
          this.outputLen = outputLen;
          this.buffer = new Uint8Array(blockLen);
          this.buffer32 = u32(this.buffer);
        }
        update(data) {
          aexists(this);
          abytes(data);
          const { blockLen, buffer, buffer32 } = this;
          const len = data.length;
          const offset = data.byteOffset;
          const buf = data.buffer;
          for (let pos = 0; pos < len; ) {
            if (this.pos === blockLen) {
              swap32IfBE(buffer32);
              this.compress(buffer32, 0, false);
              swap32IfBE(buffer32);
              this.pos = 0;
            }
            const take = Math.min(blockLen - this.pos, len - pos);
            const dataOffset = offset + pos;
            if (take === blockLen && !(dataOffset % 4) && pos + take < len) {
              const data32 = new Uint32Array(buf, dataOffset, Math.floor((len - pos) / 4));
              swap32IfBE(data32);
              for (let pos32 = 0; pos + blockLen < len; pos32 += buffer32.length, pos += blockLen) {
                this.length += blockLen;
                this.compress(data32, pos32, false);
              }
              swap32IfBE(data32);
              continue;
            }
            buffer.set(data.subarray(pos, pos + take), this.pos);
            this.pos += take;
            this.length += take;
            pos += take;
          }
          return this;
        }
        digestInto(out) {
          aexists(this);
          aoutput(out, this);
          const { pos, buffer32 } = this;
          this.finished = true;
          clean(this.buffer.subarray(pos));
          swap32IfBE(buffer32);
          this.compress(buffer32, 0, true);
          swap32IfBE(buffer32);
          const out32 = u32(out);
          this.get().forEach((v, i) => out32[i] = swap8IfBE(v));
        }
        digest() {
          const { buffer, outputLen } = this;
          this.digestInto(buffer);
          const res = buffer.slice(0, outputLen);
          this.destroy();
          return res;
        }
        _cloneInto(to) {
          const { buffer, length, finished, destroyed, outputLen, pos } = this;
          to ||= new this.constructor({ dkLen: outputLen });
          to.set(...this.get());
          to.buffer.set(buffer);
          to.destroyed = destroyed;
          to.finished = finished;
          to.length = length;
          to.pos = pos;
          to.outputLen = outputLen;
          return to;
        }
        clone() {
          return this._cloneInto();
        }
      };
      _BLAKE2b = class extends _BLAKE2 {
        // Same as SHA-512, but LE
        v0l = B2B_IV[0] | 0;
        v0h = B2B_IV[1] | 0;
        v1l = B2B_IV[2] | 0;
        v1h = B2B_IV[3] | 0;
        v2l = B2B_IV[4] | 0;
        v2h = B2B_IV[5] | 0;
        v3l = B2B_IV[6] | 0;
        v3h = B2B_IV[7] | 0;
        v4l = B2B_IV[8] | 0;
        v4h = B2B_IV[9] | 0;
        v5l = B2B_IV[10] | 0;
        v5h = B2B_IV[11] | 0;
        v6l = B2B_IV[12] | 0;
        v6h = B2B_IV[13] | 0;
        v7l = B2B_IV[14] | 0;
        v7h = B2B_IV[15] | 0;
        constructor(opts = {}) {
          const olen = opts.dkLen === void 0 ? 64 : opts.dkLen;
          super(128, olen);
          checkBlake2Opts(olen, opts, 64, 16, 16);
          let { key, personalization, salt } = opts;
          let keyLength = 0;
          if (key !== void 0) {
            abytes(key, void 0, "key");
            keyLength = key.length;
          }
          this.v0l ^= this.outputLen | keyLength << 8 | 1 << 16 | 1 << 24;
          if (salt !== void 0) {
            abytes(salt, void 0, "salt");
            const slt = u32(salt);
            this.v4l ^= swap8IfBE(slt[0]);
            this.v4h ^= swap8IfBE(slt[1]);
            this.v5l ^= swap8IfBE(slt[2]);
            this.v5h ^= swap8IfBE(slt[3]);
          }
          if (personalization !== void 0) {
            abytes(personalization, void 0, "personalization");
            const pers = u32(personalization);
            this.v6l ^= swap8IfBE(pers[0]);
            this.v6h ^= swap8IfBE(pers[1]);
            this.v7l ^= swap8IfBE(pers[2]);
            this.v7h ^= swap8IfBE(pers[3]);
          }
          if (key !== void 0) {
            const tmp = new Uint8Array(this.blockLen);
            tmp.set(key);
            this.update(tmp);
          }
        }
        // prettier-ignore
        get() {
          let { v0l, v0h, v1l, v1h, v2l, v2h, v3l, v3h, v4l, v4h, v5l, v5h, v6l, v6h, v7l, v7h } = this;
          return [v0l, v0h, v1l, v1h, v2l, v2h, v3l, v3h, v4l, v4h, v5l, v5h, v6l, v6h, v7l, v7h];
        }
        // prettier-ignore
        set(v0l, v0h, v1l, v1h, v2l, v2h, v3l, v3h, v4l, v4h, v5l, v5h, v6l, v6h, v7l, v7h) {
          this.v0l = v0l | 0;
          this.v0h = v0h | 0;
          this.v1l = v1l | 0;
          this.v1h = v1h | 0;
          this.v2l = v2l | 0;
          this.v2h = v2h | 0;
          this.v3l = v3l | 0;
          this.v3h = v3h | 0;
          this.v4l = v4l | 0;
          this.v4h = v4h | 0;
          this.v5l = v5l | 0;
          this.v5h = v5h | 0;
          this.v6l = v6l | 0;
          this.v6h = v6h | 0;
          this.v7l = v7l | 0;
          this.v7h = v7h | 0;
        }
        compress(msg, offset, isLast) {
          this.get().forEach((v, i) => BBUF[i] = v);
          BBUF.set(B2B_IV, 16);
          let { h, l } = fromBig(BigInt(this.length));
          BBUF[24] = B2B_IV[8] ^ l;
          BBUF[25] = B2B_IV[9] ^ h;
          if (isLast) {
            BBUF[28] = ~BBUF[28];
            BBUF[29] = ~BBUF[29];
          }
          let j = 0;
          const s = BSIGMA;
          for (let i = 0; i < 12; i++) {
            G1b(0, 4, 8, 12, msg, offset + 2 * s[j++]);
            G2b(0, 4, 8, 12, msg, offset + 2 * s[j++]);
            G1b(1, 5, 9, 13, msg, offset + 2 * s[j++]);
            G2b(1, 5, 9, 13, msg, offset + 2 * s[j++]);
            G1b(2, 6, 10, 14, msg, offset + 2 * s[j++]);
            G2b(2, 6, 10, 14, msg, offset + 2 * s[j++]);
            G1b(3, 7, 11, 15, msg, offset + 2 * s[j++]);
            G2b(3, 7, 11, 15, msg, offset + 2 * s[j++]);
            G1b(0, 5, 10, 15, msg, offset + 2 * s[j++]);
            G2b(0, 5, 10, 15, msg, offset + 2 * s[j++]);
            G1b(1, 6, 11, 12, msg, offset + 2 * s[j++]);
            G2b(1, 6, 11, 12, msg, offset + 2 * s[j++]);
            G1b(2, 7, 8, 13, msg, offset + 2 * s[j++]);
            G2b(2, 7, 8, 13, msg, offset + 2 * s[j++]);
            G1b(3, 4, 9, 14, msg, offset + 2 * s[j++]);
            G2b(3, 4, 9, 14, msg, offset + 2 * s[j++]);
          }
          this.v0l ^= BBUF[0] ^ BBUF[16];
          this.v0h ^= BBUF[1] ^ BBUF[17];
          this.v1l ^= BBUF[2] ^ BBUF[18];
          this.v1h ^= BBUF[3] ^ BBUF[19];
          this.v2l ^= BBUF[4] ^ BBUF[20];
          this.v2h ^= BBUF[5] ^ BBUF[21];
          this.v3l ^= BBUF[6] ^ BBUF[22];
          this.v3h ^= BBUF[7] ^ BBUF[23];
          this.v4l ^= BBUF[8] ^ BBUF[24];
          this.v4h ^= BBUF[9] ^ BBUF[25];
          this.v5l ^= BBUF[10] ^ BBUF[26];
          this.v5h ^= BBUF[11] ^ BBUF[27];
          this.v6l ^= BBUF[12] ^ BBUF[28];
          this.v6h ^= BBUF[13] ^ BBUF[29];
          this.v7l ^= BBUF[14] ^ BBUF[30];
          this.v7h ^= BBUF[15] ^ BBUF[31];
          clean(BBUF);
        }
        destroy() {
          this.destroyed = true;
          clean(this.buffer32);
          this.set(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        }
      };
      blake2b = /* @__PURE__ */ createHasher((opts) => new _BLAKE2b(opts));
      B2S_IV = /* @__PURE__ */ SHA256_IV.slice();
      _BLAKE2s = class extends _BLAKE2 {
        // Internal state, same as SHA-256
        v0 = B2S_IV[0] | 0;
        v1 = B2S_IV[1] | 0;
        v2 = B2S_IV[2] | 0;
        v3 = B2S_IV[3] | 0;
        v4 = B2S_IV[4] | 0;
        v5 = B2S_IV[5] | 0;
        v6 = B2S_IV[6] | 0;
        v7 = B2S_IV[7] | 0;
        constructor(opts = {}) {
          const olen = opts.dkLen === void 0 ? 32 : opts.dkLen;
          super(64, olen);
          checkBlake2Opts(olen, opts, 32, 8, 8);
          let { key, personalization, salt } = opts;
          let keyLength = 0;
          if (key !== void 0) {
            abytes(key, void 0, "key");
            keyLength = key.length;
          }
          this.v0 ^= this.outputLen | keyLength << 8 | 1 << 16 | 1 << 24;
          if (salt !== void 0) {
            abytes(salt, void 0, "salt");
            const slt = u32(salt);
            this.v4 ^= swap8IfBE(slt[0]);
            this.v5 ^= swap8IfBE(slt[1]);
          }
          if (personalization !== void 0) {
            abytes(personalization, void 0, "personalization");
            const pers = u32(personalization);
            this.v6 ^= swap8IfBE(pers[0]);
            this.v7 ^= swap8IfBE(pers[1]);
          }
          if (key !== void 0) {
            const tmp = new Uint8Array(this.blockLen);
            tmp.set(key);
            this.update(tmp);
          }
        }
        get() {
          const { v0, v1, v2, v3, v4, v5, v6, v7 } = this;
          return [v0, v1, v2, v3, v4, v5, v6, v7];
        }
        // prettier-ignore
        set(v0, v1, v2, v3, v4, v5, v6, v7) {
          this.v0 = v0 | 0;
          this.v1 = v1 | 0;
          this.v2 = v2 | 0;
          this.v3 = v3 | 0;
          this.v4 = v4 | 0;
          this.v5 = v5 | 0;
          this.v6 = v6 | 0;
          this.v7 = v7 | 0;
        }
        compress(msg, offset, isLast) {
          const { h, l } = fromBig(BigInt(this.length));
          const { v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14, v15 } = compress(BSIGMA, offset, msg, 10, this.v0, this.v1, this.v2, this.v3, this.v4, this.v5, this.v6, this.v7, B2S_IV[0], B2S_IV[1], B2S_IV[2], B2S_IV[3], l ^ B2S_IV[4], h ^ B2S_IV[5], isLast ? ~B2S_IV[6] : B2S_IV[6], B2S_IV[7]);
          this.v0 ^= v0 ^ v8;
          this.v1 ^= v1 ^ v9;
          this.v2 ^= v2 ^ v10;
          this.v3 ^= v3 ^ v11;
          this.v4 ^= v4 ^ v12;
          this.v5 ^= v5 ^ v13;
          this.v6 ^= v6 ^ v14;
          this.v7 ^= v7 ^ v15;
        }
        destroy() {
          this.destroyed = true;
          clean(this.buffer32);
          this.set(0, 0, 0, 0, 0, 0, 0, 0);
        }
      };
      blake2s = /* @__PURE__ */ createHasher((opts) => new _BLAKE2s(opts));
    }
  });

  // bundle-entry.js
  var { cshake256: cshake2562 } = (init_sha3_addons(), __toCommonJS(sha3_addons_exports));
  var { blake2b: blake2b2 } = (init_blake2(), __toCommonJS(blake2_exports));
  globalThis._noble_cshake256 = cshake2562;
  globalThis._noble_blake2b = blake2b2;
})();
/*! Bundled license information:

@noble/hashes/utils.js:
  (*! noble-hashes - MIT License (c) 2022 Paul Miller (paulmillr.com) *)
*/
