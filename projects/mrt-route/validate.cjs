const fs = require('fs');
const { buildRouter } = require('./router.js');
const D = JSON.parse(fs.readFileSync('mrt-data.json'));
function score(file, wait, verbose, penalty = 0) {
  const R = buildRouter(D, { wait, penalty });
  const P = JSON.parse(fs.readFileSync(file));
  let err = [], xferMatch = 0, fewMatch = 0, n = 0;
  for (const [k, p] of Object.entries(P)) {
    const [a, b] = k.split('>'), ga = R.group(a), gb = R.group(b);
    if (ga === gb) continue;
    const f = R.route(ga, gb, 'fastest'), w = R.route(ga, gb, 'fewest');
    const offX = p.fastest.walks.map(x => D.alias[x.at] || x.at).join('/');
    const myX = f.transfers.map(x => D.alias[x.at] || x.at).join('/');
    const d = f.minutes - p.fastest.total;
    err.push(Math.abs(d)); n++;
    if (offX === myX) xferMatch++;
    if (w.transfers.length === p.fewest.walks.length) fewMatch++;
    if (verbose) console.log(`${k.padEnd(10)} ${R.nameOf(a)}→${R.nameOf(b)}  official ${p.fastest.total}m [${offX || '直達'}]  model ${f.minutes}m [${myX || '直達'}]  Δ${d >= 0 ? '+' : ''}${d}${offX === myX ? '' : '  ← different transfer'}  | fewest: official ${p.fewest.walks.length}x ${p.fewest.total}m, model ${w.transfers.length}x ${w.minutes}m`);
  }
  err.sort((x, y) => x - y);
  return { n, mae: +(err.reduce((a, b) => a + b, 0) / n).toFixed(2), p90: err[Math.floor(n * 0.9)], max: err[n - 1], sameTransfers: `${xferMatch}/${n}`, fewestCount: `${fewMatch}/${n}` };
}
const TRAIN = process.env.TRAIN || 'planner_train_parsed.json';
const grid = [0, 0.5, 1, 1.5, 2, 3];
let best = null;
console.log('TRAIN (fit wait, penalty):');
for (const w of grid) for (const pen of [0, 1, 2, 3, 4]) {
  const r = score(TRAIN, w, false, pen);
  const cost = r.mae + (1 - eval(r.sameTransfers)) * 2;   // prefer matching the official transfer choice too
  if (!best || cost < best.cost) best = { w, pen, cost, r };
}
console.log(' best', JSON.stringify(best));
console.log('\nVALIDATION (held out), wait', best.w, 'penalty', best.pen);
console.log(JSON.stringify(score('planner_val_parsed.json', best.w, !!process.env.V, best.pen)));
