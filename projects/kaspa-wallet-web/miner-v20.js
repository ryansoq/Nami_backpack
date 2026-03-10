/**
 * 🌊 Kaspa Web Miner - Web Worker
 * Uses HTTP API proxy instead of wRPC
 */

importScripts('noble-bundle.js');
const cshake256 = globalThis._noble_cshake256;
const blake2b = globalThis._noble_blake2b;

// ─── HeavyHash Implementation ───

class Xoshiro256PlusPlus {
  constructor(s0, s1, s2, s3) {
    this.state = [BigInt(s0)&0xFFFFFFFFFFFFFFFFn, BigInt(s1)&0xFFFFFFFFFFFFFFFFn, BigInt(s2)&0xFFFFFFFFFFFFFFFFn, BigInt(s3)&0xFFFFFFFFFFFFFFFFn];
  }
  next() {
    const s=this.state, M=0xFFFFFFFFFFFFFFFFn;
    let r=(s[0]+s[3])&M; r=(((r<<23n)|(r>>41n))&M)+s[0]; r&=M;
    const t=(s[1]<<17n)&M;
    s[2]^=s[0]; s[3]^=s[1]; s[1]^=s[2]; s[0]^=s[3]; s[2]^=t;
    s[3]=((s[3]<<45n)|(s[3]>>19n))&M;
    return r;
  }
}

function generateMatrix(hashBytes) {
  const view = new DataView(hashBytes.buffer, hashBytes.byteOffset, 32);
  const rng = new Xoshiro256PlusPlus(view.getBigUint64(0,true), view.getBigUint64(8,true), view.getBigUint64(16,true), view.getBigUint64(24,true));
  while (true) {
    const matrix = new Uint16Array(64*64);
    for (let i=0;i<64;i++) for (let j=0;j<64;j+=16) { const v=rng.next(); for(let k=0;k<16;k++) matrix[i*64+j+k]=Number((v>>BigInt(4*k))&0xFn); }
    if (matrixRank(matrix)===64) return matrix;
  }
}

function matrixRank(matrix) {
  const mat=new Float64Array(4096); for(let i=0;i<4096;i++) mat[i]=matrix[i];
  let rank=0; const sel=new Uint8Array(64);
  for(let i=0;i<64;i++){let j=0;while(j<64&&(sel[j]||Math.abs(mat[j*64+i])<1e-9))j++;
    if(j<64){rank++;sel[j]=1;const d=mat[j*64+i];for(let p=i+1;p<64;p++)mat[j*64+p]/=d;
    for(let k=0;k<64;k++)if(k!==j&&Math.abs(mat[k*64+i])>1e-9){const f=mat[k*64+i];for(let p=i+1;p<64;p++)mat[k*64+p]-=mat[j*64+p]*f;}}}
  return rank;
}

function computePow(prePowHash, timestamp, nonce, matrix) {
  const data=new Uint8Array(80); data.set(prePowHash,0);
  const view=new DataView(data.buffer);
  const ts=BigInt(timestamp); view.setUint32(32,Number(ts&0xFFFFFFFFn),true); view.setUint32(36,Number((ts>>32n)&0xFFFFFFFFn),true);
  const nb=BigInt(nonce); view.setUint32(72,Number(nb&0xFFFFFFFFn),true); view.setUint32(76,Number((nb>>32n)&0xFFFFFFFFn),true);
  const enc=new TextEncoder();
  const powHash=cshake256(data,{personalization:enc.encode('ProofOfWorkHash'),dkLen:32});
  return heavyHash(matrix, powHash);
}

function heavyHash(matrix, hashBytes) {
  const v=new Uint16Array(64);
  for(let i=0;i<32;i++){v[i*2]=(hashBytes[i]>>4)&0x0F;v[i*2+1]=hashBytes[i]&0x0F;}
  const p=new Uint32Array(64);
  for(let r=0;r<64;r++){let sum=0;const off=r*64;for(let j=0;j<64;j++)sum+=matrix[off+j]*v[j];p[r]=(sum>>10)&0x0F;}
  const digest=new Uint8Array(32);
  for(let i=0;i<32;i++) digest[i]=hashBytes[i]^(((p[i*2]&0xF)<<4)|(p[i*2+1]&0xF));
  return cshake256(digest,{personalization:new TextEncoder().encode('HeavyHash'),dkLen:32});
}

function hashToInt(h){let r=0n;for(let i=h.length-1;i>=0;i--)r=(r<<8n)|BigInt(h[i]);return r;}
function bitsToTarget(bits){const exp=(bits>>24)&0xFF,man=bits&0xFFFFFF;return exp<=3?BigInt(man>>(8*(3-exp))):BigInt(man)<<BigInt(8*(exp-3));}

// ─── Pre-PoW Hash ───

