// 2D dispatch: force a small row width so one batch spans several rows,
// then require the exact CPU hit set (same method as test_gpu.cjs).
const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ channel: 'chromium', headless: true, args: ['--enable-unsafe-webgpu', '--enable-features=Vulkan', '--use-webgpu-adapter=swiftshader'] });
  const p = await b.newPage(); await p.goto('file://' + __dirname + '/test.html');
  console.log(JSON.stringify(await p.evaluate(async () => {
    const K = window.KHH, m = await K.GpuMiner.create(), out = [];
    for (const [base, maxX, count] of [[5000n, 4, 768], [0xFFFFFF00n, 5, 700], [1n, 3, 640]]) {
      const pre = crypto.getRandomValues(new Uint8Array(32)), ts = 77, mat = K.generateMatrix(pre);
      const groups = Math.ceil(count / 64), gx = Math.min(groups, maxX), n = gx * Math.ceil(groups / gx) * 64;
      const hs = [];
      for (let i = 0n; i < BigInt(n); i++) {
        const h = K.fastPow(pre, ts, base + i, mat); let v = 0n; for (let j = 31; j >= 0; j--) v = (v << 8n) | BigInt(h[j]);
        hs.push({ n: base + i, v });
      }
      hs.sort((a, b) => (a.v < b.v ? -1 : 1));
      m.setJob(pre, ts, hs[7].v);            // exactly the 8 smallest qualify
      const r = await m.run(base, count, maxX);
      const want = hs.slice(0, 8).map(x => x.n.toString()).sort(), got = r.hits.map(String).sort();
      out.push({ count: r.count, expected: n, rows: n / 64 / gx, hitCount: r.hitCount, match: JSON.stringify(want) === JSON.stringify(got) });
    }
    return out;
  })));
  await b.close();
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
