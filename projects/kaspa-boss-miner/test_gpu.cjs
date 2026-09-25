// GPU vs CPU: for each case, pick a target so exactly K of N nonces qualify,
// and require the GPU's hit set and best top word to equal the CPU's.
const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ channel: 'chromium', headless: true,
    args: ['--enable-unsafe-webgpu', '--enable-features=Vulkan', '--use-webgpu-adapter=swiftshader'] });
  const p = await b.newPage();
  p.on('console', m => console.log('[page]', m.text()));
  await p.goto('file://' + __dirname + '/test.html');
  const res = await p.evaluate(async () => {
    const K = window.KHH;
    const m = await K.GpuMiner.create();
    const cases = [
      { seed: 'shiokaze', nonce: 99999n },
      { seed: 'random1', nonce: 0x12345678_9abcdef0n },
      { seed: 'carry', nonce: 0xFFFFFFFFn - 100n },   // crosses the 32-bit boundary mid-batch
      { seed: 'random2', nonce: 7n },
    ];
    const out = [];
    for (const c of cases) {
      const pre = c.seed === 'shiokaze'
        ? Uint8Array.from({length: 32}, (_, i) => [1,0x23,0x45,0x67,0x89,0xab,0xcd,0xef][i % 8])
        : crypto.getRandomValues(new Uint8Array(32));
      const ts = 1234567890 + out.length;
      const N = 256;
      const mat = K.generateMatrix(pre);
      const hs = [];
      for (let i = 0n; i < BigInt(N); i++) {
        const h = K.cpuPow(pre, ts, c.nonce + i, mat);
        let v = 0n; for (let j = 31; j >= 0; j--) v = (v << 8n) | BigInt(h[j]);
        hs.push({ n: c.nonce + i, v, top: Number(v >> 224n) });
      }
      const sorted = [...hs].sort((a, b) => (a.v < b.v ? -1 : 1));
      const Kk = 5, target = sorted[Kk - 1].v;
      m.setJob(pre, ts, target);
      const g = await m.run(c.nonce, N);
      const want = sorted.slice(0, Kk).map(x => x.n.toString()).sort();
      const got = g.hits.map(x => x.toString()).sort();
      out.push({ seed: c.seed, hitCount: g.hitCount, hitsMatch: JSON.stringify(got) === JSON.stringify(want),
                 bestMatch: g.bestTop === sorted[0].top, gpuBest: g.bestTop, cpuBest: sorted[0].top });
    }
    return { adapter: m.adapterInfo.architecture, out };
  });
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
