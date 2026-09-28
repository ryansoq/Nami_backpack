const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
const fs = require('fs');
const KEY = JSON.parse(fs.readFileSync('/home/ymchang/clawd/.secrets/tn10-ttt-keys.json')).ryan;
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 1100 } });
  await p.goto('https://vprogs-tt.izio.fr', { waitUntil: 'networkidle', timeout: 90000 });
  await p.fill('input[placeholder^="privkey"]', KEY);
  await p.click('button:has-text("Load")');
  await p.waitForTimeout(7000);
  console.log('balances:', await p.evaluate(() => (document.body.innerText.match(/L2:[^\n]*/) || [''])[0]));
  // the withdraw amount box = the decimal input whose container mentions "min withdrawal"
  const handle = await p.evaluateHandle(() => [...document.querySelectorAll('input[inputmode="decimal"]')]
    .find(i => /min withdrawal/.test((i.closest('.card') || {}).innerText || '')));
  const el = handle.asElement(); if (!el) { console.log('withdraw input not found'); process.exit(1); }
  await el.fill('2');
  await p.waitForTimeout(800);
  const btn = p.locator('button', { hasText: /^Withdraw$/ });
  console.log('withdraw button enabled:', await btn.isEnabled());
  await btn.click();
  await p.waitForTimeout(8000);
  const txt = await p.evaluate(() => document.body.innerText);
  const m = txt.match(/submitted [0-9a-f…\.]+ · [\d.]+ KAS → \S+/); console.log('result:', m ? m[0] : '(no submitted line)');
  const e = txt.match(/(minimum withdrawal[^\n]*|amount must[^\n]*|Error[^\n]*)/); if (e) console.log('err:', e[0]);
  await p.waitForTimeout(6000);
  console.log('after:', await p.evaluate(() => (document.body.innerText.match(/L2:[^\n]*/) || [''])[0]));
  await b.close();
})();
