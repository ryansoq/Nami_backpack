// Headless smoke test: start mining, let it fight, check the numbers move and nothing throws.
const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
(async () => {
  const gpu = process.argv[2] !== 'cpu';
  const args = gpu ? ['--enable-unsafe-webgpu', '--enable-features=Vulkan', '--use-webgpu-adapter=swiftshader'] : ['--disable-features=WebGPU,Vulkan', '--disable-gpu'];
  const b = await chromium.launch({ channel: 'chromium', headless: true, args });
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.text()); });
  await p.goto('file://' + __dirname + '/game.html');
  await p.waitForFunction(() => !document.getElementById('go').disabled, null, { timeout: 60000 });
  console.log('device:', await p.textContent('#device'));
  await p.click('#go');
  for (let i = 0; i < 4; i++) {
    await p.waitForTimeout(5000);
    const s = await p.evaluate(() => ({ stage: __game.stage, hpLeft: __game.hpLeft, total: __game.total, hits: __game.hits, crits: __game.crits, rate: Math.round(__game.rate), diff: Math.round(__game.diff) }));
    console.log(JSON.stringify(s));
  }
  await p.screenshot({ path: __dirname + `/shot-${gpu ? 'gpu' : 'cpu'}.png` });
  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
