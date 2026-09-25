// Query the official planner for many OD pairs; save the raw result text per pair.
const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
const fs = require('fs');
const pairs = JSON.parse(fs.readFileSync(process.argv[2]));
const out = fs.existsSync('planner.json') ? JSON.parse(fs.readFileSync('planner.json')) : {};
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  for (const [from, to] of pairs) {
    const key = `${from}>${to}`;
    if (out[key]) continue;
    try {
      await p.goto('https://web.metro.taipei/pages2026/WebRoutePlan?embed=true', { waitUntil: 'networkidle', timeout: 60000 });
      await p.selectOption('.departure .stationlist select', from);
      await p.selectOption('.arrival .stationlist select', to);
      await Promise.all([p.waitForLoadState('networkidle'), p.click('#btnQuery')]);
      await p.waitForTimeout(800);
      const txt = await p.evaluate(() => document.body.innerText);
      const i = txt.indexOf('最小旅行時間');
      out[key] = txt.slice(i).replace(/\n{2,}/g, '\n');
      console.log(key, 'ok', (out[key].match(/(\d+)分鐘｜/) || [])[1]);
    } catch (e) { console.log(key, 'ERR', e.message.split('\n')[0]); }
    fs.writeFileSync('planner.json', JSON.stringify(out, null, 1));
  }
  await b.close();
})();