function calculatePrePowHash(header) {
  const parts=[];
  const vb=new Uint8Array(2); new DataView(vb.buffer).setUint16(0,header.version||0,true); parts.push(vb);
  const parents=header.parents||[];
  parts.push(u64le(parents.length));
  for(const level of parents){const hashes=level.parentHashes||[];parts.push(u64le(hashes.length));for(const h of hashes)parts.push(hexToBytes(h));}
  parts.push(hexToBytes(header.hashMerkleRoot||''));
  parts.push(hexToBytes(header.acceptedIdMerkleRoot||''));
  parts.push(hexToBytes(header.utxoCommitment||''));
  parts.push(u64le(0)); parts.push(u32le(header.bits)); parts.push(u64le(0));
  parts.push(u64le(header.daaScore||0)); parts.push(u64le(header.blueScore||0));
  const bw=header.blueWork||'';
  if(bw){let hex=bw.length%2?'0'+bw:bw;let bytes=hexToBytes(hex);let start=0;while(start<bytes.length&&bytes[start]===0)start++;bytes=bytes.slice(start);parts.push(u64le(bytes.length));if(bytes.length)parts.push(bytes);}else{parts.push(u64le(0));}
  parts.push(hexToBytes(header.pruningPoint||''));
  const total=parts.reduce((s,p)=>s+p.length,0);const buf=new Uint8Array(total);let off=0;for(const p of parts){buf.set(p,off);off+=p.length;}
  return blake2b(buf,{key:new TextEncoder().encode('BlockHash'),dkLen:32});
}

function hexToBytes(hex){if(!hex||!hex.length)return new Uint8Array(32);const b=new Uint8Array(hex.length/2);for(let i=0;i<b.length;i++)b[i]=parseInt(hex.substr(i*2,2),16);return b;}
function u64le(n){const b=new Uint8Array(8);const v=new DataView(b.buffer);const big=BigInt(n);v.setUint32(0,Number(big&0xFFFFFFFFn),true);v.setUint32(4,Number((big>>32n)&0xFFFFFFFFn),true);return b;}
function u32le(n){const b=new Uint8Array(4);new DataView(b.buffer).setUint32(0,n>>>0,true);return b;}

// ─── HTTP API Client ───

async function apiCall(baseUrl, method, params) {
  const url = baseUrl.endsWith('/') ? baseUrl + method : baseUrl + '/' + method;
  self.postMessage({ type: 'log', data: `API: ${method} → ${url}` });
  let resp;
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
  } catch(e) {
    throw new Error(`Fetch failed: ${e.message || e.toString() || 'network error'}`);
  }
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const data = await resp.json();
  if (data.error) throw new Error(typeof data.error === 'string' ? data.error : JSON.stringify(data.error));
  return data.result || data;
}

// ─── Mining Loop ───

let mining = false;
let stats = { hashes: 0, blocks: 0, startTime: 0 };

self.onmessage = async (e) => {
  const { type, data } = e.data;
  if (type === 'start') await doMining(data);
  if (type === 'stop') mining = false;
};

async function doMining({ apiUrl, walletAddress }) {
  mining = true;
  stats = { hashes: 0, blocks: 0, startTime: Date.now() };
  const post = (type, data) => self.postMessage({ type, data });

  post('status', 'connecting');
  
  // Test connection
  try {
    const info = await apiCall(apiUrl, 'getBlockDagInfo', {});
    post('status', 'connected');
    post('log', `Node: DAA=${info.virtualDaaScore || JSON.stringify(info).slice(0,80)}`);
  } catch(e) {
    post('status', 'error');
    post('log', `Connection failed: ${e.message}`);
    mining = false;
    return;
  }

  let errors = 0;
  while (mining) {
    try {
      const tmpl = await apiCall(apiUrl, 'getBlockTemplate', { payAddress: walletAddress, extraData: '' });
      if (!tmpl || !tmpl.block) { errors++; if(errors>5)break; await sleep(1000); continue; }
      errors = 0;

      const block = tmpl.block;
      const header = block.header;
      const prePowHash = calculatePrePowHash(header);
      const target = bitsToTarget(header.bits);
      const matrix = generateMatrix(prePowHash);

      post('log', `Template: DAA=${header.daaScore} bits=0x${header.bits.toString(16)}`);

      const t0 = Date.now();
      let startNonce = BigInt(Math.floor(Math.random() * 0xFFFFFFFF)) << 32n;

      for (let i = 0; mining && Date.now() - t0 < 2000; i++) {
        const nonce = startNonce + BigInt(i);
        const powHash = computePow(prePowHash, header.timestamp, nonce, matrix);
        stats.hashes++;

        if (hashToInt(powHash) <= target) {
          stats.blocks++;
          post('found', { nonce: nonce.toString() });
          try {
            block.header.nonce = nonce.toString();
            const r = await apiCall(apiUrl, 'submitBlock', { block, allowNonDAABlocks: true });
            post('log', `Submit: ${JSON.stringify(r)}`);
            post('accepted');
          } catch(e) { post('log', `Submit err: ${e.message}`); }
          break;
        }

        if (i % 100 === 0) {
          const elapsed = (Date.now() - stats.startTime) / 1000;
          post('stats', { hashes: stats.hashes, hashrate: Math.round(elapsed > 0 ? stats.hashes / elapsed : 0), blocks: stats.blocks, elapsed });
        }
      }
      
      // Update stats after each template
      const elapsed = (Date.now() - stats.startTime) / 1000;
      post('stats', { hashes: stats.hashes, hashrate: Math.round(elapsed > 0 ? stats.hashes / elapsed : 0), blocks: stats.blocks, elapsed });
      
    } catch(e) {
      post('log', `Error: ${e.message}`);
      errors++;
      if (errors > 10) { post('log', 'Too many errors, stopping'); break; }
      await sleep(2000);
    }
  }

  post('status', 'stopped');
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
