const { chromium } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
const fs = require('fs');
const KEY = JSON.parse(fs.readFileSync('/home/ymchang/clawd/.secrets/tn10-ttt-keys.json')).ryan;
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 1100 } });
  p.on('console', m => { if (['error','warning'].includes(m.type())) console.log('[console]', m.type(), m.text().slice(0, 300)); });
  p.on('pageerror', e => console.log('[pageerror]', e.message.slice(0, 300)));

  // Workaround for the demo's claim bug: composition.ts hands ALL pool UTXOs (272) to claim_tx,
  // which rejects more than MAX_DELEGATE_INPUTS = 8. Serve a patched module that picks the
  // largest UTXOs until they cover the leaf (<= 8). Only affects this headless session.
  await p.route('**/src/composition.ts*', async route => {
    const resp = await route.fetch(); let body = await resp.text();
    const from = 'delegates.map((d) => new UtxoCandidate(';
    if (!body.includes(from)) { console.log('PATCH POINT NOT FOUND'); return route.fulfill({ response: resp }); }
    body = body.replace(from, '(() => { const s = [...delegates].sort((a, b) => (b.amount > a.amount ? 1 : b.amount < a.amount ? -1 : 0)); const out = []; let t = 0n; for (const d of s) { out.push(d); t += d.amount; if (t >= args.leaf_amount || out.length === 8) break; } console.warn("[patched] delegate inputs", out.length, "of", delegates.length); return out; })().map((d) => new UtxoCandidate(');
    route.fulfill({ response: resp, body });
  });
  await p.goto('https://vprogs-tt.izio.fr', { waitUntil: 'networkidle', timeout: 90000 });
  await p.fill('input[placeholder^="privkey"]', KEY);
  await p.click('button:has-text("Load")');
  await p.waitForTimeout(8000);
  const bal = () => p.evaluate(() => (document.body.innerText.match(/L2:[^\n]*/) || [''])[0]);
  console.log('before:', await bal());
  const txt = await p.evaluate(() => { const t = document.body.innerText; const i = t.search(/claim exits/i); return t.slice(i, i + 400); });
  console.log('CLAIM section:', JSON.stringify(txt));
  const btns = p.locator('button', { hasText: /claim/i });
  const n = await btns.count(); console.log('claim buttons', n);
  for (let i = 0; i < n; i++) {
    const bt = btns.nth(i);
    if (await bt.isEnabled()) { await bt.click(); console.log('clicked claim', i); await p.waitForTimeout(6000); }
  }
  await p.waitForTimeout(4000);
  const after = await p.evaluate(() => [...document.querySelectorAll('.err,.ok')].map(e => e.className + ': ' + e.innerText).join(' | '));
  console.log('err/ok boxes:', after);
  console.log('activity:', await p.evaluate(() => { const t = document.body.innerText; const i = t.search(/\nACTIVITY|\nactivity/); return t.slice(i, i + 500); }));
  await p.waitForTimeout(8000);
  console.log('after:', await bal());
  await b.close();
})();
