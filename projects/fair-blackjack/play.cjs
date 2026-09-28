const { chromium, devices } = require('/home/ymchang/agent-coding-view/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const ctx = await b.newContext({ ...devices['iPhone 13'] });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('file://' + __dirname + '/blackjack.html'); await p.waitForTimeout(500);
  await p.emulateMedia({ reducedMotion: 'reduce' });
  // 1) decks vs Python
  const cases = await p.evaluate(async () => { const out = []; for (let k = 0; k < 20; k++) { const s = crypto.randomUUID().replace(/-/g,'') + 'ab', c = 'seed' + k; out.push({ s, c, n: k + 1, deck: await __bjApi.shuffle(s, c, k + 1) }); } return out; });
  require('fs').writeFileSync('cases.json', JSON.stringify(cases));
  // 2) play hands, honest then cheat; simple strategy: hit below 17
  const run = async (cheat, n) => {
    await p.evaluate(v => { document.getElementById('cheat').checked = v; }, cheat);
    let ok = 0, caught = 0, swaps = 0, missed = 0;
    for (let k = 0; k < n; k++) {
      await p.click('#deal'); await p.waitForTimeout(150);
      for (let g = 0; g < 10; g++) {
        const st = await p.evaluate(() => ({ phase: __bjApi.state().phase, t: __bjApi.state().player.reduce((a, c) => a, 0) }));
        if (st.phase !== 'player') break;
        const pt = await p.evaluate(() => { const s = __bjApi.state(); let t = 0, a = 0; for (const c of s.player) { const r = c.i % 13; if (!r) { a++; t += 11; } else t += Math.min(10, r + 1); } while (t > 21 && a) { t -= 10; a--; } return t; });
        await p.click(pt < 17 ? '#hit' : '#stand'); await p.waitForTimeout(120);
      }
      await p.waitForFunction(() => __bjApi.state().phase === 'done', null, { timeout: 15000 });
      await p.waitForFunction(() => window.__bj && window.__bj.rows, null, { timeout: 15000 });
      const v = await p.evaluate(() => ({ ...window.__bj, swapped: __bjApi.state().swapped.length }));
      swaps += v.swapped;
      if (v.swapped) { if (v.bad) caught++; else missed++; } else if (v.okCommit && !v.bad) ok++;
      await p.evaluate(() => { window.__bj = null; });
    }
    return { cheat, hands: n, verifiedClean: ok, cheatHands: caught + missed, caught, missed, swaps };
  };
  console.log(JSON.stringify(await run(false, 25)));
  console.log(JSON.stringify(await run(true, 40)));
  console.log('bank text', await p.textContent('#bank'));
  await p.screenshot({ path: 'bj-phone.png', fullPage: true });
  console.log('errors', errs.length ? errs : 'none');
  await b.close();
})();
